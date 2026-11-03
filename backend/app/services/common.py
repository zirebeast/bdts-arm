"""Общие операции: уведомления, аудит, настройки, нумерация, форматирование дат."""
from datetime import date, datetime

from sqlalchemy import func, select

from app.models import AuditLog, ModuleSetting, Notification
from app.permissions import CurrentUser
from app.services.events import emit


def fmt_date(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


async def audit(session, user: CurrentUser | None, action: str, entity_type: str = "", entity_id="", **details):
    session.add(AuditLog(username=user.username if user else "system", action=action, entity_type=entity_type,
                         entity_id=str(entity_id), details=details))


async def get_setting(session, key: str, default=None):
    row = await session.get(ModuleSetting, key)
    return row.value if row else default


async def notify(session, role: str, title: str, detail: str = "", link: str = "", type_: str = "Информация",
                 deo: str = "", rule_id: int | None = None):
    """Уведомление в колокольчик роли + e-mail через outbox, если правило оповещения включено (W-7.1)."""
    if rule_id is not None:
        rules = (await get_setting(session, "notify_rules", {})).get("items", [])
        rule = next((r for r in rules if r.get("id") == rule_id), None)
        if rule is not None and not rule.get("on", True):
            return
    session.add(Notification(role=role, title=title, detail=detail, link=link, type=type_, deo=deo))
    await emit(session, "notify.email", {"role": role, "subject": title, "body": detail})


async def next_number(session, model, column, prefix: str, width: int = 5) -> str:
    """Следующий номер вида «Б316-2026-00151» по максимальному существующему."""
    rows = (await session.execute(select(column).where(column.like(f"{prefix}%")))).scalars().all()
    nums = [int(r[len(prefix):]) for r in rows if r[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


async def count(session, stmt) -> int:
    return (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
