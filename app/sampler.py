"""Background task: record who is actually using which GPU, aggregated per hour."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from .auth import is_system_user
from .bookings import active_bookings
from .db import Database, UsageHourly, utcnow
from .gpu import GPUMonitor

log = logging.getLogger(__name__)


def record_sample(db: Database, monitor: GPUMonitor, minutes: float) -> None:
    gpus = monitor.read(max_age=0)
    now = utcnow()
    hour = now.replace(minute=0, second=0, microsecond=0)
    with db.session() as s:
        booked = active_bookings(s, now)
        for g in gpus:
            per_user: dict[str, float] = {}
            for p in g.processes:
                if is_system_user(p.username, db.cfg.min_uid):
                    continue
                per_user[p.username] = per_user.get(p.username, 0) + p.mem_mb
            for username, mem in per_user.items():
                row = s.scalar(
                    select(UsageHourly).where(UsageHourly.hour == hour, UsageHourly.gpu == g.index, UsageHourly.username == username)
                )
                if row is None:
                    row = UsageHourly(hour=hour, gpu=g.index, username=username, minutes=0, unbooked_minutes=0, max_mem_mb=0)
                    s.add(row)
                row.minutes += minutes
                b = booked.get(g.index)
                if b is None or b.username != username:
                    row.unbooked_minutes += minutes
                row.max_mem_mb = max(row.max_mem_mb, mem)
        s.commit()


def prune(db: Database, retention_days: int) -> None:
    with db.session() as s:
        s.execute(delete(UsageHourly).where(UsageHourly.hour < utcnow() - timedelta(days=retention_days)))
        s.commit()


async def run_sampler(db: Database, monitor: GPUMonitor, interval: int, retention_days: int) -> None:
    ticks = 0
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(record_sample, db, monitor, interval / 60)
            ticks += 1
            if ticks % max(1, 86400 // interval) == 1:
                await asyncio.to_thread(prune, db, retention_days)
        except Exception:  # noqa: BLE001 - never let the sampler die
            log.exception("usage sampling failed")
