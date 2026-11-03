from urllib.parse import quote

from fastapi import Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.permissions import CurrentUser
from app.security import get_current_user, require  # noqa: F401  (реэкспорт для роутеров)

Session = Depends(get_session)
User = Depends(get_current_user)


class Page:
    def __init__(self, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500)):
        self.page, self.size = page, size


async def paginate(session: AsyncSession, stmt, page: Page, mapper) -> dict:
    total = (await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await session.execute(stmt.offset((page.page - 1) * page.size).limit(page.size))).unique().scalars().all()
    return {"items": [mapper(r) for r in rows], "total": total, "page": page.page, "size": page.size}


def file_response(data: bytes, name: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def scoped(stmt, model, user: CurrentUser):
    return stmt.where(model.deo == user.deo) if user.deo else stmt
