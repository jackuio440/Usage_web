"""Load settings from a TOML file (path in $USAGE_WEB_CONFIG, default ./config.toml)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import tomllib
except ImportError:  # Python 3.10 (Ubuntu 22.04)
    import tomli as tomllib


@dataclass
class Rules:
    """Booking rules. Values here are defaults; admins can override them in the web UI."""

    max_hours_per_booking: float = 48
    max_gpu_hours_per_week: float = 72  # GPU-hours = hours x number of GPUs; 2 GPUs = 336 per week in total
    max_days_ahead: int = 14
    max_gpus_per_booking: int = 0  # 0 = no limit
    flag_unbooked_on_free_gpu: bool = True
    # Jobs that fit in this much GPU memory could run on people's own machines
    # (e.g. a local RTX 3050 6GB); the booking dialog reminds them. 0 = off.
    local_gpu_mem_gb: float = 6

    @classmethod
    def keys(cls) -> list[str]:
        return list(cls.__dataclass_fields__)


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8080
    secret_key: str = ""
    cookie_secure: bool = False
    data_dir: Path = Path("./data")
    timezone: str = "Asia/Taipei"
    site_title: str = ""  # empty = default name in the viewer's language

    pam_service: str = "login"
    admin_groups: list[str] = field(default_factory=lambda: ["sudo", "wheel"])
    allowed_groups: list[str] = field(default_factory=list)  # empty = every normal user
    min_uid: int = 1000

    gpu_cache_seconds: float = 5
    sample_interval_seconds: int = 60
    usage_retention_days: int = 400
    disk_paths: list[str] = field(default_factory=lambda: ["/"])

    rules: Rules = field(default_factory=Rules)

    mock: bool = False  # fake GPUs + accept any login; development only
    mock_gpu_count: int = 2

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "usage.db"


def _load_secret(cfg: Config) -> str:
    if cfg.secret_key:
        return cfg.secret_key
    path = cfg.data_dir / "secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    path.chmod(0o600)
    return key


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("USAGE_WEB_CONFIG", "config.toml"))
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

    server = raw.get("server", {})
    auth = raw.get("auth", {})
    gpu = raw.get("gpu", {})
    rules = raw.get("rules", {})

    cfg = Config()
    for key in ("host", "port", "secret_key", "cookie_secure", "timezone", "site_title"):
        if key in server:
            setattr(cfg, key, server[key])
    if "data_dir" in server:
        cfg.data_dir = Path(server["data_dir"])
    for key in ("pam_service", "admin_groups", "allowed_groups", "min_uid"):
        if key in auth:
            setattr(cfg, key, auth[key])
    for key in ("cache_seconds", "sample_interval_seconds", "usage_retention_days", "disk_paths"):
        if key in gpu:
            setattr(cfg, "gpu_cache_seconds" if key == "cache_seconds" else key, gpu[key])
    if "mock" in gpu:
        cfg.mock = gpu["mock"]
    if "mock_gpu_count" in gpu:
        cfg.mock_gpu_count = gpu["mock_gpu_count"]
    cfg.rules = Rules(**{k: v for k, v in rules.items() if k in Rules.keys()})

    if os.environ.get("USAGE_WEB_MOCK") == "1":
        cfg.mock = True
    if os.environ.get("USAGE_WEB_DATA_DIR"):
        cfg.data_dir = Path(os.environ["USAGE_WEB_DATA_DIR"])

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.secret_key = _load_secret(cfg)
    return cfg
