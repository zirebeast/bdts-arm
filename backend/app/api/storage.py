"""UC-4: поиск (W-0.2, W-0.3), иерархия (W-3.1), карточки ТМ/ЕО (W-3.2, W-3.3), записи о ТС (W-3.4, W-3.5), логи (W-3.6)."""
import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import XLSX, Page, Session, User, file_response, paginate, require, scoped
from app.errors import RuleError, not_found
from app.models import (
    EquipmentUnit, ImportLog, ImportLogEntry, PlanningMark, SavedSearch, TechPlace, TsMeasure, TsMeasurement, TsMessage, TsRecord,
)
from app.permissions import CurrentUser
from app.services import ts as svc
from app.services.common import fmt_date, parse_date
from app.services.docs import build_xlsx
from app.services.events import kick_outbox, submit_job
from app.services.storage import save_file

router = APIRouter(tags=["Хранилище ТС"])


# ---------- Иерархия ----------
@router.get("/hierarchy")
async def hierarchy(node: str = "", group: str = "tm", session=Session, user: CurrentUser = User):
    return await svc.hierarchy_children(session, user, node or None, group)


@router.get("/tm/{tid}")
async def tm_card(tid: int, session=Session, user: CurrentUser = User):
    tm = await session.get(TechPlace, tid)
    if not tm or not user.deo_allowed(tm.deo):
        raise not_found("Техническое место")
    parent = await session.get(TechPlace, tm.parent_id) if tm.parent_id else None
    sub_tm = (await session.execute(select(TechPlace.id).where(TechPlace.parent_id == tm.id))).scalars().all()
    eos = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.tm_id.in_([tm.id, *sub_tm])))).scalars().all()
    agg = await svc.aggregate_state(session, eo_ids=[e.id for e in eos])
    latest = max((a for a in agg.values()), key=lambda a: a.get("fix", ""), default={})
    return {**svc.tm_row(tm, latest), "semanticCode": tm.semantic_code, "sorName": tm.sor_name, "parentCode": parent.code if parent else "",
            "attrs": tm.attrs, "notes": tm.notes, "createdAt": svc.iso(tm.created_at.date()), "updatedAt": svc.iso(tm.updated_at.date()),
            "eoCount": len(eos), "eos": [svc.eo_row(e, agg.get(f"eo:{e.id}")) for e in eos[:50]]}


@router.get("/eo/{eid}")
async def eo_card(eid: int, session=Session, user: CurrentUser = User):
    eo = await session.get(EquipmentUnit, eid)
    if not eo or not user.deo_allowed(eo.deo):
        raise not_found("Единица оборудования")
    agg = (await svc.aggregate_state(session, eo_ids=[eo.id])).get(f"eo:{eo.id}", {})
    parent = await session.get(EquipmentUnit, eo.parent_id) if eo.parent_id else None
    children = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.parent_id == eo.id))).scalars().all()
    recs = (await session.execute(select(TsRecord).where(TsRecord.eo_id == eo.id).order_by(TsRecord.reg_date.desc()))).scalars().all()
    # Δ Сравнение замеров по совпадающим точкам контроля (динамика толщины, скорость коррозии)
    series: dict[str, list] = {}
    for r in sorted(recs, key=lambda r: r.reg_date):
        for m in (await session.execute(select(TsMeasurement).where(TsMeasurement.record_id == r.id, TsMeasurement.unit == "мм"))).scalars():
            if m.value_num is not None:
                series.setdefault(m.control_point, []).append([r.reg_date.year, m.value_num])
    compare = []
    for pt, vals in series.items():
        if len(vals) >= 2:
            years = vals[-1][0] - vals[0][0]
            compare.append({"point": pt, "values": vals, "rate": round((vals[-1][1] - vals[0][1]) / years, 3) if years else None})
    mark = await session.get(PlanningMark, eo.id)
    return {**svc.eo_row(eo, agg), "parentCode": parent.code if parent else "", "attrs": eo.attrs, "passport": eo.passport, "manufacturer": eo.manufacturer,
            "repairObject": eo.repair_object, "year": eo.year, "dn": eo.dn, "pn": eo.pn, "sCalc": eo.s_calc, "steel": eo.steel_grade, "notes": eo.notes,
            "hasPassport": eo.has_passport, "children": [svc.eo_row(c) for c in children], "records": [svc.record_row(r) for r in recs], "compare": compare[:9],
            "marks": {"mark3y": bool(mark and mark.mark_3y), "markNextYear": bool(mark and mark.mark_next_year)}}


class ConfirmIn(BaseModel):
    status: str


