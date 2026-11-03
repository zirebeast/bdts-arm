"""Реестр фоновых заданий воркера (очередь bdts.jobs)."""
from app.services import ts

HANDLERS = {
    "import_xlsx": ts.run_import,
}
