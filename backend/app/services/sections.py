"""Разделы результата ДО: оценка допуска, статус раздела, заготовка данных. Логика совпадает с frontend/src/domain/sections.ts."""
from typing import Any

RANK = {"empty": 0, "ok": 1, "borderline": 2, "exceeded": 3}


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def tol_field(spec: dict | None, v: Any) -> str | None:
    if not spec:
        return None
    t = spec["t"]
    if t == "map":
        return spec["m"].get(_s(v), "empty")
    x = _num(v)
    if _s(v) == "" or x is None:
        return "empty"
    if t == "gt":
        return "exceeded" if x > spec["v"] else "ok"
    if t == "ge_ok":
        return "ok" if x >= spec["v"] else "borderline"
    return None


def tol_row(spec: dict, r: dict) -> str:
    t = spec["t"]
    if t == "doc":
        st = _s(r.get("st"))
        return "empty" if not st else "borderline" if st == "Не предоставлен" else "ok"
    if t == "col":
        return spec["m"].get(_s(r.get(spec["c"])), "empty")
    if t == "cols":
        vals = [m.get(_s(r.get(c)), "empty") for c, m in spec["cs"]]
        return "empty" if "empty" in vals else max(vals, key=RANK.get)
    if t == "vol_col":
        vol = _num(r.get(spec["vol"]))
        if _s(r.get(spec["vol"])) and vol is not None and vol < spec["min"]:
            return "borderline"
        return spec["m"].get(_s(r.get(spec["c"])), "empty")
    if t in ("bands", "abs_bands"):
        x = _num(r.get(spec["c"]))
        if x is None:
            return "empty"
        if t == "abs_bands":
            x = abs(x)
        elif x < 0:
            return "empty"
        return "exceeded" if x > spec["bad"] else "borderline" if x > spec["warn"] else "ok"
    if t == "range":
        x = _num(r.get(spec["c"]))
        if x is None:
            return "empty"
        return "ok" if spec["lo"] <= x <= spec["hi"] else "exceeded"
    if t == "plan_fact":
        plan, fact = _num(r.get("plan")), _num(r.get("fact"))
        if _s(r.get("fact")) == "":
            return "empty"
        if plan is not None and fact is not None and fact < plan:
            return "borderline"
        return "ok"
    if t == "nonempty":
        return "ok" if _s(r.get(spec["c"])) else "empty"
    return "empty"


def tol_thk(v: Any, s: float) -> str:
    x = _num(v)
    if x is None or x <= 0:
        return "empty"
    if x < s:
        return "exceeded"
    return "borderline" if x <= 1.08 * s else "ok"


def tol_hb(v: Any, lo: float, hi: float) -> str:
    x = _num(v)
    if x is None or x <= 0:
        return "empty"
    if x < lo or x > hi:
        return "exceeded"
    return "borderline" if x <= lo + 8 or x >= hi - 8 else "ok"


def point_labels(sec: dict, el_idx: int, n: int) -> list[str]:
    labels = sec.get("labels") or []
    return [(labels[i] if el_idx == 0 and i < len(labels) else f"Т{i + 1}") for i in range(n)]


def build_sec_data(sec: dict, with_sample: bool) -> dict:
    d: dict = {"np": False, "reason": "", "serial": "", "values": {}, "items": {}, "notes": {}, "elements": [],
               "rows": [], "files": [], "comment": "", "photos": [], "concl": ""}
    for f in sec.get("fields", []):
        d["values"][f["key"]] = f.get("v", "") if with_sample else ""
    kind = sec["kind"]
    if kind == "checklist":
        sample = sec.get("sampleItems") or {}
        for code, *_ in sec["items"]:
            d["items"][code] = sample.get(code, -1) if with_sample else -1
        if with_sample and sec.get("sampleSerial"):
            d["serial"] = sec["sampleSerial"]
    if kind == "points":
        for ei, el in enumerate(sec["elements"]):
            sample = el["sample"] if with_sample else [""] * el["min"]
            n = max(el["min"], len(sample))
            labels = point_labels(sec, ei, n)
            d["elements"].append({"name": el["name"], "points": [
                {"id": f"{ei}-{i}", "label": lb, "value": sample[i] if i < len(sample) else "", "extra": i >= el["min"]}
                for i, lb in enumerate(labels)]})
        if with_sample:
            d["serial"] = "А12-550192"
    if kind == "table":
        rows = sec.get("sample", [])
        d["rows"] = [{"id": i, **(r if with_sample else {k: "" for k in r})} for i, r in enumerate(rows)]
    if with_sample and sec["code"] != "general" and sec["kind"] != "info":
        if sec["stage"] == "ПЭ":
            d["concl"] = sec.get("sampleConcl", "Контроль выполнен в полном объёме, результаты в протоколе")
    return d


