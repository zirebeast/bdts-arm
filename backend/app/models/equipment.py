"""Хранилище ТС: ТМ, ЕО (реплика МП-3 «БДО») и записи о техническом состоянии Б316–Б319."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TechPlace(Base):
    """Техническое место (ТМ) — реплика МП-3 «БДО»."""
    __tablename__ = "tech_place"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tech_place.id"), index=True)
    deo: Mapped[str] = mapped_column(String(32), index=True)
    semantic_code: Mapped[str] = mapped_column(String(64), default="")
    sor_name: Mapped[str] = mapped_column(String(255), default="")
    attrs: Mapped[list] = mapped_column(default=list)  # [[code, name, value, unit]]
    confirm_status: Mapped[str] = mapped_column(String(32), default="Подтверждено")
    status_date: Mapped[date | None] = mapped_column(Date)
    record_status: Mapped[str] = mapped_column(String(32), default="Действует")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EquipmentUnit(Base):
    """Единица оборудования (ЕО) — реплика МП-3 «БДО» + ЕО, созданные в поле (origin=field_created)."""
    __tablename__ = "equipment_unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # EO-100294
    name: Mapped[str] = mapped_column(String(255), index=True)
    tm_id: Mapped[int | None] = mapped_column(ForeignKey("tech_place.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_unit.id"), index=True)
    deo: Mapped[str] = mapped_column(String(32), index=True)
    eq_class: Mapped[str] = mapped_column(String(64), default="")  # ТПА / Сосуды и аппараты / ФА / ГРС / ЛЧ МГ
    eq_type: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    factory_number: Mapped[str] = mapped_column(String(64), default="")
    tech_number: Mapped[str] = mapped_column(String(64), default="")
    inventory_number: Mapped[str] = mapped_column(String(64), default="")
    position: Mapped[str] = mapped_column(String(64), default="")
    manufacturer: Mapped[str] = mapped_column(String(255), default="")
    repair_object: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[str] = mapped_column(String(8), default="")
    dn: Mapped[str] = mapped_column(String(16), default="")
    pn: Mapped[str] = mapped_column(String(16), default="")
    s_calc: Mapped[str] = mapped_column(String(16), default="")
    steel_grade: Mapped[str] = mapped_column(String(64), default="")
    attrs: Mapped[list] = mapped_column(default=list)  # [[code, name, value, unit]]
    passport: Mapped[list] = mapped_column(default=list)  # [[label, value]] — для раздела «Общая информация»
    origin: Mapped[str] = mapped_column(String(16), default="asupp")  # asupp | field_created
    sync_status: Mapped[str] = mapped_column(String(16), default="synced")  # synced | pending | conflict
    sync_note: Mapped[str] = mapped_column(String(255), default="")
    has_passport: Mapped[bool] = mapped_column(default=True)
    confirm_status: Mapped[str] = mapped_column(String(32), default="Подтверждено")
    status_date: Mapped[date | None] = mapped_column(Date)
    record_status: Mapped[str] = mapped_column(String(32), default="Действует")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tm: Mapped[TechPlace | None] = relationship(lazy="joined")


class TsRecord(Base):
    """Б316 Запись о техническом состоянии."""
    __tablename__ = "ts_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)  # Б316-2026-00142
    record_type: Mapped[str] = mapped_column(String(64))  # Диагностическое обследование | Выполнение ТОиР | Выполнение КР
    tm_id: Mapped[int | None] = mapped_column(ForeignKey("tech_place.id"), index=True)
    eo_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_unit.id"), index=True)
    deo: Mapped[str] = mapped_column(String(32), index=True, default="")
    reg_date: Mapped[date] = mapped_column(Date)
    object_status: Mapped[str] = mapped_column(String(64), default="")
    wear_percent: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    next_inspection: Mapped[date | None] = mapped_column(Date)
    residual_life_years: Mapped[float | None] = mapped_column(Float)
    confirm_status: Mapped[str] = mapped_column(String(32), default="Требует подтверждения")
    status_date: Mapped[date | None] = mapped_column(Date)
    confirmed_by: Mapped[str] = mapped_column(String(128), default="")
    confirmed_by_position: Mapped[str] = mapped_column(String(128), default="")
    record_status: Mapped[str] = mapped_column(String(32), default="Действует")
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual | result | report | import
    result_id: Mapped[int | None] = mapped_column(ForeignKey("do_result.id"))
    report_id: Mapped[int | None] = mapped_column(ForeignKey("technical_report.id"))
    do_report: Mapped[dict] = mapped_column(default=dict)  # Б317 «Отчёт о ДО» (строка)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    eo: Mapped[EquipmentUnit | None] = relationship(lazy="joined")
    tm: Mapped[TechPlace | None] = relationship(lazy="joined")


class TsMeasurement(Base):
    """Б318 Документ измерения."""
    __tablename__ = "ts_measurement"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("ts_record.id", ondelete="CASCADE"), index=True)
    control_point: Mapped[str] = mapped_column(String(255))
    value_num: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="")
    value_text: Mapped[str] = mapped_column(String(255), default="")
    position: Mapped[str] = mapped_column(String(64), default="")
    area: Mapped[str] = mapped_column(String(255), default="")
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    instrument: Mapped[str] = mapped_column(String(255), default="")
    expert: Mapped[str] = mapped_column(String(128), default="")
    method: Mapped[str] = mapped_column(String(128), default="")


class TsMessage(Base):
    """Б319 Сообщение ТОиР (дефект/отказ)."""
    __tablename__ = "ts_message"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("ts_record.id", ondelete="CASCADE"), index=True)
    journal_no: Mapped[str] = mapped_column(String(32), default="")
    journal_date: Mapped[date | None] = mapped_column(Date)
    author: Mapped[str] = mapped_column(String(128), default="")
    kind: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    defect_code: Mapped[str] = mapped_column(String(32), default="")
    criticality: Mapped[str] = mapped_column(String(32), default="")
    fix_status: Mapped[str] = mapped_column(String(32), default="Не устранен")
    measurement_id: Mapped[int | None] = mapped_column(Integer)


class TsMeasure(Base):
    """Мероприятия КР и ТОиР по записи о ТС."""
    __tablename__ = "ts_measure"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("ts_record.id", ondelete="CASCADE"), index=True)
    pp_line: Mapped[str] = mapped_column(String(64), default="")
    order_no: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(64))
    executor: Mapped[str] = mapped_column(String(128), default="")
    plan_start: Mapped[date | None] = mapped_column(Date)
    fact_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    fact_end: Mapped[date | None] = mapped_column(Date)
    doc_no: Mapped[str] = mapped_column(String(64), default="")
    doc_date: Mapped[date | None] = mapped_column(Date)
    defect_no: Mapped[str] = mapped_column(String(64), default="")
    operations: Mapped[str] = mapped_column(Text, default="")
    parts: Mapped[str] = mapped_column(Text, default="")
    mtr_cost: Mapped[str] = mapped_column(String(32), default="")
    labor_cost: Mapped[str] = mapped_column(String(32), default="")
    fail_reason: Mapped[str] = mapped_column(Text, default="")
