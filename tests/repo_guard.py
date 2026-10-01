#!/usr/bin/env python3
"""Helpers so tests never touch the real repo data/ tree or require ROOT .git."""
from __future__ import annotations

import atexit
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def snapshot_data_tree(data_dir: Path | None = None) -> dict[str, str]:
    """Map relative paths under data/ to sha256 (files) or empty (directories)."""
    base = Path(data_dir) if data_dir is not None else DATA
    out: dict[str, str] = {}
    if not base.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        rel_dir = Path(dirpath).relative_to(base).as_posix()
        marker = "." if rel_dir == "." else rel_dir
        out[marker + "/"] = ""
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(base).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# Taken at first import, before any test method runs (see test_000_repo_guard).
SESSION_DATA_SNAPSHOT = snapshot_data_tree()


def data_tree_drift() -> dict[str, tuple[str | None, str | None]]:
    """Paths whose presence or hash changed vs SESSION_DATA_SNAPSHOT."""
    now = snapshot_data_tree()
    before = SESSION_DATA_SNAPSHOT
    keys = set(before) | set(now)
    drift = {}
    for k in keys:
        a, b = before.get(k), now.get(k)
        if a != b:
            drift[k] = (a, b)
    return drift


def init_git_repo(path: Path, origin="https://github.com/Kees-Goedbloed/x-growth-assistant.git") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", origin],
        cwd=path, check=True, capture_output=True,
    )
    return path


_GIT_TDS: list[tempfile.TemporaryDirectory] = []


def cleanup_origin_git_envs() -> None:
    """Remove temp git dirs created by origin_git_env()."""
    while _GIT_TDS:
        _GIT_TDS.pop().cleanup()


atexit.register(cleanup_origin_git_envs)


def origin_git_env(base_env=None, work_tree: Path | None = None) -> dict:
    """Env so `git remote get-url origin` works even if ROOT has no .git."""
    env = os.environ.copy() if base_env is None else dict(base_env)
    td = tempfile.TemporaryDirectory(prefix="xdash-git-")
    _GIT_TDS.append(td)
    root = Path(td.name)
    init_git_repo(root)
    env["GIT_DIR"] = str(root / ".git")
    env["GIT_WORK_TREE"] = str(work_tree or ROOT)
    return env


def list_tmp_star_dirs() -> set[str]:
    """Default-prefix tempfile dirs (`/tmp/tmp*`, plus $TMPDIR/tmp*)."""
    roots = {Path("/tmp"), Path(tempfile.gettempdir())}
    found: set[str] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for p in root.glob("tmp*"):
                if p.is_dir():
                    try:
                        found.add(str(p.resolve()))
                    except OSError:
                        found.add(str(p))
        except OSError:
            continue
    return found


# Taken at first import, before any test method runs (see test_000_repo_guard).
SESSION_TMP_DIRS = list_tmp_star_dirs()


def leftover_tmp_star_dirs() -> set[str]:
    """Default-prefix tmp dirs that appeared after SESSION_TMP_DIRS was taken."""
    return list_tmp_star_dirs() - SESSION_TMP_DIRS
