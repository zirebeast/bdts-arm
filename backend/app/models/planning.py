"""Δ Новая концепция: пообъектный план и объекты X/Y/Z, отбор к планированию, опросные листы, участки ВТД."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PlanObject(Base):
    """Объект диагностирования X/Y/Z, созданный по строке пообъектного плана или вручную (isLocal)."""
    __tablename__ = "plan_object"
    id: Mapped[int] = mapped_column(primary_key=True)
    cipher: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    facility_type: Mapped[str] = mapped_column(String(64), default="")
    reg_number: Mapped[str] = mapped_column(String(64), default="")
    hazard_class: Mapped[str] = mapped_column(String(8), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    commission_year: Mapped[str] = mapped_column(String(8), default="")
    survey_date: Mapped[date | None] = mapped_column(Date)
    work_kind: Mapped[str] = mapped_column(String(128), default="")
    pp_row: Mapped[str] = mapped_column(String(64), default="")
    plan_year: Mapped[int | None] = mapped_column(Integer)
    deo: Mapped[str] = mapped_column(String(32), index=True, default="")
    customer: Mapped[str] = mapped_column(String(64), default="")
    executor: Mapped[str] = mapped_column(String(64), default="ОРГ_1 (ГД)")
    lnk: Mapped[str] = mapped_column(String(64), default="")
    brigade: Mapped[str] = mapped_column(String(128), default="")
    tm_code: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="Не начато")
    eo_done: Mapped[int] = mapped_column(Integer, default=0)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(128), default="")
    raw: Mapped[dict] = mapped_column(default=dict)  # строка ПП в формате ХР.xlsx (col_*)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanObjectEo(Base):
    __tablename__ = "plan_object_eo"
    __table_args__ = (UniqueConstraint("object_id", "eo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("plan_object.id", ondelete="CASCADE"), index=True)
    eo_id: Mapped[int] = mapped_column(ForeignKey("equipment_unit.id", ondelete="CASCADE"))
    copied_from: Mapped[str] = mapped_column(String(64), default="")
    ps0_task: Mapped[str] = mapped_column(String(64), default="")


class PlanningMark(Base):
    """Метки плана по ЕО: «3-летний план» и «Следующий год» ставятся раздельно (D-PLN-02)."""
    __tablename__ = "planning_mark"
    eo_id: Mapped[int] = mapped_column(ForeignKey("equipment_unit.id", ondelete="CASCADE"), primary_key=True)
    mark_3y: Mapped[bool] = mapped_column(Boolean, default=False)
    mark_next_year: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlanningExport(Base):
    """История выгрузок перечней (D-PLN-01)."""
    __tablename__ = "planning_export"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    username: Mapped[str] = mapped_column(String(255))
    eo_ids: Mapped[list] = mapped_column(default=list)
    mark: Mapped[str] = mapped_column(String(64), default="")
    recipient: Mapped[str] = mapped_column(String(128), default="")
    criteria: Mapped[list] = mapped_column(default=list)


class SurveyTemplate(Base):
    """Опросный лист (шаблон на заполнение информации о ТМ и ЕО)."""
    __tablename__ = "survey_template"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    eq_class: Mapped[str] = mapped_column(String(64), default="Все классы ЕО")
    status: Mapped[str] = mapped_column(String(32), default="Черновик")  # Черновик | Опубликован
    questions: Mapped[list] = mapped_column(default=list)  # [{id, text, type, attr, req}]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Survey(Base):
    """Опрос по ЕО объекта X/Y/Z."""
    __tablename__ = "survey"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("plan_object.id", ondelete="CASCADE"), index=True)
    eo_id: Mapped[int] = mapped_column(ForeignKey("equipment_unit.id", ondelete="CASCADE"))
    template_id: Mapped[int] = mapped_column(ForeignKey("survey_template.id", ondelete="CASCADE"))
    owner: Mapped[str] = mapped_column(String(128), default="")
    due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="Не начат")  # Не начат | В работе | Заполнен | Принят
    answers: Mapped[dict] = mapped_column(default=dict)


class Discrepancy(Base):
    """Запрос на расхождение с БДО (закрывается статусом «Всё введено», D-DISC-01)."""
    __tablename__ = "discrepancy"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    eo_id: Mapped[int] = mapped_column(ForeignKey("equipment_unit.id", ondelete="CASCADE"))
    attr: Mapped[str] = mapped_column(String(128))
    bdo_value: Mapped[str] = mapped_column(String(255), default="")
    fact_value: Mapped[str] = mapped_column(String(255), default="")
    due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="Открыт")
    survey_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VtdSection(Base):
    """Участок ВТД (OQ-28): границы не пересекаются, смежность указана (D-VTD-01)."""
    __tablename__ = "vtd_section"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    pipeline: Mapped[str] = mapped_column(String(255))
    km_from: Mapped[float] = mapped_column(Float)
    km_to: Mapped[float] = mapped_column(Float)
    section_type: Mapped[str] = mapped_column(String(64), default="Подземный")
    deo: Mapped[str] = mapped_column(String(32), default="")
    tm_code: Mapped[str] = mapped_column(String(64), default="")
    adjacent_to: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="Действует")
    history: Mapped[list] = mapped_column(default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class VtdChamber(Base):
    """Камера запуска/приёма СОД."""
    __tablename__ = "vtd_chamber"
    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("vtd_section.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))  # launch | receive
    km: Mapped[float] = mapped_column(Float)
    permanent: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
