"""Poll the backend's /health endpoint until it responds — same
30-attempt/2s-interval shape as ci.yml's deploy job's "Warte auf Backend"
step, just from Python instead of a bash loop."""
from __future__ import annotations

import time

import requests

HEALTH_URL = "http://localhost:8000/health"
DEFAULT_ATTEMPTS = 30
DEFAULT_INTERVAL_SECONDS = 2.0


def wait_for_healthy(
    attempts: int = DEFAULT_ATTEMPTS, interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> bool:
    for _ in range(attempts):
        if is_healthy():
            return True
        time.sleep(interval_seconds)
    return False


def is_healthy() -> bool:
    try:
        resp = requests.get(HEALTH_URL, timeout=5)
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except requests.RequestException:
        return False
