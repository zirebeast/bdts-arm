"""Привязать к результату ДО файлы, загруженные без entity_id (фото разделов, ЭПБ, ВТД): доступ к файлам — по ДЭО владельца.

Revision ID: 0002_bind_result_files
Revises: 0001_baseline
Create Date: 2026-11-03
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0002_bind_result_files"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _j(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


def upgrade():
    conn = op.get_bind()
    refs: dict[int, set[int]] = {}  # file_id → результаты ДО, которые на него ссылаются
    for rid, epb, vtd in conn.execute(sa.text("SELECT id, epb_file_id, vtd_file_ids FROM do_result")):
        for fid in [epb, *(_j(vtd) or [])]:
            if fid:
                refs.setdefault(int(fid), set()).add(rid)
    for rid, data in conn.execute(sa.text("SELECT result_id, data FROM do_result_section")):
        for ph in _j(data).get("photos") or []:
            if isinstance(ph, dict) and str(ph.get("id", "")).isdigit():
                refs.setdefault(int(ph["id"]), set()).add(rid)
    upd = sa.text("UPDATE file_object SET entity_id = :rid WHERE id = :fid AND entity_type = 'do_result' AND entity_id = ''")
    # Ссылки на файлы приходили от клиента: привязываем, только если владелец однозначен; остальное — на ручной разбор
    for fid, rids in refs.items():
        if len(rids) == 1:
            conn.execute(upd, {"fid": fid, "rid": str(next(iter(rids)))})
        else:
            print(f"0002: файл {fid} упоминается в нескольких результатах ДО {sorted(rids)} — оставлен без привязки")


def downgrade():
    pass  # привязка не ломает прежнее поведение
