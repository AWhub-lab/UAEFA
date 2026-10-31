"""Download the mapped UAE First Division BeSoccer squads, without media files."""

from __future__ import annotations

import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import AccessLimitedError, BASE_URL, BeSoccerClient, parse_squad


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Refresh each mapped public squad page once instead of using the cache.")
    parser.add_argument("--min-delay", type=float, default=12.0)
    parser.add_argument("--max-delay", type=float, default=18.0)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")
    season_root = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
    config = json.loads((PROJECT_ROOT / "data" / "external" / "besoccer" / "team_mappings_2026_2027.json").read_text())
    raw_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "squads"
    output_root = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"
    clubs = pd.read_parquet(season_root / "clubs.parquet")
    by_name = clubs.set_index("club_name")["club_id"].astype(str).to_dict()
    client = BeSoccerClient(cache_dir=raw_root, min_delay=args.min_delay, max_delay=args.max_delay)
    teams, squads, failures = [], [], []
    for club_name, slug in config["teams"].items():
        club_id = by_name[club_name]
        url = f"{BASE_URL}/team/squad/{slug}"
        try:
            team, players = parse_squad(client.get_html(url, refresh=args.refresh), url)
        except AccessLimitedError as error:
            failures.append({"club_name": club_name, "url": url, "error": str(error)})
            print(f"Stopped safely: {error}")
            break
        except requests.HTTPError as error:
            # A server-side error is logged once. Retrying a public source is avoided.
            failures.append({"club_name": club_name, "url": url, "error": str(error)})
            print(f"{club_name}: skipped after server error")
            continue
        teams.append({"club_id": club_id, "club_name": club_name, "besoccer_slug": slug, **team})
        for player in players:
            squads.append({
                "club_id": club_id, "club_name": club_name, "besoccer_slug": slug,
                "besoccer_player_id": player["besoccer_player_id"],
                "besoccer_name": player["name"], "squad_number": player["squad_number"],
                "source_url": player["source_url"],
            })
        print(f"{club_name}: {len(players)} roster players")
    output_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(teams).to_parquet(output_root / "teams.parquet", index=False)
    pd.DataFrame(squads).to_parquet(output_root / "squads.parquet", index=False)
    summary = {"downloaded_at": datetime.now(timezone.utc).isoformat(), "teams": len(teams), "squad_rows": len(squads), "requests": client.request_count, "refreshed": args.refresh, "media_downloads": 0, "failures": failures}
    (output_root / "squads_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
