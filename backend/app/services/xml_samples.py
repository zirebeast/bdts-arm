"""Генератор XML технического отчёта по XSD v3.8 (демо-данные, образцы для проверки загрузки, ТО хозспособа)."""
import hashlib
import uuid
from datetime import date

from lxml import etree

NS = "urn:gazprom-diagnostics:technical-report:3.8"


def _uid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _el(parent, tag: str, text=None, **attrs):
    e = etree.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _opt(parent, tag, value):
    if value not in (None, ""):
        _el(parent, tag, value)


def _prov(parent, status="confirmed", system="legacy_mvp"):
    _el(parent, "source_system", system)
    _el(parent, "verification_status", status)


EQ_TYPES = {
    "ball_valve": "Кран шаровой", "gate_valve": "Задвижка клиновая", "safety_valve": "Клапан предохранительный",
    "check_valve": "Клапан обратный", "regulator_valve": "Клапан регулирующий", "valve": "Вентиль", "separator": "Сепаратор",
    "tee": "Тройник", "flange": "Фланец", "other": "Другое",
}
VALVE_TYPES = {"ball_valve", "gate_valve", "safety_valve", "check_valve", "regulator_valve", "valve"}
STEELS = {"steel_09g2s": ("09Г2С", "ГОСТ 19281-89", 130, 160, "open"), "steel_20l": ("20Л", "ГОСТ 977-88", 120, 160, "none"),
          "steel_20": ("20", "ГОСТ 1050-2013", 120, 160, "none")}
METHODS = {"vik": "Визуальный и измерительный контроль", "uzt": "Ультразвуковая толщинометрия", "hardness": "Измерение твёрдости",
           "pvk": "Капиллярный контроль", "uzk_weld": "УЗК сварных соединений", "functional": "Функциональная диагностика"}
NTD = {"gost_r_56542": ("gost", "ГОСТ Р 56542-2015 Контроль неразрушающий. Классификация видов и методов"),
       "sto_2_2_3_1030": ("sto_gazprom", "СТО Газпром 2-2.3-1030-2016 Техническое диагностирование ТПА")}
WORK_TYPES = {"dtoir_04": "Текущий ремонт", "dtoir_05": "Капитальный ремонт"}


