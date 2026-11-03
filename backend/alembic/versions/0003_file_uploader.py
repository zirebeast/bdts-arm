"""file_object.uploader — логин загрузившего: доступ к файлу без записи-владельца проверяется по логину, а не по ФИО.

Revision ID: 0003_file_uploader
Revises: 0002_bind_result_files
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_file_uploader"
down_revision = "0002_bind_result_files"
branch_labels = None
depends_on = None


def upgrade():
    # Прежние файлы остаются с пустым логином: файл без владельца им не откроется никому, кроме пользователей без ограничения по ДЭО
    op.add_column("file_object", sa.Column("uploader", sa.String(128), nullable=False, server_default=""))


def downgrade():
    op.drop_column("file_object", "uploader")
