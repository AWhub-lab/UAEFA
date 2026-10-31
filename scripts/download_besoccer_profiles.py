"""Download enrichment only for player links already accepted by the crosswalk.

This is deliberately sequential, cache-first and media-free. Ambiguous player
links are never requested: they remain for later manual review.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import BeSoccerClient, parse_player_profile


def quantity_value(value: object) -> str | None:
    return str(value.get("value")) if isinstance(value, dict) and value.get("value") is not None else None


def main() -> None:
    external = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"
    crosswalk = pd.read_parquet(external / "player_crosswalk.parquet")
    accepted = crosswalk[crosswalk["status"].eq("accepted")].copy()
    cache_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "profiles"
    client = BeSoccerClient(cache_dir=cache_root, min_delay=10.0, max_delay=14.0)

    profiles, careers, failures = [], [], []
    for row in accepted.to_dict("records"):
        try:
            profile = parse_player_profile(client.get_html(row["besoccer_url"]), row["besoccer_url"])
        except requests.HTTPError as error:
            failures.append({"uaefa_player_id": row["uaefa_player_id"], "url": row["besoccer_url"], "error": str(error)})
            print(f"{row['uaefa_name']}: skipped after server error")
            continue

        profile_row = {
            "uaefa_player_id": row["uaefa_player_id"],
            "club_id": row["club_id"],
            "club_name": row["club_name"],
            "uaefa_name": row["uaefa_name"],
            "besoccer_player_id": profile["besoccer_player_id"],
            "besoccer_name": profile["name"],
            "birth_date": profile["birth_date"],
            "nationality": profile["nationality"],
            "birth_place": profile["birth_place"],
            "height_cm": quantity_value(profile["height"]),
            "weight_kg": quantity_value(profile["weight"]),
            "position_main": profile["main_position"] or profile["job_title"],
            "positions_secondary_json": json.dumps(profile["other_positions"], ensure_ascii=False),
            "elo_current": profile["elo_current"],
            "elo_history_json": json.dumps(profile["elo_history"], ensure_ascii=False),
            "market_value_current_eur": profile["market_value_current_eur"],
            "market_value_history_json": json.dumps(profile["market_value_history"], ensure_ascii=False),
            "source_url": profile["source_url"],
            "matched_by": row["match_method"],
        }
        profiles.append(profile_row)
        for club in profile["career"]:
            careers.append({"uaefa_player_id": row["uaefa_player_id"], "besoccer_player_id": profile["besoccer_player_id"], **club})
        print(f"{row['uaefa_name']}: profile saved")

    pd.DataFrame(profiles).to_parquet(external / "player_profiles.parquet", index=False)
    pd.DataFrame(careers).to_parquet(external / "player_career.parquet", index=False)
    summary = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "accepted_crosswalks": int(len(accepted)),
        "profiles_saved": int(len(profiles)),
        "career_rows": int(len(careers)),
        "requests": client.request_count,
        "media_downloads": 0,
        "failures": failures,
    }
    (external / "profiles_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
