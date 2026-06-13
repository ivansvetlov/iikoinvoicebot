#!/usr/bin/env python3
"""Offline CI checks for Groq Proxy (no grok CLI, no live :8080)."""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _compile_modules() -> None:
    modules = [
        "openai_proxy.py",
        "backend.py",
        "prompt_pipeline.py",
        "response_pipeline.py",
        "bridge_guards.py",
        "session_store.py",
        "phase_router.py",
        "mcp_bridge.py",
        "mcp_grok_adapter.py",
        "start_grok.py",
        "paths.py",
    ]
    for name in modules:
        path = os.path.join(ROOT, name)
        py_compile.compile(path, doraise=True)
    print("compile: OK")


def _run(script: str) -> None:
    path = os.path.join(ROOT, "tests", script)
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT
    print(f"run: {script}")
    subprocess.run([sys.executable, path], cwd=ROOT, env=env, check=True)


def main() -> int:
    os.chdir(ROOT)
    _compile_modules()
    for test in (
        "test_bridge_guards.py",
        "test_risk_mitigations.py",
        "test_structured_output.py",
        "test_session_resume.py",
        "test_two_phase.py",
        "test_backend_resume_cmd.py",
        "test_mcp_bridge.py",
        "test_no_cache_on_tool.py",
        "test_tool_calling.py",
    ):
        _run(test)
    print("ci_offline: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
