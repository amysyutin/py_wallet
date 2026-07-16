import asyncio
from contextlib import asynccontextmanager
from time import time

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import engine
from app.db.session import SessionLocal
from app.log import get_logger
from app.metrics import (
    SNAPSHOT_SCHEDULER_JOBS,
    SNAPSHOT_SCHEDULER_LAST_TICK,
    SNAPSHOT_SCHEDULER_TICKS,
    SNAPSHOT_SCHEDULER_USERS,
    configure_build_info,
)
from app.db.models.wallet import Wallet
from app.routers.auth import router as auth_router
from app.routers.portfolio import router as portfolio_router
from app.routers.snapshot_jobs import router as snapshot_jobs_router
from app.routers.snapshots import legacy_router as snapshot_legacy_router
from app.routers.snapshots import router as snapshots_router
from app.routers.wallet_groups import router as wallet_groups_router
from app.routers.wallets import router as wallets_router
from app.routes import router
from app.services.snapshot_jobs import SnapshotServiceError, create_snapshot_job

logger = get_logger(__name__)
app_settings = get_settings()
configure_build_info(
    version=app_settings.app_version,
    sha=app_settings.build_sha,
    environment=app_settings.app_env,
)


async def _snapshot_scheduler_loop() -> None:
    settings = get_settings()
    interval = settings.snapshot_scheduler_interval_seconds
    while True:
        try:
            SNAPSHOT_SCHEDULER_LAST_TICK.set(time())
            async with SessionLocal() as session:
                rows = await session.execute(
                    select(Wallet.user_id).where(Wallet.is_active.is_(True)).distinct()
                )
                user_ids = [int(r.user_id) for r in rows]
            SNAPSHOT_SCHEDULER_USERS.observe(len(user_ids))

            if user_ids:
                logger.info(
                    "Snapshot scheduler tick: users=%s interval_seconds=%s",
                    len(user_ids),
                    interval,
                )
            for user_id in user_ids:
                try:
                    await run_in_threadpool(
                        create_snapshot_job,
                        settings,
                        user_id=user_id,
                        scope_type="all",
                        trigger_type="scheduler",
                    )
                except SnapshotServiceError:
                    SNAPSHOT_SCHEDULER_JOBS.labels(outcome="error").inc()
                    # Scheduler should keep running even if snapshot service fails.
                    continue
                else:
                    SNAPSHOT_SCHEDULER_JOBS.labels(outcome="success").inc()
            SNAPSHOT_SCHEDULER_TICKS.labels(outcome="success").inc()
        except Exception:
            SNAPSHOT_SCHEDULER_TICKS.labels(outcome="error").inc()
            logger.exception("Snapshot scheduler tick failed")

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("APP_ENV=%s", settings.app_env)
    logger.info("JWT_SECRET configured: %s", bool(settings.jwt_secret))
    logger.info("JWT_SECRET source: %s", settings.jwt_secret_source)
    logger.info("SNAPSHOT_SERVICE_URL=%s", settings.snapshot_service_url)
    logger.info(
        "SNAPSHOT_SERVICE_TIMEOUT_SECONDS=%s",
        settings.snapshot_service_timeout_seconds,
    )
    logger.info(
        "SNAPSHOT_INTERNAL_API_TOKEN configured: %s",
        bool(settings.snapshot_internal_api_token),
    )
    logger.info(
        "SNAPSHOT_AUTO_ON_WALLET_CREATE=%s", settings.snapshot_auto_on_wallet_create
    )
    logger.info(
        "SNAPSHOT_SCHEDULER_ENABLED=%s interval_seconds=%s",
        settings.snapshot_scheduler_enabled,
        settings.snapshot_scheduler_interval_seconds,
    )
    if settings.using_dev_jwt_secret:
        logger.warning(
            "Using implicit DEV_JWT_SECRET — not for production. Set JWT_SECRET in .env."
        )

    scheduler_task: asyncio.Task[None] | None = None
    if settings.snapshot_scheduler_enabled:
        scheduler_task = asyncio.create_task(_snapshot_scheduler_loop())

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
    await engine.dispose()


app = FastAPI(
    title="py_wallet",
    description="Crypto portfolio aggregation and monitoring service.",
    version=app_settings.app_version,
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(wallet_groups_router)
app.include_router(wallets_router)
app.include_router(snapshots_router)
app.include_router(snapshot_legacy_router)
app.include_router(snapshot_jobs_router)
app.include_router(portfolio_router)

Instrumentator().instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


@app.get("/")
async def root():
    return {"status": "ok"}
