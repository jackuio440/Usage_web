"""SQLite storage. All datetimes are stored as naive UTC."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import Config, Rules


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_db(dt: datetime) -> datetime:
    """Aware datetime -> naive UTC for storage."""
    if dt.tzinfo is None:
        raise ValueError("datetime must include a timezone offset")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def from_db(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return from_db(dt).isoformat() if dt else None


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    gpus: Mapped[str] = mapped_column(String(128))  # comma separated GPU indexes, e.g. "0,1"
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime, index=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    mem_gb: Mapped[float | None] = mapped_column(Float, nullable=True)  # estimated GPU memory per GPU
    local_insufficient: Mapped[bool] = mapped_column(Boolean, default=False)  # "my local GPU can't run it"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def gpu_list(self) -> list[int]:
        return [int(g) for g in self.gpus.split(",") if g != ""]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "gpus": self.gpu_list,
            "start": iso(self.start),
            "end": iso(self.end),
            "purpose": self.purpose,
            "mem_gb": self.mem_gb,
            "local_insufficient": self.local_insufficient,
        }


class Blackout(Base):
    """Maintenance window: nobody can book any GPU during it."""

    __tablename__ = "blackouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": iso(self.start),
            "end": iso(self.end),
            "reason": self.reason,
            "created_by": self.created_by,
        }


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "body": self.body,
            "created_by": self.created_by,
            "created_at": iso(self.created_at),
        }


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self) -> dict:
        return {"id": self.id, "ts": iso(self.ts), "actor": self.actor, "action": self.action, "detail": self.detail}


class UsageHourly(Base):
    """Minutes each user had a process on each GPU, aggregated per hour (keeps the DB small)."""

    __tablename__ = "usage_hourly"
    __table_args__ = (UniqueConstraint("hour", "gpu", "username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hour: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC, truncated to the hour
    gpu: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(64))
    minutes: Mapped[float] = mapped_column(Float, default=0)
    unbooked_minutes: Mapped[float] = mapped_column(Float, default=0)
    max_mem_mb: Mapped[float] = mapped_column(Float, default=0)


class Database:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.engine = create_engine(
            f"sqlite:///{cfg.db_path}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def _pragmas(conn, _record):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def _add_missing_columns(self) -> None:
        """Tiny migration: add columns introduced after a database was created."""
        added = {"bookings": {"mem_gb": "FLOAT", "local_insufficient": "BOOLEAN NOT NULL DEFAULT 0"}}
        with self.engine.begin() as conn:
            for table, columns in added.items():
                have = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                for name, ddl in columns.items():
                    if name not in have:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def session(self) -> Session:
        return self.Session()

    # --- rules (config defaults, overridden by admin-edited settings) ---

    def get_rules(self) -> Rules:
        values = {k: getattr(self.cfg.rules, k) for k in Rules.keys()}
        with self.session() as s:
            for row in s.scalars(select(Setting).where(Setting.key.in_(Rules.keys()))):
                values[row.key] = json.loads(row.value)
        return Rules(**values)

    def set_rules(self, updates: dict) -> Rules:
        with self.session() as s:
            for key, value in updates.items():
                row = s.get(Setting, key)
                if row is None:
                    s.add(Setting(key=key, value=json.dumps(value)))
                else:
                    row.value = json.dumps(value)
            s.commit()
        return self.get_rules()

    def audit(self, s: Session, actor: str, action: str, detail: str = "") -> None:
        s.add(AuditLog(actor=actor, action=action, detail=detail))
