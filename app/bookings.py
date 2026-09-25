"""Booking rules: conflicts, maintenance windows and quotas."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User
from .config import Rules
from .i18n import AppError
from .db import Blackout, Booking, from_db, to_db, utcnow

# Check-then-write must not interleave between requests (single process, SQLite).
write_lock = threading.Lock()

# Allow booking the slot that is already in progress (e.g. at 14:10, book 14:00–18:00).
START_GRACE = timedelta(hours=1)


class BookingError(AppError):
    status = 409


def fmt_local(dt: datetime, tz: ZoneInfo) -> str:
    return from_db(dt).astimezone(tz).strftime("%m/%d %H:%M")


def week_start(dt_utc: datetime, tz: ZoneInfo) -> datetime:
    """Monday 00:00 (local time) of the week containing dt, returned as naive UTC."""
    local = from_db(dt_utc).astimezone(tz)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_db(monday)


def weeks_touched(start: datetime, end: datetime, tz: ZoneInfo) -> list[tuple[datetime, datetime]]:
    weeks = []
    ws = week_start(start, tz)
    while ws < end:
        we = to_db(from_db(ws).astimezone(tz) + timedelta(days=7))  # wall-clock +7 days, DST safe
        weeks.append((ws, we))
        ws = we
    return weeks


def overlap_hours(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    secs = (min(a_end, b_end) - max(a_start, b_start)).total_seconds()
    return max(secs, 0) / 3600


def gpu_hours_in(s: Session, username: str, start: datetime, end: datetime, exclude_id: int | None = None) -> float:
    q = select(Booking).where(Booking.username == username, Booking.start < end, Booking.end > start)
    total = 0.0
    for b in s.scalars(q):
        if b.id != exclude_id:
            total += overlap_hours(b.start, b.end, start, end) * len(b.gpu_list)
    return total


def overlapping_bookings(s: Session, start: datetime, end: datetime) -> list[Booking]:
    return list(s.scalars(select(Booking).where(Booking.start < end, Booking.end > start).order_by(Booking.start)))


def validate(
    s: Session,
    *,
    user: User,
    rules: Rules,
    gpu_count: int,
    tz: ZoneInfo,
    gpus: list[int],
    start: datetime,
    end: datetime,
    existing: Booking | None = None,
    mem_gb: float | None = None,
    now: datetime | None = None,
) -> None:
    """Raise BookingError (a translatable message key) if the booking is not allowed.
    All datetimes are naive UTC."""
    now = now or utcnow()
    gpus = sorted(set(gpus))

    if not gpus:
        raise BookingError("err.no_gpu")
    bad = [g for g in gpus if g < 0 or g >= gpu_count]
    if bad:
        raise BookingError("err.bad_gpu", bad=bad, count=gpu_count, last=gpu_count - 1)
    if end <= start:
        raise BookingError("err.end_before_start")

    if existing is not None and existing.start <= now:
        # Booking already started: only its end time may change.
        if existing.end <= now and not user.is_admin:
            raise BookingError("err.ended_readonly")
        if start != existing.start or gpus != existing.gpu_list:
            raise BookingError("err.started_only_end")
        if end <= now:
            raise BookingError("err.end_in_past")
    elif start < now - START_GRACE and not user.is_admin:
        raise BookingError("err.past")

    if not user.is_admin:
        hours = (end - start).total_seconds() / 3600
        if hours > rules.max_hours_per_booking:
            raise BookingError("err.too_long", max=f"{rules.max_hours_per_booking:g}", hours=f"{hours:.1f}")
        if start > now + timedelta(days=rules.max_days_ahead):
            raise BookingError("err.too_far", days=rules.max_days_ahead)
        if rules.max_gpus_per_booking and len(gpus) > rules.max_gpus_per_booking:
            raise BookingError("err.too_many_gpus", max=rules.max_gpus_per_booking)
        # The estimate drives the "run it locally" reminder in the booking dialog; it never blocks.
        if rules.local_gpu_mem_gb > 0 and mem_gb is None and (existing is None or existing.mem_gb is not None):
            raise BookingError("err.mem_required")
        exclude = existing.id if existing else None
        for ws, we in weeks_touched(start, end, tz):
            used = gpu_hours_in(s, user.username, ws, we, exclude_id=exclude)
            new = overlap_hours(start, end, ws, we) * len(gpus)
            if used + new > rules.max_gpu_hours_per_week + 1e-9:
                raise BookingError(
                    "err.quota", week=fmt_local(ws, tz), used=f"{used:.1f}", new=f"{new:.1f}",
                    max=f"{rules.max_gpu_hours_per_week:g}",
                )

    for bo in s.scalars(select(Blackout).where(Blackout.start < end, Blackout.end > start)):
        raise BookingError("err.blackout", start=fmt_local(bo.start, tz), end=fmt_local(bo.end, tz), reason=bo.reason)

    for other in overlapping_bookings(s, start, end):
        if existing is not None and other.id == existing.id:
            continue
        shared = sorted(set(other.gpu_list) & set(gpus))
        if shared:
            raise BookingError(
                "err.conflict", gpus=",".join(map(str, shared)), user=other.username,
                start=fmt_local(other.start, tz), end=fmt_local(other.end, tz),
            )


def active_bookings(s: Session, at: datetime) -> dict[int, Booking]:
    """GPU index -> booking covering the given moment."""
    result = {}
    for b in s.scalars(select(Booking).where(Booking.start <= at, Booking.end > at)):
        for g in b.gpu_list:
            result[g] = b
    return result


def next_bookings(s: Session, at: datetime, within: timedelta = timedelta(days=7)) -> dict[int, Booking]:
    """GPU index -> next booking starting after the given moment."""
    result: dict[int, Booking] = {}
    q = select(Booking).where(Booking.start > at, Booking.start < at + within).order_by(Booking.start)
    for b in s.scalars(q):
        for g in b.gpu_list:
            result.setdefault(g, b)
    return result
