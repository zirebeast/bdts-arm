"""Б303 Результат ДО: разделы ПЭ/КП, переходы статусов (ТПР т.93, п. 4.4.6–4.4.7), раскладка в записи о ТС (Б316–Б319)."""
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.errors import Conflict, RuleError, not_found
from app.models import (
    DoResult, DoResultHistory, DoResultSection, DoTask, DoTemplate, EquipmentUnit, FileObject, TsMeasurement, TsMessage, TsRecord,
)
from app.permissions import CurrentUser
from app.seed.templates import VID_SHORT
from app.services import tasks as task_svc
from app.services.common import audit, fmt_date, next_number, notify, parse_date
from app.services.events import emit
from app.services.sections import build_sec_data, sec_status, sec_tol_list, tol_hb, tol_thk

B303_STATUSES = ["ПЭ не завершен", "Требуется КП", "На согласовании", "На корректировке", "На рассмотрении ДЭО",
                 "Принят ДЭО", "Требуется ЭПБ", "Результат получен"]
IN_PROGRESS = B303_STATUSES[:-1]
KP_OPEN = ("Требуется КП", "На корректировке")
EXPORT_STATUSES = ("Требуется КП", "На согласовании", "На корректировке", "На рассмотрении ДЭО", "Требуется ЭПБ", "Результат получен")
NOTIFY = {
    "Требуется КП": ("Необходимо провести КП", "BDTS.KAMER", 4),
    "На согласовании": ("Результат ДО передан на согласование", "BDTS.SOGLTECH", 5),
    "На корректировке": ("Результат ДО отклонён и требует корректировки", "BDTS.KAMER", 6),
    "На рассмотрении ДЭО": ("Результат ДО согласован и передан на рассмотрение ДЭО", "BDTS.OTVTECHOT", 7),
    "Принят ДЭО": ("Результат ДО принят ДЭО", "BDTS.OTVTECHOT", 8),
    "Требуется ЭПБ": ("Результат ДО требует проведения ЭПБ", "BDTS.OTVTECHOT", 9),
    "Результат получен": ("Внесено заключение ЭПБ / результат получен. Задание на ДО завершено", "BDTS.OTVTECHOT", 10),
}


async def _own_files(session, ctx: "Ctx", ids: list) -> list[int]:
    """ID файлов приходят от клиента: принимаются только файлы, загруженные к этому результату ДО."""
    out = []
    for i in ids:
        fo = await session.get(FileObject, int(i)) if str(i).isdigit() else None
        if not fo or fo.deleted or fo.entity_type != "do_result" or fo.entity_id != str(ctx.r.id):
            raise RuleError("Файл не найден среди файлов результата ДО. Загрузите файл заново.", "R-FILE-01")
        out.append(fo.id)
    return out


class Ctx:
    """Загруженный результат ДО: задание, шаблон, разделы и данные разделов по ЕО."""

    def __init__(self, r: DoResult, task: DoTask, sections: list[dict], rows: dict[tuple[int, str], DoResultSection]):
        self.r, self.task, self.sections, self.rows = r, task, sections, rows

    @property
    def is_vtd(self) -> bool:
        return self.task.vid == "vtd"

    def data(self, eo_idx: int, sec: dict) -> dict:
        row = self.rows.get((eo_idx, sec["code"]))
        return row.data if row else build_sec_data(sec, False)

    def stage(self, st: str) -> list[dict]:
        return [s for s in self.sections if s["stage"] == st]

    def missing(self, stage: str) -> list[str]:
        """Обязательные разделы этапа, не пройденные хотя бы по одной ЕО."""
        out = []
        for i, eo in enumerate(self.r.eos):
            for s in self.stage(stage):
                if s.get("req") and s["kind"] != "info" and sec_status(s, self.data(i, s)) not in ("done", "skipped"):
                    out.append(f"{s['title']}" + (f" ({eo.label})" if len(self.r.eos) > 1 else ""))
        return out

    def exceeded(self) -> int:
        return sum(sec_tol_list(s, self.data(i, s)).count("exceeded") for i in range(len(self.r.eos)) for s in self.sections)


