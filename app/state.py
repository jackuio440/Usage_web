from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .auth import Authenticator
from .config import Config
from .db import Database
from .gpu import GPUMonitor


@dataclass
class AppState:
    cfg: Config
    db: Database
    monitor: GPUMonitor
    auth: Authenticator


def get_state(request: Request) -> AppState:
    return request.app.state.app
