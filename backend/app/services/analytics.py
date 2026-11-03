"""W-4.1 Аналитика (Б320), Δ W-4.2 дашборды D1–D5, Δ W-0.4 личный кабинет — расчёт по данным хранилища (витрина Б320)."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import (
    Discrepancy, DoResult, DoTask, EquipmentUnit, PlanningExport, PlanObject, TechnicalReport, TechnicalReportEo, TechPlace, TsMeasure,
    TsMeasurement, TsMessage, TsRecord,
)
from app.permissions import CurrentUser
from app.services.common import get_setting
from app.services.ts import STATE_RANK, aggregate_state

VID_KEYS = ["tpa", "vessel", "wellhead", "grs", "vtd"]
CLASS_ORDER = ["ТПА", "Сосуды и аппараты", "ФА и КГ", "ГРС", "ЛЧ МГ"]
STATES = ["Исправное", "Работоспособное", "Ограниченно работоспособное", "Неработоспособное"]


def _deo(stmt, model, deo: str):
    return stmt.where(model.deo == deo) if deo else stmt


async def _eos(session, deo: str) -> list[EquipmentUnit]:
    return (await session.execute(_deo(select(EquipmentUnit).where(EquipmentUnit.parent_id.is_(None)), EquipmentUnit, deo))).scalars().all()


async def dashboard(session, tab: str, deo: str, user: CurrentUser, eo_id: int | None = None) -> dict:
    deo = user.deo or deo
    today = date.today()
    stamp = datetime.now(timezone.utc).isoformat()
    if tab == "D1":
        eos = await _eos(session, deo)
        agg = await aggregate_state(session, eo_ids=[e.id for e in eos])
        nexts = {e.id: date.fromisoformat(agg[f"eo:{e.id}"]["next"]) for e in eos if agg.get(f"eo:{e.id}", {}).get("next")}
        tasks = (await session.execute(_deo(select(DoTask), DoTask, deo))).scalars().all()
        active_eo = {t.eo_id for t in tasks if t.status != "Выполнено"}
        due12 = [i for i, d in nexts.items() if d <= today + timedelta(days=365)]
        overdue = [i for i, d in nexts.items() if d < today and i not in active_eo]
        no_data = [e.id for e in eos if f"eo:{e.id}" not in agg]
        objs = (await session.execute(_deo(select(PlanObject), PlanObject, deo))).scalars().all()
        covered = {t.plan_object_id for t in tasks if t.plan_object_id} | {o.id for o in objs if any(t.xyz.startswith(o.cipher) for t in tasks)}
        year = today.year + (1 if today.month >= 9 else 0)
        load = [[0] * 5 for _ in range(12)]
        for t in tasks:
            if t.start_date.year in (year, year - 1) and t.vid in VID_KEYS:
                load[t.start_date.month - 1][VID_KEYS.index(t.vid)] += 1
        for i, d in nexts.items():
            if d.year == year:
                e = next(x for x in eos if x.id == i)
                k = {"ТПА": 0, "Сосуды и аппараты": 1, "ФА и КГ": 2, "ГРС": 3, "ЛЧ МГ": 4}.get(e.eq_class, 0)
                load[d.month - 1][k] += 1
        cap = (await get_setting(session, "planning", {})).get("brigade_capacity", 6)
        heat = defaultdict(lambda: [[0, 0, 0, 0], [0, 0, 0, 0]])
        for e in eos:
            d = nexts.get(e.id)
            if d and d.year <= year:
                q = (d.month - 1) // 3 if d.year == year else 0
                heat[e.deo][0][q] += 1
                if d < today:
                    heat[e.deo][1][q] += 1
        cand_less, cand_more = [], []
        for e in eos:
            a = agg.get(f"eo:{e.id}", {})
            life = a.get("life")
            if life is not None and life >= 10 and STATE_RANK.get(a.get("st", ""), 3) <= 1:
                cand_less.append([e.name, a.get("st", ""), f"{life:g} лет", "Увеличить интервал ТД"])
            elif (life is not None and life < 5) or STATE_RANK.get(a.get("st", ""), 0) >= 2:
                cand_more.append([e.name, "Ресурс < 1 интервала" if life is not None and life < 5 else f"ТС: {a.get('st')}", f"{life:g} лет" if life is not None else "—"])
        return {"tab": tab, "stamp": stamp, "year": year,
                "kpi": {"due12": len(due12), "overdue": len(overdue), "noData": len(no_data), "coverage": round(100 * len(covered) / len(objs)) if objs else 0,
                        "coverageText": f"{len(covered)} из {len(objs)} объектов ПП"},
                "load": load, "capacity": cap, "heat": [[k, v[0], v[1]] for k, v in sorted(heat.items())], "lessScope": cand_less[:8], "moreScope": cand_more[:8]}
    if tab == "D2":
        eos = await _eos(session, deo)
        agg = await aggregate_state(session, eo_ids=[e.id for e in eos])
        recs = (await session.execute(_deo(select(TsRecord).where(TsRecord.eo_id.isnot(None)), TsRecord, deo).order_by(TsRecord.reg_date.desc()))).scalars().all()
        hist = defaultdict(list)
        for r in recs:
            if r.object_status:
                hist[r.eo_id].append(r.object_status)
        worse = [i for i, h in hist.items() if len(h) > 1 and STATE_RANK.get(h[0], 0) > STATE_RANK.get(h[1], 0)]
        lives = [agg[k]["life"] for k in agg if agg[k].get("life") is not None]
        dist = {}
        for cls in CLASS_ORDER:
            c = Counter(agg.get(f"eo:{e.id}", {}).get("st", "") for e in eos if e.eq_class == cls)
            tot = sum(c[s] for s in STATES) or 1
            dist[cls] = [round(100 * c[s] / tot) for s in STATES]
        bins = [("0–2", 0, 2), ("2–5", 2, 5), ("5–7", 5, 7), ("7–10", 7, 10), ("> 10", 10, 999)]
        risk = defaultdict(lambda: [0, 0, 0])
        msgs = (await session.execute(select(TsMessage, TsRecord).join(TsRecord, TsMessage.record_id == TsRecord.id).where(TsMessage.fix_status != "Устранен"))).all()
        tm_root = await _tm_roots(session)
        for m, r in msgs:
            if deo and r.deo != deo:
                continue
            root = tm_root.get(r.tm_id, ("—", ""))
            risk[root][0 if m.criticality == "Высокая" else 1] += 1
        for k in agg:
            if agg[k].get("life") is not None and agg[k]["life"] < 2:
                eo = next((e for e in eos if f"eo:{e.id}" == k), None)
                if eo:
                    risk[tm_root.get(eo.tm_id, ("—", ""))][2] += 1
        top = sorted(([name, d, *v, v[0] * 3 + v[1] + v[2] * 5] for (name, d), v in risk.items()), key=lambda x: -x[-1])[:6]
        return {"tab": tab, "stamp": stamp,
                "kpi": {"controlled": len([e for e in eos if f"eo:{e.id}" in agg]), "worse": len(worse), "life7": sum(1 for x in lives if x < 7),
                        "life2": sum(1 for x in lives if x < 2), "confirm": sum(1 for r in recs if r.confirm_status == "Требует подтверждения")},
                "dist": dist, "life": [[lbl, sum(1 for x in lives if lo <= x < hi)] for lbl, lo, hi in bins], "risk": top}
    if tab == "D3":
        rows = (await session.execute(select(TsMessage, TsRecord).join(TsRecord, TsMessage.record_id == TsRecord.id))).all()
        rows = [(m, r) for m, r in rows if not deo or r.deo == deo]
        measures = (await session.execute(select(TsMeasure, TsRecord).join(TsRecord, TsMeasure.record_id == TsRecord.id))).all()
        rec_with_measure = {r.id for _, r in measures if not deo or r.deo == deo}
        repaired = {r.id for m, r in measures if m.fact_end and (not deo or r.deo == deo)}
        open_ = [(m, r) for m, r in rows if m.fix_status != "Устранен"]
        no_measure = [(m, r) for m, r in open_ if r.id not in rec_with_measure]
        funnel = [["Выявлено", len(rows)], ["С мероприятием", sum(1 for _, r in rows if r.id in rec_with_measure)],
                  ["Отремонтировано", sum(1 for _, r in rows if r.id in repaired)], ["Устранено", sum(1 for m, _ in rows if m.fix_status == "Устранен")],
                  ["ТС подтверждено", sum(1 for m, r in rows if m.fix_status == "Устранен" and r.confirm_status == "Подтверждено")]]
        ages = [0, 0, 0, 0]
        for m, r in open_:
            days = (today - (m.journal_date or r.reg_date)).days
            ages[0 if days < 90 else 1 if days < 180 else 2 if days < 365 else 3] += 1
        urgent = []
        for m, r in open_[:12]:
            meas = next((x for x, rr in measures if rr.id == r.id), None)
            deadline = meas.plan_end if meas and meas.plan_end else (m.journal_date or r.reg_date) + timedelta(days=180 if m.criticality == "Высокая" else 365)
            urgent.append({"defect": m.description, "eo": r.eo.name if r.eo else "", "measure": f"{meas.kind}: {meas.name}" if meas else "Не включено",
                           "deadline": deadline.isoformat(), "days": (deadline - today).days, "recordId": r.id})
        await_confirm = sum(1 for _, r in measures if r.confirm_status != "Подтверждено" and r.id in repaired)
        return {"tab": tab, "stamp": stamp, "kpi": {"noMeasure": len(no_measure), "inPlan": len(rec_with_measure), "awaitConfirm": await_confirm,
                                                     "repeat": _repeat_defects(rows)},
                "funnel": funnel, "ages": [["0–3 мес.", ages[0]], ["3–6 мес.", ages[1]], ["6–12 мес.", ages[2]], ["> 12 мес.", ages[3]]],
                "urgent": sorted(urgent, key=lambda x: x["days"])}
    if tab == "D4":
        reps = (await session.execute(_deo(select(TechnicalReport), TechnicalReport, deo))).scalars().all()
        cnt = Counter(r.status for r in reps)
        sla = 5
        overdue = 0
        returned = 0
        pareto = Counter()
        for r in reps:
            if r.status in ("На рассмотрении ДЭО", "На согласовании в ДЭО") and r.history and (datetime.now(timezone.utc) - _aware(r.history[-1].at)).days > sla:
                overdue += 1
            if any(h.status == "На доработке" for h in r.history):
                returned += 1
            for v in r.versions:
                for i in v.validation.get("issues", []):
                    pareto[(i["id"], i["text"][:60])] += 1
        unmapped = (await session.execute(select(func.count()).select_from(TechnicalReportEo).where(TechnicalReportEo.bdo_eo_id.is_(None), TechnicalReportEo.repair_object.is_(False)))).scalar_one()
        return {"tab": tab, "stamp": stamp, "statuses": [[s, cnt.get(s, 0)] for s in ["Загружен", "На рассмотрении ДЭО", "На согласовании в ДЭО", "На доработке", "Завершено ДЭО"]],
                "kpi": {"overdue": overdue, "returnShare": round(100 * returned / len(reps)) if reps else 0, "unmapped": unmapped},
                "pareto": [[k[0], k[1], v] for k, v in pareto.most_common(6)]}
    if tab == "D5":
        eos = await _eos(session, deo)
        if not eos:
            return {"tab": tab, "stamp": stamp, "eo": None, "options": []}
        options = [{"id": e.id, "label": f"{e.code} · {e.name}"} for e in eos]
        eo = next((e for e in eos if e.id == eo_id), None) or eos[0]
        agg = (await aggregate_state(session, eo_ids=[eo.id])).get(f"eo:{eo.id}", {})
        recs = (await session.execute(select(TsRecord).where(TsRecord.eo_id == eo.id).order_by(TsRecord.reg_date))).scalars().all()
        series = defaultdict(list)
        for r in recs:
            for m in (await session.execute(select(TsMeasurement).where(TsMeasurement.record_id == r.id, TsMeasurement.unit == "мм"))).scalars():
                if m.value_num is not None:
                    series[r.reg_date.year].append(m.value_num)
        thick = [[y, round(min(v), 2)] for y, v in sorted(series.items())]
        s_calc = float(eo.s_calc.replace(",", ".")) if eo.s_calc else None
        rate = None
        if len(thick) >= 2 and thick[-1][0] != thick[0][0]:
            rate = round((thick[0][1] - thick[-1][1]) / (thick[-1][0] - thick[0][0]), 3)
        timeline = []
        for r in reversed(recs):
            timeline.append({"date": r.reg_date.isoformat(), "text": f"{r.record_type}: {r.object_status or '—'}", "bad": False, "recordId": r.id})
            for m in (await session.execute(select(TsMessage).where(TsMessage.record_id == r.id))).scalars():
                timeline.append({"date": (m.journal_date or r.reg_date).isoformat(), "text": f"◆ {m.description}", "bad": True, "recordId": r.id})
        open_def = [{"crit": m.criticality, "text": m.description, "fix": m.fix_status} for r in recs for m in
                    (await session.execute(select(TsMessage).where(TsMessage.record_id == r.id, TsMessage.fix_status != "Устранен"))).scalars()]
        return {"tab": tab, "stamp": stamp, "options": options,
                "eo": {"id": eo.id, "code": eo.code, "name": eo.name, "tm": eo.tm.code if eo.tm else "", "tmName": eo.tm.name if eo.tm else "", "sync": eo.sync_status,
                       "state": agg.get("st", ""), "life": agg.get("life"), "next": agg.get("next", ""), "sCalc": s_calc},
                "thickness": thick, "rate": rate, "timeline": timeline[:14], "openDefects": open_def}
    return {"tab": tab}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _repeat_defects(rows) -> int:
    c = Counter((r.eo_id, m.defect_code) for m, r in rows if m.defect_code)
    return sum(1 for v in c.values() if v > 1)


async def _tm_roots(session) -> dict[int, tuple[str, str]]:
    tms = {t.id: t for t in (await session.execute(select(TechPlace))).scalars()}
    out = {}
    for t in tms.values():
        root = t
        while root.parent_id and root.parent_id in tms:
            root = tms[root.parent_id]
        out[t.id] = (root.name, root.deo)
    return out


async def activities_report(session, user: CurrentUser, p: dict) -> list[list]:
    """Отчёт о мероприятиях ДТОиР по ЕО (Приложение 1 ТПР)."""
    deo = user.deo or p.get("deo", "")
    d_from, d_to = p.get("from") or "1900-01-01", p.get("to") or "2999-12-31"
    works = set(p.get("works") or [])
    tms, eos = set(p.get("tm") or []), set(int(x) for x in p.get("eo") or [])
    out = []
    recs = (await session.execute(select(TsRecord).where(TsRecord.reg_date >= date.fromisoformat(d_from), TsRecord.reg_date <= date.fromisoformat(d_to)))).scalars().all()
    for r in recs:
        if deo and r.deo != deo or (tms and (not r.tm or r.tm.code not in tms)) or (eos and r.eo_id not in eos) or not r.eo:
            continue
        if r.record_type == "Диагностическое обследование" and (not works or "Диагностическое обследование" in works):
            out.append([r.description[:120] or "Диагностическое обследование", r.eo.position or r.eo.tech_number, r.eo.name, r.eo.model,
                        "Диагностическое обследование", r.reg_date.strftime("%d.%m.%Y"), ""])
        for m in (await session.execute(select(TsMeasure).where(TsMeasure.record_id == r.id))).scalars():
            if works and m.kind not in works:
                continue
            out.append([m.name, r.eo.position or r.eo.tech_number, r.eo.name, r.eo.model, m.kind,
                        m.fact_end.strftime("%d.%m.%Y") if m.fact_end else "—", m.fail_reason])
    return out


async def cabinet(session, user: CurrentUser, deo: str = "") -> dict:
    """W-0.4: виджеты по ролям пользователя (объединённые, без переключения ролей). ДЭО — из учётной записи или из фильтра кабинета."""
    deo = user.deo or deo
    q = lambda m, stmt: _deo(stmt, m, deo)  # noqa: E731
    widgets = []

    async def n(stmt):
        return (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    def by_eo(stmt):
        return stmt.join(EquipmentUnit, Discrepancy.eo_id == EquipmentUnit.id).where(EquipmentUnit.deo == deo) if deo else stmt

    if user.can("task.approve"):
        widgets.append({"title": "Задания на согласовании", "count": await n(q(DoTask, select(DoTask.id).where(DoTask.status == "На согласовании"))), "link": "/tasks", "badge": "На согласовании"})
    if user.can("task.send"):
        widgets.append({"title": "Задания на корректировке", "count": await n(q(DoTask, select(DoTask.id).where(DoTask.status.in_(["Черновик", "На корректировке"])))), "link": "/tasks", "badge": "На корректировке"})
    for action, st, title in (("result.pe", "ПЭ не завершен", "Полевой этап не завершён"), ("result.kp", "Требуется КП", "Требуется камеральная проверка"),
                              ("result.agree", "На согласовании", "Результаты ДО на согласовании"), ("result.deo", "На рассмотрении ДЭО", "Результаты ДО на рассмотрении ДЭО"),
                              ("result.epb", "Требуется ЭПБ", "Требуется ЭПБ"), ("result.export", "Результат получен", "Результаты ДО получены")):
        if user.can(action):
            stmt = select(DoResult.id).join(DoTask, DoResult.task_id == DoTask.id).where(DoResult.status == st)
            if deo:
                stmt = stmt.where(DoTask.deo == deo)
            widgets.append({"title": title, "count": await n(stmt), "link": "/results", "badge": st})
    if user.can("to.decide") or user.can("plan"):
        widgets.append({"title": "ТО на согласовании в ДЭО", "count": await n(q(TechnicalReport, select(TechnicalReport.id).where(TechnicalReport.status.in_(["На рассмотрении ДЭО", "На согласовании в ДЭО"])))),
                        "link": "/reports", "badge": "На согласовании в ДЭО"})
    if user.can("to.upload"):
        widgets.append({"title": "ТО на доработке", "count": await n(q(TechnicalReport, select(TechnicalReport.id).where(TechnicalReport.status == "На доработке"))), "link": "/reports", "badge": "На доработке"})
    if user.can("plan"):
        exports = (await session.execute(select(PlanningExport))).scalars().all()
        if deo:
            eo_deo = dict((await session.execute(select(EquipmentUnit.id, EquipmentUnit.deo))).all())
            exports = [x for x in exports if any(eo_deo.get(i) == deo for i in x.eo_ids or [])]
        widgets.append({"title": "Входящие перечни к планированию", "count": len(exports), "link": "/planning", "badge": "Требует подтверждения"})
    if user.can("survey"):
        overdue = await n(by_eo(select(Discrepancy.id).where(Discrepancy.status != "Всё введено", Discrepancy.due < date.today())))
        widgets.append({"title": "Запросы на расхождения", "count": await n(by_eo(select(Discrepancy.id).where(Discrepancy.status != "Всё введено"))), "link": "/surveys?tab=disc",
                        "badge": "Просрочен" if overdue else "Требует подтверждения"})
    if user.can("ts.confirm") or user.can("plan"):
        widgets.append({"title": "Записи о ТС ждут подтверждения", "count": await n(q(TsRecord, select(TsRecord.id).where(TsRecord.confirm_status == "Требует подтверждения"))),
                        "link": "/ts-records?confirm=Требует подтверждения", "badge": "Требует подтверждения"})
    widgets.append({"title": "Единицы оборудования на контроле", "count": await n(q(EquipmentUnit, select(EquipmentUnit.id).where(EquipmentUnit.parent_id.is_(None)))),
                    "link": "/hierarchy", "badge": "Действует"})
    return {"widgets": widgets, "deo": deo}