def sample_kp_values(sec: dict) -> dict:
    """Демо-заполнение разделов КП для засеянных результатов."""
    vals = {}
    for f in sec.get("fields", []):
        if f.get("v") is not None:
            vals[f["key"]] = f["v"]
        elif f["type"] == "select":
            vals[f["key"]] = f["opts"][1] if f["key"] == "ts" and len(f["opts"]) > 1 else f["opts"][0]
        elif f["type"] == "date":
            vals[f["key"]] = "2029-10-15"
        elif f["type"] == "num":
            vals[f["key"]] = {"rt": "12", "vc": "0.05", "st": "10.6"}.get(f["key"], "1")
        else:
            vals[f["key"]] = "Объект допускается к дальнейшей эксплуатации при выполнении компенсирующих мероприятий" if f["type"] == "textarea" else "Корпус"
    return vals


def sec_tol_list(sec: dict, d: dict) -> list[str]:
    out = []
    for f in sec.get("fields", []):
        if f.get("tol"):
            out.append(tol_field(f["tol"], d.get("values", {}).get(f["key"], "")))
    kind = sec["kind"]
    if kind == "checklist":
        res = []
        for code, _name, op in sec["items"]:
            idx = d.get("items", {}).get(code, -1)
            res.append(op[idx][1] if isinstance(idx, int) and 0 <= idx < len(op) else "empty")
        return res
    if kind == "points":
        res = []
        for ei, el in enumerate(d.get("elements", [])):
            cfg = sec["elements"][ei] if ei < len(sec["elements"]) else {}
            for p in el.get("points", []):
                if sec["mode"] == "thk":
                    res.append(tol_thk(p.get("value"), cfg.get("s", 0)))
                else:
                    res.append(tol_hb(p.get("value"), cfg.get("lo", sec.get("lo", 0)), cfg.get("hi", sec.get("hi", 0))))
        return res
    if kind == "table":
        return [tol_row(sec["tol"], r) for r in d.get("rows", [])] + out
    return out


def sec_status(sec: dict, d: dict) -> str:
    """not_started | in_progress | done | skipped. Для разделов ПЭ нужно заключение специалиста (Б303-14)."""
    if sec["kind"] == "info":
        return "done"
    if d.get("np"):
        return "skipped"
    total = filled = 0

    def need(ok: bool):
        nonlocal total, filled
        total += 1
        filled += 1 if ok else 0

    for f in sec.get("fields", []):
        if f.get("req"):
            need(_s(d.get("values", {}).get(f["key"])) != "")
    kind = sec["kind"]
    if kind == "checklist":
        for code, *_ in sec["items"]:
            idx = d.get("items", {}).get(code, -1)
            need(isinstance(idx, int) and idx >= 0)
    if kind == "points":
        for el in d.get("elements", []):
            for p in el.get("points", []):
                if not p.get("extra") or _s(p.get("value")):
                    need(_s(p.get("value")) != "")
    if kind == "table":
        rows = d.get("rows", [])
        need(len(rows) > 0)
        for r in rows:
            for c in sec["cols"]:
                req_if = c.get("reqIf")
                if not req_if or _s(r.get(req_if["col"])) == req_if["eq"]:
                    need(_s(r.get(c["key"])) != "")
    if kind == "files":
        need(len(d.get("files", [])) > 0)
    if sec["stage"] == "ПЭ":
        need(_s(d.get("concl")) != "")
    if filled == 0:
        return "not_started"
    return "done" if filled == total else "in_progress"
