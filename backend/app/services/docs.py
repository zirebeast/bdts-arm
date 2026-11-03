"""Выгрузка реестров в .xlsx. Технический отчёт .docx — services/report_docx.py."""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


def build_xlsx(title: str, columns: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(columns)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="EEF1F4")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(["" if v is None else v for v in r])
    for i, col in enumerate(columns, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(48, len(col) + 4))
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
