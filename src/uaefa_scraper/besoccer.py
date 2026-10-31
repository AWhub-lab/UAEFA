"""Small, cache-first BeSoccer reader for the UAEFA enrichment layer.

UAEFA remains the official source for identities, match records and events.
This module only collects public external enrichment and stops on any sign that
the source is limiting access.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from lxml import html


BASE_URL = "https://www.besoccer.com"
STOP_STATUS_CODES = {403, 406, 429}
PLAYER_URL_RE = re.compile(r"/player/([^/?#]+)-(\d+)/?$")


class AccessLimitedError(RuntimeError):
    """The source has blocked or limited access; do not retry automatically."""


def _text(nodes: list[Any]) -> str | None:
    value = " ".join(" ".join(node.itertext()) for node in nodes)
    value = " ".join(value.split()).strip()
    return value or None


def _first_number(value: str | None) -> int | None:
    found = re.search(r"\d+", value or "")
    return int(found.group()) if found else None


def _chart_history(html_text: str, chart_id: str, value_key: str) -> list[dict[str, int]]:
    """Extract the public annual values embedded in a BeSoccer chart script."""
    start = html_text.find(f"graphChart('{chart_id}'")
    end = html_text.find("</script>", start)
    section = html_text[start:end] if start >= 0 and end >= 0 else ""
    values_by_year: dict[int, int] = {}
    for positions, values in re.findall(
        r"graph\.areaspline\(\{.*?position:\s*\[([^]]+)\].*?data:\s*\[([^]]+)\]",
        section,
        flags=re.DOTALL,
    ):
        years = [int(value) for value in re.findall(r"\d{4}", positions)]
        amounts = [int(value) for value in re.findall(r"\d+", values)]
        values_by_year.update(zip(years, amounts))
    return [{"year": year, value_key: value} for year, value in sorted(values_by_year.items())]


@dataclass
class BeSoccerClient:
    """Sequential public-page reader with disk cache and long, random pauses."""

    cache_dir: Path
    min_delay: float = 8.0
    max_delay: float = 12.0
    timeout: float = 25.0

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "UAEFA-Research/0.1 (cached public-data research)",
                "Accept-Language": "en-US,en;q=0.8",
            }
        )
        self.request_count = 0

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        host = urlparse(url).netloc.replace(":", "_")
        return self.cache_dir / f"{host}_{digest}.json"

    def get_html(self, url: str, refresh: bool = False) -> str:
        """Read cached content or make one polite request; never bypass a block."""
        cache_path = self._cache_path(url)
        if cache_path.exists() and not refresh:
            return json.loads(cache_path.read_text(encoding="utf-8"))["html"]

        if self.request_count:
            time.sleep(random.uniform(self.min_delay, self.max_delay))
        response = self.session.get(url, timeout=self.timeout)
        self.request_count += 1
        if response.status_code in STOP_STATUS_CODES:
            raise AccessLimitedError(
                f"BeSoccer returned {response.status_code}; the run was stopped without retries."
            )
        response.raise_for_status()
        if "html" not in response.headers.get("content-type", "").lower() or len(response.content) < 10_000:
            raise AccessLimitedError("Unexpected public-page response; the run was stopped.")
        cache_path.write_text(
            json.dumps(
                {"url": url, "status_code": response.status_code, "html": response.text},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return response.text


def parse_squad(html_text: str, squad_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract a team header and public squad links without requesting player profiles."""
    tree = html.fromstring(html_text)
    title = _text(tree.xpath("//h1"))
    elo_text = _text(tree.xpath('//*[contains(@class, "head-info")]//*[contains(@class, "elo")]'))
    team = {
        "name": title,
        "source_url": squad_url,
        "elo_current": _first_number(elo_text),
    }

    players: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    # Only roster rows count. The page also contains global "most wanted"
    # player links, which must never become false squad members.
    for row in tree.xpath('//tr[contains(concat(" ", normalize-space(@class), " "), " row-body ")]'):
        links = row.xpath('.//a[@data-cy="player" and contains(@href, "/player/")]')
        if not links:
            continue
        link = links[0]
        href = urljoin(BASE_URL, link.get("href", "")).split("?", 1)[0].rstrip("/")
        found = PLAYER_URL_RE.search(urlparse(href).path)
        if not found:
            continue
        slug, player_id_raw = found.groups()
        player_id = int(player_id_raw)
        if player_id in seen_ids:
            continue
        seen_ids.add(player_id)
        row_text = _text([row])
        number_node = row.xpath('.//td[contains(@class, "number-box")]')
        image = row.xpath('.//td[contains(@class, "player-img")]//img/@src')
        name_node = row.xpath('.//td[contains(@class, "name")]//a[@data-cy="player"][1]')
        players.append(
            {
                "besoccer_player_id": player_id,
                "besoccer_slug": slug,
                "name": _text(name_node) or _text([link]),
                "squad_number": _first_number(_text(number_node)),
                "photo_url": image[0] if image else None,
                "source_url": href,
                "source_row": row_text,
            }
        )
    return team, players


