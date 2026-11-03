"""Δ W-3.8 Опросные листы по ЕО объектов X/Y/Z и запросы на расхождение с БДО (D-HS-01, D-DISC-01, OQ-25)."""
from datetime import date, timedelta

from sqlalchemy import select

from app.errors import RuleError, not_found
from app.models import Discrepancy, EquipmentUnit, PlanObjectEo, Survey, SurveyTemplate
from app.permissions import CurrentUser
from app.services.common import audit, next_number, notify

ANSWER_TYPES = ["Текст", "Число", "Дата", "Выбор из списка", "Да / Нет", "Фото"]
# Атрибут опросного листа → поле ЕО реплики БДО
ATTR_FIELDS = {"Заводской номер": "factory_number", "Год изготовления": "year", "DN": "dn", "PN": "pn", "Марка стали": "steel_grade",
               "s расчётная": "s_calc", "Изготовитель": "manufacturer"}
STATUSES = ["Не начат", "В работе", "Заполнен", "Принят"]


def tpl_row(t: SurveyTemplate) -> dict:
    return {"id": t.id, "name": t.name, "cls": t.eq_class, "status": t.status, "questions": t.questions}


def survey_row(s: Survey, eo: EquipmentUnit | None, tpl: SurveyTemplate | None) -> dict:
    qs = tpl.questions if tpl else []
    bdo = {q["attr"]: str(getattr(eo, ATTR_FIELDS[q["attr"]], "") or "—") for q in qs if q.get("attr") in ATTR_FIELDS} if eo else {}
    return {"id": s.id, "objectId": s.object_id, "eoId": s.eo_id, "eo": eo.name if eo else "", "eoCode": eo.code if eo else "", "templateId": s.template_id,
            "template": tpl.name if tpl else "", "owner": s.owner, "due": s.due.isoformat() if s.due else "", "status": s.status, "answers": s.answers,
            "filled": sum(1 for q in qs if str(s.answers.get(q["id"], "")).strip()), "total": len(qs), "bdo": bdo}


async def save_template(session, data: dict, user: CurrentUser, tid: int | None = None) -> SurveyTemplate:
    t = await session.get(SurveyTemplate, tid) if tid else SurveyTemplate()
    if tid and not t:
        raise not_found("Опросный лист")
    if not str(data.get("name") or "").strip():
        raise RuleError("Укажите наименование опросного листа", fields={"name": "Обязательное поле"})
    qs = []
    for i, q in enumerate(data.get("questions", [])):
        if q.get("type") not in ANSWER_TYPES:
            raise RuleError(f"Вопрос {i + 1}: неизвестный тип ответа")
        qs.append({"id": q.get("id") or f"q{i + 1}", "text": q.get("text", ""), "type": q["type"], "attr": q.get("attr", "—"), "req": bool(q.get("req"))})
    t.name, t.eq_class, t.questions = data["name"].strip(), data.get("cls", "Все классы ЕО"), qs
    if data.get("publish"):
        if not qs or any(not q["text"].strip() for q in qs):
            raise RuleError("Перед публикацией заполните тексты всех вопросов")
        t.status = "Опубликован"
    session.add(t)
    await session.flush()
    await audit(session, user, "survey.template", "survey_template", t.id)
    return t


async def generate(session, object_id: int, template_id: int, user: CurrentUser) -> int:
    tpl = await session.get(SurveyTemplate, template_id)
    if not tpl or tpl.status != "Опубликован":
        raise RuleError("Опросы формируются только по опубликованному опросному листу")
    eo_ids = list((await session.execute(select(PlanObjectEo.eo_id).where(PlanObjectEo.object_id == object_id))).scalars())
    if not eo_ids:
        raise RuleError("У объекта нет ЕО: загрузите ЕО из БДО (W-8.3)")
    existing = set((await session.execute(select(Survey.eo_id).where(Survey.object_id == object_id, Survey.template_id == template_id))).scalars())
    n = 0
    for eo_id in eo_ids:
        if eo_id in existing:
            continue
        eo = await session.get(EquipmentUnit, eo_id)
        session.add(Survey(object_id=object_id, eo_id=eo_id, template_id=template_id, owner=f"{eo.deo} (ДЭО)", due=date.today() + timedelta(days=30)))
        n += 1
    return n


async def answer(session, s: Survey, answers: dict, user: CurrentUser):
    if s.status == "Принят":
        raise RuleError("Принятый опрос не редактируется")
    s.answers = {**s.answers, **answers}
    if s.status == "Не начат":
        s.status = "В работе"


async def complete(session, s: Survey, user: CurrentUser):
    tpl = await session.get(SurveyTemplate, s.template_id)
    missing = [q for q in tpl.questions if q["req"] and not str(s.answers.get(q["id"], "")).strip()]
    if missing:
        raise RuleError(f"Не заполнены обязательные вопросы: {len(missing)}")
    s.status = "Заполнен"


async def accept(session, s: Survey, user: CurrentUser) -> int:
    """Принять опрос: расхождения ответов с БДО → запросы на расхождение (БДО только для чтения, D-HS-01)."""
    if s.status != "Заполнен":
        raise RuleError("Принять можно заполненный опрос")
    tpl = await session.get(SurveyTemplate, s.template_id)
    eo = await session.get(EquipmentUnit, s.eo_id)
    n = 0
    for q in tpl.questions:
        field = ATTR_FIELDS.get(q.get("attr", ""))
        ans = str(s.answers.get(q["id"], "")).strip()
        if not field or not ans:
            continue
        bdo = str(getattr(eo, field) or "").strip()
        if bdo != ans:
            number = await next_number(session, Discrepancy, Discrepancy.number, f"DSC-{date.today().year}-", 3)
            session.add(Discrepancy(number=number, eo_id=eo.id, attr=q["attr"], bdo_value=bdo or "—", fact_value=ans, due=date.today() + timedelta(days=30), survey_id=s.id))
            await session.flush()
            n += 1
    s.status = "Принят"
    if n:
        await notify(session, "BDTS.OTVTS", f"Создано запросов на расхождение с БДО: {n}", f"ЕО {eo.name}", "/surveys?tab=disc", type_="Предупреждение", deo=eo.deo)
    await audit(session, user, "survey.accept", "survey", s.id, discrepancies=n)
    return n


async def close_discrepancy(session, d: Discrepancy, user: CurrentUser):
    d.status = "Всё введено"
    await audit(session, user, "discrepancy.close", "discrepancy", d.id)
