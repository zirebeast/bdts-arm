"""Технический отчёт по результатам ДО (.docx), формируется «на лету» из данных результата ДО.

Структура — по Р Заказчик «Исполнительная документация при диагностическом обследовании»:
п. 7.1.4 (вводная часть а)–п) + протоколы НК в приложениях), п. 7.1.5 (срок следующего ДО в выводах),
п. 7.1.7 (утверждение представителем СО — гриф «УТВЕРЖДАЮ»), п. 7.1.9 (последний лист — лист согласования),
типовая форма Приложения В.1 (15 разделов, приложения-протоколы, перечень НТД).
"""
import io
import re
from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor
from sqlalchemy import select

from app.models import Brigade, EquipmentUnit, NsiRecord, Organization, TechPlace, TsRecord
from app.permissions import ROLES
from app.seed.templates import VID_NAME, VID_SHORT
from app.services.common import fmt_date, parse_date
from app.services.sections import sec_tol_list

RANK = {"empty": 0, "ok": 1, "borderline": 2, "exceeded": 3}
TOL_RU = {"ok": "Годен", "borderline": "На границе допуска", "exceeded": "Не годен", "empty": "—"}

# Тип технического устройства на титульном листе (форма В.1: «техническое устройство — …»)
DEVICE = {"vessel": "сосуд, работающий под давлением", "tpa": "трубопроводная арматура", "wellhead": "фонтанная арматура и колонная головка",
          "grs": "оборудование газораспределительной станции"}

# Раздел 3: НПА, устанавливающие требования к объекту диагностики
NPA = {
    "common": ["Федеральный закон от 21.07.1997 № 116-ФЗ «О промышленной безопасности опасных производственных объектов»"],
    "vessel": ["ФНП в области промышленной безопасности «Правила промышленной безопасности при использовании оборудования, работающего под избыточным давлением», "
               "утв. приказом Ростехнадзора от 15.12.2020 № 536",
               "ГОСТ 34233.1-2017 «Сосуды и аппараты. Нормы и методы расчета на прочность. Общие требования»",
               "СТО Заказчик 2-2.3-491-2010 «Техническое диагностирование сосудов, работающих под давлением на объектах Заказчика»"],
    "tpa": ["ФНП «Правила безопасности для опасных производственных объектов магистральных трубопроводов», утв. приказом Ростехнадзора от 11.12.2020 № 517",
            "ГОСТ 33257-2015 «Арматура трубопроводная. Методы контроля и испытаний»",
            "ГОСТ 9544-2015 «Арматура трубопроводная. Нормы герметичности затворов»"],
    "wellhead": ["ФНП «Правила безопасности в нефтяной и газовой промышленности», утв. приказом Ростехнадзора от 15.12.2020 № 534",
                 "ГОСТ 13846-89 «Арматура фонтанная и нагнетательная. Типовые схемы, основные параметры и технические требования к конструкции»",
                 "ГОСТ Р 51365-2009 «Нефтяная и газовая промышленность. Оборудование для бурения и добычи. Оборудование устья скважины и фонтанное устьевое оборудование»"],
    "grs": ["ФНП «Правила безопасности сетей газораспределения и газопотребления», утв. приказом Ростехнадзора от 15.12.2020 № 531",
            "ФНП «Правила безопасности для опасных производственных объектов магистральных трубопроводов», утв. приказом Ростехнадзора от 11.12.2020 № 517",
            "ГОСТ 32569-2013 «Трубопроводы технологические стальные. Требования к устройству и эксплуатации на взрывопожароопасных и химически опасных производствах»"],
}

# Метод (код раздела шаблона) → наименование работы (табл. 7, 10), наименование протокола, НТД метода, параметры контроля
METHOD = {
    "doc": ("Анализ технической документации", "Протокол анализа технической документации", [], []),
    "functional": ("Функциональная (оперативная) диагностика", "Протокол по результатам оперативной (функциональной) диагностики",
                   ["ГОСТ 9544-2015 «Арматура трубопроводная. Нормы герметичности затворов»"],
                   [("Режим", "Рабочий режим эксплуатации"), ("Контролируемые параметры", "Давление, температура, вибрация, состояние КИП, СА и ПАЗ")]),
    "operability": ("Проверка работоспособности запорных устройств", "Протокол проверки работоспособности запорных устройств",
                    ["ГОСТ 13846-89 «Арматура фонтанная и нагнетательная. Типовые схемы, основные параметры и технические требования к конструкции»"],
                    [("Способ проверки", "Открытие-закрытие с контролем хода шпинделя и герметичности")]),
    "vik": ("Визуальный и измерительный контроль", "Протокол по результатам визуального и измерительного контроля",
            ["РД 03-606-03 «Инструкция по визуальному и измерительному контролю»",
             "ГОСТ Р ИСО 17637-2014 «Контроль неразрушающий. Визуальный контроль соединений, выполненных сваркой плавлением»"],
            [("Освещённость контролируемых поверхностей", "не менее 500 лк"), ("Шероховатость зачищенных поверхностей", "Ra ≤ 12,5 мкм")]),
    "uzt": ("Ультразвуковая толщинометрия", "Протокол по результатам ультразвуковой толщинометрии",
            ["ГОСТ Р ИСО 16809-2015 «Контроль неразрушающий. Контроль ультразвуковой. Измерение толщины»",
             "ГОСТ Р 55614-2013 «Контроль неразрушающий. Толщиномеры ультразвуковые. Общие технические требования»"],
            [("Тип преобразователя", "Раздельно-совмещённый, 5 МГц"), ("Диапазон измерений", "0,8–300 мм"), ("Пределы допускаемой погрешности", "±(0,01·H + 0,1) мм"),
             ("Подготовка поверхности", "Зачистка до металлического блеска, Ra ≤ 6,3 мкм")]),
    "uzk_metal": ("Ультразвуковой контроль основного металла", "Протокол по результатам ультразвукового контроля основного металла",
                  ["ГОСТ Р 55724-2013 «Контроль неразрушающий. Соединения сварные. Методы ультразвуковые»"],
                  [("Схема прозвучивания", "Эхо-метод, совмещённая схема"), ("Частота", "2,5–5 МГц"), ("Контактная среда", "Гель ультразвуковой")]),
    "uzk_weld": ("Ультразвуковой контроль качества сварных соединений", "Протокол по результатам ультразвукового контроля качества сварных соединений",
                 ["ГОСТ Р 55724-2013 «Контроль неразрушающий. Соединения сварные. Методы ультразвуковые»"],
                 [("Тип ПЭП", "Наклонный, 2,5–5 МГц, угол ввода 65°/70°"), ("Уровень фиксации", "Контрольный по СОП"), ("Контактная среда", "Гель ультразвуковой")]),
    "hardness": ("Контроль твёрдости основного металла и сварных соединений", "Протокол по результатам контроля твёрдости основного металла и сварных соединений",
                 ["ГОСТ 22761-77 «Металлы и сплавы. Метод измерения твердости по Бринеллю переносными твердомерами статического действия»",
                  "ГОСТ 23677-79 «Твердомеры для металлов. Общие технические требования»"],
                 [("Шкала", "Бринелль, HB"), ("Число измерений в точке", "не менее 3, результат — среднее значение")]),
    "mpk": ("Магнитопорошковый контроль", "Протокол по результатам магнитопорошкового контроля",
            ["ГОСТ Р 56512-2015 «Контроль неразрушающий. Магнитопорошковый метод. Типовые технологические процессы»"],
            [("Индикатор", "Суспензия чёрного магнитного порошка"), ("Уровень чувствительности", "Б по ГОСТ Р 56512-2015")]),
    "pvk": ("Капиллярный контроль", "Протокол по результатам капиллярного контроля",
            ["ГОСТ 18442-80 «Контроль неразрушающий. Капиллярные методы. Общие требования»"],
            [("Метод", "Цветной"), ("Класс чувствительности", "II по ГОСТ 18442-80")]),
    "spectral": ("Спектральный анализ химического состава металла", "Протокол спектрального анализа химического состава металла",
                 ["ГОСТ 18895-97 «Сталь. Метод фотоэлектрического спектрального анализа»",
                  "ГОСТ 19281-2014 «Прокат повышенной прочности. Общие технические условия»"],
                 [("Метод", "Оптико-эмиссионный спектральный анализ")]),
    "eddy": ("Вихретоковый контроль резьб и шпилек", "Протокол по результатам вихретокового контроля",
             ["ГОСТ Р ИСО 15549-2009 «Контроль неразрушающий. Вихретоковый контроль. Основные положения»"],
             [("Тип преобразователя", "Накладной, абсолютный")]),
    "vibro": ("Вибродиагностика технологических трубопроводов", "Протокол по результатам вибродиагностики",
              ["ГОСТ ИСО 10816-3-2002 «Вибрация. Контроль состояния машин по результатам измерений вибрации на невращающихся частях»"],
              [("Измеряемый параметр", "СКЗ виброскорости в диапазоне 10–1000 Гц"), ("Пороги оценки", "4,5 / 7,1 мм/с")]),
    "ecp": ("Контроль электрохимической защиты и изоляционного покрытия", "Протокол электрометрических измерений",
            ["ГОСТ Р 51164-98 «Трубопроводы стальные магистральные. Общие требования к защите от коррозии»",
             "ГОСТ 9.602-2016 «Единая система защиты от коррозии и старения. Сооружения подземные. Общие требования к защите от коррозии»"],
            [("Критерий защищённости", "Защитный потенциал от −0,85 до −1,15 В (м.с.э.)")]),
    "bending": ("Контроль изгибных деформаций трубопроводов (нивелирование)", "Протокол геодезического контроля планово-высотного положения трубопроводов",
                ["СП 126.13330.2017 «Геодезические работы в строительстве»"], [("Допускаемое отклонение", "20 мм (предупреждение), 30 мм (недопустимо)")]),
    "acoustic": ("Контроль герметичности ТПА акустическим методом", "Протокол контроля герметичности затворов ТПА",
                 ["ГОСТ 9544-2015 «Арматура трубопроводная. Нормы герметичности затворов»"], [("Способ", "Регистрация акустического сигнала утечки на затворе")]),
}
# НТД метода, зависящая от вида ДО (форма В.1, приложение 2 — для сосудов)
VID_NTD = {("functional", "vessel"): ["ФНП «Правила промышленной безопасности при использовании оборудования, работающего под избыточным давлением», "
                                      "утв. приказом Ростехнадзора от 15.12.2020 № 536",
                                      "СТО Заказчик 2-2.3-491-2010 «Техническое диагностирование сосудов, работающих под давлением на объектах Заказчика»"]}
