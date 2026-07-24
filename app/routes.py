import asyncio
import re
from collections import OrderedDict
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from fastapi.routing import APIRouter
from app.config import ADDRESS_EVM
from app.core.config import get_settings
from app.db.models.snapshot_service import SNAPSHOT_SERVICE_TABLE_NAMES
from app.services.portfolio import summarize_all
from app.db.session import engine

router = APIRouter()

ASSETS_CACHE_TTL_SECONDS = 30.0
ASSETS_CACHE_MAX_ENTRIES = 256
ASSETS_MAX_CONCURRENT_LOOKUPS = 4
ASSETS_QUEUE_TIMEOUT_SECONDS = 0.25

_EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_assets_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_assets_cache_lock = Lock()
_assets_lookup_slots = asyncio.Semaphore(ASSETS_MAX_CONCURRENT_LOOKUPS)
_snapshot_schema_ready_sql = text(
    "SELECT "
    + " AND ".join(
        f"to_regclass('public.{table_name}') IS NOT NULL"
        for table_name in sorted(SNAPSHOT_SERVICE_TABLE_NAMES)
    )
)


def _resolve_assets_address(address: str) -> str:
    resolved = (address or ADDRESS_EVM).strip()
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EVM1_ADDRESS is not configured and address was not provided",
        )
    if _EVM_ADDRESS_RE.fullmatch(resolved) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid EVM address",
        )
    return resolved


def _get_cached_assets(cache_key: str) -> dict | None:
    now = monotonic()
    with _assets_cache_lock:
        entry = _assets_cache.pop(cache_key, None)
        if entry is None:
            return None
        cached_at, payload = entry
        if now - cached_at >= ASSETS_CACHE_TTL_SECONDS:
            return None
        _assets_cache[cache_key] = entry
        return payload


def _cache_assets(cache_key: str, payload: dict) -> None:
    with _assets_cache_lock:
        _assets_cache.pop(cache_key, None)
        _assets_cache[cache_key] = (monotonic(), payload)
        while len(_assets_cache) > ASSETS_CACHE_MAX_ENTRIES:
            _assets_cache.popitem(last=False)


def _clear_assets_cache() -> None:
    with _assets_cache_lock:
        _assets_cache.clear()


def _release_info() -> dict[str, str]:
    settings = get_settings()
    return {
        "version": settings.app_version,
        "build_sha": settings.build_sha,
    }


async def _assert_database_available(*, require_snapshot_schema: bool = False) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        if (
            require_snapshot_schema
            and get_settings().snapshot_schema_required
            and not await conn.scalar(_snapshot_schema_ready_sql)
        ):
            raise RuntimeError("snapshot-service schema unavailable")


@router.get("/health/live")
async def health_live():
    return {"status": "alive", **_release_info()}


@router.get("/health/ready")
async def health_ready():
    try:
        await _assert_database_available(require_snapshot_schema=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "ready", **_release_info()}


@router.get("/health")
async def health():
    try:
        await _assert_database_available()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "healthy", **_release_info()}


@router.get("/assets")
async def get_assets(address: str = ""):
    resolved = _resolve_assets_address(address)
    cache_key = resolved.lower()
    cached = _get_cached_assets(cache_key)
    if cached is not None:
        return cached

    try:
        async with asyncio.timeout(ASSETS_QUEUE_TIMEOUT_SECONDS):
            await _assets_lookup_slots.acquire()
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Asset lookup capacity is busy; retry shortly",
            headers={"Retry-After": "1"},
        )

    try:
        cached = _get_cached_assets(cache_key)
        if cached is not None:
            return cached
        summary = await run_in_threadpool(summarize_all, resolved)
        payload = summary.model_dump()
        _cache_assets(cache_key, payload)
        return payload
    finally:
        _assets_lookup_slots.release()
