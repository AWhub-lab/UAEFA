#!/usr/bin/env python3
"""Download UAE First Division 2026/27 week 1 with a conservative request rate.

The script keeps immutable API responses in ``data/raw`` and writes normalized
Parquet tables in ``data/processed``. It only targets the seven known matches
from the week-one date window, never crawls links, and can be rerun safely.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "first_division_2026_2027" / "week_01"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "week_01"
ASSETS_ROOT = PROJECT_ROOT / "data" / "assets" / "first_division_2026_2027"

API_BASE = "https://www.uaefa.ae/api"
FANET_IMAGE_BASE = "https://fanet.ae/UAEFA/img.ashx"
COMPETITION_ID = "2572"
WEEK_NUMBER = "1"
DATE_FROM = "2026-08-20"
DATE_TO = "2026-08-25"

TABLE_COLUMNS = {
    "matches": [
        "match_id", "competition_id", "competition", "season", "week_no", "match_no",
        "match_date", "match_time", "status_id", "home_club_id", "home_club_name",
        "away_club_id", "away_club_name", "home_score", "away_score", "home_score_h1",
        "away_score_h1", "playground", "playground_id", "attendance", "round", "group",
        "stage", "source_url",
    ],
    "clubs": ["club_id", "club_name", "crest_url", "crest_file"],
    "players": [
        "player_id", "name_en", "shortname_en", "name_ar", "shortname_ar", "position",
        "position_id", "nationality_id", "nationality_category", "player_status", "team_en",
        "photo_url", "photo_file",
    ],
    "appearances": [
        "match_id", "club_id", "player_id", "squad_role", "started", "has_played", "dorsal",
        "position", "formation_position", "captain", "minute_in", "minute_out",
    ],
    "events": [
        "match_id", "event_order", "event_type", "minute", "fulltime", "club_side", "club_id",
        "player_id", "player_name", "dorsal", "in_player_id", "in_player_name", "goal_type_id",
        "reason_id",
    ],
    "staff": [
        "match_id", "club_id", "person_id", "name_en", "shortname_en", "role", "role_order",
        "voting_eligible",
    ],
}


class RateLimitError(RuntimeError):
    """Raised when UAEFA explicitly asks us to slow down or stop."""


class GentleUAEFAClient:
    """Single-session client with disk cache and deliberately slow requests."""

    def __init__(self, min_delay: float, max_delay: float) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.uaefa.ae/en/competitions",
                "User-Agent": "UAEFA-First-Division-Research/0.1 (respectful, cached)",
            }
        )

    def _wait(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _get(self, url: str, *, stream: bool = False) -> requests.Response:
        # No parallelism, no retries after explicit rate limiting, no proxy rotation.
        self._wait()
        response = self.session.get(url, timeout=30, stream=stream)
        if response.status_code in {403, 429}:
            raise RateLimitError(f"UAEFA returned HTTP {response.status_code}; stopping safely.")
        response.raise_for_status()
        return response

    def get_json(self, url: str, path: Path, force: bool = False) -> dict[str, Any]:
        if path.exists() and not force:
            return json.loads(path.read_text(encoding="utf-8"))
        response = self._get(url)
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def get_image(self, url: str, destination_stem: Path) -> Path | None:
        cached = list(destination_stem.parent.glob(f"{destination_stem.name}.*"))
        if cached:
            return cached[0]
        response = self._get(url, stream=True)
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            return None
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type.split(";", 1)[0].lower(), ".img")
        destination = destination_stem.with_suffix(suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination


def as_list(value: Any) -> list[dict[str, Any]]:
    """UAEFA uses either an object or list for collections with one item."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first_non_empty(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Merge repeated player records without replacing useful values with blanks."""
    for key, value in candidate.items():
        if existing.get(key) in (None, "") and value not in (None, ""):
            existing[key] = value
    return existing


def image_url(image_type: str, identifier: str) -> str:
    return f"{FANET_IMAGE_BASE}?type={image_type}&id={identifier}"


def write_table(name: str, rows: Iterable[dict[str, Any]]) -> None:
    records = list(rows)
    frame = pd.DataFrame(records, columns=TABLE_COLUMNS[name])
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(PROCESSED_ROOT / f"{name}.parquet", index=False)


def fetch_week_one_matches(client: GentleUAEFAClient) -> list[dict[str, Any]]:
    url = f"{API_BASE}/matches?lang=en&date_from={DATE_FROM}&date_to={DATE_TO}"
    payload = client.get_json(url, RAW_ROOT / "match_list.json")
    found: list[dict[str, Any]] = []
    for competition in payload.get("matches", []):
        attrs = competition.get("attributes", {})
        if str(attrs.get("competition_id")) != COMPETITION_ID:
            continue
        for match in competition.get("items", []):
            if str(match.get("week_no")) == WEEK_NUMBER:
                found.append(match)
    return sorted(found, key=lambda row: int(row["match_id"]))


