"""Lease a free account from a role's candidate accounts so two cases never drive the
same account at once (which would collide sessions). Redis SET NX with a TTL when Redis
is configured (works across Celery workers); an in-process set otherwise.

The TTL is a safety net: if a worker dies mid-case the lease self-expires, so the
account isn't stuck leased forever.
"""

from __future__ import annotations

import asyncio
import time

from app.config import get_settings

_LOCAL_LEASED: set[int] = set()
_LOCAL_LOCK = asyncio.Lock()
_LOCAL_CAPTURING: set[int] = set()


async def capture_lock(cred_id: int, ttl_s: int) -> bool:
    """Single-flight guard for capturing a credential's session bundle: returns True to
    the ONE caller that may capture; others get False and should wait for the bundle to
    appear. Redis SET NX across workers; an in-process set otherwise. TTL self-expires if
    the capturer dies."""
    settings = get_settings()
    if settings.redis_url:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        try:
            return bool(await r.set(f"tp:capture:{cred_id}", "1", nx=True, ex=ttl_s))
        finally:
            await r.aclose()
    async with _LOCAL_LOCK:
        if cred_id in _LOCAL_CAPTURING:
            return False
        _LOCAL_CAPTURING.add(cred_id)
        return True


async def capture_unlock(cred_id: int) -> None:
    settings = get_settings()
    if settings.redis_url:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        try:
            await r.delete(f"tp:capture:{cred_id}")
        finally:
            await r.aclose()
    else:
        async with _LOCAL_LOCK:
            _LOCAL_CAPTURING.discard(cred_id)


async def acquire(candidate_ids: list[int], ttl_s: int, wait_s: int) -> int | None:
    """Lease one free id from candidate_ids, waiting up to wait_s for one to free.
    Returns the leased id, or None if none became free in time."""
    if not candidate_ids:
        return None
    end = time.monotonic() + max(0, wait_s)
    settings = get_settings()
    if settings.redis_url:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        try:
            while True:
                for aid in candidate_ids:
                    if await r.set(f"tp:lease:{aid}", "1", nx=True, ex=ttl_s):
                        return aid
                if time.monotonic() >= end:
                    return None
                await asyncio.sleep(1.0)
        finally:
            await r.aclose()
    else:
        while True:
            async with _LOCAL_LOCK:
                for aid in candidate_ids:
                    if aid not in _LOCAL_LEASED:
                        _LOCAL_LEASED.add(aid)
                        return aid
            if time.monotonic() >= end:
                return None
            await asyncio.sleep(0.2)


async def release(account_id: int | None) -> None:
    if account_id is None:
        return
    settings = get_settings()
    if settings.redis_url:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        try:
            await r.delete(f"tp:lease:{account_id}")
        finally:
            await r.aclose()
    else:
        async with _LOCAL_LOCK:
            _LOCAL_LEASED.discard(account_id)


async def run_slot_acquire(run_id: int, size: int, ttl_s: int, wait_s: int) -> int | None:
    """Take one of `size` slots for a run, waiting up to wait_s. This is what makes a
    project's concurrency setting real: fan_out_run hands every case to Celery at once, so
    without it the only cap was the worker's --concurrency (16), and a 49-case run opened
    16 browsers in the same instant — which is what turned one dead session into a login
    storm. Returns the slot number, or None if none freed up in time."""
    return await acquire([_run_slot_id(run_id, i) for i in range(max(1, size))], ttl_s, wait_s)


async def run_slot_release(slot: int | None) -> None:
    await release(slot)


def _run_slot_id(run_id: int, index: int) -> int:
    """Slot ids live in the same Redis keyspace as account leases, so keep them clear of
    real credential ids by offsetting far above any plausible primary key."""
    return _RUN_SLOT_BASE + run_id * _RUN_SLOT_STRIDE + index


_RUN_SLOT_BASE = 10_000_000
_RUN_SLOT_STRIDE = 1_000
