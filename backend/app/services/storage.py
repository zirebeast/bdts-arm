"""Объектное хранилище: S3 (MinIO) в контуре, локальный каталог — в тестах и при отсутствии S3."""
import hashlib
import io
import mimetypes
import uuid
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models import FileObject
from app.permissions import CurrentUser


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3Storage:
    def __init__(self):
        from minio import Minio

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = Minio(s.s3_endpoint, access_key=s.s3_access_key, secret_key=s.s3_secret_key, secure=s.s3_secure)
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=mime)

    def get(self, key: str) -> bytes:
        resp = self.client.get_object(self.bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()


_storage = None


def storage():
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.s3_endpoint else LocalStorage(s.files_dir)
    return _storage


def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


async def save_file(session, data: bytes, name: str, entity_type: str, entity_id, kind: str = "attachment",
                    user: CurrentUser | None = None, mime: str | None = None) -> FileObject:
    mime = mime or guess_mime(name)
    key = f"{entity_type or 'misc'}/{entity_id or 'na'}/{uuid.uuid4().hex}/{name}"
    await run_in_threadpool(storage().put, key, data, mime)
    fo = FileObject(storage_key=key, name=name, mime=mime, size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    entity_type=entity_type, entity_id=str(entity_id), kind=kind, uploaded_by=user.fio if user else "Система",
                    uploader=user.username if user else "")
    session.add(fo)
    await session.flush()
    return fo


async def read_file(fo: FileObject) -> bytes:
    return await run_in_threadpool(storage().get, fo.storage_key)


async def _owner_deo(session, entity_type: str, entity_id: str) -> str | None:
    """ДЭО сущности, к которой привязан файл; None — владелец не определён (черновик, импорт, файл без привязки)."""
    from app.models import DoResult, EquipmentUnit, Survey, TechnicalReport, TsRecord

    if not entity_id or not entity_id.isdigit():
        return None
    eid = int(entity_id)
    if entity_type == "do_result":
        r = await session.get(DoResult, eid)
        return r.task.deo if r else None
    if entity_type in ("ts_record", "technical_report"):
        x = await session.get(TsRecord if entity_type == "ts_record" else TechnicalReport, eid)
        return (x.deo or "") if x else None
    if entity_type == "survey":
        s = await session.get(Survey, eid)
        eo = await session.get(EquipmentUnit, s.eo_id) if s else None
        return (eo.deo or "") if eo else None
    return None


async def can_access_file(session, fo: FileObject, user: CurrentUser) -> bool:
    """Доступ к файлу — по ДЭО сущности-владельца (как к самой записи). Файлы без владельца — загрузившему."""
    if not user.deo:
        return True  # пользователь без ограничения по ДЭО видит данные всех филиалов
    deo = await _owner_deo(session, fo.entity_type, fo.entity_id)
    if deo is None:
        return bool(fo.uploader) and fo.uploader == user.username
    return user.deo_allowed(deo)


async def can_bind_file(session, entity_type: str, entity_id: str, user: CurrentUser) -> bool:
    """Загрузка с привязкой к записи — только к записи своего ДЭО (иначе файл открылся бы чужому филиалу)."""
    if entity_type not in ("do_result", "ts_record", "technical_report", "survey") or not entity_id:
        return True
    deo = await _owner_deo(session, entity_type, entity_id)
    return deo is not None and user.deo_allowed(deo)
