"""Δ W-8.1–8.3 Входящие интеграции: пообъектный план → объекты X/Y/Z; ЕО объекта из МП-3 «БДО»; создание и копирование ЕО; задачи ПС-0."""
import io
import re
from datetime import date

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.errors import RuleError, not_found
from app.integrations import registry
from app.models import EquipmentUnit, IntegrationLog, PlanObject, PlanObjectEo, TechPlace
from app.permissions import CurrentUser
from app.services.common import audit, parse_date

CIPHER_RE = re.compile(r"^\d+/\d+/\d+$")
FACILITY_TYPES = ["ГРС", "КС", "УКПГ", "ДКС", "Магистральный газопровод", "Газопровод-отвод"]
TPA_TYPES = ["Задвижка клиновая", "Задвижка шиберная", "Затвор дисковый", "Клапан обратный", "Клапан предохранительный", "Кран шаровой",
             "Вентиль (клапан) запорный", "Вентиль угловой"]
STEEL_LIST = ["09Г2С", "20", "20Л", "12Х18Н9ТЛ", "GS-C25", "LCCM", "SCS13T"]
DN_ROW = [15, 20, 25, 32, 40, 50, 65, 80, 100, 150, 200, 250, 300, 400, 500, 700, 1000, 1200, 1400]


def check_rows(rows: list[dict]) -> dict:
    """Проверка строк ПП: маска шифра X/Y/Z (ошибка — строка не загружается), ЕО не определены (предупреждение)."""
    ok, errors = [], []
    for r in rows:
        cipher = str(r.get("col_1") or "").strip()
        if not CIPHER_RE.match(cipher):
            errors.append({"row": r.get("col_43") or r.get("col_1_2") or "—", "field": "Сводный код объекта ремонта (x/y/z)", "value": cipher or "—",
                           "rule": "Маска ^\\d+/\\d+/\\d+$", "level": "Ошибка"})
            continue
        if r.get("ext_warning"):
            errors.append({"row": r.get("col_43", "—"), "field": "Объект ремонта", "value": "—", "rule": r["ext_warning"], "level": "Предупреждение"})
        ok.append(r)
    return {"rows": ok, "errors": errors, "stats": {"rows": len(rows), "objects": len(ok), "errors": sum(e["level"] == "Ошибка" for e in errors),
                                                     "warnings": sum(e["level"] == "Предупреждение" for e in errors)}}


def parse_plan_xlsx(data: bytes) -> list[dict]:
    """Файл в формате ХР.xlsx: строка с кодами колонок col_* (6-я), данные ниже."""
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr_idx = next((i for i, r in enumerate(rows) if r and any(str(c).startswith("col_") for c in r if c)), None)
    if hdr_idx is None:
        raise RuleError("Не найдена строка кодов колонок (col_1, col_3 …) формата пообъектного плана")
    codes = [str(c).strip().lower() if c else "" for c in rows[hdr_idx]]
    out = []
    for r in rows[hdr_idx + 1:]:
        if not r or not any(r):
            continue
        d = {codes[i]: (v.isoformat()[:10] if hasattr(v, "isoformat") else v) for i, v in enumerate(r) if i < len(codes) and codes[i] and v is not None}
        out.append({k: str(v) if not isinstance(v, (int, float)) else v for k, v in d.items()})
    return out


async def preview(source: str, year: int, deo: str) -> dict:
    rows = await registry.plan_source().fetch_plan(year, deo)
    return {**check_rows(rows), "source": source, "year": year}


