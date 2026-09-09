"""Budget — the token-budget window, parsed from the proxy's ``x-token-*``
headers (§1.3, BG §1.3, piece 2 of the six-piece minimum).

The developer never parses a header::

    fabric.budget.limit          # int  — tokens per window (x-token-limit)
    fabric.budget.remaining      # int  — from the last response (x-token-remaining)
    fabric.budget.reset_at       # datetime — observed_at + x-token-reset (ms delta)
    fabric.budget.observed_at    # datetime — freshness of the above
    fabric.budget.fraction_used  # 0.0-1.0 — (limit-remaining)/limit

Honest limitation (upstream gap #2): the gateway exposes budget **only in-band**.
There is no budget-query endpoint, so ``remaining`` is only as fresh as the last
call, and a brand-new process knows nothing until its first request returns.
``observed_at`` exists precisely so nobody mistakes stale data for live data — an
unobserved ``Budget`` (no call has returned yet) reports every field as ``None``,
never a misleading zero.

``x-token-reset`` is VERIFIED (LIVE) as **milliseconds *to* reset** — a delta, not
an epoch (docs/verified-apis.md §4) — so ``reset_at`` is anchored to
``observed_at`` the same way ``errors._retry_after`` treats the header.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx

from .errors import BudgetReserveReached

# The three budget headers, VERIFIED (LIVE) against the token-rate-limit policy
# (docs/verified-apis.md §4, row `Token rate limiting`). Named here so the one
# place that parses them is greppable.
LIMIT_HEADER = "x-token-limit"
REMAINING_HEADER = "x-token-remaining"
RESET_HEADER = "x-token-reset"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_int(raw: str | None) -> int | None:
    """A budget header as an int, or ``None`` if absent or non-numeric. Garbage is
    ignored rather than fatal (§0.3: never let an unexpected wire value crash the
    caller's request path)."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class Budget:
    """The token-budget window for one :class:`~agent_fabric.Fabric`, updated
    in-band from each response's ``x-token-*`` headers.

    Per-``Fabric``, never global: two instances with different credentials hold
    independent state. Construct empty (unobserved); :meth:`observe` mutates it
    from a response. Reads are cheap attribute/property access — no I/O.
    """

    def __init__(self) -> None:
        self.limit: int | None = None
        self.remaining: int | None = None
        self.reset_at: datetime | None = None
        self.observed_at: datetime | None = None

    @property
    def fraction_used(self) -> float | None:
        """Fraction of the window consumed, ``0.0``-``1.0``, or ``None`` while
        unobserved or when ``limit`` is non-positive (no window to divide by).
        Clamped: a ``remaining`` above ``limit`` (a window that reset between
        calls) reports ``0.0`` rather than a negative fraction."""
        if self.limit is None or self.remaining is None or self.limit <= 0:
            return None
        used = (self.limit - self.remaining) / self.limit
        return min(1.0, max(0.0, used))

    def observe(self, response: httpx.Response, *, now: datetime | None = None) -> None:
        """Update from a response's ``x-token-*`` headers.

        A response carrying **none** of the three headers is a defined no-op — the
        object stays exactly as it was (``observed_at`` unchanged), so a happy-path
        call without budget headers never resets freshness or raises. If at least
        one header is present, ``observed_at`` is stamped and each parseable header
        is applied; a missing or non-numeric individual header leaves that field
        untouched.

        ``now`` is injectable for tests; production passes nothing and the wall
        clock (UTC) is used.
        """
        headers = response.headers
        limit = _parse_int(headers.get(LIMIT_HEADER))
        remaining = _parse_int(headers.get(REMAINING_HEADER))
        reset_ms = _parse_int(headers.get(RESET_HEADER))

        if limit is None and remaining is None and reset_ms is None:
            return  # no budget signal on this response; nothing observed

        ts = now if now is not None else _utcnow()
        self.observed_at = ts
        if limit is not None:
            self.limit = limit
        if remaining is not None:
            self.remaining = remaining
        if reset_ms is not None:
            self.reset_at = ts + timedelta(milliseconds=reset_ms)

    @asynccontextmanager
    async def pace(self, *, reserve: float = 0.0) -> AsyncIterator[None]:
        """Guard a request so it is refused *before* it crosses your reserve, not
        after a 429 comes back (§1.3, #186).

        ``reserve`` is the fraction of the window to keep in hand (``0.0``-``1.0``):
        ``reserve=0.10`` trips at 90% used, ``reserve=0.0`` (the default) only at
        full exhaustion. On entry, if the observed :attr:`fraction_used` has reached
        ``1.0 - reserve``, :class:`~agent_fabric.core.errors.BudgetReserveReached` is
        raised and the guarded block never runs — so the request that would cross
        the reserve is never issued. Recover with :meth:`wait_for_reset` and retry::

            try:
                async with fabric.budget.pace(reserve=0.05):
                    await enrich(batch)
            except BudgetReserveReached:
                await fabric.budget.wait_for_reset()

        An **unobserved** budget (no call has returned yet, so
        :attr:`fraction_used` is ``None``) lets the block through: with nothing
        observed there is no basis to refuse, and blocking forever on a cold start
        would be worse than one request that discovers the real headroom.
        """
        if not 0.0 <= reserve <= 1.0:
            raise ValueError(f"reserve must be within [0.0, 1.0], got {reserve!r}")
        used = self.fraction_used
        if used is not None and used >= 1.0 - reserve:
            raise BudgetReserveReached(
                f"Budget reserve reached: {used:.1%} of the window used, "
                f"reserve is {reserve:.1%} (trips at {1.0 - reserve:.1%}).",
                fraction_used=used,
                reserve=reserve,
                reset_at=self.reset_at,
            )
        yield

    async def wait_for_reset(self, *, now: datetime | None = None) -> None:
        """Sleep until :attr:`reset_at`, then return — the recovery half of pacing
        (§1.3, #186).

        A single sleep, never a spin loop. If the window is unobserved
        (:attr:`reset_at` is ``None``) or already past, this returns immediately —
        there is nothing to wait for. ``now`` is injectable for tests; production
        passes nothing and the wall clock (UTC) is used.
        """
        if self.reset_at is None:
            return
        current = now if now is not None else _utcnow()
        delay = (self.reset_at - current).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
