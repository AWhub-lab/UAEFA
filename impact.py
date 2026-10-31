"""On-pitch impact metrics for one player (UAE First Division).

Port of the criteria used by the Galician federation app:

* A goal at the same minute as a substitution counts for the player who leaves, not for the one who enters.
* Stoppage-time goals count for whoever is still on the pitch (UAEFA stores 90+3 as minute 93).
* A sent-off player stops adding from the red-card minute (UAEFA leaves ``minute_out`` empty for reds).
* Own goals (``goal_type_id`` 4) count for the club that benefits. Validated against every final score.
* Every match is 90 minutes for the team; there are no stoppage minutes in the totals.

Minimum samples scale with the minutes the team has played, so the figures stay honest early in the season.
"""

from __future__ import annotations

import pandas as pd

MATCH_MINUTES = 90
MIN_WITH = 270  # below this the player sample is flagged as small
MIN_WITHOUT = 180  # below this there is no reliable "without him" reference, so On/Off is hidden
OWN_GOAL = "4"


def _minute(value: object) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def _points(goals_for: int, goals_against: int) -> int:
    return 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0


def _per_90(value: float, minutes: float) -> float | None:
    return value / minutes * MATCH_MINUTES if minutes > 0 else None


def min_with(team_minutes: float) -> float:
    return max(MIN_WITH, 0.30 * team_minutes)


def min_without(team_minutes: float) -> float:
    return max(MIN_WITHOUT, 0.20 * team_minutes)


def _club_goals(events: pd.DataFrame, club_id: str) -> list[tuple[float, bool]]:
    """(minute, scored_by_the_club) for every goal of a match, in chronological order."""
    goals = []
    for event in events[events["event_type"].eq("goal")].itertuples(index=False):
        minute = _minute(event.minute)
        if minute is None:
            continue
        scored_by_club = (str(event.club_id) == club_id) != (str(event.goal_type_id) == OWN_GOAL)
        goals.append((minute, scored_by_club, int(event.event_order)))
    goals.sort(key=lambda goal: (goal[0], goal[2]))
    return [(minute, mine) for minute, mine, _ in goals]


