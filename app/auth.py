"""Log in with the server's Linux accounts through PAM."""

from __future__ import annotations

import grp
import os
import pwd
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import Config

MAX_FAILURES = 5
LOCKOUT_SECONDS = 600


@dataclass
class User:
    username: str
    is_admin: bool


class LoginLimiter:
    """Lock a username (and the client IP) for a while after repeated failures."""

    def __init__(self):
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        return [t for t in self._failures.get(key, []) if now - t < LOCKOUT_SECONDS]

    def locked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._recent(k, now)) >= MAX_FAILURES for k in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._failures[k] = self._recent(k, now) + [now]

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


def is_system_user(username: str, min_uid: int) -> bool:
    """Root, display managers, "?" (unknown owner) etc. Their GPU processes are never flagged."""
    if username in ("?", "root"):
        return True
    try:
        return pwd.getpwnam(username).pw_uid < min_uid
    except KeyError:
        return False  # not a local account (e.g. mock users); treat as a normal user


def user_groups(username: str) -> set[str]:
    try:
        pw = pwd.getpwnam(username)
    except KeyError:
        return set()
    names = set()
    for gid in os.getgrouplist(username, pw.pw_gid):
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            pass
    return names


class Authenticator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.limiter = LoginLimiter()

    def _is_admin(self, username: str) -> bool:
        if self.cfg.mock:
            return username.startswith("admin")
        return bool(user_groups(username) & set(self.cfg.admin_groups))

    def _account_allowed(self, username: str) -> bool:
        try:
            pw = pwd.getpwnam(username)
        except KeyError:
            return False
        if pw.pw_uid < self.cfg.min_uid:
            return False
        if self.cfg.allowed_groups:
            return bool(user_groups(username) & set(self.cfg.allowed_groups))
        return True

    def _check_password(self, username: str, password: str) -> bool:
        if self.cfg.mock:
            return password == "test"
        import pam  # imported lazily so tests and mock mode work without libpam

        return pam.pam().authenticate(username, password, service=self.cfg.pam_service)

    def login(self, username: str, password: str, client_ip: str) -> User:
        """Return the user, or raise HTTPException with a message fit to show."""
        username = username.strip()
        keys = (f"user:{username}", f"ip:{client_ip}")
        if self.limiter.locked(*keys):
            raise HTTPException(429, f"登入失敗次數過多，請 {LOCKOUT_SECONDS // 60} 分鐘後再試")
        ok = bool(username) and (self.cfg.mock or self._account_allowed(username))
        ok = ok and self._check_password(username, password)
        if not ok:
            self.limiter.fail(*keys)
            raise HTTPException(401, "帳號或密碼錯誤（請使用伺服器的 Linux 帳號）")
        self.limiter.reset(*keys)
        return User(username=username, is_admin=self._is_admin(username))


def current_user(request: Request) -> User:
    data = request.session.get("user")
    if not data:
        raise HTTPException(401, "請先登入")
    return User(**data)


def require_admin(request: Request) -> User:
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(403, "需要管理員權限")
    return user