async def load(session, task_id: int, user: CurrentUser) -> Ctx:
    r = (await session.execute(select(DoResult).where(DoResult.task_id == task_id))).scalars().first()
    if not r:
        raise not_found("Результат ДО")
    task = r.task
    if not user.deo_allowed(task.deo):
        raise RuleError("Нет доступа к данным другого ДЭО", "ДЭО", 403)
    sections = []
    if task.template_id:
        tpl = await session.get(DoTemplate, task.template_id)
        sections = tpl.config.get("sections", []) if tpl else []
    rows = (await session.execute(select(DoResultSection).where(DoResultSection.result_id == r.id))).scalars().all()
    return Ctx(r, task, sections, {(x.eo_idx, x.code): x for x in rows})


def actions(ctx: Ctx, user: CurrentUser) -> tuple[list[dict], list[dict], list[str]]:
    """Кнопки блока «Управление результатом ДО» по статусу и роли (п. 4.4.7 ТПР): видимые, неактивные с подсказкой."""
    st, r, vtd = ctx.r.status, ctx.r, ctx.is_vtd
    btn, exp, hints = [], [], []
    kp_open = st in KP_OPEN
    if not vtd and st == "ПЭ не завершен" and user.can("result.pe"):
        btn.append({"key": "pe", "label": "Внести данные ПЭ", "primary": True})
    if st == "ПЭ не завершен" and user.can("result.pe_finish"):
        miss = [] if vtd else ctx.missing("ПЭ")
        btn.append({"key": "pe_finish", "label": "Завершить ПЭ", "disabled": bool(miss)})
        if miss:
            hints.append("«Завершить ПЭ» станет доступна, когда все разделы ПЭ заполнены, включая заключение специалиста по разделу. Осталось: " + "; ".join(miss[:8]) + ("…" if len(miss) > 8 else "") + ".")
    if not vtd and kp_open and user.can("result.kp"):
        btn.append({"key": "kp", "label": "Внести данные КП", "primary": True})
    if vtd and kp_open and user.can("result.vtd_upload"):
        btn.append({"key": "vtd_upload", "label": "Загрузить отчет по ВТД", "primary": True})
    if not vtd and kp_open and user.can("result.form"):
        miss = ctx.missing("ПЭ") + ctx.missing("КП")
        btn.append({"key": "form", "label": "Сформировать технический отчет", "disabled": bool(miss)})
        if miss:
            hints.append("«Сформировать технический отчет» станет доступна после заполнения всех обязательных разделов (R-B303-03).")
    if kp_open and user.can("result.send"):
        ok = bool(r.vtd_file_ids) if vtd else r.to_formed
        btn.append({"key": "send", "label": "Отправить на согласование", "disabled": not ok})
        if not ok:
            hints.append("Перед отправкой на согласование загрузите технический отчет по ВТД." if vtd else "Перед отправкой на согласование сформируйте технический отчет.")
    if st == "На согласовании" and user.can("result.agree"):
        btn.append({"key": "agree", "label": "Внести результат согласования", "primary": True})
    if st == "На рассмотрении ДЭО" and user.can("result.deo"):
        btn.append({"key": "deo", "label": "Внести результат рассмотрения ДЭО", "primary": True})
    if st == "Принят ДЭО" and user.can("result.epb_need"):
        btn.append({"key": "epb_need", "label": "Определить необходимость в ЭПБ", "primary": True})
    if st in ("Требуется ЭПБ", "Результат получен") and user.can("result.epb"):
        btn.append({"key": "epb", "label": "Внести результат ЭПБ", "primary": st == "Требуется ЭПБ"})
    if not vtd and st in EXPORT_STATUSES and user.can("result.export") and (r.to_formed or st not in KP_OPEN):
        exp.append({"key": "export", "label": "Выгрузить технический отчет (.docx)"})
        exp.append({"key": "export_xml", "label": "Выгрузить технический отчет (.xml)"})
    if vtd and st in EXPORT_STATUSES and r.vtd_file_ids and user.can("result.export"):
        exp.append({"key": "export_vtd", "label": "Выгрузить технический отчет по ВТД"})
    if st == "Результат получен" and r.epb_file_id and user.can("result.epb_export"):
        exp.append({"key": "export_epb", "label": "Выгрузить отчет по ЭПБ"})
    return btn, exp, hints


