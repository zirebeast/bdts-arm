"""Сквозные сценарии S1–S5 (ТЗ, раздел 10) и ключевые правила R-*, D-*, V-* через REST API."""
import io

from openpyxl import load_workbook

from app.services.xml_samples import sample
from tests.conftest import H


async def test_me_and_access(client):
    r = await client.get("/me", headers=H("demo"))
    assert r.status_code == 200 and r.json()["startRoute"] == "/cabinet"
    me = (await client.get("/me", headers=H("gd.org"))).json()
    assert me["startRoute"] == "/tasks" and "task.create" in me["actions"]
    assert (await client.get("/me")).status_code == 401
    assert (await client.post("/tasks", json={"vid": "vessel"}, headers=H("viewer"))).status_code == 403
    # Разграничение по ДЭО: согласующий ОРГ_9 не видит задание ОРГ_6
    assert (await client.get("/tasks/2", headers=H("gd.sogl"))).status_code == 403
    lst = (await client.get("/tasks?mode=Все", headers=H("gd.sogl"))).json()
    assert lst["total"] > 0 and all(t["deo"] == "ОРГ_9" for t in lst["items"])


async def test_s1_task_lifecycle(client):
    refs = (await client.get("/refs", headers=H("gd.org"))).json()
    tpl = next(t for t in refs["templates"] if t["vid"] == "vessel")
    r = await client.post("/tasks", json={"vid": "vessel", "xyz": "", "deo": "ОРГ_9"}, headers=H("gd.org"))
    assert r.status_code == 422 and r.json()["rule"] == "R-B301-01" and "xyz" in r.json()["fields"]
    body = {"vid": "vessel", "xyz": "97488/2/142000094607_X", "eo_name": "Подогреватель газа №3", "deo": "ОРГ_9", "location": "КС-2, ГПА-3",
            "brigade": "Бригада №1", "template_id": tpl["id"], "start_date": "2027-01-15", "end_date": "2027-01-10"}
    r = await client.post("/tasks", json=body, headers=H("gd.org"))
    assert r.status_code == 422 and r.json()["fields"]["end_date"].startswith("Дата завершения")
    body["end_date"] = "2027-01-30"
    t = (await client.post("/tasks", json=body, headers=H("gd.org"))).json()
    assert t["status"] == "Черновик" and t["eoId"]
    t = (await client.post(f"/tasks/{t['id']}/send", json={"decision": "", "version": t["version"]}, headers=H("gd.org"))).json()
    assert t["status"] == "На согласовании" and not t["can"]["edit"]
    r = await client.post(f"/tasks/{t['id']}/decision", json={"decision": "rework", "comment": " "}, headers=H("gd.sogl"))
    assert r.status_code == 422 and r.json()["rule"] == "R-B301-04"
    t = (await client.post(f"/tasks/{t['id']}/decision", json={"decision": "rework", "comment": "Уточните бригаду"}, headers=H("gd.sogl"))).json()
    assert t["status"] == "На корректировке"
    # конфликт версий (оптимистическая блокировка)
    assert (await client.post(f"/tasks/{t['id']}/send", json={"decision": "", "version": 1}, headers=H("gd.org"))).status_code == 409
    await client.put(f"/tasks/{t['id']}", json={**body, "brigade": "Бригада №2", "version": t["version"]}, headers=H("gd.org"))
    t = (await client.post(f"/tasks/{t['id']}/send", headers=H("gd.org"))).json()
    t = (await client.post(f"/tasks/{t['id']}/decision", json={"decision": "approve"}, headers=H("gd.sogl"))).json()
    assert t["status"] == "Согласовано" and t["hasResult"]
    res = (await client.get(f"/results/{t['id']}", headers=H("gd.pole"))).json()
    assert res["status"] == "ПЭ не завершен" and any(a["key"] == "pe" for a in res["actions"])
    assert (await client.delete(f"/tasks/{t['id']}", headers=H("gd.org"))).json().get("rule") == "R-B301-05"
    notes = (await client.get("/notifications", headers=H("gd.sogl"))).json()
    assert notes["unread"] >= 1


