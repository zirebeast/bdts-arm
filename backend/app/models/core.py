"""Общие сущности: организации, бригады, файлы, уведомления, аудит, настройки."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Organization(Base):
    """Организации (НСИ ЕЦП): ДЭО, ГД, подрядчики."""
    __tablename__ = "organization"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="deo")  # deo | gd | contractor
    details: Mapped[dict] = mapped_column(default=dict)  # реквизиты (НСИ ЕЦП, mock): руководитель, адрес, телефон, e-mail, аттестат ЛНК


class Brigade(Base):
    """Бригады (источник не описан, OQ-11)."""
    __tablename__ = "brigade"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    org_code: Mapped[str] = mapped_column(String(32), default="ОРГ_1")
    members: Mapped[list] = mapped_column(default=list)  # [{fio, level, cert, methods[], valid_until}]


class FileObject(Base):
    """Файл в объектном хранилище (S3) с привязкой к сущности."""
    __tablename__ = "file_object"
    id: Mapped[int] = mapped_column(primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    entity_type: Mapped[str] = mapped_column(String(32), index=True, default="")
    entity_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    kind: Mapped[str] = mapped_column(String(32), default="attachment")
    uploaded_by: Mapped[str] = mapped_column(String(128), default="")
    uploader: Mapped[str] = mapped_column(String(128), default="")  # логин загрузившего (уникален, в отличие от ФИО)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Base):
    """Уведомление «колокольчика» (адресовано роли и/или пользователю)."""
    __tablename__ = "notification"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32), index=True, default="")
    username: Mapped[str] = mapped_column(String(128), index=True, default="")
    deo: Mapped[str] = mapped_column(String(32), default="")
    type: Mapped[str] = mapped_column(String(32), default="Информация")
    title: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationState(Base):
    """Прочитано/помечено — отдельно для каждого пользователя."""
    __tablename__ = "notification_state"
    notification_id: Mapped[int] = mapped_column(ForeignKey("notification.id", ondelete="CASCADE"), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    """Журнал событий аудита (сервис Journal платформы)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    username: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict] = mapped_column(default=dict)


class ModuleSetting(Base):
    """Настройки модуля W-7.1: ключ → JSON (маршруты, правила оповещений, права, отчётный период)."""
    __tablename__ = "module_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str] = mapped_column(String(128), default="")


class SavedSearch(Base):
    """Личные шаблоны поиска пользователя (D-SRCH-01, OQ-15)."""
    __tablename__ = "saved_search"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    query: Mapped[str] = mapped_column(String(1000), default="")
    filters: Mapped[list] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
