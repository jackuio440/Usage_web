"""Run the site: `python -m app` (reads host/port from the config file)."""

import logging

import uvicorn

from .config import load_config
from .main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
cfg = load_config()
uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, proxy_headers=False, access_log=False)
