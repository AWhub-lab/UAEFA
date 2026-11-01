#!/usr/bin/env python3
"""Fetch official UAEFA player profiles once and distribute them by competition.

The same player may appear in more than one competition. A shared raw cache
prevents duplicate federation calls while every processed snapshot retains its
own profile table for independent validation and future deployment.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_SCRIPT = Path(__file__).with_name("download_first_division_week1.py")
DATASETS = {
    "second": "second_division_2026_2027",
    "third": "third_division_2026_2027",
    "u23": "pro_league_u23_2026_2027",
}
SHARED_RAW = PROJECT_ROOT / "data" / "raw" / "player_profiles_uaefa"


def load_pilot_module():
    spec = importlib.util.spec_from_file_location("uaefa_profile_batch", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the shared UAEFA client.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def profile_row(player_id: str, payload: dict) -> dict | None:
    values = payload.get("players") or []
    if not values:
        return None
    player = values[0]
    return {
        "player_id": str(player.get("player_id", player_id)), "name_en_official": player.get("name"),
        "shortname_en_official": player.get("shortname"), "jersey_no_official": player.get("jersey_no"),
        "jersey_name_official": player.get("jersey_name"), "current_team_id": player.get("current_team_id"),
        "team_official": player.get("team"), "club_id_official": player.get("club_id"),
        "club_name_official": player.get("club"), "position_official": player.get("position"),
        "nationality_official": player.get("nationality"), "nationality_id_official": player.get("nationality_id"),
        "birth_date_official": player.get("dob"), "status_official": player.get("status"),
        "first_registration_date": player.get("first_reg_date"), "person_category_official": player.get("person_category"),
        "source_url": f"https://www.uaefa.ae/api/players?lang=en&player_id={player_id}",
    }


def legacy_profile(player_id: str) -> Path | None:
    for directory in ("first_division_2026_2027", *DATASETS.values()):
        candidate = PROJECT_ROOT / "data" / "raw" / directory / "player_profiles" / f"{player_id}.json"
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competitions", nargs="+", choices=sorted(DATASETS), default=sorted(DATASETS))
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=4.5)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")

    competition_ids: dict[str, set[str]] = {}
    for code in args.competitions:
        root = PROJECT_ROOT / "data" / "processed" / DATASETS[code] / "current"
        players_file = root / "players.parquet"
        if not players_file.exists():
            raise RuntimeError(f"Missing processed players table for {code}: {players_file}")
        competition_ids[code] = set(pd.read_parquet(players_file)["player_id"].astype(str))
    all_ids = sorted(set().union(*competition_ids.values()))
    pilot = load_pilot_module()
    client = pilot.GentleUAEFAClient(args.min_delay, args.max_delay)
    profiles: dict[str, dict] = {}
    failures: list[dict[str, str]] = []
    requested = reused = migrated = 0
    for index, player_id in enumerate(all_ids, start=1):
        destination = SHARED_RAW / f"{player_id}.json"
        if destination.exists():
            payload = json.loads(destination.read_text(encoding="utf-8"))
            reused += 1
            origin = "cached"
        else:
            old_path = legacy_profile(player_id)
            if old_path:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(old_path.read_bytes())
                payload = json.loads(destination.read_text(encoding="utf-8"))
                migrated += 1
                origin = "migrated"
            else:
                try:
                    payload = client.get_json(f"{pilot.API_BASE}/players?lang=en&player_id={player_id}", destination)
                except requests.HTTPError as error:
                    failures.append({"player_id": player_id, "error": str(error)})
                    print(f"[{index}/{len(all_ids)}] {player_id}: server error, skipped", flush=True)
                    continue
                requested += 1
                origin = "saved"
        row = profile_row(player_id, payload)
        if row:
            profiles[player_id] = row
        print(f"[{index}/{len(all_ids)}] {player_id}: {origin}", flush=True)

    generated: dict[str, int] = {}
    for code, identifiers in competition_ids.items():
        root = PROJECT_ROOT / "data" / "processed" / DATASETS[code] / "current"
        rows = [profiles[player_id] for player_id in sorted(identifiers) if player_id in profiles]
        frame = pd.DataFrame(rows).drop_duplicates("player_id", keep="last")
        frame.to_parquet(root / "player_profiles_uaefa.parquet", index=False)
        generated[code] = len(frame)
        summary = {
            "downloaded_at": datetime.now(UTC).isoformat(), "competition": code,
            "requested_player_ids": len(identifiers), "profiles_saved": len(frame),
            "shared_unique_player_ids": len(all_ids), "failures": failures,
            "shared_new_api_responses": requested, "shared_reused_responses": reused,
            "shared_migrated_responses": migrated,
            "request_policy": {"parallel_requests": 0, "min_delay_seconds": args.min_delay, "max_delay_seconds": args.max_delay, "stop_status_codes": [403, 429]},
        }
        (root / "player_profiles_uaefa_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"profiles_by_competition": generated, "unique_players": len(all_ids), "new_api_responses": requested, "reused": reused, "migrated": migrated, "failures": len(failures)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    pilot = load_pilot_module()
    try:
        raise SystemExit(main())
    except pilot.RateLimitError as exc:
        print(f"SAFE STOP: {exc}")
        raise SystemExit(2)
