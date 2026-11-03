"""Δ UC-5, UC-6, UC-7: планирование (W-3.7), опросные листы (W-3.8), ВТД (W-6.x), входящие интеграции (W-8.x), аналитика и дашборды."""
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import XLSX, Page, Session, User, file_response, paginate, require
from app.errors import RuleError, not_found
from app.models import (
    Brigade, Discrepancy, DoTask, EquipmentUnit, IntegrationLog, PlanningExport, PlanObject, PlanObjectEo, Survey, SurveyTemplate, VtdChamber, VtdSection,
)
from app.permissions import CurrentUser
from app.services import analytics, inbound, planning, surveys, vtd
from app.services.docs import build_xlsx
from app.services.events import kick_outbox

router = APIRouter(tags=["Новая концепция"])


# ---------- W-3.7 Подготовка к планированию ----------
@router.get("/planning")
async def planning_rows(criteria: str = "", q: str = "", session=Session, user: CurrentUser = User):
    return {"criteria": planning.CRITERIA, "items": await planning.candidates(session, user, [c for c in criteria.split("|") if c], q)}


class MarkIn(BaseModel):
    eoIds: list[int]
    mark: str
    value: bool = True


@router.post("/planning/marks")
async def planning_marks(body: MarkIn, session=Session, user: CurrentUser = Depends(require("plan"))):
    n = await planning.set_marks(session, body.eoIds, body.mark, body.value, user)
    await session.commit()
    return {"updated": n}


class ExportIn(BaseModel):
    eoIds: list[int]
    recipient: str = "Роль 1 (планирование ДЭО)"
    criteria: list[str] = []


@router.post("/planning/export")
async def planning_export(body: ExportIn, session=Session, user: CurrentUser = Depends(require("plan"))):
    ex = await planning.export_list(session, body.eoIds, body.recipient, body.criteria, user)
    await session.commit()
    kick_outbox()
    return {"id": ex.id, "number": ex.number}


@router.get("/planning/exports")
async def planning_exports(session=Session, user: CurrentUser = User):
    rows = (await session.execute(select(PlanningExport).order_by(PlanningExport.id.desc()).limit(50))).scalars().all()
    return [{"id": e.id, "number": e.number, "date": e.at.isoformat() if e.at else "", "user": e.username, "count": len(e.eo_ids), "mark": e.mark,
             "recipient": e.recipient, "criteria": e.criteria} for e in rows]


@router.get("/planning/exports/{eid}.xlsx")
async def planning_export_file(eid: int, session=Session, user: CurrentUser = User):
    e = await session.get(PlanningExport, eid)
    if not e:
        raise not_found("Выгрузка")
    eos = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.id.in_(e.eo_ids or [-1])))).scalars().all()
    data = build_xlsx(e.number, ["Код ЕО", "Наименование ЕО", "Техническое место", "ДЭО", "Класс", "Метка"],
                      [[x.code, x.name, x.tm.code if x.tm else "", x.deo, x.eq_class, e.mark] for x in eos])
    return file_response(data, f"{e.number}.xlsx", XLSX)


@router.post("/planning/sync-bdo")
async def planning_sync(session=Session, user: CurrentUser = Depends(require("plan"))):
    from app.integrations import registry

    res = await registry.bdo_client().sync_hierarchy()
    session.add(IntegrationLog(direction="in", flow="Синхронизация реплики ТМ/ЕО", system=registry.bdo_client().name, count=res.get("note", ""), username=user.display))
    await session.commit()
    return res


# ---------- W-3.8 Опросные листы ----------
@router.get("/survey-templates")
async def survey_templates(session=Session, user: CurrentUser = User):
    return [surveys.tpl_row(t) for t in (await session.execute(select(SurveyTemplate).order_by(SurveyTemplate.id))).scalars()]


@router.post("/survey-templates")
async def survey_template_create(body: dict, session=Session, user: CurrentUser = Depends(require("survey"))):
    t = await surveys.save_template(session, body, user)
    await session.commit()
    return surveys.tpl_row(t)


@router.put("/survey-templates/{tid}")
async def survey_template_update(tid: int, body: dict, session=Session, user: CurrentUser = Depends(require("survey"))):
    t = await surveys.save_template(session, body, user, tid)
    await session.commit()
    return surveys.tpl_row(t)


