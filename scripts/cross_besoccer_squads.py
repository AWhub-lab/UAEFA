"""Build an auditable UAEFA-to-BeSoccer player crosswalk from cached squads.

No web requests are made here. Every accepted link belongs to the same mapped
club and is supported by an exact normalized name or a very high name/dorsal
match. All other proposals remain explicitly marked for review.
"""

from __future__ import annotations

import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import player_crosswalk_candidates
from uaefa_scraper.competitions import COMPETITIONS, get_competition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=sorted(COMPETITIONS), default="first")
    args = parser.parse_args()
    competition = get_competition(args.competition)
    processed = PROJECT_ROOT / "data" / "processed" / competition.directory / "current"
    external = PROJECT_ROOT / "data" / "external" / "besoccer" / competition.directory
    output = external / "player_crosswalk.parquet"

    players = pd.read_parquet(processed / "players.parquet")
    appearances = pd.read_parquet(processed / "appearances.parquet").copy()
    matches = pd.read_parquet(processed / "matches.parquet")
    clubs = pd.read_parquet(processed / "clubs.parquet")
    squads = pd.read_parquet(external / "squads.parquet")

    # A player may be listed more than once over the season. The latest match
    # observation is the best available official club/dorsal association.
    appearances = appearances.merge(matches[["match_id", "match_date"]], on="match_id", how="left")
    appearances["match_date"] = pd.to_datetime(appearances["match_date"], errors="coerce")
    roster = (
        appearances.sort_values(["player_id", "match_date"])
        .drop_duplicates("player_id", keep="last")
        [["player_id", "club_id", "dorsal"]]
    )
    official = (
        players.merge(roster, on="player_id", how="inner")
        .merge(clubs[["club_id", "club_name"]], on="club_id", how="left")
    )

    rows: list[dict] = []
    for club_id, club_official in official.groupby("club_id", dropna=False):
        club_squad = squads[squads["club_id"].astype(str).eq(str(club_id))]
        if club_squad.empty:
            continue
        external_players = club_squad.rename(columns={"besoccer_name": "name"}).to_dict("records")
        candidates = player_crosswalk_candidates(club_official.to_dict("records"), external_players)
        club_name = str(club_official["club_name"].iloc[0])
        for candidate in candidates:
            candidate["club_id"] = str(club_id)
            candidate["club_name"] = club_name
            # Exact normalized names inside the same club are safe; all others
            # still need both strong similarity and an equal shirt number.
            candidate["match_method"] = (
                "exact_name_same_club"
                if candidate["status"] == "accepted" and not candidate["same_dorsal"]
                else "name_and_dorsal_same_club"
                if candidate["status"] == "accepted"
                else "review_required"
            )
            rows.append(candidate)

    crosswalk = pd.DataFrame(rows)
    crosswalk.to_parquet(output, index=False)
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "uaefa_players_with_official_appearance": int(len(official)),
        "besoccer_squad_rows": int(len(squads)),
        "accepted": int(crosswalk["status"].eq("accepted").sum()),
        "review_required": int(crosswalk["status"].eq("review").sum()),
        "requests_made": 0,
    }
    (external / "player_crosswalk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved crosswalk: {output}")


if __name__ == "__main__":
    main()
