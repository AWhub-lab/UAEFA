"""Discover UAE Second League team slugs and propose a UAEFA crosswalk."""

from __future__ import annotations

import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import (
    BASE_URL,
    BeSoccerClient,
    parse_competition_teams,
    team_crosswalk_candidates,
)
from uaefa_scraper.competitions import COMPETITIONS, get_competition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=sorted(COMPETITIONS), default="first")
    parser.add_argument("--competition-url", required=True, help="Public BeSoccer competition teams or table URL.")
    args = parser.parse_args()
    competition = get_competition(args.competition)
    processed = PROJECT_ROOT / "data" / "processed" / competition.directory / "current"
    raw_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "team_discovery"
    output_root = PROJECT_ROOT / "data" / "external" / "besoccer" / "team_discovery"
    # BeSoccer's season-specific teams view exposes the complete roster of
    # clubs, unlike the competition landing page's abbreviated standings list.
    competition_url = args.competition_url
    client = BeSoccerClient(cache_dir=raw_root, min_delay=8.0, max_delay=12.0)
    discovered = parse_competition_teams(client.get_html(competition_url))
    official = pd.read_parquet(processed / "clubs.parquet").to_dict("records")
    proposals = team_crosswalk_candidates(official, discovered)
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "competition_url": competition_url,
        "uaefa_teams": len(official),
        "besoccer_team_links": len(discovered),
        "accepted": sum(item["status"] == "accepted" for item in proposals),
        "review": sum(item["status"] == "review" for item in proposals),
        "request_count": client.request_count,
        "proposals": proposals,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"{competition.key}_team_discovery.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "proposals"}, ensure_ascii=False, indent=2))
    print(f"Saved team mapping proposals: {path}")


if __name__ == "__main__":
    main()
