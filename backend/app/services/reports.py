"""Δ Технические отчёты XSD v3.8 (W-2.3, W-2.4): загрузка и версии, проверки, сопоставление ЕО с БДО, решение ДЭО, раскладка в Б316."""
import re
from datetime import date

from sqlalchemy import select

from app.errors import RuleError, not_found
from app.models import (
    Dict38Entry, EquipmentUnit, FileObject, TechnicalReport, TechnicalReportEo, TechnicalReportHistory, TechnicalReportVersion,
    TsMeasurement, TsMessage, TsRecord,
)
from app.permissions import CurrentUser
from app.services import tr_xml
from app.services.common import audit, fmt_date, next_number, notify, parse_date
from app.services.events import emit
from app.services.storage import save_file

STATE_RU = {"normative": "Исправное", "serviceable": "Работоспособное", "limited_serviceable": "Ограниченно работоспособное", "emergency": "Неработоспособное"}
PROFILE_RU = {"to_grs": "ГРС (to_grs)", "to_tpa": "ТПА (to_tpa)", "to_vessel": "Сосуды (to_vessel)", "to_wellhead": "ФА и КГ (to_wellhead)", "vtd_file": "ВТД (файл, OQ-13)"}
UPLOADABLE = ("Загружен", "На доработке")


async def check_xml(session, data: bytes) -> dict:
    try:
        root = tr_xml.parse_xml(data)
    except Exception as e:  # noqa: BLE001 — любой сбой разбора = Block D-TO-06
        issues = [tr_xml._issue("D-TO-06", "L1", f"Файл не является корректным XML: {str(e)[:200]}", "Проверка")]
        return {"xsd_ok": False, "parsed": {}, "issues": issues, "summary": tr_xml.summarize(issues)}
    issues = tr_xml.validate_xsd(root)
    if issues:
        return {"xsd_ok": False, "parsed": {}, "issues": issues, "summary": tr_xml.summarize(issues)}
    parsed = tr_xml.extract(root)
    groups = set((await session.execute(select(Dict38Entry.code).where(Dict38Entry.dictionary == "Equipment_Types",
                                                                        Dict38Entry.payload["is_group"].as_boolean().is_(True)))).scalars())
    candidates = set((await session.execute(select(Dict38Entry.code).where(Dict38Entry.dictionary == "Steel_Grades",
                                                                            Dict38Entry.verification_status == "candidate"))).scalars())
    known = set((await session.execute(select(EquipmentUnit.code))).scalars())
    issues = tr_xml.rules(parsed, groups, candidates, known)
    return {"xsd_ok": True, "parsed": parsed, "issues": issues, "summary": tr_xml.summarize(issues),
            "eoCount": len(parsed["equipment"]), "unmapped": sum(1 for e in parsed["equipment"] if e["asupp"] not in known)}


async def get_report(session, report_id: int, user: CurrentUser) -> TechnicalReport:
    rep = await session.get(TechnicalReport, report_id)
    if not rep:
        raise not_found("Технический отчёт")
    if not user.deo_allowed(rep.deo):
        raise RuleError("Нет доступа к данным другого ДЭО", "ДЭО", 403)
    return rep


def _current(rep: TechnicalReport) -> TechnicalReportVersion | None:
    return next((v for v in rep.versions if v.version_no == rep.current_version), rep.versions[-1] if rep.versions else None)


async def _autolink(session, rep: TechnicalReport, parsed: dict):
    """Обновить ЕО отчёта по новой версии, сохранив прежние сопоставления; ЕО с ID АСУ ПП из БДО сопоставляются сразу."""
    prev = {e.xml_uid: e for e in rep.equipment} | {e.name: e for e in rep.equipment}
    codes = {e["asupp"] for e in parsed["equipment"] if e["asupp"]}
    by_code = {}
    if codes:
        by_code = {eo.code: eo.id for eo in (await session.execute(select(EquipmentUnit).where(EquipmentUnit.code.in_(codes)))).scalars()}
    new = []
    for e in parsed["equipment"]:
        old = prev.get(e["uid"]) or prev.get(e["name"])
        steel = parsed["steels"].get(e["steel"], {}).get("name", e["steel"])
        s_nom = f"{e['s_nom']} мм" if e["s_nom"] else (f"{e['s_calc']} мм (расч.)" if e["s_calc"] else "—")
        new.append(TechnicalReportEo(
            xml_uid=e["uid"], name=e["name"], eq_type=parsed["types"].get(e["type"], {}).get("name", e["type"]), steel=steel, s_nominal=s_nom,
            origin=e["origin"] or "imported", asupp_eo_id=e["asupp"], bdo_eo_id=old.bdo_eo_id if old and old.bdo_eo_id else by_code.get(e["asupp"]),
            repair_object=old.repair_object if old else False))
    rep.equipment = new


