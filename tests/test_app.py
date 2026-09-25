from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Config, Rules
from app.main import create_app

H = {"X-Requested-With": "fetch"}


def at(hours: float) -> str:
    """ISO time `hours` from now, on a whole minute."""
    t = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=hours)
    return t.isoformat()


@pytest.fixture
def app(tmp_path):
    cfg = Config(data_dir=tmp_path, secret_key="test", mock=True, mock_gpu_count=4,
                 rules=Rules(max_hours_per_booking=24, max_gpu_hours_per_week=30, max_days_ahead=14))
    return create_app(cfg, start_sampler=False)


def login(app, name: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"username": name, "password": "test"}, follow_redirects=False)
    assert r.status_code == 303
    return c


@pytest.fixture
def alice(app):
    return login(app, "alice")


@pytest.fixture
def bob(app):
    return login(app, "bob")


@pytest.fixture
def admin(app):
    return login(app, "admin1")


def book(c, gpus, start, end, purpose="", mem_gb=20, local_insufficient=False):
    body = {"gpus": gpus, "start": start, "end": end, "purpose": purpose,
            "mem_gb": mem_gb, "local_insufficient": local_insufficient}
    return c.post("/api/bookings", json=body, headers=H)


def test_requires_login(app):
    c = TestClient(app)
    assert c.get("/api/status").status_code == 401
    assert c.get("/", follow_redirects=False).status_code == 303


def test_wrong_password_and_lockout(app):
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/login", data={"username": "eve", "password": "x"}).status_code == 401
    r = c.post("/login", data={"username": "eve", "password": "test"})
    assert r.status_code == 429


def test_status(alice):
    d = alice.get("/api/status").json()
    assert len(d["gpus"]) == 4
    assert "cpu_percent" in d["system"]


def test_write_requires_header(alice):
    r = alice.post("/api/bookings", json={"gpus": [0], "start": at(1), "end": at(2)})
    assert r.status_code == 403


def test_conflict_on_same_gpu(alice, bob):
    assert book(alice, [0, 1], at(1), at(3)).status_code == 200
    r = book(bob, [1, 2], at(2), at(4))
    assert r.status_code == 409 and "alice" in r.json()["detail"]
    # other GPUs, or back-to-back on the same GPU, are fine
    assert book(bob, [2, 3], at(2), at(4)).status_code == 200
    assert book(bob, [0], at(3), at(4)).status_code == 200


def test_rules(alice):
    assert book(alice, [0], at(2), at(1)).status_code == 409  # end before start
    assert book(alice, [9], at(1), at(2)).status_code == 409  # no such GPU
    assert book(alice, [], at(1), at(2)).status_code == 409
    assert book(alice, [0], at(-5), at(-3)).status_code == 409  # past
    assert book(alice, [0], at(1), at(30)).status_code == 409  # > 24h per booking
    assert book(alice, [0], at(24 * 20), at(24 * 20 + 1)).status_code == 409  # too far ahead


def test_weekly_quota_counts_gpu_hours(alice):
    # 30 GPU-hours per week: 4 GPUs x 8h = 32 is too much
    r = book(alice, [0, 1, 2, 3], at(1), at(9))
    assert r.status_code == 409 and "配額" in r.json()["detail"]


def test_admin_exempt_from_quota_but_not_conflicts(admin, alice):
    assert book(admin, [0, 1, 2, 3], at(1), at(9)).status_code == 200
    assert book(alice, [0], at(2), at(3)).status_code == 409
    assert book(admin, [0], at(2), at(3)).status_code == 409


def test_edit_and_delete_permissions(alice, bob, admin):
    b = book(alice, [0], at(5), at(6)).json()
    body = {"gpus": [1], "start": at(5), "end": at(7), "purpose": "x", "mem_gb": 20}
    assert bob.patch(f"/api/bookings/{b['id']}", json=body, headers=H).status_code == 403
    r = alice.patch(f"/api/bookings/{b['id']}", json=body, headers=H)
    assert r.status_code == 200 and r.json()["gpus"] == [1]
    assert bob.delete(f"/api/bookings/{b['id']}", headers=H).status_code == 403
    assert admin.delete(f"/api/bookings/{b['id']}", headers=H).json() == {"deleted": True}


def test_running_booking_only_end_can_change(alice):
    b = book(alice, [0], at(-0.5), at(2)).json()
    moved = {"gpus": [0], "start": at(-0.25), "end": at(2), "purpose": "", "mem_gb": 20}
    assert alice.patch(f"/api/bookings/{b['id']}", json=moved, headers=H).status_code == 409
    extended = {"gpus": [0], "start": b["start"], "end": at(3), "purpose": "", "mem_gb": 20}
    assert alice.patch(f"/api/bookings/{b['id']}", json=extended, headers=H).status_code == 200
    r = alice.delete(f"/api/bookings/{b['id']}", headers=H).json()
    assert r["ended"] is True
    assert datetime.fromisoformat(r["booking"]["end"]) <= datetime.now(timezone.utc)


