"""Create an auditable, no-new-request UAEFA ↔ BeSoccer roster crosswalk pilot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import (
    BASE_URL,
    BeSoccerClient,
    parse_squad,
    player_crosswalk_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--club-name", default="Al Dhaid")
    parser.add_argument("--team-slug", default="al-thaid")
    args = parser.parse_args()

    processed = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
    raw_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "coverage_probe"
    output_root = PROJECT_ROOT / "data" / "external" / "besoccer" / "crosswalk_pilots"
    clubs = pd.read_parquet(processed / "clubs.parquet")
    players = pd.read_parquet(processed / "players.parquet")
    appearances = pd.read_parquet(processed / "appearances.parquet")
    club_ids = set(clubs.loc[clubs["club_name"].eq(args.club_name), "club_id"].astype(str))
    # Club and shirt number live in the official match line-ups, not the
    # player master table. Use the most recent observed roster association.
    roster = appearances[appearances["club_id"].astype(str).isin(club_ids)].copy()
    roster = roster.drop_duplicates("player_id", keep="last")[["player_id", "club_id", "dorsal"]]
    official = players.merge(roster, on="player_id", how="inner").to_dict("records")
    if not official:
        raise SystemExit(f"No UAEFA players found for club: {args.club_name}")

    squad_url = f"{BASE_URL}/team/squad/{args.team_slug}"
    # This uses the preceding coverage cache. A missing cache is intentionally
    # still read politely, with the same stop-on-limit policy.
    client = BeSoccerClient(cache_dir=raw_root, min_delay=8.0, max_delay=12.0)
    _, external = parse_squad(client.get_html(squad_url), squad_url)
    candidates = player_crosswalk_candidates(official, external)
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "club_name": args.club_name,
        "team_slug": args.team_slug,
        "uaefa_players_seen": len(official),
        "besoccer_players_seen": len(external),
        "accepted": sum(row["status"] == "accepted" for row in candidates),
        "review": sum(row["status"] == "review" for row in candidates),
        "request_count": client.request_count,
        "candidates": candidates,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / f"{args.team_slug}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "candidates"}, ensure_ascii=False, indent=2))
    print(f"Saved crosswalk: {path}")


if __name__ == "__main__":
    main()
