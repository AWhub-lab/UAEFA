#!/usr/bin/env python3
"""Finish approved snapshots after Third Division core data has validated.

This runs strictly sequentially: official profiles, then public media, then
Drive publication. Any failed subprocess stops the pipeline immediately.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THIRD = PROJECT_ROOT / "data" / "processed" / "third_division_2026_2027" / "current"
LOG = PROJECT_ROOT / "logs" / "new_competitions_finish.log"


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def third_snapshot_valid() -> bool:
    required = [THIRD / "summary.json", *(THIRD / f"{name}.parquet" for name in ("matches", "clubs", "players", "appearances", "events", "staff"))]
    if not all(path.exists() for path in required):
        return False
    summary = json.loads((THIRD / "summary.json").read_text(encoding="utf-8"))
    matches = pd.read_parquet(THIRD / "matches.parquet")
    completed = matches[matches["status_id"].astype(str).eq("6")]
    return matches["match_id"].is_unique and len(completed) == int(summary["completed_matches"])


def run(*arguments: str) -> None:
    command = [sys.executable, *arguments]
    log("Running: " + " ".join(arguments))
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode:
        raise RuntimeError(f"Command stopped with exit code {result.returncode}: {' '.join(arguments)}")


def main() -> int:
    log("Waiting for validated Third Division core snapshot.")
    deadline = time.monotonic() + 5 * 60 * 60
    while not third_snapshot_valid():
        if time.monotonic() >= deadline:
            raise RuntimeError("Third Division did not produce a valid snapshot before the safety timeout.")
        time.sleep(30)
    log("Third Division core snapshot validated.")
    run("scripts/download_uaefa_profiles_all.py", "--competitions", "u23", "second", "third")
    for competition in ("u23", "second", "third"):
        run("scripts/download_uaefa_competition_media.py", competition)
    for competition in ("u23", "second", "third"):
        run("scripts/publish_competition_to_drive.py", competition, "--include-raw")
    log("Profiles, media and Drive publication completed for all new competitions.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"SAFE STOP: {exc}")
        raise SystemExit(2)