def test_small_jobs_should_run_locally(alice, admin):
    # 6 GB local GPU by default
    r = book(alice, [0], at(1), at(2), mem_gb=None)
    assert r.status_code == 409 and "記憶體" in r.json()["detail"]
    r = book(alice, [0], at(1), at(2), mem_gb=4)
    assert r.status_code == 409 and "本地" in r.json()["detail"]
    # ticking "local can't run it" requires a reason
    assert book(alice, [0], at(1), at(2), mem_gb=4, local_insufficient=True).status_code == 409
    r = book(alice, [0], at(1), at(2), purpose="本地太慢，要跑 20 組參數", mem_gb=4, local_insufficient=True)
    assert r.status_code == 200 and r.json()["mem_gb"] == 4
    # bigger jobs and both GPUs at once are fine
    assert book(alice, [0, 1], at(3), at(5), mem_gb=20).status_code == 200
    # admins can switch the check off
    rules = admin.get("/api/admin/rules").json()["rules"] | {"local_gpu_mem_gb": 0}
    assert admin.put("/api/admin/rules", json=rules, headers=H).status_code == 200
    assert book(alice, [0], at(6), at(7), mem_gb=None).status_code == 200


def test_moving_booking_keeps_its_memory_answer(alice):
    b = book(alice, [0], at(1), at(2), purpose="本地太慢", mem_gb=4, local_insufficient=True).json()
    body = {"gpus": [0], "start": at(2), "end": at(3), "purpose": b["purpose"],
            "mem_gb": b["mem_gb"], "local_insufficient": b["local_insufficient"]}
    assert alice.patch(f"/api/bookings/{b['id']}", json=body, headers=H).status_code == 200


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    from app.db import Database

    con = sqlite3.connect(tmp_path / "usage.db")
    con.execute("CREATE TABLE bookings (id INTEGER PRIMARY KEY, username VARCHAR(64), gpus VARCHAR(128), "
                "start DATETIME, \"end\" DATETIME, purpose TEXT, created_at DATETIME)")
    con.commit(); con.close()
    Database(Config(data_dir=tmp_path, secret_key="x"))
    cols = {r[1] for r in sqlite3.connect(tmp_path / "usage.db").execute("PRAGMA table_info(bookings)")}
    assert {"mem_gb", "local_insufficient"} <= cols


def test_blackout_blocks_bookings(admin, alice):
    assert alice.post("/api/admin/blackouts", json={"start": at(1), "end": at(2)}, headers=H).status_code == 403
    existing = book(alice, [0], at(10), at(11)).json()
    r = admin.post("/api/admin/blackouts", json={"start": at(9), "end": at(12), "reason": "更新驅動"}, headers=H).json()
    assert [b["id"] for b in r["conflicting_bookings"]] == [existing["id"]]
    r = book(alice, [2], at(11), at(13))
    assert r.status_code == 409 and "維護" in r.json()["detail"]


def test_admin_rules_update(admin, alice):
    rules = {"max_hours_per_booking": 1, "max_gpu_hours_per_week": 100, "max_days_ahead": 7,
             "max_gpus_per_booking": 1, "flag_unbooked_on_free_gpu": False, "local_gpu_mem_gb": 6}
    assert admin.put("/api/admin/rules", json=rules, headers=H).status_code == 200
    assert book(alice, [0], at(1), at(3)).status_code == 409  # > 1h
    assert book(alice, [0, 1], at(1), at(2)).status_code == 409  # > 1 GPU
    assert alice.get("/api/me").json()["rules"]["max_days_ahead"] == 7


def test_status_flags(app, alice, bob):
    # mock GPU 0 always has a process owned by "alice"
    assert alice.get("/api/status").json()["gpus"][0]["processes"][0]["flag"] == "unbooked"
    book(bob, [0], at(-0.1), at(1))
    assert alice.get("/api/status").json()["gpus"][0]["processes"][0]["flag"] == "conflict"


def test_sampler_and_stats(app, alice):
    from app.sampler import record_sample

    st = app.state.app
    book(alice, [0], at(-0.1), at(1))
    record_sample(st.db, st.monitor, minutes=30)
    record_sample(st.db, st.monitor, minutes=30)
    users = {u["username"]: u for u in alice.get("/api/stats?weeks=1").json()["weeks"][0]["users"]}
    assert users["alice"]["booked"] > 0
    # mock GPU 2 is used by "carol" without a booking
    assert users["carol"]["unbooked"] > 0
    assert users["alice"]["peak_mem_gb"] > 17  # mock process uses 18000 MB


def test_week_boundaries_use_local_time():
    from zoneinfo import ZoneInfo

    from app.bookings import week_start, weeks_touched

    tz = ZoneInfo("Asia/Taipei")
    # Sunday 2026-09-27 17:00 UTC = Monday 01:00 in Taipei -> week starts Monday 00:00 Taipei (Sun 16:00 UTC)
    assert week_start(datetime(2026, 9, 27, 17), tz) == datetime(2026, 9, 27, 16)
    assert len(weeks_touched(datetime(2026, 9, 27, 15), datetime(2026, 9, 27, 17), tz)) == 2
