#!/usr/bin/env python3
"""Incrementally synchronise completed UAE First Division 2026/27 matches.

One calendar request discovers the official match IDs. Existing raw responses
and images are reused; only missing match reports, timelines and media are
requested. The resulting Parquet tables represent every downloaded round.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_SCRIPT = Path(__file__).with_name("download_first_division_week1.py")
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "first_division_2026_2027"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
COMPETITION_ID = "2572"
SEASON_START = "2026-08-20"


def load_pilot_module():
    spec = importlib.util.spec_from_file_location("first_division_pilot", PILOT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the shared First Division downloader.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_existing_or_fetch(client: Any, url: str, candidates: list[Path]) -> tuple[dict[str, Any], bool]:
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), False
    target = candidates[-1]
    return client.get_json(url, target), True


def first_division_calendar_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every official fixture, including those without a match report yet."""
    matches: list[dict[str, Any]] = []
    for group in payload.get("matches", []):
        if str(group.get("attributes", {}).get("competition_id")) != COMPETITION_ID:
            continue
        matches.extend(group.get("items", []))
    return sorted(matches, key=lambda item: (int(item.get("week_no", 0)), int(item["match_id"])))


def normalise_scheduled_match(match: dict[str, Any], tables: dict[str, list[dict[str, Any]],], clubs: dict[str, dict[str, Any]], pilot: Any) -> None:
    """Add a calendar fixture without requesting an unavailable report or lineup."""
    raw_time = str(match.get("time") or "")
    try:
        kickoff = datetime.strptime(raw_time, "%Y-%m-%d %I:%M %p")
        match_date, match_time = kickoff.date().isoformat(), kickoff.strftime("%H:%M")
    except ValueError:
        match_date, match_time = raw_time[:10], raw_time[11:]
    home_id = str(match.get("club1_id") or "")
    # UAEFA's calendar currently exposes this field with a historical typo.
    away_id = str(match.get("club2_id") or match.get("club2_ld") or "")
    for club_id, name in ((home_id, match.get("club1")), (away_id, match.get("club2"))):
        if club_id:
            clubs.setdefault(
                club_id,
                {"club_id": club_id, "club_name": name, "crest_url": pilot.image_url("club", club_id), "crest_file": None},
            )
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


def hydrate_cached_media(clubs: dict[str, dict[str, Any]], players: dict[str, dict[str, Any]]) -> None:
    """Reconnect Parquet rows to media already stored locally after an offline sync."""
    media_root = PROJECT_ROOT / "data" / "assets" / "first_division_2026_2027"

    def local_media(kind: str, identifier: str) -> str | None:
        files = sorted((media_root / kind).glob(f"{identifier}.*"))
        return str(files[0].relative_to(PROJECT_ROOT)) if files else None

    for club_id, club in clubs.items():
        club["crest_file"] = local_media("clubs", str(club_id))
    for player_id, player in players.items():
        player["photo_file"] = local_media("players", str(player_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-to", default=date.today().isoformat(), help="Calendar end date in YYYY-MM-DD format.")
    parser.add_argument("--skip-media", action="store_true", help="Do not download missing public crests and portraits.")
    parser.add_argument("--offline", action="store_true", help="Rebuild from the cached calendar and match responses without network requests.")
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=4.5)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")

    pilot = load_pilot_module()
    client = pilot.GentleUAEFAClient(args.min_delay, args.max_delay)
    calendar_url = f"{pilot.API_BASE}/matches?lang=en&date_from={SEASON_START}&date_to={args.date_to}"
    calendar_path = RAW_ROOT / "calendar" / f"matches_{SEASON_START}_{args.date_to}.json"
    # A cached rebuild is useful after an interrupted run and never makes a
    # second request to the federation just to consolidate already saved data.
    if args.offline:
        cached_calendars = sorted(RAW_ROOT.joinpath("calendar").glob("matches_*.json"), key=lambda path: path.stat().st_mtime)
        if not cached_calendars:
            raise RuntimeError("No cached calendar is available for an offline rebuild.")
        calendar_path = cached_calendars[-1]
        calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
    else:
        # The calendar is deliberately refreshed once per run so new rounds are discovered.
        calendar = client.get_json(calendar_url, calendar_path, force=True)
    calendar_matches = first_division_calendar_matches(calendar)
    completed_matches = [item for item in calendar_matches if str(item.get("status_id")) == "6"]
    scheduled_matches = [item for item in calendar_matches if str(item.get("status_id")) != "6"]
    if not completed_matches:
        raise RuntimeError("No completed First Division matches were found. Stopping without changes.")

    tables = {name: [] for name in pilot.TABLE_COLUMNS}
    clubs: dict[str, dict[str, Any]] = {}
    players: dict[str, dict[str, Any]] = {}
    new_reports = 0
    reused_reports = 0

    for index, match in enumerate(completed_matches, start=1):
        match_id = str(match["match_id"])
        print(f"[{index}/{len(completed_matches)}] {match_id}: {match['club1']} vs {match['club2']}", flush=True)
        legacy = pilot.RAW_ROOT / "matches" / match_id
        current = RAW_ROOT / "matches" / match_id
        report, report_is_new = read_existing_or_fetch(
            client,
            f"{pilot.API_BASE}/match_report?match_id={match_id}",
            [legacy / "match_report.json", current / "match_report.json"],
        )
        highlights, highlights_is_new = read_existing_or_fetch(
            client,
            f"{pilot.API_BASE}/match_highlights2?lang=en&match_id={match_id}",
            [legacy / "match_highlights2.json", current / "match_highlights2.json"],
        )
        new_reports += int(report_is_new) + int(highlights_is_new)
        reused_reports += int(not report_is_new) + int(not highlights_is_new)
        pilot.normalise_report(match, report, highlights, tables, players, clubs)

    for match in scheduled_matches:
        normalise_scheduled_match(match, tables, clubs, pilot)

    media_summary = {"crests": 0, "portraits": 0, "missing": 0}
    if not args.skip_media:
        print(f"Checking media for {len(clubs)} clubs and {len(players)} players.", flush=True)
        media_summary = pilot.download_media(client, clubs, players)
    else:
        hydrate_cached_media(clubs, players)

    tables["clubs"] = list(clubs.values())
    tables["players"] = list(players.values())
    pilot.PROCESSED_ROOT = OUTPUT_ROOT
    for name, rows in tables.items():
        pilot.write_table(name, rows)

    summary = {
        "synchronised_at": datetime.now(UTC).isoformat(),
        "competition_id": COMPETITION_ID,
        "competition": "First Division league",
        "season": "2026/2027",
        "calendar_date_from": SEASON_START,
        "calendar_date_to": args.date_to,
        "calendar_matches": len(calendar_matches),
        "completed_matches": len(completed_matches),
        "scheduled_matches": len(scheduled_matches),
        "weeks": sorted({int(match["week_no"]) for match in calendar_matches}),
        "clubs": len(tables["clubs"]),
        "players": len(tables["players"]),
        "appearances": len(tables["appearances"]),
        "events": len(tables["events"]),
        "staff": len(tables["staff"]),
        "new_api_responses": new_reports,
        "reused_api_responses": reused_reports,
        "media_available": media_summary,
        "request_policy": {
            "parallel_requests": 0,
            "min_delay_seconds": args.min_delay,
            "max_delay_seconds": args.max_delay,
            "stop_status_codes": [403, 429],
        },
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    pilot = load_pilot_module()
    try:
        raise SystemExit(main())
    except pilot.RateLimitError as exc:
        print(f"SAFE STOP: {exc}")
        raise SystemExit(2)