def _fill(sec: dict, data: dict) -> dict:
    """Заполнить раздел корректными значениями (для ПЭ — с заключением специалиста)."""
    d = dict(data)
    for f in sec.get("fields", []):
        if f.get("req"):
            d["values"][f["key"]] = f["opts"][0] if f["type"] == "select" else "2030-01-01" if f["type"] == "date" else "12" if f["type"] == "num" else "Текст"
    if sec["kind"] == "checklist":
        d["items"] = {code: 0 for code, *_ in sec["items"]}
    if sec["kind"] == "points":
        for el, cfg in zip(d["elements"], sec["elements"]):
            for p in el["points"]:
                p["value"] = str(cfg.get("s", 0) * 1.3 if sec["mode"] == "thk" else (cfg.get("lo", sec.get("lo", 100)) + cfg.get("hi", sec.get("hi", 200))) / 2)
    if sec["kind"] == "table":
        d["rows"] = [{"id": 0, **{c["key"]: (c["opts"][0] if c["type"] == "select" else "10" if c["type"] == "num" else "Объект") for c in sec["cols"]}}]
    if sec["stage"] == "ПЭ":
        d["concl"] = "Контроль выполнен"
    return d


async def test_s2_result_lifecycle(client):
    res = (await client.get("/results/4", headers=H("gd.pole"))).json()
    uzt = next(s for s in res["sections"] if s["code"] == "uzt")
    bad = res["data"]["0"]["uzt"]
    bad["elements"][0]["points"][0]["value"] = "9,2abc"
    r = await client.put("/results/4/sections/uzt", json={"eo_idx": 0, "data": bad}, headers=H("gd.pole"))
    assert r.status_code == 422 and r.json()["rule"] == "R-B303-04"
    fin = next(a for a in res["actions"] if a["key"] == "pe_finish")
    assert fin["disabled"] and res["hints"]
    assert (await client.post("/results/4/actions/pe_finish", json={}, headers=H("gd.pole"))).json()["rule"] == "R-B303-03"
    # КП нельзя вносить в статусе ПЭ
    r = await client.put("/results/4/sections/calc", json={"eo_idx": 0, "data": res["data"]["0"]["calc"]}, headers=H("demo"))
    assert r.status_code == 403
    for eo in res["eos"]:
        for s in res["sections"]:
            if s["stage"] == "ПЭ" and s["kind"] != "info":
                cur = (await client.get("/results/4", headers=H("gd.pole"))).json()
                r = await client.put(f"/results/4/sections/{s['code']}", json={"eo_idx": eo["idx"], "data": _fill(s, cur["data"][str(eo["idx"])][s["code"]])}, headers=H("gd.pole"))
                assert r.status_code == 200, r.text
    res = (await client.get("/results/4", headers=H("gd.pole"))).json()
    assert not next(a for a in res["actions"] if a["key"] == "pe_finish")["disabled"]
    res = (await client.post("/results/4/actions/pe_finish", json={}, headers=H("gd.pole"))).json()
    assert res["status"] == "Требуется КП" and res["task"]["status"] == "Полевой этап завершен"
    for eo in res["eos"]:
        for s in res["sections"]:
            if s["stage"] == "КП":
                cur = (await client.get("/results/4", headers=H("gd.kamer"))).json()
                r = await client.put(f"/results/4/sections/{s['code']}", json={"eo_idx": eo["idx"], "data": _fill(s, cur["data"][str(eo["idx"])][s["code"]])}, headers=H("gd.kamer"))
                assert r.status_code == 200, r.text
    res = (await client.post("/results/4/actions/form", json={}, headers=H("gd.kamer"))).json()
    assert res["toFormed"] and res["toFile"]
    docx = await client.get("/results/4/export?kind=to", headers=H("gd.kamer"))
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    res = (await client.post("/results/4/actions/send", json={}, headers=H("gd.kamer"))).json()
    assert res["status"] == "На согласовании" and res["task"]["status"] == "Технический отчет сформирован"
    r = await client.post("/results/4/actions/agree", json={"decision": "b", "comment": ""}, headers=H("demo"))
    assert r.json()["rule"] == "R-B303-05"
    res = (await client.post("/results/4/actions/agree", json={"decision": "a"}, headers=H("demo"))).json()
    assert res["status"] == "На рассмотрении ДЭО"
    res = (await client.post("/results/4/actions/deo", json={"decision": "a"}, headers=H("deo.to"))).json()
    assert res["status"] == "Принят ДЭО"
    before = (await client.get("/ts-records?size=1", headers=H("demo"))).json()["total"]
    res = (await client.post("/results/4/actions/epb_need", json={"decision": "b"}, headers=H("deo.to"))).json()
    assert res["status"] == "Результат получен" and res["task"]["status"] == "Выполнено"
    after = (await client.get("/ts-records?size=1", headers=H("demo"))).json()["total"]
    assert after == before + len(res["eos"])


