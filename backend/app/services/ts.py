"""Хранилище ТС (п. 4.4.8–4.4.13 ТПР): иерархия, карточки ТМ/ЕО, записи о ТС Б316–Б319, импорт xlsx, логи."""
import io
from datetime import date, datetime, timezone

from openpyxl import Workbook, load_workbook
from sqlalchemy import and_, func, or_, select

from app.db import SessionLocal
from app.errors import RuleError, not_found
from app.models import (
    EquipmentUnit, ImportLog, ImportLogEntry, TechPlace, TsMeasure, TsMeasurement, TsMessage, TsRecord,
)
from app.permissions import CurrentUser
from app.services.common import audit, fmt_date, get_setting, next_number, notify, parse_date

CONFIRM = ("Подтверждено", "Требует подтверждения")
RECORD_TYPES = ("Диагностическое обследование", "Выполнение ТОиР", "Выполнение КР")
OBJECT_STATUSES = ("Исправное", "Работоспособное", "Ограниченно работоспособное", "Неработоспособное", "В эксплуатации")
STATE_RANK = {"Исправное": 0, "Работоспособное": 1, "В эксплуатации": 1, "Ограниченно работоспособное": 2, "Неработоспособное": 3}


def scope(stmt, model, user: CurrentUser):
    return stmt.where(model.deo == user.deo) if user.deo else stmt


def iso(d) -> str:
    return d.isoformat() if d else ""


async def aggregate_state(session, eo_ids: list[int] | None = None, tm_ids: list[int] | None = None) -> dict:
    """R-B316-03: по каждому атрибуту — значение из самой поздней записи, где он заполнен."""
    q = select(TsRecord).where(TsRecord.record_status == "Действует")
    if eo_ids is not None:
        q = q.where(TsRecord.eo_id.in_(eo_ids or [-1]))
    if tm_ids is not None:
        q = q.where(TsRecord.tm_id.in_(tm_ids or [-1]))
    rows = (await session.execute(q.order_by(TsRecord.reg_date.desc(), TsRecord.id.desc()))).scalars().all()
    out: dict[str, dict] = {}
    for r in rows:
        for key in ([f"eo:{r.eo_id}"] if r.eo_id else []) + ([f"tm:{r.tm_id}"] if r.tm_id and not r.eo_id else []):
            agg = out.setdefault(key, {"recordId": r.id, "recordNumber": r.number, "fix": iso(r.reg_date), "confirm": r.confirm_status, "statusDate": iso(r.status_date or r.reg_date)})
            for attr, val in (("st", r.object_status), ("desc", r.description), ("wear", r.wear_percent), ("next", iso(r.next_inspection)),
                              ("life", r.residual_life_years)):
                if attr not in agg and val not in (None, ""):
                    agg[attr] = val
    return out


def eo_row(eo: EquipmentUnit, agg: dict | None = None) -> dict:
    a = agg or {}
    return {"id": eo.id, "code": eo.code, "name": eo.name, "tmId": eo.tm_id, "tmCode": eo.tm.code if eo.tm else "", "tmName": eo.tm.name if eo.tm else "",
            "deo": eo.deo, "class": eo.eq_class, "type": eo.eq_type, "model": eo.model, "factoryNumber": eo.factory_number, "techNumber": eo.tech_number,
            "inventory": eo.inventory_number, "position": eo.position, "origin": eo.origin, "sync": eo.sync_status, "syncNote": eo.sync_note,
            "parentId": eo.parent_id, "fix": a.get("fix", ""), "next": a.get("next", ""), "st": a.get("st", ""), "wear": a.get("wear"),
            "desc": a.get("desc", ""), "life": a.get("life"), "confirm": eo.confirm_status, "statusDate": iso(eo.status_date) or a.get("statusDate", ""),
            "recordStatus": eo.record_status, "createdAt": iso(eo.created_at.date() if eo.created_at else None), "updatedAt": iso(eo.updated_at.date() if eo.updated_at else None)}


