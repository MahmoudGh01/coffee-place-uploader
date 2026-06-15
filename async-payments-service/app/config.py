from __future__ import annotations

import os


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


DATABASE_URL = get_env(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/async_payments",
)
HARBOUR_BASE_URL = get_env("HARBOUR_BASE_URL", "http://localhost:8090")
WORKER_POLL_SECONDS = float(get_env("WORKER_POLL_SECONDS", "2.0"))
WORKER_MAX_ATTEMPTS = int(get_env("WORKER_MAX_ATTEMPTS", "3"))