async def test_s3_technical_report(client):
    name, data = sample("errors")
    chk = (await client.post("/reports/check", files={"file": (name, data, "application/xml")}, headers=H("gd.upload"))).json()
    assert chk["xsdOk"] and chk["summary"]["Block"] == 2 and chk["exists"]
    ids = {i["id"] for i in chk["issues"]}
    assert {"V-EQ-029", "V-PH-002", "V-UZT-010", "V-DS-009", "D-TO-04", "V-DIC-045", "V-P-010"} <= ids
    bad = await client.post("/reports/check", files={"file": ("x.xml", b"<technical_report/>", "application/xml")}, headers=H("gd.upload"))
    assert not bad.json()["xsdOk"] and bad.json()["issues"][0]["id"] == "D-TO-06"
    assert (await client.post("/reports", files={"file": ("x.xml", b"<a>", "application/xml")}, headers=H("gd.upload"))).json()["rule"] == "D-TO-06"
    lst = (await client.get("/reports", headers=H("gd.upload"))).json()
    grs = next(r for r in lst["items"] if r["number"].startswith("АТД"))
    assert grs["version"] == "v2" and grs["unmappedCount"] == 2
    card = (await client.get(f"/reports/{grs['id']}", headers=H("gd.upload"))).json()
    assert "L1" in card["sendBlockReason"]
    assert (await client.post(f"/reports/{grs['id']}/send", headers=H("gd.upload"))).status_code == 422
    name, fixed = sample("fixed")
    card = (await client.post("/reports", files={"file": (name, fixed, "application/xml")}, data={"report_id": str(grs["id"])}, headers=H("gd.upload"))).json()
    assert card["version"] == "v3" and card["sendBlockReason"].startswith("Сопоставьте 2")
    eos = (await client.get("/refs/eo?q=Задвижка&deo=ОРГ_9", headers=H("gd.upload"))).json()
    items = [{"id": e["id"], "bdoEoId": eos[0]["id"]} if not e["bdoEoId"] and "Задвижка" in e["name"] else {"id": e["id"], "repairObject": True} if not e["bdoEoId"] else {"id": e["id"], "bdoEoId": e["bdoEoId"]}
             for e in card["equipment"]]
    card = (await client.put(f"/reports/{grs['id']}/mapping", json={"items": items}, headers=H("gd.upload"))).json()
    assert card["sendBlockReason"] == ""
    card = (await client.post(f"/reports/{grs['id']}/send", headers=H("gd.upload"))).json()
    assert card["status"] == "На рассмотрении ДЭО"
    r = await client.post(f"/reports/{grs['id']}/decision", json={"decision": "rework", "comment": ""}, headers=H("deo.to"))
    assert r.status_code == 422
    card = (await client.post(f"/reports/{grs['id']}/decision", json={"decision": "done"}, headers=H("deo.to"))).json()
    assert card["status"] == "Завершено ДЭО" and len(card["records"]) == 6
    xml = await client.get("/reports/sample-xml?kind=new", headers=H("gd.upload"))
    assert xml.status_code == 200 and b"technical_report" in xml.content


