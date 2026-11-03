"""UC-1, UC-2: задания на ДО (W-1.1, W-1.2), шаблоны (W-1.3, W-1.4), результаты ДО (W-2.1, W-2.2, W-2.5)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.deps import DOCX, XLSX, Page, Session, User, file_response, paginate, require, scoped
from app.errors import RuleError, not_found
from app.models import DoResult, DoTask, DoTemplate, FileObject
from app.permissions import CurrentUser
from app.seed.templates import METHOD_OF, VID_NAME
from app.services import results as res_svc
from app.services import tasks as task_svc
from app.services.common import fmt_date
from app.services.docs import build_xlsx
from app.services.report_docx import render_result_docx
from app.services.report_xml import render_result_xml
from app.services.events import kick_outbox
from app.services.storage import read_file

router = APIRouter(tags=["Процесс ДО"])


class TaskIn(BaseModel):
    vid: str
    xyz: str = ""
    eo_id: int | None = None
    eo_name: str = ""
    deo: str = ""
    location: str = ""
    brigade: str = ""
    template_id: int | None = None
    start_date: str = ""
    end_date: str = ""
    is_hs: bool = False
    version: int | None = None


class Decision(BaseModel):
    decision: str
    comment: str = Field("", max_length=1000)
    version: int | None = None


TASK_COLS = ["№", "XYZ", "Объект ДО", "Эксплуатирующая организация", "Местоположение", "Бригада", "Шаблон", "Плановое начало ДО", "Плановое завершение ДО", "Статус"]


def _task_query(user, vid, mode, q, status, hs):
    stmt = scoped(select(DoTask), DoTask, user)
    if vid:
        stmt = stmt.where(DoTask.vid == vid)
    if mode == "Выполненные":
        stmt = stmt.where(DoTask.status == "Выполнено")
    elif mode == "Активные":
        stmt = stmt.where(DoTask.status != "Выполнено")
    if status:
        stmt = stmt.where(DoTask.status == status)
    if hs is not None:
        stmt = stmt.where(DoTask.is_hs.is_(hs))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(DoTask.xyz.ilike(like), DoTask.eo_name.ilike(like), DoTask.location.ilike(like)))
    return stmt


SORTS = {"id": DoTask.id, "xyz": DoTask.xyz, "eoName": DoTask.eo_name, "deo": DoTask.deo, "startDate": DoTask.start_date, "endDate": DoTask.end_date, "status": DoTask.status}


@router.get("/tasks")
async def list_tasks(vid: str = "", mode: str = "Активные", q: str = "", status: str = "", hs: bool | None = None, sort: str = "id", order: str = "desc",
                     page: Page = Depends(), session=Session, user: CurrentUser = User):
    col = SORTS.get(sort, DoTask.id)
    stmt = _task_query(user, vid, mode, q, status, hs).order_by(col.desc() if order == "desc" else col.asc())
    data = await paginate(session, stmt, page, task_svc.task_dict)
    ids = [t["id"] for t in data["items"]]
    if ids:
        res = {r.task_id: r.status for r in (await session.execute(select(DoResult).where(DoResult.task_id.in_(ids)))).scalars()}
        for t in data["items"]:
            t["resultStatus"] = res.get(t["id"])
    return data


@router.get("/tasks/export.xlsx")
async def export_tasks(vid: str = "", mode: str = "Активные", q: str = "", session=Session, user: CurrentUser = User):
    rows = (await session.execute(_task_query(user, vid, mode, q, "", None).order_by(DoTask.id))).scalars().all()
    data = build_xlsx("Задания на ДО", TASK_COLS, [[t.id, t.xyz, t.eo_name, t.deo, t.location, t.brigade, t.template_name, fmt_date(t.start_date), fmt_date(t.end_date), t.status] for t in rows])
    return file_response(data, "Задания_на_ДО.xlsx", XLSX)


@router.post("/tasks")
async def create_task(body: TaskIn, session=Session, user: CurrentUser = Depends(require("task.create"))):
    t = await task_svc.create_task(session, body.model_dump(), user)
    await session.commit()
    await session.refresh(t)
    return task_svc.task_dict(t, True, False)


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, session=Session, user: CurrentUser = User):
    t = await task_svc.get_task(session, task_id, user)
    has = (await session.execute(select(DoResult.id).where(DoResult.task_id == t.id))).scalar() is not None
    st = t.status
    can = {"edit": st in task_svc.EDITABLE and user.can("task.edit"), "send": st in task_svc.EDITABLE and user.can("task.send"),
           "approve": st == "На согласовании" and user.can("task.approve"), "delete": st == "Черновик" and user.can("task.delete")}
    return {**task_svc.task_dict(t, True, has), "can": can}


@router.put("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskIn, session=Session, user: CurrentUser = Depends(require("task.edit"))):
    t = await task_svc.get_task(session, task_id, user)
    await task_svc.update_task(session, t, body.model_dump(), user)
    await session.commit()
    return await get_task(task_id, session, user)


@router.post("/tasks/{task_id}/send")
async def send_task(task_id: int, body: Decision | None = None, session=Session, user: CurrentUser = Depends(require("task.send"))):
    t = await task_svc.get_task(session, task_id, user)
    await task_svc.send_task(session, t, user, body.version if body else None)
    await session.commit()
    kick_outbox()
    return await get_task(task_id, session, user)


@router.post("/tasks/{task_id}/decision")
async def decide_task(task_id: int, body: Decision, session=Session, user: CurrentUser = Depends(require("task.approve"))):
    t = await task_svc.get_task(session, task_id, user)
    await task_svc.approve_task(session, t, body.decision, body.comment, user, body.version)
    await session.commit()
    kick_outbox()
    return await get_task(task_id, session, user)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, session=Session, user: CurrentUser = Depends(require("task.delete"))):
    t = await task_svc.get_task(session, task_id, user)
    await task_svc.delete_task(session, t, user)
    await session.commit()
    return {"ok": True}


# ---------- Шаблоны Б302 ----------
def _params(sec: dict) -> list[dict]:
    base = []
    if sec.get("instrument"):
        base += [{"name": "Прибор", "type": "Ссылка (Б314)", "min": "—", "max": "—", "unit": "—", "reg": "Приборы"},
                 {"name": "Специалист", "type": "Ссылка (Б306)", "min": "—", "max": "—", "unit": "—", "reg": "Сотрудники"}]
    if sec["kind"] == "points":
        for el in sec["elements"]:
            thk = sec["mode"] == "thk"
            base.append({"name": f"{'Толщина стенки' if thk else 'Твёрдость'}: {el['name']}", "type": "Числовой",
                         "min": f"{el.get('s', 0):.2f}" if thk else str(el.get("lo", sec.get("lo"))), "max": "—" if thk else str(el.get("hi", sec.get("hi"))),
                         "unit": "мм" if thk else "HB", "reg": "Измерения и контроль"})
    if sec["kind"] == "checklist":
        base += [{"name": n, "type": "Справочное значение", "min": "—", "max": "—", "unit": "—", "reg": "Дефекты"} for _, n, _ in sec["items"]]
    if sec["kind"] == "table":
        base += [{"name": c["label"], "type": {"num": "Числовой", "select": "Справочное значение"}.get(c["type"], "Строка"), "min": "—", "max": "—", "unit": "—",
                  "reg": "Документы" if sec["code"] == "doc" else "Измерения и контроль"} for c in sec["cols"]]
    base += [{"name": f["label"], "type": {"num": "Числовой", "select": "Справочное значение", "date": "Дата"}.get(f["type"], "Строка"), "min": "—", "max": "—",
              "unit": "—", "reg": "Измерения и контроль"} for f in sec.get("fields", [])]
    return base


@router.get("/templates")
async def list_templates(vid: str = "", session=Session, user: CurrentUser = User):
    stmt = select(DoTemplate).order_by(DoTemplate.no)
    if vid:
        stmt = stmt.where(DoTemplate.vid == vid)
    return [{"id": t.id, "no": t.no, "vid": t.vid, "vidName": VID_NAME[t.vid], "name": t.name} for t in (await session.execute(stmt)).scalars()]


@router.get("/templates/{tid}")
async def get_template(tid: int, session=Session, user: CurrentUser = User):
    t = await session.get(DoTemplate, tid)
    if not t:
        raise not_found("Шаблон")
    secs = [s for s in t.config.get("sections", []) if s["kind"] != "info"]
    return {"id": t.id, "no": t.no, "vid": t.vid, "vidName": VID_NAME[t.vid], "name": t.name, "profile": t.profile,
            "sections": [{"id": 4440 + i, "code": s["code"], "title": s["title"], "stage": s["stage"], "req": s.get("req", False),
                          "subsection": {"id": 12310 + i, "name": f"Результаты: {s['title'].lower()}", "method": METHOD_OF.get(s["code"], "—")},
                          "group": {"id": 123450 + i, "name": "Стандартная", "section": METHOD_OF.get(s["code"], s["title"])},
                          "params": [{"id": 345340 + i * 100 + k, **p} for k, p in enumerate(_params(s))]} for i, s in enumerate(secs)]}


# ---------- Результаты Б303 ----------
@router.get("/results")
async def list_results(vid: str = "", mode: str = "В процессе", hs: bool | None = None, q: str = "", page: Page = Depends(), session=Session, user: CurrentUser = User):
    stmt = select(DoResult).join(DoTask, DoResult.task_id == DoTask.id)
    if user.deo:
        stmt = stmt.where(DoTask.deo == user.deo)
    if vid:
        stmt = stmt.where(DoTask.vid == vid)
    if hs is not None:
        stmt = stmt.where(DoTask.is_hs.is_(hs))
    if mode == "Получены":
        stmt = stmt.where(DoResult.status == "Результат получен")
    elif mode == "В процессе":
        stmt = stmt.where(DoResult.status.in_(res_svc.IN_PROGRESS))
    if q:
        stmt = stmt.where(or_(DoTask.eo_name.ilike(f"%{q}%"), DoTask.xyz.ilike(f"%{q}%")))
    return await paginate(session, stmt.order_by(DoTask.id.desc()), page, lambda r: {**task_svc.task_dict(r.task), "resultStatus": r.status, "resultId": r.id})


@router.get("/results/{task_id}")
async def get_result(task_id: int, session=Session, user: CurrentUser = User):
    ctx = await res_svc.load(session, task_id, user)
    return await res_svc.payload(session, ctx, user)


class SectionIn(BaseModel):
    eo_idx: int = 0
    data: dict
    version: int | None = None


@router.put("/results/{task_id}/sections/{code}")
async def save_section(task_id: int, code: str, body: SectionIn, session=Session, user: CurrentUser = User):
    ctx = await res_svc.load(session, task_id, user)
    await res_svc.save_section(session, ctx, body.eo_idx, code, body.data, user, body.version)
    await session.commit()
    ctx = await res_svc.load(session, task_id, user)
    return await res_svc.payload(session, ctx, user)


class ActionIn(BaseModel):
    decision: str = "a"
    comment: str = Field("", max_length=1000)
    file_id: int | None = None
    file_ids: list[int] = []
    version: int | None = None


@router.post("/results/{task_id}/actions/{action}")
async def result_action(task_id: int, action: str, body: ActionIn, session=Session, user: CurrentUser = User):
    ctx = await res_svc.load(session, task_id, user)
    await res_svc.do_action(session, ctx, action, body.model_dump(), user)
    await session.commit()
    kick_outbox()
    ctx = await res_svc.load(session, task_id, user)
    return await res_svc.payload(session, ctx, user)


@router.get("/results/{task_id}/export")
async def export_result(task_id: int, kind: str = "to", session=Session, user: CurrentUser = User):
    """Выгрузка ТО (.docx, R-B303-09; .xml по XSD v3.8), файлов ТО ВТД и отчёта ЭПБ."""
    ctx = await res_svc.load(session, task_id, user)
    _, exports, _ = res_svc.actions(ctx, user)
    keys = {e["key"] for e in exports}
    if kind == "to" and "export" in keys:
        data, name = await render_result_docx(session, ctx)  # всегда по актуальным данным результата ДО
        return file_response(data, name, DOCX)
    if kind == "to_xml" and "export_xml" in keys:
        data, name, _ = await render_result_xml(session, ctx)  # XSD v3.8, ошибки L1 блокируют выгрузку
        return file_response(data, name, "application/xml")
    if kind == "epb" and "export_epb" in keys:
        fo = await session.get(FileObject, ctx.r.epb_file_id)
        if not fo or fo.deleted or fo.entity_type != "do_result" or fo.entity_id != str(ctx.r.id):
            raise not_found("Файл")
        return file_response(await read_file(fo), fo.name, fo.mime)
    if kind.startswith("vtd") and "export_vtd" in keys:
        fid = int(kind[3:] or ctx.r.vtd_file_ids[0])
        if fid not in ctx.r.vtd_file_ids:
            raise not_found("Файл")
        fo = await session.get(FileObject, fid)
        if not fo or fo.deleted or fo.entity_type != "do_result" or fo.entity_id != str(ctx.r.id):
            raise not_found("Файл")
        return file_response(await read_file(fo), fo.name, fo.mime)
    raise RuleError("Выгрузка недоступна в текущем статусе для вашей роли", "R-B303-09", 403)
