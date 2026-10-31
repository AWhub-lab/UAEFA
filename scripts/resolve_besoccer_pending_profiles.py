"""Promote only DOB-confirmed pending BeSoccer candidates into app enrichment."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"


def main() -> None:
    crosswalk = pd.read_parquet(EXTERNAL / "player_crosswalk_validated.parquet")
    original_profiles = pd.read_parquet(EXTERNAL / "player_profiles.parquet")
    candidate_path = EXTERNAL / "pending_candidate_profiles.parquet"
    candidates = pd.read_parquet(candidate_path) if candidate_path.exists() else pd.DataFrame()

    if not candidates.empty:
        review = crosswalk[crosswalk["identity_validation"].eq("review_required")].copy()
        review = review.merge(candidates, on="besoccer_player_id", how="left", suffixes=("", "_profile"))
        # The pre-existing crosswalk already has an empty ``birth_date`` column.
        # Preserve candidate-profile fields explicitly after the merge instead
        # of accidentally comparing that older empty column.
        for column in ("besoccer_name", "birth_date", "source_url"):
            profile_column = f"{column}_profile"
            if profile_column in review.columns:
                review[column] = review[profile_column]
        same_dob = (
            review["birth_date_official"].notna()
            & review["birth_date"].notna()
            & review["birth_date_official"].astype(str).eq(review["birth_date"].astype(str))
        )
        # A shared official birth date is the primary identity key. The small
        # name floor rejects accidentally repeated, unrelated squad candidates.
        safe_pending = same_dob & review["name_score"].ge(0.58)
        promoted_ids = set(review.loc[safe_pending, "uaefa_player_id"].astype(str))
        crosswalk.loc[crosswalk["uaefa_player_id"].astype(str).isin(promoted_ids), "identity_validation"] = "confirmed_name_club_and_dob"
        crosswalk.loc[crosswalk["uaefa_player_id"].astype(str).isin(promoted_ids), "status"] = "accepted"
    else:
        review = pd.DataFrame()
        promoted_ids = set()

    allowed = {"confirmed_name_club_and_dob", "accepted_dob_not_published_by_besoccer"}
    existing_allowed = crosswalk[crosswalk["identity_validation"].isin(allowed)][["uaefa_player_id"]]
    existing = original_profiles.merge(existing_allowed, on="uaefa_player_id", how="inner")

    if promoted_ids:
        promoted = review[review["uaefa_player_id"].astype(str).isin(promoted_ids)].copy()
        promoted["club_id"] = promoted["club_id"].astype(str)
        promoted["uaefa_player_id"] = promoted["uaefa_player_id"].astype(str)
        promoted["uaefa_name"] = promoted["uaefa_name"]
        promoted["matched_by"] = "dob_confirmed_pending_candidate"
        columns = list(original_profiles.columns)
        promoted = promoted.reindex(columns=columns)
        resolved = pd.concat([existing, promoted], ignore_index=True).drop_duplicates("uaefa_player_id", keep="last")
    else:
        resolved = existing

    crosswalk.to_parquet(EXTERNAL / "player_crosswalk_validated.parquet", index=False)
    resolved.to_parquet(EXTERNAL / "player_profiles_validated.parquet", index=False)
    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_profiles_available": int(len(candidates)),
        "newly_promoted_by_dob": int(len(promoted_ids)),
        "total_validated_profiles": int(len(resolved)),
        "profiles_with_elo": int(resolved["elo_current"].notna().sum()),
    }
    (EXTERNAL / "player_profiles_validated_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