def parse_competition_teams(html_text: str) -> list[dict[str, str]]:
    """Extract public team links from a competition page, with navigation links excluded."""
    tree = html.fromstring(html_text)
    teams: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in tree.xpath('//a[contains(@href, "/team/")]'):
        href = urljoin(BASE_URL, link.get("href", "")).split("?", 1)[0].rstrip("/")
        path = urlparse(href).path
        if not path.startswith("/team/"):
            continue
        slug = path.removeprefix("/team/").split("/", 1)[0]
        name = _text([link])
        if not slug or not name or slug in seen:
            continue
        # A real club entry includes a shield image or appears in the table/list.
        row = link.xpath("ancestor::tr[1] | ancestor::li[1] | ancestor::article[1]")
        if not row and not link.xpath(".//img"):
            continue
        seen.add(slug)
        teams.append({"name": name, "slug": slug, "source_url": href})
    return teams


def parse_player_profile(html_text: str, player_url: str) -> dict[str, Any]:
    """Read public profile fields when a later, explicitly requested profile pass runs."""
    tree = html.fromstring(html_text)
    person: dict[str, Any] = {}
    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "Person":
                person = item
                break
        if person:
            break
    found = PLAYER_URL_RE.search(urlparse(player_url).path)
    player_id = int(found.group(2)) if found else None
    nationality = person.get("nationality")
    if isinstance(nationality, dict):
        nationality = nationality.get("name")
    birthplace = person.get("birthPlace")
    if isinstance(birthplace, dict):
        birthplace = birthplace.get("name")
    main_position = _text(
        tree.xpath('//div[contains(@class, "role-positions")]//div[contains(@class, "main-role")]/span[1]')
    )
    other_positions = [
        value for value in (
            _text([node])
            for node in tree.xpath('//div[contains(@class, "role-positions")]//ul[contains(@class, "position-list")]/li/span[1]')
        ) if value
    ]

    # Both public charts are rendered client-side, but their annual values are
    # embedded in the source page and can therefore be retained verbatim.
    elo_history = _chart_history(html_text, "player-rating", "elo")
    market_history = _chart_history(html_text, "player-market", "value_eur")
    elo_text = _text(tree.xpath('//*[contains(@class, "head-info")]//*[contains(@class, "elo")]'))

    career: list[dict[str, Any]] = []
    panels = tree.xpath(
        '//h3[normalize-space()="Historical performance at clubs"]'
        '/ancestor::div[contains(concat(" ", normalize-space(@class), " "), " panel ")][1]'
    )
    if panels:
        for row in panels[0].xpath('.//tr[contains(concat(" ", normalize-space(@class), " "), " row-body ")]'):
            team_link = row.xpath('.//a[@data-cy="historicalTeamTray"][1]')
            cells = [_text([cell]) for cell in row.xpath('./td')]
            if not team_link or len(cells) < 7:
                continue
            career.append(
                {
                    "club_name": _text(team_link),
                    "club_url": urljoin(BASE_URL, team_link[0].get("href", "")),
                    "seasons": _first_number(cells[1]),
                    "matches": _first_number(cells[2]),
                    "starts": _first_number(cells[3]),
                    "minutes": _first_number(cells[4]),
                    "goals": _first_number(cells[5]),
                    "cards": _first_number(cells[6]),
                }
            )

    return {
        "besoccer_player_id": player_id,
        "besoccer_slug": found.group(1) if found else None,
        "name": person.get("name"),
        "birth_date": person.get("birthDate"),
        "nationality": nationality,
        "birth_place": birthplace,
        "height": person.get("height"),
        "weight": person.get("weight"),
        "job_title": person.get("jobTitle"),
        "main_position": main_position,
        "other_positions": other_positions,
        "elo_current": _first_number(elo_text) or (elo_history[-1]["elo"] if elo_history else None),
        "elo_history": elo_history,
        "market_value_current_eur": market_history[-1]["value_eur"] if market_history else None,
        "market_value_history": market_history,
        "career": career,
        "source_url": player_url,
    }


