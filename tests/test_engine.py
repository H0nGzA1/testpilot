"""Runnable check for the engine core — no DB, no browser needed.

python -m pytest tests/test_engine.py      (or)      python tests/test_engine.py
"""

from __future__ import annotations

import asyncio

from app.engine import aggregate, drain, resolve_attempts


def test_drain_isolates_failures_and_processes_all() -> None:
    async def handler(n: int):
        if n % 3 == 0:
            raise ValueError(f"boom {n}")
        return n * 10

    items = list(range(10))
    results = asyncio.run(drain(items, handler, concurrency=4))

    assert len(results) == len(items)  # every item handled despite failures
    failures = [r for r in results if isinstance(r, Exception)]
    oks = [r for r in results if not isinstance(r, Exception)]
    assert len(failures) == 4  # 0,3,6,9
    assert sorted(oks) == [n * 10 for n in items if n % 3 != 0]


def test_shared_slot_caps_concurrency_across_runs() -> None:
    """Two runs draining at per-run concurrency 5 (10 workers) share one slot(3):
    observed simultaneous handlers must never exceed 3 — the global budget holds
    across simultaneous runs."""
    live = 0
    peak = 0
    slot = None  # created inside the loop so the semaphore binds to it

    async def go() -> None:
        nonlocal live, peak, slot
        slot = asyncio.Semaphore(3)

        async def handler(_n: int):
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1

        await asyncio.gather(
            drain(list(range(8)), handler, concurrency=5, slot=slot),
            drain(list(range(8)), handler, concurrency=5, slot=slot),
        )

    asyncio.run(go())
    assert peak <= 3  # never exceeded the global cap despite 10 eager workers
    assert peak == 3  # and actually saturated it (not accidentally serialized)


def test_aggregate_counts_and_percentiles() -> None:
    summary = aggregate(
        ["passed", "passed", "failed", "error"],
        [100, 200, 300, 400],
    )
    assert summary["total"] == 4
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["error"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["latency_p50_ms"] == 250
    assert summary["latency_p95_ms"] == 400


def test_aggregate_empty() -> None:
    summary = aggregate([], [])
    assert summary["total"] == 0
    assert summary["pass_rate"] == 0.0
    assert summary["latency_p50_ms"] == 0


def test_resolve_attempts() -> None:
    assert resolve_attempts(["passed"]) == ("passed", False)  # first try, not flaky
    assert resolve_attempts(["error", "passed"]) == ("passed", True)  # retried into pass -> flaky
    assert resolve_attempts(["error", "error"]) == ("error", False)  # never passed
    assert resolve_attempts(["failed"]) == ("failed", False)  # genuine failure, not retried


if __name__ == "__main__":
    test_drain_isolates_failures_and_processes_all()
    test_shared_slot_caps_concurrency_across_runs()
    test_aggregate_counts_and_percentiles()
    test_aggregate_empty()
    test_resolve_attempts()
    print("engine self-check: OK")