@router.post("/tm/{tid}/confirm")
async def tm_confirm(tid: int, body: ConfirmIn, session=Session, user: CurrentUser = Depends(require("ts.confirm"))):
    tm = await session.get(TechPlace, tid)
    if not tm or not user.deo_allowed(tm.deo):
        raise not_found("Техническое место")
    await svc.set_confirm(session, tm, body.status, user)
    await session.commit()
    return {"ok": True, "status": tm.confirm_status}


@router.post("/eo/{eid}/confirm")
async def eo_confirm(eid: int, body: ConfirmIn, session=Session, user: CurrentUser = Depends(require("ts.confirm"))):
    eo = await session.get(EquipmentUnit, eid)
    if not eo or not user.deo_allowed(eo.deo):
        raise not_found("Единица оборудования")
    await svc.set_confirm(session, eo, body.status, user)
    await session.commit()
    return {"ok": True, "status": eo.confirm_status}


# ---------- Записи о ТС ----------
@router.get("/ts-records")
async def list_records(q: str = "", confirm: str = "", rtype: str = "", eo_id: int | None = None, page: Page = Depends(), session=Session, user: CurrentUser = User):
    return await paginate(session, await svc.list_records(session, user, q, confirm, rtype, eo_id), page, svc.record_row)


@router.get("/ts-records/export.xlsx")
async def export_records(q: str = "", confirm: str = "", session=Session, user: CurrentUser = User):
    rows = (await session.execute(await svc.list_records(session, user, q, confirm))).unique().scalars().all()
    cols = ["ID записи", "Тип записи о тех. состоянии", "Техническое место", "Единица оборудования", "Дата регистрации", "Актуальный статус объекта",
            "Краткое описание", "Статус подтверждения", "Дата статуса", "Статус записи", "Примечания"]
    data = build_xlsx("Записи о ТС", cols, [[r.number, r.record_type, r.tm.code if r.tm else "", r.eo.name if r.eo else "", fmt_date(r.reg_date), r.object_status,
                                               r.description, r.confirm_status, fmt_date(r.status_date), r.record_status, r.notes] for r in rows])
    return file_response(data, "Записи_о_ТС.xlsx", XLSX)


@router.get("/ts-records/import-template.xlsx")
async def import_template(user: CurrentUser = User):
    return file_response(svc.import_template(), "Шаблон_импорта_БДТС.xlsx", XLSX)


class RecordIn(BaseModel):
    recordType: str = "Выполнение ТОиР"
    eoId: int | None = None
    st: str = ""
    desc: str = ""
    notes: str = ""
    regDate: str = ""
    next: str = ""
    wear: float | None = None


@router.post("/ts-records")
async def create_record(body: RecordIn, session=Session, user: CurrentUser = Depends(require("ts.create"))):
    r = await svc.create_record(session, body.model_dump(), user)
    await session.commit()
    kick_outbox()
    return svc.record_row(await svc.get_record(session, r.id, user))


@router.get("/ts-records/{rid}")
async def get_record(rid: int, session=Session, user: CurrentUser = User):
    r = await svc.get_record(session, rid, user)
    return await svc.record_detail(session, r)


@router.patch("/ts-records/{rid}")
async def patch_record(rid: int, body: dict, session=Session, user: CurrentUser = Depends(require("ts.edit"))):
    r = await svc.get_record(session, rid, user)
    await svc.update_record(session, r, body, user)
    await session.commit()
    kick_outbox()
    return await svc.record_detail(session, r)


@router.post("/ts-records/{rid}/confirm")
async def confirm_record(rid: int, body: ConfirmIn, session=Session, user: CurrentUser = Depends(require("ts.confirm"))):
    r = await svc.get_record(session, rid, user)
    await svc.set_confirm(session, r, body.status, user)
    await session.commit()
    return await svc.record_detail(session, r)


@router.patch("/ts-records/{rid}/messages/{mid}")
async def patch_message(rid: int, mid: int, body: dict, session=Session, user: CurrentUser = Depends(require("ts.edit"))):
    r = await svc.get_record(session, rid, user)
    m = await session.get(TsMessage, mid)
    if not m or m.record_id != r.id:
        raise not_found("Сообщение")
    if "fixStatus" in body and body["fixStatus"] != m.fix_status:
        m.fix_status = body["fixStatus"]
        await svc.flag_changed(session, r, user, "статус устранения дефекта")
    await session.commit()
    kick_outbox()
    return await svc.record_detail(session, r)


