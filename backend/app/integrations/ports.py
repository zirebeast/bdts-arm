"""Порты внешних интеграций (интеграции.txt). Реализации выбираются переменными ADAPTER_* в app.integrations.registry."""
from typing import Protocol


class PlanSource(Protocol):
    """Вход 2.1: пообъектный план (ФМ-5.1 «Формирование планов», до 01.01.2027 — АСУ ТОиР)."""
    name: str

    async def fetch_plan(self, year: int, deo: str) -> list[dict]:
        """Строки ПП в формате ХР.xlsx (ключи col_*)."""


class BdoClient(Protocol):
    """Вход 2.2: атрибутивная информация по объектам из МП-3 «БДО» (ФМ-3.2)."""
    name: str

    async def equipment_by_object(self, cipher: str, tm_code: str) -> list[dict]:
        """ЕО по ТМ объекта: asupp, type, mark, techNum, serialNum, year, manufacturer, dn, pn, sCalc, steelGrade, sync, conflict."""

    async def sync_hierarchy(self) -> dict:
        """Синхронизация реплики ТМ/ЕО (DataSyncronizer). Возвращает счётчики."""


class ReportSink(Protocol):
    """Выход 3.1: передача технических отчётов (ИУС ГД / СЭД / архив)."""
    name: str

    async def send_report(self, payload: dict) -> dict: ...


class DiagnosticsSink(Protocol):
    """Выход 3.2: сведения по диагностическому обследованию (дефекты, перечни к планированию — МП-1, ТОиР)."""
    name: str

    async def send(self, kind: str, payload: dict) -> dict: ...


class Ps0Client(Protocol):
    """Задача ПС-0 на добавление ЕО/ТМ в БДО (memo 31.07.2026, схема 03)."""
    name: str

    async def create_task(self, payload: dict) -> dict: ...


class Notifier(Protocol):
    """Отправка оповещений по e-mail (Notification-Api → SMTP)."""
    name: str

    async def send(self, to_role: str, subject: str, body: str) -> dict: ...