async def test_s4_storage(client):
    roots = (await client.get("/hierarchy", headers=H("deo.ts"))).json()
    assert roots and all(r["type"] == "ТМ" and r["deo"] == "ОРГ_9" for r in roots)
    kids = (await client.get(f"/hierarchy?node={roots[0]['key']}", headers=H("deo.ts"))).json()
    assert kids
    eo = next(x for x in (await client.get("/refs/eo?q=Подогреватель газа №3", headers=H("deo.ts"))).json())
    card = (await client.get(f"/eo/{eo['id']}", headers=H("deo.ts"))).json()
    assert card["st"] and card["records"] and card["compare"]
    rec = card["records"][0]
    assert (await client.post(f"/ts-records/{rec['id']}/confirm", json={"status": "Подтверждено"}, headers=H("gd.org"))).status_code == 403
    d = (await client.patch(f"/ts-records/{rec['id']}", json={"st": "Ограниченно работоспособное"}, headers=H("deo.ts"))).json()
    assert d["confirm"] == "Требует подтверждения"
    d = (await client.post(f"/ts-records/{rec['id']}/confirm", json={"status": "Подтверждено"}, headers=H("deo.ts"))).json()
    assert d["confirm"] == "Подтверждено" and d["confirmedBy"] == "ФИО_7"
    r = await client.post("/ts-records", json={"recordType": "Выполнение ТОиР", "eoId": eo["id"], "st": "Работоспособное", "desc": "Замена уплотнений"}, headers=H("deo.ts"))
    assert r.json()["confirm"] == "Требует подтверждения"
    s = (await client.get("/search?q=Подогреватель*", headers=H("deo.ts"))).json()
    assert any(i["kind"] == "eo" for i in s["items"])
    assert (await client.get("/search?q=" + "x" * 1001, headers=H("deo.ts"))).json()["rule"] == "R-SRCH-01"
    xlsx = (await client.get("/ts-records/import-template.xlsx", headers=H("deo.ts"))).content
    assert load_workbook(io.BytesIO(xlsx)).sheetnames[0] == "Запись о техсостоянии"
    r = (await client.post("/ts-import", files={"file": ("import.xlsx", xlsx, "application/octet-stream")}, data={"kind": "Импорт данных"}, headers=H("deo.ts"))).json()
    assert r["state"] == "done" and r["loaded"] == 1 and r["warnings"] == 1
    entries = (await client.get(f"/logs/entries?log_id={r['id']}", headers=H("deo.ts"))).json()["items"]
    assert any(e["level"] == "Предупреждение" for e in entries)


