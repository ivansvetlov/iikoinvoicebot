#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge_guards import (
    classify_backend_result,
    stderr_indicates_real_timeout,
    stderr_indicates_session_build_failure,
)
from backend import BackendResult


def test_auto_background_on_timeout_not_real_timeout():
    err = 'auto_background_on_timeout requires enabled_background to be true'
    assert not stderr_indicates_real_timeout(err)


def test_session_build_failure_classified():
    stderr = "ERROR Agent building failed Requirements unsatisfied"
    assert stderr_indicates_session_build_failure(stderr)
    r = BackendResult(stdout='{"type":"error"}', stderr=stderr, returncode=1, backend="grok-cli:plan", elapsed_s=1)
    ev = classify_backend_result(r)
    assert ev.code == "grok_session_build_failed"
    assert not ev.retry_planner


if __name__ == "__main__":
    test_auto_background_on_timeout_not_real_timeout()
    test_session_build_failure_classified()
    print("OK")