@router.get("/surveys")
async def survey_list(object_id: int | None = None, session=Session, user: CurrentUser = User):
    stmt = select(Survey)
    if object_id:
        stmt = stmt.where(Survey.object_id == object_id)
    out = []
    tpls = {t.id: t for t in (await session.execute(select(SurveyTemplate))).scalars()}
    for s in (await session.execute(stmt.order_by(Survey.id))).scalars():
        eo = await session.get(EquipmentUnit, s.eo_id)
        if eo and user.deo_allowed(eo.deo):
            out.append(surveys.survey_row(s, eo, tpls.get(s.template_id)))
    return out


class GenIn(BaseModel):
    objectId: int
    templateId: int


@router.post("/surveys/generate")
async def survey_generate(body: GenIn, session=Session, user: CurrentUser = Depends(require("survey"))):
    n = await surveys.generate(session, body.objectId, body.templateId, user)
    await session.commit()
    return {"created": n}


async def _survey(session, sid: int) -> Survey:
    s = await session.get(Survey, sid)
    if not s:
        raise not_found("Опрос")
    return s


@router.put("/surveys/{sid}/answers")
async def survey_answers(sid: int, body: dict, session=Session, user: CurrentUser = Depends(require("survey"))):
    s = await _survey(session, sid)
    await surveys.answer(session, s, body.get("answers", {}), user)
    await session.commit()
    return {"ok": True, "status": s.status}


@router.post("/surveys/{sid}/complete")
async def survey_complete(sid: int, session=Session, user: CurrentUser = Depends(require("survey"))):
    s = await _survey(session, sid)
    await surveys.complete(session, s, user)
    await session.commit()
    return {"ok": True, "status": s.status}


@router.post("/surveys/{sid}/accept")
async def survey_accept(sid: int, session=Session, user: CurrentUser = Depends(require("survey"))):
    s = await _survey(session, sid)
    n = await surveys.accept(session, s, user)
    await session.commit()
    kick_outbox()
    return {"ok": True, "discrepancies": n}


@router.get("/discrepancies")
async def discrepancies(session=Session, user: CurrentUser = User):
    rows = (await session.execute(select(Discrepancy, EquipmentUnit).join(EquipmentUnit, Discrepancy.eo_id == EquipmentUnit.id).order_by(Discrepancy.id.desc()))).all()
    return [{"id": d.id, "number": d.number, "eo": e.name, "eoId": e.id, "attr": d.attr, "bdo": d.bdo_value, "fact": d.fact_value,
             "due": d.due.isoformat() if d.due else "", "status": d.status} for d, e in rows if user.deo_allowed(e.deo)]


@router.post("/discrepancies/{did}/close")
async def discrepancy_close(did: int, session=Session, user: CurrentUser = Depends(require("survey"))):
    d = await session.get(Discrepancy, did)
    if not d:
        raise not_found("Запрос")
    await surveys.close_discrepancy(session, d, user)
    await session.commit()
    return {"ok": True}


# ---------- W-6 Участки ВТД ----------
@router.get("/vtd")
async def vtd_list(session=Session, user: CurrentUser = User):
    secs = (await session.execute(select(VtdSection).order_by(VtdSection.pipeline, VtdSection.km_from))).scalars().all()
    ch = (await session.execute(select(VtdChamber))).scalars().all()
    ov = vtd.overlaps(secs)
    return {"items": [{**vtd.section_row(s, ch), "overlaps": ov.get(s.id, [])} for s in secs], "types": vtd.SECTION_TYPES}


@router.get("/vtd/template.xlsx")
async def vtd_template(user: CurrentUser = User):
    return file_response(vtd.template_xlsx(), "Шаблон_участков_ВТД.xlsx", XLSX)


@router.post("/vtd/import")
async def vtd_import(file: UploadFile = File(...), session=Session, user: CurrentUser = Depends(require("vtd.edit"))):
    res = await vtd.import_xlsx(session, await file.read(), user)
    await session.commit()
    return res


@router.get("/vtd/{sid}")
async def vtd_card(sid: int, session=Session, user: CurrentUser = User):
    s = await session.get(VtdSection, sid)
    if not s:
        raise not_found("Участок ВТД")
    ch = (await session.execute(select(VtdChamber).where(VtdChamber.section_id == sid))).scalars().all()
    secs = (await session.execute(select(VtdSection))).scalars().all()
    tasks = (await session.execute(select(DoTask).where(DoTask.vid == "vtd"))).scalars().all()
    from app.models import DoResult, FileObject

    files = []
    for t in tasks:
        r = (await session.execute(select(DoResult).where(DoResult.task_id == t.id))).scalars().first()
        for fid in (r.vtd_file_ids if r else []):
            fo = await session.get(FileObject, fid)
            if fo:
                files.append({"id": fo.id, "name": fo.name, "task": t.id, "status": r.status})
    return {**vtd.section_row(s, ch), "overlaps": vtd.overlaps(secs).get(s.id, []), "files": files}