async def test_s5_planning_and_delta(client):
    p = (await client.get("/planning?criteria=Дефекты прошлого периода|Истекает срок ЭПБ", headers=H("deo.plan"))).json()
    assert p["items"]
    ids = [p["items"][0]["id"]]
    assert (await client.post("/planning/marks", json={"eoIds": ids, "mark": "both"}, headers=H("deo.plan"))).json()["rule"] == "D-PLN-02"
    assert (await client.post("/planning/marks", json={"eoIds": ids, "mark": "mark3y"}, headers=H("deo.plan"))).json()["updated"] == 1
    ex = (await client.post("/planning/export", json={"eoIds": ids}, headers=H("deo.plan"))).json()
    hist = (await client.get("/planning/exports", headers=H("deo.plan"))).json()
    assert hist[0]["number"] == ex["number"]
    prev = (await client.post("/inbound/plan/preview", json={"year": 2027}, headers=H("deo.plan"))).json()
    assert prev["stats"]["objects"] == 5 and prev["stats"]["errors"] == 1
    acc = (await client.post("/inbound/plan/accept", json={"rows": prev["rows"], "source": prev["source"], "year": 2027}, headers=H("deo.plan"))).json()
    assert acc["created"] == 5
    objs = (await client.get("/inbound/objects?q=Южная", headers=H("deo.plan"))).json()["items"]
    oid = objs[0]["id"]
    cat = (await client.get(f"/inbound/objects/{oid}/bdo", headers=H("deo.plan"))).json()
    added = (await client.post(f"/inbound/objects/{oid}/bdo", json={"asupp": [c["asupp"] for c in cat]}, headers=H("deo.plan"))).json()
    assert added["added"] == 5
    bad = await client.post(f"/inbound/objects/{oid}/eo", json={"form": {"type": "Кран шаровой", "techNum": "6-2-40"}}, headers=H("deo.plan"))
    assert bad.status_code == 422 and bad.json()["fields"]["techNum"].startswith("Технологический")
    form = {"type": "Кран шаровой", "mark": "КШ 150/80", "techNum": "6-2-99", "serialNum": "777", "dn": "150", "pn": "8.0", "sCalc": "14.0", "steelGrade": "09Г2С"}
    assert (await client.post(f"/inbound/objects/{oid}/eo", json={"form": form}, headers=H("deo.plan"))).status_code == 200
    assert (await client.post(f"/inbound/objects/{oid}/ps0", headers=H("deo.plan"))).json()["created"] == 1
    tpls = (await client.get("/survey-templates", headers=H("deo.plan"))).json()
    pub = next(t for t in tpls if t["status"] == "Опубликован")
    assert (await client.post("/surveys/generate", json={"objectId": oid, "templateId": pub["id"]}, headers=H("deo.plan"))).json()["created"] == 6
    sv = next(s for s in (await client.get("/surveys", headers=H("deo.plan"))).json() if s["status"] == "Заполнен")
    assert (await client.post(f"/surveys/{sv['id']}/accept", headers=H("deo.plan"))).json()["discrepancies"] >= 1
    for tab in ("D1", "D2", "D3", "D4", "D5"):
        r = await client.get(f"/dashboards/{tab}", headers=H("deo.plan"))
        assert r.status_code == 200, tab
    rep = (await client.post("/analytics/activities", json={"from": "2020-01-01", "to": "2027-12-31"}, headers=H("deo.ts"))).json()
    assert rep["rows"]
    assert (await client.get("/cabinet", headers=H("demo"))).json()["widgets"]


async def test_nsi_vtd_settings(client):
    r = await client.post("/nsi/B314", json={"data": {"name": ""}}, headers=H("admin"))
    assert r.status_code == 422 and r.json()["rule"] == "R-NSI-01"
    rec = (await client.post("/nsi/B314", json={"data": {"name": "Толщиномер УТ-907"}}, headers=H("admin"))).json()
    rec2 = (await client.post("/nsi/B314", json={"data": {"name": "Толщиномер УТ-907М"}}, headers=H("admin"))).json()
    assert rec["recordNo"] > 4003 and rec2["recordNo"] == rec["recordNo"] + 1  # № записи — следующий за максимальным в каталоге
    assert (await client.delete(f"/nsi/B314/{rec['id']}", headers=H("admin"))).json()["recordStatus"] == "Помечено на удаление"
    assert (await client.post("/nsi/B314", json={"data": {"name": "x"}}, headers=H("deo.ts"))).status_code == 403
    d = (await client.get("/dict38", headers=H("admin"))).json()
    assert any(x["code"] == "Steel_Grades" and x["candidate"] > 0 for x in d)
    v = (await client.get("/vtd", headers=H("admin"))).json()
    assert any(s["overlaps"] for s in v["items"])
    s = (await client.get("/settings", headers=H("admin"))).json()
    assert s["canEdit"] and len(s["notify_rules"]["items"]) == 11
    assert (await client.put("/settings/report_period", json={"closed_to": "2026-06-30"}, headers=H("deo.ts"))).status_code == 403
    i = (await client.get("/integrations", headers=H("admin"))).json()
    assert len(i["adapters"]) == 7


