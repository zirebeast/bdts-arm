import os
import shutil
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="bdts-test-")
os.environ.update({"DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/test.db", "FILES_DIR": f"{_tmp}/files", "AUTH_MODE": "dev",
                   "RABBITMQ_URL": "", "S3_ENDPOINT": "", "SEED_ON_START": "true"})

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app, init_db  # noqa: E402


def H(user: str) -> dict:
    return {"Authorization": f"Bearer dev:{user}"}


@pytest.fixture(scope="session")
async def client():
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as c:
        yield c
    shutil.rmtree(_tmp, ignore_errors=True)
