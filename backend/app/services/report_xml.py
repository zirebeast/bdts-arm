"""Технический отчёт по результатам ДО в XML (XSD v3.8), формируется «на лету» из тех же данных, что и .docx.

Разделы шаблона → протоколы: ВИК, УЗТ, твёрдость, МПК, УЗК — в специализированные блоки XSD, прочие методы
(ФД, спектральный анализ, ВД, ЭХЗ, расчёт и др.) — в generic_data. В снимок справочников попадают только
подтверждённые записи (V-DIC-052): тип ЕО без подтверждённой записи выгружается как «other», марка стали — без ссылки.
Перед выдачей XML проходит ту же проверку, что и загружаемые ТО (XSD + правила V-*); ошибки L1 блокируют выгрузку.
"""
import hashlib
import mimetypes
import uuid
from datetime import date

from lxml import etree
from sqlalchemy import select

from app.errors import RuleError
from app.models import Dict38Entry, Dict38Version, EquipmentUnit, FileObject
from app.seed.templates import VID_PROFILE, VID_SHORT
from app.services.report_docx import METHOD, STAGES_SIGN, _attr_v, _fio, _hist_at, _method_ntd, _specialist, _tm_attrs, collect, report_no
from app.services.sections import sec_tol_list, tol_field
from app.services.storage import read_file

NS = "urn:gazprom-diagnostics:technical-report:3.8"
STATE_CODE = {"Исправное": "normative", "Работоспособное": "serviceable", "Ограниченно работоспособное": "limited_serviceable", "Неработоспособное": "emergency"}
CERT_METHOD = {"ВИК": "vik", "УЗТ": "uzt", "УЗК": "uzk_weld", "Твёрдость": "hardness", "МПК": "mpk", "ПВК": "pvk"}
BLOCK = {"mpk": "mpk", "uzk_metal": "uzk_metal", "uzk_weld": "uzk_weld"}
NOT_PROTOCOL = {"doc", "ntd", "work_scope", "conclusion"}
# Вид работ ДТОиР для ведомости дефектов; ведомость выгружается, только если запись подтверждена на W-5.10
DTOIR_BY_VID = {"vessel": "dtoir_01"}
DTOIR_DEFAULT = "dtoir_11"
CATEGORY = {"functional": "functional_defects", "operability": "functional_defects", "acoustic": "functional_defects", "ecp": "ecp_defects"}


def uid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "bdts:" + seed))


def eo_uid(r, reo) -> str:
    """Стабильный идентификатор ЕО в ТО (по ЕО БДО или по позиции в результате ДО)."""
    return uid(f"eo:{reo.eo_id}" if reo.eo_id else f"result:{r.id}:eo:{reo.idx}")


def _el(parent, tag: str, text=None, **attrs):
    e = etree.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _opt(parent, tag, value):
    if value not in (None, "", "—"):
        _el(parent, tag, str(value)[:500])


def _dec(v) -> str | None:
    """Положительное десятичное число для XSD (запятая → точка) или None."""
    try:
        x = float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return f"{x:g}" if x > 0 else None


def _txt(v) -> str:
    return str(v).strip()[:500] if v not in (None, "") else ""


def _worst(tols: list[str]) -> str:
    rank = {"empty": 0, "ok": 1, "borderline": 2, "exceeded": 3}
    return max(tols, key=lambda x: rank.get(x, 0)) if tols else "empty"


def _ntd_code(name: str) -> str:
    return "ntd_" + hashlib.sha1(name.encode()).hexdigest()[:12]


def _doc_type(name: str) -> str:
    n = name.upper()
    for prefix, code in (("ГОСТ", "gost"), ("СТО", "sto_gazprom"), ("ФНП", "fnp"), ("РД", "rd"), ("СП ", "sp"), ("ФЕДЕРАЛЬНЫЙ ЗАКОН", "federal_law")):
        if n.startswith(prefix):
            return code
    return "other"


