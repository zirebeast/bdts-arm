"""МП-3.5 «БДТС» — API модуля. OpenAPI: /api/docs."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from app import __version__
from app.api import admin, delta, me, process, reports, storage
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.errors import RuleError, rule_error_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bdts")

REQS = Counter("bdts_http_requests_total", "HTTP requests", ["method", "route", "status"])
LAT = Histogram("bdts_http_request_seconds", "HTTP latency", ["method", "route"])


async def init_db():
    """Схема создаётся миграциями Alembic (prod). Для SQLite/dev — create_all. Демо-данные — при пустой БД."""
    s = get_settings()
    if s.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if s.seed_on_start:
        from app.seed.loader import seed_if_empty

        async with SessionLocal() as session:
            await seed_if_empty(session)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="МП-3.5 «БДТС» API", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan,
                  description="База данных технического состояния оборудования (ЕЦП ДТОиР). Интеграции — через порты с mock-адаптерами.")
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
    app.add_exception_handler(RuleError, rule_error_handler)

    @app.middleware("http")
    async def metrics(request: Request, call_next):
        start = time.perf_counter()
        resp = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        REQS.labels(request.method, path, resp.status_code).inc()
        LAT.labels(request.method, path).observe(time.perf_counter() - start)
        return resp

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервиса БДТС. Введённые данные не потеряны — повторите запрос.", "rule": "ERR_BDTS_API"})

    for r in (me.router, process.router, reports.router, storage.router, admin.router, delta.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/api/health", include_in_schema=False)
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/ready", include_in_schema=False)
    async def ready():
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
        return {"status": "ready"}

    @app.get("/api/metrics", include_in_schema=False)
    async def prom():
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