async def payload(session, ctx: Ctx, user: CurrentUser) -> dict:
    r, t = ctx.r, ctx.task
    files = {}
    ids = [i for i in [r.to_file_id, r.epb_file_id, *r.vtd_file_ids] if i]
    if ids:
        for fo in (await session.execute(select(FileObject).where(FileObject.id.in_(ids)))).scalars():
            files[fo.id] = {"id": fo.id, "name": fo.name, "size": fo.size}
    btn, exp, hints = actions(ctx, user)
    eo_ids = [e.eo_id for e in r.eos if e.eo_id]
    passports = {}
    if eo_ids:
        for eo in (await session.execute(select(EquipmentUnit).where(EquipmentUnit.id.in_(eo_ids)))).scalars():
            passports[eo.id] = eo.passport or []
    data = {str(i): {s["code"]: ctx.data(i, s) for s in ctx.sections} for i in range(len(r.eos))}
    return {
        "id": r.id, "taskId": t.id, "status": r.status, "version": r.version, "toFormed": r.to_formed,
        "task": task_svc.task_dict(t), "isVtd": ctx.is_vtd, "short": VID_SHORT.get(t.vid, t.vid),
        "eos": [{"idx": e.idx, "eoId": e.eo_id, "label": e.label, "passport": passports.get(e.eo_id, [])} for e in r.eos],
        "sections": ctx.sections, "data": data,
        "toFile": files.get(r.to_file_id), "epbFile": files.get(r.epb_file_id), "vtdFiles": [files[i] for i in r.vtd_file_ids if i in files],
        "history": [{"date": h.at.isoformat(), "user": h.username, "status": h.status, "file": h.file, "comment": h.comment} for h in r.history],
        "actions": btn, "exports": exp, "hints": hints, "exceeded": ctx.exceeded(),
        "can": {"pe": user.can("result.pe") and r.status == "ПЭ не завершен",
                "kp": user.can("result.kp") and r.status in KP_OPEN, "concl": user.can("result.concl")},
    }


def _check_numbers(sec: dict, d: dict):
    def bad(v):
        s = str(v or "").strip().replace(",", ".")
        if not s:
            return False
        try:
            float(s)
            return False
        except ValueError:
            return True

    for el in d.get("elements", []):
        for p in el.get("points", []):
            if bad(p.get("value")):
                raise RuleError(f"«{el.get('name')}, {p.get('label')}»: введите число", "R-B303-04")
    for f in sec.get("fields", []):
        if f["type"] == "num" and bad(d.get("values", {}).get(f["key"])):
            raise RuleError(f"«{f['label']}»: введите число", "R-B303-04")
    for c in sec.get("cols", []):
        if c["type"] == "num" and any(bad(row.get(c["key"])) for row in d.get("rows", [])):
            raise RuleError(f"«{c['label']}»: введите число", "R-B303-04")
    for k in ("comment", "concl"):
        if len(str(d.get(k) or "")) > 1000:
            raise RuleError("Комментарий — строка до 1000 символов", "R-B303-08")


