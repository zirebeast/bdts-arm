"""Δ W-6.1/6.2 Участки ВТД: границы участков не пересекаются, смежность указана (D-VTD-01); импорт из Excel с отчётом об ошибках."""
import io
from datetime import date

from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.errors import RuleError
from app.models import VtdChamber, VtdSection
from app.permissions import CurrentUser
from app.services.common import audit, fmt_date

SECTION_TYPES = ["Подземный", "Подводный переход", "Надземный", "Поворот", "Переход через дороги"]
COLS = ["Код участка", "Магистральный газопровод", "Км начала", "Км конца", "Тип участка", "ДЭО", "Камера запуска (км)", "Камера приёма (км)", "Смежный участок"]


def section_row(s: VtdSection, chambers: list[VtdChamber]) -> dict:
    return {"id": s.id, "code": s.code, "pipeline": s.pipeline, "kmFrom": s.km_from, "kmTo": s.km_to, "type": s.section_type, "deo": s.deo, "tm": s.tm_code,
            "adjacent": s.adjacent_to, "status": s.status, "notes": s.notes, "history": s.history,
            "chambers": [{"id": c.id, "code": c.code, "kind": c.kind, "km": c.km, "permanent": c.permanent, "active": c.active} for c in chambers if c.section_id == s.id]}


def overlaps(sections: list[VtdSection]) -> dict[int, list[str]]:
    """Пересечения границ по одному газопроводу (D-VTD-01)."""
    out: dict[int, list[str]] = {}
    for a in sections:
        for b in sections:
            if a.id != b.id and a.pipeline == b.pipeline and a.km_from < b.km_to and b.km_from < a.km_to:
                out.setdefault(a.id, []).append(f"{b.code}: {max(a.km_from, b.km_from):g}–{min(a.km_to, b.km_to):g} км")
    return out


async def recheck(session) -> dict[int, list[str]]:
    secs = (await session.execute(select(VtdSection))).scalars().all()
    ov = overlaps(secs)
    for s in secs:
        s.status = "На корректировке" if s.id in ov else "Действует"
    return ov


def validate(data: dict) -> dict:
    errs = {}
    for k in ("code", "pipeline"):
        if not str(data.get(k) or "").strip():
            errs[k] = "Обязательное поле"
    try:
        a, b = float(str(data.get("kmFrom")).replace(",", ".")), float(str(data.get("kmTo")).replace(",", "."))
        if a < 0 or b <= a:
            errs["kmTo"] = "Км конца должен быть больше км начала"
    except (TypeError, ValueError):
        errs["kmFrom"] = "Введите число"
    return errs


async def save(session, data: dict, user: CurrentUser, sid: int | None = None) -> VtdSection:
    errs = validate(data)
    if errs:
        raise RuleError("Проверьте поля участка", "D-VTD-01", fields=errs)
    s = await session.get(VtdSection, sid) if sid else VtdSection(history=[])
    s.code, s.pipeline = data["code"].strip(), data["pipeline"].strip()
    s.km_from, s.km_to = float(str(data["kmFrom"]).replace(",", ".")), float(str(data["kmTo"]).replace(",", "."))
    s.section_type, s.deo, s.adjacent_to, s.notes = data.get("type", "Подземный"), data.get("deo", ""), data.get("adjacent", ""), data.get("notes", "")
    s.history = [*(s.history or []), {"date": fmt_date(date.today()), "user": user.fio, "text": "Изменение участка" if sid else "Создан участок"}]
    session.add(s)
    await session.flush()
    await recheck(session)
    await audit(session, user, "vtd.save", "vtd_section", s.id)
    return s


def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Участки ВТД"
    ws.append(COLS)
    ws.append(["VTD-010", "МГ «Север–Юг» нитка II", 0, 48.5, "Подземный", "ОРГ_9", 0, 48.5, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def import_xlsx(session, data: bytes, user: CurrentUser) -> dict:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    errors, created = [], 0
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(r):
            continue
        r = list(r) + [None] * 9
        d = {"code": str(r[0] or ""), "pipeline": str(r[1] or ""), "kmFrom": r[2], "kmTo": r[3], "type": str(r[4] or "Подземный"), "deo": str(r[5] or ""), "adjacent": str(r[8] or "")}
        errs = validate(d)
        if errs:
            errors.append({"row": i, "code": d["code"], "error": "; ".join(f"{k}: {v}" for k, v in errs.items())})
            continue
        exists = (await session.execute(select(VtdSection).where(VtdSection.code == d["code"]))).scalars().first()
        s = await save(session, d, user, exists.id if exists else None)
        for kind, km in (("launch", r[6]), ("receive", r[7])):
            if km not in (None, ""):
                session.add(VtdChamber(section_id=s.id, code=f"{'КЗ' if kind == 'launch' else 'КП'}-{s.code[-3:]}", kind=kind, km=float(km)))
        created += 1
    ov = await recheck(session)
    secs = {s.id: s.code for s in (await session.execute(select(VtdSection))).scalars()}
    return {"created": created, "errors": errors, "overlaps": [{"code": secs[k], "with": v} for k, v in ov.items()]}
