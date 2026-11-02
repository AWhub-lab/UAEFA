"""Validate accepted UAEFA-to-BeSoccer links with official dates of birth.

This script only joins existing local Parquet files. It never makes network
requests and will downgrade a link if both sources publish different DOBs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.competitions import COMPETITIONS, get_competition


VALIDATED_IDENTITIES = {
    "confirmed_name_club_and_dob",
    "accepted_dob_not_published_by_besoccer",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=sorted(COMPETITIONS), default="first")
    args = parser.parse_args()
    competition = get_competition(args.competition)
    uaefa_root = PROJECT_ROOT / "data" / "processed" / competition.directory / "current"
    besoccer_root = PROJECT_ROOT / "data" / "external" / "besoccer" / competition.directory
    crosswalk = pd.read_parquet(besoccer_root / "player_crosswalk.parquet")
    uaefa_profiles = pd.read_parquet(uaefa_root / "player_profiles_uaefa.parquet")
    besoccer_profiles = pd.read_parquet(besoccer_root / "player_profiles.parquet")

    crosswalk = crosswalk.merge(
        uaefa_profiles[["player_id", "birth_date_official"]],
        left_on="uaefa_player_id", right_on="player_id", how="left",
    ).drop(columns="player_id")
    crosswalk = crosswalk.merge(
        besoccer_profiles[["uaefa_player_id", "birth_date"]], on="uaefa_player_id", how="left"
    )
    accepted = crosswalk["status"].eq("accepted")
    same_dob = accepted & crosswalk["birth_date_official"].notna() & crosswalk["birth_date"].notna() & (
        crosswalk["birth_date_official"].astype(str) == crosswalk["birth_date"].astype(str)
    )
    conflicting_dob = accepted & crosswalk["birth_date_official"].notna() & crosswalk["birth_date"].notna() & ~same_dob

    crosswalk["identity_validation"] = "review_required"
    crosswalk.loc[accepted, "identity_validation"] = "accepted_name_and_club"
    crosswalk.loc[same_dob, "identity_validation"] = "confirmed_name_club_and_dob"
    crosswalk.loc[accepted & crosswalk["birth_date"].isna(), "identity_validation"] = "accepted_dob_not_published_by_besoccer"
    crosswalk.loc[conflicting_dob, "identity_validation"] = "do_not_use_dob_conflict"
    crosswalk.loc[conflicting_dob, "status"] = "review"

    output = besoccer_root / "player_crosswalk_validated.parquet"
    crosswalk.to_parquet(output, index=False)
    validated_ids = set(
        crosswalk.loc[crosswalk["identity_validation"].isin(VALIDATED_IDENTITIES), "uaefa_player_id"].astype(str)
    )
    validated_profiles = besoccer_profiles[
        besoccer_profiles["uaefa_player_id"].astype(str).isin(validated_ids)
    ].copy()
    validated_profiles.to_parquet(besoccer_root / "player_profiles_validated.parquet", index=False)

    careers_path = besoccer_root / "player_career.parquet"
    career_rows = 0
    if careers_path.exists():
        careers = pd.read_parquet(careers_path)
        careers = careers[careers["uaefa_player_id"].astype(str).isin(validated_ids)].copy()
        careers.to_parquet(careers_path, index=False)
        career_rows = len(careers)

    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "validated_profiles": len(validated_profiles),
        "profiles_with_elo": int(validated_profiles["elo_current"].notna().sum()),
        "career_rows": career_rows,
        "dob_conflicts": int(crosswalk["identity_validation"].eq("do_not_use_dob_conflict").sum()),
        "review_required": int(crosswalk["status"].eq("review").sum()),
    }
    (besoccer_root / "player_profiles_validated_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        {
            "rows": len(crosswalk),
            "confirmed_name_club_and_dob": int(crosswalk["identity_validation"].eq("confirmed_name_club_and_dob").sum()),
            "accepted_dob_not_published_by_besoccer": int(crosswalk["identity_validation"].eq("accepted_dob_not_published_by_besoccer").sum()),
            "dob_conflicts": int(crosswalk["identity_validation"].eq("do_not_use_dob_conflict").sum()),
            "review_required": int(crosswalk["status"].eq("review").sum()),
            "validated_profiles": len(validated_profiles),
            "output": str(output),
        }
    )


if __name__ == "__main__":
    main()