@router.post("/vtd")
async def vtd_create(body: dict, session=Session, user: CurrentUser = Depends(require("vtd.edit"))):
    s = await vtd.save(session, body, user)
    await session.commit()
    return {"id": s.id}


@router.put("/vtd/{sid}")
async def vtd_update(sid: int, body: dict, session=Session, user: CurrentUser = Depends(require("vtd.edit"))):
    s = await vtd.save(session, body, user, sid)
    await session.commit()
    return {"id": s.id}


# ---------- W-8 Входящие интеграции ----------
class PlanQuery(BaseModel):
    source: str = "ФМ-5.1 «Формирование планов»"
    year: int = 2027
    deo: str = ""


@router.post("/inbound/plan/preview")
async def plan_preview(body: PlanQuery, user: CurrentUser = Depends(require("int.load"))):
    return await inbound.preview(body.source, body.year, user.deo or body.deo)


@router.post("/inbound/plan/upload")
async def plan_upload(file: UploadFile = File(...), user: CurrentUser = Depends(require("int.load"))):
    rows = inbound.parse_plan_xlsx(await file.read())
    return {**inbound.check_rows(rows), "source": f"Файл {file.filename}"}


class PlanAccept(BaseModel):
    rows: list[dict]
    source: str
    year: int = 2027


@router.post("/inbound/plan/accept")
async def plan_accept(body: PlanAccept, session=Session, user: CurrentUser = Depends(require("int.load"))):
    res = await inbound.accept(session, body.rows, body.source, body.year, user)
    await session.commit()
    return res


@router.get("/inbound/log")
async def inbound_log(session=Session, user: CurrentUser = User):
    logs = (await session.execute(select(IntegrationLog).where(IntegrationLog.direction == "in").order_by(IntegrationLog.id.desc()).limit(50))).scalars().all()
    pending = (await session.execute(select(func.count()).select_from(EquipmentUnit).where(EquipmentUnit.sync_status == "pending"))).scalar_one()
    conflicts = (await session.execute(select(func.count()).select_from(EquipmentUnit).where(EquipmentUnit.sync_status == "conflict"))).scalar_one()
    plan_log = next((l for l in logs if l.flow.startswith("Пообъектный план")), None)
    from app.integrations import registry

    return {"log": [{"date": l.at.isoformat() if l.at else "", "flow": l.flow, "src": l.system, "count": l.count, "st": l.status, "user": l.username} for l in logs],
            "cards": [{"title": "Пообъектный план", "src": registry.plan_source().name, "last": plan_log.at.isoformat() if plan_log else "", "st": "Успешно" if plan_log else "Не начато"},
                      {"title": "Атрибуты ЕО", "src": registry.bdo_client().name, "last": "", "st": "С предупреждениями" if conflicts else "Успешно"},
                      {"title": "Задачи на добавление ЕО/ТМ в БДО", "src": registry.ps0_client().name, "last": f"{pending} ЕО ждут добавления", "st": "Ожидает добавления в БДО" if pending else "Успешно"}]}


