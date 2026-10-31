#!/usr/bin/env python3
"""Publish the current local UAE First Division snapshot to Google Drive.

Use after a successful UAEFA/BeSoccer update. The script hashes every file and
uploads only new or changed data, preserving raw JSON snapshots in Drive.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.drive_sync import DriveSyncError, publish_project_snapshot, settings_from_mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-raw", action="store_true", help="Do not publish cached UAEFA JSON responses.")
    args = parser.parse_args()
    settings = settings_from_mapping()
    if not settings:
        raise DriveSyncError("Set GOOGLE_DRIVE_ROOT_ID and GOOGLE_SERVICE_ACCOUNT_JSON before publishing.")
    manifest = publish_project_snapshot(PROJECT_ROOT, settings, include_raw=not args.skip_raw)
    print(json.dumps(manifest["summary"], indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DriveSyncError as exc:
        print(f"Drive publish stopped: {exc}", file=sys.stderr)
        raise SystemExit(2)