async def test_result_report_docx_on_the_fly(client):
    """Завершённый результат ДО: ТО .docx формируется по данным (структура формы В.1, п. 7.1.4, 7.1.7, 7.1.9)."""
    import io

    from docx import Document

    for tid in (11, 12, 13, 14, 15):
        res = (await client.get(f"/results/{tid}", headers=H("demo"))).json()
        assert res["status"] == "Результат получен" and any(e["key"] == "export" for e in res["exports"])
        r = await client.get(f"/results/{tid}/export", params={"kind": "to"}, headers=H("demo"))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
        doc = Document(io.BytesIO(r.content))
        text = "\n".join(p.text for p in doc.paragraphs)
        for must in ("УТВЕРЖДАЮ", "ТЕХНИЧЕСКИЙ ОТЧЁТ", "1. Основания для проведения работ", "7. Перечень приборов и оборудования",
                     "13. Результаты технического диагностирования", "15. Выводы по результатам технического диагностирования",
                     "Рекомендуемый срок проведения следующего технического диагностирования", "ПРИЛОЖЕНИЕ № 1", "ЛИСТ СОГЛАСОВАНИЯ"):
            assert must in text, (tid, must)
        assert len(doc.tables) > 10
    # ДЭО другого филиала выгрузить не может
    assert (await client.get("/results/13/export", params={"kind": "to"}, headers=H("deo.to"))).status_code == 403


async def test_result_report_xml_on_the_fly(client):
    """ТО .xml по тем же данным, что и .docx: проходит XSD v3.8 и правила V-* без ошибок L1 (4 вида ДО)."""
    from urllib.parse import unquote

    from app.services import tr_xml

    for tid in (11, 12, 13, 14, 15):
        docx_name = unquote((await client.get(f"/results/{tid}/export", params={"kind": "to"}, headers=H("demo"))).headers["content-disposition"])
        r = await client.get(f"/results/{tid}/export", params={"kind": "to_xml"}, headers=H("demo"))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml"), (tid, r.text[:300])
        root = tr_xml.parse_xml(r.content)
        assert tr_xml.validate_xsd(root) == [], tid
        p = tr_xml.extract(root)
        assert not [i for i in tr_xml.rules(p) if i["level"] == "L1"], tid
        assert f"''{p['report']['number']}_" in docx_name, (tid, docx_name)  # номер ТО общий с .docx
        assert p["equipment"] and all(e["s_calc"] for e in p["equipment"])  # V-EQ-029
        kinds = {pr["kind"] for pr in p["protocols"]}
        assert {"vik_data", "uzt_data", "hardness_data"} <= kinds, (tid, kinds)
        assert any(m["value"] for pr in p["protocols"] if pr["kind"] == "uzt_data" for row in pr["rows"] for m in row["measurements"])
        assert p["conclusions"] and p["conclusions"][0]["state"] in ("normative", "serviceable", "limited_serviceable", "emergency")
        assert p["signatures"]
        # нет подтверждённого вида работ ДТОиР → ведомость дефектов не выгружается
        assert p["statements"] == []
    assert (await client.get("/results/13/export", params={"kind": "to_xml"}, headers=H("deo.to"))).status_code == 403


async def test_result_report_xml_defects_statement_after_dtoir_confirmed(client):
    """После подтверждения вида работ ДТОиР (W-5.10) отклонения выгружаются ведомостью дефектов."""
    from app.services import tr_xml

    rows = (await client.get("/dict38/DTOIR_Work_Types", params={"q": "dtoir_11"}, headers=H("admin"))).json()["items"]
    eid = next(x["id"] for x in rows if x["code"] == "dtoir_11")
    assert (await client.post(f"/dict38/entry/{eid}/verify", json={"status": "confirmed"}, headers=H("admin"))).status_code == 200
    try:
        r = await client.get("/results/13/export", params={"kind": "to_xml"}, headers=H("demo"))
        root = tr_xml.parse_xml(r.content)
        assert tr_xml.validate_xsd(root) == []
        st = tr_xml.extract(root)["statements"]
        assert len(st) == 1 and st[0]["work_type"] == "dtoir_11" and st[0]["items"]
        assert [int(i["no"]) for i in st[0]["items"]] == list(range(1, len(st[0]["items"]) + 1))
    finally:
        await client.post(f"/dict38/entry/{eid}/verify", json={"status": "candidate"}, headers=H("admin"))


