"""Δ W-3.7 Подготовка к планированию: отбор ЕО по признакам, раздельные метки плана (D-PLN-02), история выгрузок (D-PLN-01)."""
from datetime import date, timedelta

from sqlalchemy import select

from app.errors import RuleError
from app.models import EquipmentUnit, PlanningExport, PlanningMark, TsMeasure, TsMessage, TsRecord
from app.permissions import CurrentUser
from app.services.common import audit, next_number, notify
from app.services.events import emit
from app.services.ts import aggregate_state, scope

CRITERIA = ["Дефекты прошлого периода", "Истекает срок ЭПБ", "После КР", "Давно не обследовались", "Новые объекты",
            "Нет паспорта", "АВР", "Метки плана", "Обходы"]


async def candidates(session, user: CurrentUser, criteria: list[str], q: str = "") -> list[dict]:
    eos = (await session.execute(scope(select(EquipmentUnit).where(EquipmentUnit.parent_id.is_(None)), EquipmentUnit, user).order_by(EquipmentUnit.code))).scalars().all()
    ids = [e.id for e in eos]
    agg = await aggregate_state(session, eo_ids=ids)
    recs = (await session.execute(select(TsRecord).where(TsRecord.eo_id.in_(ids or [-1])))).scalars().all()
    by_eo: dict[int, list[TsRecord]] = {}
    for r in recs:
        by_eo.setdefault(r.eo_id, []).append(r)
    open_def = {}
    for m, eo_id in (await session.execute(select(TsMessage, TsRecord.eo_id).join(TsRecord, TsMessage.record_id == TsRecord.id)
                                           .where(TsRecord.eo_id.in_(ids or [-1]), TsMessage.fix_status != "Устранен"))).all():
        open_def.setdefault(eo_id, []).append(m)
    marks = {m.eo_id: m for m in (await session.execute(select(PlanningMark).where(PlanningMark.eo_id.in_(ids or [-1])))).scalars()}
    today = date.today()
    out = []
    for e in eos:
        rs = by_eo.get(e.id, [])
        a = agg.get(f"eo:{e.id}", {})
        nxt = date.fromisoformat(a["next"]) if a.get("next") else None
        last_do = max((r.reg_date for r in rs if r.record_type == "Диагностическое обследование"), default=None)
        flags = {
            "Дефекты прошлого периода": bool(open_def.get(e.id)),
            "Истекает срок ЭПБ": bool(nxt and nxt <= today + timedelta(days=365)),
            "После КР": any(r.record_type == "Выполнение КР" and r.reg_date >= today - timedelta(days=3 * 365) for r in rs),
            "Давно не обследовались": not last_do or last_do < today - timedelta(days=4 * 365),
            "Новые объекты": e.origin == "field_created" or bool(e.created_at and e.created_at.date() >= today - timedelta(days=365) and not rs),
            "Нет паспорта": not e.has_passport,
            "АВР": any(m.kind == "Отказ" for m in open_def.get(e.id, [])),
            "Метки плана": bool(marks.get(e.id) and (marks[e.id].mark_3y or marks[e.id].mark_next_year)),
            "Обходы": any(m.kind == "Замечание обхода" for m in open_def.get(e.id, [])),
        }
        matched = [c for c in criteria if flags.get(c)]
        if criteria and not matched:
            continue
        if q and q.lower() not in f"{e.code} {e.name}".lower():
            continue
        mk = marks.get(e.id)
        out.append({"id": e.id, "code": e.code, "name": e.name, "tm": e.tm.code if e.tm else "", "deo": e.deo, "class": e.eq_class,
                    "defects": [f"{m.defect_code or ''} {m.description}".strip() for m in open_def.get(e.id, [])][:3],
                    "epbDate": a.get("next", ""), "lastDo": last_do.isoformat() if last_do else "", "state": a.get("st", ""),
                    "mark3y": bool(mk and mk.mark_3y), "markNextYear": bool(mk and mk.mark_next_year), "matched": matched or [c for c, v in flags.items() if v]})
    return out


async def set_marks(session, eo_ids: list[int], mark: str, value: bool, user: CurrentUser) -> int:
    if mark not in ("mark3y", "markNextYear"):
        raise RuleError("Метки «3-летний план» и «Следующий год» ставятся раздельно", "D-PLN-02")
    n = 0
    for i in eo_ids:
        m = await session.get(PlanningMark, i) or PlanningMark(eo_id=i)
        setattr(m, "mark_3y" if mark == "mark3y" else "mark_next_year", value)
        m.updated_by = user.fio
        session.add(m)
        n += 1
    await audit(session, user, "plan.mark", "planning_mark", "", mark=mark, value=value, count=n)
    return n


async def export_list(session, eo_ids: list[int], recipient: str, criteria: list[str], user: CurrentUser) -> PlanningExport:
    if not eo_ids:
        raise RuleError("Выберите объекты для выгрузки перечня")
    number = await next_number(session, PlanningExport, PlanningExport.number, f"EXP-{date.today().year}-", 2)
    marks = {m.eo_id: m for m in (await session.execute(select(PlanningMark).where(PlanningMark.eo_id.in_(eo_ids)))).scalars()}
    m3 = sum(1 for i in eo_ids if marks.get(i) and marks[i].mark_3y)
    mn = sum(1 for i in eo_ids if marks.get(i) and marks[i].mark_next_year)
    mark = "3-летний план" if m3 >= mn and m3 else "Следующий год" if mn else "Без метки"
    ex = PlanningExport(number=number, username=user.display, eo_ids=eo_ids, mark=mark, recipient=recipient, criteria=criteria)
    session.add(ex)
    eos = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.id.in_(eo_ids)))).scalars().all()
    await emit(session, "plan.list", {"number": number, "recipient": recipient, "eo": [e.code for e in eos], "summary": f"{len(eos)} ЕО → {recipient}", "user": user.display},
               key=f"plan.list:{number}")
    await notify(session, "BDTS.PLANNER", f"Получен перечень {number}: {len(eos)} ЕО к планированию", f"От {user.fio}, метка: {mark}", "/planning")
    return ex


async def last_measures(session, eo_ids: list[int]) -> dict:
    rows = (await session.execute(select(TsMeasure, TsRecord.eo_id).join(TsRecord, TsMeasure.record_id == TsRecord.id).where(TsRecord.eo_id.in_(eo_ids or [-1])))).all()
    out: dict[int, list] = {}
    for m, eo in rows:
        out.setdefault(eo, []).append(m)
    return out
