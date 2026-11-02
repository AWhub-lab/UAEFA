"""Promote only DOB-confirmed pending BeSoccer candidates into app enrichment."""

from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from uaefa_scraper.besoccer import normalize_name
from uaefa_scraper.competitions import COMPETITIONS, get_competition


def recover_historical_profiles(
    resolved: pd.DataFrame,
    original_profiles: pd.DataFrame,
    candidates: pd.DataFrame,
    official_root: Path,
) -> tuple[pd.DataFrame, int, int]:
    """Keep historic enrichment only where UAEFA identity evidence is still strong.

    A current BeSoccer roster is not a complete historical roster. A player may
    have appeared earlier in the UAEFA season and subsequently left the club.
    Those profiles remain valid only with an exact DOB plus a strong name
    comparison; mismatching DOBs are deliberately never carried forward.
    """
    official = pd.read_parquet(official_root / "player_profiles_uaefa.parquet")
    official["uaefa_player_id"] = official["player_id"].astype(str)
    official_ids = set(resolved["uaefa_player_id"].astype(str))
    used_candidate_ids = set(resolved["besoccer_player_id"].dropna().astype(str))
    recovered_original: list[pd.DataFrame] = []

    for _, profile in original_profiles.iterrows():
        player_id = str(profile["uaefa_player_id"])
        if player_id in official_ids:
            continue
        match = official[official["uaefa_player_id"].eq(player_id)]
        if match.empty:
            continue
        official_row = match.iloc[0]
        same_dob = (
            pd.notna(profile.get("birth_date"))
            and str(profile["birth_date"]) == str(official_row.get("birth_date_official"))
        )
        exact_name_without_dob = (
            pd.isna(profile.get("birth_date"))
            and normalize_name(str(profile.get("besoccer_name") or ""))
            == normalize_name(str(official_row.get("name_en_official") or ""))
        )
        if same_dob or exact_name_without_dob:
            recovered_original.append(profile.to_frame().T)
            official_ids.add(player_id)

    recovered_candidate: list[dict] = []
    if not candidates.empty:
        candidates = candidates.dropna(subset=["birth_date", "besoccer_name"]).copy()
        candidate_by_dob = candidates.groupby("birth_date")
        for _, official_row in official.iterrows():
            player_id = str(official_row["uaefa_player_id"])
            birth_date = official_row.get("birth_date_official")
            if player_id in official_ids or pd.isna(birth_date) or birth_date not in candidate_by_dob.groups:
                continue
            options = candidate_by_dob.get_group(birth_date).copy()
            options["name_score"] = options["besoccer_name"].map(
                lambda name: SequenceMatcher(
                    None,
                    normalize_name(str(official_row.get("name_en_official") or "")),
                    normalize_name(str(name)),
                ).ratio()
            )
            safe = options[options["name_score"].ge(0.80)]
            # Ambiguous same-DOB records never enter without a club-level link.
            if len(safe) != 1:
                continue
            recovered = safe.iloc[0].to_dict()
            if str(recovered["besoccer_player_id"]) in used_candidate_ids:
                continue
            recovered["uaefa_player_id"] = player_id
            recovered["uaefa_name"] = official_row.get("name_en_official")
            recovered["matched_by"] = "historical_dob_and_strong_name"
            recovered_candidate.append(recovered)
            official_ids.add(player_id)
            used_candidate_ids.add(str(recovered["besoccer_player_id"]))

    additions = [*recovered_original]
    if recovered_candidate:
        additions.append(pd.DataFrame(recovered_candidate).reindex(columns=original_profiles.columns))
    if additions:
        resolved = pd.concat([resolved, *additions], ignore_index=True).drop_duplicates("uaefa_player_id", keep="last")
    return resolved, len(recovered_original), len(recovered_candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", choices=sorted(COMPETITIONS), default="first")
    args = parser.parse_args()
    competition = get_competition(args.competition)
    external = PROJECT_ROOT / "data" / "external" / "besoccer" / competition.directory
    official_root = PROJECT_ROOT / "data" / "processed" / competition.directory / "current"
    crosswalk = pd.read_parquet(external / "player_crosswalk_validated.parquet")
    original_profiles = pd.read_parquet(external / "player_profiles.parquet")
    candidate_path = external / "pending_candidate_profiles.parquet"
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

    # Confirmed candidates stay confirmed across later roster refreshes. Attach
    # their cached public profile again instead of relying on this run's newly
    # promoted IDs, which may legitimately be zero after a resumable rerun.
    confirmed_candidates = pd.DataFrame()
    if not candidates.empty:
        confirmed_candidates = crosswalk[
            crosswalk["identity_validation"].eq("confirmed_name_club_and_dob")
        ].merge(candidates, on="besoccer_player_id", how="inner", suffixes=("", "_profile"))
        if not confirmed_candidates.empty:
            confirmed_candidates["uaefa_player_id"] = confirmed_candidates["uaefa_player_id"].astype(str)
            confirmed_candidates["uaefa_name"] = confirmed_candidates["uaefa_name"]
            confirmed_candidates["matched_by"] = "dob_confirmed_pending_candidate"
            confirmed_candidates = confirmed_candidates.reindex(columns=original_profiles.columns)

    if promoted_ids:
        promoted = review[review["uaefa_player_id"].astype(str).isin(promoted_ids)].copy()
        promoted["club_id"] = promoted["club_id"].astype(str)
        promoted["uaefa_player_id"] = promoted["uaefa_player_id"].astype(str)
        promoted["uaefa_name"] = promoted["uaefa_name"]
        promoted["matched_by"] = "dob_confirmed_pending_candidate"
        columns = list(original_profiles.columns)
        promoted = promoted.reindex(columns=columns)
        resolved = pd.concat([existing, confirmed_candidates, promoted], ignore_index=True).drop_duplicates("uaefa_player_id", keep="last")
    else:
        resolved = pd.concat([existing, confirmed_candidates], ignore_index=True).drop_duplicates("uaefa_player_id", keep="last")

    resolved, recovered_original, recovered_candidate = recover_historical_profiles(
        resolved, original_profiles, candidates, official_root
    )
    crosswalk.to_parquet(external / "player_crosswalk_validated.parquet", index=False)
    resolved.to_parquet(external / "player_profiles_validated.parquet", index=False)
    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_profiles_available": int(len(candidates)),
        "newly_promoted_by_dob": int(len(promoted_ids)),
        "total_validated_profiles": int(len(resolved)),
        "profiles_with_elo": int(resolved["elo_current"].notna().sum()),
        "historical_profiles_recovered": recovered_original + recovered_candidate,
    }
    (external / "player_profiles_validated_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