def tm_row(tm: TechPlace, agg: dict | None = None, has_children: bool = True) -> dict:
    a = agg or {}
    return {"id": tm.id, "code": tm.code, "name": tm.name, "parentId": tm.parent_id, "deo": tm.deo, "fix": a.get("fix", ""), "next": a.get("next", ""),
            "st": a.get("st", ""), "desc": a.get("desc", ""), "confirm": tm.confirm_status, "statusDate": iso(tm.status_date), "recordStatus": tm.record_status,
            "createdAt": iso(tm.created_at.date() if tm.created_at else None), "updatedAt": iso(tm.updated_at.date() if tm.updated_at else None),
            "hasChildren": has_children}


async def hierarchy_children(session, user: CurrentUser, node: str | None, group: str = "tm") -> list[dict]:
    """Ленивое дерево: корень → ТМ верхнего уровня; ТМ → дочерние ТМ и ЕО; ЕО → дочерние ЕО и записи о ТС."""
    out = []
    if group in ("class", "model", "deo") and not node:
        col = {"class": EquipmentUnit.eq_class, "model": EquipmentUnit.model, "deo": EquipmentUnit.deo}[group]
        q = scope(select(col, func.count()).group_by(col), EquipmentUnit, user)
        for val, cnt in (await session.execute(q)).all():
            out.append({"key": f"grp:{group}:{val}", "type": "GROUP", "name": f"{val or '—'} ({cnt})", "hasChildren": True})
        return sorted(out, key=lambda x: x["name"])
    if node and node.startswith("grp:"):
        _, g, val = node.split(":", 2)
        col = {"class": EquipmentUnit.eq_class, "model": EquipmentUnit.model, "deo": EquipmentUnit.deo}[g]
        eos = (await session.execute(scope(select(EquipmentUnit).where(col == val).order_by(EquipmentUnit.name), EquipmentUnit, user))).scalars().all()
        agg = await aggregate_state(session, eo_ids=[e.id for e in eos])
        return [{"key": f"eo:{e.id}", "type": "ЕО", **eo_row(e, agg.get(f"eo:{e.id}")), "hasChildren": True} for e in eos]
    if not node:
        tms = (await session.execute(scope(select(TechPlace).where(TechPlace.parent_id.is_(None)).order_by(TechPlace.code), TechPlace, user))).scalars().all()
        agg = await aggregate_state(session, tm_ids=[t.id for t in tms])
        return [{"key": f"tm:{t.id}", "type": "ТМ", **tm_row(t, agg.get(f"tm:{t.id}"))} for t in tms]
    kind, _, sid = node.partition(":")
    nid = int(sid)
    if kind == "tm":
        tms = (await session.execute(scope(select(TechPlace).where(TechPlace.parent_id == nid).order_by(TechPlace.code), TechPlace, user))).scalars().all()
        eos = (await session.execute(scope(select(EquipmentUnit).where(EquipmentUnit.tm_id == nid, EquipmentUnit.parent_id.is_(None)).order_by(EquipmentUnit.name), EquipmentUnit, user))).scalars().all()
        agg = await aggregate_state(session, tm_ids=[t.id for t in tms])
        agg |= await aggregate_state(session, eo_ids=[e.id for e in eos])
        out = [{"key": f"tm:{t.id}", "type": "ТМ", **tm_row(t, agg.get(f"tm:{t.id}"))} for t in tms]
        out += [{"key": f"eo:{e.id}", "type": "ЕО", **eo_row(e, agg.get(f"eo:{e.id}")), "hasChildren": True} for e in eos]
        return out
    if kind == "eo":
        eos = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.parent_id == nid).order_by(EquipmentUnit.id))).scalars().all()
        agg = await aggregate_state(session, eo_ids=[e.id for e in eos])
        out = [{"key": f"eo:{e.id}", "type": "ЕО", **eo_row(e, agg.get(f"eo:{e.id}")), "hasChildren": True} for e in eos]
        recs = (await session.execute(select(TsRecord).where(TsRecord.eo_id == nid).order_by(TsRecord.reg_date.desc()).limit(10))).scalars().all()
        out += [{"key": f"ts:{r.id}", "type": "ТС", **record_row(r), "hasChildren": False} for r in recs]
        return out
    return []


