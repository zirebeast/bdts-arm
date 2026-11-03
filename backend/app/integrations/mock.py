"""Mock-адаптеры MVP: имитируют внешние системы, ответы — из fixtures, исходящие пакеты сохраняются в журнал."""
import asyncio
import random
import uuid

from app.integrations.fixtures import BDO_CATALOG, PLAN_ROWS


class MockPlanSource:
    name = "ФМ-5.1 «Формирование планов» (mock)"

    async def fetch_plan(self, year: int, deo: str) -> list[dict]:
        await asyncio.sleep(0)
        return [r for r in PLAN_ROWS if not deo or r.get("col_3") in (deo, None)]


class MockBdoClient:
    name = "МП-3 «БДО» ФМ-3.2 (mock)"

    async def equipment_by_object(self, cipher: str, tm_code: str) -> list[dict]:
        return [dict(e) for e in BDO_CATALOG.get(tm_code, BDO_CATALOG["GDAST-D02-G05-GRS-YUG"])]

    async def sync_hierarchy(self) -> dict:
        return {"tm": 0, "eo": 0, "note": "Реплика ТМ/ЕО актуальна (mock)"}


class MockReportSink:
    name = "ИУС ГД / СЭД (mock)"

    async def send_report(self, payload: dict) -> dict:
        return {"external_id": f"ИУС-{uuid.uuid4().hex[:8].upper()}", "accepted": True}


class MockDiagnosticsSink:
    name = "МП-1 / ТОиР (mock)"

    async def send(self, kind: str, payload: dict) -> dict:
        return {"external_id": f"{kind.upper()}-{uuid.uuid4().hex[:6].upper()}", "accepted": True}


class MockPs0Client:
    name = "ПС-0 (mock)"

    async def create_task(self, payload: dict) -> dict:
        return {"task_no": f"ПС-0 №{4100 + random.randint(0, 899)}"}


class MockNotifier:
    name = "SMTP (mock, без отправки)"

    async def send(self, to_role: str, subject: str, body: str) -> dict:
        return {"queued": True, "to": to_role}