TK_CODE = {"doc": "АТД", "functional": "ФД", "operability": "ПР", "vik": "ВИК", "uzt": "УЗТ", "uzk_metal": "УЗК", "uzk_weld": "УЗК-СС", "hardness": "ТВ",
           "mpk": "МПК", "pvk": "ПВК", "spectral": "СА", "eddy": "ВТК", "vibro": "ВД", "ecp": "ЭХЗ", "bending": "ГК", "acoustic": "АК"}
TK_VID = {"vessel": "СД", "tpa": "ТПА", "wellhead": "ФА", "grs": "ГРС"}


def _method_ntd(code: str, vid: str) -> list[str]:
    return VID_NTD.get((code, vid)) or METHOD.get(code, ("", "", [], []))[2]


def _tk(code: str, vid: str) -> str:
    return f"ТК-{TK_CODE.get(code, code.upper())}-{TK_VID.get(vid, vid.upper())}-01"


# Табл. 8 (раздел 11) — фиксированный перечень формы В.1 дополняется документами, указанными в разделе «Анализ технической документации»
DOC_FORM = ["Лицензия на осуществление деятельности", "Свидетельство о регистрации опасных производственных объектов",
            "Договор обязательного страхования гражданской ответственности", "Положение о производственном контроле",
            "План мероприятий по локализации и ликвидации последствий аварий", "Журнал учета аварий и инцидентов"]
STAGES_SIGN = [  # лист согласования: этап → статус результата в истории, в котором этап завершён
    ("Полевой этап выполнил", "Требуется КП"), ("Камеральную проверку выполнил, отчёт сформировал", "На согласовании"),
    ("Технический отчёт согласовал", "На рассмотрении ДЭО"), ("Технический отчёт рассмотрел и принял (ДЭО)", "Принят ДЭО"),
    ("Результат ДО завершил", "Результат получен"),
]