def normalise_report(
    match: dict[str, Any], report: dict[str, Any], highlights: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]], players: dict[str, dict[str, Any]],
    clubs: dict[str, dict[str, Any]],
) -> None:
    match_id = str(match["match_id"])
    report_body = report.get("match_report", {})
    report_attrs = report_body.get("attributes", {})
    teams = [("H", report_body.get("team1", {})), ("A", report_body.get("team2", {}))]
    team_ids: dict[str, str] = {}

    for side, team in teams:
        attrs = team.get("attributes", {})
        club_id = str(attrs.get("id", ""))
        team_ids[side] = club_id
        clubs.setdefault(
            club_id,
            {
                "club_id": club_id,
                "club_name": attrs.get("name_en"),
                "crest_url": image_url("club", club_id),
                "crest_file": None,
            },
        )

    home = teams[0][1].get("attributes", {})
    away = teams[1][1].get("attributes", {})
    tables["matches"].append(
        {
            "match_id": match_id,
            "competition_id": report_attrs.get("competition_id", match.get("competition_id")),
            "competition": report_attrs.get("competition_en", match.get("competition")),
            "season": report_attrs.get("season_en"),
            "week_no": report_attrs.get("week", match.get("week_no")),
            "match_no": report_attrs.get("match_no", match.get("match_no")),
            "match_date": report_attrs.get("match_date"),
            "match_time": report_attrs.get("match_time"),
            "status_id": report_attrs.get("status_id", match.get("status_id")),
            "home_club_id": team_ids["H"],
            "home_club_name": home.get("name_en"),
            "away_club_id": team_ids["A"],
            "away_club_name": away.get("name_en"),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "home_score_h1": home.get("score_h1"),
            "away_score_h1": away.get("score_h1"),
            "playground": report_attrs.get("Stadium_en", match.get("playground")),
            "playground_id": match.get("playground_id"),
            "attendance": report_attrs.get("attendance"),
            "round": report_attrs.get("round_en", match.get("round")),
            "group": report_attrs.get("group_en", match.get("group")),
            "stage": report_attrs.get("stage_en", match.get("stage")),
            "source_url": f"https://www.uaefa.ae/en/match/{match_id}",
        }
    )

    for side, team in teams:
        attrs = team.get("attributes", {})
        club_id = team_ids[side]
        for squad_role, block in (("starter", team.get("active", {})), ("substitute", team.get("substitute", {}))):
            for player in as_list(block.get("player")):
                # Some lower-division reports include empty list placeholders or
                # substitution metadata in the player collection. They are not
                # player records and must not become appearances.
                if not isinstance(player, dict) or not isinstance(player.get("attributes"), dict):
                    continue
                player_attrs = player.get("attributes", {})
                player_id = str(player_attrs.get("player_id", ""))
                if not player_id:
                    continue
                player_row = {
                    "player_id": player_id,
                    "name_en": player_attrs.get("name_en"),
                    "shortname_en": player_attrs.get("shortname_en"),
                    "name_ar": player_attrs.get("name_ar"),
                    "shortname_ar": player_attrs.get("shortname_ar"),
                    "position": player_attrs.get("position"),
                    "position_id": player_attrs.get("position_id"),
                    "nationality_id": player_attrs.get("nationality_id"),
                    "nationality_category": player_attrs.get("cat_en"),
                    "player_status": player_attrs.get("playerstatus_en"),
                    "team_en": player_attrs.get("team_en"),
                    "photo_url": image_url("person", player_id),
                    "photo_file": None,
                }
                players[player_id] = first_non_empty(players.get(player_id, player_row), player_row)
                tables["appearances"].append(
                    {
                        "match_id": match_id,
                        "club_id": club_id,
                        "player_id": player_id,
                        "squad_role": squad_role,
                        "started": squad_role == "starter",
                        "has_played": player_attrs.get("hasPlayed") == "1" or squad_role == "starter",
                        "dorsal": player_attrs.get("j_no"),
                        "position": player_attrs.get("position"),
                        "formation_position": player_attrs.get("formation_pos"),
                        "captain": player_attrs.get("captain") == "1",
                        "minute_in": player.get("subs_in", {}).get("time"),
                        "minute_out": player.get("subs_out", {}).get("time"),
                    }
                )

        for official in as_list(team.get("official")):
            if not isinstance(official, dict):
                continue
            tables["staff"].append(
                {
                    "match_id": match_id,
                    "club_id": club_id,
                    "person_id": official.get("person_id"),
                    "name_en": official.get("name_en"),
                    "shortname_en": official.get("shortname_en"),
                    "role": official.get("title_name_en"),
                    "role_order": official.get("type_ord"),
                    "voting_eligible": official.get("voting") == "1",
                }
            )

    for event_order, event in enumerate(highlights.get("match_highlights2", {}).get("event", []), start=1):
        if not isinstance(event, dict):
            continue
        side = event.get("club_dir")
        tables["events"].append(
            {
                "match_id": match_id,
                "event_order": event_order,
                "event_type": event.get("type"),
                "minute": event.get("time"),
                "fulltime": event.get("fulltime"),
                "club_side": side,
                "club_id": team_ids.get(side),
                "player_id": event.get("player_id"),
                "player_name": event.get("player_name"),
                "dorsal": event.get("j_no"),
                "in_player_id": event.get("in_player_id"),
                "in_player_name": event.get("in_player_name"),
                "goal_type_id": event.get("goal_type"),
                "reason_id": event.get("reason_id"),
            }
        )


