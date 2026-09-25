"""Admin API (members of the configured admin groups, e.g. sudo)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from . import bookings as bk
from .auth import User, require_admin
from .i18n import AppError
from .db import Announcement, AuditLog, Blackout, to_db
from .state import AppState, get_state

router = APIRouter(prefix="/api/admin")


class RulesIn(BaseModel):
    max_hours_per_booking: float = Field(gt=0, le=24 * 60)
    max_gpu_hours_per_week: float = Field(gt=0, le=24 * 7 * 64)
    max_days_ahead: int = Field(ge=1, le=365)
    max_gpus_per_booking: int = Field(ge=0, le=64)
    flag_unbooked_on_free_gpu: bool
    local_gpu_mem_gb: float = Field(ge=0, le=1024)


class BlackoutIn(BaseModel):
    start: AwareDatetime
    end: AwareDatetime
    reason: str = Field("", max_length=500)


class AnnouncementIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.get("/rules")
def get_rules(user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    return {"rules": st.db.get_rules().__dict__, "defaults": st.cfg.rules.__dict__}


@router.put("/rules")
def put_rules(body: RulesIn, user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    rules = st.db.set_rules(body.model_dump())
    with st.db.session() as s:
        st.db.audit(s, user.username, "update_rules", str(body.model_dump()))
        s.commit()
    return {"rules": rules.__dict__}


@router.get("/blackouts")
def list_blackouts(user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        return [b.to_dict() for b in s.scalars(select(Blackout).order_by(Blackout.start.desc()).limit(100))]


@router.post("/blackouts")
def create_blackout(body: BlackoutIn, user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    start, end = to_db(body.start), to_db(body.end)
    if end <= start:
        raise AppError("err.end_before_start", 400)
    with bk.write_lock, st.db.session() as s:
        b = Blackout(start=start, end=end, reason=body.reason.strip(), created_by=user.username)
        s.add(b)
        s.flush()
        st.db.audit(s, user.username, "create_blackout", f"#{b.id} {bk.fmt_local(start, st.cfg.tz)}–{bk.fmt_local(end, st.cfg.tz)} {b.reason}")
        # Existing bookings are not removed automatically; the admin decides.
        conflicts = [x.to_dict() for x in bk.overlapping_bookings(s, start, end)]
        s.commit()
        return {"blackout": b.to_dict(), "conflicting_bookings": conflicts}


@router.delete("/blackouts/{blackout_id}")
def delete_blackout(blackout_id: int, user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        b = s.get(Blackout, blackout_id)
        if b is None:
            raise AppError("err.blackout_not_found", 404)
        st.db.audit(s, user.username, "delete_blackout", f"#{b.id} {bk.fmt_local(b.start, st.cfg.tz)}–{bk.fmt_local(b.end, st.cfg.tz)} {b.reason}")
        s.delete(b)
        s.commit()
    return {"deleted": True}


@router.post("/announcements")
def create_announcement(body: AnnouncementIn, user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        a = Announcement(body=body.body.strip(), created_by=user.username)
        s.add(a)
        st.db.audit(s, user.username, "create_announcement", a.body[:200])
        s.commit()
        return a.to_dict()


@router.delete("/announcements/{announcement_id}")
def delete_announcement(announcement_id: int, user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        a = s.get(Announcement, announcement_id)
        if a is None:
            raise AppError("err.announcement_not_found", 404)
        st.db.audit(s, user.username, "delete_announcement", a.body[:200])
        s.delete(a)
        s.commit()
    return {"deleted": True}


@router.get("/audit")
def audit(limit: int = Query(200, ge=1, le=2000), user: User = Depends(require_admin), st: AppState = Depends(get_state)):
    with st.db.session() as s:
        return [r.to_dict() for r in s.scalars(select(AuditLog).order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(limit))]