async def save_section(session, ctx: Ctx, eo_idx: int, code: str, data: dict, user: CurrentUser, version: int | None):
    if version is not None and version != ctx.r.version:
        raise Conflict("Результат ДО изменён другим пользователем. Данные обновлены.")
    sec = next((s for s in ctx.sections if s["code"] == code), None)
    if not sec or sec["kind"] == "info":
        raise RuleError("Раздел не редактируется")
    if not 0 <= eo_idx < len(ctx.r.eos):
        raise RuleError("Неизвестная ЕО результата")
    if sec["stage"] == "ПЭ":
        if ctx.r.status != "ПЭ не завершен" or not user.can("result.pe"):
            raise RuleError("Данные ПЭ вносятся в статусе «ПЭ не завершен» исполнителем полевых работ", "R-B303-01", 403)
    elif ctx.r.status not in KP_OPEN or not user.can("result.kp"):
        raise RuleError("Данные КП вносятся в статусах «Требуется КП», «На корректировке»", "R-B303-02", 403)
    _check_numbers(sec, data)
    old = ctx.rows.get((eo_idx, code))
    if sec["stage"] == "ПЭ" and not user.can("result.concl"):
        data["concl"] = old.data.get("concl", "") if old else ""
    if old:
        old.data = data
        old.updated_by = user.display
    else:
        row = DoResultSection(result_id=ctx.r.id, eo_idx=eo_idx, code=code, data=data, updated_by=user.display)
        session.add(row)
        ctx.rows[(eo_idx, code)] = row
    ctx.r.version += 1


async def _change(session, ctx: Ctx, nxt: str, comment: str, user: CurrentUser, file: str = "Нет"):
    r, t = ctx.r, ctx.task
    r.status = nxt
    r.version += 1
    r.history.append(DoResultHistory(username=user.display, status=nxt, comment=comment, file=file))
    t_next = task_svc.TASK_BY_RESULT.get(nxt)
    if t_next and t_next != t.status:
        t.status = t_next
        t.version += 1
        t.history.append(task_svc.DoTaskHistory(username="Система", status=t_next, comment=f"Автоматически: результат ДО → «{nxt}»"))
    n = NOTIFY.get(nxt)
    if n:
        await notify(session, n[1], f"{n[0]}: задание № {t.id}", f"Объект «{t.eo_name}», {t.deo}", f"/results/{t.id}", deo=t.deo, rule_id=n[2])
    if nxt == "Результат получен":
        await _explode_to_ts(session, ctx, user)
    await audit(session, user, "result.status", "do_result", r.id, status=nxt)


def _comment_required(decision: str, comment: str):
    if decision == "b" and not (comment or "").strip():
        raise RuleError("Возврат на корректировку требует комментария", "R-B303-05", fields={"comment": "Укажите, что исправить"})
    if len(comment or "") > 1000:
        raise RuleError("Комментарий — строка до 1000 символов", "R-B303-08")


