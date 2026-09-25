"""Booking rules: conflicts, maintenance windows and quotas."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User
from .config import Rules
from .db import Blackout, Booking, from_db, to_db, utcnow

# Check-then-write must not interleave between requests (single process, SQLite).
write_lock = threading.Lock()

# Allow booking the slot that is already in progress (e.g. at 14:10, book 14:00–18:00).
START_GRACE = timedelta(hours=1)


class BookingError(Exception):
    pass


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
    local_insufficient: bool = False,
    purpose: str = "",
    now: datetime | None = None,
) -> None:
    """Raise BookingError with a user-facing message if the booking is not allowed.
    All datetimes are naive UTC."""
    now = now or utcnow()
    gpus = sorted(set(gpus))

    if not gpus:
        raise BookingError("請至少選一張 GPU")
    bad = [g for g in gpus if g < 0 or g >= gpu_count]
    if bad:
        raise BookingError(f"GPU {bad} 不存在（本機共 {gpu_count} 張，編號 0–{gpu_count - 1}）")
    if end <= start:
        raise BookingError("結束時間必須晚於開始時間")

    if existing is not None and existing.start <= now:
        # Booking already started: only its end time may change.
        if existing.end <= now and not user.is_admin:
            raise BookingError("已結束的預約不能修改")
        if start != existing.start or gpus != existing.gpu_list:
            raise BookingError("已開始的預約只能調整結束時間")
        if end <= now:
            raise BookingError("結束時間不能早於現在；要提前結束請按「取消 / 提前結束」")
    elif start < now - START_GRACE and not user.is_admin:
        raise BookingError("不能預約過去的時間")

    if not user.is_admin:
        hours = (end - start).total_seconds() / 3600
        if hours > rules.max_hours_per_booking:
            raise BookingError(f"單次預約最多 {rules.max_hours_per_booking:g} 小時（這次 {hours:.1f} 小時）")
        if start > now + timedelta(days=rules.max_days_ahead):
            raise BookingError(f"最多只能預約 {rules.max_days_ahead} 天內的時段")
        if rules.max_gpus_per_booking and len(gpus) > rules.max_gpus_per_booking:
            raise BookingError(f"單次預約最多 {rules.max_gpus_per_booking} 張 GPU")
        limit = rules.local_gpu_mem_gb
        mem_changed = existing is None or mem_gb != existing.mem_gb or local_insufficient != existing.local_insufficient
        if limit > 0 and mem_changed:
            if mem_gb is None:
                raise BookingError("請填寫預估需要的 GPU 記憶體（GB）")
            if mem_gb <= limit and not local_insufficient:
                raise BookingError(
                    f"預估只需要 {mem_gb:g} GB，本地顯卡（{limit:g} GB）應該跑得動，請先在自己的電腦上跑；"
                    f"如果本地真的跑不動，請勾選「本地跑不動」並在用途說明原因"
                )
            if mem_gb <= limit and not purpose.strip():
                raise BookingError("勾選「本地跑不動」時，請在用途說明原因（例如：太慢、要跑很多組參數）")
        exclude = existing.id if existing else None
        for ws, we in weeks_touched(start, end, tz):
            used = gpu_hours_in(s, user.username, ws, we, exclude_id=exclude)
            new = overlap_hours(start, end, ws, we) * len(gpus)
            if used + new > rules.max_gpu_hours_per_week + 1e-9:
                raise BookingError(
                    f"超過每週配額：{fmt_local(ws, tz)} 起這週已預約 {used:.1f} GPU·小時，"
                    f"加上這次 {new:.1f}，上限 {rules.max_gpu_hours_per_week:g}"
                )

    for bo in s.scalars(select(Blackout).where(Blackout.start < end, Blackout.end > start)):
        raise BookingError(f"與維護時段衝突：{fmt_local(bo.start, tz)}–{fmt_local(bo.end, tz)} {bo.reason}")

    for other in overlapping_bookings(s, start, end):
        if existing is not None and other.id == existing.id:
            continue
        shared = sorted(set(other.gpu_list) & set(gpus))
        if shared:
            raise BookingError(
                f"GPU {','.join(map(str, shared))} 在 {fmt_local(other.start, tz)}–{fmt_local(other.end, tz)} "
                f"已被 {other.username} 預約"
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