async def accept(session, rows: list[dict], source: str, year: int, user: CurrentUser) -> dict:
    """Повторная загрузка обновляет объекты по шифру, ничего не удаляя."""
    res = check_rows(rows)
    created = updated = 0
    for r in res["rows"]:
        cipher = r["col_1"].strip()
        o = (await session.execute(select(PlanObject).where(PlanObject.cipher == cipher))).scalars().first()
        if o:
            updated += 1
        else:
            o = PlanObject(cipher=cipher)
            session.add(o)
            created += 1
        o.name = r.get("col_5") or r.get("col_6") or cipher
        o.facility_type = r.get("ext_type", o.facility_type or "")
        o.reg_number, o.hazard_class, o.address = r.get("ext_reg", o.reg_number or ""), r.get("ext_hazard", o.hazard_class or ""), r.get("ext_address", o.address or "")
        o.survey_date = parse_date(r.get("ext_date") or r.get("col_12")) or o.survey_date
        o.work_kind, o.pp_row, o.plan_year, o.deo = r.get("col_7", ""), r.get("col_43", ""), year, r.get("col_3", "")
        o.customer, o.executor, o.brigade = r.get("col_4", ""), r.get("col_32", "ОРГ_1 (ГД)"), r.get("col_32_3", "")
        o.tm_code = r.get("ext_tm", o.tm_code or "")
        if not o.eo_done:
            o.eo_done = int(r.get("ext_done", 0) or 0)
        o.status = r.get("ext_status", o.status or "Не начато")
        o.source, o.raw, o.is_local = source, r, False
        o.lnk = "ЛНК № 42-НК-098"
    st = res["stats"]
    session.add(IntegrationLog(direction="in", flow=f"Пообъектный план {year}", system=source, adapter="mock",
                               count=f"{st['rows']} строк → {st['objects']} объектов (новых {created}, обновлено {updated})",
                               status="С предупреждениями" if res["errors"] else "Успешно", username=user.display, details={"errors": res["errors"]}))
    await audit(session, user, "plan.import", "plan_object", "", created=created, updated=updated)
    return {"created": created, "updated": updated, **st}


def object_row(o: PlanObject, eo_count: int) -> dict:
    total = eo_count or (o.raw or {}).get("ext_total", 0) or 0
    return {"id": o.id, "cipher": o.cipher, "name": o.name, "type": o.facility_type, "reg": o.reg_number, "hazard": o.hazard_class, "address": o.address,
            "date": o.survey_date.isoformat() if o.survey_date else "", "vid": o.work_kind, "ppRow": o.pp_row, "deo": o.deo, "customer": o.customer,
            "executor": o.executor, "lnk": o.lnk, "brigade": o.brigade, "tm": o.tm_code, "status": o.status, "local": o.is_local, "source": o.source,
            "commissionYear": o.commission_year, "total": total, "done": min(o.eo_done, total) if total else 0, "eoCount": eo_count}


def validate_object(f: dict) -> dict:
    e = {}
    if f.get("facilityType") not in FACILITY_TYPES:
        e["facilityType"] = "Выберите тип сооружения"
    if not 3 <= len(str(f.get("name") or "").strip()) <= 250:
        e["name"] = "От 3 до 250 символов"
    try:
        if not 1950 <= int(f.get("commissionYear")) <= 2100:
            raise ValueError
    except (TypeError, ValueError):
        e["commissionYear"] = "Год 1950–2100"
    if not str(f.get("regNumber") or "").strip():
        e["regNumber"] = "Обязательное поле"
    if not CIPHER_RE.match(str(f.get("cipher") or "").strip()):
        e["cipher"] = "Маска X/Y/Z: три группы цифр через «/»"
    if f.get("hazardClass") not in ("I", "II", "III", "IV"):
        e["hazardClass"] = "Выберите класс опасности"
    return e


async def create_local(session, f: dict, user: CurrentUser) -> PlanObject:
    errs = validate_object(f)
    if errs:
        raise RuleError("Проверьте поля объекта", fields=errs)
    if (await session.execute(select(PlanObject).where(PlanObject.cipher == f["cipher"].strip()))).scalars().first():
        raise RuleError("Объект с таким шифром уже есть в списке", fields={"cipher": "Шифр уже используется"})
    o = PlanObject(cipher=f["cipher"].strip(), name=f["name"].strip(), facility_type=f["facilityType"], reg_number=f["regNumber"].strip(),
                   hazard_class=f["hazardClass"], address=f.get("address", ""), commission_year=str(f["commissionYear"]), survey_date=date.today(),
                   work_kind="Вне плана", deo=user.deo or f.get("deo") or "ОРГ_9", is_local=True, source="Создан вручную (isLocal)", status="Не начато",
                   tm_code=f.get("tmCode", ""), customer="ОРГ_3")
    session.add(o)
    await session.flush()
    await audit(session, user, "object.create_local", "plan_object", o.id)
    return o


