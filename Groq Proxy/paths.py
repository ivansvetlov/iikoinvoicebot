"""Shared paths for Groq Proxy runtime artifacts."""

from __future__ import annotations

import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(ROOT_DIR, "logs")


def ensure_logs_dir() -> str:
    os.makedirs(LOGS_DIR, exist_ok=True)
    return LOGS_DIR


def log_path(name: str) -> str:
    return os.path.join(ensure_logs_dir(), name)