async def upload(session, data: bytes, filename: str, attachments: list[tuple[str, bytes]], user: CurrentUser, report_id: int | None = None) -> TechnicalReport:
    res = await check_xml(session, data)
    if not res["xsd_ok"]:
        raise RuleError("XML не проходит проверку по XSD v3.8 — отчёт не загружен. Исправьте файл в системе ГД.", "D-TO-06", fields={"issues": res["issues"]})
    p = res["parsed"]
    number = p["report"]["number"]
    rep = await get_report(session, report_id, user) if report_id else (await session.execute(select(TechnicalReport).where(TechnicalReport.number == number))).scalars().first()
    if report_id and rep.number != number:
        raise RuleError(f"Номер отчёта в XML ({number}) не совпадает с карточкой ({rep.number})", "D-TO-01")
    if rep:
        if rep.status not in UPLOADABLE:
            raise RuleError("Новая версия ТО загружается в статусах «Загружен» и «На доработке»", "D-TO-01")
        version_no = rep.current_version + 1
    else:
        deo = p["report"]["customer"] if re.fullmatch(r"ОРГ_\d+", p["report"]["customer"] or "") else (user.deo or "ОРГ_9")
        rep = TechnicalReport(number=number, deo=deo, source="ИУС ГД (XML v3.8)", status="Загружен", current_version=0, history=[], versions=[], equipment=[])
        session.add(rep)
        version_no = 1
    rep.report_date = parse_date(p["report"]["date"])
    rep.title, rep.profile = p["report"]["title"], p["report"]["profile"]
    rep.executor, rep.customer = p["report"]["executor"], p["report"]["customer"]
    rep.opo = p["report"]["opo"]
    rep.dict_snapshot = ", ".join(sorted(set(v.split(" ")[-1] for v in p["report"]["dict_versions"]))) or "—"
    await session.flush()
    fo = await save_file(session, data, filename or f"report_{rep.id}_v{version_no}.xml", "technical_report", rep.id, "xml", user, "application/xml")
    att_ids = [(await save_file(session, b, n, "technical_report", rep.id, "attachment", user)).id for n, b in attachments]
    rep.versions.append(TechnicalReportVersion(version_no=version_no, file_id=fo.id, file_name=fo.name, attachment_ids=att_ids, parsed=p,
                                               validation={"xsd_ok": True, "issues": res["issues"], "summary": res["summary"]},
                                               dict_snapshot=rep.dict_snapshot, uploaded_by=user.display))
    rep.current_version = version_no
    await _autolink(session, rep, p)
    blocks = res["summary"]["Block"]
    rep.status = "Загружен"
    rep.history.append(TechnicalReportHistory(username=user.display, status="Загружен",
                                              comment=f"Загружена версия v{version_no}" + (f": ошибок L1 — {blocks}" if blocks else ", ошибок L1 нет")))
    await audit(session, user, "report.upload", "technical_report", rep.id, version=version_no)
    return rep


def send_block_reason(rep: TechnicalReport) -> str:
    v = _current(rep)
    blocks = (v.validation.get("summary", {}).get("Block", 0) if v else 0)
    if blocks:
        return f"Есть {blocks} ошибки L1 (Block): исправьте их в системе ГД и загрузите новую версию"
    unmapped = [e for e in rep.equipment if not e.bdo_eo_id and not e.repair_object]
    if unmapped:
        return f"Сопоставьте {len(unmapped)} ЕО с БДО (D-TO-04)"
    ids = [e.bdo_eo_id for e in rep.equipment if e.bdo_eo_id]
    if len(ids) != len(set(ids)):
        return "Одна ЕО БДО выбрана для нескольких ЕО отчёта"
    return ""


