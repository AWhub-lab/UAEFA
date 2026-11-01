#!/usr/bin/env python3
"""Synchronise one approved UAEFA competition with a conservative request rate.

The downloader only requests an official calendar once, then fetches the
report and event timeline for completed fixtures. Each competition writes to
its own raw, processed and asset directories, so its snapshot can be checked
and published independently before it is exposed in the application.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_SCRIPT = Path(__file__).with_name("download_first_division_week1.py")


@dataclass(frozen=True)
class Competition:
    identifier: str
    name: str
    directory: str
    season_start: str


COMPETITIONS = {
    "second": Competition("2573", "Second Division league", "second_division_2026_2027", "2026-08-28"),
    "third": Competition("2574", "Third Division league", "third_division_2026_2027", "2026-09-04"),
    "u23": Competition("2578", "Pro League U23 Years", "pro_league_u23_2026_2027", "2026-08-15"),
}


def load_pilot_module():
    spec = importlib.util.spec_from_file_location("uaefa_downloader", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the shared UAEFA downloader.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cached_or_fetch(client: Any, url: str, destination: Path) -> tuple[dict[str, Any], bool]:
    if destination.exists():
        return json.loads(destination.read_text(encoding="utf-8")), False
    return client.get_json(url, destination), True


def competition_matches(payload: dict[str, Any], competition_id: str) -> list[dict[str, Any]]:
    for group in payload.get("matches", []):
        if str(group.get("attributes", {}).get("competition_id")) == competition_id:
            return sorted(group.get("items", []), key=lambda item: (int(item.get("week_no") or 0), int(item["match_id"])))
    return []


def add_scheduled_match(match: dict[str, Any], tables: dict[str, list[dict[str, Any]]], clubs: dict[str, dict[str, Any]], pilot: Any) -> None:
    """Keep calendar-only fixtures visible without inventing sporting data."""
    raw_time = str(match.get("time") or "")
    try:
        kickoff = datetime.strptime(raw_time, "%Y-%m-%d %I:%M %p")
        match_date, match_time = kickoff.date().isoformat(), kickoff.strftime("%H:%M")
    except ValueError:
        match_date, match_time = raw_time[:10], raw_time[11:]
    home_id = str(match.get("club1_id") or "")
    away_id = str(match.get("club2_id") or match.get("club2_ld") or "")
    for club_id, name in ((home_id, match.get("club1")), (away_id, match.get("club2"))):
        if club_id:
            clubs.setdefault(club_id, {"club_id": club_id, "club_name": name, "crest_url": pilot.image_url("club", club_id), "crest_file": None})
    tables["matches"].append(
        {
            "match_id": str(match["match_id"]), "competition_id": match.get("competition_id"),
            "competition": match.get("competition"), "season": "2026/2027", "week_no": match.get("week_no"),
            "match_no": match.get("match_no"), "match_date": match_date, "match_time": match_time,
            "status_id": match.get("status_id"), "home_club_id": home_id, "home_club_name": match.get("club1"),
            "away_club_id": away_id, "away_club_name": match.get("club2"), "home_score": None,
            "away_score": None, "home_score_h1": None, "away_score_h1": None,
            "playground": match.get("playground"), "playground_id": match.get("playground_id"),
            "attendance": None, "round": match.get("round"), "group": match.get("group"),
            "stage": match.get("stage"), "source_url": f"https://www.uaefa.ae/en/match/{match['match_id']}",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("competition", choices=sorted(COMPETITIONS))
    parser.add_argument("--date-to", default=date.today().isoformat(), help="Calendar end date in YYYY-MM-DD format.")
    parser.add_argument("--skip-media", action="store_true", help="Defer crest and portrait downloads until core data has passed validation.")
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=4.5)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")

    competition = COMPETITIONS[args.competition]
    pilot = load_pilot_module()
    raw_root = PROJECT_ROOT / "data" / "raw" / competition.directory
    processed_root = PROJECT_ROOT / "data" / "processed" / competition.directory / "current"
    assets_root = PROJECT_ROOT / "data" / "assets" / competition.directory
    pilot.PROCESSED_ROOT = processed_root
    pilot.ASSETS_ROOT = assets_root
    client = pilot.GentleUAEFAClient(args.min_delay, args.max_delay)

    calendar_path = raw_root / "calendar" / f"matches_{competition.season_start}_{args.date_to}.json"
    calendar_url = f"{pilot.API_BASE}/matches?lang=en&date_from={competition.season_start}&date_to={args.date_to}"
    calendar, calendar_is_new = cached_or_fetch(client, calendar_url, calendar_path)
    fixtures = competition_matches(calendar, competition.identifier)
    completed = [fixture for fixture in fixtures if str(fixture.get("status_id")) == "6"]
    scheduled = [fixture for fixture in fixtures if str(fixture.get("status_id")) != "6"]
    if not completed:
        raise RuntimeError(f"No completed matches found for {competition.name}; no data was written.")

    tables = {name: [] for name in pilot.TABLE_COLUMNS}
    clubs: dict[str, dict[str, Any]] = {}
    players: dict[str, dict[str, Any]] = {}
    requested = int(calendar_is_new)
    reused = int(not calendar_is_new)
    for index, match in enumerate(completed, start=1):
        match_id = str(match["match_id"])
        print(f"[{competition.identifier} {index}/{len(completed)}] {match_id}: {match['club1']} vs {match['club2']}", flush=True)
        report, report_is_new = cached_or_fetch(client, f"{pilot.API_BASE}/match_report?match_id={match_id}", raw_root / "matches" / match_id / "match_report.json")
        events, events_is_new = cached_or_fetch(client, f"{pilot.API_BASE}/match_highlights2?lang=en&match_id={match_id}", raw_root / "matches" / match_id / "match_highlights2.json")
        requested += int(report_is_new) + int(events_is_new)
        reused += int(not report_is_new) + int(not events_is_new)
        pilot.normalise_report(match, report, events, tables, players, clubs)

    for match in scheduled:
        add_scheduled_match(match, tables, clubs, pilot)
    tables["clubs"] = list(clubs.values())
    tables["players"] = list(players.values())
    media = {"crests": 0, "portraits": 0, "missing": 0}
    if not args.skip_media:
        print(f"Media phase: {len(clubs)} clubs and {len(players)} players.", flush=True)
        media = pilot.download_media(client, clubs, players)
        tables["clubs"] = list(clubs.values())
        tables["players"] = list(players.values())
    for name, rows in tables.items():
        pilot.write_table(name, rows)

    summary = {
        "synchronised_at": datetime.now(UTC).isoformat(), "competition_id": competition.identifier,
        "competition": competition.name, "season": "2026/2027", "calendar_date_from": competition.season_start,
        "calendar_date_to": args.date_to, "calendar_matches": len(fixtures), "completed_matches": len(completed),
        "scheduled_matches": len(scheduled), "weeks": sorted({int(match.get("week_no") or 0) for match in fixtures}),
        "clubs": len(tables["clubs"]), "players": len(tables["players"]), "appearances": len(tables["appearances"]),
        "events": len(tables["events"]), "staff": len(tables["staff"]), "new_api_responses": requested,
        "reused_api_responses": reused, "media": media,
        "request_policy": {"parallel_requests": 0, "min_delay_seconds": args.min_delay, "max_delay_seconds": args.max_delay, "stop_status_codes": [403, 429]},
    }
    processed_root.mkdir(parents=True, exist_ok=True)
    (processed_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    pilot = load_pilot_module()
    try:
        raise SystemExit(main())
    except pilot.RateLimitError as exc:
        print(f"SAFE STOP: {exc}")
        raise SystemExit(2)