def player_impact(data: dict[str, pd.DataFrame], player_id: str, club_id: str) -> dict[str, object]:
    """Impact of ``player_id`` for ``club_id`` over the matches contained in ``data``."""
    player_id, club_id = str(player_id), str(club_id)
    matches = data["matches"]
    club_matches = matches[(matches["home_club_id"].astype(str).eq(club_id)) | (matches["away_club_id"].astype(str).eq(club_id))]
    appearances = data["appearances"]
    events = data["events"]
    mine = appearances[appearances["player_id"].astype(str).eq(player_id)].set_index("match_id")
    player_events = events[events["player_id"].astype("string").eq(player_id)]

    r: dict[str, object] = {
        "min": 0.0, "pj": 0, "gf": 0, "gc": 0, "team_pj": len(club_matches), "team_min": 0.0, "team_gf": 0, "team_gc": 0, "team_pts": 0,
        "pts_exit": 0, "pts_gained": 0, "clean_sheets": 0, "cs_eligible": 0, "state": {"win": 0.0, "draw": 0.0, "loss": 0.0},
        "bench": {"n": 0, "gf": 0, "gc": 0, "pts": 0, "min": 0.0}, "starts": 0, "subbed_off": 0, "sub_minutes": [], "yellow": 0, "red": 0, "gc_after_red": 0,
    }
    state: dict[str, float] = r["state"]  # type: ignore[assignment]
    bench: dict[str, float] = r["bench"]  # type: ignore[assignment]

    for match in club_matches.itertuples(index=False):
        match_id = str(match.match_id)
        home = str(match.home_club_id) == club_id
        team_for, team_against = (int(match.home_score), int(match.away_score)) if home else (int(match.away_score), int(match.home_score))
        r["team_min"] += MATCH_MINUTES
        r["team_gf"] += team_for
        r["team_gc"] += team_against
        r["team_pts"] += _points(team_for, team_against)

        if match_id not in mine.index:
            continue
        appearance = mine.loc[match_id]
        if isinstance(appearance, pd.DataFrame):
            appearance = appearance.iloc[0]
        started, played = bool(appearance["started"]), bool(appearance["has_played"])
        if not started and not played:
            continue

        match_events = events[events["match_id"].astype(str).eq(match_id)]
        goals = _club_goals(match_events, club_id)
        own_events = player_events[player_events["match_id"].astype(str).eq(match_id)]
        red_minutes = [m for m in (_minute(v) for v in own_events[own_events["event_type"].eq("rcard")]["minute"]) if m is not None]

        entry = 0.0 if started else (_minute(appearance["minute_in"]) or 0.0)
        exit_minute = _minute(appearance["minute_out"])
        if exit_minute is None and red_minutes:
            exit_minute = min(red_minutes)
        until = exit_minute if exit_minute is not None else float("inf")  # no substitution: stoppage time included
        left_at = exit_minute if exit_minute is not None else float(MATCH_MINUTES)
        minutes_played = max(left_at - entry, 0.0)
        if minutes_played <= 0:
            continue

        def score_at(limit: float) -> tuple[int, int]:
            return (sum(1 for t, m in goals if t <= limit and m), sum(1 for t, m in goals if t <= limit and not m))

        r["pj"] += 1
        r["min"] += minutes_played
        gf = sum(1 for t, m in goals if entry < t <= until and m)
        gc = sum(1 for t, m in goals if entry < t <= until and not m)
        r["gf"] += gf
        r["gc"] += gc

        on_entry = score_at(entry)
        on_exit = score_at(exit_minute) if exit_minute is not None else (team_for, team_against)
        points_exit, points_entry = _points(*on_exit), _points(*on_entry)
        r["pts_exit"] += points_exit
        r["pts_gained"] += points_exit - points_entry

        if minutes_played >= 60:
            r["cs_eligible"] += 1
            r["clean_sheets"] += int(gc == 0)

        # minutes according to the scoreboard: segments between goals while he is on the pitch
        cursor, (ahead, behind) = entry, on_entry
        for t, scored in goals:
            if t <= entry or t > left_at:
                continue
            key = "win" if ahead > behind else "draw" if ahead == behind else "loss"
            state[key] += t - cursor
            ahead, behind = (ahead + 1, behind) if scored else (ahead, behind + 1)
            cursor = t
        key = "win" if ahead > behind else "draw" if ahead == behind else "loss"
        state[key] += max(left_at - cursor, 0.0)

        if started:
            r["starts"] += 1
            if exit_minute is not None and not red_minutes:
                r["subbed_off"] += 1
                r["sub_minutes"].append(exit_minute)  # type: ignore[union-attr]
        else:
            bench["n"] += 1
            bench["gf"] += gf
            bench["gc"] += gc
            bench["pts"] += points_exit - points_entry
            bench["min"] += minutes_played

        r["yellow"] += int(own_events["event_type"].eq("ycard").sum())
        r["red"] += int(own_events["event_type"].eq("rcard").sum())
        for red in red_minutes:
            r["gc_after_red"] += sum(1 for t, m in goals if not m and t > red)

    pm = r["gf"] - r["gc"]
    off_min = r["team_min"] - r["min"]
    r["pm"] = pm
    r["off_min"] = off_min
    r["dg_on"] = _per_90(pm, r["min"])
    r["dg_off"] = _per_90((r["team_gf"] - r["gf"]) - (r["team_gc"] - r["gc"]), off_min) if off_min >= min_without(r["team_min"]) else None
    r["onoff"] = r["dg_on"] - r["dg_off"] if r["dg_on"] is not None and r["dg_off"] is not None else None
    r["pts_exit_avg"] = r["pts_exit"] / r["pj"] if r["pj"] else None
    r["pts_gained_avg"] = r["pts_gained"] / r["pj"] if r["pj"] else None
    r["team_ppg"] = r["team_pts"] / r["team_pj"] if r["team_pj"] else None
    r["pct_min"] = r["min"] / r["team_min"] if r["team_min"] else None
    r["sub_minute_avg"] = sum(r["sub_minutes"]) / len(r["sub_minutes"]) if r["sub_minutes"] else None  # type: ignore[arg-type]
    r["cards_90"] = _per_90(r["yellow"] + r["red"], r["min"])
    r["min_with"] = min_with(r["team_min"])
    r["min_without"] = min_without(r["team_min"])
    r["small_sample"] = r["min"] < r["min_with"]
    return r
