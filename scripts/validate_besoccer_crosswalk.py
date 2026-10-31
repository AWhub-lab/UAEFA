"""Validate accepted UAEFA-to-BeSoccer links with official dates of birth.

This script only joins existing local Parquet files. It never makes network
requests and will downgrade a link if both sources publish different DOBs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UAEFA_ROOT = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
BESOCCER_ROOT = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"


def main() -> None:
    crosswalk = pd.read_parquet(BESOCCER_ROOT / "player_crosswalk.parquet")
    uaefa_profiles = pd.read_parquet(UAEFA_ROOT / "player_profiles_uaefa.parquet")
    besoccer_profiles = pd.read_parquet(BESOCCER_ROOT / "player_profiles.parquet")

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

    output = BESOCCER_ROOT / "player_crosswalk_validated.parquet"
    crosswalk.to_parquet(output, index=False)
    print(
        {
            "rows": len(crosswalk),
            "confirmed_name_club_and_dob": int(crosswalk["identity_validation"].eq("confirmed_name_club_and_dob").sum()),
            "accepted_dob_not_published_by_besoccer": int(crosswalk["identity_validation"].eq("accepted_dob_not_published_by_besoccer").sum()),
            "dob_conflicts": int(crosswalk["identity_validation"].eq("do_not_use_dob_conflict").sum()),
            "review_required": int(crosswalk["status"].eq("review").sum()),
            "output": str(output),
        }
    )


if __name__ == "__main__":
    main()