async def set_mapping(session, rep: TechnicalReport, items: list[dict], user: CurrentUser):
    if rep.status not in UPLOADABLE:
        raise RuleError("Сопоставление доступно в статусах «Загружен» и «На доработке»", "D-TO-04")
    by_id = {e.id: e for e in rep.equipment}
    for it in items:
        e = by_id.get(it["id"])
        if not e:
            continue
        e.repair_object = bool(it.get("repairObject"))
        e.bdo_eo_id = None if e.repair_object else it.get("bdoEoId")
    await audit(session, user, "report.map", "technical_report", rep.id)


async def suggest_mapping(session, rep: TechnicalReport) -> int:
    """Предложить сопоставление по наименованию (первое значимое слово + совпадение заводского номера)."""
    eos = (await session.execute(select(EquipmentUnit).where(EquipmentUnit.deo == rep.deo))).scalars().all() if rep.deo else []
    taken = {e.bdo_eo_id for e in rep.equipment if e.bdo_eo_id}
    n = 0
    for e in rep.equipment:
        if e.bdo_eo_id or e.repair_object:
            continue
        key = re.split(r"[\s№-]+", e.name.lower())[0][:6]
        cand = next((x for x in eos if x.id not in taken and key and x.name.lower().startswith(key)), None)
        if cand:
            e.bdo_eo_id = cand.id
            taken.add(cand.id)
            n += 1
    return n


async def send_to_deo(session, rep: TechnicalReport, user: CurrentUser):
    if rep.status != "Загружен":
        raise RuleError("Отправить в ДЭО можно ТО в статусе «Загружен»", "OQ-10")
    reason = send_block_reason(rep)
    if reason:
        raise RuleError(f"Отправка недоступна: {reason}", "D-TO-04" if "Сопоставьте" in reason else "V-L1")
    rep.status = "На рассмотрении ДЭО"
    rep.history.append(TechnicalReportHistory(username=user.display, status=rep.status, comment="Отправлено в ДЭО"))
    await notify(session, "BDTS.OTVTECHOT", f"Технический отчёт {rep.number} поступил на рассмотрение ДЭО", rep.title, f"/reports/{rep.id}", deo=rep.deo)


async def decide(session, rep: TechnicalReport, decision: str, comment: str, user: CurrentUser):
    if rep.status not in ("На рассмотрении ДЭО", "На согласовании в ДЭО"):
        raise RuleError("Решение ДЭО вносится по ТО на рассмотрении", "OQ-10")
    comment = (comment or "").strip()
    if decision == "rework":
        if not comment:
            raise RuleError("При возврате на доработку комментарий обязателен", "R-B303-05", fields={"comment": "Укажите, что доработать"})
        rep.status = "На доработке"
        rep.history.append(TechnicalReportHistory(username=user.display, status=rep.status, comment=comment))
        await notify(session, "BDTS.TO_UPLOAD", f"ТО {rep.number} возвращён на доработку", comment, f"/reports/{rep.id}", type_="Предупреждение")
        return
    rep.status = "Завершено ДЭО"
    rep.history.append(TechnicalReportHistory(username=user.display, status=rep.status, comment=comment or "Принято без замечаний"))
    n = await explode(session, rep, user)
    await emit(session, "report.accepted", {"number": rep.number, "version": rep.current_version, "deo": rep.deo, "records": n,
                                            "summary": f"ТО {rep.number} v{rep.current_version}", "user": user.display}, key=f"report.accepted:{rep.id}:{rep.current_version}")
    await notify(session, "BDTS.TO_UPLOAD", f"ТО {rep.number} завершён ДЭО", f"Сформировано записей о ТС: {n}", f"/reports/{rep.id}")