async def object_eos(session, object_id: int) -> list[tuple[EquipmentUnit, PlanObjectEo]]:
    rows = (await session.execute(select(EquipmentUnit, PlanObjectEo).join(PlanObjectEo, PlanObjectEo.eo_id == EquipmentUnit.id)
                                  .where(PlanObjectEo.object_id == object_id))).all()
    return sorted(rows, key=lambda x: (x[0].eq_type, int(re.sub(r"\D", "", x[0].factory_number) or 0), x[0].factory_number))


def eo_card(e: EquipmentUnit, link: PlanObjectEo | None) -> dict:
    return {"id": e.id, "code": e.code, "asupp": e.code if e.origin == "asupp" else "", "type": e.eq_type, "mark": e.model, "techNum": e.tech_number,
            "serialNum": e.factory_number, "year": e.year, "manufacturer": e.manufacturer, "dn": e.dn, "pn": e.pn, "sCalc": e.s_calc,
            "steelGrade": e.steel_grade, "origin": e.origin, "sync": e.sync_status, "conflict": e.sync_note,
            "copiedFrom": link.copied_from if link else "", "task": link.ps0_task if link else ""}


async def _tm_for(session, o: PlanObject) -> TechPlace:
    code = o.tm_code or f"LOCAL-{o.cipher.replace('/', '-')}"
    tm = (await session.execute(select(TechPlace).where(TechPlace.code == code))).scalars().first()
    if not tm:
        tm = TechPlace(code=code, name=o.name, deo=o.deo or "ОРГ_9", sor_name=o.name)
        session.add(tm)
        await session.flush()
    return tm


async def bdo_catalog(session, o: PlanObject) -> list[dict]:
    items = await registry.bdo_client().equipment_by_object(o.cipher, o.tm_code)
    present = {e.code for e, _ in await object_eos(session, o.id)}
    for it in items:
        it["already"] = it["asupp"] in present
    return items


async def add_from_bdo(session, o: PlanObject, asupp_ids: list[str], user: CurrentUser) -> int:
    items = {i["asupp"]: i for i in await registry.bdo_client().equipment_by_object(o.cipher, o.tm_code)}
    tm = await _tm_for(session, o)
    n, conflicts = 0, 0
    for a in asupp_ids:
        it = items.get(a)
        if not it:
            continue
        eo = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.code == a))).scalars().first()
        if not eo:
            eo = EquipmentUnit(code=a, name=f"{it['type']} {it['mark']}", tm_id=tm.id, deo=o.deo or tm.deo, eq_class="ТПА", origin="asupp")
            session.add(eo)
        eo.eq_type, eo.model, eo.tech_number, eo.factory_number = it["type"], it["mark"], it["techNum"], it["serialNum"]
        eo.year, eo.manufacturer, eo.dn, eo.pn, eo.s_calc, eo.steel_grade = it["year"], it["manufacturer"], it["dn"], it["pn"], it["sCalc"], it["steelGrade"]
        eo.sync_status, eo.sync_note = it.get("sync", "synced"), it.get("conflict", "")
        eo.passport = [["Тип оборудования", it["type"]], ["Марка / обозначение", it["mark"]], ["Технологический №", it["techNum"]], ["Заводской №", it["serialNum"]],
                       ["Год изготовления", it["year"]], ["DN, мм", it["dn"]], ["PN, МПа", it["pn"]], ["s расчётная, мм", it["sCalc"] or "—"], ["Марка стали", it["steelGrade"]]]
        await session.flush()
        if not (await session.execute(select(PlanObjectEo).where(PlanObjectEo.object_id == o.id, PlanObjectEo.eo_id == eo.id))).scalars().first():
            session.add(PlanObjectEo(object_id=o.id, eo_id=eo.id))
            n += 1
            conflicts += it.get("sync") == "conflict"
    session.add(IntegrationLog(direction="in", flow=f"ЕО объекта {o.cipher}", system=registry.bdo_client().name, count=f"{n} ЕО",
                               status="С предупреждениями" if conflicts else "Успешно", username=user.display))
    return n