class MeasureIn(BaseModel):
    name: str
    kind: str
    executor: str = ""
    planStart: str = ""
    planEnd: str = ""
    factEnd: str = ""
    orderNo: str = ""
    ops: str = ""
    reason: str = ""


@router.post("/ts-records/{rid}/measures")
async def add_measure(rid: int, body: MeasureIn, session=Session, user: CurrentUser = Depends(require("ts.edit"))):
    r = await svc.get_record(session, rid, user)
    if not body.name.strip():
        raise RuleError("Заполните «Название Заказа»", "R-NSI-01", fields={"name": "Обязательное поле"})
    session.add(TsMeasure(record_id=r.id, name=body.name.strip(), kind=body.kind, executor=body.executor, plan_start=parse_date(body.planStart),
                          plan_end=parse_date(body.planEnd), fact_end=parse_date(body.factEnd), order_no=body.orderNo, operations=body.ops, fail_reason=body.reason))
    await svc.flag_changed(session, r, user, "мероприятия КР и ТОиР")
    await session.commit()
    kick_outbox()
    return await svc.record_detail(session, r)


@router.post("/ts-records/{rid}/files")
async def record_file(rid: int, file: UploadFile = File(...), session=Session, user: CurrentUser = Depends(require("ts.edit"))):
    r = await svc.get_record(session, rid, user)
    await save_file(session, await file.read(), file.filename or "file", "ts_record", r.id, "attachment", user)
    await session.commit()
    return await svc.record_detail(session, r)


# ---------- Импорт и логи ----------
@router.post("/ts-import")
async def ts_import(file: UploadFile = File(...), kind: str = Form("Импорт данных"), session=Session, user: CurrentUser = Depends(require("ts.import"))):
    if kind not in ("Импорт данных", "Загрузка начальных данных"):
        raise RuleError("Неизвестная операция")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise RuleError("Выберите файл .xlsx", "R-IMP-01")
    fo = await save_file(session, await file.read(), file.filename, "import", "ts", "import", user)
    log = ImportLog(name=kind, file_name=fo.name, file_id=fo.id, username=user.fio, state="queued", description="Операция поставлена в очередь")
    session.add(log)
    await session.commit()
    log_id = log.id
    mode = await submit_job("import_xlsx", {"log_id": log_id, "kind": kind, "file_id": fo.id, "username": user.fio})
    kick_outbox()
    log = await session.get(ImportLog, log_id, populate_existing=True)
    return {"id": log.id, "state": log.state, "mode": mode, "description": log.description, "loaded": log.loaded, "total": log.total, "warnings": log.warnings}


@router.get("/logs")
async def logs(page: Page = Depends(), session=Session, user: CurrentUser = User):
    return await paginate(session, select(ImportLog).order_by(ImportLog.id.desc()), page, lambda l: {
        "id": l.id, "date": l.at.isoformat() if l.at else "", "name": l.name, "file": l.file_name, "fileId": l.file_id, "description": l.description,
        "author": l.username, "state": l.state, "loaded": l.loaded, "total": l.total, "warnings": l.warnings})


