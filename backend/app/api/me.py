"""Профиль пользователя, справочники для форм, уведомления («колокольчик»), файлы."""
from datetime import date

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import or_, select

from app.api.deps import Session, User, file_response
from app.config import get_settings
from app.errors import RuleError, not_found
from app.models import Brigade, DoTemplate, EquipmentUnit, FileObject, Notification, NotificationState, Organization, TechPlace
from app.permissions import ROLE_SCREENS, ROLES, CurrentUser
from app.seed.templates import VID_NAME, VID_ORDER, VID_SHORT
from app.services.storage import can_access_file, can_bind_file, read_file, save_file

router = APIRouter(tags=["Профиль и справочники"])

ALLOWED_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xml", ".jpg", ".jpeg", ".png", ".sig", ".zip", ".txt", ".csv"}


@router.get("/me")
async def me(user: CurrentUser = User):
    screens = sorted({s for r in user.roles for s in ROLE_SCREENS.get(r, [])})
    return {"username": user.username, "fio": user.fio, "position": user.position, "deo": user.deo, "display": user.display,
            "roles": [{"code": r, **ROLES[r]} for r in user.roles], "actions": sorted(user.actions), "editScreens": screens,
            "startRoute": user.start_route, "suiaUrl": get_settings().suia_url_template, "today": date.today().isoformat()}


@router.get("/refs")
async def refs(session=Session, user: CurrentUser = User):
    orgs = (await session.execute(select(Organization).order_by(Organization.code))).scalars().all()
    brigades = (await session.execute(select(Brigade).order_by(Brigade.name))).scalars().all()
    tpls = (await session.execute(select(DoTemplate).order_by(DoTemplate.no))).scalars().all()
    tms = (await session.execute(select(TechPlace.code, TechPlace.name).order_by(TechPlace.code))).all()
    return {
        "vids": [{"key": k, "name": VID_NAME[k], "short": VID_SHORT[k]} for k in VID_ORDER],
        "deo": [{"code": o.code, "name": o.name} for o in orgs if o.kind == "deo" and user.deo_allowed(o.code)],
        "orgs": [{"code": o.code, "name": o.name, "kind": o.kind} for o in orgs],
        "brigades": [{"name": b.name, "members": b.members} for b in brigades],
        "templates": [{"id": t.id, "no": t.no, "vid": t.vid, "name": t.name} for t in tpls],
        "tms": [{"code": c, "name": n} for c, n in tms],
    }


@router.get("/refs/eo")
async def eo_lookup(q: str = "", vid: str = "", deo: str = "", limit: int = 30, session=Session, user: CurrentUser = User):
    """Combobox ЕО с серверным поиском (раздел 8 ТЗ: большой справочник, от 2 символов)."""
    cls = {"tpa": "ТПА", "vessel": "Сосуды и аппараты", "wellhead": "ФА и КГ", "grs": "ГРС", "vtd": "ЛЧ МГ"}.get(vid)
    stmt = select(EquipmentUnit).where(EquipmentUnit.parent_id.is_(None))
    if cls:
        stmt = stmt.where(EquipmentUnit.eq_class == cls)
    if user.deo or deo:
        stmt = stmt.where(EquipmentUnit.deo == (user.deo or deo))
    if q:
        stmt = stmt.where(or_(EquipmentUnit.name.ilike(f"%{q}%"), EquipmentUnit.code.ilike(f"%{q}%")))
    rows = (await session.execute(stmt.order_by(EquipmentUnit.name).limit(min(limit, 100)))).scalars().all()
    return [{"id": e.id, "code": e.code, "name": e.name, "deo": e.deo, "tm": e.tm.code if e.tm else "", "location": e.tm.name if e.tm else ""} for e in rows]


def _note_scope(stmt, user: CurrentUser):
    stmt = stmt.where(or_(Notification.role.in_(user.roles), Notification.username == user.username))
    if user.deo:
        stmt = stmt.where(or_(Notification.deo == "", Notification.deo == user.deo))
    return stmt


