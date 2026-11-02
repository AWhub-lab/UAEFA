#!/usr/bin/env python3
"""Publish one validated competition snapshot to its own Google Drive folders.

Processed tables are the application-ready source. Raw API responses are
optional evidence copies and never used by the hosted application directly.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.drive_sync import (
    DriveSyncError,
    ensure_path,
    load_project_env,
    publisher_service_from_oauth,
    publish_tree,
    sha256_file,
    settings_from_mapping,
    upload_bytes,
    upload_file,
)

load_project_env(PROJECT_ROOT / ".env")


DATASETS = {
    "second": "second_division_2026_2027",
    "third": "third_division_2026_2027",
    "u23": "pro_league_u23_2026_2027",
}


def build_media_bundle(directory: str) -> Path | None:
    """Package one competition's media for Drive without scattering thousands of files."""
    asset_root = PROJECT_ROOT / "data" / "assets" / directory
    sources = sorted(path for path in asset_root.rglob("*") if path.is_file()) if asset_root.exists() else []
    if not sources:
        return None
    bundle = PROJECT_ROOT / "tmp" / f"{directory}_media.zip"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in sources:
            archive.write(source, source.relative_to(asset_root).as_posix())
    return bundle


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
    media_bundle = build_media_bundle(directory)
    summary_path = processed / "summary.json"
    if not summary_path.exists():
        raise DriveSyncError(f"No validated processed snapshot found for {directory}.")

    service = publisher_service_from_oauth(PROJECT_ROOT)
    table_root = ensure_path(service, settings.root_folder_id, ["02_Processed data", "competitions", directory, "current", "tables"])
    raw_root = ensure_path(service, settings.root_folder_id, ["01_Raw data", "competitions", directory]) if args.include_raw else None
    assets_root = ensure_path(service, settings.root_folder_id, ["03_Assets", "competitions", directory]) if media_bundle else None
    records, uploaded, skipped = publish_tree(service, processed, table_root, "tables", {})
    raw_records: list[dict] = []
    if raw_root and raw.exists():
        raw_records, raw_uploaded, raw_skipped = publish_tree(service, raw, raw_root, "raw", {})
        uploaded += raw_uploaded
        skipped += raw_skipped
    media_record = None
    if media_bundle and assets_root:
        upload_file(service, assets_root, media_bundle)
        media_record = {
            "path": f"03_Assets/competitions/{directory}/{media_bundle.name}",
            "sha256": sha256_file(media_bundle), "bytes": media_bundle.stat().st_size,
        }
        uploaded += 1
    manifest = {
        "schema_version": 1, "published_at": datetime.now(UTC).isoformat(), "competition": args.competition,
        "directory": directory, "snapshot": json.loads(summary_path.read_text(encoding="utf-8")),
        "files": records, "raw_files": raw_records, "media_bundle": media_record,
        "summary": {"uploaded": uploaded, "unchanged": skipped, "total": len(records) + len(raw_records) + int(media_record is not None)},
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
