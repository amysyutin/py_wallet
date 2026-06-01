from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import engine
from app.routers.auth import router as auth_router
from app.routers.portfolio import router as portfolio_router
from app.routers.snapshots import router as snapshots_router
from app.routers.wallets import router as wallets_router
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
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