@router.get("/notifications")
async def notifications(filter: str = "Все", session=Session, user: CurrentUser = User):
    rows = (await session.execute(_note_scope(select(Notification), user).order_by(Notification.id.desc()).limit(200))).scalars().all()
    states = {s.notification_id: s for s in (await session.execute(select(NotificationState).where(
        NotificationState.username == user.username, NotificationState.notification_id.in_([r.id for r in rows] or [-1])))).scalars()}
    items = []
    for n in rows:
        st = states.get(n.id)
        read = bool(st and st.read)
        if (filter == "Непрочитанные" and read) or (filter == "Прочитанные" and not read):
            continue
        items.append({"id": n.id, "type": n.type, "title": n.title, "detail": n.detail, "link": n.link, "role": ROLES.get(n.role, {}).get("label", n.role), "deo": n.deo,
                      "date": n.created_at.isoformat() if n.created_at else "", "read": read, "flagged": bool(st and st.flagged)})
    unread = sum(1 for n in rows if not (states.get(n.id) and states[n.id].read))
    return {"items": items, "unread": unread}


@router.post("/notifications/{nid}")
async def notification_state(nid: int, read: bool | None = None, flagged: bool | None = None, session=Session, user: CurrentUser = User):
    st = await session.get(NotificationState, (nid, user.username)) or NotificationState(notification_id=nid, username=user.username)
    if read is not None:
        st.read = read
    if flagged is not None:
        st.flagged = flagged
    session.add(st)
    await session.commit()
    return {"ok": True}


@router.post("/notifications-read-all")
async def notifications_read_all(session=Session, user: CurrentUser = User):
    for n in (await session.execute(_note_scope(select(Notification.id), user))).scalars():
        st = await session.get(NotificationState, (n, user.username)) or NotificationState(notification_id=n, username=user.username)
        st.read = True
        session.add(st)
    await session.commit()
    return {"ok": True}


@router.post("/files")
async def upload_file(file: UploadFile = File(...), entity_type: str = Form("draft"), entity_id: str = Form(""), kind: str = Form("attachment"),
                      session=Session, user: CurrentUser = User):
    """Загрузка файла в S3 (OQ-21: до MAX_UPLOAD_MB, типы из белого списка)."""
    name = file.filename or "file"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        raise RuleError(f"Тип файла {ext or '(без расширения)'} не поддерживается. Допустимы: {', '.join(sorted(ALLOWED_EXT))}", "OQ-21")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise RuleError(f"Размер файла превышает {get_settings().max_upload_mb} МБ", "OQ-21")
    if not await can_bind_file(session, entity_type, entity_id, user):
        raise RuleError("Нет доступа к записи другого ДЭО", "ДЭО", 403)
    fo = await save_file(session, data, name, entity_type, entity_id, kind, user)
    await session.commit()
    return {"id": fo.id, "name": fo.name, "size": fo.size, "mime": fo.mime, "sha256": fo.sha256}


@router.get("/files/{fid}")
async def download_file(fid: int, session=Session, user: CurrentUser = User):
    fo = await session.get(FileObject, fid)
    if not fo or fo.deleted or not await can_access_file(session, fo, user):
        raise not_found("Файл")  # чужой файл неотличим от отсутствующего
    return file_response(await read_file(fo), fo.name, fo.mime)


@router.delete("/files/{fid}")
async def delete_file(fid: int, session=Session, user: CurrentUser = User):
    """Удаление файла записи (R-FILE-01: с подтверждением в UI). Файл помечается удалённым — физически остаётся в S3 для аудита."""
    fo = await session.get(FileObject, fid)
    if not fo or not await can_access_file(session, fo, user):
        raise not_found("Файл")
    if fo.entity_type == "ts_record" and not user.can("ts.edit"):
        raise RuleError("Удалять файлы записи о ТС может ответственный ДЭО за контроль ТС", "R-FILE-01", 403)
    fo.deleted = True
    await session.commit()
    return {"ok": True}