async def test_result_report_xml_photos_only_own_files(client):
    """Фото в XML — только файлы этого результата ДО: чужой ID файла в данных раздела игнорируется."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import DoResult, DoResultSection
    from app.services import tr_xml

    async with SessionLocal() as s:
        r = (await s.execute(select(DoResult).where(DoResult.task_id == 13))).scalars().first()
        rid = r.id
    up = lambda et, eid: client.post("/files", files={"file": ("p.jpg", b"\xff\xd8photo", "image/jpeg")},  # noqa: E731
                                     data={"entity_type": et, "entity_id": eid}, headers=H("demo"))
    own, foreign = (await up("do_result", str(rid))).json()["id"], (await up("ts_record", "1")).json()["id"]
    async with SessionLocal() as s:
        row = (await s.execute(select(DoResultSection).where(DoResultSection.result_id == rid, DoResultSection.code == "vik"))).scalars().first()
        old = row.data
        row.data = {**old, "photos": [{"id": own, "name": "p.jpg"}, {"id": foreign, "name": "x.jpg"}]}
        await s.commit()
    try:
        r = await client.get("/results/13/export", params={"kind": "to_xml"}, headers=H("demo"))
        photos = tr_xml.extract(tr_xml.parse_xml(r.content))["photos"]
        assert [p["uri"] for p in photos] == [f"files/{own}.jpg"]
    finally:
        async with SessionLocal() as s:
            row = (await s.execute(select(DoResultSection).where(DoResultSection.result_id == rid, DoResultSection.code == "vik"))).scalars().first()
            row.data = old
            await s.commit()


async def test_file_access_by_owner_deo(client):
    """GET/DELETE /files/{id}: файл доступен по ДЭО записи-владельца; файл без владельца — только загрузившему."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import DoResult, DoTask

    async with SessionLocal() as s:
        foreign = (await s.execute(select(DoResult).join(DoTask).where(DoTask.deo != "ОРГ_9", DoResult.to_file_id.is_not(None)))).scalars().first()
        own = (await s.execute(select(DoResult).join(DoTask).where(DoTask.deo == "ОРГ_9"))).scalars().first()
        foreign_file, foreign_id, own_id = foreign.to_file_id, foreign.id, own.id
    assert (await client.get(f"/files/{foreign_file}", headers=H("demo"))).status_code == 200  # без ограничения по ДЭО
    assert (await client.get(f"/files/{foreign_file}", headers=H("deo.to"))).status_code == 404  # ДЭО ОРГ_9 — чужой филиал
    assert (await client.delete(f"/files/{foreign_file}", headers=H("deo.to"))).status_code == 404
    up = lambda et, eid, who: client.post("/files", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},  # noqa: E731
                                          data={"entity_type": et, "entity_id": eid}, headers=H(who))
    assert (await up("do_result", str(foreign_id), "deo.to")).status_code == 403  # нельзя привязать файл к чужой записи
    mine = (await up("do_result", str(own_id), "deo.to")).json()["id"]
    assert (await client.get(f"/files/{mine}", headers=H("deo.ts"))).status_code == 200  # тот же ДЭО
    draft = (await up("draft", "", "deo.to")).json()["id"]
    assert (await client.get(f"/files/{draft}", headers=H("deo.to"))).status_code == 200  # загрузивший
    assert (await client.get(f"/files/{draft}", headers=H("deo.ts"))).status_code == 404  # владелец не определён