async def do_action(session, ctx: Ctx, action: str, body: dict, user: CurrentUser):
    """Выполнить действие блока «Управление результатом ДО». Проверки статуса/роли повторяют actions()."""
    if body.get("version") is not None and body["version"] != ctx.r.version:
        raise Conflict("Статус уже изменён другим пользователем. Карточка перечитана.")
    allowed = {b["key"]: b for b in actions(ctx, user)[0]}
    if action not in allowed:
        raise RuleError("Действие недоступно в текущем статусе для вашей роли", "R-B303-01", 403)
    if allowed[action].get("disabled"):
        raise RuleError("Действие пока недоступно: не выполнены условия", "R-B303-03")
    comment = (body.get("comment") or "").strip()
    decision = body.get("decision", "a")
    if action == "pe_finish":
        await _change(session, ctx, "Требуется КП", "Полевые работы ВТД завершены" if ctx.is_vtd else comment, user)
    elif action == "form":
        from app.services.report_docx import render_result_docx
        from app.services.storage import save_file

        data, name = await render_result_docx(session, ctx)
        fo = await save_file(session, data, name, "do_result", ctx.r.id, "technical_report", user)
        ctx.r.to_formed, ctx.r.to_file_id = True, fo.id
        ctx.r.version += 1
        ctx.r.history.append(DoResultHistory(username=user.display, status=ctx.r.status, file="Да", comment="Сформирован технический отчет (.docx)"))
    elif action == "send":
        await _change(session, ctx, "На согласовании", comment, user)
        if ctx.task.is_hs:
            from app.services.reports import register_hs_report

            await register_hs_report(session, ctx, user)
    elif action in ("agree", "deo"):
        _comment_required(decision, comment)
        if decision == "b":
            ctx.r.to_formed = False
            await _change(session, ctx, "На корректировке", comment, user)
        else:
            await _change(session, ctx, "На рассмотрении ДЭО" if action == "agree" else "Принят ДЭО", comment, user)
    elif action == "epb_need":
        if decision == "a":
            await _change(session, ctx, "Требуется ЭПБ", comment, user)
        else:
            await _change(session, ctx, "Результат получен", "ЭПБ не требуется", user)
    elif action == "epb":
        fid = body.get("file_id")
        if not fid:
            raise RuleError("Выберите файл заключения ЭПБ: прикладывается ровно 1 файл", "R-B303-06")
        ctx.r.epb_file_id = (await _own_files(session, ctx, [fid]))[0]
        if ctx.r.status == "Результат получен":
            ctx.r.version += 1
            ctx.r.history.append(DoResultHistory(username=user.display, status=ctx.r.status, file="Да", comment=comment or "Файл ЭПБ заменён"))
        else:
            await _change(session, ctx, "Результат получен", comment or "Внесён результат ЭПБ", user, file="Да")
    elif action == "vtd_upload":
        ids = body.get("file_ids") or []
        if not 1 <= len(ids) <= 2:
            raise RuleError("Для ВТД прикладывается от 1 до 2 файлов технического отчёта", "R-B303-07")
        replaced = bool(ctx.r.vtd_file_ids)
        ctx.r.vtd_file_ids = await _own_files(session, ctx, ids)
        ctx.r.version += 1
        ctx.r.history.append(DoResultHistory(username=user.display, status=ctx.r.status, file="Да", comment=comment or ("Файлы ТО ВТД заменены" if replaced else "Загружен ТО ВТД")))
    elif action in ("pe", "kp"):
        pass  # переход в режим правки — только на клиенте
    else:
        raise RuleError("Неизвестное действие")