async def explode(session, rep: TechnicalReport, user: CurrentUser) -> int:
    """1 ТО → N записей Б316 (memo п.5): по каждой сопоставленной ЕО — измерения протоколов и строки ведомости дефектов."""
    v = _current(rep)
    p = v.parsed if v else {}
    concl = (p.get("conclusions") or [{}])[0]
    year = date.today().year
    n = 0
    for e in rep.equipment:
        if not e.bdo_eo_id:
            continue
        eo = await session.get(EquipmentUnit, e.bdo_eo_id)
        number = await next_number(session, TsRecord, TsRecord.number, f"Б316-{year}-")
        rec = TsRecord(number=number, record_type="Диагностическое обследование", tm_id=eo.tm_id, eo_id=eo.id, deo=rep.deo or eo.deo,
                       reg_date=rep.report_date or date.today(), object_status=STATE_RU.get(concl.get("state", ""), ""),
                       description=(concl.get("text") or "")[:500], confirm_status="Требует подтверждения", source="report", report_id=rep.id,
                       notes=f"Раскладка ТО {rep.number} v{rep.current_version}",
                       do_report={"pp": rep.pp_line, "executor": rep.executor, "vid": PROFILE_RU.get(rep.profile, rep.profile), "toNumber": rep.number,
                                  "toDate": fmt_date(rep.report_date), "deoDate": fmt_date(date.today()),
                                  "ops": ", ".join(sorted({p["methods"].get(pr["method"], pr["method"]) for pr in p.get("protocols", [])}))})
        session.add(rec)
        await session.flush()
        for pr in p.get("protocols", []):
            for row in pr["rows"]:
                if row["eo"] != e.xml_uid:
                    continue
                for m in row["measurements"]:
                    try:
                        val = float(m["value"])
                    except (TypeError, ValueError):
                        val = None
                    session.add(TsMeasurement(record_id=rec.id, control_point=f"{e.name}, {m['label']}", value_num=val,
                                              unit="мм" if pr["kind"] == "uzt_data" else "HB" if pr["kind"] == "hardness_data" else "",
                                              position=m["label"], method=p["methods"].get(pr["method"], pr["method"]), instrument="Толщиномер ультразвуковой А1207",
                                              expert=(p.get("signatures") or [{}])[0].get("name", "")))
                for d in row["defects"]:
                    session.add(TsMessage(record_id=rec.id, journal_no=pr["number"], journal_date=rep.report_date, author=rep.executor,
                                          kind="Результат ВИК", description=d, criticality="Средняя"))
        for s in p.get("statements", []):
            for it in s["items"]:
                if it["eo"] == e.xml_uid:
                    session.add(TsMessage(record_id=rec.id, journal_no=f"{s['number']}/{it['no']}", journal_date=parse_date(s["date"]), author=rep.executor,
                                          kind="Ведомость дефектов", description=it["text"], defect_code=it["category"],
                                          criticality="Высокая" if it["adm"] in ("not_fit", "not_corresponds") else "Средняя"))
        n += 1
    if n:
        await notify(session, "BDTS.OTVTS", f"По ТО {rep.number} сформировано {n} записей о ТС, требуется подтверждение", rep.title, "/ts-records",
                     type_="Предупреждение", deo=rep.deo, rule_id=11)
    return n


async def register_hs_report(session, ctx, user: CurrentUser):
    """ТО хозспособа: при отправке результата ДО на согласование регистрируется ТО в реестре (источник «Хозспособ»).
    Файл версии — .docx; содержимое и проверка — по XML v3.8, сформированному из тех же данных (карточка ТО, раскладка в Б316)."""
    from app.services.report_xml import eo_uid, render_result_xml

    t, r = ctx.task, ctx.r
    _, _, res = await render_result_xml(session, ctx, check=False)
    validation = {k: res[k] for k in ("xsd_ok", "issues", "summary")}
    rep = (await session.execute(select(TechnicalReport).where(TechnicalReport.result_id == r.id))).scalars().first()
    if not rep:
        rep = TechnicalReport(number=f"ТО-ХС-{date.today().year}-{t.deo.replace('_', '')}-{t.id:05d}", report_date=date.today(),
                              title=f"{t.eo_name} (хозспособ)", profile={"tpa": "to_tpa", "vessel": "to_vessel", "wellhead": "to_wellhead", "grs": "to_grs"}.get(t.vid, ""),
                              executor=f"Служба диагностики {t.deo} (хозспособ)", customer=t.deo, deo=t.deo, source="Хозспособ",
                              pp_line=f"График ДЭО, задание № {t.id}", status="На согласовании в ДЭО", current_version=1, result_id=r.id,
                              dict_snapshot="v3.8.14", history=[], versions=[], equipment=[])
        session.add(rep)
        rep.versions.append(TechnicalReportVersion(version_no=1, file_id=r.to_file_id, file_name=f"ТО_{t.id}.docx", parsed=res["parsed"], validation=validation,
                                                   dict_snapshot="v3.8.14", uploaded_by=user.display))
        rep.equipment = [TechnicalReportEo(xml_uid=eo_uid(r, e), name=e.label, origin="field_created" if not e.eo_id else "asupp", bdo_eo_id=e.eo_id) for e in r.eos]
    elif (v := _current(rep)) is not None:  # повторная отправка после корректировки — содержимое по актуальным данным
        v.parsed, v.validation = res["parsed"], validation
    rep.status = "На согласовании в ДЭО"
    rep.history.append(TechnicalReportHistory(username=user.display, status=rep.status, comment="ТО хозспособа сформирован и направлен на согласование"))
    await emit(session, "report.hs_sent", {"number": rep.number, "summary": f"ТО {rep.number}", "user": user.display}, key=f"report.hs:{r.id}:{r.version}")


