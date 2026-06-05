from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.db.session import engine
from app.log import get_logger
from app.routers.auth import router as auth_router
from app.routers.portfolio import router as portfolio_router
from app.routers.snapshots import router as snapshots_router
from app.routers.wallets import router as wallets_router
from app.routes import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("APP_ENV=%s", settings.app_env)
    logger.info("JWT_SECRET configured: %s", bool(settings.jwt_secret))
    logger.info("JWT_SECRET source: %s", settings.jwt_secret_source)
    if settings.using_dev_jwt_secret:
        logger.warning(
            "Using implicit DEV_JWT_SECRET — not for production. Set JWT_SECRET in .env."
        )
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.include_router(auth_router)
app.include_router(wallets_router)
app.include_router(snapshots_router)
app.include_router(portfolio_router)


@app.get("/")
async def root():
    return {"status": "ok"}
