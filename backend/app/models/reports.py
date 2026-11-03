"""Δ Технический отчёт (ТО) как отдельная сущность: 1 ТО → N ЕО (memo п.5, OQ-09)."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TechnicalReport(Base):
    __tablename__ = "technical_report"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(128), unique=True)
    report_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(500), default="")
    profile: Mapped[str] = mapped_column(String(32), default="")
    executor: Mapped[str] = mapped_column(String(255), default="")
    customer: Mapped[str] = mapped_column(String(255), default="")
    deo: Mapped[str] = mapped_column(String(32), index=True, default="")
    source: Mapped[str] = mapped_column(String(64), default="ИУС ГД (XML v3.8)")  # | Хозспособ | ИУС ГД (Файл)
    pp_line: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(64), index=True, default="Загружен")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    dict_snapshot: Mapped[str] = mapped_column(String(128), default="")
    opo: Mapped[dict] = mapped_column(default=dict)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("do_result.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["TechnicalReportVersion"]] = relationship(order_by="TechnicalReportVersion.version_no", cascade="all, delete-orphan", lazy="selectin")
    equipment: Mapped[list["TechnicalReportEo"]] = relationship(order_by="TechnicalReportEo.id", cascade="all, delete-orphan", lazy="selectin")
    history: Mapped[list["TechnicalReportHistory"]] = relationship(order_by="TechnicalReportHistory.id", cascade="all, delete-orphan", lazy="selectin")


class TechnicalReportVersion(Base):
    """Версия ТО (D-TO-01): XML в S3, разобранное содержимое и результат проверки."""
    __tablename__ = "technical_report_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("technical_report.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[int | None] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    attachment_ids: Mapped[list] = mapped_column(default=list)
    parsed: Mapped[dict] = mapped_column(default=dict)
    validation: Mapped[dict] = mapped_column(default=dict)  # {xsd_ok, issues:[{id, level, action, text, tab}]}
    validation_state: Mapped[str] = mapped_column(String(16), default="done")  # queued | done | error
    dict_snapshot: Mapped[str] = mapped_column(String(128), default="")
    uploaded_by: Mapped[str] = mapped_column(String(255), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TechnicalReportEo(Base):
    """ЕО из XML-отчёта и её сопоставление с ЕО МП-3 «БДО» (D-TO-04, D-TO-05)."""
    __tablename__ = "technical_report_eo"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("technical_report.id", ondelete="CASCADE"), index=True)
    xml_uid: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    eq_type: Mapped[str] = mapped_column(String(128), default="")
    steel: Mapped[str] = mapped_column(String(64), default="")
    s_nominal: Mapped[str] = mapped_column(String(32), default="")
    origin: Mapped[str] = mapped_column(String(32), default="imported")
    asupp_eo_id: Mapped[str] = mapped_column(String(64), default="")
    bdo_eo_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_unit.id"))
    repair_object: Mapped[bool] = mapped_column(default=False)  # «ЕО нет в БДО — объект ремонта» (D-TO-05)


class TechnicalReportHistory(Base):
    __tablename__ = "technical_report_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("technical_report.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    username: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default="")
