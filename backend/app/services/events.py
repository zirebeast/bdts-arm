"""Transactional outbox + фоновые задания. С RabbitMQ — асинхронно в воркере; без него — в процессе API (тесты, dev)."""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.config import get_settings
from app.db import SessionLocal
from app.integrations import registry
from app.models import IntegrationLog, OutboxEvent

log = logging.getLogger(__name__)

OUTBOX_QUEUE = "bdts.outbox"
JOBS_QUEUE = "bdts.jobs"

TOPICS = {
    "report.accepted": ("Передача ТО (завершено ДЭО)", "report_sink"),
    "report.hs_sent": ("Передача ТО хозспособа в ГД", "report_sink"),
    "diag.defects": ("Сведения о выявленных дефектах", "diag_sink"),
    "plan.list": ("Перечень объектов к планированию", "diag_sink"),
    "ps0.task": ("Задача на добавление ЕО/ТМ в БДО", "ps0"),
    "notify.email": ("Оповещение e-mail", "notifier"),
}


async def emit(session, topic: str, payload: dict, key: str | None = None) -> None:
    session.add(OutboxEvent(topic=topic, payload=payload, idempotency_key=key or f"{topic}:{uuid.uuid4().hex}"))


async def _deliver(ev: OutboxEvent) -> dict:
    p = ev.payload
    if ev.topic.startswith("report."):
        return await registry.report_sink().send_report(p)
    if ev.topic == "diag.defects":
        return await registry.diag_sink().send("defects", p)
    if ev.topic == "plan.list":
        return await registry.diag_sink().send("plan_list", p)
    if ev.topic == "ps0.task":
        return await registry.ps0_client().create_task(p)
    if ev.topic == "notify.email":
        return await registry.notifier().send(p.get("role", ""), p.get("subject", ""), p.get("body", ""))
    raise ValueError(f"Неизвестный топик {ev.topic}")


async def dispatch_pending(limit: int = 100) -> int:
    """Доставка новых событий (идемпотентно: событие помечается sent только после ответа адаптера)."""
    sent = 0
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(OutboxEvent).where(or_(OutboxEvent.status == "new", (OutboxEvent.status == "failed") & (OutboxEvent.attempts < 5)))
            .order_by(OutboxEvent.id).limit(limit))).scalars().all()
        for ev in rows:
            flow, port = TOPICS.get(ev.topic, (ev.topic, ""))
            ev.attempts += 1
            try:
                res = await _deliver(ev)
                ev.status, ev.sent_at = "sent", datetime.now(timezone.utc)
                if ev.topic != "notify.email":
                    adapter = getattr(registry, port)() if port else None
                    session.add(IntegrationLog(direction="out", flow=flow, system=adapter.name if adapter else "", count=ev.payload.get("summary", ""),
                                               status="Успешно", username=ev.payload.get("user", "Система"), details={"response": res, "event": ev.id}))
                sent += 1
            except Exception as e:  # noqa: BLE001 — ошибка адаптера не должна ронять обработку очереди
                ev.status, ev.last_error = "failed", str(e)
                log.exception("outbox delivery failed: %s", ev.id)
        await session.commit()
    return sent


_rabbit = None


async def _channel():
    global _rabbit
    import aio_pika

    if _rabbit is None or _rabbit.is_closed:
        _rabbit = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    ch = await _rabbit.channel()
    for q in (OUTBOX_QUEUE, JOBS_QUEUE):
        await ch.declare_queue(q, durable=True)
    return ch


async def _publish(queue: str, body: dict) -> None:
    import aio_pika

    ch = await _channel()
    try:
        await ch.default_exchange.publish(aio_pika.Message(json.dumps(body).encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=queue)
    finally:
        await ch.close()


_bg: set[asyncio.Task] = set()


def kick_outbox() -> None:
    """Вызывать после commit: будит воркер (или доставляет в процессе, если брокера нет)."""
    async def run():
        try:
            if get_settings().rabbitmq_url:
                await _publish(OUTBOX_QUEUE, {"kick": True})
            else:
                await dispatch_pending()
        except Exception:  # noqa: BLE001
            log.exception("outbox kick failed")

    t = asyncio.get_event_loop().create_task(run())
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def run_job(name: str, args: dict) -> None:
    from app.services import jobs

    await jobs.HANDLERS[name](**args)


async def submit_job(name: str, args: dict) -> str:
    """Длительная операция: через RabbitMQ в воркер, без брокера — выполняется сразу. Возвращает режим."""
    if get_settings().rabbitmq_url:
        try:
            await _publish(JOBS_QUEUE, {"job": name, "args": args})
            return "queued"
        except Exception:  # noqa: BLE001 — брокер недоступен: выполняем в процессе, данные не теряются
            log.exception("rabbit unavailable, running job inline")
    await run_job(name, args)
    return "done"