@router.get("/logs/entries")
async def log_entries(log_id: int | None = None, level: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    stmt = select(ImportLogEntry, ImportLog).join(ImportLog, ImportLogEntry.log_id == ImportLog.id)
    if log_id:
        stmt = stmt.where(ImportLogEntry.log_id == log_id)
    if level:
        stmt = stmt.where(ImportLogEntry.level == level)
    rows = (await session.execute(stmt.order_by(ImportLogEntry.id.desc()).offset((page.page - 1) * page.size).limit(page.size))).all()
    return {"items": [{"id": e.id, "date": e.at.isoformat() if e.at else "", "name": l.name, "level": e.level, "file": l.file_name, "text": e.text, "row": e.row_ref}
                      for e, l in rows]}


# ---------- Поиск (R-SRCH-01) ----------
def wildcard_to_like(q: str) -> tuple[str, bool]:
    """«*» — любая последовательность, «?» — один символ, «\\» — экранирование. Возвращает LIKE-шаблон."""
    out, i, has = [], 0, False
    while i < len(q):
        c = q[i]
        if c == "\\" and i + 1 < len(q):
            nxt = q[i + 1]
            out.append("\\" + nxt if nxt in "%_\\" else nxt)
            i += 2
            continue
        if c == "*":
            out.append("%")
            has = True
        elif c == "?":
            out.append("_")
            has = True
        elif c in "%_":
            out.append("\\" + c)
        else:
            out.append(c)
        i += 1
    return "".join(out), has


@router.get("/search")
async def search(q: str = "", classes: str = "", deo: str = "", date_from: str = "", date_to: str = "", exact: bool = False, attachments: bool = True,
                 limit: int = 100, session=Session, user: CurrentUser = User):
    if len(q) > 1000:
        raise RuleError("Строка поиска — не более 1000 символов", "R-SRCH-01")
    pat, has_wild = wildcard_to_like(q.strip())
    like = pat if (exact or has_wild) else f"%{pat}%"
    want = set(filter(None, classes.split(","))) or {"eo", "tm", "ts"}
    dfrom, dto = parse_date(date_from), parse_date(date_to)
    out = []

    def dok(d):
        return (not dfrom or (d and d >= dfrom)) and (not dto or (d and d <= dto))

    if "eo" in want:
        stmt = scoped(select(EquipmentUnit), EquipmentUnit, user).where(or_(EquipmentUnit.name.ilike(like, escape="\\"), EquipmentUnit.code.ilike(like, escape="\\")))
        if deo:
            stmt = stmt.where(EquipmentUnit.deo == deo)
        for e in (await session.execute(stmt.limit(limit))).scalars():
            if dok(e.updated_at.date() if e.updated_at else None):
                out.append({"kind": "eo", "id": e.id, "name": e.name, "code": e.code, "cls": "Единица оборудования", "desc": e.tm.name if e.tm else "", "deo": e.deo,
                            "created": svc.iso(e.created_at.date()), "author": "МП-3 «БДО»" if e.origin == "asupp" else "БДТС", "modAuthor": "Синхронизация",
                            "mod": svc.iso(e.updated_at.date()), "link": f"/eo/{e.id}", "lvl": 1})
    if "tm" in want:
        stmt = scoped(select(TechPlace), TechPlace, user).where(or_(TechPlace.name.ilike(like, escape="\\"), TechPlace.code.ilike(like, escape="\\")))
        if deo:
            stmt = stmt.where(TechPlace.deo == deo)
        for t in (await session.execute(stmt.limit(limit))).scalars():
            if dok(t.updated_at.date() if t.updated_at else None):
                out.append({"kind": "tm", "id": t.id, "name": t.name, "code": t.code, "cls": "Техническое место", "desc": t.sor_name, "deo": t.deo,
                            "created": svc.iso(t.created_at.date()), "author": "МП-3 «БДО»", "modAuthor": "Синхронизация", "mod": svc.iso(t.updated_at.date()),
                            "link": f"/tm/{t.id}", "lvl": 1})
    if "ts" in want and attachments:
        stmt = scoped(select(TsRecord), TsRecord, user).join(EquipmentUnit, TsRecord.eo_id == EquipmentUnit.id, isouter=True).where(
            or_(TsRecord.number.ilike(like, escape="\\"), EquipmentUnit.name.ilike(like, escape="\\")))
        if deo:
            stmt = stmt.where(TsRecord.deo == deo)
        for r in (await session.execute(stmt.limit(limit))).unique().scalars():
            if dok(r.reg_date):
                out.append({"kind": "ts", "id": r.id, "name": f"Запись о ТС № {r.number}", "code": r.number, "cls": "Запись о техническом состоянии",
                            "desc": r.record_type, "deo": r.deo, "created": svc.iso(r.reg_date), "author": "БДТС", "modAuthor": r.confirmed_by or "—",
                            "mod": svc.iso(r.updated_at.date()), "link": f"/ts-records/{r.id}", "lvl": 2})
    return {"items": out[:limit], "total": len(out)}


class SavedSearchIn(BaseModel):
    name: str
    query: str = ""
    filters: list = []


@router.get("/saved-searches")
async def saved_searches(session=Session, user: CurrentUser = User):
    rows = (await session.execute(select(SavedSearch).where(SavedSearch.username == user.username).order_by(SavedSearch.id.desc()))).scalars().all()
    return [{"id": s.id, "name": s.name, "query": s.query, "filters": s.filters} for s in rows]


@router.post("/saved-searches")
async def add_saved_search(body: SavedSearchIn, session=Session, user: CurrentUser = User):
    if not body.name.strip():
        raise RuleError("Укажите название шаблона поиска")
    s = SavedSearch(username=user.username, name=body.name.strip()[:255], query=body.query[:1000], filters=body.filters)
    session.add(s)
    await session.commit()
    return {"id": s.id}


@router.delete("/saved-searches/{sid}")
async def del_saved_search(sid: int, session=Session, user: CurrentUser = User):
    s = await session.get(SavedSearch, sid)
    if s and s.username == user.username:
        await session.delete(s)
        await session.commit()
    return {"ok": True}