async def test_epb_accepts_only_own_result_files(client):
    """Действие «ЭПБ»: ID файла от клиента — только файл, загруженный к этому результату ДО (иначе выгрузка отдала бы чужой файл)."""
    res = (await client.get("/results/11", headers=H("demo"))).json()
    assert res["status"] == "Результат получен"
    up = lambda et, eid: client.post("/files", files={"file": ("e.pdf", b"%PDF-1.4", "application/pdf")},  # noqa: E731
                                     data={"entity_type": et, "entity_id": eid}, headers=H("demo"))
    foreign = (await up("ts_record", "1")).json()["id"]
    r = await client.post("/results/11/actions/epb", json={"file_id": foreign, "comment": "замена"}, headers=H("demo"))
    assert r.status_code == 422 and "файлов результата" in r.text
    own = (await up("do_result", str(res["id"]))).json()["id"]
    r = await client.post("/results/11/actions/epb", json={"file_id": own, "comment": "замена"}, headers=H("demo"))
    assert r.status_code == 200 and r.json()["epbFile"]["id"] == own


async def test_hs_report_registered_with_xml_content(client):
    """ТО хозспособа в реестре: содержимое и проверка — по XML v3.8, ЕО отчёта совпадают с ЕО XML (раскладка в Б316)."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import TechnicalReport
    from app.permissions import DEV_USERS, build_user
    from app.services import results as res_svc
    from app.services.reports import register_hs_report

    u = DEV_USERS["demo"]
    user = build_user("demo", u["fio"], u["roles"], u.get("deo", ""), "")
    async with SessionLocal() as s:
        ctx = await res_svc.load(s, 10, user)
        assert ctx.task.is_hs
        await register_hs_report(s, ctx, user)
        await s.commit()
        rep = (await s.execute(select(TechnicalReport).where(TechnicalReport.result_id == ctx.r.id))).scalars().first()
        v = rep.versions[-1]
        assert v.validation["xsd_ok"] and not [i for i in v.validation["issues"] if i["level"] == "L1"]
        assert {e["uid"] for e in v.parsed["equipment"]} == {e.xml_uid for e in rep.equipment}
        assert v.parsed["report"]["profile"] == "to_vessel"


async def test_cabinet_deo_filter(client):
    w = {d: {x["title"]: x["count"] for x in (await client.get("/cabinet", params={"deo": d}, headers=H("admin"))).json()["widgets"]} for d in ("", "ОРГ_4", "ОРГ_6", "ОРГ_9")}
    key = "Единицы оборудования на контроле"
    assert w["ОРГ_4"][key] + w["ОРГ_6"][key] + w["ОРГ_9"][key] == w[""][key]
    assert len({tuple(sorted(w[d].items())) for d in ("ОРГ_4", "ОРГ_6", "ОРГ_9")}) == 3
    # пользователь ДЭО видит только свой филиал, параметр игнорируется
    own = (await client.get("/cabinet", params={"deo": "ОРГ_4"}, headers=H("deo.ts"))).json()
    assert own["deo"] == "ОРГ_9"


async def test_notifications_read_unread_and_dashboards(client):
    """В демо-данных есть и прочитанные, и новые уведомления; фильтры согласованы со счётчиком. Дашборды D1–D5 по всем ДЭО."""
    r = {f: (await client.get("/notifications", params={"filter": f}, headers=H("demo"))).json() for f in ("Все", "Непрочитанные", "Прочитанные")}
    assert r["Непрочитанные"]["items"] and r["Прочитанные"]["items"]
    assert len(r["Непрочитанные"]["items"]) == r["Все"]["unread"]
    assert len(r["Непрочитанные"]["items"]) + len(r["Прочитанные"]["items"]) == len(r["Все"]["items"])
    for deo in ("", "ОРГ_4", "ОРГ_6", "ОРГ_9"):
        for tab in ("D1", "D2", "D3", "D4", "D5"):
            d = await client.get(f"/dashboards/{tab}", params={"deo": deo}, headers=H("demo"))
            assert d.status_code == 200 and d.json()["tab"] == tab, (deo, tab)