def record_row(r: TsRecord) -> dict:
    return {"id": r.id, "number": r.number, "recordType": r.record_type, "tmId": r.tm_id, "tmCode": r.tm.code if r.tm else "", "eoId": r.eo_id,
            "eoName": r.eo.name if r.eo else "", "eoCode": r.eo.code if r.eo else "", "deo": r.deo, "regDate": iso(r.reg_date), "st": r.object_status,
            "wear": r.wear_percent, "desc": r.description, "next": iso(r.next_inspection), "life": r.residual_life_years, "confirm": r.confirm_status,
            "statusDate": iso(r.status_date), "recordStatus": r.record_status, "notes": r.notes, "source": r.source, "reportId": r.report_id,
            "resultId": r.result_id, "createdAt": iso(r.created_at.date() if r.created_at else None), "updatedAt": iso(r.updated_at.date() if r.updated_at else None)}


async def list_records(session, user: CurrentUser, q: str = "", confirm: str = "", rtype: str = "", eo_id: int | None = None):
    stmt = scope(select(TsRecord), TsRecord, user)
    if q:
        like = f"%{q}%"
        stmt = stmt.join(EquipmentUnit, TsRecord.eo_id == EquipmentUnit.id, isouter=True).where(or_(TsRecord.number.ilike(like), EquipmentUnit.name.ilike(like), TsRecord.description.ilike(like)))
    if confirm:
        stmt = stmt.where(TsRecord.confirm_status == confirm)
    if rtype:
        stmt = stmt.where(TsRecord.record_type == rtype)
    if eo_id:
        stmt = stmt.where(TsRecord.eo_id == eo_id)
    return stmt.order_by(TsRecord.reg_date.desc(), TsRecord.id.desc())


async def get_record(session, rid: int, user: CurrentUser) -> TsRecord:
    r = await session.get(TsRecord, rid, populate_existing=True)
    if not r:
        raise not_found("Запись о ТС")
    if not user.deo_allowed(r.deo):
        raise RuleError("Нет доступа к данным другого ДЭО", "ДЭО", 403)
    return r


async def _period_check(session, d: date | None):
    closed = parse_date((await get_setting(session, "report_period", {})).get("closed_to"))
    if closed and d and d <= closed:
        raise RuleError(f"Отчётный период закрыт по {fmt_date(closed)}: данные доступны только для чтения", "W-7.1")


async def create_record(session, data: dict, user: CurrentUser) -> TsRecord:
    if data.get("recordType") not in RECORD_TYPES[1:]:
        raise RuleError("Вручную создаются записи по результатам КР и ТОиР; записи по ДО создаются автоматически", "R-NSI-01")
    eo = await session.get(EquipmentUnit, data.get("eoId") or 0)
    if not eo:
        raise RuleError("Выберите единицу оборудования", "R-NSI-01", fields={"eoId": "Обязательное поле"})
    if not user.deo_allowed(eo.deo):
        raise RuleError("Нет доступа к данным другого ДЭО", "ДЭО", 403)
    if not data.get("st"):
        raise RuleError("Укажите актуальный статус объекта", "R-NSI-01", fields={"st": "Обязательное поле"})
    reg = parse_date(data.get("regDate")) or date.today()
    await _period_check(session, reg)
    number = await next_number(session, TsRecord, TsRecord.number, f"Б316-{reg.year}-")
    r = TsRecord(number=number, record_type=data["recordType"], tm_id=eo.tm_id, eo_id=eo.id, deo=eo.deo, reg_date=reg, object_status=data["st"],
                 description=data.get("desc", ""), notes=data.get("notes", ""), confirm_status="Требует подтверждения", source="manual",
                 next_inspection=parse_date(data.get("next")), wear_percent=data.get("wear"))
    session.add(r)
    await session.flush()
    await notify(session, "BDTS.OTVTS", f"Запись технического состояния № {number} внесена и требует подтверждения", eo.name, f"/ts-records/{r.id}",
                 type_="Предупреждение", deo=eo.deo, rule_id=11)
    await audit(session, user, "ts.create", "ts_record", r.id)
    return r


