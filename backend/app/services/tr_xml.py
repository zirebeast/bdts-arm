"""Проверка XML технического отчёта: XSD v3.8 (D-TO-06) и валидаторы модели v3.8; разбор содержимого для карточки ТО.

Действие по уровню (OQ-07): L1 → Block, L2 → Warn, L3/L5 → Info, V-P-010 → Auto-fix, D-TO-04 → Escalate.
"""
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

NS = "urn:gazprom-diagnostics:technical-report:3.8"
N = {"tr": NS}
XSD_PATH = Path(__file__).resolve().parent.parent / "xsd" / "technical_report_v3_8.xsd"
ACTION = {"L1": "Block", "L2": "Warn", "L3": "Info", "L5": "Info", "AF": "Auto-fix", "ESC": "Escalate"}
MAX_XML_BYTES = 30 * 1024 * 1024


@lru_cache
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(XSD_PATH)))


def _t(el, path: str, default: str = "") -> str:
    if el is None:
        return default
    x = el.find(path, N)
    return (x.text or "").strip() if x is not None and x.text else default


def _issue(rule: str, level: str, text: str, tab: str, field: str = "") -> dict:
    return {"id": rule, "level": level, "action": ACTION[level], "text": text, "tab": tab, "field": field}


def parse_xml(data: bytes):
    if len(data) > MAX_XML_BYTES:
        raise ValueError("Файл больше 30 МБ")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    return etree.fromstring(data, parser)


def validate_xsd(root) -> list[dict]:
    if root.tag != f"{{{NS}}}technical_report":
        return [_issue("D-TO-06", "L1", "Корневой элемент не technical_report пространства имён urn:gazprom-diagnostics:technical-report:3.8. Выгрузите отчёт по схеме v3.8.", "Проверка")]
    sc = schema()
    if sc.validate(root):
        return []
    out = []
    for e in list(sc.error_log)[:20]:
        msg = re.sub(r"\{urn:gazprom-diagnostics:technical-report:3\.8\}", "", e.message)
        out.append(_issue("D-TO-06", "L1", f"XML не проходит проверку по XSD v3.8 (строка {e.line}): {msg}", "Проверка"))
    return out


