"""Read GPU and system status. Uses NVML (no CUDA context, no GPU memory used),
falls back to nvidia-smi, and can produce fake data for development."""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field

import psutil

from .config import Config

log = logging.getLogger(__name__)


@dataclass
class GPUProcess:
    pid: int
    username: str
    name: str
    mem_mb: float


@dataclass
class GPUInfo:
    index: int
    name: str
    util: float  # percent
    mem_used_mb: float
    mem_total_mb: float
    temperature: float | None
    power_w: float | None
    processes: list[GPUProcess] = field(default_factory=list)


def _proc_owner(pid: int) -> tuple[str, str]:
    try:
        p = psutil.Process(pid)
        return p.username(), p.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "?", "?"


class NvmlReader:
    def __init__(self):
        import pynvml

        self.nv = pynvml
        pynvml.nvmlInit()

    def read(self) -> list[GPUInfo]:
        nv = self.nv
        gpus = []
        for i in range(nv.nvmlDeviceGetCount()):
            h = nv.nvmlDeviceGetHandleByIndex(i)
            name = nv.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            mem = nv.nvmlDeviceGetMemoryInfo(h)
            try:
                util = nv.nvmlDeviceGetUtilizationRates(h).gpu
            except nv.NVMLError:
                util = 0
            try:
                temp = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
            except nv.NVMLError:
                temp = None
            try:
                power = nv.nvmlDeviceGetPowerUsage(h) / 1000
            except nv.NVMLError:
                power = None
            procs: dict[int, GPUProcess] = {}
            for getter in (nv.nvmlDeviceGetComputeRunningProcesses, nv.nvmlDeviceGetGraphicsRunningProcesses):
                try:
                    running = getter(h)
                except nv.NVMLError:
                    continue
                for p in running:
                    user, pname = _proc_owner(p.pid)
                    used = (p.usedGpuMemory or 0) / 2**20
                    procs[p.pid] = GPUProcess(p.pid, user, pname, round(used))
            gpus.append(
                GPUInfo(i, name, util, round(mem.used / 2**20), round(mem.total / 2**20), temp, power, list(procs.values()))
            )
        return gpus


class NvidiaSmiReader:
    def __init__(self):
        if not shutil.which("nvidia-smi"):
            raise RuntimeError("nvidia-smi not found")

    @staticmethod
    def _run(args: list[str]) -> list[list[str]]:
        out = subprocess.run(
            ["nvidia-smi", *args, "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        return [[c.strip() for c in line.split(",")] for line in out.strip().splitlines() if line.strip()]

    @staticmethod
    def _num(s: str) -> float | None:
        try:
            return float(s)
        except ValueError:
            return None

    def read(self) -> list[GPUInfo]:
        rows = self._run(["--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"])
        gpus, by_uuid = [], {}
        for idx, uuid, name, util, used, total, temp, power in rows:
            g = GPUInfo(int(idx), name, self._num(util) or 0, self._num(used) or 0, self._num(total) or 0, self._num(temp), self._num(power))
            gpus.append(g)
            by_uuid[uuid] = g
        for uuid, pid, mem in self._run(["--query-compute-apps=gpu_uuid,pid,used_memory"]):
            if uuid in by_uuid:
                user, pname = _proc_owner(int(pid))
                by_uuid[uuid].processes.append(GPUProcess(int(pid), user, pname, self._num(mem) or 0))
        return gpus


class MockReader:
    """Fake GPUs whose load drifts over time; for development and screenshots."""

    USERS = ["alice", "bob", "carol"]

    def __init__(self, count: int):
        self.count = count

    def read(self) -> list[GPUInfo]:
        t = time.time() / 60
        gpus = []
        for i in range(self.count):
            busy = i % 2 == 0 or math.sin(t + i) > 0.3
            util = (55 + 40 * math.sin(t * 3 + i)) if busy else 0
            procs = [GPUProcess(10000 + i, self.USERS[i % len(self.USERS)], "python", 18000)] if busy else []
            gpus.append(
                GPUInfo(i, "NVIDIA RTX 6000 Ada (mock)", round(util), 18500 if busy else 3, 49140, 38 + util * 0.4, 70 + util * 2.5, procs)
            )
        return gpus


class GPUMonitor:
    """Caches readings so many open dashboards cost only one query per cache period."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._cached: tuple[float, list[GPUInfo]] | None = None
        self.error: tuple[str, dict] | None = None  # (i18n key, params)
        self.known_count = 0  # keeps bookings working if a single read fails
        self.reader = self._make_reader()

    def _make_reader(self):
        if self.cfg.mock:
            return MockReader(self.cfg.mock_gpu_count)
        for cls in (NvmlReader, NvidiaSmiReader):
            try:
                return cls()
            except Exception as e:  # noqa: BLE001 - try the next backend
                log.warning("GPU backend %s unavailable: %s", cls.__name__, e)
        self.error = ("gpu.error.none", {})
        return None

    def read(self, max_age: float | None = None) -> list[GPUInfo]:
        max_age = self.cfg.gpu_cache_seconds if max_age is None else max_age
        with self._lock:
            now = time.monotonic()
            if self._cached and now - self._cached[0] < max_age:
                return self._cached[1]
            gpus: list[GPUInfo] = []
            if self.reader is not None:
                try:
                    gpus = self.reader.read()
                    self.known_count = max(self.known_count, len(gpus))
                    self.error = None
                except Exception as e:  # noqa: BLE001 - keep serving the site even if the driver hiccups
                    log.exception("GPU read failed")
                    self.error = ("gpu.error.read", {"detail": str(e)})
                    gpus = self._cached[1] if self._cached else []
            self._cached = (now, gpus)
            return gpus

    def gpu_count(self) -> int:
        return max(len(self.read()), self.known_count)


def system_status(disk_paths: list[str]) -> dict:
    vm = psutil.virtual_memory()
    disks = []
    for path in disk_paths:
        try:
            du = psutil.disk_usage(path)
            disks.append({"path": path, "used_gb": round(du.used / 1e9, 1), "total_gb": round(du.total / 1e9, 1), "percent": du.percent})
        except OSError:
            pass
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(),
        "load_avg": [round(x, 2) for x in psutil.getloadavg()],
        "mem_used_gb": round((vm.total - vm.available) / 1e9, 1),
        "mem_total_gb": round(vm.total / 1e9, 1),
        "mem_percent": vm.percent,
        "disks": disks,
        "users_logged_in": sorted({u.name for u in psutil.users()}),
    }


def gpu_to_dict(g: GPUInfo) -> dict:
    return asdict(g)