def build_report_xml(spec: dict) -> bytes:
    """spec: number, date, title, profile, numbering, opo{}, customer, executor, equipment[], schemes[], method_statuses[],
    uzt{eo:[(label, value, extra)]}, hardness{eo:[(label, hb)]}, vik{eo:[defects]}, defects[], photos[], conclusion, state."""
    root = etree.Element(f"{{{NS}}}technical_report", nsmap={None: NS}, schema_version="3.8", generated_at=f"{spec['date']}T10:00:00")
    eq = spec["equipment"]
    used_types = sorted({e["type"] for e in eq})
    used_steels = sorted({e["steel"] for e in eq if e.get("steel")})
    used_methods = sorted({"vik", "uzt", "hardness", "pvk"} | {m["method"] for m in spec.get("method_statuses", [])})
    ver = spec.get("dict_version", "3.8.14")

    rep = _el(root, "report")
    _el(rep, "report_id", _uid("report:" + spec["number"]))
    _el(rep, "report_number", spec["number"])
    _el(rep, "report_date", spec["date"])
    _opt(rep, "report_title", spec.get("title"))
    _el(rep, "profile", spec["profile"])
    _el(rep, "protocol_numbering_mode", spec.get("numbering", "auto_mask"))
    _el(rep, "survey_year", spec["date"][:4])
    opo = _el(rep, "opo")
    _el(opo, "name", spec["opo"]["name"])
    _opt(opo, "registration_number", spec["opo"].get("reg"))
    _opt(opo, "opo_hazard_class", spec["opo"].get("hazard"))
    for tag in ("customer", "executor"):
        o = _el(rep, tag)
        _el(o, "name", spec[tag])
    dv = _el(rep, "dictionary_versions")
    for code in ("Steel_Grades", "Equipment_Types", "Control_Methods", "НТД", "DTOIR_Work_Types"):
        x = _el(dv, "dictionary_version")
        _el(x, "dictionary_code", code)
        _el(x, "version", ver)
    an = _el(rep, "applied_ntd")
    for code in NTD:
        _el(an, "ntd_ref", code)

    snap = _el(root, "dictionary_snapshots")
    sg = _el(snap, "steel_grades", dictionary_code="Steel_Grades", version=ver)
    for code in used_steels:
        name, std, lo, hi, conflict = STEELS[code]
        s = _el(sg, "steel_grade")
        _el(s, "code", code)
        _el(s, "name", name)
        _el(s, "standard", std)
        _el(s, "material_kind", "steel")
        _el(s, "has_norm_data", "true")
        _el(s, "hb_min", lo)
        _el(s, "hb_max", hi)
        _el(s, "sigma_allowable_mpa", "167.4")
        _el(s, "conflict_state", conflict)
        _prov(s)
    et = _el(snap, "equipment_types", dictionary_code="Equipment_Types", version=ver)
    if any(t in VALVE_TYPES for t in used_types):
        for code, name, parent in (("asupp_000000001", "Технические устройства", None), ("asupp_000000003", "Трубопроводная арматура", "asupp_000000001")):
            g = _el(et, "equipment_type_group")
            _el(g, "code", code)
            _el(g, "name", name)
            _opt(g, "parent_code", parent)
            _el(g, "is_group", "true")
            _el(g, "category", "valve_armature" if parent else "other")
            _el(g, "source_code", code[-9:])
            _el(g, "source_system", "asupp")
            _el(g, "verification_status", "candidate")
    for code in used_types:
        lf = _el(et, "equipment_type")
        _el(lf, "code", code)
        _el(lf, "name", EQ_TYPES[code])
        if code in VALVE_TYPES:
            _el(lf, "parent_code", "asupp_000000003")
        _el(lf, "is_group", "false")
        _el(lf, "has_drive", "false")
        _el(lf, "category", "valve_armature" if code in VALVE_TYPES else ("vessel" if code == "separator" else "pipeline_element" if code in ("tee", "flange") else "other"))
        _prov(lf)
    wt = _el(snap, "dtoir_work_types", dictionary_code="DTOIR_Work_Types", version=ver)
    for code, name in WORK_TYPES.items():
        w = _el(wt, "dtoir_work_type")
        _el(w, "code", code)
        _el(w, "name", name)
        _prov(w)
    nd = _el(snap, "ntd_documents", dictionary_code="НТД", version=ver)
    for code, (dt, fn) in NTD.items():
        n = _el(nd, "ntd")
        _el(n, "code", code)
        _el(n, "doc_type", dt)
        _el(n, "full_name", fn)
        _prov(n)
    cm = _el(snap, "control_methods", dictionary_code="Control_Methods", version=ver)
    for code in used_methods:
        c = _el(cm, "control_method")
        _el(c, "code", code)
        _el(c, "name", METHODS[code])
        _prov(c)

    sp_uid = _uid("spec:" + spec["number"])
    sps = _el(root, "specialists")
    sp = _el(sps, "specialist")
    _el(sp, "specialist_id", sp_uid)
    _el(sp, "full_name", spec.get("specialist", "ФИО_4"))
    _el(sp, "position", "Ведущий инженер НК")
    ins_uid = _uid("instr:" + spec["number"])
    ins = _el(_el(root, "instruments"), "instrument")
    _el(ins, "instrument_id", ins_uid)
    _el(ins, "name", "Толщиномер ультразвуковой А1207")
    _el(ins, "serial_number", "SN-449102")
    _el(ins, "verification_valid_until", "2027-03-01")

    eqs = _el(root, "equipment")
    for e in eq:
        x = _el(eqs, "equipment_item")
        _el(x, "eo_uid", _uid("eo:" + spec["number"] + e["name"]))
        _opt(x, "asupp_eo_id", e.get("asupp"))
        _el(x, "origin", e.get("origin", "asupp"))
        _el(x, "sync_status", e.get("sync", "synced"))
        _el(x, "name", e["name"])
        _el(x, "equipment_type", e["type"])
        _opt(x, "type_mark", e.get("mark"))
        _opt(x, "factory_number", e.get("factory"))
        _opt(x, "manufacture_year", e.get("year"))
        _opt(x, "location", e.get("location"))
        _opt(x, "dn_mm", e.get("dn"))
        _opt(x, "pn_mpa", e.get("pn"))
        _opt(x, "steel_grade_ref", e.get("steel"))
        _opt(x, "s_nominal_mm", e.get("s_nom"))
        _opt(x, "s_calc_min_mm", e.get("s_calc"))
        if e.get("s_calc"):
            _el(x, "s_calc_min_source", "calc_sto")
        _el(x, "thickness_basis", "nominal" if e.get("s_nom") else "calc_min")

    ecs = _el(root, "equipment_control_schemes")
    for e in eq:
        s = _el(ecs, "equipment_control_scheme")
        _el(s, "eo_uid", _uid("eo:" + spec["number"] + e["name"]))
        _el(s, "control_method_ref", "uzt")
        pl = _el(s, "point_labels")
        for lb in e.get("scheme", ["Т-1", "Т-2", "Т-3"]):
            _el(pl, "point_label", lb)

    mss = _el(root, "method_statuses")
    for m in spec.get("method_statuses", []) or [{"method": "vik", "status": "performed"}]:
        x = _el(mss, "method_status")
        _el(x, "method_ref", m["method"])
        _el(x, "status", m["status"])
        _opt(x, "reason", m.get("reason"))
        _opt(x, "comment", m.get("comment"))

    prs = _el(root, "protocols")
    order = 0

    def proto(method: str):
        nonlocal order
        order += 1
        p = _el(prs, "protocol")
        _el(p, "protocol_id", _uid(f"proto:{spec['number']}:{order}"))
        _el(p, "control_method_ref", method)
        md = _el(p, "metadata")
        num = spec.get("proto_numbers", {}).get(order) or f"{spec['number']}-{order:02d}"
        _el(md, "protocol_number", num)
        _el(md, "order", order)
        _el(md, "protocol_date", spec["date"])
        _el(_el(md, "instrument_refs"), "ref", ins_uid)
        _el(_el(md, "specialist_refs"), "ref", sp_uid)
        return _el(p, "data")

    d = _el(proto("vik"), "vik_data")
    for e in eq:
        v = _el(d, "equipment_vik_data")
        _el(v, "eo_ref", _uid("eo:" + spec["number"] + e["name"]))
        if e.get("vik_defect"):
            df = _el(_el(v, "defects"), "defect")
            _el(df, "description", e["vik_defect"])
        _el(v, "comment", e.get("vik_comment", "Недопустимых дефектов не выявлено"))
    d = _el(proto("uzt"), "uzt_data")
    for e in eq:
        u = _el(d, "equipment_uzt_data")
        _el(u, "eo_ref", _uid("eo:" + spec["number"] + e["name"]))
        ms = _el(u, "measurements")
        for lb, val, extra in e.get("uzt", [("Т-1", e.get("s_nom") or e.get("s_calc") or "8.0", False)]):
            mm = _el(ms, "measurement")
            _el(mm, "point_label", lb)
            _el(mm, "s_measured_mm", val)
            if extra:
                _el(mm, "is_extra_point", "true")
    d = _el(proto("hardness"), "hardness_data")
    for e in eq:
        if not e.get("hb"):
            continue
        h = _el(d, "equipment_hardness_data")
        _el(h, "eo_ref", _uid("eo:" + spec["number"] + e["name"]))
        ms = _el(h, "measurements")
        for lb, hb in e["hb"]:
            mm = _el(ms, "measurement")
            _el(mm, "point_label", lb)
            _el(mm, "avg_hb_value", hb)

    if spec.get("defects"):
        ds = _el(_el(root, "defects_statements"), "defects_statement")
        _el(ds, "statement_id", _uid("ds:" + spec["number"]))
        _el(ds, "statement_status", "issued")
        _el(ds, "statement_number", f"ВД-{spec['number'][-4:]}")
        _el(ds, "statement_date", spec["date"])
        _el(ds, "technical_report_number", spec["number"])
        _el(ds, "repair_object_code", spec.get("repair_code", "97488/2/142"))
        _el(ds, "dtoir_work_type_ref", "dtoir_04")
        items = _el(ds, "items")
        for k, it in enumerate(spec["defects"], start=1):
            i = _el(items, "item")
            _el(i, "item_no", it.get("no", k))
            _el(i, "noncompliance_category", it.get("category", "structure_defects"))
            _el(i, "object_name", it["eo"])
            _el(i, "eo_uid", _uid("eo:" + spec["number"] + it["eo"]))
            _el(i, "defect_description", it["text"])
            _el(i, "admissibility", it.get("adm", "fit"))
            _opt(i, "measures", it.get("measures"))
            _opt(i, "clock_position", it.get("clock"))

    phs = _el(root, "photos")
    for k, ph in enumerate(spec.get("photos", []), start=1):
        p = _el(phs, "photo")
        _el(p, "photo_id", _uid(f"photo:{spec['number']}:{k}"))
        _el(p, "photo_kind", "eo")
        _el(p, "eo_uid", _uid("eo:" + spec["number"] + ph["eo"]))
        _el(p, "file_uri", ph.get("uri", f"photos/{k:02d}.jpg"))
        _el(p, "sha256", hashlib.sha256(f"{spec['number']}{k}".encode()).hexdigest())
        _el(p, "mime", "image/jpeg")
        _el(p, "caption", ph["caption"])
        _el(p, "order", k)
    if not len(phs):
        root.remove(phs)

    cs = _el(_el(root, "conclusions"), "conclusion")
    _el(cs, "technical_state_ref", spec.get("state", "serviceable"))
    _el(cs, "text", spec.get("conclusion", "Техническое состояние работоспособное. Допускается к дальнейшей эксплуатации."))
    sg_ = _el(_el(root, "signatures"), "signature")
    _el(sg_, "role", "Руководитель работ")
    _el(sg_, "specialist_ref", sp_uid)
    _el(sg_, "full_name", spec.get("specialist", "ФИО_4"))
    _el(sg_, "signed_at", spec["date"])
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ТО ГРС от ГД (прототип: 7 ЕО, 2 ошибки L1, предупреждения L2, 2 ЕО без сопоставления)
GRS_SPEC = {
    "number": "АТД-2023-ГТСПБ-ПСК-ГРС-000013844", "date": "2026-10-15", "title": "Техническое диагностирование оборудования ГРС «Степановская»",
    "profile": "to_grs", "numbering": "auto_mask", "opo": {"name": "Площадка ГРС «Степановская»", "reg": "А45-01928-002", "hazard": "II"},
    "customer": "ОРГ_9", "executor": "ОРГ_1 (ГД)", "proto_numbers": {2: "2026-112-02"},
    "equipment": [
        {"name": "Подогреватель газа ПГ-3", "type": "other", "asupp": "EO-100294", "steel": "steel_09g2s", "s_nom": "8.00", "mark": "ПТПГ-30", "factory": "449102",
         "uzt": [("Т-1", "7.4", False), ("Т-2", "7.9", False), ("Т-14", "7.1", False)], "hb": [("Т-1", 152)], "scheme": ["Т-1", "Т-2", "Т-3"]},
        {"name": "Задвижка клиновая ЗКЛ2-50", "type": "gate_valve", "origin": "field_created", "sync": "synced", "steel": "steel_20l", "factory": "1107",
         "uzt": [("Т-1", "6.1", False)]},
        {"name": "Кран шаровый Ду300", "type": "ball_valve", "origin": "field_created", "sync": "pending", "steel": "steel_09g2s", "s_nom": "10.00",
         "uzt": [("Т-1", "10.4", False), ("Т-2", "10.2", False)]},
        {"name": "Клапан предохранительный ПК-1", "type": "safety_valve", "asupp": "EO-700112", "steel": "steel_20l", "s_nom": "6.00", "uzt": [("Т-1", "6.3", False)]},
        {"name": "Фильтр-сепаратор ФС-1", "type": "separator", "asupp": "EO-700113", "steel": "steel_09g2s", "s_nom": "12.00",
         "uzt": [("Т-1", "12.6", False), ("Т-2", "12.4", False)], "hb": [("Т-1", 148), ("Т-2", 151)]},
        {"name": "Регулятор давления РД-1", "type": "regulator_valve", "asupp": "EO-700114", "steel": "steel_20", "s_nom": "7.00", "uzt": [("Т-1", "7.3", False)]},
        {"name": "Тройник Ду300 входной", "type": "tee", "asupp": "EO-700115", "steel": "steel_09g2s", "s_nom": "9.00", "uzt": [("Т-1", "9.5", False)]},
    ],
    "method_statuses": [{"method": "vik", "status": "performed"}, {"method": "uzt", "status": "performed"}, {"method": "hardness", "status": "performed"},
                        {"method": "pvk", "status": "not_performed", "reason": "not_applicable", "comment": "Отсутствие открытых сварных швов"}],
    "defects": [{"no": 1, "eo": "Подогреватель газа ПГ-3", "text": "Локальное нарушение АКП корпуса, нижняя образующая", "adm": "fit", "measures": "Текущий ремонт", "clock": "06:00"},
                {"no": 3, "eo": "Кран шаровый Ду300", "text": "Негерметичность сальникового уплотнения", "adm": "not_fit", "measures": "Замена уплотнений", "clock": "12"}],
    "photos": [{"eo": "Подогреватель газа ПГ-3", "caption": "Общий вид подогревателя газа ПГ-3"}, {"eo": "Подогреватель газа ПГ-3", "caption": "Зона замера УЗТ №1"},
               {"eo": "Задвижка клиновая ЗКЛ2-50", "caption": "Шильдик заводского номера ЗКЛ2-50", "uri": ""}],
    "state": "serviceable", "conclusion": "Техническое состояние объекта: работоспособное. Срок безопасной эксплуатации продлён до 15.10.2029.",
}

# Исправленная версия: без ошибок L1
GRS_SPEC_FIXED = {**GRS_SPEC, "equipment": [
    {**GRS_SPEC["equipment"][0]},
    {**GRS_SPEC["equipment"][1], "s_nom": "6.50"},
    *GRS_SPEC["equipment"][2:],
], "photos": [p if p.get("uri") != "" else {**p, "uri": "photos/03.jpg"} for p in GRS_SPEC["photos"]]}


def sample(kind: str) -> tuple[str, bytes]:
    if kind == "fixed":
        return "report_grs_000013844_v3.xml", build_report_xml(GRS_SPEC_FIXED)
    if kind == "new":
        spec = {**GRS_SPEC_FIXED, "number": f"ТО-ГД-{date.today().year}-{uuid.uuid4().hex[:5].upper()}", "date": date.today().isoformat(),
                "title": "Техническое диагностирование ГРС (образец)", "proto_numbers": {}}
        return f"report_{spec['number']}.xml", build_report_xml(spec)
    return "report_grs_000013844_v2.xml", build_report_xml(GRS_SPEC)
