"""Δ UC-3: реестр и карточка технического отчёта XSD v3.8 (W-2.3, W-2.4)."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.deps import Page, Session, User, file_response, paginate, require, scoped
from app.models import TechnicalReport
from app.permissions import CurrentUser
from app.services import reports as svc
from app.services.events import kick_outbox
from app.services.xml_samples import sample

router = APIRouter(prefix="/reports", tags=["Технические отчёты"])


@router.get("")
async def list_reports(source: str = "", profile: str = "", status: str = "", q: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    stmt = scoped(select(TechnicalReport), TechnicalReport, user)
    if source == "gd":
        stmt = stmt.where(TechnicalReport.source.like("ИУС ГД%"))
    elif source == "hs":
        stmt = stmt.where(TechnicalReport.source == "Хозспособ")
    if profile:
        stmt = stmt.where(TechnicalReport.profile == profile)
    if status:
        stmt = stmt.where(TechnicalReport.status == status)
    if q:
        stmt = stmt.where(or_(TechnicalReport.number.ilike(f"%{q}%"), TechnicalReport.title.ilike(f"%{q}%")))
    return await paginate(session, stmt.order_by(TechnicalReport.report_date.desc(), TechnicalReport.id.desc()), page, svc.report_row)


@router.get("/sample-xml")
async def sample_xml(kind: str = "errors", user: CurrentUser = User):
    """Образцы XML v3.8 для проверки загрузки: errors — с ошибками L1, fixed — исправленная версия, new — новый отчёт."""
    name, data = sample(kind)
    return file_response(data, name, "application/xml")


@router.post("/check")
async def check(file: UploadFile = File(...), session=Session, user: CurrentUser = Depends(require("to.upload"))):
    """Шаг 3 мастера: проверка XSD v3.8 (D-TO-06) и правил модели без сохранения."""
    res = await svc.check_xml(session, await file.read())
    p = res["parsed"]
    return {"xsdOk": res["xsd_ok"], "issues": res["issues"], "summary": res["summary"], "eoCount": res.get("eoCount", 0), "unmapped": res.get("unmapped", 0),
            "number": p.get("report", {}).get("number", "") if p else "", "title": p.get("report", {}).get("title", "") if p else "",
            "exists": bool(p and (await session.execute(select(TechnicalReport.id).where(TechnicalReport.number == p["report"]["number"]))).scalar())}


@router.post("")
async def upload(file: UploadFile = File(...), attachments: list[UploadFile] = File(default=[]), report_id: int | None = Form(None),
                 session=Session, user: CurrentUser = Depends(require("to.upload"))):
    att = [(a.filename or "file", await a.read()) for a in attachments]
    rep = await svc.upload(session, await file.read(), file.filename or "report.xml", att, user, report_id)
    await session.commit()
    rep = await svc.get_report(session, rep.id, user)
    return await svc.payload(session, rep, user)


@router.get("/{rid}")
async def get_report(rid: int, session=Session, user: CurrentUser = User):
    return await svc.payload(session, await svc.get_report(session, rid, user), user)


class MappingIn(BaseModel):
    items: list[dict]


@router.put("/{rid}/mapping")
async def set_mapping(rid: int, body: MappingIn, session=Session, user: CurrentUser = Depends(require("to.map"))):
    rep = await svc.get_report(session, rid, user)
    await svc.set_mapping(session, rep, body.items, user)
    await session.commit()
    return await svc.payload(session, rep, user)


@router.post("/{rid}/suggest")
async def suggest(rid: int, session=Session, user: CurrentUser = Depends(require("to.map"))):
    rep = await svc.get_report(session, rid, user)
    n = await svc.suggest_mapping(session, rep)
    await session.commit()
    return {"matched": n, **(await svc.payload(session, rep, user))}


@router.post("/{rid}/send")
async def send(rid: int, session=Session, user: CurrentUser = Depends(require("to.send"))):
    rep = await svc.get_report(session, rid, user)
    await svc.send_to_deo(session, rep, user)
    await session.commit()
    kick_outbox()
    return await svc.payload(session, rep, user)


class DecisionIn(BaseModel):
    decision: str
    comment: str = Field("", max_length=1000)


@router.post("/{rid}/decision")
async def decision(rid: int, body: DecisionIn, session=Session, user: CurrentUser = Depends(require("to.decide"))):
    rep = await svc.get_report(session, rid, user)
    await svc.decide(session, rep, body.decision, body.comment, user)
    await session.commit()
    kick_outbox()
    rep = await svc.get_report(session, rid, user)
    return await svc.payload(session, rep, user)
