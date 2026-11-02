"""Single source of truth for supported UAEFA competition snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Competition:
    key: str
    uaefa_id: str
    name: str
    directory: str
    logo_filename: str
    season: str = "2026/27"
    report_filename: str | None = None

    @property
    def report_path(self) -> str:
        return self.report_filename or f"{self.directory}_category_board_report_en.pdf"


COMPETITIONS: dict[str, Competition] = {
    "first": Competition(
        key="first",
        uaefa_id="2572",
        name="UAE First Division",
        directory="first_division_2026_2027",
        logo_filename="first_division_league.png",
        report_filename="uae_first_division_category_board_report_en.pdf",
    ),
    "second": Competition(
        key="second",
        uaefa_id="2573",
        name="Second Division League",
        directory="second_division_2026_2027",
        logo_filename="second_division_league.png",
    ),
    "third": Competition(
        key="third",
        uaefa_id="2574",
        name="Third Division League",
        directory="third_division_2026_2027",
        logo_filename="third_division_league.png",
    ),
    "u23": Competition(
        key="u23",
        uaefa_id="2578",
        name="Pro League U23",
        directory="pro_league_u23_2026_2027",
        logo_filename="pro_league_u23.png",
    ),
}


def get_competition(key: str) -> Competition:
    """Return a configured competition or fail with an actionable error."""
    try:
        return COMPETITIONS[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported competition: {key}") from exc
