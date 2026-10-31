"""Download unresolved BeSoccer player candidates with a resumable local cache.

Candidates are intentionally kept separate from validated UAEFA enrichments.
They are later promoted only when the official UAEFA date of birth confirms the
identity, so a weak name match can never alter the app on its own.
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

from uaefa_scraper.besoccer import AccessLimitedError, BeSoccerClient, parse_player_profile


def quantity_value(value: object) -> str | None:
    return str(value.get("value")) if isinstance(value, dict) and value.get("value") is not None else None


def profile_row(profile: dict[str, object]) -> dict[str, object]:
    return {
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
    }


def main() -> None:
    external = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"
    crosswalk = pd.read_parquet(external / "player_crosswalk_validated.parquet")
    pending = crosswalk[crosswalk["identity_validation"].eq("review_required")].copy()
    pending = pending.drop_duplicates("besoccer_player_id")

    output_path = external / "pending_candidate_profiles.parquet"
    summary_path = external / "pending_candidate_profiles_summary.json"
    saved = pd.read_parquet(output_path) if output_path.exists() else pd.DataFrame()
    saved_ids = set(saved.get("besoccer_player_id", pd.Series(dtype="int64")).astype(str))

    cache_root = PROJECT_ROOT / "data" / "raw" / "besoccer" / "profiles"
    client = BeSoccerClient(cache_dir=cache_root, min_delay=10.0, max_delay=14.0)
    rows = saved.to_dict("records")
    failures: list[dict[str, str]] = []
    stopped = False

    for index, candidate in enumerate(pending.to_dict("records"), start=1):
        candidate_id = str(candidate["besoccer_player_id"])
        if candidate_id in saved_ids:
            continue
        try:
            profile = parse_player_profile(client.get_html(candidate["besoccer_url"]), candidate["besoccer_url"])
        except AccessLimitedError as error:
            failures.append({"besoccer_player_id": candidate_id, "url": candidate["besoccer_url"], "error": str(error)})
            stopped = True
            print(f"Stopped safely: {error}")
            break
        except requests.HTTPError as error:
            failures.append({"besoccer_player_id": candidate_id, "url": candidate["besoccer_url"], "error": str(error)})
            print(f"Skipped {candidate_id}: {error}")
            continue

        rows.append(profile_row(profile))
        saved_ids.add(candidate_id)
        # Checkpoint every successful response so an interrupted run is resumable.
        pd.DataFrame(rows).drop_duplicates("besoccer_player_id", keep="last").to_parquet(output_path, index=False)
        print(f"[{index}/{len(pending)}] saved {profile['name']} ({candidate_id})")

    result = pd.DataFrame(rows).drop_duplicates("besoccer_player_id", keep="last")
    result.to_parquet(output_path, index=False)
    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "unique_pending_candidates": int(len(pending)),
        "profiles_saved": int(len(result)),
        "new_requests_this_run": client.request_count,
        "stopped_safely": stopped,
        "failures": failures,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