def normalize_name(value: str | None) -> str:
    """Comparable Latin-script name key; original names always remain untouched."""
    text = "".join(
        char for char in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(char) != "Mn"
    ).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def team_crosswalk_candidates(
    uaefa_teams: list[dict[str, Any]], besoccer_teams: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Produce visible team-mapping proposals; uncertain aliases require review."""
    proposals = []
    for official in uaefa_teams:
        name = str(official["club_name"])
        ranked = sorted(
            (
                (
                    SequenceMatcher(None, normalize_name(name), normalize_name(external["name"])).ratio(),
                    external,
                )
                for external in besoccer_teams
            ),
            key=lambda item: item[0],
        )
        if not ranked:
            continue
        score, external = ranked[-1]
        proposals.append(
            {
                "uaefa_club_id": str(official["club_id"]),
                "uaefa_name": name,
                "besoccer_slug": external["slug"],
                "besoccer_name": external["name"],
                "name_score": round(score, 3),
                "status": "accepted" if score >= 0.92 else "review",
                "besoccer_url": external["source_url"],
            }
        )
    return sorted(proposals, key=lambda item: (item["status"] != "accepted", -item["name_score"]))


def player_crosswalk_candidates(
    uaefa_players: list[dict[str, Any]], besoccer_players: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Propose, but never silently accept, player identity links for review."""
    proposals: list[dict[str, Any]] = []
    for uaefa in uaefa_players:
        official_name = str(uaefa.get("name_en") or uaefa.get("shortname_en") or "")
        best: tuple[float, dict[str, Any], bool] | None = None
        for external in besoccer_players:
            score = SequenceMatcher(
                None, normalize_name(official_name), normalize_name(str(external.get("name") or ""))
            ).ratio()
            same_dorsal = bool(
                uaefa.get("dorsal") is not None
                and external.get("squad_number") is not None
                and str(uaefa["dorsal"]) == str(external["squad_number"])
            )
            if same_dorsal:
                score = min(1.0, score + 0.12)
            if best is None or score > best[0]:
                best = (score, external, same_dorsal)
        if best is None:
            continue
        score, external, same_dorsal = best
        exact_name = normalize_name(official_name) == normalize_name(str(external.get("name") or ""))
        accepted = exact_name or (score >= 0.92 and same_dorsal)
        proposals.append(
            {
                "uaefa_player_id": str(uaefa.get("player_id")),
                "uaefa_name": official_name,
                "uaefa_dorsal": uaefa.get("dorsal"),
                "besoccer_player_id": external["besoccer_player_id"],
                "besoccer_name": external.get("name"),
                "besoccer_dorsal": external.get("squad_number"),
                "name_score": round(score, 3),
                "same_dorsal": same_dorsal,
                "status": "accepted" if accepted else "review",
                "besoccer_url": external.get("source_url"),
            }
        )
    return sorted(proposals, key=lambda item: (item["status"] != "accepted", -item["name_score"]))
