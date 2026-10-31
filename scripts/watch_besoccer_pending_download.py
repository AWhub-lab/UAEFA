"""Run the safe local resolver after the pending profile download completes."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027" / "pending_candidate_profiles_summary.json"


def main() -> None:
    while not SUMMARY.exists():
        time.sleep(60)
    subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "resolve_besoccer_pending_profiles.py")], check=True)


if __name__ == "__main__":
    main()