def extract(root) -> dict:
    """Разбор отчёта: шапка, ЕО, протоколы, статусы методов, ведомости, фото, заключение, подписи."""
    rep = root.find("tr:report", N)
    eq = []
    for e in root.findall("tr:equipment/tr:equipment_item", N):
        eq.append({
            "uid": _t(e, "tr:eo_uid"), "asupp": _t(e, "tr:asupp_eo_id"), "origin": _t(e, "tr:origin", "imported"),
            "sync": _t(e, "tr:sync_status"), "name": _t(e, "tr:name"), "type": _t(e, "tr:equipment_type"), "mark": _t(e, "tr:type_mark"),
            "mark_ref": _t(e, "tr:mark_ref"), "factory": _t(e, "tr:factory_number"), "steel": _t(e, "tr:steel_grade_ref"),
            "s_nom": _t(e, "tr:s_nominal_mm"), "s_calc": _t(e, "tr:s_calc_min_mm"), "basis": _t(e, "tr:thickness_basis"),
            "s_calc_source": _t(e, "tr:s_calc_min_source"), "s_calc_just": _t(e, "tr:s_calc_min_justification"),
            "climate": _t(e, "tr:climate_execution"), "climate_ref": _t(e, "tr:climate_execution_ref"),
        })
    types = {}
    for g in root.findall("tr:dictionary_snapshots/tr:equipment_types/*", N):
        types[_t(g, "tr:code")] = {"name": _t(g, "tr:name"), "group": g.tag.endswith("equipment_type_group")}
    steels = {}
    for s in root.findall("tr:dictionary_snapshots/tr:steel_grades/tr:steel_grade", N):
        steels[_t(s, "tr:code")] = {"name": _t(s, "tr:name"), "conflict": _t(s, "tr:conflict_state", "none"), "hb": [_t(s, "tr:hb_min"), _t(s, "tr:hb_max")]}
    methods = {_t(m, "tr:code"): _t(m, "tr:name") for m in root.findall("tr:dictionary_snapshots/tr:control_methods/tr:control_method", N)}
    marks = {_t(m, "tr:code"): _t(m, "tr:name") for m in root.findall("tr:dictionary_snapshots/tr:equipment_marks/tr:equipment_mark", N)}
    schemes = {}
    for s in root.findall("tr:equipment_control_schemes/tr:equipment_control_scheme", N):
        schemes[(_t(s, "tr:eo_uid"), _t(s, "tr:control_method_ref"))] = [x.text for x in s.findall("tr:point_labels/tr:point_label", N)]
    ms = [{"method": _t(m, "tr:method_ref"), "eo": _t(m, "tr:eo_uid"), "status": _t(m, "tr:status"), "reason": _t(m, "tr:reason"),
           "reason_text": _t(m, "tr:reason_text"), "comment": _t(m, "tr:comment")} for m in root.findall("tr:method_statuses/tr:method_status", N)]
    protocols = []
    for p in root.findall("tr:protocols/tr:protocol", N):
        md = p.find("tr:metadata", N)
        data = p.find("tr:data", N)
        kind = etree.QName(data[0]).localname if data is not None and len(data) else ""
        rows = []
        for item in (data[0] if kind else []):
            if not isinstance(item.tag, str):
                continue
            eo_ref = _t(item, "tr:eo_ref")
            meas = []
            for m in item.findall("tr:measurements/tr:measurement", N):
                meas.append({"label": _t(m, "tr:point_label") or _t(m, "tr:zone_number"), "value": _t(m, "tr:s_measured_mm") or _t(m, "tr:avg_hb_value") or _t(m, "tr:value_percent"),
                             "extra": _t(m, "tr:is_extra_point") == "true", "zone": _t(m, "tr:zone_number"), "norm": _t(m, "tr:norm_ref"),
                             "override": bool(m.find("tr:hb_min_override", N) is not None), "agg": _t(m, "tr:aggregation_applied"),
                             "raw": len(m.findall("tr:raw_hb_values/tr:raw_hb_value", N))})
            defects = [_t(d, "tr:description") for d in item.findall("tr:defects/tr:defect", N)]
            rows.append({"eo": eo_ref, "measurements": meas, "defects": defects, "comment": _t(item, "tr:comment"), "assessment": _t(item, "tr:assessment_result")})
        protocols.append({"number": _t(md, "tr:protocol_number"), "order": int(_t(md, "tr:order", "0") or 0), "date": _t(md, "tr:protocol_date"),
                          "method": _t(p, "tr:control_method_ref"), "kind": kind, "rows": rows})
    statements = []
    for d in root.findall("tr:defects_statements/tr:defects_statement", N):
        statements.append({
            "status": _t(d, "tr:statement_status", "draft"), "number": _t(d, "tr:statement_number"), "date": _t(d, "tr:statement_date"),
            "repair_code": _t(d, "tr:repair_object_code"), "work_type": _t(d, "tr:dtoir_work_type_ref"), "survey_year": _t(d, "tr:survey_year"),
            "items": [{"no": _t(i, "tr:item_no"), "category": _t(i, "tr:noncompliance_category"), "object": _t(i, "tr:object_name"),
                       "eo": _t(i, "tr:eo_uid"), "text": _t(i, "tr:defect_description"), "adm": _t(i, "tr:admissibility"),
                       "measures": _t(i, "tr:measures"), "clock": _t(i, "tr:clock_position"), "kind": _t(i, "tr:identifier_kind"),
                       "ident": _t(i, "tr:object_identifier"), "km_from": _t(i, "tr:km_from"), "km_to": _t(i, "tr:km_to")}
                      for i in d.findall("tr:items/tr:item", N)],
        })
    bstatements = []
    for b in root.findall("tr:building_defects_statements/tr:building_defects_statement", N):
        bstatements.append({"number": _t(b, "tr:number"), "overall": _t(b, "tr:overall_state_ref"),
                            "items": [{"no": _t(i, "tr:item_no"), "construction": _t(i, "tr:construction"), "state": _t(i, "tr:construction_state_ref"),
                                       "no_defects": _t(i, "tr:no_defects") == "true", "text": _t(i, "tr:defect_description")} for i in b.findall("tr:items/tr:item", N)]})
    photos = [{"id": _t(p, "tr:photo_id"), "kind": _t(p, "tr:photo_kind"), "eo": _t(p, "tr:eo_uid"), "uri": _t(p, "tr:file_uri"),
               "sha": _t(p, "tr:sha256"), "caption": _t(p, "tr:caption")} for p in root.findall("tr:photos/tr:photo", N)]
    conclusions = [{"method": _t(c, "tr:method_ref"), "state": _t(c, "tr:technical_state_ref"), "text": _t(c, "tr:text")} for c in root.findall("tr:conclusions/tr:conclusion", N)]
    signatures = [{"role": _t(s, "tr:role"), "name": _t(s, "tr:full_name"), "date": _t(s, "tr:signed_at")} for s in root.findall("tr:signatures/tr:signature", N)]
    dv = [f"{_t(x, 'tr:dictionary_code')} {_t(x, 'tr:version')}" for x in rep.findall("tr:dictionary_versions/tr:dictionary_version", N)] if rep is not None else []
    return {
        "report": {"number": _t(rep, "tr:report_number"), "date": _t(rep, "tr:report_date"), "title": _t(rep, "tr:report_title"),
                   "profile": _t(rep, "tr:profile"), "numbering": _t(rep, "tr:protocol_numbering_mode", "auto_mask"), "year": _t(rep, "tr:survey_year"),
                   "opo": {"name": _t(rep, "tr:opo/tr:name"), "reg": _t(rep, "tr:opo/tr:registration_number"), "hazard": _t(rep, "tr:opo/tr:opo_hazard_class")},
                   "customer": _t(rep, "tr:customer/tr:name"), "executor": _t(rep, "tr:executor/tr:name"),
                   "ntd": [x.text for x in rep.findall("tr:applied_ntd/tr:ntd_ref", N)] if rep is not None else [], "dict_versions": dv},
        "equipment": eq, "types": types, "steels": steels, "methods": methods, "marks": marks, "method_statuses": ms,
        "schemes": {f"{k[0]}|{k[1]}": v for k, v in schemes.items()}, "protocols": protocols, "statements": statements,
        "building": bstatements, "photos": photos, "conclusions": conclusions, "signatures": signatures,
    }


