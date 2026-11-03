"""Б301 Задание на ДО: статусная модель (ТПР т.84, OQ-01) и правила R-B301-01…06."""
from datetime import date

from sqlalchemy import select

from app.errors import Conflict, RuleError, not_found
from app.models import DoResult, DoResultEo, DoResultHistory, DoTask, DoTaskHistory, DoTemplate, EquipmentUnit
from app.permissions import CurrentUser
from app.seed.templates import VID_NAME
from app.services.common import audit, fmt_date, notify, parse_date

TASK_STATUSES = ["Черновик", "На согласовании", "На корректировке", "Согласовано", "Полевой этап завершен",
                 "Технический отчет сформирован", "Выполнено"]
EDITABLE = ("Черновик", "На корректировке")
REQUIRED = {"xyz": "XYZ", "eo_name": "Объект ДО", "deo": "Эксплуатирующая организация", "location": "Местоположение",
            "brigade": "Бригада", "start_date": "Плановое начало ДО", "end_date": "Плановое завершение ДО"}


def task_dict(t: DoTask, with_history: bool = False, has_result: bool | None = None) -> dict:
    d = {
        "id": t.id, "vid": t.vid, "vidDo": VID_NAME.get(t.vid, t.vid), "xyz": t.xyz, "eoId": t.eo_id, "eoName": t.eo_name,
        "deo": t.deo, "location": t.location, "brigade": t.brigade, "templateId": t.template_id, "template": t.template_name,
        "startDate": t.start_date.isoformat(), "endDate": t.end_date.isoformat(), "status": t.status, "isHs": t.is_hs,
        "version": t.version, "createdBy": t.created_by,
    }
    if has_result is not None:
        d["hasResult"] = has_result
    if with_history:
        d["history"] = [{"date": h.at.isoformat(), "user": h.username, "status": h.status, "comment": h.comment} for h in t.history]
    return d


def validate_task(data: dict) -> dict:
    """R-B301-01 (все поля обязательны), OQ-04 (для ВТД шаблон не обязателен), OQ-05 (даты)."""
    errs = {k: "Обязательное поле" for k in REQUIRED if not str(data.get(k) or "").strip()}
    if data.get("vid") != "vtd" and not data.get("template_id"):
        errs["template_id"] = "Обязательное поле"
    sd, ed = parse_date(data.get("start_date")), parse_date(data.get("end_date"))
    if data.get("start_date") and not sd:
        errs["start_date"] = "Формат даты ДД.ММ.ГГГГ"
    if data.get("end_date") and not ed:
        errs["end_date"] = "Формат даты ДД.ММ.ГГГГ"
    if sd and ed and ed < sd:
        errs["end_date"] = "Дата завершения раньше даты начала"
    if data.get("vid") not in VID_NAME:
        errs["vid"] = "Неизвестный вид ДО"
    return errs


async def _apply(session, t: DoTask, data: dict):
    tpl = await session.get(DoTemplate, data["template_id"]) if data.get("template_id") and data["vid"] != "vtd" else None
    if data.get("template_id") and data["vid"] != "vtd" and (not tpl or tpl.vid != data["vid"]):
        raise RuleError("Шаблон не соответствует виду ДО", "R-B301-02", fields={"template_id": "Шаблон другого вида ДО"})
    t.vid, t.xyz, t.eo_name, t.deo = data["vid"], data["xyz"].strip(), data["eo_name"].strip(), data["deo"]
    t.eo_id = data.get("eo_id")
    if t.eo_id is None:
        eo = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.name == t.eo_name))).scalars().first()
        t.eo_id = eo.id if eo else None
    t.location, t.brigade = data["location"].strip(), data["brigade"]
    t.template_id = tpl.id if tpl else None
    t.template_name = tpl.name if tpl else "— (для ВТД шаблон не предусмотрен)"
    t.start_date, t.end_date = parse_date(data["start_date"]), parse_date(data["end_date"])


def _check_deo(user: CurrentUser, deo: str):
    if not user.deo_allowed(deo):
        raise RuleError("Нет доступа к данным другого ДЭО", "ДЭО", 403)


async def get_task(session, task_id: int, user: CurrentUser) -> DoTask:
    t = await session.get(DoTask, task_id)
    if not t:
        raise not_found("Задание на ДО")
    _check_deo(user, t.deo)
    return t


def _history(t: DoTask, user_display: str, status: str, comment: str = ""):
    t.history.append(DoTaskHistory(username=user_display, status=status, comment=comment))


async def create_task(session, data: dict, user: CurrentUser) -> DoTask:
    errs = validate_task(data)
    if errs:
        raise RuleError("Заполните обязательные поля", "R-B301-01", fields=errs)
    _check_deo(user, data["deo"])
    t = DoTask(status="Черновик", created_by=user.display, is_hs=bool(data.get("is_hs")), start_date=date.today(), end_date=date.today())
    await _apply(session, t, data)
    session.add(t)
    _history(t, user.display, "Черновик", "Создано задание на ДО")
    await session.flush()
    await audit(session, user, "task.create", "do_task", t.id)
    return t


