"""Интеграционный слой: outbox исходящих событий, журнал обменов, логи загрузки данных (т.113, т.114)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OutboxEvent(Base):
    """Transactional outbox: событие пишется в одной транзакции с бизнес-изменением, доставляется воркером."""
    __tablename__ = "outbox_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(64), index=True)  # report.accepted | diag.defects | ps0.task | plan.list | notify.email
    payload: Mapped[dict] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), index=True, default="new")  # new | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationLog(Base):
    """Журнал обменов с внешними системами (W-8.1, W-7.1 «Интеграции»)."""
    __tablename__ = "integration_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    direction: Mapped[str] = mapped_column(String(8), default="in")  # in | out
    flow: Mapped[str] = mapped_column(String(255))
    system: Mapped[str] = mapped_column(String(128))
    adapter: Mapped[str] = mapped_column(String(32), default="mock")
    count: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="Успешно")
    username: Mapped[str] = mapped_column(String(255), default="")
    details: Mapped[dict] = mapped_column(default=dict)


class ImportLog(Base):
    """Лог (т.113): операция импорта/загрузки начальных данных."""
    __tablename__ = "import_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    name: Mapped[str] = mapped_column(String(128))
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    state: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | error
    total: Mapped[int] = mapped_column(Integer, default=0)
    loaded: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[int] = mapped_column(Integer, default=0)

    entries: Mapped[list["ImportLogEntry"]] = relationship(order_by="ImportLogEntry.id", cascade="all, delete-orphan", lazy="selectin")


class ImportLogEntry(Base):
    """Лог загрузки данных (т.114): строки хода операции."""
    __tablename__ = "import_log_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    log_id: Mapped[int] = mapped_column(ForeignKey("import_log.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(16), default="Информация")  # Информация | Предупреждение | Ошибка
    text: Mapped[str] = mapped_column(Text)
    row_ref: Mapped[str] = mapped_column(String(64), default="")
