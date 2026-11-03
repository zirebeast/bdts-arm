"""Базовая схема MVP (все сущности модуля). Дальнейшие изменения — инкрементальными миграциями (alembic revision --autogenerate).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-25
"""
from alembic import op

import app.models  # noqa: F401
from app.db import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