def _check_version(t: DoTask, version: int | None):
    if version is not None and version != t.version:
        raise Conflict()


async def update_task(session, t: DoTask, data: dict, user: CurrentUser) -> DoTask:
    _check_version(t, data.get("version"))
    if t.status not in EDITABLE:
        raise RuleError("Редактирование доступно только в статусах «Черновик» и «На корректировке»", "R-B301-03")
    errs = validate_task(data)
    if errs:
        raise RuleError("Заполните обязательные поля", "R-B301-01", fields=errs)
    await _apply(session, t, data)
    t.version += 1
    await audit(session, user, "task.edit", "do_task", t.id)
    return t


async def send_task(session, t: DoTask, user: CurrentUser, version: int | None) -> DoTask:
    _check_version(t, version)
    if t.status not in EDITABLE:
        raise RuleError("Отправить на согласование можно только из статусов «Черновик» и «На корректировке»", "R-B301-03")
    t.status = "На согласовании"
    t.version += 1
    _history(t, user.display, t.status)
    await notify(session, "BDTS.SOGLZAD", f"Задание на ДО № {t.id} передано на согласование",
                 f"Задание на ДО № {t.id} от {fmt_date(t.start_date)} передано на согласование. Согласуйте или напишите замечания.",
                 f"/tasks/{t.id}", deo=t.deo, rule_id=1)
    return t


async def create_result_for(session, t: DoTask, user_display: str = "Система", comment: str = "Создан по шаблону задания на ДО") -> DoResult:
    """R-B301-06: при согласовании создаётся результат ДО «ПЭ не завершен»; ЕО результата — дочерние ЕО объекта ДО либо сам объект."""
    existing = (await session.execute(select(DoResult).where(DoResult.task_id == t.id))).scalars().first()
    if existing:
        return existing
    r = DoResult(task_id=t.id, status="ПЭ не завершен")
    eos: list[tuple[int | None, str]] = []
    if t.eo_id:
        children = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.parent_id == t.eo_id).order_by(EquipmentUnit.id))).scalars().all()
        if children:
            eos = [(c.id, f"{c.name}{' · зав. № ' + c.factory_number if c.factory_number else ''}") for c in children]
        else:
            eo = await session.get(EquipmentUnit, t.eo_id)
            eos = [(eo.id, f"{eo.name}{' · зав. № ' + eo.factory_number if eo.factory_number else ''}")]
    if not eos:
        eos = [(None, t.eo_name)]
    r.eos = [DoResultEo(idx=i, eo_id=e, label=lbl) for i, (e, lbl) in enumerate(eos)]
    r.history = [DoResultHistory(username=user_display, status="ПЭ не завершен", comment=comment)]
    session.add(r)
    await session.flush()
    return r


async def approve_task(session, t: DoTask, decision: str, comment: str, user: CurrentUser, version: int | None) -> DoTask:
    _check_version(t, version)
    if t.status != "На согласовании":
        raise RuleError("Задание не находится на согласовании", "R-B301-03")
    comment = (comment or "").strip()
    if decision == "approve":
        t.status = "Согласовано"
        _history(t, user.display, t.status, comment or "Согласовано без замечаний")
        await create_result_for(session, t)
        await notify(session, "BDTS.ORGWORK", f"Задание на ДО № {t.id} согласовано", "Создан результат ДО в статусе «ПЭ не завершен».",
                     f"/tasks/{t.id}", rule_id=3)
        await notify(session, "BDTS.POLEV", f"Результат ДО по заданию № {t.id}: необходимо провести полевой этап",
                     f"Задание № {t.id}, объект «{t.eo_name}»", f"/results/{t.id}", deo=t.deo)
    elif decision == "rework":
        if not comment:
            raise RuleError("При возврате на корректировку комментарий обязателен", "R-B301-04", fields={"comment": "Укажите, что исправить"})
        if len(comment) > 1000:
            raise RuleError("Комментарий — не более 1000 символов", "R-B303-08")
        t.status = "На корректировке"
        _history(t, user.display, t.status, comment)
        await notify(session, "BDTS.ORGWORK", f"Задание на ДО № {t.id} отклонено", comment, f"/tasks/{t.id}", type_="Предупреждение", rule_id=2)
    else:
        raise RuleError("Неизвестное решение")
    t.version += 1
    await audit(session, user, f"task.{decision}", "do_task", t.id)
    return t


async def delete_task(session, t: DoTask, user: CurrentUser):
    if t.status != "Черновик":
        raise RuleError("Удалить можно только задание в статусе «Черновик»", "R-B301-05")
    await audit(session, user, "task.delete", "do_task", t.id)
    await session.delete(t)


TASK_BY_RESULT = {"Требуется КП": "Полевой этап завершен", "На согласовании": "Технический отчет сформирован",
                  "На корректировке": "Полевой этап завершен", "Результат получен": "Выполнено"}