def validate_eo(f: dict, others: list[EquipmentUnit]) -> dict:
    e = {k: "Обязательное поле" for k in ("type", "mark", "techNum", "serialNum", "dn", "pn", "sCalc", "steelGrade") if not str(f.get(k) or "").strip()}
    if f.get("techNum") and any(o.tech_number == str(f["techNum"]).strip() for o in others):
        e["techNum"] = "Технологический № уже есть на объекте"
    y = str(f.get("year") or "")
    if y and y != "Н/Д" and not (y.isdigit() and 1950 <= int(y) <= 2100):
        e["year"] = "Год 1950–2100 или «Н/Д»"
    if f.get("dn") and not str(f["dn"]).isdigit():
        e["dn"] = "Целое число > 0"
    try:
        if f.get("pn") and float(str(f["pn"]).replace(",", ".")) <= 0:
            e["pn"] = "Число > 0"
    except ValueError:
        e["pn"] = "Число > 0"
    if f.get("sCalc") and not re.fullmatch(r"\d+([.,]\d)?", str(f["sCalc"])):
        e["sCalc"] = "Число > 0 с точностью 0,1 мм"
    return e


async def create_eo(session, o: PlanObject, f: dict, user: CurrentUser, copied_from: str = "") -> EquipmentUnit:
    """V-EQ-033: ЕО, созданная в поле, получает origin=field_created, sync=pending до добавления в БДО (задача ПС-0)."""
    others = [e for e, _ in await object_eos(session, o.id)]
    errs = validate_eo(f, others)
    if errs:
        raise RuleError(f"Исправьте поля, отмеченные красным ({len(errs)})", "V-EQ-033", fields=errs)
    tm = await _tm_for(session, o)
    n = (await session.execute(select(func.count()).select_from(EquipmentUnit).where(EquipmentUnit.origin == "field_created"))).scalar_one()
    eo = EquipmentUnit(code=f"EO-F{date.today():%y}{n + 1:04d}", name=f"{f['type']} {f['mark']}", tm_id=tm.id, deo=o.deo or tm.deo, eq_class="ТПА",
                       eq_type=f["type"], model=f["mark"], tech_number=f["techNum"].strip(), factory_number=f["serialNum"].strip(), year=f.get("year", ""),
                       manufacturer=f.get("manufacturer", ""), dn=str(f["dn"]), pn=str(f["pn"]), s_calc=str(f["sCalc"]).replace(",", "."), steel_grade=f["steelGrade"],
                       origin="field_created", sync_status="pending",
                       attrs=[["MAT_COVER", "Крышка / пробка", f.get("matCover", ""), "—"], ["MAT_SPINDLE", "Шпиндель / шток", f.get("matSpindle", ""), "—"],
                              ["MAT_SEAL", "Уплотнения", f.get("matSeal", ""), "—"]],
                       passport=[["Тип оборудования", f["type"]], ["Марка / обозначение", f["mark"]], ["Технологический №", f["techNum"]], ["Заводской №", f["serialNum"]],
                                 ["DN, мм", str(f["dn"])], ["PN, МПа", str(f["pn"])], ["s расчётная, мм", str(f["sCalc"])], ["Марка стали", f["steelGrade"]]])
    session.add(eo)
    await session.flush()
    session.add(PlanObjectEo(object_id=o.id, eo_id=eo.id, copied_from=copied_from))
    await audit(session, user, "eo.create_field", "equipment_unit", eo.id, copied_from=copied_from)
    return eo


async def ps0_tasks(session, o: PlanObject, user: CurrentUser) -> int:
    n = 0
    for e, link in await object_eos(session, o.id):
        if e.sync_status == "pending" and not link.ps0_task:
            res = await registry.ps0_client().create_task({"eo": e.code, "type": e.eq_type, "mark": e.model, "object": o.cipher, "tm": o.tm_code})
            link.ps0_task = res["task_no"]
            n += 1
    if n:
        session.add(IntegrationLog(direction="out", flow="Задачи на добавление ЕО/ТМ в БДО", system=registry.ps0_client().name, count=f"{n} задач", username=user.display))
    return n