async def flag_changed(session, r: TsRecord, user: CurrentUser, what: str):
    """R-B316-02: правка поля «требует подтверждения» переводит запись в «Требует подтверждения»."""
    r.confirm_status = "Требует подтверждения"
    r.status_date = date.today()
    await notify(session, "BDTS.OTVTS", f"Запись технического состояния № {r.number} изменена ({what}) и требует подтверждения", "", f"/ts-records/{r.id}",
                 type_="Предупреждение", deo=r.deo, rule_id=11)
    await audit(session, user, "ts.flagged", "ts_record", r.id, what=what)


async def update_record(session, r: TsRecord, data: dict, user: CurrentUser) -> TsRecord:
    await _period_check(session, r.reg_date)
    flagged = []
    if "st" in data and data["st"] != r.object_status:
        if data["st"] not in OBJECT_STATUSES:
            raise RuleError("Недопустимое значение статуса объекта")
        r.object_status = data["st"]
        flagged.append("актуальный статус объекта")
    for k, attr in (("desc", "description"), ("notes", "notes")):
        if k in data:
            setattr(r, attr, data[k] or "")
    if "next" in data:
        r.next_inspection = parse_date(data["next"])
    if flagged:
        await flag_changed(session, r, user, ", ".join(flagged))
    return r


async def set_confirm(session, r, status: str, user: CurrentUser):
    """R-B316-01: статус подтверждения меняет только роль Б316-14 (BDTS.OTVTS)."""
    if not user.can("ts.confirm"):
        raise RuleError("Статус подтверждения данных меняет только ответственный ДЭО за контроль ТС", "R-B316-01", 403)
    if status not in CONFIRM:
        raise RuleError("Недопустимый статус подтверждения")
    r.confirm_status, r.status_date = status, date.today()
    if isinstance(r, TsRecord):
        r.confirmed_by, r.confirmed_by_position = user.fio, user.position or "Ответственный ДЭО за контроль ТС"
    await audit(session, user, "ts.confirm", type(r).__tablename__, r.id, status=status)


async def record_detail(session, r: TsRecord) -> dict:
    meas = (await session.execute(select(TsMeasurement).where(TsMeasurement.record_id == r.id).order_by(TsMeasurement.id))).scalars().all()
    msgs = (await session.execute(select(TsMessage).where(TsMessage.record_id == r.id).order_by(TsMessage.id))).scalars().all()
    acts = (await session.execute(select(TsMeasure).where(TsMeasure.record_id == r.id).order_by(TsMeasure.id))).scalars().all()
    from app.models import FileObject, TechnicalReport

    files = (await session.execute(select(FileObject).where(FileObject.entity_type == "ts_record", FileObject.entity_id == str(r.id), FileObject.deleted.is_(False)))).scalars().all()
    rep = await session.get(TechnicalReport, r.report_id) if r.report_id else None
    return {
        **record_row(r), "confirmedBy": r.confirmed_by, "confirmedByPosition": r.confirmed_by_position, "doReport": r.do_report or {},
        "report": {"id": rep.id, "number": rep.number} if rep else None,
        "measurements": [{"id": m.id, "point": m.control_point, "value": m.value_num, "unit": m.unit, "text": m.value_text, "position": m.position,
                          "area": m.area, "at": m.measured_at.isoformat() if m.measured_at else "", "instrument": m.instrument, "expert": m.expert, "method": m.method} for m in meas],
        "messages": [{"id": m.id, "journalNo": m.journal_no, "journalDate": iso(m.journal_date), "author": m.author, "kind": m.kind, "description": m.description,
                      "code": m.defect_code, "criticality": m.criticality, "fixStatus": m.fix_status, "measurementId": m.measurement_id} for m in msgs],
        "measures": [{"id": a.id, "pp": a.pp_line, "order": a.order_no, "name": a.name, "kind": a.kind, "executor": a.executor, "planStart": iso(a.plan_start),
                      "factStart": iso(a.fact_start), "planEnd": iso(a.plan_end), "factEnd": iso(a.fact_end), "docNo": a.doc_no, "docDate": iso(a.doc_date),
                      "defectNo": a.defect_no, "ops": a.operations, "parts": a.parts, "mtr": a.mtr_cost, "labor": a.labor_cost, "reason": a.fail_reason} for a in acts],
        "files": [{"id": f.id, "name": f.name, "mime": f.mime, "size": f.size, "at": f.uploaded_at.isoformat() if f.uploaded_at else "", "by": f.uploaded_by} for f in files],
    }


