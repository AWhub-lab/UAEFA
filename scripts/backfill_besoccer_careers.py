#!/usr/bin/env python3
"""Build validated BeSoccer career rows from the local cache without web requests.

This fills historical club data after a profile-only enrichment run. A cached
page is parsed only when its UAEFA identity has already been validated, so no
candidate or ambiguous record can enter the application.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.competitions import COMPETITIONS, get_competition
from uaefa_scraper.besoccer import BeSoccerClient, parse_player_profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=sorted(COMPETITIONS), default="first")
    args = parser.parse_args()
    competition = get_competition(args.competition)
    external = PROJECT_ROOT / "data" / "external" / "besoccer" / competition.directory
    profiles_path = external / "player_profiles_validated.parquet"
    if not profiles_path.exists():
        raise FileNotFoundError(f"No validated BeSoccer profiles found: {profiles_path}")

    profiles = pd.read_parquet(profiles_path).copy()
    cache_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "profiles"
    client = BeSoccerClient(cache_dir=cache_root)
    careers: list[dict[str, object]] = []
    missing_cache = 0

    for profile in profiles.to_dict("records"):
        url = str(profile.get("source_url") or "")
        if not url or not client._cache_path(url).exists():  # Cache-only by design: never fetch here.
            missing_cache += 1
            continue
        parsed = parse_player_profile(client.get_html(url), url)
        for club in parsed["career"]:
            careers.append(
                {
                    "uaefa_player_id": str(profile["uaefa_player_id"]),
                    "besoccer_player_id": profile.get("besoccer_player_id"),
                    **club,
                }
            )

    career = pd.DataFrame(careers)
    if not career.empty:
        career = career.drop_duplicates(
            ["uaefa_player_id", "club_name", "club_url"], keep="last"
        )
    career.to_parquet(external / "player_career.parquet", index=False)
    summary = {
        "updated_at": datetime.now(UTC).isoformat(),
        "competition": competition.key,
        "validated_profiles": int(len(profiles)),
        "players_with_career": int(career["uaefa_player_id"].nunique()) if not career.empty else 0,
        "career_rows": int(len(career)),
        "missing_cached_profiles": missing_cache,
        "web_requests": client.request_count,
    }
    (external / "player_career_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
