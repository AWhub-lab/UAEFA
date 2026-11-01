#!/usr/bin/env python3
"""Publish one validated competition snapshot to its own Google Drive folders.

Processed tables are the application-ready source. Raw API responses are
optional evidence copies and never used by the hosted application directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.drive_sync import (
    DriveSyncError,
    ensure_path,
    publisher_service_from_oauth,
    publish_tree,
    settings_from_mapping,
    upload_bytes,
)


DATASETS = {
    "second": "second_division_2026_2027",
    "third": "third_division_2026_2027",
    "u23": "pro_league_u23_2026_2027",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("competition", choices=sorted(DATASETS))
    parser.add_argument("--include-raw", action="store_true", help="Also upload cached official JSON source responses to 01_Raw data.")
    args = parser.parse_args()
    settings = settings_from_mapping()
    if not settings:
        raise DriveSyncError("Set GOOGLE_DRIVE_ROOT_ID and GOOGLE_SERVICE_ACCOUNT_JSON before publishing.")

    directory = DATASETS[args.competition]
    processed = PROJECT_ROOT / "data" / "processed" / directory / "current"
    raw = PROJECT_ROOT / "data" / "raw" / directory
    summary_path = processed / "summary.json"
    if not summary_path.exists():
        raise DriveSyncError(f"No validated processed snapshot found for {directory}.")

    service = publisher_service_from_oauth(PROJECT_ROOT)
    table_root = ensure_path(service, settings.root_folder_id, ["02_Processed data", "competitions", directory, "current", "tables"])
    raw_root = ensure_path(service, settings.root_folder_id, ["01_Raw data", "competitions", directory]) if args.include_raw else None
    records, uploaded, skipped = publish_tree(service, processed, table_root, "tables", {})
    raw_records: list[dict] = []
    if raw_root and raw.exists():
        raw_records, raw_uploaded, raw_skipped = publish_tree(service, raw, raw_root, "raw", {})
        uploaded += raw_uploaded
        skipped += raw_skipped
    manifest = {
        "schema_version": 1, "published_at": datetime.now(UTC).isoformat(), "competition": args.competition,
        "directory": directory, "snapshot": json.loads(summary_path.read_text(encoding="utf-8")),
        "files": records, "raw_files": raw_records, "summary": {"uploaded": uploaded, "unchanged": skipped, "total": len(records) + len(raw_records)},
    }
    upload_bytes(service, table_root, "drive_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DriveSyncError as exc:
        print(f"Drive publish stopped: {exc}", file=sys.stderr)
        raise SystemExit(2)