# ---------- сбор данных ----------
class Info:
    """Данные для отчёта, которые не входят в результат ДО: реквизиты организаций, бригада, ЕО, поверка СИ, история ТС."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _attr_v(attrs: list, code: str, default: str = "—") -> str:
    return next((str(a[2]) for a in attrs or [] if a and a[0] == code), default)


def _passport(eo: EquipmentUnit | None, label: str) -> str:
    return next((v for k, v in (eo.passport if eo else []) or [] if k.startswith(label)), "")


async def collect(session, ctx) -> Info:
    t = ctx.task
    orgs = {o.code: o for o in (await session.execute(select(Organization))).scalars()}
    customer = orgs.get(t.deo)
    executor = customer if t.is_hs else orgs.get("ОРГ_1")
    brigade = (await session.execute(select(Brigade).where(Brigade.name == t.brigade))).scalars().first()
    ids = [e.eo_id for e in ctx.r.eos if e.eo_id] + ([t.eo_id] if t.eo_id else [])
    eos = {e.id: e for e in (await session.execute(select(EquipmentUnit).where(EquipmentUnit.id.in_(ids or [-1])))).scalars()}
    tms = {x.id: x for x in (await session.execute(select(TechPlace))).scalars()}
    instruments = {n.data.get("name", ""): n.data for n in (await session.execute(select(NsiRecord).where(NsiRecord.catalog == "B314"))).scalars()}
    prev = (await session.execute(select(TsRecord).where(TsRecord.eo_id.in_(ids or [-1]), TsRecord.record_type == "Диагностическое обследование",
                                                         (TsRecord.result_id.is_(None)) | (TsRecord.result_id != ctx.r.id)).order_by(TsRecord.reg_date.desc()))).scalars().all()
    return Info(customer=customer, executor=executor, members=(brigade.members if brigade else []) or [], eos=eos, tms=tms, instruments=instruments, prev=prev)


def _tm_attrs(info: Info, eo: EquipmentUnit | None) -> list:
    """Атрибуты ТМ с наследованием от родительских ТМ (сведения об ОПО задаются на корневом ТМ)."""
    out, tm = [], info.tms.get(eo.tm_id) if eo else None
    while tm:
        out += [a for a in tm.attrs or [] if not any(a[0] == b[0] for b in out)]
        tm = info.tms.get(tm.parent_id) if tm.parent_id else None
    return out


def _hist_at(ctx, status: str):
    h = [x for x in ctx.r.history if x.status == status]
    return h[-1] if h else None


def report_no(ctx) -> tuple[str, date]:
    """Номер и дата ТО — общие для .docx и .xml: дата формирования (передача на согласование) или сегодня."""
    formed = _hist_at(ctx, "На согласовании")
    rep_date = formed.at.date() if formed else date.today()
    return f"ТО-{rep_date.year}-{ctx.task.id:03d}", rep_date


def _fio(username: str) -> tuple[str, str]:
    """«ФИО_4 (BDTS.KAMER)» → («ФИО_4», «БДТС. Ответственный за камеральную проверку»)."""
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", username or "")
    if not m:
        return username, ""
    role = "; ".join(ROLES.get(x.strip(), {}).get("label", x.strip()) for x in m.group(2).split(","))
    return m.group(1), role


# ---------- оформление ----------
def _no_theme_fonts(style, name="Times New Roman"):
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if fonts.get(qn(a)) is not None:
            del fonts.attrib[qn(a)]
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(a), name)


def _setup(doc: Document):
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Mm(297), Mm(210)
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Mm(30), Mm(15), Mm(20), Mm(20)
    st = doc.styles["Normal"]
    _no_theme_fonts(st)
    st.font.size = Pt(12)
    pf = st.paragraph_format
    pf.space_after, pf.space_before, pf.line_spacing = Pt(3), Pt(0), 1.1
    for name, size in (("Heading 1", 13), ("Heading 2", 12), ("Title", 16)):
        s = doc.styles[name]
        _no_theme_fonts(s)
        s.font.size, s.font.bold, s.font.color.rgb = Pt(size), True, RGBColor(0, 0, 0)
        s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(10 if name != "Title" else 0), Pt(6)
        s.paragraph_format.keep_with_next = True


def _p(doc, text="", bold=False, align=None, size=None, italic=False, indent=None, space_after=None, first_line=None):
    p = _new_page_hook(doc.add_paragraph())
    if text:
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        if size:
            r.font.size = Pt(size)
    if align:
        p.alignment = align
    if indent is not None:
        p.paragraph_format.left_indent = Cm(indent)
    if first_line is not None:
        p.paragraph_format.first_line_indent = Cm(first_line)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def _h(doc, text, level):
    return _new_page_hook(doc.add_heading(text, level))


def _para(doc, text):
    """Абзац основного текста: выравнивание по ширине, отступ первой строки 1,25 см."""
    return _p(doc, text, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_line=1.25)


def _caption(doc, text):
    return _p(doc, text, align=WD_ALIGN_PARAGRAPH.RIGHT, size=11, space_after=2)


def _shade(cell, fill="E7E9EC"):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def _repeat_header(row):
    trpr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trpr.append(el)


def _cell_text(cell, text, bold=False, size=10, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.first_line_indent = Cm(0)
    lines = str("" if text is None else text).split("\n")
    for i, line in enumerate(lines):
        r = p.add_run(line)
        r.bold, r.font.size = bold, Pt(size)
        if i < len(lines) - 1:
            r.add_break()
    if align:
        p.alignment = align


def _table(doc, header: list[str] | None, rows: list[list], widths: list[float] | None = None, size=10, kv=False):
    """Таблица с повторяющейся шапкой; kv=True — двухколоночная «параметр: значение» (первый столбец затенён)."""
    cols = len(header) if header else max(len(r) for r in rows)
    t = doc.add_table(rows=0, cols=cols)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    if header:
        cells = t.add_row().cells
        _repeat_header(t.rows[0])
        for i, h in enumerate(header):
            _cell_text(cells[i], h, bold=True, size=size, align=WD_ALIGN_PARAGRAPH.CENTER)
            _shade(cells[i])
    for row in rows:
        cells = t.add_row().cells
        if len(row) == 1 and cols > 1:  # строка-подзаголовок на всю ширину
            m = cells[0].merge(cells[-1])
            _cell_text(m, row[0], bold=True, size=size)
            _shade(m, "F3F4F6")
            continue
        for i, v in enumerate(row[:cols]):
            _cell_text(cells[i], v, size=size, bold=kv and i == 0)
            if kv and i == 0:
                _shade(cells[i], "F3F4F6")
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths[: len(row.cells)]):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def _field(run, instr: str):
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "1"), ("end", None)):
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            run._r.append(fc)
        elif text == instr:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = f" {instr} "
            run._r.append(it)
        else:
            tx = OxmlElement("w:t")
            tx.text = text
            run._r.append(tx)


def _header_footer(doc, header_text: str):
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = hp.add_run(header_text)
    r.font.size, r.italic = Pt(9), True
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for part in ("Стр. ", "PAGE", " из ", "NUMPAGES"):
        run = fp.add_run()
        run.font.size = Pt(9)
        if part in ("PAGE", "NUMPAGES"):
            _field(run, part)
        else:
            run.text = part


_NEW_PAGE: set[int] = set()  # документы (по id DocumentPart), у которых следующий абзац начинается с новой страницы


def _page_break(doc):
    """Следующий абзац — с новой страницы (page_break_before вместо разрыва: не даёт пустых страниц после полной страницы)."""
    _NEW_PAGE.add(id(doc.part))


def _new_page_hook(p):
    if id(p.part) in _NEW_PAGE:
        p.paragraph_format.page_break_before = True
        _NEW_PAGE.discard(id(p.part))
    return p


def _sign_block(doc, rows: list[tuple[str, str, str]]):
    """Подписи: роль | ____ | ФИО и квалификация (без рамок)."""
    t = doc.add_table(rows=0, cols=3)
    t.autofit = False
    for role, line, who in rows:
        c = t.add_row().cells
        _cell_text(c[0], role, size=11)
        _cell_text(c[1], line, size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(c[2], who, size=11)
    for row in t.rows:
        for i, w in enumerate((5.5, 4.0, 6.5)):
            row.cells[i].width = Cm(w)
    doc.add_paragraph()


# ---------- вычисления по разделам ----------
def _worst(tols: list[str]) -> str:
    return max(tols, key=lambda x: RANK.get(x, 0)) if tols else "empty"


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _f(v, d=1) -> str:
    x = _num(v)
    return "—" if x is None else f"{x:.{d}f}".replace(".", ",")


def _volume(sec: dict, d: dict) -> str:
    if d.get("np"):
        return "Не проводился"
    k = sec["kind"]
    if k == "points":
        n = sum(1 for el in d.get("elements", []) for p in el.get("points", []) if str(p.get("value") or "").strip())
        return f"{n} точ. на {len(d.get('elements', []))} элем."
    if k == "checklist":
        return f"{len(sec['items'])} категорий осмотра, 100 %"
    if k == "table":
        if sec["code"] == "doc":
            return f"{len(d.get('rows', []))} документов"
        return f"{len(d.get('rows', []))} зон / участков"
    return "В объёме программы"


def _summary(sec: dict, d: dict) -> str:
    if d.get("np"):
        return f"Не проводился. Причина: {d.get('reason') or 'не указана'}"
    tols = sec_tol_list(sec, d)
    ex, bl = tols.count("exceeded"), tols.count("borderline")
    if sec["code"] == "doc":
        miss = sum(1 for r in d.get("rows", []) if r.get("st") == "Не предоставлен")
        res = d.get("values", {}).get("res") or "Документация рассмотрена"
        return res + (f"; не предоставлено документов: {miss}" if miss else "")
    if ex:
        return f"Выявлены недопустимые отклонения ({ex})"
    if bl:
        return f"Недопустимых дефектов не выявлено; отклонения на границе допуска ({bl}) — по протоколу"
    return "Недопустимых дефектов не выявлено, требования НТД выполняются"


def _deviations(ctx) -> list[list]:
    """Ведомость выявленных дефектов и несоответствий: всё, что вне допуска или на границе."""
    out = []
    for i, reo in enumerate(ctx.r.eos):
        for s in ctx.sections:
            if s["kind"] == "info":
                continue
            d = ctx.data(i, s)
            if d.get("np"):
                continue
            title = METHOD.get(s["code"], (s["title"],))[0]
            if s["kind"] == "checklist":
                for code, name, op in s["items"]:
                    idx = d.get("items", {}).get(code, -1)
                    if isinstance(idx, int) and 0 <= idx < len(op) and op[idx][1] in ("borderline", "exceeded"):
                        out.append([reo.label, title, f"{name}: {op[idx][0]}" + (f". {d['notes'][code]}" if d.get("notes", {}).get(code) else ""), TOL_RU[op[idx][1]]])
            elif s["kind"] == "points":
                tols = sec_tol_list(s, d)
                k = 0
                for el in d.get("elements", []):
                    for p in el.get("points", []):
                        tl = tols[k] if k < len(tols) else "empty"
                        k += 1
                        if tl in ("borderline", "exceeded"):
                            unit = "мм" if s["mode"] == "thk" else "HB"
                            out.append([reo.label, title, f"{el['name']}, точка {p['label']}: {_f(p.get('value'), 1 if unit == 'HB' else 2)} {unit}", TOL_RU[tl]])
            elif s["kind"] == "table" and s["code"] not in ("doc", "ntd", "work_scope"):
                tols = sec_tol_list(s, d)
                for k, row in enumerate(d.get("rows", [])):
                    tl = tols[k] if k < len(tols) else "empty"
                    if tl in ("borderline", "exceeded"):
                        out.append([reo.label, title, "; ".join(f"{c['label']}: {row.get(c['key'], '')}" for c in s["cols"]), TOL_RU[tl]])
            elif s["kind"] == "form":
                for f in s.get("fields", []):
                    if f.get("tol"):
                        from app.services.sections import tol_field

                        tl = tol_field(f["tol"], d.get("values", {}).get(f["key"]))
                        if tl in ("borderline", "exceeded"):
                            out.append([reo.label, title, f"{f['label']}: {d['values'].get(f['key'])}", TOL_RU[tl]])
    return out


# ---------- документ ----------
def build_report_docx(ctx, info: Info) -> tuple[bytes, str]:
    t, r = ctx.task, ctx.r
    root = info.eos.get(t.eo_id)
    eos = [info.eos.get(e.eo_id) for e in r.eos]
    cust, exe = info.customer, info.executor
    cd, ed = (cust.details if cust else {}) or {}, (exe.details if exe else {}) or {}
    cust_full, exe_full = cd.get("full") or (cust.name if cust else t.deo), ed.get("full") or (exe.name if exe else "организация-исполнитель")
    number, rep_date = report_no(ctx)
    approved = _hist_at(ctx, "На рассмотрении ДЭО")
    pe_done = _hist_at(ctx, "Требуется КП")
    tm_attrs = _tm_attrs(info, root or (eos[0] if eos else None))
    opo_name, opo_class, opo_reg = _attr_v(tm_attrs, "OPO_NAME"), _attr_v(tm_attrs, "CLASS"), _attr_v(tm_attrs, "OPO_REG")
    opo_addr = _attr_v(tm_attrs, "ADDRESS", cd.get("location", "—"))
    pe_secs = [s for s in ctx.sections if s["stage"] == "ПЭ" and s["kind"] != "info"]
    calc = next((s for s in ctx.sections if s["code"] == "calc"), None)
    concl = next((s for s in ctx.sections if s["code"] == "conclusion"), None)
    ntd_sec = next((s for s in ctx.sections if s["code"] == "ntd"), None)
    vdp = next((s for s in ctx.sections if s["code"] == "vdp"), None)
    appx = {s["code"]: n for n, s in enumerate(pe_secs, start=1)}
    n_next = len(pe_secs) + 1
    if calc:
        appx["calc"], n_next = n_next, n_next + 1
    if vdp:
        appx["vdp"], n_next = n_next, n_next + 1
    appx["ntd"] = n_next
    device = DEVICE.get(t.vid, "техническое устройство")
    fact_from, fact_to = t.start_date, pe_done.at.date() if pe_done else t.end_date
    chief_pos, chief_fio = ed.get("chief", ["Главный инженер", "______________"])
    do_pos, do_fio = ed.get("do_head", ["Начальник службы ДО", "______________"])

    doc = Document()
    _setup(doc)
    _header_footer(doc, f"Технический отчёт № {number} · {t.eo_name}")

    # ---- Титульный лист (форма В.1) ----
    _p(doc, "ГЕНЗАКАЗЧИК", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=12, space_after=0)
    _p(doc, f"Дочернее общество: {cust.name if cust else t.deo}", align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=0)
    _p(doc, f"Диагностическое обследование, договор № {t.xyz} от {fmt_date(t.start_date)}", align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=0)
    _p(doc, f"Объект: {t.eo_name}", align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=0)
    _p(doc, f"Инв. № {root.inventory_number if root and root.inventory_number else '—'}", align=WD_ALIGN_PARAGRAPH.CENTER, size=11, space_after=12)
    _p(doc, (exe.name if exe else "Организация-исполнитель").upper(), bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=12, space_after=18)
    for line, b in (("УТВЕРЖДАЮ", True), (chief_pos, False), (exe.name if exe else "", False),
                    (f"______________ /{chief_fio}/", False),
                    (f"«{approved.at.day:02d}» {_month(approved.at.month)} {approved.at.year} г." if approved else "«____» __________ 20__ г.", False)):
        _p(doc, line, bold=b, indent=9.0, size=12, space_after=2)
    _p(doc, "", space_after=24)
    _p(doc, "ТЕХНИЧЕСКИЙ ОТЧЁТ", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=18, space_after=2)
    _p(doc, "ПО РЕЗУЛЬТАТАМ ТЕХНИЧЕСКОГО ДИАГНОСТИРОВАНИЯ", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=14, space_after=2)
    _p(doc, f"№ {number} от {fmt_date(rep_date)}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13, space_after=12)
    _p(doc, f"Вид работ: {VID_NAME.get(t.vid, t.vid)}", align=WD_ALIGN_PARAGRAPH.CENTER, size=12)
    _p(doc, "Объект технического диагностирования:", bold=True, size=12, space_after=2)
    _p(doc, f"техническое устройство — {device}", size=12, space_after=4)
    _table(doc, ["Наименование", "Заводской №", "Регистрационный №", "Инвентарный №"],
           [[t.eo_name, (root.factory_number if root else "") or "—", _reg_no(root), (root.inventory_number if root else "") or "—"]], [6.5, 3.0, 3.5, 3.0])
    _table(doc, ["Наименование ОПО", "Класс опасности ОПО", "Регистрационный № ОПО"], [[opo_name, opo_class, opo_reg]], [8.0, 3.5, 4.5])
    _p(doc, f"Местонахождение объекта: {t.location}; {opo_addr}", size=12, space_after=18)
    _p(doc, do_pos, size=12, space_after=0)
    _p(doc, f"______________ /{do_fio}/", size=12, space_after=0)
    _p(doc, f"«{rep_date.day:02d}» {_month(rep_date.month)} {rep_date.year} г.", size=12, space_after=30)
    _p(doc, f"{ed.get('city', '')}\n{rep_date.year} г.", align=WD_ALIGN_PARAGRAPH.CENTER, size=12)
    _page_break(doc)

    # ---- Содержание ----
    _p(doc, "СОДЕРЖАНИЕ", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13, space_after=8)
    toc = ["Основания для проведения работ", "Сроки проведения работ", "Перечень нормативных и правовых актов, устанавливающих требования к объекту диагностики",
           "Сведения о Заказчике", "Сведения об организации, проводившей техническое диагностирование", "Сведения о специалистах, проводивших обследование",
           "Перечень приборов и оборудования", "Перечень объектов технического диагностирования",
           "Краткая техническая характеристика и назначение объектов технического диагностирования", "Перечень работ, выполненных в процессе технического диагностирования",
           "Сведения о рассмотренных в процессе технического диагностирования документах", "Анализ результатов предыдущего диагностирования",
           "Результаты технического диагностирования", "Результаты расчетной оценки технического состояния", "Выводы по результатам технического диагностирования"]
    for i, x in enumerate(toc, start=1):
        _p(doc, f"{i}. {x}", size=12, space_after=1)
    for s in pe_secs:
        _p(doc, f"Приложение № {appx[s['code']]}. {METHOD.get(s['code'], (s['title'], s['title']))[1]}", size=12, space_after=1)
    if calc:
        _p(doc, f"Приложение № {appx['calc']}. Расчет на прочность и оценка остаточного ресурса", size=12, space_after=1)
    if vdp:
        _p(doc, f"Приложение № {appx['vdp']}. Ведомость дефектов зданий и сооружений", size=12, space_after=1)
    _p(doc, f"Приложение № {appx['ntd']}. Перечень применяемой при техническом диагностировании нормативной, технической и методической документации", size=12, space_after=1)
    _p(doc, "Лист согласования", size=12, space_after=1)
    _page_break(doc)

    # ---- 1–3 ----
    _h(doc, "1. Основания для проведения работ", 1)
    _para(doc, f"Работы по техническому диагностированию проведены в соответствии с договором между {cust_full} и "
               f"{exe_full} № {t.xyz} от {fmt_date(t.start_date)}, на основании задания на диагностическое "
               f"обследование № {t.id} (шаблон «{t.template_name}»){' — хозяйственным способом силами ДЭО' if t.is_hs else ''}.")
    _h(doc, "2. Сроки проведения работ", 1)
    _para(doc, f"Работы по техническому диагностированию проведены в период с {fmt_date(fact_from)} по {fmt_date(fact_to)} "
               f"(плановые сроки по заданию: {fmt_date(t.start_date)} — {fmt_date(t.end_date)}). Технический отчёт сформирован {fmt_date(rep_date)}.")
    _h(doc, "3. Перечень нормативных и правовых актов, устанавливающих требования к объекту диагностики", 1)
    for x in NPA["common"] + NPA.get(t.vid, []):
        _p(doc, f"– {x};", align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=0.6)

    # ---- 4–6 ----
    _h(doc, "4. Сведения о Заказчике", 1)
    _caption(doc, "Таблица № 1")
    _table(doc, None, _org_rows(cust, cd), [6.0, 10.0], kv=True)
    _h(doc, "5. Сведения об организации, проводившей техническое диагностирование", 1)
    _caption(doc, "Таблица № 2")
    _table(doc, None, _org_rows(exe, ed) + [["Свидетельство об аттестации лаборатории неразрушающего контроля", ed.get("lnk", "—")]], [6.0, 10.0], kv=True)
    _h(doc, "6. Сведения о специалистах, проводивших обследование", 1)
    _caption(doc, "Таблица № 3")
    _table(doc, ["№ п/п", "Ф.И.О.", "№ удостоверения", "Область аттестации", "Срок действия удостоверения"],
           [[f"{i}.", m.get("fio", ""), m.get("cert", ""), f"{m.get('level', '')} уровень: {', '.join(m.get('methods', []))}", fmt_date(parse_date(m.get("validUntil")))]
            for i, m in enumerate(info.members, start=1)] or [["—", "Состав бригады не указан", "", "", ""]], [1.2, 3.3, 3.2, 5.0, 3.3])

    # ---- 7. Приборы ----
    _h(doc, "7. Перечень приборов и оборудования", 1)
    _caption(doc, "Таблица № 4")
    rows, seen = [], set()
    for s in pe_secs:
        name = s.get("instrument")
        if not name or name in seen:
            continue
        seen.add(name)
        reg = info.instruments.get(name, {})
        serial = reg.get("serial") or next((ctx.data(i, s).get("serial") for i in range(len(r.eos)) if ctx.data(i, s).get("serial")), "") or "—"
        rows.append([f"{len(rows) + 1}.", name, serial, reg.get("verif") or reg.get("cert") or "—", fmt_date(parse_date(reg.get("valid"))) or "—"])
    _table(doc, ["№ п/п", "Наименование прибора", "Заводской номер прибора", "Свидетельство о поверке*", "Действительно до"], rows or [["—", "Приборы не применялись", "", "", ""]],
           [1.2, 5.0, 3.0, 4.6, 2.2])
    _p(doc, "* — в соответствии с данными электронного реестра ФГИС «Аршин» Росстандарта.", size=10, italic=True)

    # ---- 8–9. Объекты ----
    _h(doc, "8. Перечень объектов технического диагностирования", 1)
    _caption(doc, "Таблица № 5")
    obj_rows = []
    for k, (reo, eo) in enumerate(zip(r.eos, eos), start=1):
        if len(r.eos) > 1:
            obj_rows.append([f"8.{k}. {reo.label}"])
        tm = info.tms.get(eo.tm_id) if eo else None
        obj_rows += [["Объект технического диагностирования", eo.name if eo else reo.label], ["Заводской №", (eo.factory_number if eo else "") or "—"],
                     ["Регистрационный №", _reg_no(eo)], ["Инвентарный №", (eo.inventory_number if eo else "") or "—"],
                     ["Технологический № (позиция)", (eo.position if eo else "") or "—"], ["Наименование ОПО", opo_name], ["Класс ОПО", opo_class],
                     ["Регистрационный № ОПО", opo_reg], ["Место установки", f"{tm.name} ({tm.code})" if tm else t.location], ["Местонахождение (адрес) ОПО", opo_addr]]
    _table(doc, None, obj_rows, [6.0, 10.0], kv=True)
    _h(doc, "9. Краткая техническая характеристика и назначение объектов технического диагностирования", 1)
    _caption(doc, "Таблица № 6")
    ch_rows = []
    for k, (reo, eo) in enumerate(zip(r.eos, eos), start=1):
        if len(r.eos) > 1:
            ch_rows.append([f"9.{k}. {reo.label}"])
        ch_rows += _characteristics(t.vid, eo, reo.label)
    _table(doc, None, ch_rows, [7.0, 9.0], kv=True)

    # ---- 10. Перечень работ ----
    _h(doc, "10. Перечень работ, выполненных в процессе технического диагностирования", 1)
    _caption(doc, "Таблица № 7")
    w_rows = []
    for k, s in enumerate(pe_secs, start=1):
        vols = sorted({_volume(s, ctx.data(i, s)) for i in range(len(r.eos))})
        ntd = _method_ntd(s["code"], t.vid)
        w_rows.append([f"{k}.", METHOD.get(s["code"], (s["title"],))[0], ("; ".join(vols) + (f" (по {len(r.eos)} ЕО)" if len(r.eos) > 1 else "")),
                       "; ".join(x.split(" «")[0] for x in ntd) or "Программа работ"])
    if calc:
        w_rows.append([f"{len(w_rows) + 1}.", "Расчет на прочность и оценка остаточного ресурса", "По результатам контроля", "ГОСТ 34233.1-2017" if t.vid == "vessel" else "Методика ДО"])
    _table(doc, ["№ п/п", "Наименование работы", "Объем контроля", "Нормативная документация"], w_rows, [1.2, 6.0, 4.6, 4.2])
    ws = next((s for s in ctx.sections if s["code"] == "work_scope"), None)
    if ws:
        d = ctx.data(0, ws)
        if d.get("rows"):
            _p(doc, "Фактический объём выполненных работ (по данным камеральной проверки):", size=12)
            _table(doc, [c["label"] for c in ws["cols"]], [[row.get(c["key"], "") for c in ws["cols"]] for row in d["rows"]])

    # ---- 11. Документы ----
    _h(doc, "11. Сведения о рассмотренных в процессе технического диагностирования документах", 1)
    _caption(doc, "Таблица № 8")
    doc_sec = next((s for s in ctx.sections if s["code"] == "doc"), None)
    d_rows, names = [], set()
    if doc_sec:
        for i in range(len(r.eos)):
            for row in ctx.data(i, doc_sec).get("rows", []):
                key = (row.get("type"), row.get("no"))
                if key in names:
                    continue
                names.add(key)
                d_rows.append([row.get("type", ""), row.get("no") or "—", row.get("st", "")])
    for x in DOC_FORM:
        if not any(x.lower()[:20] in rr[0].lower() for rr in d_rows):
            d_rows.append([x, f"Представлено {cust.code if cust else 'ДЭО'}", "Предоставлен"])
    _table(doc, ["№ п/п", "Наименование документа", "Идентификационный номер документа", "Отметка о предоставлении"],
           [[f"{k}.", *row] for k, row in enumerate(d_rows, start=1)], [1.2, 7.0, 4.4, 3.4])

    # ---- 12. Предыдущее ДО ----
    _h(doc, "12. Анализ результатов предыдущего диагностирования", 1)
    _caption(doc, "Таблица № 9")
    p_rows = []
    for rec in info.prev[:8]:
        eo = info.eos.get(rec.eo_id)
        res = f"ТС: {rec.object_status or '—'}" + (f"; остаточный ресурс {_f(rec.residual_life_years)} лет" if rec.residual_life_years is not None else "")
        p_rows.append([fmt_date(rec.reg_date), "Техническое диагностирование", (f"{eo.name}: " if eo and len(r.eos) > 1 else "") + res, f"Запись о ТС {rec.number}"])
    p_rows.append(["—", "Экспертиза промышленной безопасности", "Сведения приведены в разделе 11", "—"])
    p_rows.append(["—", "Периодическое техническое освидетельствование", "Замечаний не зафиксировано" if t.vid == "vessel" else "Не применимо", "—"])
    _table(doc, ["Дата", "Вид обследования", "Результаты контроля", "Наименование и номер отчетной документации"], p_rows, [2.4, 4.4, 5.6, 3.6])
    if info.prev:
        _para(doc, f"По результатам предыдущих обследований (последнее — {fmt_date(info.prev[0].reg_date)}) техническое состояние оценивалось как "
                   f"«{info.prev[0].object_status or '—'}». Результаты учтены при оценке скорости коррозионного износа и остаточного ресурса.")
    else:
        _para(doc, "Сведения о предыдущих диагностических обследованиях в БДТС отсутствуют; диагностирование проведено впервые в рамках системы.")

    # ---- 13. Результаты ----
    _h(doc, "13. Результаты технического диагностирования", 1)
    _caption(doc, "Таблица № 10")
    res_rows = []
    for k, s in enumerate(pe_secs, start=1):
        parts = [_summary(s, ctx.data(i, s)) for i in range(len(r.eos))]
        text = parts[0] if len(set(parts)) == 1 else "\n".join(f"{reo.label}: {p}" for reo, p in zip(r.eos, parts))
        res_rows.append([f"{k}.", METHOD.get(s["code"], (s["title"],))[0], text, f"Приложение № {appx[s['code']]}"])
    if calc:
        rt = [ctx.data(i, calc)["values"].get("rt") for i in range(len(r.eos))]
        res_rows.append([f"{len(res_rows) + 1}.", "Расчет на прочность и оценка остаточного ресурса",
                         f"Остаточный ресурс R_T = {', '.join(_f(x) for x in rt if x)} лет", f"Приложение № {appx['calc']}"])
    _table(doc, ["№ п/п", "Наименование работы", "Результаты контроля", "Наименование и номер отчетной документации"], res_rows, [1.2, 5.2, 6.6, 3.0])
    devs = _deviations(ctx)
    if devs:
        _p(doc, "Перечень выявленных дефектов и несоответствий", bold=True, size=12)
        _caption(doc, "Таблица № 11")
        _table(doc, ["№ п/п", "Единица оборудования", "Метод контроля", "Описание дефекта / несоответствия", "Оценка"],
               [[f"{k}.", *row] for k, row in enumerate(devs, start=1)], [1.2, 3.6, 3.6, 5.6, 2.0])

    # ---- 14. Расчётная оценка ----
    _h(doc, "14. Результаты расчетной оценки технического состояния", 1)
    if calc:
        for i, reo in enumerate(r.eos):
            v = ctx.data(i, calc)["values"]
            label = f"{reo.label}: " if len(r.eos) > 1 else ""
            _para(doc, f"{label}по результатам расчета на прочность с учетом фактических толщин стенок элементов произведена оценка работоспособности; "
                       f"остаточный ресурс R_T = {_f(v.get('rt'))} лет" + (f", скорость коррозии {_f(v.get('vc'), 2)} мм/год" if v.get("vc") else "")
                       + (f", определяющий элемент — {v.get('el')}" if v.get("el") else "") + f" (Приложение № {appx['calc']}).")
    else:
        _para(doc, "Оценка работоспособности выполнена по критериям допуска методов контроля (раздел 13) с учётом результатов анализа технической "
                   "документации; расчёт на прочность программой работ для данного вида ДО не предусмотрен, так как фактические толщины стенок "
                   "элементов не ниже расчётных значений.")

    # ---- 15. Выводы ----
    _h(doc, "15. Выводы по результатам технического диагностирования", 1)
    worst = _worst([x for i in range(len(r.eos)) for s in ctx.sections for x in sec_tol_list(s, ctx.data(i, s))])
    for i, (reo, eo) in enumerate(zip(r.eos, eos)):
        cv = ctx.data(i, concl)["values"] if concl else {}
        ok_txt = "удовлетворяют" if worst != "exceeded" else "не в полной мере удовлетворяют"
        _para(doc, f"Фактические значения параметров, определяющих возможность эксплуатации объекта — {device}: {eo.name if eo else reo.label}"
                   f"{', зав. № ' + eo.factory_number if eo and eo.factory_number else ''}, рег. № {_reg_no(eo)}, инв. № {(eo.inventory_number if eo else '') or '—'}, "
                   f"{ok_txt} требованиям нормативных документов. Техническое состояние объекта диагностирования — {(cv.get('ts') or '—').lower()}.")
        if cv.get("text"):
            _para(doc, cv["text"])
        if cv.get("next"):
            _para(doc, f"Рекомендуемый срок проведения следующего технического диагностирования — не позднее {fmt_date(parse_date(cv['next']))} (п. 7.1.5).")
    if devs:
        _para(doc, f"Выявленные дефекты и несоответствия приведены в таблице № 11; мероприятия по их устранению включаются в план ТОиР эксплуатирующей организации.")

    # ---- Приложения-протоколы ----
    for s in pe_secs:
        _page_break(doc)
        _protocol(doc, ctx, info, s, appx[s["code"]], number, fact_to, cust, exe, ed, t)
    if calc:
        _page_break(doc)
        _calc_appendix(doc, ctx, calc, appx["calc"], number, t)
    if vdp:
        _page_break(doc)
        _p(doc, f"ПРИЛОЖЕНИЕ № {appx['vdp']}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _p(doc, "Ведомость дефектов зданий и сооружений", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13)
        for i, reo in enumerate(r.eos):
            rows_v = ctx.data(i, vdp).get("rows", [])
            if rows_v:
                if len(r.eos) > 1:
                    _p(doc, reo.label, bold=True, size=11)
                _table(doc, ["№ п/п"] + [c["label"] for c in vdp["cols"]], [[f"{k}.", *[row.get(c["key"], "") for c in vdp["cols"]]] for k, row in enumerate(rows_v, start=1)])
    _page_break(doc)
    _p(doc, f"ПРИЛОЖЕНИЕ № {appx['ntd']}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _p(doc, "Перечень применяемой при техническом диагностировании нормативной, технической и методической документации*", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13)
    ntd_all = list(NPA["common"] + NPA.get(t.vid, []))
    for s in pe_secs:
        ntd_all += [x for x in _method_ntd(s["code"], t.vid) if x not in ntd_all]
    if ntd_sec:
        for i in range(len(r.eos)):
            for row in ctx.data(i, ntd_sec).get("rows", []):
                x = f"{row.get('doc', '')} «{row.get('name', '')}»" if row.get("name") else row.get("doc", "")
                if x and not any(row.get("doc", "") and row.get("doc") in y for y in ntd_all):
                    ntd_all.append(x)
    _table(doc, None, [[f"{k}", x] for k, x in enumerate(ntd_all, start=1)], [1.2, 14.8])
    _p(doc, "* — указанная в типовой форме нормативно-техническая документация подлежит актуализации на дату оформления технического отчёта.", size=10, italic=True)

    # ---- Лист согласования (п. 7.1.9) ----
    _page_break(doc)
    _p(doc, "ЛИСТ СОГЛАСОВАНИЯ", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13)
    _p(doc, f"к техническому отчёту № {number} от {fmt_date(rep_date)}", align=WD_ALIGN_PARAGRAPH.CENTER, size=12, space_after=8)
    s_rows = []
    for stage, st in STAGES_SIGN:
        h = _hist_at(ctx, st)
        if h:
            fio, role = _fio(h.username)
            s_rows.append([stage, role or "—", fio, fmt_date(h.at.date()), "Согласовано в БДТС"])
    if approved:
        s_rows.append(["Технический отчёт утвердил (п. 7.1.7)", f"{chief_pos}, {exe.name if exe else ''}", chief_fio, fmt_date(approved.at.date()), "Утверждено"])
    _table(doc, ["Этап", "Должность / роль", "Ф.И.О.", "Дата", "Отметка"], s_rows or [["—", "Согласование не проводилось", "", "", ""]], [4.0, 5.0, 2.4, 2.2, 2.4])
    _para(doc, "Технический отчёт сформирован автоматически в МП-3.5 «БДТС» по данным результата ДО. Подписание усиленной квалифицированной "
               "электронной подписью исполнителя и утверждающего лица выполняется средствами ЕЦП ДТОиР при передаче отчёта в электронный архив.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), f"{number}_{VID_SHORT.get(t.vid, t.vid)}.docx"


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _month(m: int) -> str:
    return MONTHS[m - 1]


def _reg_no(eo: EquipmentUnit | None) -> str:
    v = _passport(eo, "Рег. №")
    return v.split(",")[0].strip() if v else "Не подлежит регистрации"


def _org_rows(o: Organization | None, d: dict) -> list[list]:
    return [["Полное наименование организации", d.get("full") or (o.name if o else "—")], ["Руководитель организации", d.get("head", "—")],
            ["Юридический адрес", d.get("address", "—")], ["Местонахождение", d.get("location") or d.get("address", "—")],
            ["Телефон", d.get("phone", "—")], ["E-mail", d.get("email", "—")]]


def _characteristics(vid: str, eo: EquipmentUnit | None, label: str) -> list[list]:
    if not eo:
        return [["Наименование объекта", label], ["Сведения", "ЕО создана в поле, паспортные данные уточняются"]]
    a = eo.attrs or []
    rows = [["Наименование объекта", eo.name], ["Назначение", _attr_v(a, "PURPOSE")], ["Условное обозначение (марка)", eo.model or "—"],
            ["Наименование завода-изготовителя", eo.manufacturer or "—"], ["Год изготовления", eo.year or "—"],
            ["Год ввода в эксплуатацию", (_attr_v(a, "INSTALLATION", "—")[-4:])]]
    if vid == "vessel":
        rows += [["Проектное давление, МПа", _attr_v(a, "P_DESIGN")], ["Рабочее давление, МПа", _attr_v(a, "P_WORK")],
                 ["Номинальный внутренний диаметр, мм", _attr_v(a, "D_NOM")], ["Наименование рабочей среды", _attr_v(a, "MEDIUM")],
                 ["Рабочая температура среды, °C", _attr_v(a, "T_WORK")], ["Марка материала корпуса", eo.steel_grade or "—"],
                 ["Вместимость, м³", _attr_v(a, "VOLUME")], ["Климатическое исполнение", _attr_v(a, "CLIMATE")], ["Расчетный срок службы, лет", _attr_v(a, "LIFE")]]
    elif vid == "wellhead":
        rows += [["Рабочее / пробное давление, МПа", f"{_attr_v(a, 'P_WORK')} / {_attr_v(a, 'P_TEST')}"], ["Материал основных деталей", eo.steel_grade or "—"],
                 ["Рабочая среда", _attr_v(a, "MEDIUM")], ["Климатическое исполнение", _attr_v(a, "CLIMATE")], ["Назначенный срок службы, лет", _attr_v(a, "LIFE")]]
    else:
        rows += [["DN, мм / PN, МПа", f"{eo.dn or '—'} / {eo.pn or '—'}"], ["Марка стали (корпус)", eo.steel_grade or "—"],
                 ["Расчетная толщина стенки, мм", eo.s_calc or "—"], ["Рабочая среда", _attr_v(a, "MEDIUM")],
                 ["Климатическое исполнение", _attr_v(a, "CLIMATE")], ["Назначенный срок службы, лет", _attr_v(a, "LIFE")]]
    return rows


def _specialist(members: list[dict], method_title: str) -> tuple[dict, dict]:
    """Контроль провёл — специалист, аттестованный по методу; заключение выдал — специалист наивысшего уровня."""
    key = {"Визуальный": "ВИК", "толщинометрия": "УЗТ", "Ультразвуковой контроль": "УЗК", "твёрдости": "Твёрдость", "Магнитопорошковый": "МПК", "Капиллярный": "ПВК"}
    m_code = next((v for k, v in key.items() if k in method_title), "")
    doer = next((m for m in members if m_code and m_code in m.get("methods", [])), members[0] if members else {})
    lead = max(members, key=lambda m: {"I": 1, "II": 2, "III": 3}.get(m.get("level", ""), 0)) if members else {}
    return doer, lead


def _protocol(doc, ctx, info, s, n, number, rep_date, cust, exe, ed, t):
    work, title, _ntd, params = METHOD.get(s["code"], (s["title"], f"Протокол: {s['title']}", [], []))
    ntd = _method_ntd(s["code"], t.vid)
    _p(doc, f"ПРИЛОЖЕНИЕ № {n}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _p(doc, title, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13)
    head = [["Предприятие-исполнитель", exe.name if exe else "—"], ["Почтовый адрес", ed.get("address", "—")],
            ["Лаборатория НК / свидетельство об аттестации", ed.get("lnk", "—")], ["Предприятие-Заказчик", cust.name if cust else t.deo],
            ["Место нахождения оборудования", t.location], ["Тип и наименование оборудования", f"{VID_NAME.get(t.vid, '')}: {t.eo_name}"]]
    _table(doc, None, head, [6.0, 10.0], kv=True, size=10)
    _p(doc, f"{title} № {number}-{n:02d} от {fmt_date(rep_date)}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=12)
    k = 1
    if ntd:
        _h(doc, f"{k}. Нормативно-техническая документация, в соответствии с которой выполнен контроль", 2)
        for x in ntd + [f"Технологическая карта № {_tk(s['code'], t.vid)}"]:
            _p(doc, f"– {x};", indent=0.6, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        k += 1
    if s.get("instrument"):
        _h(doc, f"{k}. Применяемое оборудование", 2)
        reg = info.instruments.get(s["instrument"], {})
        serial = reg.get("serial") or ctx.data(0, s).get("serial") or "—"
        _table(doc, ["№ п/п", "Наименование прибора", "Заводской номер прибора", "Свидетельство о поверке"], [["1.", s["instrument"], serial, reg.get("verif") or "—"]],
               [1.2, 6.8, 3.5, 4.5])
        k += 1
    if params:
        _h(doc, f"{k}. Параметры контроля", 2)
        _table(doc, None, [[a, b] for a, b in params], [7.0, 9.0], kv=True)
        k += 1
        _h(doc, f"{k}. Схема контроля", 2)
        _para(doc, f"Схема контроля (расположение зон и точек) — по технологической карте {_tk(s['code'], t.vid)}; "
                   "обозначения точек и участков в таблице результатов соответствуют схеме.")
        k += 1
    _h(doc, f"{k}. Результаты контроля", 2)
    worst = "empty"
    concls = []
    for i, reo in enumerate(ctx.r.eos):
        d = ctx.data(i, s)
        if len(ctx.r.eos) > 1:
            _p(doc, f"{k}.{i + 1}. {reo.label}", bold=True, size=11)
        if d.get("np"):
            _para(doc, f"Контроль не проводился. Причина: {d.get('reason') or 'не указана'}.")
            continue
        tols = sec_tol_list(s, d)
        worst = _worst([worst, *tols])
        _results_table(doc, s, d, tols)
        if d.get("concl"):
            concls.append((reo.label, d["concl"]))
        if d.get("comment"):
            _p(doc, f"Примечание: {d['comment']}", size=10, italic=True)
    k += 1
    _h(doc, f"{k}. Заключение по результатам контроля", 2)
    _para(doc, _verdict(s, worst))
    for label, c in concls:
        _para(doc, (f"{label}: " if len(ctx.r.eos) > 1 else "") + f"Заключение специалиста: {c}")
    doer, lead = _specialist(info.members, work)
    _sign_block(doc, [("Контроль провёл: специалист", "______________", f"{doer.get('fio', '')}, {doer.get('level', '')} уровень, квал. уд. № {doer.get('cert', '')}"),
                      ("Заключение выдал: специалист", "______________", f"{lead.get('fio', '')}, {lead.get('level', '')} уровень, квал. уд. № {lead.get('cert', '')}")])


def _verdict(s: dict, worst: str) -> str:
    bad = worst == "exceeded"
    code = s["code"]
    if code == "doc":
        return "Представленная техническая документация ведётся в соответствии с требованиями действующей нормативно-технической документации." if not bad else \
            "Представленная техническая документация не в полной мере соответствует требованиям НТД (см. таблицу результатов)."
    if code == "uzt":
        return ("Измеренная толщина стенок элементов не ниже минимально допустимых значений и удовлетворяет требованиям нормативно-технической документации."
                if not bad else "Измеренная толщина стенок отдельных элементов ниже минимально допустимых значений и не удовлетворяет требованиям НТД.")
    if code == "hardness":
        return ("Измеренные значения твёрдости металла находятся в допустимых пределах и отвечают требованиям нормативно-технической документации."
                if not bad else "Измеренные значения твёрдости металла в отдельных точках выходят за допустимые пределы.")
    if s["kind"] == "form":
        return ("Контролируемые параметры соответствуют требованиям нормативно-технической документации." if not bad
                else "Отдельные контролируемые параметры не соответствуют требованиям НТД.")
    return ("По результатам контроля недопустимых дефектов не обнаружено, объект контроля соответствует требованиям нормативно-технической документации."
            + (" Отклонения на границе допуска приведены в таблице результатов." if worst == "borderline" else "")
            if not bad else "По результатам контроля обнаружены недопустимые дефекты, объект контроля не соответствует требованиям нормативно-технической документации.")


def _results_table(doc, s, d, tols):
    kind = s["kind"]
    if kind == "checklist":
        rows = []
        for k, (code, name, op) in enumerate(s["items"]):
            idx = d.get("items", {}).get(code, -1)
            val = op[idx][0] if isinstance(idx, int) and 0 <= idx < len(op) else "—"
            rows.append([f"{k + 1}.", name, "100 %", (val + (f". {d['notes'][code]}" if d.get("notes", {}).get(code) else "")), TOL_RU.get(tols[k] if k < len(tols) else "empty")])
        _table(doc, ["№ п/п", "Наименование объекта контроля", "Объем контроля", "Описание обнаруженных дефектов, их размеры", "Оценка качества"], rows, [1.2, 4.6, 2.2, 5.6, 2.4])
    elif kind == "points":
        rows, j = [], 0
        thk = s["mode"] == "thk"
        for ei, el in enumerate(d.get("elements", [])):
            cfg = s["elements"][ei] if ei < len(s["elements"]) else {}
            pts = [p for p in el.get("points", []) if str(p.get("value") or "").strip()]
            n_all = len(el.get("points", []))
            el_tols = tols[j:j + n_all]
            j += n_all
            vals = [_num(p["value"]) for p in pts if _num(p["value"]) is not None]
            values = "; ".join(f"{p['label']} – {_f(p['value'], 2 if thk else 0)}" for p in pts)
            if thk:
                rows.append([el["name"], _f(cfg.get("s"), 1), values, _f(min(vals), 2) if vals else "—", TOL_RU.get(_worst(el_tols))])
            else:
                lo, hi = cfg.get("lo", s.get("lo")), cfg.get("hi", s.get("hi"))
                rows.append([el["name"], f"{lo}–{hi}", values, f"{round(sum(vals) / len(vals))}" if vals else "—", TOL_RU.get(_worst(el_tols))])
        if thk:
            _table(doc, ["Наименование элемента", "s расч., мм", "№ точки – толщина, мм", "s min факт., мм", "Оценка"], rows, [4.2, 1.8, 6.0, 2.0, 2.0])
        else:
            _table(doc, ["Участок контроля", "Допустимая твёрдость, HB", "№ точки – твёрдость, HB", "Среднее, HB", "Оценка"], rows, [4.2, 2.4, 5.4, 2.0, 2.0])
    elif kind == "table":
        cols = s["cols"]
        with_tol = s["code"] not in ("ntd", "work_scope", "doc")
        hdr = ["№ п/п"] + [c["label"] for c in cols] + (["Оценка"] if with_tol else [])
        rows = [[f"{k + 1}.", *[row.get(c["key"], "") for c in cols], *([TOL_RU.get(tols[k] if k < len(tols) else "empty")] if with_tol else [])]
                for k, row in enumerate(d.get("rows", []))]
        _table(doc, hdr, rows)
    fields = [f for f in s.get("fields", []) if str(d.get("values", {}).get(f["key"], "")).strip()]
    if fields:
        from app.services.sections import tol_field

        _table(doc, ["Показатель", "Значение", "Оценка"],
               [[f["label"], d["values"][f["key"]], TOL_RU.get(tol_field(f["tol"], d["values"][f["key"]])) if f.get("tol") else "—"] for f in fields], [7.5, 5.5, 3.0])


def _calc_appendix(doc, ctx, calc, n, number, t):
    _p(doc, f"ПРИЛОЖЕНИЕ № {n}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _p(doc, "Расчет на прочность и оценка остаточного ресурса", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=13)
    uzt = next((s for s in ctx.sections if s["code"] == "uzt"), None)
    _para(doc, "Остаточный ресурс по критерию коррозионного износа определён по формуле T = (s_ф − s_R) / a, где s_ф — минимальная фактическая толщина стенки "
               "элемента по результатам УЗТ, мм; s_R — расчётная (отбраковочная) толщина стенки, мм; a — скорость коррозии, мм/год. "
               "Ресурс объекта принимается по наиболее нагруженному (изношенному) элементу." + (" Расчётные толщины — по ГОСТ 34233.2-2017." if t.vid == "vessel" else ""))
    for i, reo in enumerate(ctx.r.eos):
        v = ctx.data(i, calc)["values"]
        if len(ctx.r.eos) > 1:
            _p(doc, reo.label, bold=True, size=11)
        a = _num(v.get("vc"))
        t_vals = []
        if uzt:
            rows = []
            for ei, el in enumerate(ctx.data(i, uzt).get("elements", [])):
                cfg = uzt["elements"][ei] if ei < len(uzt["elements"]) else {}
                vals = [_num(p.get("value")) for p in el.get("points", []) if _num(p.get("value")) is not None]
                if not vals:
                    continue
                sf, sr = min(vals), float(cfg.get("s", 0))
                t_vals.append((sf, sr))
                rows.append([el["name"], _f(sr, 2), _f(sf, 2), _f(sf - sr, 2), _f((sf - sr) / a) if a and sf > sr else ("—" if not a else "0")])
            _table(doc, ["Элемент", "s_R, мм", "s_ф min, мм", "Запас s_ф − s_R, мм", "T, лет" + (f" (a = {_f(a, 2)} мм/год)" if a else "")], rows, [5.2, 2.2, 2.4, 3.0, 3.2])
        _table(doc, None, [[f["label"], v.get(f["key"]) or "—"] for f in calc.get("fields", [])], [9.0, 7.0], kv=True)
        t_min = min(((sf - sr) / a for sf, sr in t_vals if sf > sr), default=None) if a else None
        limited = t_min is not None and _num(v.get("rt")) is not None and _num(v.get("rt")) < t_min - 0.05
        _para(doc, f"Принятый остаточный ресурс R_T = {_f(v.get('rt'))} лет"
                   + (" (ограничен с учётом назначенного срока службы и периодичности технического диагностирования)" if limited else "")
                   + ". Прочность элементов при рабочих параметрах обеспечена.")


async def render_result_docx(session, ctx) -> tuple[bytes, str]:
    """Сборка данных и формирование отчёта (используется при «Сформировать технический отчет» и при каждой выгрузке)."""
    return build_report_docx(ctx, await collect(session, ctx))
