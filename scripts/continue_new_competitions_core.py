#!/usr/bin/env python3
"""Continue the approved core UAEFA downloads without concurrent traffic.

This helper waits for the already-running Second Division process to write a
complete snapshot. It performs basic relational checks, then starts Third
Division as a separate sequential process. It never starts a second download
if the preceding snapshot is incomplete.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECOND = PROJECT_ROOT / "data" / "processed" / "second_division_2026_2027" / "current"
THIRD = PROJECT_ROOT / "data" / "processed" / "third_division_2026_2027" / "current"
LOG = PROJECT_ROOT / "logs" / "new_competitions_core.log"


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def valid_snapshot(root: Path) -> bool:
    summary = root / "summary.json"
    required = [root / f"{name}.parquet" for name in ("matches", "clubs", "players", "appearances", "events", "staff")]
    if not summary.exists() or not all(path.exists() for path in required):
        return False
    metadata = json.loads(summary.read_text(encoding="utf-8"))
    matches = pd.read_parquet(root / "matches.parquet")
    completed = matches[matches["status_id"].astype(str).eq("6")]
    if len(completed) != int(metadata["completed_matches"]) or not matches["match_id"].is_unique:
        return False
    appearances = pd.read_parquet(root / "appearances.parquet")
    events = pd.read_parquet(root / "events.parquet")
    players = pd.read_parquet(root / "players.parquet")
    ids = set(completed["match_id"])
    return (
        not (~appearances["match_id"].isin(ids)).any()
        and not (~events["match_id"].isin(ids)).any()
        and not (~appearances["player_id"].isin(set(players["player_id"]))).any()
    )


def wait_for_second(timeout_seconds: int = 3 * 60 * 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if valid_snapshot(SECOND):
            log("Second Division snapshot validated.")
            return
        time.sleep(30)
    raise RuntimeError("Second Division did not produce a valid snapshot before the safety timeout.")


def main() -> int:
    log("Waiting for the active Second Division snapshot.")
    wait_for_second()
    command = [sys.executable, "scripts/sync_uaefa_competition.py", "third", "--skip-media", "--date-to", "2026-11-02"]
    log("Starting Third Division core download.")
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Third Division stopped with exit code {result.returncode}.")
    if not valid_snapshot(THIRD):
        raise RuntimeError("Third Division completed but its snapshot failed validation.")
    log("Third Division snapshot validated.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"SAFE STOP: {exc}")
        raise SystemExit(2)