def download_media(client: GentleUAEFAClient, clubs: dict[str, dict[str, Any]], players: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Download public crests and player portraits once, skipping cached files."""
    downloaded = {"crests": 0, "portraits": 0, "missing": 0}
    for club_id, club in clubs.items():
        target = ASSETS_ROOT / "clubs" / str(club_id)
        saved = client.get_image(club["crest_url"], target)
        if saved:
            club["crest_file"] = str(saved.relative_to(PROJECT_ROOT))
            downloaded["crests"] += 1
        else:
            downloaded["missing"] += 1
    for player_id, player in players.items():
        target = ASSETS_ROOT / "players" / str(player_id)
        saved = client.get_image(player["photo_url"], target)
        if saved:
            player["photo_file"] = str(saved.relative_to(PROJECT_ROOT))
            downloaded["portraits"] += 1
        else:
            downloaded["missing"] += 1
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-media", action="store_true", help="Do not download club crests or player portraits.")
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=4.5)
    args = parser.parse_args()
    if args.min_delay <= 0 or args.max_delay < args.min_delay:
        parser.error("Use positive delays where --max-delay is at least --min-delay.")

    client = GentleUAEFAClient(args.min_delay, args.max_delay)
    tables = {name: [] for name in TABLE_COLUMNS}
    clubs: dict[str, dict[str, Any]] = {}
    players: dict[str, dict[str, Any]] = {}

    matches = fetch_week_one_matches(client)
    if len(matches) != 7:
        raise RuntimeError(f"Expected 7 First Division week-one matches, found {len(matches)}. Stopping for review.")

    for index, match in enumerate(matches, start=1):
        match_id = str(match["match_id"])
        print(f"[{index}/{len(matches)}] Downloading match {match_id}: {match['club1']} vs {match['club2']}", flush=True)
        report = client.get_json(
            f"{API_BASE}/match_report?match_id={match_id}",
            RAW_ROOT / "matches" / match_id / "match_report.json",
        )
        highlights = client.get_json(
            f"{API_BASE}/match_highlights2?lang=en&match_id={match_id}",
            RAW_ROOT / "matches" / match_id / "match_highlights2.json",
        )
        normalise_report(match, report, highlights, tables, players, clubs)

    media_summary = {"crests": 0, "portraits": 0, "missing": 0}
    if not args.skip_media:
        print(f"Downloading media for {len(clubs)} clubs and {len(players)} unique players.", flush=True)
        media_summary = download_media(client, clubs, players)

    tables["clubs"] = list(clubs.values())
    tables["players"] = list(players.values())
    for name, rows in tables.items():
        write_table(name, rows)

    summary = {
        "downloaded_at": datetime.now(UTC).isoformat(),
        "competition_id": COMPETITION_ID,
        "competition": "First Division league",
        "season": "2026/2027",
        "week": int(WEEK_NUMBER),
        "matches": len(tables["matches"]),
        "clubs": len(tables["clubs"]),
        "players": len(tables["players"]),
        "appearances": len(tables["appearances"]),
        "events": len(tables["events"]),
        "staff": len(tables["staff"]),
        "media": media_summary,
        "request_policy": {
            "parallel_requests": 0,
            "min_delay_seconds": args.min_delay,
            "max_delay_seconds": args.max_delay,
            "stop_status_codes": [403, 429],
        },
    }
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    (PROCESSED_ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RateLimitError as exc:
        print(f"SAFE STOP: {exc}")
        raise SystemExit(2)
