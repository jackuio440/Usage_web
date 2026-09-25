"""JSON API used by the pages: GPU status, bookings, stats."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from . import bookings as bk
from .auth import User, current_user, is_system_user
from .db import Announcement, Blackout, Booking, UsageHourly, from_db, iso, to_db, utcnow
from .gpu import gpu_to_dict, system_status
from .state import AppState, get_state

router = APIRouter(prefix="/api")


class BookingIn(BaseModel):
    gpus: list[int]
    start: AwareDatetime
    end: AwareDatetime
    purpose: str = Field("", max_length=500)
    mem_gb: float | None = Field(None, gt=0, le=1024)
    local_insufficient: bool = False


def parse_query_dt(value: str, st: AppState) -> datetime:
    """FullCalendar range params -> naive UTC. Naive values are read as local site time."""
    try:
        dt = datetime.fromisoformat(value.replace(" ", "+").replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(400, f"時間格式錯誤：{value}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=st.cfg.tz)
    return to_db(dt)


@router.get("/status")
def status(user: User = Depends(current_user), st: AppState = Depends(get_state)):
    gpus = st.monitor.read()
    rules = st.db.get_rules()
    now = utcnow()
    with st.db.session() as s:
        current = bk.active_bookings(s, now)
        upcoming = bk.next_bookings(s, now)
        announcements = [a.to_dict() for a in s.scalars(select(Announcement).order_by(Announcement.created_at.desc()).limit(5))]
        blackouts = [
            b.to_dict()
            for b in s.scalars(select(Blackout).where(Blackout.end > now, Blackout.start < now + timedelta(days=14)).order_by(Blackout.start))
        ]

    out = []
    for g in gpus:
        d = gpu_to_dict(g)
        booking = current.get(g.index)
        d["booking"] = booking.to_dict() if booking else None
        d["next_booking"] = upcoming[g.index].to_dict() if g.index in upcoming else None
        for p in d["processes"]:
            if is_system_user(p["username"], st.cfg.min_uid):
                p["flag"] = "system"
            elif booking is None:
                p["flag"] = "unbooked" if rules.flag_unbooked_on_free_gpu else "ok"
            elif booking.username == p["username"]:
                p["flag"] = "ok"
            else:
                p["flag"] = "conflict"  # using a GPU someone else booked
        out.append(d)

    return {
        "now": iso(now),
        "gpus": out,
        "gpu_error": st.monitor.error,
        "system": system_status(st.cfg.disk_paths),
        "announcements": announcements,
        "blackouts": blackouts,
    }


@router.get("/events")
def events(
    start: str = Query(...),
    end: str = Query(...),
    user: User = Depends(current_user),
    st: AppState = Depends(get_state),
):
    s_utc, e_utc = parse_query_dt(start, st), parse_query_dt(end, st)
    with st.db.session() as s:
        bookings = [b.to_dict() for b in bk.overlapping_bookings(s, s_utc, e_utc)]
        blackouts = [b.to_dict() for b in s.scalars(select(Blackout).where(Blackout.start < e_utc, Blackout.end > s_utc))]
    return {"bookings": bookings, "blackouts": blackouts}


def _validate(st: AppState, s, user: User, body: BookingIn, existing: Booking | None = None):
    try:
        bk.validate(
            s,
            user=user,
            rules=st.db.get_rules(),
            gpu_count=st.monitor.gpu_count(),
            tz=st.cfg.tz,
            gpus=body.gpus,
            start=to_db(body.start),
            end=to_db(body.end),
            existing=existing,
            mem_gb=body.mem_gb,
            local_insufficient=body.local_insufficient,
            purpose=body.purpose,
        )
    except bk.BookingError as e:
        raise HTTPException(409, str(e)) from e


def _span(st: AppState, start: datetime, end: datetime) -> str:
    return f"{bk.fmt_local(start, st.cfg.tz)}–{bk.fmt_local(end, st.cfg.tz)}"


def _gpus_str(gpus: list[int]) -> str:
    return ",".join(str(g) for g in sorted(set(gpus)))


@router.post("/bookings")
def create_booking(body: BookingIn, user: User = Depends(current_user), st: AppState = Depends(get_state)):
    with bk.write_lock, st.db.session() as s:
        _validate(st, s, user, body)
        b = Booking(
            username=user.username,
            gpus=_gpus_str(body.gpus),
            start=to_db(body.start),
            end=to_db(body.end),
            purpose=body.purpose.strip(),
            mem_gb=body.mem_gb,
            local_insufficient=body.local_insufficient,
        )
        s.add(b)
        s.flush()
        st.db.audit(s, user.username, "create_booking", f"#{b.id} GPU {b.gpus} {_span(st, b.start, b.end)}")
        s.commit()
        return b.to_dict()


def _get_owned(s, booking_id: int, user: User) -> Booking:
    b = s.get(Booking, booking_id)
    if b is None:
        raise HTTPException(404, "找不到這筆預約")
    if b.username != user.username and not user.is_admin:
        raise HTTPException(403, "只能修改自己的預約")
    return b


@router.patch("/bookings/{booking_id}")
def update_booking(booking_id: int, body: BookingIn, user: User = Depends(current_user), st: AppState = Depends(get_state)):
    with bk.write_lock, st.db.session() as s:
        b = _get_owned(s, booking_id, user)
        _validate(st, s, user, body, existing=b)
        b.gpus, b.start, b.end, b.purpose = _gpus_str(body.gpus), to_db(body.start), to_db(body.end), body.purpose.strip()
        b.mem_gb, b.local_insufficient = body.mem_gb, body.local_insufficient
        st.db.audit(s, user.username, "update_booking", f"#{b.id} ({b.username}) GPU {b.gpus} {_span(st, b.start, b.end)}")
        s.commit()
        return b.to_dict()


@router.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int, user: User = Depends(current_user), st: AppState = Depends(get_state)):
    """Future booking: removed. Running booking: ended now (kept for history). Past: admin only."""
    now = utcnow().replace(second=0, microsecond=0)
    with bk.write_lock, st.db.session() as s:
        b = _get_owned(s, booking_id, user)
        if b.start <= now < b.end:
            b.end = max(now, b.start + timedelta(minutes=1))
            st.db.audit(s, user.username, "end_booking_early", f"#{b.id} ({b.username})")
            result = {"ended": True, "booking": b.to_dict()}
        elif b.end <= now and not user.is_admin:
            raise HTTPException(409, "已結束的預約會保留作為紀錄，不能刪除")
        else:
            st.db.audit(s, user.username, "delete_booking", f"#{b.id} ({b.username}) GPU {b.gpus} {_span(st, b.start, b.end)}")
            s.delete(b)
            result = {"deleted": True}
        s.commit()
        return result


@router.get("/me")
def me(user: User = Depends(current_user), st: AppState = Depends(get_state)):
    rules = st.db.get_rules()
    now = utcnow()
    ws = bk.week_start(now, st.cfg.tz)
    we = to_db(from_db(ws).astimezone(st.cfg.tz) + timedelta(days=7))
    with st.db.session() as s:
        used = bk.gpu_hours_in(s, user.username, ws, we)
        mine = s.scalars(
            select(Booking)
            .where(Booking.username == user.username, Booking.end > now - timedelta(days=30))
            .order_by(Booking.start.desc())
        )
        items = [b.to_dict() for b in mine]
    return {
        "username": user.username,
        "is_admin": user.is_admin,
        "gpu_count": st.monitor.gpu_count(),
        "rules": rules.__dict__,
        "week_start": iso(ws),
        "week_gpu_hours": round(used, 2),
        "bookings": items,
    }


@router.get("/stats")
def stats(weeks: int = Query(4, ge=1, le=26), user: User = Depends(current_user), st: AppState = Depends(get_state)):
    """Per user and week: GPU-hours booked vs. GPU-hours actually used (sampled)."""
    tz = st.cfg.tz
    this_week = bk.week_start(utcnow(), tz)
    result = []
    with st.db.session() as s:
        for i in range(weeks):
            ws = to_db(from_db(this_week).astimezone(tz) - timedelta(days=7 * i))
            we = to_db(from_db(ws).astimezone(tz) + timedelta(days=7))
            rows: dict[str, dict] = {}

            def row(name: str) -> dict:
                return rows.setdefault(name, {"username": name, "booked": 0.0, "used": 0.0, "unbooked": 0.0, "peak_mem_gb": 0.0})

            for b in bk.overlapping_bookings(s, ws, we):
                row(b.username)["booked"] += bk.overlap_hours(b.start, b.end, ws, we) * len(b.gpu_list)
            for u in s.scalars(select(UsageHourly).where(UsageHourly.hour >= ws, UsageHourly.hour < we)):
                r = row(u.username)
                r["used"] += u.minutes / 60
                r["unbooked"] += u.unbooked_minutes / 60
                r["peak_mem_gb"] = max(r["peak_mem_gb"], u.max_mem_mb / 1024)
            users = sorted(rows.values(), key=lambda r: -(r["booked"] + r["used"]))
            for r in users:
                for k in ("booked", "used", "unbooked", "peak_mem_gb"):
                    r[k] = round(r[k], 1)
            result.append({"week_start": iso(ws), "users": users})
    return {"weeks": result}


@router.get("/announcements")
def announcements(user: User = Depends(current_user), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        return [a.to_dict() for a in s.scalars(select(Announcement).order_by(Announcement.created_at.desc()).limit(50))]