def rules(p: dict, dict_groups: set[str] | None = None, candidates: set[str] | None = None, known_eo: set[str] | None = None) -> list[dict]:
    """Валидаторы модели v3.8 (DataModel_v3_8_updates) по разобранному отчёту."""
    out: list[dict] = []
    names = {e["uid"]: e["name"] for e in p["equipment"]}
    eo_uids = set(names)
    for e in p["equipment"]:
        if not e["s_nom"] and not e["s_calc"]:
            out.append(_issue("V-EQ-029", "L1", f"ЕО «{e['name']}»: не задана толщина стенки. Укажите номинальную или расчётную минимальную толщину.", "ЕО (Сопоставление)", e["uid"]))
        t = p["types"].get(e["type"], {})
        if t.get("group") or (dict_groups and e["type"] in dict_groups):
            out.append(_issue("V-EQ-032", "L1", f"ЕО «{e['name']}»: тип оборудования «{t.get('name', e['type'])}» является группой. Выберите листовой тип.", "ЕО (Сопоставление)", e["uid"]))
        if e["mark_ref"] and e["mark"] and p["marks"].get(e["mark_ref"]) and p["marks"][e["mark_ref"]] != e["mark"]:
            out.append(_issue("V-EQ-027", "L2", f"Марка из справочника ({p['marks'][e['mark_ref']]}) не совпадает с маркой в тексте ({e['mark']}). Проверьте значение.", "Паспорт", e["uid"]))
        if e["climate"] and e["climate_ref"] and e["climate"] != e["climate_ref"]:
            out.append(_issue("V-EQ-028", "L2", f"ЕО «{e['name']}»: климатическое исполнение в тексте и по справочнику не совпадают.", "Паспорт", e["uid"]))
        if e["basis"] == "calc_min" and (not e["s_calc"] or not e["s_calc_source"]):
            out.append(_issue("V-EQ-030", "L2", f"ЕО «{e['name']}»: эталон по расчётной толщине, но не задана s расч. или её источник.", "ЕО (Сопоставление)", e["uid"]))
        if e["s_calc_source"] == "manual_justified" and not e["s_calc_just"]:
            out.append(_issue("V-EQ-030", "L2", f"ЕО «{e['name']}»: для ручной расчётной толщины требуется обоснование.", "ЕО (Сопоставление)", e["uid"]))
        if e["origin"] == "field_created" and not e["asupp"] and e["sync"] != "pending":
            out.append(_issue("V-EQ-033", "L2", f"ЕО «{e['name']}» создана в поле без ID АСУ ПП: статус синхронизации должен быть pending.", "ЕО (Сопоставление)", e["uid"]))
        st = p["steels"].get(e["steel"])
        if st and st["conflict"] == "open":
            out.append(_issue("V-DIC-045", "L5", f"Марка стали {st['name']}: открыт конфликт нормативных значений твёрдости (conflict_state = open).", "ЕО (Сопоставление)", e["uid"]))
        if candidates and e["steel"] in candidates:
            out.append(_issue("V-DIC-052", "L5", f"Марка стали {e['steel']} не подтверждена (candidate) и не попадёт в выгрузку.", "Паспорт", e["uid"]))
    # Протоколы и методы
    not_perf = {(m["method"], m["eo"]) for m in p["method_statuses"] if m["status"] == "not_performed"}
    for m in p["method_statuses"]:
        if m["status"] == "not_performed" and not m["reason"]:
            out.append(_issue("V-MS-002", "L2", f"Метод «{p['methods'].get(m['method'], m['method'])}» не проводился, но причина не указана.", "Протоколы"))
        if m["reason"] == "other" and not m["reason_text"]:
            out.append(_issue("V-MS-002", "L2", "Причина «иное» требует текстового пояснения.", "Протоколы"))
    for pr in p["protocols"]:
        if (pr["method"], "") in not_perf:
            out.append(_issue("V-MS-001", "L2", f"Метод «{p['methods'].get(pr['method'], pr['method'])}» отмечен как не проводившийся, но протокол {pr['number']} сформирован.", "Протоколы"))
        if p["report"]["numbering"] == "auto_mask":
            expected = f"{p['report']['number']}-{pr['order']:02d}"
            if pr["number"] != expected:
                out.append(_issue("V-P-010", "AF", f"Номер протокола исправлен по маске: {expected}.", "Протоколы"))
                pr["number_fixed"] = expected
        for row in pr["rows"]:
            for m in row["measurements"]:
                if pr["kind"] in ("uzt_data", "hardness_data") and not m["label"] and not m["zone"]:
                    out.append(_issue("V-UZT-009" if pr["kind"] == "uzt_data" else "V-HRD-011", "L2", "Точка замера без номера зоны и метки.", "Протоколы"))
                if pr["kind"] == "uzt_data" and m["label"]:
                    labels = p["schemes"].get(f"{row['eo']}|uzt")
                    if labels and m["label"] not in labels and not m["extra"]:
                        out.append(_issue("V-UZT-010", "L2", f"Протокол УЗТ ({names.get(row['eo'], '')}): метка точки «{m['label']}» отсутствует в схеме контроля ЕО и не отмечена как дополнительная.", "Протоколы"))
                if pr["kind"] == "hardness_data" and m["agg"] and not m["raw"]:
                    out.append(_issue("V-HRD-013", "L2", "Указана агрегация твёрдости без исходных замеров.", "Протоколы"))
    # Ведомости
    for s in p["statements"]:
        if s["status"] == "issued" and (not s["number"] or not s["date"]):
            out.append(_issue("V-DS-004", "L2", "Ведомость дефектов выпущена без номера или даты.", "Ведомости"))
        if s["repair_code"] and not re.fullmatch(r"\d+/\d+/\d+", s["repair_code"]):
            out.append(_issue("V-DS-008", "L2", f"Код объекта ремонта «{s['repair_code']}» не в формате X/Y/Z.", "Ведомости"))
        nums = sorted(int(i["no"]) for i in s["items"] if i["no"].isdigit())
        if nums and nums != list(range(1, len(nums) + 1)):
            out.append(_issue("V-DS-009", "L2", "Ведомость дефектов: нарушена сплошная нумерация строк 1..N.", "Ведомости"))
        for i in s["items"]:
            if i["eo"] and i["eo"] not in eo_uids:
                out.append(_issue("V-DS-010", "L2", f"Строка {i['no']} ведомости ссылается на ЕО, которой нет в отчёте.", "Ведомости"))
            if i["clock"] and not re.fullmatch(r"(1[0-2]|[1-9])|([01]?[0-9]|2[0-3]):[0-5][0-9]", i["clock"]):
                out.append(_issue("V-DS-011", "L2", f"Строка {i['no']}: часовая позиция «{i['clock']}» не в формате 1–12 или ЧЧ:ММ.", "Ведомости"))
            if i["kind"] == "range_km" and i["km_from"] and i["km_to"] and float(i["km_from"]) > float(i["km_to"]):
                out.append(_issue("V-DS-007", "L2", f"Строка {i['no']}: км начала больше км конца.", "Ведомости"))
        if s["survey_year"] and s["date"] and int(s["survey_year"]) > int(s["date"][:4]):
            out.append(_issue("V-DS-012", "L2", "Год обследования позже даты ведомости.", "Ведомости"))
    order = ["normative", "serviceable", "limited_serviceable", "emergency"]
    for b in p["building"]:
        worst = max((order.index(i["state"]) for i in b["items"] if i["state"] in order), default=0)
        if b["overall"] in order and order.index(b["overall"]) < worst:
            out.append(_issue("V-BDS-003", "L2", "Общее состояние ЗиС лучше худшей строки ведомости.", "Ведомости"))
    # Фото
    for ph in p["photos"]:
        if not ph["uri"]:
            out.append(_issue("V-PH-002", "L1", f"Фото «{ph['caption']}» без файла: file_uri пуст. Приложите файл фотографии.", "Фото"))
        if ph["kind"] == "eo" and not ph["eo"]:
            out.append(_issue("V-PH-001", "L2", f"Фото «{ph['caption']}» вида «ЕО» без привязки к ЕО.", "Фото"))
        if ph["eo"] and ph["eo"] not in eo_uids:
            out.append(_issue("V-PH-003", "L2", f"Фото «{ph['caption']}» привязано к ЕО, которой нет в отчёте.", "Фото"))
    if known_eo is not None:
        unknown = [e for e in p["equipment"] if not e["asupp"] or e["asupp"] not in known_eo]
        if unknown:
            out.append(_issue("D-TO-04", "ESC", f"{len(unknown)} единиц(ы) оборудования не найдены в БДО. Сопоставьте их или отметьте как объект ремонта.", "ЕО (Сопоставление)"))
    return out


def summarize(issues: list[dict]) -> dict:
    by = {"Block": 0, "Warn": 0, "Info": 0, "Auto-fix": 0, "Escalate": 0}
    for i in issues:
        by[i["action"]] += 1
    return by
