"""Al Wasl Football Intelligence | UAE First Division Hub (local Streamlit viewer)."""

from __future__ import annotations

import base64
import io
import json
import os
import re
from functools import lru_cache
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitSecretNotFoundError

from impact import player_impact
from src.uaefa_scraper.drive_sync import DriveSyncError, settings_from_mapping, sync_runtime_snapshot


PROJECT_ROOT = Path(__file__).resolve().parent
SEASON_DATA_ROOT = PROJECT_ROOT / "data" / "processed" / "first_division_2026_2027"


def drive_settings():
    """Read optional deployment secrets without exposing them in the UI or Git."""
    try:
        if "drive" in st.secrets:
            return settings_from_mapping(dict(st.secrets["drive"]))
    except StreamlitSecretNotFoundError:
        # A local installation deliberately has no secrets file until Drive is enabled.
        pass
    return settings_from_mapping()


def local_snapshot_available() -> bool:
    required = ["matches", "clubs", "players", "appearances", "events", "staff"]
    current = SEASON_DATA_ROOT / "current"
    return all((current / f"{name}.parquet").exists() for name in required)


def ensure_runtime_snapshot(force: bool = False) -> dict[str, object] | None:
    """Bootstrap a deployed app from Drive, while keeping local use offline-first."""
    settings = drive_settings()
    if not settings or (local_snapshot_available() and not force):
        return None
    return sync_runtime_snapshot(PROJECT_ROOT, settings)


# Git deliberately excludes data. A hosted app receives its approved snapshot
# from Drive on first start; local work remains fully usable without Drive.
try:
    ensure_runtime_snapshot()
except DriveSyncError:
    # The regular missing-data message remains useful in a new local checkout.
    pass

# ``current`` is rebuilt by the incremental synchroniser. Keep the pilot as a
# fallback so the viewer remains usable before the first full synchronisation.
DATA_ROOT = SEASON_DATA_ROOT / "current" if (SEASON_DATA_ROOT / "current").exists() else SEASON_DATA_ROOT / "week_01"
EXTERNAL_ROOT = PROJECT_ROOT / "data" / "external" / "besoccer" / "first_division_2026_2027"
BRAND_ROOT = PROJECT_ROOT / "data" / "assets" / "brand"

SEASON = "2026/27"
PAGES = {
    "Clasificación": ("01", ":material/leaderboard:", "Clasificación y goleadores de la jornada"),
    "Partidos": ("02", ":material/stadium:", "Actas, alineaciones y cronología de cada partido"),
    "Equipos": ("03", ":material/shield:", "Club por club: plantilla vista y cuerpo técnico"),
    "Jugadores": ("04", ":material/person:", "Catálogo y ficha individual de cada jugador"),
}
TRANSLATIONS = {
    "Clasificación": "Standings", "Partidos": "Matches", "Equipos": "Teams", "Jugadores": "Players",
    "Clasificación y goleadores de la jornada": "Standings and matchday scorers",
    "Actas, alineaciones y cronología de cada partido": "Match reports, lineups and event timeline",
    "Club por club: plantilla vista y cuerpo técnico": "Club-by-club: squad overview and coaching staff",
    "Catálogo y ficha individual de cada jugador": "Player catalogue and individual profile",
    "Jornada": "Matchday", "Todas las jornadas": "All matchdays", "Temporada": "Season",
    "Rankings": "Rankings", "Más minutos": "Most minutes", "Más jóvenes": "Youngest", "Amarillas": "Yellow cards", "Rojas": "Red cards",
    "Goles": "Goals", "Minutos": "Minutes", "Nacimiento": "Birth year", "Posición": "Position",
    "Goles a favor": "Goals for", "Goles en contra": "Goals against", "Diferencia": "Goal difference",
    "Diferencia jornada": "Matchday difference", "Diferencia acumulada": "Cumulative difference",
    "Clasificación provisional": "Provisional standings", "Acumulada hasta": "Accumulated through",
    "Ritmo de gol": "Goal rhythm", "Eventos y marcadores oficiales UAEFA": "Official UAEFA events and scores",
    "Alineaciones": "Lineups", "Once inicial sobre el campo y banquillo": "Starting XI on the pitch and substitutes",
    "Cuerpo técnico": "Coaching staff", "Staff registrado en el acta": "Staff listed in the match report",
    "Participación": "Appearances", "Partidos disputados": "Matches played",
    "Enriquecimiento validado": "Validated enrichment", "Evolución de Elo": "Elo progression",
    "Evolución de valor de mercado": "Market value progression", "Valor de mercado": "Market value",
    "Filtros de búsqueda": "Search filters", "Comparador de jugadores": "Player comparator",
    "Jugadores identificados": "Identified players", "Abrir ficha de jugador": "Open player profile",
    "Busca directamente un jugador para consultar su perfil completo.": "Search directly for a player to view the full profile.",
    "Buscar jugador": "Search player", "Nombre o apellidos": "First name or surname", "Rango de edad": "Age range",
    "Rango de año de nacimiento": "Birth-year range", "Filtros vinculados": "Linked filters",
    "El último filtro ajustado define la selección exacta; el otro se actualiza automáticamente.": "The last filter adjusted defines the exact selection; the other updates automatically.",
    "Minutos mínimos": "Minimum minutes", "Selecciona un jugador...": "Select a player...",
    "Todas": "All", "Todos": "All", "Sin dato": "No data", "Sin eventos registrados.": "No events recorded.",
    "Sin participaciones registradas.": "No appearances recorded.", "No hay registros suficientes para este ranking en el periodo seleccionado.": "There are not enough records for this ranking in the selected period.",
    "No hay jugadores que cumplan los filtros seleccionados.": "No players match the selected filters.",
    "No hay jugadores con valores positivos y publicados para la combinación de métricas elegida.": "No players have published positive values for the selected metric combination.",
    "Ver ficha": "View profile", "Ver ficha del jugador": "View player profile", "Ver club": "View team", "Abierto": "Open",
    "Abrir acta": "Open match report", "Acta abierta": "Match report open", "← Volver": "← Back",
    "Actualizar datos": "Refresh data", "Jornada de corte": "Matchday cut-off", "Vista activa": "Active view",
    "Datos locales en Parquet · actualización incremental disponible.": "Local Parquet data · incremental update available.",
    "Fuente: UAEFA public API": "Source: UAEFA public API", "Dorsal": "Squad number",
    "Partidos titular": "Matches started", "Partidos jugados": "Matches played", "Minutos jugados": "Minutes played",
    "Convocatorias": "Squad selections", "Titularidades": "Starts", "Tarjetas amarillas": "Yellow cards", "Tarjetas rojas": "Red cards", "Cambios": "Substitutions",
    "Año": "Year", "Club": "Club", "Acumulada": "Cumulative", "Tramo": "Interval",
    "Comparar equipos": "Compare teams", "Máximo cinco equipos para mantener el gráfico legible.": "Maximum five teams to keep the chart readable.",
    "La evolución de posiciones aparecerá cuando haya al menos dos jornadas disputadas.": "Position progression will appear once at least two matchdays have been played.",
    "Selecciona entre uno y cinco equipos para comparar su posición.": "Select between one and five teams to compare their position.",
    "Acciones": "Actions", "Disponibilidad, producción y disciplina oficial UAEFA": "Official UAEFA availability, output and discipline",
    "Solo jugadores con minutos": "Only players with minutes", "DISPONIBILIDAD": "AVAILABILITY", "Estatus": "Status",
    "Eje X": "X axis", "Eje Y": "Y axis", "Posiciones en el gráfico": "Positions in chart", "Excluir 0 y sin dato": "Exclude 0 and missing values",
    "Porteros": "Goalkeepers", "Defensas": "Defenders", "Mediocampistas": "Midfielders", "Atacantes": "Attackers",
    "Mostrar más": "Show more", "restantes": "remaining", "Catálogo": "Catalogue", "Titular": "Starter",
    "Elo del jugador": "Player Elo", "Elo del equipo": "Team Elo", "Rendimiento de la plantilla en el periodo seleccionado": "Squad performance in the selected period",
    "Plantilla vista": "Squad overview", "jugadores en acta": "players in match reports", "por posición y minutos": "by position and minutes",
    "Banquillo registrado en el acta": "Bench staff listed in the match report", "Ficha del club": "Team profile",
    "Resultados y acceso a cada acta": "Results and access to each match report", "Cronología": "Timeline",
    "Eventos oficiales del acta": "Official match-report events", "Asistencia": "Attendance", "Fecha": "Date", "Partido": "Match",
    "Sede": "Venue", "Min.": "Min.", "Acción": "Action", "Relación": "Related player", "Entra": "On", "Sale": "Off",
    "Local": "Home", "Visitante": "Away", "Eventos": "Events", "Minuto": "Minute", "Cambios": "Substitutions",
    "GOLES POR TRAMOS DE 15' · LOCAL Y VISITANTE": "GOALS BY 15-MINUTE INTERVAL · HOME AND AWAY",
    "TARJETAS AMARILLAS POR TRAMOS DE 15' · LOCAL Y VISITANTE": "YELLOW CARDS BY 15-MINUTE INTERVAL · HOME AND AWAY",
    "TARJETAS ROJAS POR TRAMOS DE 15' · LOCAL Y VISITANTE": "RED CARDS BY 15-MINUTE INTERVAL · HOME AND AWAY",
    "MINUTOS DE ENTRADA Y SALIDA": "SUBSTITUTION MINUTES",
    "GOLES POR TRAMOS DE 15' · A FAVOR ARRIBA / EN CONTRA ABAJO": "GOALS BY 15-MINUTE INTERVAL · FOR ABOVE / AGAINST BELOW",
    "DIFERENCIA POR JORNADA Y ACUMULADA": "MATCHDAY AND CUMULATIVE GOAL DIFFERENCE",
    "Para ver la evolución entre jornadas, selecciona «Todas las jornadas» en el selector superior.": "To view matchday progression, select ‘All matchdays’ in the top selector.",
    "Nacimiento / edad": "Birth year / age", "Edad": "Age", "Categoría UAEFA": "UAEFA category",
    "Edad: no publicada todavía": "Age: not published yet", "EXPLORADOR DE PLANTILLAS": "SQUAD EXPLORER",
    "Filtra y combina criterios sin perder contexto": "Filter and combine criteria without losing context",
    "Todas las posiciones": "All positions", "Portero": "Goalkeeper", "Defensa": "Defender", "Mediocampista": "Midfielder", "Atacante": "Attacker",
    "Glosario · cómo leer una tarjeta de jugador": "Glossary · how to read a player card",
    "El ejemplo aparecerá al obtener al menos un jugador con los filtros aplicados.": "An example will appear once at least one player matches the selected filters.",
    "ANÁLISIS MULTIVARIABLE": "MULTIVARIATE ANALYSIS", "Explora perfiles y cuadrantes de rendimiento": "Explore player profiles and performance quadrants",
    "Selecciona las variables de cada eje. Elo y valor solo aparecen si el dato externo está publicado y validado": "Choose the variable for each axis. Elo and market value appear only when external data is published and validated.",
    "Se ocultan los ceros y datos sin publicar.": "Zeros and unpublished data are hidden.",
    "Se muestran los ceros; solo se omiten coordenadas no publicadas.": "Zeros are shown; only unpublished coordinates are omitted.",
    "Medias del gráfico": "Chart averages", "jugadores visibles": "visible players", "resultados": "results", "goleadores primero": "top scorers first",
    "Sin cambios que involucren al jugador en el periodo seleccionado.": "No substitutions involving this player in the selected period.",
    "Matriz de cambios": "Substitution matrix", "Entrada o salida y jugador relacionado": "On/off action and related player",
    "Convocado": "Selected", "de convocatorias": "of selections", "del total de liga": "of league total", "partidos de liga": "league matches",
    "No jugó": "Did not play", "Suplente": "Substitute", "Volver a": "Back to",
    "Datos externos · identidad confirmada con UAEFA": "External data · identity confirmed with UAEFA",
    "Datos externos · histórico publicado": "External data · published history", "Datos externos · histórico publicado del jugador": "External data · published player history",
    "Euros": "Euros", "Valor": "Value", "Idioma": "Language", "Navegación": "Navigation",
    "Sección": "Section", "años": "years", "Media por partido": "Average per match",
    "Puntos": "Points", "Goles a favor / en contra": "Goals for / against",
    "Rendimiento individual · foto, club, posición, nacimiento y métrica oficial UAEFA": "Individual performance · photo, club, position, birth year and official UAEFA metric",
    "Top 5 de la jornada por defecto · compara hasta cinco equipos": "Current matchday top 5 by default · compare up to five teams",
    "Evolución de posiciones": "Position progression", "Elige un club para abrir su ficha": "Choose a club to open its profile",
    "Combina perfil, club y rendimiento para localizar jugadores concretos": "Combine profile, club and performance to locate specific players",
    "resultados · goleadores primero": "results · top scorers first", "Diferencia por jornada": "Matchday goal difference",
}
POSITIONS = {
    "GK": ("Goalkeeper", "#f5a524"),
    "D": ("Defense", "#4c9aff"),
    "M": ("Midfielder", "#2fd27a"),
    "A": ("Attacker", "#ff5c6c"),
}
POSITION_LINES = ["A", "M", "D", "GK"]  # top of the pitch to the goalkeeper
GRID_PAGE = 24


def is_english() -> bool:
    return st.session_state.get("language", "English") == "English"


def t(value: str) -> str:
    """Translate fixed UI copy while retaining official player and club data verbatim."""
    return TRANSLATIONS.get(value, value) if is_english() else value


