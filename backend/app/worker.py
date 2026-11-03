"""Воркер (TasksWorker): очереди RabbitMQ bdts.jobs (импорт и др. длительные операции) и bdts.outbox (доставка в адаптеры).

Дополнительно раз в 30 с выбирает недоставленные события outbox — гарантированная доставка при сбоях брокера/адаптера.
"""
import asyncio
import json
import logging

import aio_pika

from app.config import get_settings
from app.services.events import JOBS_QUEUE, OUTBOX_QUEUE, dispatch_pending, run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger("bdts.worker")


async def sweeper():
    while True:
        try:
            n = await dispatch_pending()
            if n:
                log.info("outbox sweep: delivered %s", n)
        except Exception:  # noqa: BLE001
            log.exception("outbox sweep failed")
        await asyncio.sleep(30)


async def main():
    url = get_settings().rabbitmq_url
    conn = await aio_pika.connect_robust(url)
    ch = await conn.channel()
    await ch.set_qos(prefetch_count=4)
    jobs = await ch.declare_queue(JOBS_QUEUE, durable=True)
    outbox = await ch.declare_queue(OUTBOX_QUEUE, durable=True)

    async def on_job(msg: aio_pika.IncomingMessage):
        async with msg.process(requeue=False):
            body = json.loads(msg.body)
            log.info("job %s %s", body.get("job"), body.get("args"))
            await run_job(body["job"], body.get("args", {}))

    async def on_outbox(msg: aio_pika.IncomingMessage):
        async with msg.process(requeue=False):
            await dispatch_pending()

    await jobs.consume(on_job)
    await outbox.consume(on_outbox)
    log.info("worker started")
    await sweeper()


if __name__ == "__main__":
    asyncio.run(main())