async def payload(session, rep: TechnicalReport, user: CurrentUser) -> dict:
    v = _current(rep)
    files = {}
    ids = [x.file_id for x in rep.versions if x.file_id] + [a for x in rep.versions for a in (x.attachment_ids or [])]
    if ids:
        files = {f.id: f for f in (await session.execute(select(FileObject).where(FileObject.id.in_(ids)))).scalars()}
    bdo = {}
    bdo_ids = [e.bdo_eo_id for e in rep.equipment if e.bdo_eo_id]
    if bdo_ids:
        bdo = {x.id: x for x in (await session.execute(select(EquipmentUnit).where(EquipmentUnit.id.in_(bdo_ids)))).scalars()}
    p = v.parsed if v else {}
    reason = send_block_reason(rep)
    can_upload = user.can("to.upload") and rep.status in UPLOADABLE and rep.source != "Хозспособ"
    return {
        **report_row(rep), "opo": rep.opo, "dictSnapshot": rep.dict_snapshot,
        "validation": v.validation if v else {}, "parsed": p,
        "versions": [{"version": x.version_no, "file": x.file_name, "fileId": x.file_id, "snapshot": x.dict_snapshot, "by": x.uploaded_by,
                      "at": x.uploaded_at.isoformat() if x.uploaded_at else "", "blocks": x.validation.get("summary", {}).get("Block", 0),
                      "attachments": [{"id": a, "name": files[a].name} for a in (x.attachment_ids or []) if a in files]} for x in reversed(rep.versions)],
        "equipment": [{"id": e.id, "name": e.name, "type": e.eq_type, "steel": e.steel, "sNom": e.s_nominal, "origin": e.origin, "asupp": e.asupp_eo_id,
                       "bdoEoId": e.bdo_eo_id, "bdoLabel": f"{bdo[e.bdo_eo_id].code} · {bdo[e.bdo_eo_id].name}" if e.bdo_eo_id in bdo else "",
                       "repairObject": e.repair_object} for e in rep.equipment],
        "history": [{"date": h.at.isoformat(), "user": h.username, "status": h.status, "comment": h.comment} for h in rep.history],
        "records": [{"id": r.id, "number": r.number} for r in (await session.execute(select(TsRecord).where(TsRecord.report_id == rep.id))).scalars()],
        "can": {"upload": can_upload, "map": user.can("to.map") and rep.status in UPLOADABLE,
                "send": user.can("to.send") and rep.status == "Загружен", "decide": user.can("to.decide") and rep.status in ("На рассмотрении ДЭО", "На согласовании в ДЭО")},
        "sendBlockReason": reason,
    }


def report_row(rep: TechnicalReport) -> dict:
    unmapped = sum(1 for e in rep.equipment if not e.bdo_eo_id and not e.repair_object)
    return {"id": rep.id, "number": rep.number, "date": rep.report_date.isoformat() if rep.report_date else "", "title": rep.title,
            "profile": rep.profile, "profileName": PROFILE_RU.get(rep.profile, rep.profile), "executor": rep.executor, "customer": rep.customer,
            "deo": rep.deo, "eoCount": len(rep.equipment), "unmappedCount": unmapped, "ppLine": rep.pp_line, "source": rep.source,
            "status": rep.status, "version": f"v{rep.current_version}", "resultId": rep.result_id}