@router.get("/inbound/objects")
async def objects(status: str = "Все", q: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    stmt = select(PlanObject)
    if user.deo:
        stmt = stmt.where(PlanObject.deo == user.deo)
    if status != "Все":
        stmt = stmt.where(PlanObject.status == status)
    if q:
        stmt = stmt.where((PlanObject.cipher.ilike(f"%{q}%")) | (PlanObject.name.ilike(f"%{q}%")))
    counts = dict((await session.execute(select(PlanObjectEo.object_id, func.count()).group_by(PlanObjectEo.object_id))).all())
    return await paginate(session, stmt.order_by(PlanObject.id.desc()), page, lambda o: inbound.object_row(o, counts.get(o.id, 0)))


@router.post("/inbound/objects")
async def object_create(body: dict, session=Session, user: CurrentUser = Depends(require("int.load"))):
    o = await inbound.create_local(session, body, user)
    await session.commit()
    return inbound.object_row(o, 0)


async def _object(session, oid: int, user: CurrentUser) -> PlanObject:
    o = await session.get(PlanObject, oid)
    if not o or not user.deo_allowed(o.deo):
        raise not_found("Объект диагностирования")
    return o


@router.get("/inbound/objects/{oid}")
async def object_card(oid: int, session=Session, user: CurrentUser = User):
    o = await _object(session, oid, user)
    eos = await inbound.object_eos(session, oid)
    brig = (await session.execute(select(Brigade).where(Brigade.name == o.brigade))).scalars().first() or (await session.execute(select(Brigade))).scalars().first()
    task = (await session.execute(select(DoTask).where((DoTask.plan_object_id == oid) | (DoTask.xyz.like(f"{o.cipher}%"))))).scalars().first()
    return {**inbound.object_row(o, len(eos)), "eos": [inbound.eo_card(e, l) for e, l in eos], "brigade": {"name": brig.name if brig else "", "members": brig.members if brig else []},
            "taskId": task.id if task else None, "refs": {"facilityTypes": inbound.FACILITY_TYPES, "tpaTypes": inbound.TPA_TYPES, "steels": inbound.STEEL_LIST, "dn": inbound.DN_ROW}}


@router.get("/inbound/objects/{oid}/bdo")
async def object_bdo(oid: int, session=Session, user: CurrentUser = Depends(require("int.load"))):
    return await inbound.bdo_catalog(session, await _object(session, oid, user))


class BdoAdd(BaseModel):
    asupp: list[str]


@router.post("/inbound/objects/{oid}/bdo")
async def object_bdo_add(oid: int, body: BdoAdd, session=Session, user: CurrentUser = Depends(require("int.load"))):
    n = await inbound.add_from_bdo(session, await _object(session, oid, user), body.asupp, user)
    await session.commit()
    return {"added": n}


@router.post("/inbound/objects/{oid}/eo")
async def object_eo(oid: int, body: dict, session=Session, user: CurrentUser = Depends(require("int.load"))):
    eo = await inbound.create_eo(session, await _object(session, oid, user), body.get("form", {}), user, body.get("copiedFrom", ""))
    await session.commit()
    return {"id": eo.id, "code": eo.code}


@router.post("/inbound/objects/{oid}/ps0")
async def object_ps0(oid: int, session=Session, user: CurrentUser = Depends(require("int.load"))):
    n = await inbound.ps0_tasks(session, await _object(session, oid, user), user)
    await session.commit()
    return {"created": n}


# ---------- Аналитика и кабинет ----------
@router.get("/cabinet")
async def cabinet(deo: str = "", session=Session, user: CurrentUser = User):
    return await analytics.cabinet(session, user, deo)


@router.get("/dashboards/{tab}")
async def dashboards(tab: str, deo: str = "", eo_id: int | None = None, session=Session, user: CurrentUser = User):
    return await analytics.dashboard(session, tab, deo, user, eo_id)


ACT_COLS = ["Краткое описание работ", "Позиция по схеме", "Название ЕО", "Марка или тип оборудования", "Вид ремонта", "Дата выполнения", "Причины невыполнения ремонта"]


@router.post("/analytics/activities")
async def activities(body: dict, session=Session, user: CurrentUser = Depends(require("analytics"))):
    return {"columns": ACT_COLS, "rows": await analytics.activities_report(session, user, body)}


@router.post("/analytics/activities/export")
async def activities_export(body: dict, fmt: str = "xlsx", session=Session, user: CurrentUser = Depends(require("analytics"))):
    rows = await analytics.activities_report(session, user, body)
    rows = [[i + 1, *r] for i, r in enumerate(rows)]
    if fmt == "csv":
        import csv
        import io

        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["№ п/п", *ACT_COLS])
        w.writerows(rows)
        return file_response(buf.getvalue().encode("utf-8-sig"), "Отчет_о_мероприятиях_ДТОиР.csv", "text/csv")
    if fmt == "docx":
        import io

        from docx import Document

        doc = Document()
        doc.add_heading("Отчет о мероприятиях ДТОиР по ЕО", 1)
        t = doc.add_table(rows=1, cols=len(ACT_COLS) + 1)
        t.style = "Table Grid"
        for i, h in enumerate(["№ п/п", *ACT_COLS]):
            t.rows[0].cells[i].text = h
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = str(v)
        buf = io.BytesIO()
        doc.save(buf)
        return file_response(buf.getvalue(), "Отчет_о_мероприятиях_ДТОиР.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if fmt != "xlsx":
        raise RuleError("Формат не поддерживается: XLSX, CSV, DOCX")
    return file_response(build_xlsx("Мероприятия ДТОиР", ["№ п/п", *ACT_COLS], rows), "Отчет_о_мероприятиях_ДТОиР.xlsx", XLSX)
