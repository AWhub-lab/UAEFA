#!/usr/bin/env python3
"""Download missing UAEFA crests and player portraits for one snapshot."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_SCRIPT = Path(__file__).with_name("download_first_division_week1.py")
DATASETS = {
    "second": "second_division_2026_2027",
    "third": "third_division_2026_2027",
    "u23": "pro_league_u23_2026_2027",
}


def load_pilot_module():
    spec = importlib.util.spec_from_file_location("uaefa_media", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the shared UAEFA downloader.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("competition", choices=sorted(DATASETS))
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=4.5)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")

    directory = DATASETS[args.competition]
    processed = PROJECT_ROOT / "data" / "processed" / directory / "current"
    pilot = load_pilot_module()
    pilot.ASSETS_ROOT = PROJECT_ROOT / "data" / "assets" / directory
    clubs_frame = pd.read_parquet(processed / "clubs.parquet")
    players_frame = pd.read_parquet(processed / "players.parquet")
    clubs = {str(row.club_id): row._asdict() for row in clubs_frame.itertuples(index=False)}
    players = {str(row.player_id): row._asdict() for row in players_frame.itertuples(index=False)}
    client = pilot.GentleUAEFAClient(args.min_delay, args.max_delay)
    media = pilot.download_media(client, clubs, players)
    pd.DataFrame(clubs.values(), columns=pilot.TABLE_COLUMNS["clubs"]).to_parquet(processed / "clubs.parquet", index=False)
    pd.DataFrame(players.values(), columns=pilot.TABLE_COLUMNS["players"]).to_parquet(processed / "players.parquet", index=False)
    summary = {"downloaded_at": datetime.now(UTC).isoformat(), "competition": args.competition, "media": media, "request_policy": {"parallel_requests": 0, "min_delay_seconds": args.min_delay, "max_delay_seconds": args.max_delay, "stop_status_codes": [403, 429]}}
    (processed / "media_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    pilot = load_pilot_module()
    try:
        raise SystemExit(main())
    except pilot.RateLimitError as exc:
        print(f"SAFE STOP: {exc}")
        raise SystemExit(2)