async def _explode_to_ts(session, ctx: Ctx, user: CurrentUser):
    """«Результат получен»: по каждой ЕО создаётся запись о ТС (Б316) с измерениями (Б318) и дефектами (Б319)."""
    t = ctx.task
    year = date.today().year
    concl_sec = next((s for s in ctx.sections if s["code"] == "conclusion"), None)
    calc_sec = next((s for s in ctx.sections if s["code"] == "calc"), None)
    defects_payload = []
    for i, reo in enumerate(ctx.r.eos):
        eo = await session.get(EquipmentUnit, reo.eo_id) if reo.eo_id else None
        cvals = ctx.data(i, concl_sec)["values"] if concl_sec else {}
        rt = ctx.data(i, calc_sec)["values"].get("rt") if calc_sec else None
        number = await next_number(session, TsRecord, TsRecord.number, f"Б316-{year}-")
        rec = TsRecord(
            number=number, record_type="Диагностическое обследование", tm_id=eo.tm_id if eo else None, eo_id=eo.id if eo else None,
            deo=t.deo, reg_date=date.today(), object_status=cvals.get("ts", ""), description=(cvals.get("text") or "")[:500],
            next_inspection=parse_date(cvals.get("next")), confirm_status="Требует подтверждения", source="result", result_id=ctx.r.id,
            residual_life_years=float(str(rt).replace(",", ".")) if rt and str(rt).replace(",", ".").replace(".", "", 1).isdigit() else None,
            notes=f"Создана автоматически по результату ДО № {t.id}",
            do_report={"pp": t.xyz, "order": str(t.id), "orderName": f"ДО: {t.eo_name}", "executor": "ОРГ_1 (ГД)", "vid": task_svc.VID_NAME.get(t.vid, t.vid),
                       "planStart": fmt_date(t.start_date), "planEnd": fmt_date(t.end_date), "factEnd": fmt_date(date.today()),
                       "toNumber": f"ТО-{year}-{t.id:03d}", "toDate": fmt_date(date.today()), "ops": ", ".join(s["title"] for s in ctx.stage("ПЭ") if s["kind"] != "info")},
        )
        session.add(rec)
        await session.flush()
        now = datetime.now(timezone.utc)
        for s in ctx.sections:
            d = ctx.data(i, s)
            if d.get("np"):
                continue
            if s["kind"] == "points":
                for ei, el in enumerate(d.get("elements", [])):
                    cfg = s["elements"][ei] if ei < len(s["elements"]) else {}
                    for p in el.get("points", []):
                        v = str(p.get("value") or "").replace(",", ".")
                        if not v:
                            continue
                        m = TsMeasurement(record_id=rec.id, control_point=f"{el['name']}, {p['label']}", value_num=float(v), unit="мм" if s["mode"] == "thk" else "HB",
                                          position=p["label"], area=el["name"], measured_at=now, instrument=s.get("instrument", ""), expert="ФИО_3", method=s["title"])
                        session.add(m)
                        tol = tol_thk(v, cfg.get("s", 0)) if s["mode"] == "thk" else tol_hb(v, cfg.get("lo", s.get("lo", 0)), cfg.get("hi", s.get("hi", 0)))
                        if tol == "exceeded":
                            await session.flush()
                            desc = f"{'Утонение стенки ниже s расч.' if s['mode'] == 'thk' else 'Твёрдость вне нормы'}: {el['name']}, {p['label']} = {v}"
                            session.add(TsMessage(record_id=rec.id, journal_no=f"{rec.id}/{year}", journal_date=date.today(), author="ФИО_3",
                                                  kind="Дефект основного металла", description=desc, defect_code="УТ.01.003" if s["mode"] == "thk" else "ТВ.02.001",
                                                  criticality="Высокая", fix_status="Не устранен", measurement_id=m.id))
                            defects_payload.append({"eo": eo.code if eo else reo.label, "description": desc})
            if s["kind"] == "checklist":
                for code, name, op in s["items"]:
                    idx = d.get("items", {}).get(code, -1)
                    if isinstance(idx, int) and 0 <= idx < len(op) and op[idx][1] in ("borderline", "exceeded"):
                        desc = f"{name}: {op[idx][0]}" + (f". {d['notes'].get(code)}" if d.get("notes", {}).get(code) else "")
                        session.add(TsMessage(record_id=rec.id, journal_no=f"{rec.id}/{year}", journal_date=date.today(), author="ФИО_3",
                                              kind="Результат ВИК", description=desc, defect_code=code,
                                              criticality="Высокая" if op[idx][1] == "exceeded" else "Средняя", fix_status="Не устранен"))
                        if op[idx][1] == "exceeded":
                            defects_payload.append({"eo": eo.code if eo else reo.label, "description": desc})
        if eo:
            eo.status_date = date.today()
        await notify(session, "BDTS.OTVTS", f"Запись технического состояния № {number} внесена и требует подтверждения",
                     f"{eo.name if eo else reo.label}", f"/ts-records/{rec.id}", type_="Предупреждение", deo=t.deo, rule_id=11)
    if defects_payload:
        await emit(session, "diag.defects", {"task": t.id, "defects": defects_payload, "summary": f"{len(defects_payload)} дефектов", "user": user.display},
                   key=f"diag.defects:result:{ctx.r.id}")
