"""НСИ: справочники ТПР Б304–Б315 (универсальное хранение) и справочники модели ТО v3.8."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NsiRecord(Base):
    """Запись справочника НСИ (Б304…Б315). Состав полей задан схемой каталога (app.services.nsi_catalogs)."""
    __tablename__ = "nsi_record"
    __table_args__ = (UniqueConstraint("catalog", "record_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    catalog: Mapped[str] = mapped_column(String(8), index=True)  # B306 …
    record_no: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(default=dict)
    record_status: Mapped[str] = mapped_column(String(32), default="Действует")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str] = mapped_column(String(128), default="")


class Dict38Entry(Base):
    """Запись справочника модели ТО v3.8 (seed dictionaries_seed_v3_8.json): происхождение и статус верификации."""
    __tablename__ = "dict38_entry"
    __table_args__ = (UniqueConstraint("dictionary", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dictionary: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(500), default="")
    verification_status: Mapped[str] = mapped_column(String(16), default="confirmed")
    source_system: Mapped[str] = mapped_column(String(32), default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    quality_flags: Mapped[list] = mapped_column(default=list)
    payload: Mapped[dict] = mapped_column(default=dict)


class Dict38Version(Base):
    """Dictionary_Versions: версия справочника, ровно одна текущая (V-DIC-051)."""
    __tablename__ = "dict38_version"
    __table_args__ = (UniqueConstraint("dictionary", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dictionary: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    is_current: Mapped[bool] = mapped_column(default=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
