"""UC-6: НСИ Б304–Б315 (W-5.1…W-5.9), справочники модели ТО v3.8 (W-5.10), настройки модуля (W-7.1), статус интеграций."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import XLSX, Page, Session, User, file_response, paginate, require
from app.integrations.registry import adapters_status
from app.models import Dict38Entry, Dict38Version, IntegrationLog, ModuleSetting, NsiRecord, OutboxEvent
from app.permissions import DEV_USERS, ROLES, CurrentUser
from app.services import nsi as nsi_svc
from app.services.common import audit, get_setting
from app.services.docs import build_xlsx
from app.services.events import dispatch_pending

router = APIRouter(tags=["НСИ и настройки"])


@router.get("/nsi")
async def nsi_catalogs(session=Session, user: CurrentUser = User):
    counts = dict((await session.execute(select(NsiRecord.catalog, func.count()).group_by(NsiRecord.catalog))).all())
    return [{"code": k, "screen": c["screen"], "title": c["title"], "count": counts.get(k, 0)} for k, c in nsi_svc.CATALOGS.items()]


@router.get("/nsi/{code}")
async def nsi_list(code: str, q: str = "", status: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    c = nsi_svc.catalog(code)
    stmt = select(NsiRecord).where(NsiRecord.catalog == code)
    if status:
        stmt = stmt.where(NsiRecord.record_status == status)
    rows = await paginate(session, stmt.order_by(NsiRecord.record_no), page, nsi_svc.row)
    if q:
        ql = q.lower()
        rows["items"] = [r for r in rows["items"] if ql in " ".join(str(v) for v in r["data"].values()).lower() or ql in str(r["recordNo"])]
    opts = {f["key"]: nsi_svc.SELECT_OPTIONS.get((code, f["key"]), []) for f in c["fields"] if f["type"] == "select"}
    return {**rows, "schema": {**c, "code": code, "options": opts}}


@router.get("/nsi/{code}/export.xlsx")
async def nsi_export(code: str, session=Session, user: CurrentUser = User):
    c = nsi_svc.catalog(code)
    rows = (await session.execute(select(NsiRecord).where(NsiRecord.catalog == code).order_by(NsiRecord.record_no))).scalars().all()
    cols = ["ID записи", *[f["label"] for f in c["fields"]], "Статус записи", "Примечания"]
    data = build_xlsx(c["title"], cols, [[r.record_no, *[r.data.get(f["key"], "") for f in c["fields"]], r.record_status, r.notes] for r in rows])
    return file_response(data, f"{c['title']}.xlsx", XLSX)


class NsiIn(BaseModel):
    data: dict
    notes: str = ""


@router.post("/nsi/{code}")
async def nsi_create(code: str, body: NsiIn, session=Session, user: CurrentUser = Depends(require("nsi.edit"))):
    r = await nsi_svc.save(session, code, body.data, body.notes, user)
    await session.commit()
    return nsi_svc.row(r)


@router.put("/nsi/{code}/{rid}")
async def nsi_update(code: str, rid: int, body: NsiIn, session=Session, user: CurrentUser = Depends(require("nsi.edit"))):
    r = await nsi_svc.save(session, code, body.data, body.notes, user, rid)
    await session.commit()
    return nsi_svc.row(r)


@router.delete("/nsi/{code}/{rid}")
async def nsi_delete(code: str, rid: int, session=Session, user: CurrentUser = Depends(require("nsi.edit"))):
    """R-NSI-02: удаление = пометка «Помечено на удаление»."""
    r = await nsi_svc.mark_deleted(session, code, rid, user)
    await session.commit()
    return nsi_svc.row(r)


# ---------- Справочники модели ТО v3.8 ----------
DICT_GROUPS = {
    "Equipment_Types": "Технические", "Equipment_Marks": "Технические", "Climate_Executions": "Технические", "Working_Media": "Технические",
    "Control_Scheme_Variants": "Методические", "Control_Schemes": "Методические", "Steel_Grades": "Методические", "Steel_Grade_Source_Values": "Служебные",
    "Hardness_Norms": "Методические", "Building_Technical_States": "Ведомость и дефекты", "Noncompliance_Categories": "Ведомость и дефекты",
    "Admissibility_Assessments": "Ведомость и дефекты", "DTOIR_Work_Types": "Ведомость и дефекты", "Equipment_Marks_excluded": "Служебные",
}


@router.get("/dict38")
async def dict38_list(session=Session, user: CurrentUser = User):
    rows = (await session.execute(select(Dict38Entry.dictionary, Dict38Entry.verification_status, func.count()).group_by(Dict38Entry.dictionary, Dict38Entry.verification_status))).all()
    vers = {v.dictionary: v for v in (await session.execute(select(Dict38Version).where(Dict38Version.is_current.is_(True)))).scalars()}
    agg: dict[str, dict] = {}
    for d, st, n in rows:
        a = agg.setdefault(d, {"code": d, "group": DICT_GROUPS.get(d, "Служебные"), "confirmed": 0, "candidate": 0})
        a[st] = a.get(st, 0) + n
    return [{**a, "total": a["confirmed"] + a["candidate"], "version": vers[a["code"]].version if a["code"] in vers else "—",
             "publishedAt": vers[a["code"]].published_at.isoformat() if a["code"] in vers else ""} for a in sorted(agg.values(), key=lambda x: (x["group"], x["code"]))]


@router.get("/dict38/{dictionary}")
async def dict38_entries(dictionary: str, status: str = "", q: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    stmt = select(Dict38Entry).where(Dict38Entry.dictionary == dictionary)
    if status in ("confirmed", "candidate"):
        stmt = stmt.where(Dict38Entry.verification_status == status)
    if q:
        stmt = stmt.where(or_(Dict38Entry.name.ilike(f"%{q}%"), Dict38Entry.code.ilike(f"%{q}%")))
    return await paginate(session, stmt.order_by(Dict38Entry.code), page, lambda e: {
        "id": e.id, "code": e.code, "name": e.name, "status": e.verification_status, "sourceSystem": e.source_system, "sourceCode": e.source_code,
        "flags": e.quality_flags, "payload": e.payload})


class VerifyIn(BaseModel):
    status: str


@router.post("/dict38/entry/{eid}/verify")
async def dict38_verify(eid: int, body: VerifyIn, session=Session, user: CurrentUser = Depends(require("nsi.edit"))):
    e = await session.get(Dict38Entry, eid)
    if e and body.status in ("confirmed", "candidate"):
        e.verification_status = body.status
        await audit(session, user, "dict38.verify", e.dictionary, e.code, status=body.status)
        await session.commit()
    return {"ok": True}


# ---------- Настройки модуля W-7.1 ----------
SETTING_KEYS = ("routes", "notify_rules", "access", "report_period", "planning")


@router.get("/settings")
async def get_settings_all(session=Session, user: CurrentUser = User):
    out = {k: await get_setting(session, k, {}) for k in SETTING_KEYS}
    users_by_role: dict[str, list[str]] = {}
    for login, u in DEV_USERS.items():
        for r in u["roles"]:
            users_by_role.setdefault(r, []).append(f"{u['fio']} ({login})")
    out["roles"] = [{"code": r, **ROLES[r], "users": users_by_role.get(r, [])} for r in ROLES]
    out["canEdit"] = user.can("settings")
    return out


@router.put("/settings/{key}")
async def put_setting(key: str, body: dict, session=Session, user: CurrentUser = Depends(require("settings"))):
    if key not in SETTING_KEYS:
        from app.errors import not_found

        raise not_found("Настройка")
    row = await session.get(ModuleSetting, key) or ModuleSetting(key=key)
    if key == "routes":
        old = row.value or {}
        body = {**body, "version": f"v{int(str(old.get('version', 'v1'))[1:] or 1) + 1}"} if body.get("newVersion") else body
    row.value, row.updated_by = body, user.fio
    session.add(row)
    await audit(session, user, "settings.save", "module_setting", key)
    await session.commit()
    return row.value


@router.get("/integrations")
async def integrations(session=Session, user: CurrentUser = User):
    stats = dict((await session.execute(select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status))).all())
    logs = (await session.execute(select(IntegrationLog).order_by(IntegrationLog.id.desc()).limit(100))).scalars().all()
    return {"adapters": adapters_status(), "outbox": stats,
            "log": [{"id": l.id, "date": l.at.isoformat() if l.at else "", "direction": l.direction, "flow": l.flow, "system": l.system, "count": l.count,
                     "status": l.status, "user": l.username} for l in logs]}


@router.post("/integrations/outbox/retry")
async def outbox_retry(session=Session, user: CurrentUser = Depends(require("settings"))):
    return {"sent": await dispatch_pending()}
