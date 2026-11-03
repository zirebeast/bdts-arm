"""НСИ Б304–Б315 (п. 4.4.18–4.4.26 ТПР): схемы справочников, правила R-NSI-01 (обязательность), R-NSI-02 (пометка на удаление)."""
from sqlalchemy import func, select

from app.errors import RuleError, not_found
from app.models import NsiRecord
from app.permissions import CurrentUser
from app.services.common import audit


def F(key, label, req=True, auto=False, type_="text", ref=None):
    return {"key": key, "label": label, "req": req, "auto": auto, "type": type_, "ref": ref}


CATALOGS = {
    "B306": {"screen": "W-5.1", "title": "Эксперты ДО", "notes": True, "fields": [
        F("fio", "ФИО"), F("cert", "Номер удостоверения"), F("area", "Область аттестации"), F("valid", "Срок действия удостоверения", type_="date"),
        F("permit", "Допуск", ref="B304"), F("org", "Организация-исполнитель")]},
    "B304": {"screen": "W-5.2", "title": "Допуски", "notes": True, "fields": [F("no", "№ допуска"), F("date", "Дата допуска", type_="date"), F("issuer", "Выдал")]},
    "B305": {"screen": "W-5.3", "title": "Сертификаты", "notes": True, "fields": [F("no", "№ сертификата"), F("valid", "Дата действия", type_="date"), F("issuer", "Выдал")]},
    "B314": {"screen": "W-5.4", "title": "Инструменты", "notes": True, "fields": [
        F("name", "Наименование"), F("serial", "Заводской номер", req=False), F("cert", "№ Свидетельства/ Сертификата", req=False, ref="B305")]},
    "B311": {"screen": "W-5.5", "title": "Каталоги сообщений", "notes": True, "fields": [F("name", "Наименование")]},
    "B312": {"screen": "W-5.6", "title": "Коды сообщений", "notes": True, "fields": [
        F("name", "Наименование"), F("code", "Код дефекта"), F("parent", "Вышестоящий код", req=False), F("catalog", "Каталог", ref="B311")]},
    "B309": {"screen": "W-5.7", "title": "Параметры контроля", "notes": False, "fields": [
        F("name", "Наименование"), F("dtype", "Тип данных", type_="select"), F("min", "Минимальное значение", type_="num"),
        F("max", "Максимальное значение", type_="num"), F("unit", "Единица измерения")]},
    "B310": {"screen": "W-5.8", "title": "Точки контроля", "notes": True, "fields": [
        F("name", "Наименование"), F("param", "Параметр контроля", ref="B309"), F("tm", "Техническое место", auto=True), F("eo", "Единица оборудования"),
        F("pos", "Номер позиции", req=False), F("area", "Область/Место", req=False)]},
    "B315": {"screen": "W-5.9", "title": "Методы контроля", "notes": False, "fields": [F("name", "Наименование"), F("vid", "Вид ДО", type_="select")]},
}
SELECT_OPTIONS = {
    ("B309", "dtype"): ["Числовой", "Целый", "Строка", "Справочное значение", "Дата"],
    ("B315", "vid"): ["Обследование сосудов и аппаратов", "Обследование трубопроводной арматуры", "Обследование фонтанной арматуры и колонной головки",
                      "Комплексное диагностическое обследование газораспределительной станции", "Внутритрубная диагностика линейной части магистральных трубопроводов и подводных переходов"],
}


def catalog(code: str) -> dict:
    c = CATALOGS.get(code)
    if not c:
        raise not_found("Справочник")
    return c


def row(r: NsiRecord) -> dict:
    return {"id": r.id, "recordNo": r.record_no, "data": r.data, "recordStatus": r.record_status, "notes": r.notes,
            "createdAt": r.created_at.date().isoformat() if r.created_at else "", "updatedAt": r.updated_at.date().isoformat() if r.updated_at else "",
            "updatedBy": r.updated_by}


def validate(code: str, data: dict) -> dict:
    c = catalog(code)
    errs = {f["key"]: "Обязательное поле" for f in c["fields"] if f["req"] and not f["auto"] and not str(data.get(f["key"]) or "").strip()}
    if code == "B309" and not errs:
        try:
            if float(str(data["min"]).replace(",", ".")) > float(str(data["max"]).replace(",", ".")):
                errs["max"] = "Максимальное значение меньше минимального"
        except ValueError:
            errs["min"] = "Введите число"
    return errs


async def save(session, code: str, data: dict, notes: str, user: CurrentUser, rec_id: int | None = None) -> NsiRecord:
    errs = validate(code, data)
    if errs:
        raise RuleError("Заполните обязательные поля записи справочника", "R-NSI-01", fields=errs)
    if rec_id:
        r = await session.get(NsiRecord, rec_id)
        if not r or r.catalog != code:
            raise not_found("Запись справочника")
    else:
        mx = (await session.execute(select(func.max(NsiRecord.record_no)).where(NsiRecord.catalog == code))).scalar() or 0
        r = NsiRecord(catalog=code, record_no=mx + 1 if mx else 1001)
        session.add(r)
    keep = {k: v for k, v in (r.data or {}).items() if any(f["key"] == k and f["auto"] for f in catalog(code)["fields"])}
    r.data = {**data, **keep}
    r.notes, r.updated_by = notes or "", user.fio
    await session.flush()
    await audit(session, user, "nsi.save", code, r.id)
    return r


async def mark_deleted(session, code: str, rec_id: int, user: CurrentUser):
    r = await session.get(NsiRecord, rec_id)
    if not r or r.catalog != code:
        raise not_found("Запись справочника")
    r.record_status = "Помечено на удаление"
    await audit(session, user, "nsi.mark_deleted", code, r.id)
    return r
