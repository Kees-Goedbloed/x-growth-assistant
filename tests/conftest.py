"""Pytest session guard (the unittest suite uses test_000 / test_zzz)."""
from __future__ import annotations

import sys
from pathlib import Path

# pytest invoked from the repo root does not put tests/ on sys.path.
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import repo_guard


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    drift = repo_guard.data_tree_drift()
    if drift:
        raise RuntimeError(f"tests mutated repo data/: {drift}")