def translate_markup(markup: str) -> str:
    if not is_english():
        return markup
    for source, target in sorted(TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        markup = markup.replace(source, target)
    return markup

st.set_page_config(
    page_title="Al Wasl | UAE First Division Hub",
    page_icon=str(BRAND_ROOT / "al_wasl.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)


# --------------------------------------------------------------------------- data
def asset_path(relative_path: object) -> Path | None:
    if relative_path is None or pd.isna(relative_path):
        return None
    path = PROJECT_ROOT / str(relative_path)
    return path if path.exists() else None


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    required = ["matches", "clubs", "players", "appearances", "events", "staff"]
    missing = [name for name in required if not (DATA_ROOT / f"{name}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"Faltan tablas Parquet: {', '.join(missing)}")
    frames = {name: pd.read_parquet(DATA_ROOT / f"{name}.parquet").copy() for name in required}
    frames["matches"]["match_id"] = frames["matches"]["match_id"].astype(str)
    frames["clubs"]["club_id"] = frames["clubs"]["club_id"].astype(str)
    frames["players"]["player_id"] = frames["players"]["player_id"].astype(str)
    for name in ("appearances", "events", "staff"):
        frames[name]["match_id"] = frames[name]["match_id"].astype(str)
    frames["appearances"]["club_id"] = frames["appearances"]["club_id"].astype(str)
    frames["appearances"]["player_id"] = frames["appearances"]["player_id"].astype(str)
    frames["events"]["club_id"] = frames["events"]["club_id"].astype("string")
    frames["events"]["player_id"] = frames["events"]["player_id"].astype("string")
    frames["events"]["in_player_id"] = frames["events"]["in_player_id"].astype("string")
    frames["staff"]["club_id"] = frames["staff"]["club_id"].astype(str)

    # UAEFA leaves minute_out empty for sent-off players: close their appearance at the red-card minute.
    reds = frames["events"][frames["events"]["event_type"].eq("rcard")].dropna(subset=["player_id", "minute"])
    red_exit = {(str(m), str(p)): minute for m, p, minute in zip(reds["match_id"], reds["player_id"], reds["minute"])}
    red_minute = pd.Series(
        [red_exit.get(key) for key in zip(frames["appearances"]["match_id"], frames["appearances"]["player_id"])],
        index=frames["appearances"].index,
    )
    frames["appearances"]["minute_out"] = frames["appearances"]["minute_out"].fillna(red_minute)

    # UAEFA profiles are the identity source. BeSoccer values are joined only
    # when the local crosswalk has confirmed the player identity with DOB.
    uaefa_profiles_path = DATA_ROOT / "player_profiles_uaefa.parquet"
    if uaefa_profiles_path.exists():
        profiles = pd.read_parquet(uaefa_profiles_path).copy()
        profiles["player_id"] = profiles["player_id"].astype(str)
        frames["players"] = frames["players"].merge(profiles, on="player_id", how="left")

    crosswalk_path = EXTERNAL_ROOT / "player_crosswalk_validated.parquet"
    validated_profiles_path = EXTERNAL_ROOT / "player_profiles_validated.parquet"
    besoccer_profiles_path = (
        validated_profiles_path if validated_profiles_path.exists()
        else EXTERNAL_ROOT / "player_profiles.parquet"
    )
    if validated_profiles_path.exists():
        # This file has already passed the UAEFA identity checks. It can retain
        # verified historic players even after they leave a current squad page.
        enrichment = pd.read_parquet(validated_profiles_path).copy()
        enrichment["player_id"] = enrichment["uaefa_player_id"].astype(str)
        enrichment = enrichment[
            [
                "player_id", "market_value_current_eur", "market_value_history_json",
                "elo_current", "elo_history_json", "position_main", "positions_secondary_json",
            ]
        ]
        frames["players"] = frames["players"].merge(enrichment, on="player_id", how="left")
    elif crosswalk_path.exists() and besoccer_profiles_path.exists():
        # Legacy fallback for a local dataset created before the validated file.
        crosswalk = pd.read_parquet(crosswalk_path)
        approved = crosswalk[
            crosswalk["identity_validation"].isin(
                ["confirmed_name_club_and_dob", "accepted_dob_not_published_by_besoccer"]
            )
        ][["uaefa_player_id"]].drop_duplicates()
        approved["uaefa_player_id"] = approved["uaefa_player_id"].astype(str)
        besoccer_profiles = pd.read_parquet(besoccer_profiles_path).copy()
        besoccer_profiles["uaefa_player_id"] = besoccer_profiles["uaefa_player_id"].astype(str)
        enrichment = approved.merge(besoccer_profiles, on="uaefa_player_id", how="inner")
        enrichment = enrichment.rename(columns={"uaefa_player_id": "player_id"})[
            [
                "player_id", "market_value_current_eur", "market_value_history_json",
                "elo_current", "elo_history_json", "position_main", "positions_secondary_json",
            ]
        ]
        frames["players"] = frames["players"].merge(enrichment, on="player_id", how="left")

    teams_path = EXTERNAL_ROOT / "teams.parquet"
    if teams_path.exists():
        team_elo = pd.read_parquet(teams_path)[["club_id", "elo_current"]].drop_duplicates("club_id")
        team_elo["club_id"] = team_elo["club_id"].astype(str)
        frames["clubs"] = frames["clubs"].merge(team_elo, on="club_id", how="left")
    return frames


def data_for_week(data: dict[str, pd.DataFrame], week: int | None) -> dict[str, pd.DataFrame]:
    """Return a consistent season slice: every linked table follows the selected matches."""
    if week is None:
        return data
    week_numbers = pd.to_numeric(data["matches"]["week_no"], errors="coerce")
    matches = data["matches"][week_numbers.eq(week)].copy()
    match_ids = set(matches["match_id"])
    appearances = data["appearances"][data["appearances"]["match_id"].isin(match_ids)].copy()
    club_ids = set(matches["home_club_id"]).union(matches["away_club_id"])
    player_ids = set(appearances["player_id"])
    return {
        "matches": matches,
        "clubs": data["clubs"].copy(),
        "players": data["players"][data["players"]["player_id"].isin(player_ids)].copy(),
        "appearances": appearances,
        "events": data["events"][data["events"]["match_id"].isin(match_ids)].copy(),
        "staff": data["staff"][data["staff"]["match_id"].isin(match_ids)].copy(),
    }


def data_through_week(data: dict[str, pd.DataFrame], week: int) -> dict[str, pd.DataFrame]:
    """Return the season state accumulated through the selected matchday."""
    week_numbers = pd.to_numeric(data["matches"]["week_no"], errors="coerce")
    matches = data["matches"][week_numbers.le(week)].copy()
    match_ids = set(matches["match_id"])
    appearances = data["appearances"][data["appearances"]["match_id"].isin(match_ids)].copy()
    club_ids = set(matches["home_club_id"]).union(matches["away_club_id"])
    player_ids = set(appearances["player_id"])
    return {
        "matches": matches,
        "clubs": data["clubs"].copy(),
        "players": data["players"][data["players"]["player_id"].isin(player_ids)].copy(),
        "appearances": appearances,
        "events": data["events"][data["events"]["match_id"].isin(match_ids)].copy(),
        "staff": data["staff"][data["staff"]["match_id"].isin(match_ids)].copy(),
    }


def scope_label() -> str:
    week = st.session_state.get("matchday")
    return f"{t('Jornada')} {week}" if week else t("Jornada")


def build_standings(matches: pd.DataFrame, all_clubs: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for match in matches.itertuples(index=False):
        home_goals, away_goals = int(match.home_score), int(match.away_score)
        for side, goals_for, goals_against in (("home", home_goals, away_goals), ("away", away_goals, home_goals)):
            rows.append(
                {
                    "club_id": str(getattr(match, f"{side}_club_id")),
                    "Club": getattr(match, f"{side}_club_name"),
                    "P": 1,
                    "W": int(goals_for > goals_against),
                    "D": int(goals_for == goals_against),
                    "L": int(goals_for < goals_against),
                    "GF": goals_for,
                    "GA": goals_against,
                    "Pts": 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0,
                }
            )
    if rows:
        table = pd.DataFrame(rows).groupby(["club_id", "Club"], as_index=False).sum(numeric_only=True)
    else:
        table = pd.DataFrame(columns=["club_id", "Club", "P", "W", "D", "L", "GF", "GA", "Pts"])
    if all_clubs is not None:
        known = all_clubs[["club_id", "club_name"]].copy()
        known["club_id"] = known["club_id"].astype(str)
        missing = known[~known["club_id"].isin(table["club_id"].astype(str))].rename(columns={"club_name": "Club"})
        if not missing.empty:
            for column in ["P", "W", "D", "L", "GF", "GA", "Pts"]:
                missing[column] = 0
            table = pd.concat([table, missing[["club_id", "Club", "P", "W", "D", "L", "GF", "GA", "Pts"]]], ignore_index=True)
    if table.empty:
        return pd.DataFrame(columns=["#", "club_id", "Club", "P", "W", "D", "L", "GF", "GA", "Pts", "GD"])
    table["GD"] = table["GF"] - table["GA"]
    table = table.sort_values(["Pts", "GD", "GF", "Club"], ascending=[False, False, False, True]).reset_index(drop=True)
    table.insert(0, "#", table.index + 1)
    return table


def appearance_minutes(appearances: pd.DataFrame) -> pd.Series:
    """Minutes on the pitch: starters until their substitution (or 90), substitutes from their entry."""
    minute_in = to_number(appearances["minute_in"])
    minute_out = to_number(appearances["minute_out"])
    started = appearances["started"].astype(bool)
    played = appearances["has_played"].astype(bool)
    minutes = pd.Series(0, index=appearances.index, dtype=float)
    minutes[started] = minute_out[started].where(minute_out[started] > 0, 90)
    sub_in = ~started & played
    left_at = minute_out[sub_in].where(minute_out[sub_in] > 0, 90)  # a substitute can also be taken off or sent off
    minutes[sub_in] = (left_at - minute_in[sub_in]).clip(lower=0)
    return minutes


def build_player_totals(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    appearances = data["appearances"].copy()
    appearances["estimated_minutes"] = appearance_minutes(appearances)
    totals = appearances.groupby("player_id", as_index=False).agg(
        Matches=("has_played", "sum"),
        Starts=("started", "sum"),
        Minutes=("estimated_minutes", "sum"),
        Squad=("match_id", "nunique"),
        club_id=("club_id", "first"),
        dorsal=("dorsal", "first"),
    )
    events = data["events"]
    for label, kind in (("Goals", "goal"), ("Yellow", "ycard"), ("Red", "rcard")):
        counts = events[events["event_type"].eq(kind)].groupby("player_id").size().rename(label)
        totals = totals.merge(counts, left_on="player_id", right_index=True, how="left")
    totals[["Goals", "Yellow", "Red"]] = totals[["Goals", "Yellow", "Red"]].fillna(0).astype(int)
    merged = data["players"].merge(totals, on="player_id", how="left")
    merged = merged.fillna({"Matches": 0, "Starts": 0, "Minutes": 0, "Squad": 0})
    club_names = data["clubs"].set_index("club_id")["club_name"]
    merged["club_name"] = merged["club_id"].map(club_names).fillna("-")
    merged["nationality_category"] = merged["nationality_category"].str.strip()
    reference_date = data["matches"]["match_date"].max() if not data["matches"].empty else None
    merged["Edad"] = merged["birth_date_official"].map(lambda value: age_at_date(value, reference_date))
    merged["Nacimiento"] = merged["birth_date_official"].map(lambda value: birth_year_age_label(value, reference_date))
    player_elo = pd.to_numeric(merged.get("elo_current"), errors="coerce")
    merged["elo_percentile"] = player_elo.rank(pct=True)
    return merged


def age_at_date(birth_date: object, reference_date: object) -> int | None:
    """Calculate a player's completed years on the latest visible match date."""
    birth = pd.to_datetime(birth_date, errors="coerce")
    reference = pd.to_datetime(reference_date, errors="coerce")
    if pd.isna(birth) or pd.isna(reference):
        return None
    return int(reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day)))


def birth_year_age_label(birth_date: object, reference_date: object) -> str | None:
    """Show official birth year and age measured at the relevant data cut-off."""
    birth = pd.to_datetime(birth_date, errors="coerce")
    if pd.isna(birth):
        return None
    age = age_at_date(birth, reference_date)
    return f"{birth.year} ({age} {t('años')})" if age is not None else str(birth.year)


def birth_label(value: object, fallback: str = "") -> str:
    """Return a safe display label for a nullable birth-year/age value."""
    return str(value) if value is not None and not pd.isna(value) else fallback


def player_elo_orb(player: pd.Series) -> str:
    """A compact individual-Elo badge, coloured by dynamic percentile bands."""
    value = pd.to_numeric(pd.Series([player.get("elo_current")]), errors="coerce").iloc[0]
    percentile = pd.to_numeric(pd.Series([player.get("elo_percentile")]), errors="coerce").iloc[0]
    if pd.isna(value) or pd.isna(percentile):
        return ""
    bands = [
        (0.20, "#d64558", "tramo bajo"),
        (0.40, "#df7a32", "tramo medio-bajo"),
        (0.60, "#c29400", "tramo medio"),
        (0.80, "#6a9f2f", "tramo medio-alto"),
        (1.00, "#148a54", "tramo alto"),
    ]
    color, label = bands[-1][1:]
    for limit, candidate_color, candidate_label in bands:
        if percentile <= limit:
            color, label = candidate_color, candidate_label
            break
    return f"<span class='elo-player' style='--elo:{color}' title='Elo individual publicado · {label}'>{int(round(value))}</span>"


def team_goal_intervals(data: dict[str, pd.DataFrame], club_id: str) -> pd.DataFrame:
    """Count official goals for and against in six 15-minute match intervals."""
    labels = ["01-15'", "16-30'", "31-45'", "46-60'", "61-75'", "76-90+'"]
    matches = data["matches"]
    club_matches = matches[
        matches["home_club_id"].eq(club_id) | matches["away_club_id"].eq(club_id)
    ]
    goals = data["events"][
        data["events"]["event_type"].eq("goal")
        & data["events"]["match_id"].isin(set(club_matches["match_id"]))
    ].copy()
    goals["minute_num"] = pd.to_numeric(goals["minute"], errors="coerce").fillna(0)
    goals["interval"] = pd.cut(
        goals["minute_num"],
        bins=[0, 15, 30, 45, 60, 75, float("inf")],
        labels=labels,
        include_lowest=True,
    )
    own = goals[goals["club_id"].astype(str).eq(club_id)].groupby("interval", observed=False).size()
    against = goals[~goals["club_id"].astype(str).eq(club_id)].groupby("interval", observed=False).size()
    return pd.DataFrame({
        "Tramo": labels,
        "Goles a favor": [int(own.get(label, 0)) for label in labels],
        "Goles en contra": [int(against.get(label, 0)) for label in labels],
    })


def team_goal_difference(data: dict[str, pd.DataFrame], club_id: str) -> pd.DataFrame:
    """Build weekly goal difference and its running total from official results."""
    rows = []
    for match in data["matches"].itertuples(index=False):
        if str(match.home_club_id) == club_id:
            goals_for, goals_against = int(match.home_score), int(match.away_score)
        elif str(match.away_club_id) == club_id:
            goals_for, goals_against = int(match.away_score), int(match.home_score)
        else:
            continue
        rows.append({"Jornada": int(match.week_no), "Diferencia jornada": goals_for - goals_against})
    weekly = pd.DataFrame(rows)
    if weekly.empty:
        return pd.DataFrame(columns=["Jornada", "Diferencia jornada", "Diferencia acumulada"])
    weekly = weekly.groupby("Jornada", as_index=False)["Diferencia jornada"].sum().sort_values("Jornada")
    weekly["Diferencia acumulada"] = weekly["Diferencia jornada"].cumsum()
    return weekly


INTERVAL_LABELS = ["01-15'", "16-30'", "31-45'", "46-60'", "61-75'", "76-90+'"]


def player_availability(appearances: pd.DataFrame, matches: pd.DataFrame, club_id: str) -> dict[str, int]:
    """Summarise official call-ups and participation within the visible scope."""
    club_matches = matches[
        matches["home_club_id"].astype(str).eq(str(club_id))
        | matches["away_club_id"].astype(str).eq(str(club_id))
    ]
    played = appearances[appearances["has_played"].astype(bool)]
    return {
        "total_matches": int(club_matches["match_id"].nunique()),
        "called": int(appearances["match_id"].nunique()),
        "played": int(played["match_id"].nunique()),
        "starts": int(appearances[appearances["started"].astype(bool)]["match_id"].nunique()),
        "minutes": int(appearance_minutes(appearances).sum()),
    }


def player_event_intervals(events: pd.DataFrame, matches: pd.DataFrame, player_id: str, event_type: str) -> pd.DataFrame:
    """Count one player's official events by 15-minute interval and venue."""
    rows = events[
        events["event_type"].eq(event_type) & events["player_id"].astype(str).eq(str(player_id))
    ].merge(matches[["match_id", "home_club_id"]], on="match_id", how="left")
    if not rows.empty:
        rows = rows.copy()
        rows["minute_num"] = pd.to_numeric(rows["minute"], errors="coerce").fillna(0)
        rows["Tramo"] = pd.cut(
            rows["minute_num"], bins=[0, 15, 30, 45, 60, 75, float("inf")],
            labels=INTERVAL_LABELS, include_lowest=True,
        )
        rows["Condición"] = rows["club_id"].astype(str).eq(rows["home_club_id"].astype(str)).map(
            {True: "Local", False: "Visitante"}
        )
        grouped = rows.groupby(["Tramo", "Condición"], observed=False).size().rename("Eventos")
    else:
        grouped = pd.Series(dtype=int, name="Eventos")
    index = pd.MultiIndex.from_product([INTERVAL_LABELS, ["Local", "Visitante"]], names=["Tramo", "Condición"])
    return grouped.reindex(index, fill_value=0).reset_index()


def player_substitutions(events: pd.DataFrame, matches: pd.DataFrame, player_id: str) -> pd.DataFrame:
    """Return every official substitution involving the player, with both identities intact."""
    substitutions = events[events["event_type"].eq("subs")].copy()
    substitutions = substitutions[
        substitutions["player_id"].astype(str).eq(str(player_id))
        | substitutions["in_player_id"].astype(str).eq(str(player_id))
    ].merge(
        matches[["match_id", "match_date", "home_club_id", "home_club_name", "away_club_id", "away_club_name"]],
        on="match_id", how="left",
    )
    result = []
    for row in substitutions.itertuples(index=False):
        enters = str(row.in_player_id) == str(player_id)
        home = str(row.club_id) == str(row.home_club_id)
        result.append({
            "Fecha": row.match_date,
            "Partido": f"{row.home_club_name} · {row.away_club_name}",
            "Condición": "Local" if home else "Visitante",
            "Minuto": num(row.minute),
            "Acción": "Entra" if enters else "Sale",
            "Relación": f"{'for' if is_english() else 'por'} {row.player_name}" if enters else f"{'for' if is_english() else 'por'} {row.in_player_name}",
        })
    return pd.DataFrame(result).sort_values(["Fecha", "Minuto"], ascending=[False, False]) if result else pd.DataFrame(
        columns=["Fecha", "Partido", "Condición", "Minuto", "Acción", "Relación"]
    )


def accumulated_difference_segments(weekly: pd.DataFrame) -> pd.DataFrame:
    """Split the accumulated line at zero so each segment keeps its true sign."""
    if len(weekly) < 2:
        return pd.DataFrame(columns=["segment", "Jornada", "Acumulada", "Signo"])
    rows: list[dict[str, object]] = []
    points = weekly[["Jornada", "Diferencia acumulada"]].to_dict("records")
    for index, (start, end) in enumerate(zip(points, points[1:])):
        x0, y0 = float(start["Jornada"]), float(start["Diferencia acumulada"])
        x1, y1 = float(end["Jornada"]), float(end["Diferencia acumulada"])

        def add_segment(segment: str, first: tuple[float, float], second: tuple[float, float], sign: str) -> None:
            rows.extend(
                {
                    "segment": segment,
                    "Jornada": x,
                    "Acumulada": y,
                    "Signo": sign,
                }
                for x, y in (first, second)
            )

        # Zero belongs to the negative/red side. A crossing is split exactly
        # at zero instead of masking the direction change with a third colour.
        crosses_zero = (y0 <= 0 < y1) or (y1 <= 0 < y0)
        if crosses_zero:
            cross_x = x0 + ((0 - y0) * (x1 - x0) / (y1 - y0))
            add_segment(f"{index}-a", (x0, y0), (cross_x, 0), "Negativa")
            add_segment(f"{index}-b", (cross_x, 0), (x1, y1), "Positiva" if y1 > 0 else "Negativa")
        else:
            sign = "Positiva" if y1 > 0 else "Negativa"
            add_segment(str(index), (x0, y0), (x1, y1), sign)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------- assets
@lru_cache(maxsize=None)
def image_uri(path: str, kind: str) -> str:
    """Embed an image as a data URI; player portraits are downscaled to keep pages light."""
    from PIL import Image

    image = Image.open(path).convert("RGBA")
    buffer = io.BytesIO()
    if kind == "photo":
        image.thumbnail((200, 267))
        image.save(buffer, format="WEBP", quality=82)
        mime = "image/webp"
    else:
        image.thumbnail((220, 220))
        image.save(buffer, format="PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def uri_from(relative_path: object, kind: str) -> str | None:
    path = asset_path(relative_path)
    return image_uri(str(path), kind) if path else None


def brand_uri(name: str) -> str:
    return image_uri(str(BRAND_ROOT / name), "crest")


def crest(club: pd.Series | None, size: int = 36) -> str:
    uri = uri_from(club.get("crest_file"), "crest") if club is not None else None
    if not uri:
        return f"<span class='crest crest-empty' style='--s:{size}px'></span>"
    return f"<img class='crest' style='--s:{size}px' src='{uri}' alt=''>"


def crest_with_elo(club: pd.Series | None, size: int = 120) -> str:
    """Display the current team Elo as an overlay instead of a separate KPI."""
    elo = club.get("elo_current") if club is not None else None
    badge = f"<span class='elo-orb'>Elo<br><b>{int(elo)}</b></span>" if elo is not None and not pd.isna(elo) else ""
    return f"<div class='crest-elo' style='--crest-size:{size}px'>{crest(club, size)}{badge}</div>"


def portrait(player: pd.Series, extra_class: str = "") -> str:
    uri = uri_from(player.get("photo_file"), "photo")
    inner = f"<img src='{uri}' alt=''>" if uri else "<span class='ph-empty'>?</span>"
    return f"<div class='ph {extra_class}'>{inner}</div>"


def pos_badge(code: object, full: bool = False) -> str:
    code = str(code).strip() if code is not None and not pd.isna(code) else "-"
    label, color = POSITIONS.get(code, (code, "#8b95a3"))
    text = f"{code} · {label}" if full else code
    return f"<span class='pos' style='--c:{color}' title='{escape(label)}'>{escape(text)}</span>"


_FLAG_SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 30 20'><rect width='30' height='20' fill='#fff'/><rect x='7.5' width='22.5' height='6.67' fill='#00732f'/><rect x='7.5' y='13.33' width='22.5' height='6.67' fill='#000'/><rect width='7.5' height='20' fill='#f00'/></svg>"
# st.html strips inline <svg>, so the flag travels as an image data URI
UAE_FLAG = f"<img class='flag' src='data:image/svg+xml;base64,{base64.b64encode(_FLAG_SVG.encode()).decode()}' alt='UAE' title='United Arab Emirates'>"

COUNTRY_FLAGS = {
    "albania": "🇦🇱", "algeria": "🇩🇿", "argentina": "🇦🇷", "bahrain": "🇧🇭",
    "belgium": "🇧🇪", "bosnia": "🇧🇦", "brazil": "🇧🇷", "bulgaria": "🇧🇬",
    "burkina faso": "🇧🇫", "cameroon": "🇨🇲", "colombia": "🇨🇴",
    "comoros": "🇰🇲", "congo, democratic republic of the": "🇨🇩",
    "cote d'ivoire": "🇨🇮", "croatia": "🇭🇷", "egypt": "🇪🇬", "eritrea": "🇪🇷",
    "france": "🇫🇷", "gambia": "🇬🇲", "ghana": "🇬🇭", "guinea": "🇬🇳",
    "germany": "🇩🇪", "india": "🇮🇳", "iran": "🇮🇷", "iraq": "🇮🇶",
    "italy": "🇮🇹", "jordan": "🇯🇴", "lebanon": "🇱🇧", "liberia": "🇱🇷",
    "luxembourg": "🇱🇺", "macedonia, the former yugoslav republic": "🇲🇰",
    "mali": "🇲🇱", "morocco": "🇲🇦", "mozambique": "🇲🇿", "netherlands": "🇳🇱",
    "new zealand": "🇳🇿", "niger": "🇳🇪", "nigeria": "🇳🇬", "oman": "🇴🇲",
    "pakistan": "🇵🇰", "palestine": "🇵🇸", "poland": "🇵🇱", "portugal": "🇵🇹",
    "republic of the congo": "🇨🇬", "senegal": "🇸🇳", "serbia": "🇷🇸",
    "slovakia": "🇸🇰", "spain": "🇪🇸", "sudan": "🇸🇩", "sweden": "🇸🇪",
    "syria": "🇸🇾", "togo": "🇹🇬", "trinidad and tobago": "🇹🇹", "tunisia": "🇹🇳",
    "united arab emirates": "🇦🇪", "u a e": "🇦🇪", "uae": "🇦🇪",
    "united kingdom": "🇬🇧", "uruguay": "🇺🇾", "usa": "🇺🇸", "venezuela": "🇻🇪",
    "yemen": "🇾🇪", "zambia": "🇿🇲",
}


def country_flag(country: object) -> str:
    """Return a compact flag when the official country label is recognised."""
    if country is None or pd.isna(country):
        return "🌐"
    return COUNTRY_FLAGS.get(str(country).strip().lower(), "🌐")


def market_value(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    amount = float(value)
    return f"€{amount / 1_000_000:.2f}m" if amount >= 1_000_000 else f"€{amount / 1_000:.0f}k"


def identity_chips(player: pd.Series, compact: bool = False) -> str:
    """Keep UAEFA registration visible alongside the official nationality."""
    country = player.get("nationality_official")
    label = str(country) if country is not None and not pd.isna(country) else str(player.get("nationality_category", "-"))
    country_chip = (
        f"<span class='country-flag' title='Nacionalidad: {escape(label)}' "
        f"aria-label='Nacionalidad: {escape(label)}'>{country_flag(label)}</span>"
    )
    if label.strip().lower() in {"united arab emirates", "u a e", "uae"}:
        return f"<span class='chip nat' title='Registro UAEFA · Nacionalidad: United Arab Emirates'>{UAE_FLAG} UAEFA</span>"
    registry = f"<span class='chip nat'>{UAE_FLAG} UAEFA</span>"
    return f"{registry}{country_chip}"


def is_emirati(player: pd.Series) -> bool:
    """UAEFA nationality_id 1 = United Arab Emirates (citizens, citizens' children and passport holders)."""
    return str(player.get("nationality_id")) == "1"


def num(value: object) -> int:
    return int(value) if value is not None and not pd.isna(value) else 0


# -------------------------------------------------------------------------- CSS
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#fcfcfb;--s1:#ffffff;--s2:#f3f3f0;--s3:#e9ebe8;--line:#e1e1da;--yellow:#ae7800;--yellow-d:#865b00;--text:#111315;--muted:#62666b;--green:#148a54;--red:#d64558;--navy:#14234a}
html,body,.stApp,[data-testid="stAppViewContainer"]{background:radial-gradient(1100px 520px at 90% -10%,rgba(255,210,31,.15),transparent 60%),radial-gradient(900px 500px at -10% 110%,rgba(37,106,191,.07),transparent 60%),var(--bg)!important;color:var(--text);font-family:'Inter',sans-serif}
[data-testid="stHeader"],[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"],#MainMenu,footer{display:none!important}
.block-container{max-width:1320px;padding:0 1.6rem 3rem!important}
[data-testid="stVerticalBlock"]{gap:.8rem}
h1,h2,h3{font-family:'Barlow Condensed',sans-serif;letter-spacing:.02em}
h1,h2,h3,p,label,[data-testid="stWidgetLabel"]{color:var(--text)}
/* ---------- brand bar */
div[data-testid="stElementContainer"]:has(.brandbar){position:sticky;top:0;z-index:100}
.brandbar{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.7rem 1.1rem;margin:0 -1.6rem;background:rgba(255,255,255,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.brandbar::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:linear-gradient(90deg,var(--yellow),rgba(255,210,31,0) 70%)}
.brand-left,.brand-right{display:flex;align-items:center;gap:.85rem}
.brand-left img{height:46px;width:auto;filter:drop-shadow(0 4px 10px rgba(255,210,31,.25))}
.brand-title{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.55rem;line-height:1;text-transform:uppercase;letter-spacing:.06em}
.brand-title b{color:var(--yellow)}
.brand-sub{font-size:.68rem;color:var(--muted);letter-spacing:.18em;text-transform:uppercase;margin-top:.2rem}
.here{display:flex;align-items:center;gap:.5rem;padding:.4rem .85rem;border:1px solid rgba(255,210,31,.35);border-radius:999px;background:rgba(255,210,31,.08);font-size:.74rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--yellow)}
.here i{width:8px;height:8px;border-radius:50%;background:var(--yellow);box-shadow:0 0 0 0 rgba(255,210,31,.7);animation:pulse 1.8s infinite}
@keyframes pulse{70%{box-shadow:0 0 0 9px rgba(255,210,31,0)}100%{box-shadow:0 0 0 0 rgba(255,210,31,0)}}
/* ---------- nav (segmented control) */
[data-testid="stButtonGroup"]{justify-content:flex-start}.nav-wrap [data-testid="stButtonGroup"]{justify-content:center}
[data-testid="stButtonGroup"] button{background:var(--s1)!important;border:1px solid var(--line)!important;color:var(--muted)!important;font-family:'Barlow Condensed',sans-serif;font-size:1.05rem!important;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:.55rem 1.5rem!important;min-height:46px;transition:all .18s}
[data-testid="stButtonGroup"] button:hover{color:var(--text)!important;border-color:var(--yellow)!important}
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"],[data-testid="stButtonGroup"] button[aria-checked="true"],[data-testid="stButtonGroup"] button[aria-pressed="true"]{background:var(--yellow)!important;color:#0a0c0f!important;border-color:var(--yellow)!important;box-shadow:0 6px 22px rgba(255,210,31,.28)}
/* ---------- buttons */
div[data-testid="stElementContainer"]:has(.stButton){width:100%!important}.stButton{width:100%}.stButton>button{width:100%;background:var(--s2);border:1px solid var(--line);color:var(--text);border-radius:12px;font-weight:600;font-size:.8rem;letter-spacing:.04em;padding:.35rem .6rem;min-height:2.2rem;transition:all .18s}
.stButton>button:hover{border-color:var(--yellow);color:var(--yellow);background:rgba(255,210,31,.07);transform:translateY(-1px)}
.stButton>button[kind="primary"]{background:var(--yellow);color:#0a0c0f;border-color:var(--yellow)}
.stButton>button[kind="primary"]:hover{background:#ffe055;color:#0a0c0f}
div[class*="st-key-crumb-"] .stButton,div[class*="st-key-crumb-"] .stButton>button{width:auto!important}
div[class*="st-key-crumb-"] .stButton>button{min-height:1.8rem;padding:.1rem .15rem!important;border:0!important;border-radius:7px!important;background:transparent!important;color:var(--muted)!important;font-size:.72rem!important;font-weight:600!important;letter-spacing:.12em!important;text-transform:uppercase}
div[class*="st-key-crumb-"] .stButton>button:hover{background:rgba(255,210,31,.14)!important;color:#8a5e00!important;transform:none}
.crumb-sep{display:grid;place-items:center;height:1.8rem;color:#b77d00;font-weight:800;font-size:1rem}
.crumb-current{display:flex;align-items:center;min-height:1.8rem;color:var(--text);font-size:.72rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.st-key-player_back,.st-key-player_back .stButton{width:auto!important}.st-key-player_back .stButton>button{width:auto!important;min-height:2.45rem;padding:.42rem 1.05rem!important;border-radius:999px!important;font-size:.82rem!important;font-weight:800!important;box-shadow:0 5px 14px rgba(183,125,0,.2)}
/* ---------- inputs */
[data-baseweb="input"],[data-baseweb="select"]>div{background:var(--s1)!important;border-color:var(--line)!important;border-radius:12px!important}
[data-baseweb="input"] input,[data-baseweb="select"] *,[data-baseweb="select"] svg{color:var(--text)!important;fill:var(--text)!important}
[data-baseweb="tag"]{background:#f4e4af!important;border:1px solid #d6ac45!important}[data-baseweb="tag"] span{color:#604000!important}
[data-testid="stWidgetLabel"] p{font-size:.7rem;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:600}
.scope-panel{display:flex;align-items:center;gap:.7rem;padding:.55rem .75rem;margin-bottom:.35rem;border:1px solid rgba(255,210,31,.6);border-radius:12px 12px 8px 8px;background:linear-gradient(90deg,rgba(255,210,31,.16),rgba(255,210,31,.03));box-shadow:0 8px 22px rgba(255,210,31,.08)}
.scope-panel i{display:block;width:9px;height:9px;border-radius:50%;background:var(--yellow);box-shadow:0 0 0 5px rgba(255,210,31,.12)}
.scope-panel span{font-size:.65rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--yellow)}
.scope-panel b{margin-left:auto;font-family:'Barlow Condensed',sans-serif;font-size:1rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text)}
div[data-testid="stElementContainer"]:has(.scope-panel) + div [data-baseweb="select"]>div{min-height:54px;border:2px solid var(--yellow)!important;background:linear-gradient(90deg,rgba(255,210,31,.13),var(--s1))!important;box-shadow:0 9px 24px rgba(0,0,0,.3)}
/* ---------- page banner */
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin:1.3rem 0 .6rem;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.crumbs span.sep{color:var(--yellow)}.crumbs b{color:var(--text);font-weight:600}
.banner{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:1.5rem;padding:1.6rem 2rem;border-radius:22px;border:1px solid var(--line);background:linear-gradient(120deg,#ffffff 0%,#f6f7f4 55%,#fff8e5 130%)}
.banner::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:linear-gradient(180deg,var(--yellow),var(--yellow-d))}
.banner .num{font-family:'Barlow Condensed',sans-serif;font-size:7rem;font-weight:800;line-height:.8;color:rgba(255,210,31,.09);position:absolute;right:2rem;top:1.2rem;letter-spacing:.02em}
.banner .kicker{font-size:.72rem;letter-spacing:.24em;text-transform:uppercase;color:var(--yellow);font-weight:600}
.banner h1{font-size:3.1rem;text-transform:uppercase;margin:.35rem 0 .3rem;line-height:.95;font-weight:800}
.banner p{margin:0;color:var(--muted);max-width:640px;font-size:.92rem}
.banner img.watermark{height:120px;opacity:.95;position:relative;z-index:1;filter:drop-shadow(0 10px 24px rgba(0,0,0,.5))}
.section{display:flex;align-items:center;gap:.8rem;margin:1.8rem 0 .8rem}
.section::before{content:"";width:5px;height:30px;border-radius:3px;background:var(--yellow)}
.section h2{margin:0;font-size:1.7rem;text-transform:uppercase;font-weight:700}
.section small{margin-left:auto;color:var(--muted);font-size:.74rem;letter-spacing:.1em;text-transform:uppercase}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.scatter-shell){margin-top:.15rem;border-color:#dedfd8!important;border-radius:20px!important;background:linear-gradient(145deg,#ffffff,#fbfbf7)!important;box-shadow:0 10px 30px rgba(28,35,22,.06)}
.scatter-shell{display:flex;align-items:baseline;gap:.75rem;margin:.05rem 0 .55rem;padding-bottom:.65rem;border-bottom:1px solid var(--line)}
.scatter-shell span{font-size:.66rem;font-weight:800;letter-spacing:.16em;color:#8b6200}.scatter-shell b{font-size:.8rem;font-weight:600;color:var(--muted)}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.filter-shell){margin-top:.15rem;border-color:#dedfd8!important;border-radius:20px!important;background:linear-gradient(145deg,#ffffff,#fbfbf7)!important;box-shadow:0 10px 30px rgba(28,35,22,.05)}
.filter-shell{display:flex;align-items:baseline;gap:.75rem;margin:.05rem 0 .55rem;padding-bottom:.65rem;border-bottom:1px solid var(--line)}
.filter-shell span{font-size:.66rem;font-weight:800;letter-spacing:.16em;color:#8b6200}.filter-shell b{font-size:.8rem;font-weight:600;color:var(--muted)}
.filter-legend{display:flex;gap:.55rem;flex-wrap:wrap;justify-content:flex-start;margin-top:.25rem;padding-top:.65rem;border-top:1px dashed var(--line)}
/* ---------- kpis */
.kpis{display:grid;grid-template-columns:repeat(var(--n,4),1fr);gap:.8rem;margin-top:.9rem}
.kpi{background:var(--s1);border:1px solid var(--line);border-radius:16px;padding:.95rem 1.1rem;position:relative;overflow:hidden}
.kpi::after{content:"";position:absolute;left:1.1rem;right:1.1rem;bottom:0;height:3px;border-radius:3px 3px 0 0;background:var(--k,var(--yellow))}
.kpi label{display:block;font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:600}
.kpi div{font-family:'Barlow Condensed',sans-serif;font-size:2.5rem;font-weight:700;line-height:1.1;margin-top:.15rem}
/* ---------- player availability */
.availability{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem;margin-top:.9rem}
.availability-card{position:relative;overflow:hidden;padding:1rem 1.1rem;border:1px solid var(--line);border-radius:16px;background:linear-gradient(135deg,color-mix(in srgb,var(--a) 11%,var(--s1)),var(--s1) 68%)}
.availability-card::after{content:"";position:absolute;left:1.1rem;right:1.1rem;bottom:0;height:3px;border-radius:3px 3px 0 0;background:var(--a)}
.availability-card label{display:block;font-size:.66rem;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:700}
.availability-card b{display:block;margin:.18rem 0 .32rem;font-family:'Barlow Condensed',sans-serif;font-size:2.35rem;line-height:1;color:var(--text)}
.availability-card .main-rate{color:var(--a);font-weight:700;font-size:.82rem}.availability-card small{display:block;margin-top:.25rem;color:var(--muted);font-size:.68rem;line-height:1.35}
/* ---------- crest / photo / badges */
.crest{width:var(--s);height:var(--s);object-fit:contain;flex:none;filter:drop-shadow(0 3px 6px rgba(0,0,0,.45))}
.crest-empty{display:inline-block;border-radius:50%;background:var(--s3)}
.crest-elo{position:relative;width:var(--crest-size);height:var(--crest-size);flex:none}
.crest-elo .crest{display:block}
.elo-orb{position:absolute;right:-12px;bottom:-10px;width:48px;height:48px;border-radius:50%;display:grid;place-items:center;align-content:center;background:#111827;border:2px solid #d5a900;box-shadow:0 5px 16px rgba(17,24,39,.38);color:#d9dee8;font-size:.57rem;line-height:1.05;text-align:center;text-transform:uppercase;font-weight:700;letter-spacing:.08em}
.elo-orb b{display:block;color:#ffd21f;font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;letter-spacing:0}
.ph{position:relative;overflow:hidden;background:#fff;border-radius:14px;aspect-ratio:3/4}
.ph img{width:100%;height:100%;object-fit:cover;object-position:top center;display:block}
.ph-empty{position:absolute;inset:0;display:grid;place-items:center;font-size:2rem;color:#0a0c0f;font-weight:800}
.ph.round{aspect-ratio:1;border-radius:50%;border:2px solid var(--yellow)}
.ph.round img{object-position:top center;transform:scale(1.25);transform-origin:50% 18%}
.pos{display:inline-block;padding:.12rem .5rem;border-radius:7px;font-size:.7rem;font-weight:700;letter-spacing:.06em;color:var(--c);background:color-mix(in srgb,var(--c) 15%,transparent);border:1px solid color-mix(in srgb,var(--c) 45%,transparent)}
.chip{display:inline-flex;align-items:center;gap:.35rem;padding:.2rem .6rem;border-radius:999px;background:var(--s3);color:var(--muted);font-size:.7rem;font-weight:600;letter-spacing:.04em}
.chip.y{background:rgba(255,210,31,.14);color:var(--yellow)}
.chip.elo{background:#111827;border:1px solid #2e3c59;color:#d5dbe7}.chip.elo b{margin-left:.08rem;color:#ffd21f;font-family:'Barlow Condensed',sans-serif;font-size:1rem;line-height:.8}
/* ---------- poster-cells table (standings) */
.scroll-x{overflow-x:auto}
.ptable{min-width:880px;display:flex;flex-direction:column;gap:.45rem}
.prow{display:grid;grid-template-columns:58px minmax(240px,1fr) repeat(7,66px) 92px;gap:.4rem;align-items:stretch}
.pc{display:flex;align-items:center;justify-content:center;background:var(--s1);border:1px solid var(--line);border-radius:12px;padding:.55rem .3rem;font-family:'Barlow Condensed',sans-serif;font-size:1.35rem;font-weight:600;min-height:58px;transition:transform .15s,border-color .15s}
.prow:not(.phead):hover .pc{border-color:rgba(255,210,31,.5)}
.pc.club{justify-content:flex-start;gap:.8rem;padding-left:.8rem;font-size:1.3rem;font-weight:700;letter-spacing:.02em;text-transform:uppercase}
.pc.rank{font-size:1.6rem;font-weight:800;color:var(--muted)}
.pc.pts{background:linear-gradient(135deg,var(--yellow),var(--yellow-d));color:#0a0c0f;border-color:var(--yellow);font-size:1.9rem;font-weight:800}
.pc.pos-up{color:var(--green)}.pc.neg{color:var(--red)}.pc.dim{color:var(--muted)}
.prow.lead .pc.rank{background:var(--yellow);color:#0a0c0f;border-color:var(--yellow)}
.prow.lead .pc.club{border-color:rgba(255,210,31,.55);background:linear-gradient(90deg,rgba(255,210,31,.12),var(--s1) 60%)}
.phead .pc{background:transparent;border:none;min-height:auto;padding:.1rem 0;font-family:'Inter',sans-serif;font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);font-weight:600}
/* ---------- cards grids */
.grid{display:grid;grid-template-columns:repeat(var(--cols,4),minmax(0,1fr));gap:.9rem}
.card{background:var(--s1);border:1px solid var(--line);border-radius:18px;transition:transform .18s,border-color .18s,box-shadow .18s}
.card:hover{transform:translateY(-3px);border-color:rgba(174,120,0,.55);box-shadow:0 14px 30px rgba(25,28,20,.14)}
.card.sel{border-color:var(--yellow);box-shadow:0 0 0 1px var(--yellow),0 14px 34px rgba(255,210,31,.16)}
/* scorers */
.scorer{padding:.8rem;position:relative;overflow:hidden}
.scorer .rank{position:absolute;left:.8rem;top:.8rem;z-index:2;min-width:30px;height:30px;padding:0 .4rem;display:grid;place-items:center;border-radius:9px;background:#0a0c0f;color:var(--yellow);font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.15rem}
.scorer.first{background:linear-gradient(160deg,#2a2400,var(--s1) 65%);border-color:rgba(255,210,31,.6)}
.scorer .goals{position:absolute;right:.8rem;top:.8rem;z-index:2;text-align:center;line-height:1;padding:.35rem .6rem;border-radius:11px;background:#0a0c0f;border:1px solid var(--yellow)}
.scorer .goals b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:1.7rem;color:var(--yellow)}
.scorer .goals small{font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.scorer .nm,.pcard .nm{margin-top:.65rem;font-family:'Barlow Condensed',sans-serif;font-size:1.3rem;font-weight:700;text-transform:uppercase;line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta{display:flex;align-items:center;gap:.45rem;margin-top:.4rem;font-size:.74rem;color:var(--muted);white-space:nowrap;overflow:hidden}
.meta span{overflow:hidden;text-overflow:ellipsis}
/* ranking cards */
.ranking{position:relative;overflow:hidden;padding:.75rem;min-height:132px;background:linear-gradient(145deg,color-mix(in srgb,var(--r) 13%,var(--s1)),var(--s1) 70%);border-color:color-mix(in srgb,var(--r) 35%,var(--line))}
.ranking .rank-no{position:absolute;right:.7rem;top:.6rem;display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:#0a0c0f;border:1px solid var(--r);color:var(--r);font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;font-weight:800}
.ranking .rank-main{display:flex;gap:.7rem;align-items:center;padding-right:2rem}.ranking .rank-photo{width:56px;flex:none}.ranking .rank-photo .ph{border-radius:11px}
.ranking .rank-info{min-width:0;flex:1}.ranking .rank-name{font-family:'Barlow Condensed',sans-serif;font-size:1.18rem;font-weight:700;line-height:1.02;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ranking .rank-club{display:flex;align-items:center;gap:.35rem;margin-top:.3rem;color:var(--muted);font-size:.67rem;white-space:nowrap;overflow:hidden}.ranking .rank-club span{overflow:hidden;text-overflow:ellipsis}
.ranking .rank-foot{display:flex;align-items:end;justify-content:space-between;gap:.5rem;margin-top:.62rem;padding-top:.5rem;border-top:1px solid color-mix(in srgb,var(--r) 22%,var(--line))}.ranking .rank-age{font-size:.64rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.ranking .rank-age b{display:block;margin-top:.08rem;color:var(--text);font-family:'Barlow Condensed',sans-serif;font-size:1rem;letter-spacing:0}
.ranking .rank-value{text-align:right;color:var(--r);font-family:'Barlow Condensed',sans-serif;font-size:1.65rem;font-weight:800;line-height:.85}.ranking .rank-value small{display:block;margin-top:.22rem;color:var(--muted);font-family:'Inter',sans-serif;font-size:.54rem;letter-spacing:.12em;text-transform:uppercase}
/* ranking evolution / bumpy chart */
.bumpy-legend{display:flex;flex-wrap:wrap;gap:.55rem;margin:.4rem 0 .75rem}.bumpy-team{display:flex;align-items:center;gap:.42rem;padding:.3rem .58rem;border:1px solid color-mix(in srgb,var(--bc) 55%,var(--line));border-radius:999px;background:color-mix(in srgb,var(--bc) 11%,var(--s1));font-size:.7rem;font-weight:700;letter-spacing:.04em}.bumpy-team i{width:8px;height:8px;border-radius:50%;background:var(--bc);box-shadow:0 0 9px var(--bc)}
/* player cards: a restrained positional tint makes the squad easier to scan. */
.pcard{padding:.75rem;background:linear-gradient(135deg,color-mix(in srgb,var(--pos-c) 14%,var(--s1)),var(--s1) 58%);border-color:color-mix(in srgb,var(--pos-c) 30%,var(--line))}
.pcard .pc-head{display:flex;align-items:center;gap:.8rem}
.pcard .thumb{position:relative;width:76px;flex:none}
.pcard .thumb .ph{border-radius:12px}
.pcard .dorsal{position:absolute;left:.25rem;bottom:.25rem;padding:.1rem .35rem;border-radius:6px;background:#0a0c0f;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:.95rem;color:var(--yellow);line-height:1}
.pcard .info{min-width:0;flex:1}
.pcard .info .nm{margin:0;font-size:1.3rem}
.pcard .tags{display:flex;align-items:center;gap:.5rem;margin-top:.5rem}
.age-inline{margin-left:auto;padding:.1rem .42rem;border-radius:999px;background:rgba(37,106,191,.09);border:1px solid rgba(37,106,191,.18);color:#24598f;font-size:.63rem;font-weight:700;letter-spacing:.04em;white-space:nowrap}
.elo-player{width:42px;height:42px;display:grid;place-items:center;flex:none;border-radius:50%;background:#111827;border:3px solid var(--elo);box-shadow:0 3px 10px rgba(17,24,39,.18);color:var(--elo);font-family:'Barlow Condensed',sans-serif;font-size:1.2rem;font-weight:800;line-height:1}
.flag{height:16px;width:auto;border-radius:3px;box-shadow:0 0 0 1px rgba(255,255,255,.18);vertical-align:middle;flex:none}
.chip.nat{display:inline-flex;align-items:center;gap:.45rem;background:rgba(17,19,21,.06);color:var(--text)}
.chip.age{background:rgba(37,106,191,.10);border:1px solid rgba(37,106,191,.22);color:#205895}
.country-flag{display:inline-grid;place-items:center;width:32px;height:28px;border-radius:999px;background:var(--s3);border:1px solid var(--line);font-size:1.05rem;line-height:1;cursor:help;box-shadow:0 2px 8px rgba(0,0,0,.18);transition:border-color .16s,transform .16s}
.country-flag:hover{border-color:var(--yellow);transform:translateY(-1px)}
.posgroup{display:flex;align-items:center;gap:.7rem;margin:1.6rem 0 .8rem}
.posgroup h3{margin:0;font-size:1.35rem;text-transform:uppercase;font-weight:700;color:var(--c)}
.posgroup small{color:var(--muted);font-size:.72rem;letter-spacing:.1em;text-transform:uppercase}
.posgroup::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,color-mix(in srgb,var(--c) 55%,transparent),transparent)}
.posgroup .pos{font-size:.85rem;padding:.2rem .6rem}
.stats{display:grid;grid-template-columns:repeat(var(--n,5),1fr);gap:.35rem;margin-top:.7rem}
.stat{background:var(--s2);border-radius:10px;padding:.35rem .1rem;text-align:center;line-height:1.1}
.stat b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:1.25rem}
.stat small{font-size:.54rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.stat.g b{color:var(--yellow)}.stat.y b{color:var(--yellow)}.stat.r b{color:var(--red)}
/* match cards */
.mcard{padding:.9rem 1rem}
.mcard .when{display:flex;justify-content:space-between;font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.mcard .teams{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:.4rem;margin-top:.8rem;text-align:center}
.mcard .tn{font-family:'Barlow Condensed',sans-serif;font-weight:700;text-transform:uppercase;font-size:1.02rem;line-height:1.05;margin-top:.35rem;min-height:2.1em;display:flex;align-items:center;justify-content:center}
.mcard .sc{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:2.1rem;white-space:nowrap}
.mcard .sc i{color:var(--yellow);font-style:normal;margin:0 .1rem}
.mcard.fill{display:flex;flex-direction:column;justify-content:center;text-align:center;background:linear-gradient(150deg,#1a1800,var(--s1));border-style:dashed}
.mcard.fill b{font-family:'Barlow Condensed',sans-serif;font-size:3.6rem;color:var(--yellow);line-height:1}
.mcard.fill span{font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
/* matchday list */
.match-list{display:flex;flex-direction:column;gap:.55rem}
.match-row{display:grid;grid-template-columns:120px minmax(160px,1fr) 86px minmax(160px,1fr) 110px;align-items:center;gap:.8rem;padding:.7rem 1rem}
.match-row .date{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);line-height:1.45}
.match-row .team{display:flex;align-items:center;gap:.7rem;font-family:'Barlow Condensed',sans-serif;font-size:1.2rem;font-weight:700;text-transform:uppercase;min-width:0}
.match-row .team.home{justify-content:flex-end;text-align:right}.match-row .team span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.match-row .result{padding:.28rem .45rem;border-radius:10px;background:#111827;border:1px solid #d5a900;color:#ffffff;font-family:'Barlow Condensed',sans-serif;font-size:1.65rem;font-weight:800;text-align:center;white-space:nowrap;box-shadow:0 3px 8px rgba(17,24,39,.16)}
.match-row .result i{color:#ffd21f;font-style:normal;margin:0 .18rem}.match-row .meta{text-align:right;justify-content:flex-end;margin:0;font-size:.67rem;line-height:1.35}
/* scoreboard */
.board{position:relative;overflow:hidden;border-radius:24px;border:1px solid var(--line);padding:1.6rem 1.2rem;background:radial-gradient(600px 220px at 50% 0%,rgba(255,210,31,.12),transparent 70%),var(--s1)}
.board .row{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:1rem}
.board .team{text-align:center}
.board .team h3{font-size:2rem;margin:.6rem 0 .1rem;text-transform:uppercase;font-weight:800}
.board .scorers{font-size:.78rem;color:var(--muted);line-height:1.6}
.board .mid{text-align:center}
.board .when{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--yellow);font-weight:600}
.board .big{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:6rem;line-height:1;margin:.3rem 0;white-space:nowrap}
.board .big i{color:var(--yellow);font-style:normal;margin:0 .6rem}
.board .info{display:flex;justify-content:center;flex-wrap:wrap;gap:.45rem;margin-top:.4rem}
/* timeline */
.tl{display:flex;flex-direction:column;gap:.4rem}
.tl .ev{display:grid;grid-template-columns:1fr 62px 1fr;gap:.5rem;align-items:center}
.tl .min{display:grid;place-items:center;height:36px;border-radius:10px;background:#0a0c0f;border:1px solid var(--line);font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.15rem;color:var(--yellow)}
.tl .cell{background:var(--s1);border:1px solid var(--line);border-radius:12px;padding:.45rem .8rem;font-size:.82rem;display:flex;align-items:center;gap:.55rem;min-height:36px}
.tl .cell.h{justify-content:flex-end;text-align:right}
.tl .cell.empty{background:transparent;border-color:transparent}
.tl .cell.goal{border-color:rgba(255,210,31,.6);background:linear-gradient(90deg,rgba(255,210,31,.12),var(--s1))}
.tl .cell small{display:block;color:var(--muted);font-size:.7rem}
.ic{display:inline-block;width:13px;height:18px;border-radius:3px;flex:none}
.ic.y{background:#ffd21f}.ic.r{background:#ff3b4a}
.ic.sub{width:auto;height:auto;font-weight:700;color:var(--green)}
.ic.ball{width:auto;height:auto;font-size:1rem}
/* pitch */
.teamhead{display:flex;align-items:center;gap:.8rem;margin-bottom:.7rem}
.teamhead h3{margin:0;font-size:1.5rem;text-transform:uppercase}
.pitch{border-radius:20px;padding:1rem .6rem;border:1px solid #1d4a33;background:repeating-linear-gradient(180deg,#0f3a28 0 52px,#10402c 52px 104px);position:relative;display:flex;flex-direction:column;gap:1.1rem}
.pitch::before{content:"";position:absolute;left:50%;top:0;bottom:0;width:0;border-left:0}
.pitch::after{content:"";position:absolute;inset:10px;border:1px solid rgba(255,255,255,.14);border-radius:12px;pointer-events:none}
.line{display:flex;justify-content:space-evenly;gap:.4rem;position:relative;z-index:1}
.pl{width:84px;text-align:center}
.pl .av{position:relative;width:62px;margin:0 auto}
.pl .num{position:absolute;right:-8px;bottom:-4px;min-width:24px;height:24px;display:grid;place-items:center;padding:0 .25rem;border-radius:8px;background:#ffd21f;border:1px solid #ffffff;color:#111827;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:.95rem;box-shadow:0 2px 6px rgba(0,0,0,.22)}
.pl .cap{position:absolute;left:-6px;top:-4px;width:20px;height:20px;border-radius:50%;background:var(--yellow);color:#0a0c0f;font-size:.68rem;font-weight:800;display:grid;place-items:center}
.pl .out{position:absolute;left:-8px;bottom:-4px;font-size:.62rem;font-weight:700;padding:.05rem .3rem;border-radius:6px;background:#3a1016;color:var(--red);border:1px solid #6b1c27}
.pl .pn{margin-top:.4rem;font-size:.72rem;font-weight:600;line-height:1.15;color:#fff;text-shadow:0 1px 3px #000;overflow:visible}
.pl .player-name{display:-webkit-box;overflow:hidden;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:1.15em}
.pl .pn small{display:block;margin-top:.08rem;color:#ffd21f;font-size:.59rem;font-weight:700;letter-spacing:.04em;text-shadow:0 1px 2px #000}
.bench{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem;margin-top:.8rem}
.bn{display:flex;align-items:center;gap:.55rem;background:var(--s1);border:1px solid var(--line);border-radius:12px;padding:.4rem .6rem;min-width:0}
.bn.played{border-color:rgba(47,210,122,.45)}
.bn .av{width:38px;flex:none}
.bn .t{min-width:0;line-height:1.2}.bn .t b{display:block;font-size:.76rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bn .t small{color:var(--muted);font-size:.66rem}.bn .dn{margin-left:auto;font-family:'Barlow Condensed',sans-serif;font-weight:800;color:var(--yellow);font-size:1.05rem}
/* staff */
.staff{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem}
.sc2{background:var(--s1);border:1px solid var(--line);border-radius:12px;padding:.55rem .8rem;min-width:0}
.sc2 small{display:block;color:var(--yellow);font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;font-weight:600}
.sc2 b{font-size:.84rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}
/* club picker */
.ctile{display:flex;flex-direction:column;align-items:center;gap:.5rem;padding:.9rem .4rem .7rem}
.ctile b{font-family:'Barlow Condensed',sans-serif;font-size:.98rem;text-transform:uppercase;text-align:center;line-height:1.05;min-height:2.1em;display:flex;align-items:center}
/* profile */
.profile{display:grid;grid-template-columns:280px 1fr;gap:1.6rem;padding:1.4rem;border-radius:24px;border:1px solid var(--line);background:radial-gradient(520px 260px at 100% 0%,rgba(255,210,31,.12),transparent 70%),var(--s1)}
.profile .ph{border-radius:18px}
.profile h2{font-family:'Barlow Condensed',sans-serif;font-size:2.8rem;text-transform:uppercase;margin:.3rem 0 0;line-height:1;font-weight:800}
.profile .ar{direction:rtl;text-align:left;color:var(--muted);font-size:1.1rem;margin:.2rem 0 .8rem}
.profile .tags{display:flex;gap:.45rem;flex-wrap:wrap;margin:.7rem 0 1rem}
.clubline{display:flex;align-items:center;gap:.7rem;font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;font-weight:700;text-transform:uppercase}
.hrow{display:grid;grid-template-columns:110px 1fr auto 1fr 120px 90px;gap:.4rem;align-items:center;margin-bottom:.45rem}
.hrow .pc{min-height:50px;font-size:1.05rem}
.hrow .pc.t{gap:.6rem;font-size:1rem;text-transform:uppercase;font-weight:700}
.hrow .pc.t.h{justify-content:flex-end}.hrow .pc.t.a{justify-content:flex-start}
.footer{margin-top:2.4rem;padding:1.3rem 1rem;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:1rem;color:var(--muted);font-size:.74rem;flex-wrap:wrap}
.footer .fl{display:flex;align-items:center;gap:.8rem}.footer img{height:34px}
.empty{padding:2.2rem;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:16px}
.quick-open{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.05rem 0 .5rem}.quick-open b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:1.35rem;text-transform:uppercase;letter-spacing:.03em}.quick-open span{font-size:.72rem;color:var(--muted)}.quick-open i{width:10px;height:42px;border-radius:99px;background:var(--yellow);display:block;flex:none}
/* ---------- player season + on-pitch impact */
details.fold{margin-top:.9rem;border:1px solid var(--line);border-radius:20px;background:var(--s1);overflow:hidden}
details.fold>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:.9rem;padding:.85rem 1.1rem;background:linear-gradient(90deg,rgba(255,210,31,.07),transparent 60%)}
details.fold>summary::-webkit-details-marker{display:none}
.fold .chev{flex:none;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:var(--yellow);color:#0a0c0f;font-size:.8rem;transition:transform .2s}
details.fold[open] .chev{transform:rotate(90deg)}
.fold .ft{font-family:'Barlow Condensed',sans-serif;font-size:1.45rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}
.fold .fs{color:var(--muted);font-size:.84rem;min-width:0}.fold .fs b{color:var(--yellow);font-weight:700}
.fold .fh{margin-left:auto;color:var(--muted);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap}
.fold .fh::after{content:attr(data-open)}details.fold:not([open]) .fh::after{content:attr(data-closed)}
.fold .fbody{padding:.2rem 1.1rem 1.1rem}
.sample{display:flex;align-items:center;gap:.7rem;margin:.6rem 0 .9rem;padding:.6rem .9rem;border-radius:12px;border:1px dashed rgba(255,176,32,.55);background:rgba(255,176,32,.07);color:#ffcf7a;font-size:.8rem;line-height:1.4}
.sample i{font-style:normal;font-weight:800;color:#ffb020}
.impact-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:.9rem}
.icard{grid-column:span var(--span,6);display:flex;flex-direction:column;min-width:0;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:linear-gradient(160deg,color-mix(in srgb,var(--ic,#ffd21f) 8%,var(--s1)),var(--s1) 62%)}
.ic-head{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;padding:1rem 1.1rem .9rem}
.ic-head h3{margin:0;padding-left:.7rem;border-left:4px solid var(--ic,#ffd21f);font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;line-height:1;text-transform:uppercase;font-weight:800}
.ic-head small{display:block;margin:.4rem 0 0 .85rem;color:var(--muted);font-size:.76rem}
.ic-big{text-align:right;flex:none}.ic-big b{display:block;font-family:'Barlow Condensed',sans-serif;font-size:3.1rem;line-height:.9;font-weight:800}.ic-big small{margin:.35rem 0 0}
.ifacts{display:grid;grid-template-columns:repeat(var(--c,3),minmax(0,1fr));gap:1px;background:var(--line);border-top:1px solid var(--line);flex:1;grid-auto-rows:1fr}
.ifact{background:var(--s1);padding:.8rem 1.1rem;min-width:0}
.ifact span{display:block;font-size:.63rem;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:700}
.ifact b{display:block;margin-top:.15rem;font-family:'Barlow Condensed',sans-serif;font-size:2.1rem;line-height:1.05;font-weight:700}
.ifact b{white-space:nowrap}.ifact b .cardico{vertical-align:-1px;margin-right:.2rem}.ifact em{display:block;margin-top:.15rem;font-style:normal;color:var(--muted);font-size:.72rem;line-height:1.35}
.tp{color:var(--green)}.tn{color:var(--red)}.tw{color:#ffb020}.ty{color:var(--yellow)}.tz{color:var(--text)}
.cmp{padding:0 1.1rem 1rem}.cmp h4{margin:.8rem 0 .45rem;font-size:.64rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.cbar{display:grid;grid-template-columns:104px minmax(0,1fr) 62px;gap:.7rem;align-items:center;margin:.4rem 0;font-size:.88rem}
.cbar .tr{position:relative;height:14px;border-radius:99px;background:var(--s3)}
.cbar .tr i{position:absolute;top:0;bottom:0;border-radius:99px;background:var(--col)}
.cbar .tr.div::after{content:"";position:absolute;left:50%;top:-4px;bottom:-4px;width:2px;background:var(--muted);opacity:.7}
.cbar b{text-align:right;font-family:'Barlow Condensed',sans-serif;font-size:1.3rem}
.cmp-rule{border-top:1px solid var(--line);margin-top:.9rem}
.stack-top,.stack{display:flex;margin:0 1.1rem}.stack-top{margin-bottom:.35rem;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.05rem}
.stack-top span{text-align:center;min-width:0;overflow:hidden}
.stack{height:50px;border-radius:12px;overflow:hidden}.stack i{display:grid;place-items:center;min-width:0;font-style:normal;font-weight:800;font-size:.9rem;color:#0a0c0f}
.legend2{display:flex;gap:1rem;flex-wrap:wrap;padding:.8rem 1.1rem 1.1rem;color:var(--muted);font-size:.8rem}.legend2 span::before{content:"";display:inline-block;width:11px;height:11px;border-radius:3px;background:var(--col);margin-right:.4rem;vertical-align:-1px}
.empty-in{padding:2rem 1.1rem 2.4rem;text-align:center;color:var(--muted);font-size:.9rem}
.foot-note{margin:.9rem .2rem 0;color:var(--muted);font-size:.74rem;line-height:1.5}
.season-top{display:grid;grid-template-columns:1fr;gap:.9rem;margin-bottom:.9rem}
.srow{display:grid;grid-template-columns:44px 68px minmax(150px,1.5fr) 104px minmax(140px,1fr) minmax(120px,.9fr) 84px;gap:.6rem;align-items:center;padding:.55rem .9rem;border-top:1px solid var(--line)}
.srow:first-child{border-top:0}.srow:hover{background:rgba(255,210,31,.05)}
.srow .j{font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;font-weight:800;color:var(--muted)}
.srow .ha{justify-self:start}.chip.home{background:rgba(47,210,122,.14);color:var(--green)}.chip.away{background:rgba(76,154,255,.14);color:#7db4ff}
.rival{display:flex;align-items:center;gap:.6rem;min-width:0;font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;font-weight:700;text-transform:uppercase}
.rival span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.res{display:flex;align-items:center;gap:.5rem;font-family:'Barlow Condensed',sans-serif;font-size:1.35rem;font-weight:800}
.wdl{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;font:800 .78rem 'Inter',sans-serif;color:#fff}.wdl.W{background:#1a9b5a}.wdl.D{background:#c99a1a}.wdl.L{background:#d04552}
.srow .role{color:var(--muted);font-size:.85rem}
.mbar{display:flex;align-items:center;gap:.6rem}.mbar .t{flex:1;height:8px;border-radius:99px;background:var(--s3);overflow:hidden}.mbar .t i{display:block;height:100%;background:var(--green)}.mbar b{font-family:'Barlow Condensed',sans-serif;font-size:1.15rem;min-width:38px;text-align:right}
.evs{display:flex;gap:.3rem;align-items:center;justify-content:flex-end;flex-wrap:wrap}.cardico{width:11px;height:15px;border-radius:2px;display:inline-block}.cardico.y{background:#ffd21f}.cardico.r{background:#ff3b4a}
@media (max-width:900px){
 .grid{--cols:2!important}.board .big{font-size:3.6rem}.board .team h3{font-size:1.3rem}.banner h1{font-size:2.1rem}.banner img.watermark,.here{display:none}
 .profile{grid-template-columns:1fr}.kpis,.availability{grid-template-columns:repeat(2,1fr)}.brand-sub{display:none}.hrow{grid-template-columns:1fr}.banner .num{font-size:4rem}
 .icard{grid-column:1/-1!important}.srow{grid-template-columns:40px minmax(0,1fr) auto;row-gap:.35rem}.srow .ha{display:none}.srow .role,.srow .mbar{grid-column:2/-1}.srow .evs{justify-content:flex-start;grid-column:2/-1}.fold .fs{display:none}.ifacts[style*='--c:3']{grid-template-columns:repeat(2,minmax(0,1fr))}.cbar{grid-template-columns:84px minmax(0,1fr) 56px}
 .match-row{grid-template-columns:1fr auto 1fr}.match-row .date,.match-row .meta{display:none}.match-row .team{font-size:1rem}.match-row .result{font-size:1.35rem}
}
</style>
"""


def html(markup: str) -> None:
    st.html(re.sub(r">\s*\n\s*<", "><", translate_markup(markup.strip())))


# ------------------------------------------------------------------- components
BAR_SLOT: list = []


def brand_bar(page: str, detail: str | None) -> None:
    here = f"{t(page)}" + (f" · {detail}" if detail else "")
    BAR_SLOT[0].html(
        f"""<div class='brandbar'>
        <div class='brand-left'><img src='{brand_uri("al_wasl.png")}' alt='Al Wasl'>
        <div><div class='brand-title'>Al Wasl <b>·</b> First Division Hub</div><div class='brand-sub'>UAE First Division · {t("Temporada")} {SEASON}</div></div></div>
        <div class='brand-right'><div class='here'><i></i>{escape(here)}</div></div>
        </div>""".replace("\n", "")
    )


def banner(page: str, trail: list[str], show_crumbs: bool = True) -> None:
    number, _, subtitle = PAGES[page]
    mark = f"<img class='watermark' src='{brand_uri('al_wasl.png')}' alt=''>" if len(trail) == 1 else ""
    if show_crumbs:
        app_breadcrumbs(page, trail)
    html(
        f"""<div class='banner'><div><div class='kicker'>{t('Sección')} {number} · Al Wasl Football Intelligence</div><h1>{escape(trail[-1] if len(trail) > 1 else page)}</h1><p>{escape(subtitle)}</p></div>
        <div class='num'>{number}</div>{mark}</div>"""
    )


def section(title: str, hint: str = "") -> None:
    small = f"<small>{escape(hint)}</small>" if hint else ""
    html(f"<div class='section'><h2>{escape(title)}</h2>{small}</div>")


def kpis(items: list[tuple[str, object, str]]) -> None:
    cells = "".join(f"<div class='kpi' style='--k:{color}'><label>{escape(label)}</label><div>{value}</div></div>" for label, value, color in items)
    html(f"<div class='kpis' style='--n:{len(items)}'>{cells}</div>")


def go(**state: object) -> None:
    st.session_state.update(state)


def open_player(player_id: str, origin: str = "Catálogo") -> None:
    st.session_state.update(page="Jugadores", player_id=player_id, player_origin=origin, player_scroll_top=True)


def return_from_player() -> None:
    """Return to the screen that opened the player profile."""
    origin = str(st.session_state.get("player_origin", "Catálogo"))
    destination = {"Clasificación": "Clasificación", "Equipos": "Equipos", "Partidos": "Partidos"}.get(origin, "Jugadores")
    st.session_state.update(page=destination, player_id=None, player_origin=None, player_scroll_top=True)


def app_breadcrumbs(page: str, trail: list[str]) -> None:
    """Clickable trail shared by every app screen, with the current item as text."""
    reset = {"player_id": None, "player_origin": None, "player_scroll_top": True}
    items: list[tuple[str, str | None]] = [
        ("UAE First Division", "Clasificación"),
        (SEASON, "Clasificación"),
        (scope_label(), "Partidos"),
    ]
    if len(trail) > 1:
        items.extend([(page, page), (str(trail[-1]), None)])
    else:
        items.append((page, None))
    widths: list[float] = []
    for label, _ in items:
        widths.extend([max(0.55, min(1.7, len(label) / 11)), 0.07])
    columns = st.columns(widths[:-1], gap="small", vertical_alignment="center")
    for index, (label, destination) in enumerate(items):
        column = columns[index * 2]
        with column:
            if destination is None:
                html(f"<div class='crumb-current'>{escape(t(label))}</div>")
            else:
                st.button(t(label), key=f"crumb-{page}-{index}", on_click=go, kwargs={"page": destination, **reset})
        if index < len(items) - 1:
            with columns[index * 2 + 1]:
                html("<div class='crumb-sep'>›</div>")


def scroll_to_top_if_needed() -> None:
    """Streamlit reruns preserve browser scroll; reset it when navigating into or out of a profile."""
    if st.session_state.pop("player_scroll_top", False):
        components.html("<script>window.parent.scrollTo({top: 0, behavior: 'instant'});</script>", height=0, width=0)


# ------------------------------------------------------------------------ pages
def club_lookup(clubs: pd.DataFrame) -> dict[str, pd.Series]:
    return {row.club_id: row for _, row in clubs.iterrows()}


def standings_table(standings: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    head = "".join(f"<div class='pc'>{label}</div>" for label in ["#", "Club", "PJ", "G", "E", "P", "GF", "GC", "DG", "Pts"])
    head = f"<div class='prow phead'>{head}</div>"
    rows = []
    for _, row in standings.iterrows():
        gd_class = "pos-up" if row.GD > 0 else "neg" if row.GD < 0 else "dim"
        cells = (
            f"<div class='pc rank'>{row['#']}</div>"
            f"<div class='pc club'>{crest(club_map.get(row.club_id), 38)}<span>{escape(row.Club)}</span></div>"
            f"<div class='pc'>{row.P}</div><div class='pc'>{row.W}</div><div class='pc'>{row.D}</div><div class='pc'>{row.L}</div>"
            f"<div class='pc'>{row.GF}</div><div class='pc'>{row.GA}</div><div class='pc {gd_class}'>{row.GD:+d}</div>"
            f"<div class='pc pts'>{row.Pts}</div>"
        )
        rows.append(f"<div class='prow{' lead' if row['#'] == 1 else ''}'>{cells}</div>")
    html(f"<div class='scroll-x'><div class='ptable'>{head}{''.join(rows)}</div></div>")


def standings_evolution(matches: pd.DataFrame, all_clubs: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the table after each available matchday for a position timeline."""
    weeks = sorted(pd.to_numeric(matches["week_no"], errors="coerce").dropna().astype(int).unique())
    rows = []
    for week in weeks:
        running = build_standings(matches[pd.to_numeric(matches["week_no"], errors="coerce").le(week)], all_clubs)
        for item in running.itertuples(index=False):
            rows.append({"Jornada": week, "club_id": str(item.club_id), "Club": item.Club, "Posición": int(getattr(item, "_0"))})
    return pd.DataFrame(rows)


def render_position_evolution(data: dict[str, pd.DataFrame], standings: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    """Bumpy-style standings chart, highlighting no more than five chosen clubs."""
    evolution = standings_evolution(data["matches"], data["clubs"])
    if evolution.empty or evolution["Jornada"].nunique() < 2:
        st.info(t("La evolución de posiciones aparecerá cuando haya al menos dos jornadas disputadas."))
        return
    default_ids = standings.head(5)["club_id"].astype(str).tolist()
    if st.session_state.get("bumpy_context_week") != st.session_state.get("matchday"):
        st.session_state["bumpy_clubs"] = default_ids
        st.session_state["bumpy_context_week"] = st.session_state.get("matchday")
    ordered_ids = standings["club_id"].astype(str).tolist()
    selected_ids = st.multiselect(
        t("Comparar equipos"), ordered_ids, key="bumpy_clubs", max_selections=5,
        format_func=lambda club_id: str(club_map[str(club_id)].club_name),
        help=t("Máximo cinco equipos para mantener el gráfico legible."),
    )
    if not selected_ids:
        st.info(t("Selecciona entre uno y cinco equipos para comparar su posición."))
        return
    palette = ["#ae7800", "#256abf", "#148a54", "#c85d24", "#8b5bb8"]
    colors = {str(club_id): palette[index] for index, club_id in enumerate(selected_ids)}
    legend = "".join(
        f"<div class='bumpy-team' style='--bc:{colors[str(club_id)]}'>{crest(club_map[str(club_id)], 22)}<i></i>{escape(str(club_map[str(club_id)].club_name))}</div>"
        for club_id in selected_ids
    )
    html(f"<div class='bumpy-legend'>{legend}</div>")
    weeks = sorted(evolution["Jornada"].unique().tolist())
    team_count = max(len(club_map), int(evolution["Posición"].max()))
    background = alt.Chart(evolution).mark_line(color="#303842", opacity=0.55, strokeWidth=1.2).encode(
        x=alt.X("Jornada:O", sort=weeks, title=t("Jornada")),
        y=alt.Y("Posición:Q", title=t("Posición"), scale=alt.Scale(domain=[team_count + 0.5, 0.5]), axis=alt.Axis(values=list(range(1, team_count + 1)))),
        detail="club_id:N",
    )
    muted_points = alt.Chart(evolution).mark_point(color="#303842", opacity=0.7, filled=True, size=22).encode(
        x=alt.X("Jornada:O", sort=weeks), y=alt.Y("Posición:Q", scale=alt.Scale(domain=[team_count + 0.5, 0.5])), detail="club_id:N"
    )
    highlighted = evolution[evolution["club_id"].isin([str(item) for item in selected_ids])]
    scale = alt.Scale(domain=list(colors), range=list(colors.values()))
    highlights = alt.Chart(highlighted).mark_line(strokeWidth=3.2, point=alt.OverlayMarkDef(filled=True, size=90)).encode(
        x=alt.X("Jornada:O", sort=weeks), y=alt.Y("Posición:Q", scale=alt.Scale(domain=[team_count + 0.5, 0.5])),
        color=alt.Color("club_id:N", scale=scale, legend=None), detail="club_id:N",
        tooltip=[alt.Tooltip("Club:N", title=t("Club")), alt.Tooltip("Jornada:Q", title=t("Jornada")), alt.Tooltip("Posición:Q", title=t("Posición"))],
    )
    latest = highlighted[highlighted["Jornada"].eq(max(weeks))]
    labels = alt.Chart(latest).mark_text(align="left", dx=9, dy=-10, fontWeight=700, fontSize=11).encode(
        x=alt.X("Jornada:O", sort=weeks), y=alt.Y("Posición:Q", scale=alt.Scale(domain=[team_count + 0.5, 0.5])),
        color=alt.Color("club_id:N", scale=scale, legend=None), text="Club:N",
    )
    st.altair_chart(
        alt.layer(background, muted_points, highlights, labels).properties(height=430).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
            labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
        ),
        width="stretch",
    )


def ranking_cards(
    players: pd.DataFrame,
    club_map: dict[str, pd.Series],
    value_column: str,
    value_label: str,
    color: str,
    value_suffix: str = "",
    columns: int = 5,
    key_prefix: str = "ranking",
) -> None:
    """Render compact player rankings with the same official identity details."""
    if players.empty:
        html("<div class='empty'>No hay registros suficientes para este ranking en el periodo seleccionado.</div>")
        return
    for start in range(0, len(players), columns):
        card_columns = st.columns(columns, gap="small")
        window = players.iloc[start : start + columns]
        for column, (rank, (_, p)) in zip(card_columns, enumerate(window.iterrows(), start=start + 1)):
            club = club_map.get(p.club_id)
            birth_text = birth_label(p.get("Nacimiento"), "Sin dato")
            value = p.get(value_column, 0)
            value_text = f"{int(value):,}{value_suffix}".replace(",", ".")
            card = (
                f"<div class='card ranking' style='--r:{color}'><span class='rank-no'>{rank}</span><div class='rank-main'>"
                f"<div class='rank-photo'>{portrait(p)}</div><div class='rank-info'><div class='rank-name'>{escape(str(p.shortname_en))}</div>"
                f"<div class='rank-club'>{crest(club, 18)}<span>{escape(str(p.club_name))}</span>{pos_badge(p.position)}</div></div></div>"
                f"<div class='rank-foot'><div class='rank-age'>Nacimiento<b>{escape(str(birth_text))}</b></div>"
                f"<div class='rank-value'>{value_text}<small>{escape(value_label)}</small></div></div></div>"
            )
            with column:
                html(card)
                st.button(
                    t("Ver ficha del jugador"),
                    key=f"{key_prefix}_{p.player_id}",
                    on_click=open_player,
                    args=(str(p.player_id), "Clasificación"),
                )


def render_player_rankings(
    data: dict[str, pd.DataFrame],
    player_totals: pd.DataFrame,
    club_map: dict[str, pd.Series],
    title: str = "Rankings",
    hint: str = "Rendimiento individual · foto, club, posición, nacimiento y métrica oficial UAEFA",
    key_prefix: str = "ranking",
) -> None:
    """Render the same five official player leaderboards in league or club context."""
    rankings = player_totals.copy()
    if "Edad" not in rankings:
        reference_date = data["matches"]["match_date"].max() if not data["matches"].empty else None
        rankings["Edad"] = rankings["birth_date_official"].map(lambda value: age_at_date(value, reference_date))
    if "Nacimiento" not in rankings:
        reference_date = data["matches"]["match_date"].max() if not data["matches"].empty else None
        rankings["Nacimiento"] = rankings["birth_date_official"].map(lambda value: birth_year_age_label(value, reference_date))
    section(title, hint)
    minutes_tab, youngest_tab, goals_tab, yellow_tab, red_tab = st.tabs(
        [t(label) for label in ["Más minutos", "Más jóvenes", "Goles", "Amarillas", "Rojas"]]
    )
    with minutes_tab:
        ranking_cards(rankings[rankings["Minutes"].gt(0)].sort_values(["Minutes", "Matches"], ascending=False).head(10), club_map, "Minutes", t("Minutos"), "#4c9aff", "'", key_prefix=f"{key_prefix}_minutes")
    with youngest_tab:
        ranking_cards(rankings[rankings["Minutes"].gt(0) & rankings["Edad"].notna()].sort_values(["Edad", "Minutes"], ascending=[True, False]).head(10), club_map, "Minutes", t("Minutos"), "#2fd27a", "'", key_prefix=f"{key_prefix}_youngest")
    with goals_tab:
        ranking_cards(rankings[rankings["Goals"].gt(0)].sort_values(["Goals", "Minutes"], ascending=False).head(10), club_map, "Goals", t("Goles"), "#ae7800", key_prefix=f"{key_prefix}_goals")
    with yellow_tab:
        ranking_cards(rankings[rankings["Yellow"].gt(0)].sort_values(["Yellow", "Minutes"], ascending=False).head(10), club_map, "Yellow", t("Amarillas"), "#f5a524", key_prefix=f"{key_prefix}_yellow")
    with red_tab:
        ranking_cards(rankings[rankings["Red"].gt(0)].sort_values(["Red", "Minutes"], ascending=False).head(10), club_map, "Red", t("Rojas"), "#ff5c6c", key_prefix=f"{key_prefix}_red")


def render_overview(data: dict[str, pd.DataFrame], standings: pd.DataFrame, player_totals: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    brand_bar("Clasificación", None)
    banner("Clasificación", ["Clasificación"])
    goals = int((data["events"]["event_type"] == "goal").sum())
    kpis([
        ("Partidos", len(data["matches"]), "#ffd21f"),
        ("Goles", goals, "#ff5c6c"),
        ("Media por partido", f"{goals / max(len(data['matches']), 1):.2f}", "#2fd27a"),
        ("Jugadores", len(data["players"]), "#4c9aff"),
    ])
    section("Clasificación provisional", f"Acumulada hasta {scope_label()}")
    standings_table(standings, club_map)
    section("Evolución de posiciones", "Top 5 de la jornada por defecto · compara hasta cinco equipos")
    render_position_evolution(data, standings, club_map)
    render_player_rankings(data, player_totals, club_map, key_prefix="league_ranking")


def match_label(match: pd.Series) -> str:
    return f"{match.home_club_name} {match.home_score}-{match.away_score} {match.away_club_name}"


def event_cell(event: pd.Series, side: str) -> str:
    kind = event["event_type"]
    if kind == "goal":
        icon, body, extra = "<span class='ic ball'>⚽</span>", f"<b>{escape(str(event['player_name']))}</b>", " goal"
    elif kind == "ycard":
        icon, body, extra = "<span class='ic y'></span>", escape(str(event["player_name"])), ""
    elif kind == "rcard":
        icon, body, extra = "<span class='ic r'></span>", escape(str(event["player_name"])), ""
    else:
        icon = "<span class='ic sub'>⇄</span>"
        body = f"<span><b>{escape(str(event['in_player_name']))}</b><small>{'for' if is_english() else 'por'} {escape(str(event['player_name']))}</small></span>"
        extra = ""
    inner = f"{body}{icon}" if side == "h" else f"{icon}{body}"
    return f"<div class='cell {side}{extra}'>{inner}</div>"


def timeline_html(events: pd.DataFrame) -> str:
    rows = []
    events = events.assign(minute_num=to_number(events["minute"])).sort_values(["minute_num", "event_order"])
    for _, event in events.iterrows():
        home = event["club_side"] == "H"
        left = event_cell(event, "h") if home else "<div class='cell empty'></div>"
        right = "<div class='cell empty'></div>" if home else event_cell(event, "a")
        rows.append(f"<div class='ev'>{left}<div class='min'>{escape(str(event['minute']))}'</div>{right}</div>")
    return f"<div class='tl'>{''.join(rows)}</div>" if rows else "<div class='empty'>Sin eventos registrados.</div>"


def formation_key(value: object) -> int:
    digits = re.findall(r"\d+", str(value))
    return int(digits[0]) if digits else 0


def pitch_html(roster: pd.DataFrame, minutes_out: dict[str, str]) -> str:
    lines = []
    starters = roster[roster["started"]].copy()
    starters["fkey"] = starters["formation_position"].map(formation_key)
    for code in POSITION_LINES:
        group = starters[starters["position"].eq(code)].sort_values(["fkey", "dorsal"])
        if group.empty:
            continue
        players = []
        for _, p in group.iterrows():
            captain = "<span class='cap'>C</span>" if p["captain"] else ""
            out = f"<span class='out'>↓{minutes_out[p.player_id]}'</span>" if p.player_id in minutes_out else ""
            birth_text = birth_label(p.get("Nacimiento"))
            birth_markup = f"<small>{escape(str(birth_text))}</small>" if birth_text else ""
            players.append(
                f"<div class='pl'><div class='av'>{portrait(p, 'round')}<span class='num'>{escape(str(p['dorsal']))}</span>{captain}{out}</div>"
                f"<div class='pn'><span class='player-name'>{escape(str(p['shortname_en']))}</span>{birth_markup}</div></div>"
            )
        lines.append(f"<div class='line'>{''.join(players)}</div>")
    return f"<div class='pitch'>{''.join(lines)}</div>"


def bench_html(roster: pd.DataFrame) -> str:
    subs = roster[~roster["started"]].sort_values("dorsal", key=lambda s: pd.to_numeric(s, errors="coerce"))
    cells = []
    for _, p in subs.iterrows():
        entered = f"<span class='dn'>↑{escape(str(p['minute_in']))}'</span>" if p["has_played"] and not pd.isna(p["minute_in"]) else ""
        birth_text = birth_label(p.get("Nacimiento"))
        birth_markup = f" · {escape(str(birth_text))}" if birth_text else ""
        cells.append(
            f"<div class='bn{' played' if p['has_played'] else ''}'><div class='av'>{portrait(p, 'round')}</div>"
            f"<div class='t'><b>{escape(str(p['shortname_en']))}</b><small>#{escape(str(p['dorsal']))} · {pos_badge(p['position'])}{birth_markup}</small></div>{entered}</div>"
        )
    return f"<div class='bench'>{''.join(cells)}</div>"


def render_matches(data: dict[str, pd.DataFrame], club_map: dict[str, pd.Series]) -> None:
    matches = data["matches"].sort_values(["match_date", "match_time", "match_id"]).reset_index(drop=True)
    selected_id = st.session_state.get("match_id")
    if selected_id not in set(matches["match_id"]):
        selected_id = matches.iloc[0]["match_id"]
    match = matches[matches["match_id"].eq(selected_id)].iloc[0]
    brand_bar("Partidos", match_label(match))
    banner("Partidos", ["Partidos", match_label(match)])

    section(scope_label(), "Resultados y acceso a cada acta")
    for _, row in matches.iterrows():
        home, away = club_map.get(str(row.home_club_id)), club_map.get(str(row.away_club_id))
        html(
            f"""<div class='card match-row{' sel' if row.match_id == selected_id else ''}'>
            <div class='date'>{escape(str(row.match_date))}<br>{escape(str(row.match_time))}</div>
            <div class='team home'><span>{escape(str(row.home_club_name))}</span>{crest(home, 42)}</div>
            <div class='result'>{row.home_score}<i>:</i>{row.away_score}</div>
            <div class='team'>{crest(away, 42)}<span>{escape(str(row.away_club_name))}</span></div>
            <div class='meta'>{escape(str(row.playground))}</div></div>"""
        )
        st.button(
            t("Acta abierta") if row.match_id == selected_id else t("Abrir acta"),
            key=f"match_{row.match_id}",
            type="primary" if row.match_id == selected_id else "secondary",
            on_click=go,
            kwargs={"match_id": row.match_id},
        )

    home, away = club_map[str(match.home_club_id)], club_map[str(match.away_club_id)]
    events = data["events"][data["events"]["match_id"].eq(match.match_id)]
    players = data["players"].set_index("player_id")
    goal_lines = {"H": [], "A": []}
    for _, goal in events[events["event_type"].eq("goal")].sort_values("event_order").iterrows():
        goal_lines[goal["club_side"]].append(f"⚽ {escape(str(goal['player_name']))} {escape(str(goal['minute']))}'")
    html(
        f"""<div class='board' style='margin-top:1.4rem'><div class='row'>
        <div class='team'>{crest(home, 116)}<h3>{escape(str(match.home_club_name))}</h3><div class='scorers'>{'<br>'.join(goal_lines['H'])}</div></div>
        <div class='mid'><div class='when'>{t('Jornada')} {escape(str(match.week_no))} · {escape(str(match.match_date))} · {escape(str(match.match_time))}</div>
        <div class='big'>{match.home_score}<i>:</i>{match.away_score}</div>
        <div class='info'><span class='chip y'>HT {match.home_score_h1}-{match.away_score_h1}</span><span class='chip'>{escape(str(match.playground))}</span><span class='chip'>{t('Asistencia')} {escape(str(match.attendance))}</span></div></div>
        <div class='team'>{crest(away, 116)}<h3>{escape(str(match.away_club_name))}</h3><div class='scorers'>{'<br>'.join(goal_lines['A'])}</div></div></div></div>"""
    )

    section("Cronología", "Eventos oficiales del acta")
    html(timeline_html(events))

    section("Alineaciones", "Once inicial sobre el campo y banquillo")
    appearances = data["appearances"][data["appearances"]["match_id"].eq(match.match_id)].merge(
        data["players"][["player_id", "shortname_en", "photo_file", "birth_date_official"]], on="player_id", how="left"
    )
    appearances["Edad"] = appearances["birth_date_official"].map(lambda value: age_at_date(value, match.match_date))
    appearances["Nacimiento"] = appearances["birth_date_official"].map(lambda value: birth_year_age_label(value, match.match_date))
    subs_out = events[events["event_type"].eq("subs")].set_index("player_id")["minute"].astype(str).to_dict()
    left, right = st.columns(2, gap="large")
    for column, club_id, club in ((left, str(match.home_club_id), home), (right, str(match.away_club_id), away)):
        roster = appearances[appearances["club_id"].eq(club_id)]
        with column:
            html(f"<div class='teamhead'>{crest(club, 44)}<h3>{escape(str(club['club_name']))}</h3></div>")
            html(pitch_html(roster, subs_out))
            html(bench_html(roster))

    section("Cuerpo técnico", "Staff registrado en el acta")
    left, right = st.columns(2, gap="large")
    for column, club_id, club in ((left, str(match.home_club_id), home), (right, str(match.away_club_id), away)):
        staff = data["staff"][(data["staff"]["match_id"].eq(match.match_id)) & (data["staff"]["club_id"].eq(club_id))].sort_values("role_order")
        cells = "".join(f"<div class='sc2'><small>{escape(str(s.role))}</small><b>{escape(str(s.name_en))}</b></div>" for s in staff.itertuples())
        with column:
            html(f"<div class='teamhead'>{crest(club, 34)}<h3 style='font-size:1.25rem'>{escape(str(club['club_name']))}</h3></div><div class='staff'>{cells}</div>")


def player_card(p: pd.Series, club_map: dict[str, pd.Series], show_dorsal: bool = True) -> str:
    club = club_map.get(p.club_id)
    _, position_color = POSITIONS.get(str(p.get("position", "")).strip(), ("", "#8b95a3"))
    dorsal = f"<span class='dorsal'>{escape(str(p.dorsal))}</span>" if show_dorsal and not pd.isna(p.dorsal) else ""
    stats = (
        f"<div class='stat'><b>{num(p.Matches)}</b><small>PJ</small></div><div class='stat'><b>{num(p.Minutes)}</b><small>Min</small></div>"
        f"<div class='stat g'><b>{p.Goals}</b><small>Goles</small></div><div class='stat y'><b>{p.Yellow}</b><small>TA</small></div><div class='stat r'><b>{p.Red}</b><small>TR</small></div>"
    )
    value = market_value(p.get("market_value_current_eur"))
    enrichment = f"<span class='chip ext'>💰 {escape(value)}</span>" if value else ""
    birth_text = birth_label(p.get("Nacimiento"))
    birth_markup = f"<span class='age-inline'>{escape(birth_text)}</span>" if birth_text else ""
    elo_orb = player_elo_orb(p)
    return (
        f"<div class='card pcard' style='--pos-c:{position_color}'><div class='pc-head'><div class='thumb'>{portrait(p)}{dorsal}</div>"
        f"<div class='info'><div class='nm'>{escape(str(p.shortname_en))}</div>"
        f"<div class='meta'>{crest(club, 18)}<span>{escape(str(p.club_name))}</span>{birth_markup}</div><div class='tags'>{identity_chips(p)}{enrichment}</div></div>{elo_orb}</div>"
        f"<div class='stats'>{stats}</div></div>"
    )


def percentage(numerator: int, denominator: int) -> int:
    return round((numerator / denominator) * 100) if denominator else 0


def availability_cards(summary: dict[str, int]) -> None:
    """Show league availability and the same measures relative to call-ups."""
    total = summary["total_matches"]
    called = summary["called"]
    total_minutes = total * 90
    called_minutes = called * 90
    if is_english():
        details = [
            f"{called} of {total} league matches",
            f"{percentage(summary['played'], called)}% of selections · {summary['played']} of {called}",
            f"{percentage(summary['starts'], called)}% of selections · {summary['starts']} of {called}",
            f"{percentage(summary['minutes'], called_minutes)}% of selected-player minutes · {summary['minutes']}' of {called_minutes}'",
        ]
    else:
        details = [
            f"{called} de {total} partidos de liga",
            f"{percentage(summary['played'], called)}% de convocatorias · {summary['played']} de {called}",
            f"{percentage(summary['starts'], called)}% de convocatorias · {summary['starts']} de {called}",
            f"{percentage(summary['minutes'], called_minutes)}% de minutos convocado · {summary['minutes']}' de {called_minutes}'",
        ]
    items = [
        (t("Convocado"), str(called), percentage(called, total), details[0], "#ffd21f"),
        (t("Partidos jugados"), str(summary["played"]), percentage(summary["played"], total), details[1], "#4c9aff"),
        (t("Partidos titular"), str(summary["starts"]), percentage(summary["starts"], total), details[2], "#2fd27a"),
        (t("Minutos jugados"), f"{summary['minutes']}'", percentage(summary["minutes"], total_minutes), details[3], "#ff8a54"),
    ]
    cards = "".join(
        f"<div class='availability-card' style='--a:{color}'><label>{label}</label><b>{value}</b>"
        f"<span class='main-rate'>{league_rate}% {t('del total de liga')}</span><small>{detail}</small></div>"
        for label, value, league_rate, detail, color in items
    )
    html(f"<div class='availability'>{cards}</div>")


def render_player_interval_chart(intervals: pd.DataFrame, event_label: str, colors: list[str]) -> None:
    """Render home/away event timing with only non-zero labels shown."""
    if intervals["Eventos"].sum() == 0:
        message = (
            f"No {event_label.lower()} recorded in the selected period."
            if is_english()
            else f"No hay {event_label.lower()} registradas en el periodo seleccionado."
        )
        html(f"<div class='empty'>{message}</div>")
        return
    bars = alt.Chart(intervals).mark_bar(cornerRadius=7, size=24).encode(
        x=alt.X("Tramo:O", sort=INTERVAL_LABELS, title=t("Tramo")),
        xOffset=alt.XOffset("Condición:N", sort=["Local", "Visitante"]),
        y=alt.Y("Eventos:Q", title=event_label, axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Condición:N", scale=alt.Scale(domain=["Local", "Visitante"], range=colors), title=None),
        tooltip=[alt.Tooltip("Tramo:O", title=t("Tramo")), alt.Tooltip("Condición:N", title="Home / Away" if is_english() else "Condición"), alt.Tooltip("Eventos:Q", title=event_label)],
    )
    labels = alt.Chart(intervals[intervals["Eventos"].gt(0)]).mark_text(dy=-9, color="#252a2f", fontWeight=700).encode(
        x=alt.X("Tramo:O", sort=INTERVAL_LABELS), xOffset=alt.XOffset("Condición:N", sort=["Local", "Visitante"]),
        y="Eventos:Q", text="Eventos:Q",
    )
    st.altair_chart(
        alt.layer(bars, labels).properties(height=280).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
            labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
        ),
        width="stretch",
    )


def render_player_actions(data: dict[str, pd.DataFrame], player: pd.Series, appearances: pd.DataFrame) -> None:
    """Official per-player availability, scoring, discipline and substitution analysis."""
    summary = player_availability(appearances, data["matches"], str(player.club_id))
    section("Acciones", "Disponibilidad, producción y disciplina oficial UAEFA")
    availability_cards(summary)
    goals_tab, yellow_tab, red_tab, substitutions_tab = st.tabs([t(label) for label in ["Goles", "Amarillas", "Rojas", "Cambios"]])
    with goals_tab:
        st.caption(t("GOLES POR TRAMOS DE 15' · LOCAL Y VISITANTE"))
        render_player_interval_chart(
            player_event_intervals(data["events"], data["matches"], player.player_id, "goal"), t("Goles"), ["#2fd27a", "#4c9aff"]
        )
    with yellow_tab:
        st.caption(t("TARJETAS AMARILLAS POR TRAMOS DE 15' · LOCAL Y VISITANTE"))
        render_player_interval_chart(
            player_event_intervals(data["events"], data["matches"], player.player_id, "ycard"), t("Amarillas"), ["#ffd21f", "#f5a524"]
        )
    with red_tab:
        st.caption(t("TARJETAS ROJAS POR TRAMOS DE 15' · LOCAL Y VISITANTE"))
        render_player_interval_chart(
            player_event_intervals(data["events"], data["matches"], player.player_id, "rcard"), t("Rojas"), ["#ff5c6c", "#ff8a97"]
        )
    with substitutions_tab:
        substitutions = player_substitutions(data["events"], data["matches"], player.player_id)
        if substitutions.empty:
            html(f"<div class='empty'>{t('Sin cambios que involucren al jugador en el periodo seleccionado.')}</div>")
            return
        st.caption(t("MINUTOS DE ENTRADA Y SALIDA"))
        chart_data = substitutions.groupby(["Minuto", "Acción"], as_index=False).size().rename(columns={"size": "Cambios"})
        bars = alt.Chart(chart_data).mark_bar(cornerRadius=7, size=28).encode(
            x=alt.X("Minuto:O", sort=sorted(chart_data["Minuto"].unique()), title=t("Minuto")),
            xOffset=alt.XOffset("Acción:N", sort=["Entra", "Sale"]),
            y=alt.Y("Cambios:Q", title=t("Cambios"), axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("Acción:N", scale=alt.Scale(domain=["Entra", "Sale"], range=["#2fd27a", "#ff5c6c"]), title=None),
            tooltip=[alt.Tooltip("Minuto:O", title=t("Minuto")), alt.Tooltip("Acción:N", title=t("Acción")), alt.Tooltip("Cambios:Q", title=t("Cambios"))],
        )
        labels = alt.Chart(chart_data).mark_text(dy=-9, color="#252a2f", fontWeight=700).encode(
            x=alt.X("Minuto:O", sort=sorted(chart_data["Minuto"].unique())), xOffset=alt.XOffset("Acción:N", sort=["Entra", "Sale"]),
            y="Cambios:Q", text="Cambios:Q",
        )
        st.altair_chart(
            alt.layer(bars, labels).properties(height=260).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
                labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
            ),
            width="stretch",
        )
        section("Matriz de cambios", "Entrada o salida y jugador relacionado")
        header = "".join(f"<div class='pc'>{t(label)}</div>" for label in ["Fecha", "Partido", "Sede", "Min.", "Acción", "Relación"])
        rows = []
        for item in substitutions.itertuples(index=False):
            action_color = "#2fd27a" if item.Acción == "Entra" else "#ff5c6c"
            rows.append(
                f"<div class='hrow'><div class='pc'>{escape(str(item.Fecha))}</div><div class='pc'>{escape(item.Partido)}</div>"
                f"<div class='pc'>{escape(item.Condición)}</div><div class='pc'>{item.Minuto}'</div>"
                f"<div class='pc' style='color:{action_color}'>{escape(item.Acción)}</div><div class='pc'>{escape(item.Relación)}</div></div>"
            )
        html(f"<div class='hrow phead'>{header}</div>{''.join(rows)}")


def render_teams(data: dict[str, pd.DataFrame], standings: pd.DataFrame, player_totals: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    clubs = data["clubs"].sort_values("club_name").reset_index(drop=True)
    selected_id = st.session_state.get("club_id")
    if selected_id not in set(clubs["club_id"]):
        selected_id = clubs.iloc[0]["club_id"]
    club = club_map[selected_id]
    brand_bar("Equipos", str(club.club_name))
    banner("Equipos", ["Equipos", str(club.club_name)])

    section(
        f"{len(clubs)} teams" if is_english() else f"Los {len(clubs)} clubes",
        "Choose a club to open its profile" if is_english() else "Elige un club para abrir su ficha",
    )
    for start in range(0, len(clubs), 7):
        columns = st.columns(7, gap="small")
        for column, (_, row) in zip(columns, clubs.iloc[start : start + 7].iterrows()):
            with column:
                html(f"<div class='card ctile{' sel' if row.club_id == selected_id else ''}'>{crest(row, 64)}<b>{escape(str(row.club_name))}</b></div>")
                st.button(
                    t("Abierto") if row.club_id == selected_id else t("Ver club"),
                    key=f"club_{row.club_id}",
                    type="primary" if row.club_id == selected_id else "secondary",
                    on_click=go,
                    kwargs={"club_id": row.club_id},
                )

    standing = standings[standings["club_id"].eq(selected_id)].iloc[0]
    html(
        f"""<div class='banner' style='margin-top:1.4rem'><div style='display:flex;align-items:center;gap:1.4rem'>{crest_with_elo(club, 120)}
        <div><div class='kicker'>Ficha del club</div><h1 style='margin-bottom:0'>{escape(str(club.club_name))}</h1></div></div></div>"""
    )
    kpis([
        ("Posición", f"#{standing['#']}", "#ffd21f"),
        ("Puntos", standing.Pts, "#ffd21f"),
        ("Goles a favor / en contra", f"{standing.GF} / {standing.GA}", "#ff5c6c"),
        ("Diferencia", f"{standing.GD:+d}", "#2fd27a"),
    ])

    section("Ritmo de gol", "Eventos y marcadores oficiales UAEFA")
    intervals = team_goal_intervals(data, selected_id).set_index("Tramo")
    goal_difference = team_goal_difference(data, selected_id).set_index("Jornada")
    left, right = st.columns(2, gap="large")
    with left:
        st.caption("GOLES POR TRAMOS DE 15' · A FAVOR ARRIBA / EN CONTRA ABAJO")
        interval_chart = intervals.reset_index().rename(columns={"Goles a favor": "A favor", "Goles en contra": "En contra"})
        interval_chart["En contra"] = -interval_chart["En contra"]
        interval_chart = interval_chart.melt(id_vars="Tramo", var_name="Tipo", value_name="Goles")
        interval_chart["Etiqueta"] = interval_chart["Goles"].abs().astype(int).astype(str)
        bars = alt.Chart(interval_chart).mark_bar(cornerRadius=8, size=28).encode(
            x=alt.X("Tramo:O", sort=intervals.index.tolist(), title="Tramo"),
            y=alt.Y("Goles:Q", title=t("Goles"), axis=alt.Axis(format="~s")),
            color=alt.Color(
                "Tipo:N", scale=alt.Scale(domain=["A favor", "En contra"], range=["#2fd27a", "#ff5c6c"]), legend=None
            ),
            tooltip=[alt.Tooltip("Tramo:O", title=t("Tramo")), alt.Tooltip("Tipo:N", title="Type" if is_english() else "Tipo"), alt.Tooltip("Goles:Q", title=t("Goles"))],
        )
        positive_labels = alt.Chart(interval_chart).transform_filter(
            alt.datum.Goles > 0
        ).mark_text(dy=-8, color="#16633f", fontWeight=700).encode(
            x=alt.X("Tramo:O", sort=intervals.index.tolist()), y="Goles:Q", text="Etiqueta:N"
        )
        negative_labels = alt.Chart(interval_chart).transform_filter(
            alt.datum.Goles < 0
        ).mark_text(dy=8, color="#a42f40", fontWeight=700).encode(
            x=alt.X("Tramo:O", sort=intervals.index.tolist()), y="Goles:Q", text="Etiqueta:N"
        )
        st.altair_chart(
            alt.layer(bars, positive_labels, negative_labels).properties(height=300).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
                labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
            ),
            width="stretch",
        )
    with right:
        st.caption("DIFERENCIA POR JORNADA Y ACUMULADA")
        chart_data = goal_difference.reset_index()
        chart_data["Etiqueta jornada"] = chart_data["Diferencia jornada"].astype(int).astype(str)
        chart_data["Etiqueta acumulada"] = chart_data["Diferencia acumulada"].astype(int).astype(str)
        bars = alt.Chart(chart_data).mark_bar(cornerRadius=8, size=28).encode(
            x=alt.X("Jornada:Q", title=t("Jornada"), axis=alt.Axis(values=chart_data["Jornada"].tolist(), labelAngle=0, format=".0f")),
            y=alt.Y("Diferencia jornada:Q", title=t("Diferencia por jornada")),
            color=alt.condition(alt.datum["Diferencia jornada"] >= 0, alt.value("#2fd27a"), alt.value("#ff5c6c")),
            tooltip=[alt.Tooltip("Jornada:Q", title=t("Jornada"), format=".0f"), alt.Tooltip("Diferencia jornada:Q", title=t("Diferencia"))],
        )
        segments = accumulated_difference_segments(chart_data)
        line = alt.Chart(segments).mark_line(strokeWidth=3).encode(
            x=alt.X("Jornada:Q", title=t("Jornada")),
            y=alt.Y("Acumulada:Q", title=t("Diferencia acumulada")),
            detail="segment:N",
            color=alt.Color("Signo:N", scale=alt.Scale(domain=["Positiva", "Negativa"], range=["#2fd27a", "#ff5c6c"]), legend=None),
        )
        points = alt.Chart(chart_data).mark_point(filled=True, size=72).encode(
            x=alt.X("Jornada:Q", title=t("Jornada")),
            y=alt.Y("Diferencia acumulada:Q", title=t("Diferencia acumulada")),
            color=alt.condition(alt.datum["Diferencia acumulada"] > 0, alt.value("#2fd27a"), alt.value("#ff5c6c")),
            tooltip=[alt.Tooltip("Jornada:Q", title=t("Jornada"), format=".0f"), alt.Tooltip("Diferencia acumulada:Q", title=t("Acumulada"))],
        )
        bar_labels = alt.Chart(chart_data).mark_text(color="#252a2f", fontWeight=700).encode(
            x="Jornada:Q", y="Diferencia jornada:Q", text="Etiqueta jornada:N"
        )
        line_labels = alt.Chart(chart_data).mark_text(dx=10, dy=-10, color="#252a2f", fontWeight=700).encode(
            x="Jornada:Q", y="Diferencia acumulada:Q", text="Etiqueta acumulada:N"
        )
        st.altair_chart(
            alt.layer(bars, line, points, bar_labels, line_labels).properties(height=300).configure(
                background="#ffffff"
            ).configure_view(strokeOpacity=0).configure_axis(
                labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
            ),
            width="stretch",
        )
    if len(goal_difference) < 2:
        st.info("Para ver la evolución entre jornadas, selecciona «Todas las jornadas» en el selector superior.")

    squad = player_totals[player_totals["club_id"].eq(selected_id) & player_totals["Squad"].gt(0)]
    squad = squad.sort_values(["Minutes", "Goals", "shortname_en"], ascending=[False, False, True])
    section("Plantilla vista", f"{len(squad)} jugadores en acta · por posición y minutos")
    for code in ("GK", "D", "M", "A"):
        group = squad[squad["position"].eq(code)]
        if group.empty:
            continue
        label, color = POSITIONS[code]
        html(f"<div class='posgroup' style='--c:{color}'>{pos_badge(code)}<h3>{label}</h3><small>{len(group)} jugadores</small></div>")
        for start in range(0, len(group), 3):
            columns = st.columns(3, gap="small")
            for column, (_, p) in zip(columns, group.iloc[start : start + 3].iterrows()):
                with column:
                    html(player_card(p, club_map))
                    st.button(t("Ver ficha"), key=f"team_p_{p.player_id}", on_click=open_player, args=(str(p.player_id), "Equipos"))

    section("Cuerpo técnico", "Banquillo registrado en el acta")
    staff = data["staff"][data["staff"]["club_id"].eq(selected_id)].drop_duplicates("person_id").sort_values("role_order", key=lambda s: pd.to_numeric(s, errors="coerce"))
    cells = "".join(f"<div class='sc2'><small>{escape(str(s.role))}</small><b>{escape(str(s.name_en))}</b></div>" for s in staff.itertuples())
    html(f"<div class='staff' style='grid-template-columns:repeat(4,minmax(0,1fr))'>{cells}</div>")
    render_player_rankings(
        data,
        squad,
        club_map,
        title=f"Rankings · {club.club_name}",
        hint="Rendimiento de la plantilla en el periodo seleccionado",
        key_prefix=f"club_{selected_id}_ranking",
    )


def L(spanish: str, english: str) -> str:
    return english if is_english() else spanish


def fnum(value: float | None, digits: int = 2, signed: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    text = f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    return text if is_english() else text.replace(".", ",")


def tone(value: float | None, eps: float = 1e-4) -> str:
    return "tz" if value is None or pd.isna(value) else "tp" if value > eps else "tn" if value < -eps else "tz"


def fold(title: str, summary: str, body: str) -> str:
    return (
        f"<details class='fold' open><summary><span class='chev'>▸</span><span class='ft'>{title}</span><span class='fs'>{summary}</span>"
        f"<span class='fh' data-open='{L('ocultar', 'hide')}' data-closed='{L('ver', 'show')}'></span></summary><div class='fbody'>{body}</div></details>"
    )


def ifact(label: str, value: str, sub: str = "", cls: str = "tz") -> str:
    return f"<div class='ifact'><span>{label}</span><b class='{cls}'>{value}</b>{f'<em>{sub}</em>' if sub else ''}</div>"


def icard(title: str, sub: str, body: str, span: int = 6, color: str = "#ffd21f", big: str = "", big_sub: str = "", big_cls: str = "tz") -> str:
    head_big = f"<div class='ic-big'><b class='{big_cls}'>{big}</b><small>{big_sub}</small></div>" if big else ""
    return (
        f"<div class='icard' style='--span:{span};--ic:{color}'><div class='ic-head'><div><h3>{title}</h3>{f'<small>{sub}</small>' if sub else ''}</div>{head_big}</div>{body}</div>"
    )


def ifacts(cells: list[str], columns: int = 3) -> str:
    return f"<div class='ifacts' style='--c:{columns}'>{''.join(cells)}</div>"


def cbar(label: str, value: float | None, scale: float, color: str, diverging: bool, text: str) -> str:
    if value is None or pd.isna(value):
        fill = ""
    elif diverging:
        width = min(abs(value) / scale, 1) * 50
        left = 50 if value >= 0 else 50 - width
        fill = f"<i style='left:{left:.1f}%;width:{max(width, 1.5):.1f}%;--col:{color if value >= 0 else '#ff5c6c'}'></i>"
    else:
        fill = f"<i style='left:0;width:{min(max(value, 0) / scale, 1) * 100:.1f}%;--col:{color}'></i>"
    return f"<div class='cbar'><span>{label}</span><div class='tr{' div' if diverging else ''}'>{fill}</div><b class='{tone(value) if diverging else 'tz'}'>{text}</b></div>"


def render_player_season(data: dict[str, pd.DataFrame], player: pd.Series, appearances: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    """Season summary and one poster row per match: venue, rival, result, role, minutes and events."""
    pid = str(player.player_id)
    mine = data["events"][data["events"]["player_id"].astype("string").eq(pid)]
    rows, goals, yellows, reds = [], 0, 0, 0
    appearances = appearances.sort_values(["match_date", "match_time"])
    for _, a in appearances.iterrows():
        home = str(a.home_club_id) == str(a.club_id)
        rival_id = str(a.away_club_id if home else a.home_club_id)
        rival = a.away_club_name if home else a.home_club_name
        goals_for, goals_against = (int(a.home_score), int(a.away_score)) if home else (int(a.away_score), int(a.home_score))
        result = "W" if goals_for > goals_against else "D" if goals_for == goals_against else "L"
        minutes = int(appearance_minutes(pd.DataFrame([a])).iloc[0])
        left = pd.to_numeric(a.minute_out, errors="coerce")
        entered = pd.to_numeric(a.minute_in, errors="coerce")
        if a.started:
            role = L("Titular", "Starter") + (f" · {L('sale', 'off')} {int(left)}'" if not pd.isna(left) and left < 90 else "")
        elif a.has_played:
            role = f"{L('Entra', 'On')} {int(entered)}'" + (f" · {L('sale', 'off')} {int(left)}'" if not pd.isna(left) else "")
        else:
            role = L("No jugó", "Did not play")
        match_events = mine[mine["match_id"].astype(str).eq(str(a.match_id))]
        own = match_events[match_events["event_type"].eq("goal") & match_events["goal_type_id"].astype(str).eq("4")]
        scored = match_events[match_events["event_type"].eq("goal")].shape[0] - own.shape[0]
        y, r = int(match_events["event_type"].eq("ycard").sum()), int(match_events["event_type"].eq("rcard").sum())
        goals += scored
        yellows += y
        reds += r
        icons = "⚽" * scored + ("<span class='chip'>OG</span>" * own.shape[0]) + "<span class='cardico y'></span>" * y + "<span class='cardico r'></span>" * r
        rows.append(
            f"<div class='srow'><span class='j'>J{escape(str(a.week_no))}</span>"
            f"<span class='ha chip {'home' if home else 'away'}'>{L('Casa', 'Home') if home else L('Fuera', 'Away')}</span>"
            f"<span class='rival'>{crest(club_map.get(rival_id), 30)}<span>{escape(str(rival))}</span></span>"
            f"<span class='res'>{goals_for}-{goals_against}<span class='wdl {result}'>{ {'W': L('V', 'W'), 'D': L('E', 'D'), 'L': L('D', 'L')}[result] }</span></span>"
            f"<span class='role'>{role}</span>"
            f"<span class='mbar'><span class='t'><i style='width:{min(minutes / 90 * 100, 100):.0f}%'></i></span><b>{minutes}'</b></span>"
            f"<span class='evs'>{icons}</span></div>"
        )
    played = appearances[appearances["has_played"].astype(bool)]
    total_minutes = int(appearance_minutes(appearances).sum())
    per_match = round(total_minutes / len(played)) if len(played) else 0
    summary_cells = [
        ifact(L("Jugados", "Played"), str(len(played))),
        ifact(L("Titular", "Starts"), str(int(appearances["started"].astype(bool).sum()))),
        ifact(L("Goles", "Goals"), str(goals), cls="tp" if goals else "tz"),
        ifact(L("Tarjetas", "Cards"), f"<span class='cardico y'></span> {yellows} &nbsp;<span class='cardico r'></span> {reds}"),
    ]
    summary = icard(
        L("Resumen", "Summary"), f"{len(appearances)} {L('convocatorias', 'call-ups')}", ifacts(summary_cells, 4),
        span=12, big=f"{total_minutes}'", big_sub=f"{per_match}' {L('por partido', 'per match')}", color="#2fd27a",
    )
    list_head = f"<div class='ic-head'><div><h3>{L('Partidos', 'Matches')}</h3><small>{L('Ordenados por fecha', 'Sorted by date')}</small></div></div>"
    body = (
        f"<div class='season-top'><div class='impact-grid'>{summary}</div></div>"
        f"<div class='icard' style='--ic:#ffd21f'>{list_head}<div style='border-top:1px solid var(--line)'>{''.join(rows) or '<div class=empty-in>' + L('Sin participaciones registradas.', 'No appearances recorded.') + '</div>'}</div></div>"
    )
    html(fold(L("Temporada", "Season"), f"{len(played)} {L('partidos', 'matches')} · {total_minutes}' · {goals} {L('goles', 'goals')}", body))


def render_player_impact(data: dict[str, pd.DataFrame], player: pd.Series) -> None:
    """On/off impact of the player: goals, points, scoreboard minutes, trust, bench and discipline."""
    r = player_impact(data, str(player.player_id), str(player.club_id))
    if not r["pj"]:
        html(fold(L("Impacto en el campo", "On-pitch impact"), "", f"<div class='empty-in'>{L('Aún no ha jugado minutos en el periodo seleccionado.', 'No minutes played yet in the selected period.')}</div>"))
        return
    minutes, pj = int(r["min"]), int(r["pj"])
    onoff_sub = (
        L("con él menos sin él, por 90", "with minus without him, per 90") if r["onoff"] is not None
        else L(f"sin minutos suficientes sin él (mín. {int(r['min_without'])}')", f"not enough minutes without him (min. {int(r['min_without'])}')")
    )
    with_him = icard(
        L("Con él en el campo", "With him on the pitch"), f"{minutes}' · {pj} {L('partidos', 'matches')}",
        ifacts([
            ifact(L("Goles a favor", "Goals for"), str(r["gf"]), cls="tp"),
            ifact(L("Goles en contra", "Goals against"), str(r["gc"]), cls="tn"),
            ifact("On/Off", fnum(r["onoff"], 2, True) if r["onoff"] is not None else "—", onoff_sub, tone(r["onoff"])),
            ifact(L("Puntos a la salida", "Points at exit"), fnum(r["pts_exit_avg"]), f"{L('por partido', 'per match')} · {L('equipo', 'team')} {fnum(r['team_ppg'])}", "tw"),
            ifact(L("Puntos ganados", "Points gained"), fnum(r["pts_gained"], 0, True), f"{fnum(r['pts_gained_avg'], 2, True)} {L('por partido', 'per match')}", tone(r["pts_gained"])),
            ifact(L("Porterías a cero", "Clean sheets"), f"{r['clean_sheets']}/{r['cs_eligible']}", L("partidos de 60' o más", "matches of 60' or more")),
        ]),
        span=7, big=fnum(float(r["pm"]), 0, True), big_sub=f"{fnum(r['dg_on'], 2, True)} {L('por 90', 'per 90')}", big_cls=tone(r["pm"]), color="#2fd27a",
    )
    comparison = icard(
        L("Comparativa", "Comparison"), L("con él / sin él / equipo", "with him / without him / team"),
        "<div class='cmp'>"
        f"<h4>{L('Diferencia de goles por 90', 'Goal difference per 90')}</h4>"
        + cbar(L("Con él", "With him"), r["dg_on"], 1.5, "#2fd27a", True, fnum(r["dg_on"], 2, True))
        + cbar(L("Sin él", "Without him"), r["dg_off"], 1.5, "#2fd27a", True, fnum(r["dg_off"], 2, True))
        + cbar("On/Off", r["onoff"], 1.5, "#2fd27a", True, fnum(r["onoff"], 2, True))
        + f"<div class='cmp-rule'></div><h4>{L('Puntos por partido', 'Points per match')}</h4>"
        + cbar(L("A su salida", "At exit"), r["pts_exit_avg"], 3, "#ffb020", False, fnum(r["pts_exit_avg"]))
        + cbar(L("Media equipo", "Team average"), r["team_ppg"], 3, "#4c9aff", False, fnum(r["team_ppg"]))
        + "</div>",
        span=5, color="#4c9aff",
    )
    state = r["state"]
    total_state = sum(state.values()) or 1
    segments = [("win", L("Ganando", "Winning"), "#2fd27a"), ("draw", L("Empatando", "Drawing"), "#ffb020"), ("loss", L("Perdiendo", "Losing"), "#ff5c6c")]
    dominant = max(segments, key=lambda seg: state[seg[0]])
    top = "".join(f"<span style='flex:{state[key]:.3f}'>{int(state[key])}'</span>" for key, _, _ in segments if state[key] > 0)
    bar = "".join(f"<i style='flex:{state[key]:.3f};background:{color}'>{round(state[key] / total_state * 100)}%</i>" for key, _, color in segments if state[key] > 0)
    legend = "".join(f"<span style='--col:{color}'>{label}</span>" for _, label, color in segments)
    by_state = icard(
        L("Minutos según el marcador", "Minutes by scoreline"), f"{minutes}' {L('en el campo', 'on the pitch')}",
        f"<div class='stack-top'>{top}</div><div class='stack'>{bar}</div><div class='legend2'>{legend}</div>",
        span=6, color="#ffb020", big=f"{round(state[dominant[0]] / total_state * 100)}%", big_sub=dominant[1].lower(), big_cls="tw",
    )
    trust = icard(
        L("Confianza del entrenador", "Coach's trust"), L("uso del jugador", "player usage"),
        ifacts([
            ifact(L("Titularidades", "Starts"), f"{r['starts']}/{r['team_pj']}"),
            ifact(L("Sustituido", "Substituted"), str(r["subbed_off"]), L(f"de {r['starts']} de titular", f"of {r['starts']} starts")),
            ifact(L("Minuto medio de cambio", "Average substitution minute"), f"{fnum(r['sub_minute_avg'], 0)}'" if r["sub_minute_avg"] is not None else "—",
                  "" if r["sub_minute_avg"] is not None else L("nunca sustituido", "never substituted")),
        ]),
        span=6, color="#2fd27a", big=f"{round((r['pct_min'] or 0) * 100)}%", big_sub=L("de los minutos posibles", "of possible minutes"), big_cls="tp",
    )
    bench = r["bench"]
    if bench["n"]:
        bench_body = ifacts([
            ifact(L("Entradas", "Appearances"), str(bench["n"]), f"{int(bench['min'])}' {L('en total', 'in total')}"),
            ifact(L("Goles a favor / en contra", "Goals for / against"), f"{bench['gf']} / {bench['gc']}", cls=tone(bench["gf"] - bench["gc"])),
            ifact(L("Puntos ganados", "Points gained"), fnum(float(bench["pts"]), 0, True), cls=tone(bench["pts"])),
        ])
    else:
        bench_body = f"<div class='empty-in'>{L('No ha entrado como suplente en el periodo seleccionado.', 'No substitute appearances in the selected period.')}</div>"
    bench_card = icard(L("Desde el banquillo", "From the bench"), "", bench_body, span=6, color="#4c9aff")
    discipline = icard(
        L("Disciplina", "Discipline"), f"{r['yellow']} {L('amarillas', 'yellow')} · {r['red']} {L('rojas', 'red')}",
        ifacts([
            ifact(L("Amarillas", "Yellow cards"), str(r["yellow"]), cls="ty"),
            ifact(L("Rojas", "Red cards"), str(r["red"]), cls="tn" if r["red"] else "tz"),
            ifact(L("GC tras su roja", "Goals against after his red"), str(r["gc_after_red"]) if r["red"] else "—", "" if r["red"] else L("sin expulsiones", "no sending-offs")),
        ]),
        span=6, color="#ff5c6c", big=fnum(r["cards_90"]), big_sub=L("tarjetas por 90", "cards per 90"), big_cls="tn" if (r["cards_90"] or 0) > 0 else "tz",
    )
    notice = ""
    if r["small_sample"]:
        notice = (
            f"<div class='sample'><i>!</i><span>{L('Muestra pequeña', 'Small sample')}: {minutes}' {L('de', 'of')} {int(r['min_with'])}' "
            f"{L('mínimos. Las cifras aún pueden moverse mucho con cada partido.', 'minimum. Figures can still swing a lot with every match.')}</span></div>"
        )
    note = (
        f"<p class='foot-note'>ⓘ {L('Partidos del equipo en el periodo seleccionado', 'Team matches in the selected period')} · "
        f"{L('mínimos', 'minimum')} {int(r['min_with'])}' {L('con él y', 'with him and')} {int(r['min_without'])}' {L('sin él para el On/Off', 'without him for On/Off')} · "
        f"{L('sin minutos de descuento; un gol en el minuto de un cambio cuenta para quien sale; los autogoles cuentan para quien se benefician', 'no stoppage minutes; a goal at the minute of a substitution counts for the player leaving; own goals count for the beneficiary')}.</p>"
    )
    summary = f"+/- <b>{fnum(float(r['pm']), 0, True)}</b> · {L('puntos a la salida', 'points at exit')} <b>{fnum(r['pts_exit_avg'])}</b>"
    html(fold(L("Impacto en el campo", "On-pitch impact"), summary, f"{notice}<div class='impact-grid'>{with_him}{comparison}{by_state}{trust}{bench_card}{discipline}</div>{note}"))


def render_player_profile(data: dict[str, pd.DataFrame], player: pd.Series, club_map: dict[str, pd.Series]) -> None:
    club = club_map.get(player.club_id)
    ar = f"<div class='ar'>{escape(str(player.name_ar))}</div>" if isinstance(player.name_ar, str) else ""
    identity = identity_chips(player)
    birth_text = birth_label(player.get("Nacimiento"))
    birth_chip = f"<span class='chip age'>Nacimiento {escape(birth_text)}</span>" if birth_text else ""
    tags = f"{identity}{birth_chip}<span class='chip y'>{escape(str(player.nationality_category))}</span><span class='chip'>{escape(str(player.player_status))}</span><span class='chip'>{escape(str(player.team_en))}</span>"
    dorsal = f"<span class='chip'>Dorsal #{escape(str(player.dorsal))}</span>" if not pd.isna(player.dorsal) else ""
    html(
        f"""<div class='profile'><div>{portrait(player)}</div><div>
        {pos_badge(player.position, full=True)}<h2>{escape(str(player.name_en))}</h2>{ar}
        <div class='clubline'>{crest(club, 44)}<span>{escape(str(player.club_name))}</span></div><div class='tags'>{tags}{dorsal}</div></div></div>"""
    )
    kpis([
        ("Partidos", num(player.Matches), "#4c9aff"),
        ("Titular", num(player.Starts), "#2fd27a"),
        ("Minutos", num(player.Minutes), "#ffd21f"),
        ("Goles", player.Goals, "#ffd21f"),
        ("Amarillas", player.Yellow, "#ffd21f"),
        ("Rojas", player.Red, "#ff5c6c"),
    ])
    value = market_value(player.get("market_value_current_eur"))
    external_metrics = []
    player_elo = player.get("elo_current")
    if player_elo is not None and not pd.isna(player_elo):
        external_metrics.append(("Elo del jugador", int(player_elo), "#4c9aff"))
    if value:
        external_metrics.append(("Valor de mercado", value, "#2fd27a"))
    club_elo = club.get("elo_current") if club is not None else None
    if club_elo is not None and not pd.isna(club_elo):
        external_metrics.append(("Elo del equipo", int(club_elo), "#4c9aff"))
    if external_metrics:
        section("Enriquecimiento validado", "Datos externos · identidad confirmada con UAEFA")
        kpis(external_metrics)
    raw_history = player.get("market_value_history_json")
    try:
        value_history = json.loads(raw_history) if isinstance(raw_history, str) else []
    except json.JSONDecodeError:
        value_history = []
    if value_history:
        history = pd.DataFrame(value_history)
        history["Etiqueta"] = history["value_eur"].map(market_value)
        section("Evolución de valor de mercado", "Datos externos · histórico publicado")
        st.altair_chart(
            alt.layer(
                alt.Chart(history).mark_line(color="#2fd27a", strokeWidth=3, point=alt.OverlayMarkDef(filled=True, size=70)).encode(
                    x=alt.X("year:O", title=t("Año")),
                    y=alt.Y("value_eur:Q", title=t("Euros"), axis=alt.Axis(format="~s")),
                    tooltip=[alt.Tooltip("year:O", title=t("Año")), alt.Tooltip("value_eur:Q", title=t("Valor"), format=",.0f")],
                ),
                alt.Chart(history).mark_text(dy=-12, color="#bff3d5", fontWeight=700).encode(
                    x=alt.X("year:O"), y=alt.Y("value_eur:Q"), text="Etiqueta:N"
                ),
            ).properties(height=245).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
                labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
            ),
            width="stretch",
        )
    raw_elo_history = player.get("elo_history_json")
    try:
        elo_history = json.loads(raw_elo_history) if isinstance(raw_elo_history, str) else []
    except json.JSONDecodeError:
        elo_history = []
    if elo_history:
        history = pd.DataFrame(elo_history)
        history["Etiqueta"] = history["elo"].astype(int).astype(str)
        section("Evolución de Elo", "Datos externos · histórico publicado del jugador")
        st.altair_chart(
            alt.layer(
                alt.Chart(history).mark_line(color="#4c9aff", strokeWidth=3, point=alt.OverlayMarkDef(filled=True, size=70)).encode(
                    x=alt.X("year:O", title=t("Año")), y=alt.Y("elo:Q", title="Elo"),
                    tooltip=[alt.Tooltip("year:O", title=t("Año")), alt.Tooltip("elo:Q", title="Elo")],
                ),
                alt.Chart(history).mark_text(dy=-12, color="#c5dcff", fontWeight=700).encode(
                    x=alt.X("year:O"), y=alt.Y("elo:Q"), text="Etiqueta:N"
                ),
            ).properties(height=245).configure(background="#ffffff").configure_view(strokeOpacity=0).configure_axis(
                labelColor="#62666b", titleColor="#62666b", gridColor="#e1e1da"
            ),
            width="stretch",
        )
    pid = player.player_id
    appearances = data["appearances"][data["appearances"]["player_id"].eq(pid)].merge(data["matches"], on="match_id", how="left")
    render_player_season(data, player, appearances, club_map)
    render_player_impact(data, player)
    render_player_actions(data, player, appearances)


def render_players(data: dict[str, pd.DataFrame], player_totals: pd.DataFrame, club_map: dict[str, pd.Series]) -> None:
    selected = st.session_state.get("player_id")
    if selected and selected in set(player_totals["player_id"]):
        player = player_totals[player_totals["player_id"].eq(selected)].iloc[0]
        brand_bar("Jugadores", str(player.shortname_en))
        banner("Jugadores", ["Jugadores", str(player.shortname_en)])
        origin = str(st.session_state.get("player_origin", "Catálogo"))
        st.button(t("← Volver"), on_click=return_from_player, key="player_back", type="primary", help=f"{t('Volver a')} {t(origin)}")
        render_player_profile(data, player, club_map)
        return

    brand_bar("Jugadores", "Catálogo")
    banner("Jugadores", ["Jugadores", "Catálogo"])
    player_labels = {
        str(row.player_id): f"{row.name_en} · {row.club_name}"
        for row in player_totals.sort_values(["name_en", "club_name"]).itertuples(index=False)
    }

    def select_player() -> None:
        chosen = st.session_state.get("player_picker")
        if chosen:
            open_player(str(chosen))

    with st.container(border=True):
        html("<div class='quick-open'><div><b>Abrir ficha de jugador</b><span>Busca directamente un jugador para consultar su perfil completo.</span></div><i></i></div>")
        st.selectbox(
            t("Abrir ficha de jugador"),
            options=[""] + list(player_labels),
            format_func=lambda player_id: t("Selecciona un jugador...") if not player_id else player_labels[player_id],
            key="player_picker",
            on_change=select_player,
            label_visibility="collapsed",
        )

    # Build a single exploration table so catalogue filters and the scatterplot
    # use the same official playing data and validated external enrichment.
    explorer = player_totals.copy()
    reference_date = pd.to_datetime(data["matches"]["match_date"], errors="coerce").max()
    explorer["Edad"] = explorer["birth_date_official"].map(lambda value: age_at_date(value, reference_date))
    explorer["Nacimiento"] = explorer["birth_date_official"].map(lambda value: birth_year_age_label(value, reference_date))
    explorer["Año de nacimiento"] = pd.to_datetime(explorer["birth_date_official"], errors="coerce").dt.year
    team_elo = data["clubs"][["club_id", "elo_current"]].copy().rename(columns={"elo_current": "Elo equipo"})
    team_elo["club_id"] = team_elo["club_id"].astype(str)
    explorer["club_id"] = explorer["club_id"].astype(str)
    explorer = explorer.merge(team_elo.drop_duplicates("club_id"), on="club_id", how="left")
    explorer["Elo jugador"] = pd.to_numeric(explorer["elo_current"], errors="coerce")
    explorer["Valor de mercado"] = pd.to_numeric(explorer["market_value_current_eur"], errors="coerce")
    explorer["Elo equipo"] = pd.to_numeric(explorer["Elo equipo"], errors="coerce")

    section("Filtros de búsqueda", "Combina perfil, club y rendimiento para localizar jugadores concretos")
    # Keep existing browser sessions compatible with the clearer Spanish defaults.
    for state_key, old_value, new_value in (("pos", "All", "Todas"), ("cat", "All", "Todas"), ("clubf", "All", "Todos"), ("player_status", "All", "Todos")):
        if st.session_state.get(state_key) == old_value:
            st.session_state[state_key] = new_value
    with st.container(border=True):
        html("<div class='filter-shell'><span>EXPLORADOR DE PLANTILLAS</span><b>Filtra y combina criterios sin perder contexto</b></div>")
        primary_filters = st.columns(4, gap="small", vertical_alignment="bottom")
        query = primary_filters[0].text_input(t("Buscar jugador"), placeholder=t("Nombre o apellidos"), key="q")
        position = primary_filters[1].selectbox(
            t("Posición"), ["Todas", "GK", "D", "M", "A"], key="pos",
            format_func=lambda code: {"Todas": t("Todas las posiciones"), "GK": f"GK · {t('Portero')}", "D": f"D · {t('Defensa')}", "M": f"M · {t('Mediocampista')}", "A": f"A · {t('Atacante')}"}[code],
        )
        category = primary_filters[2].selectbox(
            t("Categoría UAEFA"), ["Todas"] + sorted(explorer["nationality_category"].dropna().unique().tolist()), key="cat"
        )
        club_filter = primary_filters[3].selectbox(t("Club"), ["Todos"] + sorted(explorer["club_name"].unique().tolist()), key="clubf")

        detail_filters = st.columns(5, gap="small", vertical_alignment="bottom")
        age_values = explorer["Edad"].dropna()
        birth_year_values = explorer["Año de nacimiento"].dropna()
        if age_values.empty or birth_year_values.empty:
            age_range = None
            detail_filters[0].caption(t("Edad: no publicada todavía"))
        else:
            age_min, age_max = int(age_values.min()), int(age_values.max())
            year_min, year_max = int(birth_year_values.min()), int(birth_year_values.max())

            # Both widgets expose the same official birth-date data. The control
            # last changed becomes the exact filter, while the other remains a
            # synchronized, readable representation of the selected cohort.
            if "age_range" not in st.session_state:
                st.session_state["age_range"] = (age_min, age_max)
            if "birth_year_range" not in st.session_state:
                st.session_state["birth_year_range"] = (year_min, year_max)
            if "birth_filter_driver" not in st.session_state:
                st.session_state["birth_filter_driver"] = "age"

            def sync_birth_year_from_age() -> None:
                low, high = st.session_state["age_range"]
                years = explorer.loc[explorer["Edad"].between(low, high), "Año de nacimiento"].dropna()
                if not years.empty:
                    st.session_state["birth_year_range"] = (int(years.min()), int(years.max()))
                st.session_state["birth_filter_driver"] = "age"

            def sync_age_from_birth_year() -> None:
                low, high = st.session_state["birth_year_range"]
                ages = explorer.loc[explorer["Año de nacimiento"].between(low, high), "Edad"].dropna()
                if not ages.empty:
                    st.session_state["age_range"] = (int(ages.min()), int(ages.max()))
                st.session_state["birth_filter_driver"] = "birth_year"

            # Refresh stale browser state safely after a data update changes the
            # available age or birth-year limits.
            current_age = st.session_state["age_range"]
            current_years = st.session_state["birth_year_range"]
            if current_age[0] < age_min or current_age[1] > age_max:
                st.session_state["age_range"] = (age_min, age_max)
            if current_years[0] < year_min or current_years[1] > year_max:
                st.session_state["birth_year_range"] = (year_min, year_max)

            age_range = detail_filters[0].slider(
                t("Rango de edad"), age_min, age_max, key="age_range", on_change=sync_birth_year_from_age
            )
            birth_year_range = detail_filters[1].slider(
                t("Rango de año de nacimiento"), year_min, year_max,
                key="birth_year_range", on_change=sync_age_from_birth_year
            )
            detail_filters[1].caption(f"{t('Filtros vinculados')} · {t('El último filtro ajustado define la selección exacta; el otro se actualiza automáticamente.')}")
        min_minutes = int(detail_filters[2].number_input(t("Minutos mínimos"), min_value=0, value=0, step=30, key="min_minutes"))
        status_options = ["Todos"] + sorted(explorer["player_status"].dropna().unique().tolist())
        player_status = detail_filters[3].selectbox(t("Estatus"), status_options, key="player_status")
        with detail_filters[4]:
            st.caption(t("DISPONIBILIDAD"))
            played_only = st.checkbox(t("Solo jugadores con minutos"), value=False, key="played_only")

        legend = "".join(pos_badge(code, full=True) for code in ("GK", "D", "M", "A"))
        html(f"<div class='filter-legend'>{legend}</div>")

    filtered = explorer.copy()
    if query:
        filtered = filtered[
            filtered["name_en"].str.contains(query, case=False, na=False)
            | filtered["shortname_en"].str.contains(query, case=False, na=False)
            | filtered["name_en_official"].str.contains(query, case=False, na=False)
        ]
    if position != "Todas":
        filtered = filtered[filtered["position"].eq(position)]
    if category != "Todas":
        filtered = filtered[filtered["nationality_category"].eq(category)]
    if club_filter != "Todos":
        filtered = filtered[filtered["club_name"].eq(club_filter)]
    if age_range is not None:
        if st.session_state.get("birth_filter_driver") == "birth_year":
            filtered = filtered[filtered["Año de nacimiento"].between(*birth_year_range, inclusive="both")]
        else:
            filtered = filtered[filtered["Edad"].between(*age_range, inclusive="both")]
    if min_minutes:
        filtered = filtered[filtered["Minutes"].ge(min_minutes)]
    if player_status != "Todos":
        filtered = filtered[filtered["player_status"].eq(player_status)]
    if played_only:
        filtered = filtered[filtered["Minutes"].gt(0)]
    filtered = filtered.sort_values(["Goals", "Minutes", "Starts", "name_en"], ascending=[False, False, False, True]).reset_index(drop=True)

    with st.expander(t("Glosario · cómo leer una tarjeta de jugador"), expanded=False):
        if filtered.empty:
            st.caption(t("El ejemplo aparecerá al obtener al menos un jugador con los filtros aplicados."))
        else:
            sample, explanation = st.columns([1.05, 1.35], gap="large")
            with sample:
                html(player_card(filtered.iloc[0], club_map))
            with explanation:
                st.markdown(
                    """**How to read this card**

                    - The photo and squad number identify the player in official match reports.
                    - The border and soft shading identify the role: goalkeeper, defender, midfielder or attacker.
                    - `UAEFA` confirms the player is in the official ecosystem; the adjacent flag shows the published nationality.
                    - Birth year displays the official year and age calculated using the visible matchday cut-off date.
                    - The coloured circle is the **individual Elo** when it is published and the identity match is validated: red is the lower range and green the upper range among available Elo values.
                    - `PJ`, `MIN`, `Goles`, `TA` and `TR` are official UAEFA matches played, minutes, goals, yellow cards and red cards.
                    """ if is_english() else """**Ejemplo de lectura**

                    - La foto y el dorsal identifican al jugador en las actas oficiales.
                    - El borde y sombreado suave indican su posición: portero, defensa, mediocampista o atacante.
                    - `UAEFA` confirma su presencia en el ecosistema oficial; la bandera contigua indica la nacionalidad publicada.
                    - El nacimiento muestra el año oficial y la edad calculada con la fecha de corte de la jornada visible.
                    - El círculo de color es el **Elo individual** cuando está publicado y el cruce de identidad está validado: rojo representa el tramo inferior y verde el superior dentro de los Elo disponibles.
                    - `PJ`, `MIN`, `Goles`, `TA` y `TR` son partidos jugados, minutos, goles, tarjetas amarillas y tarjetas rojas oficiales UAEFA.
                    """
                )

    # The chart has its own position selector, so it can compare roles even
    # when the catalogue cards are narrowed to one specific position.
    scatter_pool = explorer.copy()
    if query:
        scatter_pool = scatter_pool[
            scatter_pool["name_en"].str.contains(query, case=False, na=False)
            | scatter_pool["shortname_en"].str.contains(query, case=False, na=False)
            | scatter_pool["name_en_official"].str.contains(query, case=False, na=False)
        ]
    if category != "Todas":
        scatter_pool = scatter_pool[scatter_pool["nationality_category"].eq(category)]
    if club_filter != "Todos":
        scatter_pool = scatter_pool[scatter_pool["club_name"].eq(club_filter)]
    if age_range is not None:
        if st.session_state.get("birth_filter_driver") == "birth_year":
            scatter_pool = scatter_pool[scatter_pool["Año de nacimiento"].between(*birth_year_range, inclusive="both")]
        else:
            scatter_pool = scatter_pool[scatter_pool["Edad"].between(*age_range, inclusive="both")]
    if min_minutes:
        scatter_pool = scatter_pool[scatter_pool["Minutes"].ge(min_minutes)]
    if player_status != "Todos":
        scatter_pool = scatter_pool[scatter_pool["player_status"].eq(player_status)]
    if played_only:
        scatter_pool = scatter_pool[scatter_pool["Minutes"].gt(0)]

    # Keep widget values language-neutral so switching language never invalidates
    # a selected axis in an active browser session.
    metric_options = {
        "age": ("Edad", "Edad"), "squad": ("Convocatorias", "Squad"),
        "matches": ("Partidos jugados", "Matches"), "starts": ("Titularidades", "Starts"),
        "minutes": ("Minutos", "Minutes"), "goals": ("Goles", "Goals"),
        "yellow": ("Tarjetas amarillas", "Yellow"), "red": ("Tarjetas rojas", "Red"),
        "player_elo": ("Elo del jugador", "Elo jugador"), "market_value": ("Valor de mercado", "Valor de mercado"),
        "team_elo": ("Elo del equipo", "Elo equipo"),
    }
    section("Comparador de jugadores", "Selecciona las variables de cada eje. Elo y valor solo aparecen si el dato externo está publicado y validado")
    with st.container(border=True):
        html("<div class='scatter-shell'><span>ANÁLISIS MULTIVARIABLE</span><b>Explora perfiles y cuadrantes de rendimiento</b></div>")
        scatter_controls = st.columns([1.1, 1.1, 1.35, 1], gap="small", vertical_alignment="bottom")
        metric_names = list(metric_options)
        x_metric = scatter_controls[0].selectbox(t("Eje X"), metric_names, index=4, key="scatter_x", format_func=lambda key: t(metric_options[key][0]))
        y_metric = scatter_controls[1].selectbox(t("Eje Y"), metric_names, index=5, key="scatter_y", format_func=lambda key: t(metric_options[key][0]))
        scatter_positions = scatter_controls[2].multiselect(
            t("Posiciones en el gráfico"),
            options=["GK", "D", "M", "A"],
            default=["GK", "D", "M", "A"],
            key="scatter_positions",
            format_func=lambda code: {"GK": t("Porteros"), "D": t("Defensas"), "M": t("Mediocampistas"), "A": t("Atacantes")}[code],
        )
        exclude_nulls = scatter_controls[3].checkbox(t("Excluir 0 y sin dato"), value=True, key="scatter_nulls")

        scatter_data = scatter_pool[scatter_pool["position"].isin(scatter_positions)].copy()
        x_label, x_column = t(metric_options[x_metric][0]), metric_options[x_metric][1]
        y_label, y_column = t(metric_options[y_metric][0]), metric_options[y_metric][1]
        valid_coordinates = scatter_data.dropna(subset=[x_column, y_column]).copy()
        if exclude_nulls:
            # In official event metrics, zero means no activity. Treat it as an
            # empty value for comparative analysis, then recompute both means.
            scatter_data = valid_coordinates[valid_coordinates[x_column].gt(0) & valid_coordinates[y_column].gt(0)].copy()
        else:
            # Coordinates must exist to draw a point, but valid zeroes remain visible.
            scatter_data = valid_coordinates

        if scatter_data.empty:
            html(f"<div class='empty'>{t('No hay jugadores con valores positivos y publicados para la combinación de métricas elegida.')}</div>")
        else:
            points = (
                alt.Chart(scatter_data)
                .mark_circle(size=105, opacity=0.88, stroke="#ffffff", strokeWidth=1.5)
                .encode(
                    x=alt.X(f"{x_column}:Q", title=x_label),
                    y=alt.Y(f"{y_column}:Q", title=y_label),
                    color=alt.Color(
                        "position:N",
                        title=t("Posición"),
                        scale=alt.Scale(domain=["GK", "D", "M", "A"], range=["#ae7800", "#256abf", "#148a54", "#cf4054"]),
                    ),
                    tooltip=[
                        alt.Tooltip("name_en:N", title="Player" if is_english() else "Jugador"),
                        alt.Tooltip("club_name:N", title=t("Club")), alt.Tooltip("position:N", title=t("Posición")),
                        alt.Tooltip("Nacimiento:N", title=t("Nacimiento / edad")), alt.Tooltip("Minutes:Q", title=t("Minutos")),
                        alt.Tooltip("Goals:Q", title=t("Goles")), alt.Tooltip("Elo jugador:Q", title=t("Elo del jugador"), format=".1f"),
                        alt.Tooltip("Valor de mercado:Q", title=t("Valor de mercado"), format=",.0f"),
                    ],
                )
            )
            # Reference lines are recalculated from exactly the points on screen.
            mean_x = float(scatter_data[x_column].mean())
            mean_y = float(scatter_data[y_column].mean())
            mean_x_rule = alt.Chart(pd.DataFrame({x_column: [mean_x]})).mark_rule(
                color="#657083", strokeDash=[7, 6], strokeWidth=1.35, opacity=0.92
            ).encode(x=alt.X(f"{x_column}:Q"))
            mean_y_rule = alt.Chart(pd.DataFrame({y_column: [mean_y]})).mark_rule(
                color="#657083", strokeDash=[7, 6], strokeWidth=1.35, opacity=0.92
            ).encode(y=alt.Y(f"{y_column}:Q"))
            chart = (
                alt.layer(mean_x_rule, mean_y_rule, points)
                .properties(height=390)
                .interactive()
                .configure(background="#ffffff")
                .configure_view(stroke="#e1e1da", strokeWidth=1)
                .configure_axis(labelColor="#62666b", titleColor="#30343a", gridColor="#ecece7", domainColor="#bfc2ba", tickColor="#bfc2ba")
                .configure_legend(labelColor="#30343a", titleColor="#30343a")
            )
            st.altair_chart(chart, use_container_width=True)
            mode_note = t("Se ocultan los ceros y datos sin publicar.") if exclude_nulls else t("Se muestran los ceros; solo se omiten coordenadas no publicadas.")
            st.caption(
                f"{len(scatter_data)} / {len(scatter_pool)} {t('jugadores visibles')} · {mode_note} "
                f"{t('Medias del gráfico')}: {x_label.lower()} {mean_x:.1f} · {y_label.lower()} {mean_y:.1f}."
            )

    section("Jugadores identificados", f"{len(filtered)} resultados · goleadores primero")
    if filtered.empty:
        html("<div class='empty'>No hay jugadores que cumplan los filtros seleccionados.</div>")
        return
    shown = min(st.session_state.get("shown", GRID_PAGE), len(filtered))
    visible = filtered.head(shown)
    for start in range(0, len(visible), 3):
        columns = st.columns(3, gap="small")
        for column, (_, p) in zip(columns, visible.iloc[start : start + 3].iterrows()):
            with column:
                html(player_card(p, club_map))
                st.button(t("Ver ficha"), key=f"p_{p.player_id}", on_click=open_player, args=(str(p.player_id), "Catálogo"))
    if shown < len(filtered):
        _, middle, _ = st.columns([1, 1, 1])
        middle.button(f"{t('Mostrar más')} ({len(filtered) - shown} {t('restantes')})", on_click=go, kwargs={"shown": shown + GRID_PAGE}, key="more", type="primary")


def footer() -> None:
    html(
        f"""<div class='footer'><div class='fl'><img src='{brand_uri("al_wasl.png")}' alt=''></div>
        <span>{t('Datos locales en Parquet · actualización incremental disponible.')}</span></div>"""
    )
def main() -> None:
    st.html(CSS)
    scroll_to_top_if_needed()
    try:
        season_data = load_data()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    st.session_state.setdefault("page", "Clasificación")
    st.session_state.setdefault("language", "English")
    # Reserve the top slot so the sticky brand bar renders above the nav; each page fills it in.
    BAR_SLOT.clear()
    BAR_SLOT.append(st.empty())
    available_weeks = sorted(pd.to_numeric(season_data["matches"]["week_no"], errors="coerce").dropna().astype(int).unique().tolist())
    scope_options = ["Todas las jornadas"] + [f"Jornada {week}" for week in available_weeks]
    if st.session_state.get("matchday") not in available_weeks:
        # The day-to-day operational view opens on the latest completed matchday.
        st.session_state["matchday"] = available_weeks[-1]
    navigation, scope_control, refresh, language_control = st.columns([4.0, 1.75, 1.2, 1.05], gap="small", vertical_alignment="bottom")
    page = navigation.segmented_control(
        "Navegación", list(PAGES), key="page", label_visibility="collapsed",
        format_func=lambda name: f"{PAGES[name][1]} {t(name)}",
    )
    with scope_control:
        html("<div class='scope-panel'><i></i><span>Jornada de corte</span><b>Vista activa</b></div>")
        previous, current, following = st.columns([1, 3, 1], gap="small", vertical_alignment="center")
        with previous:
            if st.button("‹", key="previous_matchday", disabled=st.session_state["matchday"] == available_weeks[0], use_container_width=True):
                st.session_state["matchday"] = available_weeks[available_weeks.index(st.session_state["matchday"]) - 1]
                st.rerun()
        with current:
            html(f"<div class='scope-panel' style='margin:0;justify-content:center;border-radius:10px'><b>{escape(scope_label())}</b></div>")
        with following:
            if st.button("›", key="next_matchday", disabled=st.session_state["matchday"] == available_weeks[-1], use_container_width=True):
                st.session_state["matchday"] = available_weeks[available_weeks.index(st.session_state["matchday"]) + 1]
                st.rerun()
    if refresh.button(f"↻ {t('Actualizar datos')}", key="reload", type="primary", use_container_width=True):
        try:
            remote = ensure_runtime_snapshot(force=True)
            if remote:
                st.toast(f"Drive: {remote.get('downloaded', 0)} files synchronized", icon="☁️")
        except DriveSyncError as exc:
            st.warning(f"Drive update unavailable: {exc}")
        st.cache_data.clear()
        st.rerun()
    language_control.selectbox(
        "Language",
        ["English", "Español"],
        key="language",
        label_visibility="collapsed",
    )
    page = page or "Clasificación"
    selected_week = st.session_state["matchday"]
    matchday_data = data_for_week(season_data, selected_week)
    data = data_through_week(season_data, selected_week)
    standings = build_standings(data["matches"], season_data["clubs"])
    player_totals = build_player_totals(data)
    club_map = club_lookup(data["clubs"])

    if page == "Clasificación":
        render_overview(data, standings, player_totals, club_map)
    elif page == "Partidos":
        render_matches(matchday_data, club_lookup(matchday_data["clubs"]))
    elif page == "Equipos":
        render_teams(data, standings, player_totals, club_map)
    else:
        render_players(data, player_totals, club_map)
    footer()


if __name__ == "__main__":
    main()
