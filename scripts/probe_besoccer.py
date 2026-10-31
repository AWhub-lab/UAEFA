"""Run a deliberately tiny BeSoccer coverage check for one public team page."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import BASE_URL, BeSoccerClient, parse_squad


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-slug", default="al-thaid", help="Public BeSoccer team slug to validate")
    args = parser.parse_args()

    raw_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "coverage_probe"
    output_root = PROJECT_ROOT / "data" / "external" / "besoccer" / "coverage_probe"
    squad_url = f"{BASE_URL}/team/squad/{args.team_slug}"
    client = BeSoccerClient(cache_dir=raw_root, min_delay=8.0, max_delay=12.0)
    team, players = parse_squad(client.get_html(squad_url), squad_url)
    output_root.mkdir(parents=True, exist_ok=True)
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "team_slug": args.team_slug,
        "team": team,
        "players_found": len(players),
        "sample_players": players[:5],
        "request_count": client.request_count,
        "policy": {"cached": True, "parallel_requests": 0, "delay_seconds": [8, 12]},
    }
    path = output_root / f"{args.team_slug}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved coverage summary: {path}")


if __name__ == "__main__":
    main()
