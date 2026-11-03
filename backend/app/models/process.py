"""Процесс ДО: шаблоны Б302, задания Б301, результаты Б303."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DoTemplate(Base):
    """Б302 Шаблон задания на ДО. Разделы, подразделы, группы и параметры — в config (настраивают разработчики)."""
    __tablename__ = "do_template"
    id: Mapped[int] = mapped_column(primary_key=True)
    no: Mapped[int] = mapped_column(Integer, unique=True)
    vid: Mapped[str] = mapped_column(String(16), index=True)  # vessel | tpa | wellhead | grs
    name: Mapped[str] = mapped_column(String(255))
    profile: Mapped[str] = mapped_column(String(32), default="")
    config: Mapped[dict] = mapped_column(default=dict)  # {sections:[...]}


class DoTask(Base):
    """Б301 Задание на ДО."""
    __tablename__ = "do_task"
    id: Mapped[int] = mapped_column(primary_key=True)
    vid: Mapped[str] = mapped_column(String(16), index=True)
    xyz: Mapped[str] = mapped_column(String(64))
    eo_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_unit.id"))
    eo_name: Mapped[str] = mapped_column(String(255))
    deo: Mapped[str] = mapped_column(String(32), index=True)
    location: Mapped[str] = mapped_column(String(500))
    brigade: Mapped[str] = mapped_column(String(128))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("do_template.id"))
    template_name: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(64), index=True, default="Черновик")
    is_hs: Mapped[bool] = mapped_column(Boolean, default=False)  # Δ хозяйственный способ
    plan_object_id: Mapped[int | None] = mapped_column(ForeignKey("plan_object.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)  # оптимистическая блокировка
    created_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    history: Mapped[list["DoTaskHistory"]] = relationship(order_by="DoTaskHistory.id", cascade="all, delete-orphan", lazy="selectin")


class DoTaskHistory(Base):
    __tablename__ = "do_task_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("do_task.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    username: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str] = mapped_column(Text, default="")


class DoResult(Base):
    """Б303 Результат ДО (создаётся при согласовании задания, R-B301-06)."""
    __tablename__ = "do_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("do_task.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(64), index=True, default="ПЭ не завершен")
    to_formed: Mapped[bool] = mapped_column(Boolean, default=False)
    to_file_id: Mapped[int | None] = mapped_column(Integer)
    epb_file_id: Mapped[int | None] = mapped_column(Integer)
    vtd_file_ids: Mapped[list] = mapped_column(default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    task: Mapped[DoTask] = relationship(lazy="joined")
    history: Mapped[list["DoResultHistory"]] = relationship(order_by="DoResultHistory.id", cascade="all, delete-orphan", lazy="selectin")
    eos: Mapped[list["DoResultEo"]] = relationship(order_by="DoResultEo.idx", cascade="all, delete-orphan", lazy="selectin")


class DoResultEo(Base):
    """Единица оборудования в составе результата ДО (одно задание → N ЕО)."""
    __tablename__ = "do_result_eo"
    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("do_result.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    eo_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_unit.id"))
    label: Mapped[str] = mapped_column(String(255))


class DoResultSection(Base):
    """Данные раздела результата ДО по ЕО: измерения, чек-листы, таблицы, заключение специалиста."""
    __tablename__ = "do_result_section"
    __table_args__ = (UniqueConstraint("result_id", "eo_idx", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("do_result.id", ondelete="CASCADE"), index=True)
    eo_idx: Mapped[int] = mapped_column(Integer, default=0)
    code: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(default=dict)
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DoResultHistory(Base):
    __tablename__ = "do_result_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("do_result.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    username: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64))
    file: Mapped[str] = mapped_column(String(8), default="Нет")
    comment: Mapped[str] = mapped_column(Text, default="")
