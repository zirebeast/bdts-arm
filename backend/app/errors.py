"""Ошибки бизнес-правил: код правила (R-*, D-*, V-*) передаётся клиенту для подсказки."""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class RuleError(HTTPException):
    def __init__(self, message: str, rule: str = "", status_code: int = 422, fields: dict | None = None):
        super().__init__(status_code=status_code, detail=message)
        self.rule = rule
        self.fields = fields or {}


class Conflict(RuleError):
    """Объект изменён другим пользователем (оптимистическая блокировка)."""

    def __init__(self, message: str = "Статус уже изменён другим пользователем. Данные обновлены."):
        super().__init__(message, rule="CONFLICT", status_code=409)


def not_found(what: str = "Объект") -> HTTPException:
    return HTTPException(404, f"{what} не найден")


async def rule_error_handler(_: Request, exc: RuleError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "rule": exc.rule, "fields": exc.fields})