async def _dicts(session):
    rows = (await session.execute(select(Dict38Entry).where(Dict38Entry.dictionary.in_(["Equipment_Types", "Steel_Grades", "DTOIR_Work_Types"]),
                                                            Dict38Entry.verification_status == "confirmed"))).scalars().all()
    by = {}
    for e in rows:
        by.setdefault(e.dictionary, {})[e.code] = e
    vers = {v.dictionary: v.version for v in (await session.execute(select(Dict38Version).where(Dict38Version.is_current.is_(True)))).scalars()}
    return by, vers


def _eq_type(types: dict, eo: EquipmentUnit | None) -> str:
    name = (eo.eq_type if eo else "").strip().lower()
    leaf = next((c for c, e in types.items() if not (e.payload or {}).get("is_group") and e.name.strip().lower() == name), None)
    return leaf or "other"


def _steel(steels: dict, name: str) -> str | None:
    return next((c for c, e in steels.items() if e.name.strip().lower() == (name or "").strip().lower()), None) if name else None


async def build_result_xml(session, ctx) -> tuple[bytes, str]:
    t, r = ctx.task, ctx.r
    info = await collect(session, ctx)
    by, vers = await _dicts(session)
    types, steels, works = by.get("Equipment_Types", {}), by.get("Steel_Grades", {}), by.get("DTOIR_Work_Types", {})
    ver = vers.get("Equipment_Types", "3.8.14")
    number, rep_date = report_no(ctx)
    secs = [s for s in ctx.sections if s["kind"] != "info"]
    protos = [s for s in secs if s["code"] not in NOT_PROTOCOL and (s["stage"] == "ПЭ" or s["code"] in ("calc", "vdp"))]
    sec = {s["code"]: s for s in secs}
    eos = [(reo, info.eos.get(reo.eo_id), eo_uid(r, reo)) for reo in r.eos]
    root_eo = info.eos.get(t.eo_id) or (eos[0][1] if eos else None)

    # Справочные данные, которые реально используются в отчёте
    used_types = {_eq_type(types, eo) for _, eo, _ in eos}
    used_steels = {c for _, eo, _ in eos if (c := _steel(steels, eo.steel_grade if eo else ""))}
    methods = {s["code"]: METHOD.get(s["code"], (s["title"],))[0] for s in protos}
    ntd = {}  # code → full_name
    for row in ctx.data(0, sec["ntd"]).get("rows", []) if "ntd" in sec else []:
        name = " ".join(x for x in (_txt(row.get("doc")), _txt(row.get("name"))) if x)
        if name:
            ntd[_ntd_code(name)] = name
    applied = list(ntd)
    proto_ntd = {s["code"]: [n for n in _method_ntd(s["code"], t.vid) if n] for s in protos}
    for names in proto_ntd.values():
        for n in names:
            ntd.setdefault(_ntd_code(n[:500]), n[:500])
    work_code = DTOIR_BY_VID.get(t.vid, DTOIR_DEFAULT)
    work = works.get(work_code)

    root = etree.Element(f"{{{NS}}}technical_report", nsmap={None: NS}, schema_version="3.8", generated_at=date.today().isoformat() + "T00:00:00")
    # ---- report ----
    rep = _el(root, "report")
    _el(rep, "report_id", uid(f"result:{r.id}:report"))
    _el(rep, "report_number", number)
    _el(rep, "report_date", rep_date.isoformat())
    _opt(rep, "report_title", f"Технический отчёт по результатам ДО: {t.eo_name}")
    _el(rep, "profile", VID_PROFILE.get(t.vid, "to_" + t.vid))
    _el(rep, "protocol_numbering_mode", "auto_mask")
    _el(rep, "survey_year", rep_date.year)
    tm_attrs = _tm_attrs(info, root_eo)
    opo_name = _attr_v(tm_attrs, "OPO_NAME", "")
    if opo_name and opo_name != "—":
        opo = _el(rep, "opo")
        _el(opo, "name", opo_name[:500])
        _opt(opo, "registration_number", _attr_v(tm_attrs, "OPO_REG", ""))
        _opt(opo, "opo_hazard_class", _attr_v(tm_attrs, "CLASS", ""))
    for tag, org in (("customer", info.customer), ("executor", info.executor)):
        d = (org.details if org else {}) or {}
        o = _el(rep, tag)
        _el(o, "name", (d.get("full") or (org.name if org else t.deo))[:500])
        _opt(o, "inn", d.get("inn"))
        _opt(o, "address", d.get("address"))
    snapshots = [("Steel_Grades", bool(used_steels)), ("Equipment_Types", True), ("DTOIR_Work_Types", bool(work)), ("НТД", bool(ntd)), ("Control_Methods", bool(methods))]
    dv = _el(rep, "dictionary_versions")
    for code, on in snapshots:
        if on:
            x = _el(dv, "dictionary_version")
            _el(x, "dictionary_code", code)
            _el(x, "version", vers.get(code, ver))
    if applied:
        an = _el(rep, "applied_ntd")
        for c in applied:
            _el(an, "ntd_ref", c)

    # ---- снимок справочников ----
    snap = _el(root, "dictionary_snapshots")
    if used_steels:
        sg = _el(snap, "steel_grades", dictionary_code="Steel_Grades", version=vers.get("Steel_Grades", ver))
        for code in sorted(used_steels):
            p = steels[code].payload or {}
            s = _el(sg, "steel_grade")
            _el(s, "code", code)
            _el(s, "name", steels[code].name)
            _opt(s, "standard", p.get("standard"))
            _opt(s, "material_kind", p.get("material_kind"))
            if p.get("has_norm_data") is not None:
                _el(s, "has_norm_data", str(bool(p["has_norm_data"])).lower())
            for k in ("hb_min", "hb_max"):
                _opt(s, k, p.get(k))
            _opt(s, "sigma_allowable_mpa", _dec(p.get("sigma_allowable_mpa")))
            _opt(s, "conflict_state", p.get("conflict_state"))
            _el(s, "source_system", p.get("source_system") or steels[code].source_system or "legacy_mvp")
            _el(s, "verification_status", "confirmed")
    et = _el(snap, "equipment_types", dictionary_code="Equipment_Types", version=ver)
    for code in sorted(used_types):
        e = types.get(code)
        p = (e.payload if e else {}) or {}
        lf = _el(et, "equipment_type")
        _el(lf, "code", code)
        _el(lf, "name", e.name if e else "Другое")
        _el(lf, "is_group", "false")
        _el(lf, "category", p.get("category") or "other")
        _el(lf, "source_system", p.get("source_system") or (e.source_system if e else "") or "legacy_mvp")
        _el(lf, "verification_status", "confirmed")
    if work:
        wt = _el(snap, "dtoir_work_types", dictionary_code="DTOIR_Work_Types", version=vers.get("DTOIR_Work_Types", ver))
        w = _el(wt, "dtoir_work_type")
        _el(w, "code", work_code)
        _el(w, "name", work.name)
        _el(w, "source_system", (work.payload or {}).get("source_system") or work.source_system or "legacy_mvp")
        _el(w, "verification_status", "confirmed")
    if ntd:
        nd = _el(snap, "ntd_documents", dictionary_code="НТД", version=ver)
        for code, name in ntd.items():
            n = _el(nd, "ntd")
            _el(n, "code", code)
            _el(n, "doc_type", _doc_type(name))
            _el(n, "full_name", name)
            _el(n, "source_system", "manual")
            _el(n, "verification_status", "confirmed")
    if methods:
        cm = _el(snap, "control_methods", dictionary_code="Control_Methods", version=ver)
        for code, name in methods.items():
            c = _el(cm, "control_method")
            _el(c, "code", code)
            _el(c, "name", name[:500])
            _el(c, "source_system", "manual")
            _el(c, "verification_status", "confirmed")
    if not len(snap):
        root.remove(snap)

    # ---- специалисты и приборы ----
    sp_ids = {}
    if info.members:
        sps = _el(root, "specialists")
        for m in info.members:
            sid = uid(f"specialist:{m.get('cert') or m.get('fio')}")
            sp_ids[m.get("fio")] = sid
            sp = _el(sps, "specialist")
            _el(sp, "specialist_id", sid)
            _el(sp, "full_name", m.get("fio") or "—")
            certs = [CERT_METHOD[x] for x in m.get("methods", []) if x in CERT_METHOD]
            if certs:
                cs = _el(sp, "certifications")
                for mc in certs:
                    c = _el(cs, "certification")
                    _el(c, "method_ref", mc)
                    _opt(c, "level", m.get("level"))
                    _opt(c, "certificate_number", m.get("cert"))
                    _opt(c, "valid_until", m.get("validUntil"))
    ins_ids = {}
    ins_rows = []
    for s in protos:
        name = s.get("instrument")
        reg = info.instruments.get(name or "", {})
        serial = reg.get("serial") or ctx.data(0, s).get("serial")
        if name and serial and name not in ins_ids:
            ins_ids[name] = uid(f"instrument:{name}:{serial}")
            ins_rows.append((ins_ids[name], name, serial, reg.get("cert") or reg.get("verif")))
    if ins_rows:
        ins = _el(root, "instruments")
        for iid, name, serial, cert in ins_rows:
            x = _el(ins, "instrument")
            _el(x, "instrument_id", iid)
            _el(x, "name", name[:500])
            _el(x, "serial_number", str(serial)[:500])
            _opt(x, "verification_certificate", cert)

    # ---- рассмотренные документы и перечень работ ----
    if "doc" in sec:
        docs = [row for row in ctx.data(0, sec["doc"]).get("rows", []) if _txt(row.get("type"))]
        if docs:
            rd = _el(root, "reviewed_documents")
            for row in docs:
                x = _el(rd, "reviewed_document")
                _el(x, "title", _txt(row["type"]))
                _opt(x, "number", _txt(row.get("no")))
                _opt(x, "comment", _txt(row.get("st")))
    if "work_scope" in sec:
        cols = sec["work_scope"].get("cols", [])
        rows = [row for row in ctx.data(0, sec["work_scope"]).get("rows", []) if cols and _txt(row.get(cols[0]["key"]))]
        if rows:
            works_el = _el(_el(root, "work_scope"), "works")
            for row in rows:
                w = _el(works_el, "work")
                _el(w, "work_name", _txt(row[cols[0]["key"]]))
                rest = "; ".join(f"{c['label']}: {_txt(row.get(c['key']))}" for c in cols[1:] if _txt(row.get(c["key"])))
                if rest:
                    _el(w, "volume_kind", "text")
                    _el(w, "volume_text", rest[:500])

    # ---- ЕО ----
    eqs = _el(root, "equipment")
    for reo, eo, u in eos:
        x = _el(eqs, "equipment_item")
        _el(x, "eo_uid", u)
        if eo and eo.origin == "asupp":
            _el(x, "asupp_eo_id", eo.code)
        _el(x, "origin", eo.origin if eo and eo.origin in ("asupp", "field_created") else "field_created")
        _el(x, "sync_status", eo.sync_status if eo and eo.sync_status in ("synced", "pending", "conflict") else "pending")
        _el(x, "name", (eo.name if eo else reo.label)[:500])
        _el(x, "equipment_type", _eq_type(types, eo))
        if eo:
            _opt(x, "type_mark", eo.model)
            _opt(x, "factory_number", eo.factory_number)
            if eo.year and eo.year.isdigit() and len(eo.year) == 4:
                _el(x, "manufacture_year", eo.year)
        _opt(x, "location", t.location)
        if eo:
            _opt(x, "dn_mm", _dec(eo.dn))
            _opt(x, "pn_mpa", _dec(eo.pn))
            _opt(x, "steel_grade_ref", _steel(steels, eo.steel_grade))
        # Эталон толщины: s расч. ЕО; для ЕО без паспорта — минимально допустимая толщина первого элемента УЗТ по шаблону
        uzt = next((s for s in protos if s["kind"] == "points" and s.get("mode") == "thk"), None)
        s_calc = _dec(eo.s_calc) if eo else None
        s_calc = s_calc or (_dec(uzt["elements"][0].get("s")) if uzt and uzt.get("elements") else None)
        if s_calc:
            _el(x, "s_calc_min_mm", s_calc)
            _el(x, "s_calc_min_source", "calc_sto")
            _el(x, "thickness_basis", "calc_min")

    # ---- схемы контроля (метки точек УЗТ и твёрдости) ----
    labels = {}
    for s in protos:
        if s["kind"] != "points":
            continue
        for i, (_, _, u) in enumerate(eos):
            d = ctx.data(i, s)
            ls = list(dict.fromkeys(f"{el['name']}: {p['label']}" for el in d.get("elements", []) for p in el.get("points", []) if _dec(p.get("value"))))
            if ls and not d.get("np"):
                labels[(u, s["code"])] = ls
    if labels:
        ecs = _el(root, "equipment_control_schemes")
        for (u, code), ls in labels.items():
            x = _el(ecs, "equipment_control_scheme")
            _el(x, "eo_uid", u)
            _el(x, "control_method_ref", code)
            pl = _el(x, "point_labels")
            for lb in ls:
                _el(pl, "point_label", lb[:500])

    # ---- статусы методов ----
    if protos:
        mss = _el(root, "method_statuses")
        for s in protos:
            for i, (_, _, u) in enumerate(eos):
                d = ctx.data(i, s)
                x = _el(mss, "method_status")
                _el(x, "method_ref", s["code"])
                _el(x, "eo_uid", u)
                _el(x, "status", "not_performed" if d.get("np") else "performed")
                if d.get("np"):
                    _el(x, "reason", "other")
                    _opt(x, "reason_text", _txt(d.get("reason")))

    # ---- протоколы ----
    deviations = []  # (eo_uid, name, section code, text, tol)
    prs = _el(root, "protocols")
    order = 0
    for s in protos:
        items = []
        for i, (reo, eo, u) in enumerate(eos):
            d = ctx.data(i, s)
            if d.get("np"):
                continue
            tols = sec_tol_list(s, d)
            items.append((reo, u, d, tols))
        if not items:
            continue
        kind = s["kind"]
        block = ("uzt" if s.get("mode") == "thk" else "hardness") if kind == "points" else "vik" if kind == "checklist" else BLOCK.get(s["code"], "generic")
        if kind == "points" and not any(_dec(p.get("value")) for _, _, d, _ in items for el in d.get("elements", []) for p in el.get("points", [])):
            continue
        order += 1
        p = _el(prs, "protocol")
        _el(p, "protocol_id", uid(f"result:{r.id}:protocol:{s['code']}"))
        _el(p, "control_method_ref", s["code"])
        md = _el(p, "metadata")
        _el(md, "protocol_number", f"{number}-{order:02d}")
        _el(md, "order", order)
        _el(md, "protocol_date", rep_date.isoformat())
        if s.get("instrument") in ins_ids:
            _el(_el(md, "instrument_refs"), "ref", ins_ids[s["instrument"]])
        doer, lead = _specialist(info.members, methods[s["code"]])
        refs = list(dict.fromkeys(sp_ids[m["fio"]] for m in (doer, lead) if m and m.get("fio") in sp_ids))
        if refs:
            sr = _el(md, "specialist_refs")
            for ref in refs:
                _el(sr, "ref", ref)
        if proto_ntd[s["code"]]:
            nr = _el(md, "ntd_refs")
            for n in proto_ntd[s["code"]]:
                _el(nr, "ref", _ntd_code(n[:500]))
        data = _el(_el(p, "data"), f"{block}_data")
        for reo, u, d, tols in items:
            name = info.eos[reo.eo_id].name if reo.eo_id in info.eos else reo.label
            worst = _worst(tols)
            if kind == "points":
                x = _el(data, f"equipment_{block}_data")
                _el(x, "eo_ref", u)
                ms = _el(x, "measurements")
                k = 0
                for el in d.get("elements", []):
                    for pt in el.get("points", []):
                        tl, k = (tols[k] if k < len(tols) else "empty"), k + 1
                        v = _dec(pt.get("value"))
                        if not v:
                            continue
                        m = _el(ms, "measurement")
                        _el(m, "point_label", f"{el['name']}: {pt['label']}"[:500])
                        _el(m, "section_label", el["name"][:500])
                        _el(m, "s_measured_mm" if block == "uzt" else "avg_hb_value", v)
                        if tl in ("borderline", "exceeded"):
                            deviations.append((u, name, s["code"], f"{el['name']}, точка {pt['label']}: {v} {'мм' if block == 'uzt' else 'HB'}", tl))
                if not len(ms):
                    data.remove(x)
                    continue
            elif block == "generic":
                x = _el(data, "equipment_result")
                _el(x, "eo_ref", u)
                params = [(f["label"], _txt(d.get("values", {}).get(f["key"])), f) for f in s.get("fields", []) if _txt(d.get("values", {}).get(f["key"]))]
                rows = [(f"Строка {n}", "; ".join(f"{c['label']}: {_txt(row.get(c['key']))}" for c in s.get("cols", []) if _txt(row.get(c["key"]))), None)
                        for n, row in enumerate(d.get("rows", []), start=1)]
                rows = [x_ for x_ in rows if x_[1]]
                if worst != "empty":
                    _el(x, "assessment_result", worst)
                if params or rows:
                    ps = _el(x, "parameters")
                    for label, val, _f in params + rows:
                        pp = _el(ps, "parameter")
                        _el(pp, "name", label[:500])
                        _el(pp, "value", val)
                for f in s.get("fields", []):
                    tl = tol_field(f["tol"], d.get("values", {}).get(f["key"])) if f.get("tol") else None
                    if tl in ("borderline", "exceeded"):
                        deviations.append((u, name, s["code"], f"{f['label']}: {_txt(d['values'].get(f['key']))}", tl))
                _table_deviations(s, d, tols, u, name, deviations)
            else:
                x = _el(data, f"equipment_{block}_data")
                _el(x, "eo_ref", u)
                defects = []
                if kind == "checklist":
                    for code, label, op in s["items"]:
                        idx = d.get("items", {}).get(code, -1)
                        if isinstance(idx, int) and 0 <= idx < len(op) and op[idx][1] in ("borderline", "exceeded"):
                            note = d.get("notes", {}).get(code)
                            defects.append((f"{label}: {op[idx][0]}" + (f". {note}" if note else ""), op[idx][1]))
                else:
                    before = len(deviations)
                    _table_deviations(s, d, tols, u, name, deviations)
                    defects = [(t_, tl) for (_, _, _, t_, tl) in deviations[before:]]
                    del deviations[before:]
                if defects:
                    ds = _el(x, "defects")
                    for text, _tl in defects:
                        _el(_el(ds, "defect"), "description", text[:2000])
                    deviations += [(u, name, s["code"], text, tl) for text, tl in defects]
                if worst != "empty":
                    _el(x, "assessment_result", worst)
            _opt(x, "comment", _txt(d.get("concl")) or _txt(d.get("comment")))
        if not len(data):
            prs.remove(p)
            order -= 1
    if not len(prs):
        root.remove(prs)

    # ---- ведомость дефектов (только при подтверждённом виде работ ДТОиР) ----
    if deviations and work:
        st = _el(_el(root, "defects_statements"), "defects_statement")
        _el(st, "statement_id", uid(f"result:{r.id}:statement"))
        _el(st, "statement_status", "issued")
        _el(st, "statement_number", f"ВД-{number}")
        _el(st, "statement_date", rep_date.isoformat())
        _el(st, "technical_report_number", number)
        if t.xyz:
            _el(st, "repair_object_code", t.xyz)
        _el(st, "dtoir_work_type_ref", work_code)
        items = _el(st, "items")
        for n, (u, name, code, text, tl) in enumerate(deviations, start=1):
            it = _el(items, "item")
            _el(it, "item_no", n)
            _el(it, "noncompliance_category", CATEGORY.get(code, "structure_defects"))
            _el(it, "object_name", name[:500])
            _el(it, "eo_uid", u)
            _el(it, "defect_description", f"{methods.get(code, code)}. {text}")
            _el(it, "admissibility", "not_fit" if tl == "exceeded" else "fit")

    # ---- фото ----
    photos = []
    for s in secs:
        for i, (_, _, u) in enumerate(eos):
            for ph in ctx.data(i, s).get("photos", []) or []:
                if isinstance(ph, dict) and ph.get("id"):
                    photos.append((s, u, ph))
    if photos:
        phs = _el(root, "photos")
        for k, (s, u, ph) in enumerate(photos, start=1):
            fo = await session.get(FileObject, ph["id"])
            # ID фото приходят от клиента: берём только файлы этого результата ДО (старые загрузки привязаны миграцией 0002)
            if not fo or fo.deleted or fo.entity_type != "do_result" or fo.entity_id != str(r.id):
                continue
            ext = (fo.name.rsplit(".", 1)[-1].lower() if "." in fo.name else "bin")
            x = _el(phs, "photo")
            _el(x, "photo_id", uid(f"file:{fo.id}"))
            _el(x, "photo_kind", "eo")
            _el(x, "eo_uid", u)
            if s["code"] in methods:
                _el(x, "method_ref", s["code"])
            _el(x, "file_uri", f"files/{fo.id}.{ext}")
            _el(x, "sha256", hashlib.sha256(await read_file(fo)).hexdigest())
            _opt(x, "mime", fo.mime or mimetypes.guess_type(fo.name)[0])
            _opt(x, "caption", f"{s['title']}: {fo.name}")
            _el(x, "order", k)
        if not len(phs):
            root.remove(phs)

    # ---- заключение и подписи ----
    concl = ctx.data(0, sec["conclusion"]).get("values", {}) if "conclusion" in sec else {}
    text = " ".join(x for x in (_txt(concl.get("text")), f"Срок следующего технического диагностирования: {concl['next']}." if concl.get("next") else "") if x)
    if text:
        c = _el(_el(root, "conclusions"), "conclusion")
        _opt(c, "technical_state_ref", STATE_CODE.get(_txt(concl.get("ts"))))
        _el(c, "text", text)
    sigs = [(role, h) for role, status in STAGES_SIGN if (h := _hist_at(ctx, status))]
    if sigs:
        sg = _el(root, "signatures")
        for role, h in sigs:
            fio, pos = _fio(h.username)
            x = _el(sg, "signature")
            _el(x, "role", role)
            if fio in sp_ids:
                _el(x, "specialist_ref", sp_ids[fio])
            _el(x, "full_name", (fio or h.username or "—")[:500])
            _opt(x, "position", pos)
            _el(x, "signed_at", h.at.date().isoformat())
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True), f"{number}_{VID_SHORT.get(t.vid, t.vid)}.xml"


def _table_deviations(s, d, tols, u, name, out):
    if s["kind"] != "table":
        return
    for k, row in enumerate(d.get("rows", [])):
        tl = tols[k] if k < len(tols) else "empty"
        if tl in ("borderline", "exceeded"):
            out.append((u, name, s["code"], "; ".join(f"{c['label']}: {_txt(row.get(c['key']))}" for c in s.get("cols", []) if _txt(row.get(c["key"]))), tl))


async def render_result_xml(session, ctx, check: bool = True) -> tuple[bytes, str, dict]:
    """XML ТО + результат проверки (XSD v3.8 и правила V-*). Ошибки L1 блокируют выгрузку."""
    from app.services.reports import check_xml

    data, name = await build_result_xml(session, ctx)
    res = await check_xml(session, data)
    if check:
        blocking = [i for i in res["issues"] if i["level"] == "L1"]
        if blocking:
            raise RuleError("XML ТО не проходит проверку v3.8: " + "; ".join(i["text"] for i in blocking[:3]), blocking[0]["id"], 422)
    return data, name, res
