#!/usr/bin/env python3
"""Incrementally cache official UAEFA player identity profiles.

Only player IDs already observed in the First Division match reports are read.
The script makes one sequential request per missing profile, preserves every
official JSON response, and stops immediately if UAEFA returns 403 or 429.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_SCRIPT = Path(__file__).with_name("download_first_division_week1.py")
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "first_division_2026_2027" / "player_profiles"


def load_pilot_module():
    spec = importlib.util.spec_from_file_location("first_division_pilot", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the shared UAEFA client.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def profile_row(player_id: str, payload: dict) -> dict | None:
    players = payload.get("players") or []
    if not players:
        return None
    player = players[0]
    return {
        "player_id": str(player.get("player_id", player_id)),
        "name_en_official": player.get("name"),
        "shortname_en_official": player.get("shortname"),
        "jersey_no_official": player.get("jersey_no"),
        "jersey_name_official": player.get("jersey_name"),
        "current_team_id": player.get("current_team_id"),
        "team_official": player.get("team"),
        "club_id_official": player.get("club_id"),
        "club_name_official": player.get("club"),
        "position_official": player.get("position"),
        "nationality_official": player.get("nationality"),
        "nationality_id_official": player.get("nationality_id"),
        "birth_date_official": player.get("dob"),
        "status_official": player.get("status"),
        "first_registration_date": player.get("first_reg_date"),
        "person_category_official": player.get("person_category"),
        "source_url": f"https://www.uaefa.ae/api/players?lang=en&player_id={player_id}",
    }


def main() -> int:
    pilot = load_pilot_module()
    players = pd.read_parquet(PROCESSED_ROOT / "players.parquet")
    player_ids = sorted(players["player_id"].astype(str).unique())
    client = pilot.GentleUAEFAClient(min_delay=2.5, max_delay=4.5)
    rows, failures, fetched, reused = [], [], 0, 0

    for index, player_id in enumerate(player_ids, start=1):
        path = RAW_ROOT / f"{player_id}.json"
        try:
            payload = client.get_json(
                f"{pilot.API_BASE}/players?lang=en&player_id={player_id}", path
            )
        except requests.HTTPError as error:
            # Do not retry 5xx responses in the same run; preserve a gentle rate.
            failures.append({"player_id": player_id, "error": str(error)})
            print(f"[{index}/{len(player_ids)}] {player_id}: server error, skipped", flush=True)
            continue
        if path.exists():
            # Existing cache was reused unless it was just fetched in this run.
            # The client has no request counter, so infer it from the pre-read state.
            pass
        row = profile_row(player_id, payload)
        if row:
            rows.append(row)
        print(f"[{index}/{len(player_ids)}] {player_id}: profile {'saved' if row else 'empty'}", flush=True)

    profiles = pd.DataFrame(rows).drop_duplicates("player_id", keep="last")
    profiles.to_parquet(PROCESSED_ROOT / "player_profiles_uaefa.parquet", index=False)
    summary = {
        "downloaded_at": datetime.now(UTC).isoformat(),
        "requested_player_ids": len(player_ids),
        "profiles_saved": len(profiles),
        "failures": failures,
        "request_policy": {
            "parallel_requests": 0,
            "min_delay_seconds": 2.5,
            "max_delay_seconds": 4.5,
            "stop_status_codes": [403, 429],
        },
    }
    (PROCESSED_ROOT / "player_profiles_uaefa_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    pilot = load_pilot_module()
    try:
        raise SystemExit(main())
    except pilot.RateLimitError as error:
        print(f"SAFE STOP: {error}")
        raise SystemExit(2)