# ---------- Импорт xlsx (R-IMP-01): 5 листов в заданном порядке ----------
SHEETS = ["Запись о техсостоянии", "Документы измерения", "Сообщения (дефекты)", "Мероприятия КР и ТОиР", "Отчёт ДО"]
COLUMNS = {
    SHEETS[0]: ["ID строки", "Тип записи о тех. состоянии", "Код ЕО", "Дата регистрации", "Актуальный статус объекта", "Краткое описание", "Примечания"],
    SHEETS[1]: ["ID строки записи", "Точка контроля", "Числовое значение", "Единица измерения", "Метод контроля", "Инструмент"],
    SHEETS[2]: ["ID строки записи", "Описание дефекта", "Код дефекта", "Критичность дефекта", "Статус устранения дефекта"],
    SHEETS[3]: ["ID строки записи", "Название Заказа", "Вид ремонта", "Исполнитель", "Дата окончания. План"],
    SHEETS[4]: ["ID строки записи", "Номер Технического отчета", "Дата Технического отчета", "Исполнитель", "Вид ДО"],
}


def import_template() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    samples = {
        SHEETS[0]: [["R1", "Выполнение ТОиР", "EO-100294", "2026-09-02", "Работоспособное", "Восстановлено АКП корпуса", "Импорт"],
                    ["R2", "Диагностическое обследование", "EO-999404", "2026-08-15", "Работоспособное", "ЕО отсутствует в БДО — строка будет пропущена", ""]],
        SHEETS[1]: [["R1", "Корпус, сечение 1-1", 6.4, "мм", "Ультразвуковая толщинометрия", "Толщиномер А1207"]],
        SHEETS[2]: [["R1", "Локальное нарушение АКП", "КР-04", "Низкая", "Устранен"]],
        SHEETS[3]: [["R1", "Восстановление АКП корпуса", "Текущий ремонт", "ОРГ_10", "2026-09-30"]],
        SHEETS[4]: [["R2", "ТО-2024-118", "2024-08-20", "ОРГ_1", "Обследование сосудов и аппаратов"]],
    }
    for name in SHEETS:
        ws = wb.create_sheet(name)
        ws.append(COLUMNS[name])
        for r in samples[name]:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def run_import(log_id: int, kind: str, file_id: int, username: str):
    """Фоновая операция импорта: пишет «Лог» (т.113) и «Лог загрузки данных» (т.114). OQ-20: строки с ЕО вне БДО пропускаются."""
    from app.models import FileObject
    from app.services.storage import read_file

    async with SessionLocal() as session:
        log = await session.get(ImportLog, log_id)
        log.state = "running"

        def entry(level: str, text: str, ref: str = ""):
            log.entries.append(ImportLogEntry(level=level, text=text, row_ref=ref))

        entry("Информация", "Начало выполнения операции")
        try:
            fo = await session.get(FileObject, file_id)
            wb = load_workbook(io.BytesIO(await read_file(fo)), read_only=True, data_only=True)
            names = wb.sheetnames
            expected = SHEETS if kind == "Загрузка начальных данных" else SHEETS
            if names[:len(expected)] != expected:
                raise RuleError(f"Листы файла должны идти в порядке: {', '.join(expected)}. В файле: {', '.join(names)}", "R-IMP-01")
            eos = {e.code: e for e in (await session.execute(select(EquipmentUnit))).scalars()}
            created: dict[str, TsRecord] = {}
            rows0 = list(wb[SHEETS[0]].iter_rows(min_row=2, values_only=True))
            log.total = len([r for r in rows0 if any(r)])
            for r in rows0:
                if not any(r):
                    continue
                rid, rtype, code, regd, st, desc, notes = (list(r) + [None] * 7)[:7]
                eo = eos.get(str(code or "").strip())
                if not eo:
                    log.warnings += 1
                    entry("Предупреждение", f"Единица оборудования {code} не найдена — строка пропущена", str(rid))
                    continue
                regdate = regd.date() if isinstance(regd, datetime) else parse_date(str(regd or "")) or date.today()
                number = await next_number(session, TsRecord, TsRecord.number, f"Б316-{regdate.year}-")
                rec = TsRecord(number=number, record_type=str(rtype or "Выполнение ТОиР"), tm_id=eo.tm_id, eo_id=eo.id, deo=eo.deo, reg_date=regdate,
                               object_status=str(st or ""), description=str(desc or ""), notes=str(notes or f"Импорт: {fo.name}"),
                               confirm_status="Требует подтверждения", source="import")
                session.add(rec)
                await session.flush()
                created[str(rid)] = rec
                log.loaded += 1
            for r in wb[SHEETS[1]].iter_rows(min_row=2, values_only=True):
                if any(r) and str(r[0]) in created:
                    session.add(TsMeasurement(record_id=created[str(r[0])].id, control_point=str(r[1] or ""), value_num=float(r[2]) if r[2] not in (None, "") else None,
                                              unit=str(r[3] or ""), method=str(r[4] or ""), instrument=str(r[5] or "") if len(r) > 5 else "", measured_at=datetime.now(timezone.utc)))
                elif any(r):
                    log.warnings += 1
                    entry("Предупреждение", "Документ измерения ссылается на пропущенную запись — пропущен", str(r[0]))
            for r in wb[SHEETS[2]].iter_rows(min_row=2, values_only=True):
                if any(r) and str(r[0]) in created:
                    session.add(TsMessage(record_id=created[str(r[0])].id, description=str(r[1] or ""), defect_code=str(r[2] or ""), criticality=str(r[3] or ""),
                                          fix_status=str(r[4] or "Не устранен"), kind="Импорт", journal_date=date.today(), author=username))
            for r in wb[SHEETS[3]].iter_rows(min_row=2, values_only=True):
                if any(r) and str(r[0]) in created:
                    pe = r[4].date() if isinstance(r[4], datetime) else parse_date(str(r[4] or ""))
                    session.add(TsMeasure(record_id=created[str(r[0])].id, name=str(r[1] or ""), kind=str(r[2] or ""), executor=str(r[3] or ""), plan_end=pe))
            if kind == "Загрузка начальных данных":
                for r in wb[SHEETS[4]].iter_rows(min_row=2, values_only=True):
                    if any(r) and str(r[0]) in created:
                        created[str(r[0])].do_report = {"toNumber": str(r[1] or ""), "toDate": str(r[2] or "")[:10], "executor": str(r[3] or ""), "vid": str(r[4] or "")}
            else:
                n4 = len([r for r in wb[SHEETS[4]].iter_rows(min_row=2, values_only=True) if any(r)])
                if n4:
                    entry("Информация", f"Лист «Отчёт ДО» пользователем не загружается (R-IMP-01): пропущено строк — {n4}")
            log.state = "done"
            log.description = f"Загружено {log.loaded} из {log.total} строк" + (f", {log.warnings} предупреждений" if log.warnings else " без предупреждений")
            entry("Информация", f"Операция завершена: {log.loaded} из {log.total} строк")
            if log.loaded:
                await notify(session, "BDTS.OTVTS", f"{kind}: загружено записей о ТС — {log.loaded}, требуется подтверждение", log.description, "/ts-records", type_="Предупреждение")
        except RuleError as e:
            log.state, log.description = "error", e.detail
            entry("Ошибка", e.detail)
        except Exception as e:  # noqa: BLE001 — ошибка разбора файла пишется в лог, а не теряется
            log.state, log.description = "error", f"Не удалось обработать файл: {e}"
            entry("Ошибка", log.description)
        await session.commit()


async def eo_scope_ids(session, user: CurrentUser) -> list[int]:
    return list((await session.execute(scope(select(EquipmentUnit.id), EquipmentUnit, user))).scalars())


def and_all(*conds):
    return and_(*[c for c in conds if c is not None])
