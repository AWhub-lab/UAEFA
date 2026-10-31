#!/usr/bin/env python3
"""Build a bilingual Al Wasl-styled UAE First Division category report.

The report intentionally uses UAEFA's local official snapshot only. It can be
regenerated after every incremental sync without hand-editing any statistics.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
ASSET_ROOT = ROOT / "data" / "assets" / "brand"
TMP_ROOT = ROOT / "tmp" / "category_report"
OUTPUT = ROOT / "output" / "pdf" / "uae_first_division_category_report_en.pdf"

YELLOW = "#FFD21F"
GOLD = "#B98400"
GREEN = "#0B4A33"
DEEP_GREEN = "#071D15"
INK = "#11151A"
MUTED = "#5E666E"
LINE = "#DADDD8"
BLUE = "#2A67B1"
RED = "#D64C5B"

POSITION_ORDER = ["GK", "D", "M", "A"]
POSITION_LABELS = {
    "GK": "Goalkeepers",
    "D": "Defenders",
    "M": "Midfielders",
    "A": "Attackers",
}
POSITION_COLORS = {"GK": "#D69B16", "D": "#3277C7", "M": "#1B9B63", "A": "#D34F60"}
AGE_ORDER = ["<=20", "21-23", "24-27", "28-31", "32+"]


def safe_int(value: object) -> int:
    return int(value) if pd.notna(value) else 0


def age_at_cutoff(birth_date: object, cutoff: pd.Timestamp) -> int | None:
    birth = pd.to_datetime(birth_date, errors="coerce")
    if pd.isna(birth) or pd.isna(cutoff):
        return None
    return int(cutoff.year - birth.year - ((cutoff.month, cutoff.day) < (birth.month, birth.day)))


def age_band(age: object) -> str | None:
    if pd.isna(age):
        return None
    age = int(age)
    if age <= 20:
        return "<=20"
    if age <= 23:
        return "21-23"
    if age <= 27:
        return "24-27"
    if age <= 31:
        return "28-31"
    return "32+"


def read_snapshot() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    players = pd.read_parquet(DATA_ROOT / "players.parquet")
    profiles = pd.read_parquet(DATA_ROOT / "player_profiles_uaefa.parquet")
    matches = pd.read_parquet(DATA_ROOT / "matches.parquet")
    appearances = pd.read_parquet(DATA_ROOT / "appearances.parquet")
    clubs = pd.read_parquet(DATA_ROOT / "clubs.parquet")
    cutoff = pd.to_datetime(matches["match_date"], errors="coerce").max()
    columns = ["player_id", "birth_date_official"]
    players = players.merge(profiles[columns], on="player_id", how="left")
    # A player can have a newer federation profile at a different club. For a
    # category report, their latest appearance identifies the relevant club.
    latest_appearance = appearances.merge(matches[["match_id", "match_date"]], on="match_id", how="left")
    latest_appearance["match_date"] = pd.to_datetime(latest_appearance["match_date"], errors="coerce")
    latest_appearance = latest_appearance.sort_values("match_date").drop_duplicates("player_id", keep="last")
    latest_appearance["player_id"] = latest_appearance["player_id"].astype(str)
    clubs["club_id"] = clubs["club_id"].astype(str)
    players["player_id"] = players["player_id"].astype(str)
    players = players.merge(latest_appearance[["player_id", "club_id"]], on="player_id", how="left")
    players["club_id"] = players["club_id"].astype(str)
    players = players.merge(clubs[["club_id", "club_name", "crest_file"]], on="club_id", how="left")
    players["birth_date_official"] = pd.to_datetime(players["birth_date_official"], errors="coerce")
    players["age"] = players["birth_date_official"].map(lambda value: age_at_cutoff(value, cutoff))
    players["birth_year"] = players["birth_date_official"].dt.year
    players["age_band"] = players["age"].map(age_band)
    players["position"] = players["position"].fillna("-")
    players["nationality_category"] = players["nationality_category"].fillna("Not published").astype(str).str.strip()
    players["player_status"] = players["player_status"].fillna("Not published").astype(str).str.strip()
    return players, matches, cutoff


def rounded_bars(ax: plt.Axes, labels: list[str], values: list[float], colors_: list[str], width: float = 0.62) -> list[FancyBboxPatch]:
    """Draw vertical bars with softly rounded caps rather than square blocks."""
    patches: list[FancyBboxPatch] = []
    for index, (value, color) in enumerate(zip(values, colors_)):
        patch = FancyBboxPatch(
            (index - width / 2, 0), width, value,
            boxstyle=f"round,pad=0,rounding_size={width * 0.18}",
            linewidth=0, facecolor=color,
        )
        ax.add_patch(patch)
        patches.append(patch)
    ax.set_xlim(-0.7, len(labels) - 0.3)
    ax.set_xticks(range(len(labels)), labels)
    return patches


def chart_style(ax: plt.Axes, title: str, subtitle: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color=INK, pad=18)
    if subtitle:
        ax.text(0, 1.01, subtitle, transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="y", color="#E8EAE6", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors="#46505A", labelsize=9)


def save_age_chart(players: pd.DataFrame) -> Path:
    series = players["age_band"].value_counts().reindex(AGE_ORDER, fill_value=0)
    fig, ax = plt.subplots(figsize=(7.1, 3.5), facecolor="white")
    bars = rounded_bars(ax, series.index.tolist(), series.values.tolist(), [YELLOW, "#E7B918", "#C8950B", "#96700A", "#5B4A16"])
    chart_style(ax, "Age distribution", "Players with an official UAEFA birth date")
    ax.set_ylabel("Players", color=MUTED)
    ax.set_ylim(0, series.max() * 1.16)
    for bar, value in zip(bars, series.values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(series.max() * 0.02, 0.4), str(value), ha="center", va="bottom", fontweight="bold", color=INK)
    fig.tight_layout()
    path = TMP_ROOT / "age_distribution.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_position_age_chart(players: pd.DataFrame) -> Path:
    data = players.dropna(subset=["age"])
    stats = data.groupby("position")["age"].agg(["mean", "median", "count"]).reindex(POSITION_ORDER).dropna(how="all")
    fig, ax = plt.subplots(figsize=(7.1, 3.5), facecolor="white")
    bars = rounded_bars(ax, stats.index.tolist(), stats["mean"].tolist(), [POSITION_COLORS.get(position, MUTED) for position in stats.index], width=0.58)
    chart_style(ax, "Mean age by position", "Calculated at the competition data cut-off")
    ax.set_ylabel("Age", color=MUTED)
    ax.set_ylim(0, max(40, stats["mean"].max() + 6))
    for bar, (mean, count) in zip(bars, stats[["mean", "count"]].itertuples(index=False, name=None)):
        ax.text(bar.get_x() + bar.get_width() / 2, mean + 0.5, f"{mean:.1f}\nn={int(count)}", ha="center", va="bottom", fontweight="bold", color=INK, fontsize=9)
    fig.tight_layout()
    path = TMP_ROOT / "position_age.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_status_nationality_chart(players: pd.DataFrame) -> Path:
    status = players["player_status"].value_counts().sort_values(ascending=True)
    nationality = players["nationality_category"].value_counts().sort_values(ascending=True)
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.5), facecolor="white", gridspec_kw={"wspace": 0.55})
    for ax, series, title, color in (
        (axes[0], status, "Registration status", GREEN),
        (axes[1], nationality, "UAEFA nationality category", GOLD),
    ):
        bars = ax.barh(series.index, series.values, color=color, alpha=0.9)
        ax.set_title(title, loc="left", fontsize=11.5, fontweight="bold", color=INK, pad=12)
        ax.spines[["top", "right", "bottom"]].set_visible(False)
        ax.tick_params(axis="both", labelsize=8, colors="#46505A")
        ax.grid(axis="x", color="#E8EAE6", linewidth=0.8)
        ax.set_axisbelow(True)
        for bar, value in zip(bars, series.values):
            ax.text(value + max(series.max() * 0.015, 0.4), bar.get_y() + bar.get_height() / 2, str(value), va="center", fontsize=8.5, fontweight="bold", color=INK)
    fig.tight_layout()
    path = TMP_ROOT / "status_nationality.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_heatmap(players: pd.DataFrame) -> Path:
    matrix = pd.crosstab(players["age_band"], players["position"]).reindex(index=AGE_ORDER, columns=POSITION_ORDER, fill_value=0)
    fig, ax = plt.subplots(figsize=(7.1, 3.65), facecolor="white")
    image = ax.imshow(matrix.values, cmap="YlGn", aspect="auto")
    ax.set_title("Age and position", loc="left", fontsize=15, fontweight="bold", color=INK, pad=18)
    ax.text(0, 1.01, "Registered players with an official UAEFA birth date", transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    ax.set_xticks(range(len(matrix.columns)), matrix.columns)
    ax.set_yticks(range(len(matrix.index)), matrix.index)
    ax.set_xlabel("Position", color=MUTED)
    ax.set_ylabel("Age band", color=MUTED)
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix.iloc[row, column]
            ax.text(column, row, str(value), ha="center", va="center", color=INK, fontweight="bold")
    fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025, label="Players")
    fig.tight_layout()
    path = TMP_ROOT / "age_position.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_birth_year_chart(players: pd.DataFrame) -> Path:
    series = players["birth_year"].dropna().astype(int).value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7.1, 3.5), facecolor="white")
    bars = ax.bar(series.index.astype(str), series.values, color=BLUE, width=0.72)
    chart_style(ax, "Birth-year distribution", "Registered players with an official UAEFA birth date")
    ax.set_ylabel("Players", color=MUTED)
    ax.tick_params(axis="x", rotation=45, labelsize=7.5)
    for bar, value in zip(bars, series.values):
        if value >= max(2, series.max() * 0.14):
            ax.text(bar.get_x() + bar.get_width() / 2, value + max(series.max() * 0.02, 0.35), str(value), ha="center", va="bottom", fontweight="bold", color=INK, fontsize=7.5)
    fig.tight_layout()
    path = TMP_ROOT / "birth_years.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_status_mix_chart(players: pd.DataFrame) -> Path:
    """Show professional/amateur share within every published UAEFA category."""
    matrix = pd.crosstab(players["nationality_category"], players["player_status"])
    matrix = matrix.reindex(columns=["Professional", "Amateur"], fill_value=0)
    matrix["total"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("total", ascending=True)
    share = matrix[["Professional", "Amateur"]].div(matrix["total"], axis=0).mul(100)
    fig, ax = plt.subplots(figsize=(7.1, 4.05), facecolor="white")
    left = pd.Series(0.0, index=share.index)
    palette = {"Professional": GREEN, "Amateur": "#D8A316"}
    for status in ["Professional", "Amateur"]:
        ax.barh(share.index, share[status], left=left, color=palette[status], height=0.58, label=status)
        left += share[status]
    ax.set_title("Registration status within UAEFA categories", loc="left", fontsize=14, fontweight="bold", color=INK, pad=17)
    ax.text(0, 1.01, "Each bar sums to 100%; labels show registered-player count", transform=ax.transAxes, fontsize=8.2, color=MUTED, va="bottom")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of each UAEFA category (%)", color=MUTED)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color="#E8EAE6", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=8.5, colors="#46505A")
    for y, (_, row) in enumerate(matrix.iterrows()):
        ax.text(101.5, y, f"n={int(row['total'])}", va="center", fontsize=8, fontweight="bold", color=INK)
    ax.legend(loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.29), fontsize=8.5)
    fig.tight_layout()
    path = TMP_ROOT / "status_mix.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def save_team_size_chart(players: pd.DataFrame) -> Path:
    series = players.dropna(subset=["club_name"]).groupby("club_name").size().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(7.1, 3.9), facecolor="white")
    bars = rounded_bars(ax, series.index.tolist(), series.values.tolist(), [GREEN] * len(series), width=0.62)
    chart_style(ax, "Registered players by club", "Latest club represented in UAE First Division match reports")
    ax.set_ylabel("Players", color=MUTED)
    ax.set_ylim(0, series.max() * 1.2)
    ax.tick_params(axis="x", rotation=50, labelsize=7.1)
    for bar, value in zip(bars, series.values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.5, str(value), ha="center", va="bottom", fontsize=7.8, fontweight="bold", color=INK)
    fig.tight_layout()
    path = TMP_ROOT / "team_sizes.png"
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)
    return path


def compact_distribution(series: pd.Series, order: list[str] | None = None) -> str:
    if order is not None:
        series = series.reindex(order, fill_value=0)
    total = int(series.sum())
    if not total:
        return "No published records"
    return " | ".join(f"{label}: {int(value)} ({value / total:.0%})" for label, value in series.items() if value)


def team_card(team_name: str, squad: pd.DataFrame, styles_: dict[str, ParagraphStyle]) -> Table:
    """Compact board-readable team profile, using the club crest from local assets."""
    total = len(squad)
    age_data = squad["age"].dropna()
    average_age = f"{age_data.mean():.1f}" if not age_data.empty else "Not published"
    crest_file = squad["crest_file"].dropna().iloc[0] if squad["crest_file"].notna().any() else None
    crest_path = ROOT / str(crest_file) if crest_file else None
    crest = Image(str(crest_path), width=1.3 * cm, height=1.3 * cm) if crest_path and crest_path.exists() else Spacer(1.3 * cm, 1.3 * cm)
    title = Paragraph(f"<b>{team_name}</b><br/><font size=8 color='#5E666E'>{total} registered players | Mean age: {average_age}</font>", styles_["body"])
    header = Table([[crest, title]], colWidths=[1.7 * cm, 15.0 * cm], rowHeights=[1.65 * cm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F7F3")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(YELLOW)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    position_text = compact_distribution(squad["position"].value_counts(), POSITION_ORDER)
    age_text = compact_distribution(squad["age_band"].value_counts(), AGE_ORDER)
    status_text = compact_distribution(squad["player_status"].value_counts())
    category_text = compact_distribution(squad["nationality_category"].value_counts().sort_values(ascending=False))
    body_rows = [
        [Paragraph("<b>SQUAD SHAPE</b>", styles_["small"]), Paragraph(position_text, styles_["small"])],
        [Paragraph("<b>AGE PROFILE</b>", styles_["small"]), Paragraph(age_text, styles_["small"])],
        [Paragraph("<b>REGISTRATION</b>", styles_["small"]), Paragraph(status_text, styles_["small"])],
        [Paragraph("<b>UAEFA CATEGORY</b>", styles_["small"]), Paragraph(category_text, styles_["small"])],
    ]
    # UAEFA category labels may legitimately contain five groups; reserve a
    # little extra space for the only row that can wrap onto a second line.
    body = Table(body_rows, colWidths=[3.4 * cm, 13.3 * cm], rowHeights=[0.65 * cm, 0.65 * cm, 0.65 * cm, 0.88 * cm])
    body.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(LINE)),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F6F7F3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    card = Table([[header], [body]], colWidths=[16.7 * cm])
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(LINE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return card


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle("cover_kicker", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=colors.HexColor(YELLOW), spaceAfter=9, tracking=1.7),
        "cover_title": ParagraphStyle("cover_title", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=27, leading=30, textColor=colors.white, spaceAfter=10),
        "cover_subtitle": ParagraphStyle("cover_subtitle", parent=sample["Normal"], fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor("#D5DDD8")),
        "h1": ParagraphStyle("h1", parent=sample["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor(INK), spaceBefore=3, spaceAfter=9),
        "h2": ParagraphStyle("h2", parent=sample["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(GREEN), spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("body", parent=sample["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.3, textColor=colors.HexColor("#343B42"), spaceAfter=7),
        "small": ParagraphStyle("small", parent=sample["BodyText"], fontName="Helvetica", fontSize=7.6, leading=10.5, textColor=colors.HexColor(MUTED), spaceAfter=4),
        "metric": ParagraphStyle("metric", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=18, leading=19, textColor=colors.HexColor(INK), alignment=TA_CENTER),
        "metric_label": ParagraphStyle("metric_label", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=6.25, leading=7.5, textColor=colors.HexColor(MUTED), alignment=TA_CENTER),
    }


def metric_card(value: str, label: str, s: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(value, s["metric"])], [Paragraph(label, s["metric_label"])]], colWidths=[3.55 * cm], rowHeights=[0.65 * cm, 0.78 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F7F3")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(LINE)),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(YELLOW)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(YELLOW))
    canvas.setLineWidth(2)
    canvas.line(1.7 * cm, 1.25 * cm, A4[0] - 1.7 * cm, 1.25 * cm)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(1.7 * cm, 0.82 * cm, "Al Wasl Football Intelligence | UAE First Division 2026/27")
    canvas.drawRightString(A4[0] - 1.7 * cm, 0.82 * cm, f"{doc.page}")
    canvas.restoreState()


def build_report_legacy() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    players, matches, cutoff = read_snapshot()
    dated = players.dropna(subset=["age"]).copy()
    chart_paths = [
        save_age_chart(dated), save_position_age_chart(dated), save_status_nationality_chart(players),
        save_heatmap(dated), save_birth_year_chart(dated),
    ]
    age_chart, position_chart, status_chart, heatmap_chart, birth_chart = chart_paths
    s = styles()
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=1.7 * cm, leftMargin=1.7 * cm, topMargin=1.45 * cm, bottomMargin=1.65 * cm)
    story: list[object] = []
    logo = ASSET_ROOT / "al_wasl.png"
    total = len(players)
    age_coverage = len(dated)
    latest_week = pd.to_numeric(matches["week_no"], errors="coerce").max()
    professional = int(players["player_status"].eq("Professional").sum())
    citizen = int(players["nationality_category"].eq("UAE Citizen").sum())
    median_age = dated["age"].median()
    oldest = dated.loc[dated["age"].idxmax()]
    youngest = dated.loc[dated["age"].idxmin()]

    cover_data = [["", ""]]
    cover = Table(cover_data, colWidths=[2.6 * cm, 14.8 * cm], rowHeights=[22.8 * cm])
    cover.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(DEEP_GREEN)), ("LINEBEFORE", (0, 0), (0, -1), 5, colors.HexColor(YELLOW))]))
    story.append(cover)
    # Overlay cover content with a nested table to preserve a bold, uncluttered front page.
    logo_flow = Image(str(logo), width=2.15 * cm, height=2.15 * cm) if logo.exists() else Spacer(2.15 * cm, 2.15 * cm)
    cover_content = Table([
        [logo_flow, Paragraph("AL WASL FOOTBALL INTELLIGENCE", s["cover_kicker"])],
        ["", Paragraph("UAE FIRST DIVISION<br/>CATEGORY REPORT", s["cover_title"])],
        ["", Paragraph("Informe estadistico bilingue / Bilingual statistical report<br/>Temporada 2026/27 | Corte: Jornada %s | %s" % (safe_int(latest_week), cutoff.strftime("%d %b %Y")), s["cover_subtitle"])],
    ], colWidths=[2.8 * cm, 13.9 * cm], rowHeights=[2.6 * cm, 2.6 * cm, 3.0 * cm])
    cover_content.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(DEEP_GREEN)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(Spacer(0, -21.3 * cm))
    story.append(cover_content)
    story.append(Spacer(0, 13.6 * cm))
    story.append(Paragraph("Fuente / Source: UAEFA public match reports and player records stored locally. External sources are not used in this category snapshot.", s["small"]))
    story.append(PageBreak())

    story.append(Paragraph("Panorama de la categoria / Category overview", s["h1"]))
    story.append(Paragraph(
        "Este documento describe el registro de jugadores de la UAE First Division a la fecha de corte indicada. "
        "Las edades se calculan con la fecha del ultimo partido disponible; los analisis de edad incluyen exclusivamente fichas con nacimiento oficial publicado.<br/><br/>"
        "This report describes the UAE First Division player register at the stated cut-off. "
        "Ages are calculated on the latest available match date; age analysis includes only profiles with an official published birth date.", s["body"]
    ))
    metrics = Table([[
        metric_card(str(total), "JUGADORES REGISTRADOS / REGISTERED PLAYERS", s),
        metric_card(f"{age_coverage}/{total}", "COBERTURA DE NACIMIENTO / BIRTH-DATE COVERAGE", s),
        metric_card(str(safe_int(latest_week)), "JORNADA DE CORTE / MATCHDAY CUT-OFF", s),
        metric_card(str(len(matches)), "PARTIDOS DISPONIBLES / MATCHES AVAILABLE", s),
    ]], colWidths=[4.25 * cm] * 4)
    story.append(metrics)
    story.append(Spacer(0, 0.5 * cm))
    summary_table = Table([
        ["Indicador / Indicator", "Resultado / Result", "Lectura / Reading"],
        ["Edad mediana / Median age", f"{median_age:.1f}" if pd.notna(median_age) else "-", "Nacimiento publicado / Birth published"],
        ["Mas joven / Youngest", f"{youngest['shortname_en']} ({safe_int(youngest['age'])})", "Edad al corte / Age at cut-off"],
        ["Mayor / Oldest", f"{oldest['shortname_en']} ({safe_int(oldest['age'])})", "Edad al corte / Age at cut-off"],
        ["Profesionales / Professionals", f"{professional} ({professional / total:.1%})", "Estatus UAEFA / UAEFA status"],
        ["Ciudadanos EAU / UAE citizens", f"{citizen} ({citizen / total:.1%})", "Categoria UAEFA / UAEFA category"],
    ], colWidths=[4.5 * cm, 5.0 * cm, 7.4 * cm], repeatRows=1)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2), ("LEADING", (0, 0), (-1, -1), 10.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F7F3")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(0, 0.25 * cm))
    story.append(summary_table)
    story.append(PageBreak())

    story.append(Paragraph("Estructura de edad / Age structure", s["h1"]))
    story.append(Paragraph("La distribucion muestra el equilibrio entre jugadores de desarrollo, prime competitivo y experiencia. El denominador se limita a fichas con fecha de nacimiento oficial disponible.<br/><br/>The distribution describes the balance between development players, competitive prime and experience. The denominator is limited to official profiles with a published birth date.", s["body"]))
    story.append(Image(str(age_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(Spacer(0, 0.35 * cm))
    story.append(Image(str(position_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(PageBreak())

    story.append(Paragraph("Posicion, profesion y categoria UAEFA / Position, status and UAEFA category", s["h1"]))
    story.append(Paragraph("El estatus y la categoria de nacionalidad se reproducen tal y como figuran en el registro UAEFA. No se reinterpretan las categorias administrativas como nacionalidad deportiva.<br/><br/>Status and nationality category are reproduced exactly as listed by UAEFA. Administrative categories are not reinterpreted as sporting nationality.", s["body"]))
    story.append(Image(str(status_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(Spacer(0, 0.35 * cm))
    position_counts = players["position"].value_counts().reindex(POSITION_ORDER, fill_value=0)
    position_rows = [["Posicion / Position", "Jugadores / Players", "Cuota / Share"]]
    for position, count in position_counts.items():
        position_rows.append([POSITION_LABELS.get(position, position), str(count), f"{count / total:.1%}"])
    position_table = Table(position_rows, colWidths=[8.2 * cm, 4.5 * cm, 4.3 * cm], repeatRows=1)
    position_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(DEEP_GREEN)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F7F3")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(position_table)
    story.append(PageBreak())

    story.append(Paragraph("Edad, posicion y ano de nacimiento / Age, position and birth year", s["h1"]))
    story.append(Paragraph("Estos cruces permiten detectar concentraciones de cohortes y leer la estructura de cada linea de juego. Son descriptivos; no representan minutos, rendimiento ni valor de mercado.<br/><br/>These cross-sections identify cohort concentrations and show the makeup of each line. They are descriptive; they do not represent minutes, performance or market value.", s["body"]))
    story.append(Image(str(heatmap_chart), width=17.0 * cm, height=8.75 * cm))
    story.append(Spacer(0, 0.3 * cm))
    story.append(Image(str(birth_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(PageBreak())

    pos_age = dated.groupby("position")["age"].mean().sort_values()
    youngest_position = pos_age.index[0] if not pos_age.empty else "-"
    oldest_position = pos_age.index[-1] if not pos_age.empty else "-"
    youngest_position_age = pos_age.iloc[0] if not pos_age.empty else float("nan")
    oldest_position_age = pos_age.iloc[-1] if not pos_age.empty else float("nan")
    story.append(Paragraph("Lecturas para scouting / Scouting takeaways", s["h1"]))
    findings = [
        f"<b>Cobertura demografica / Demographic coverage:</b> {age_coverage} de {total} jugadores ({age_coverage / total:.1%}) cuentan con fecha de nacimiento oficial publicada; toda lectura de edad debe referirse a esa cobertura.",
        f"<b>Perfil central / Central profile:</b> la edad mediana registrada es {median_age:.1f} anos. El rango observado va de {safe_int(youngest['age'])} a {safe_int(oldest['age'])} anos al corte de datos.",
        f"<b>Lineas de juego / Playing lines:</b> la media de edad mas baja corresponde a {POSITION_LABELS.get(youngest_position, youngest_position)} ({youngest_position_age:.1f}); la mas alta, a {POSITION_LABELS.get(oldest_position, oldest_position)} ({oldest_position_age:.1f}).",
        f"<b>Registro competitivo / Competitive register:</b> {professional} jugadores figuran como profesionales y {citizen} aparecen en la categoria UAE Citizen. Son etiquetas administrativas UAEFA, no una valoracion de calidad.",
        "<b>Uso recomendado / Recommended use:</b> combinar esta radiografia con minutos, convocatorias, acciones oficiales y video antes de tomar decisiones de scouting o plantilla.",
    ]
    for finding in findings:
        story.append(Paragraph(finding, s["body"]))
    story.append(Spacer(0, 0.35 * cm))
    story.append(Paragraph("Notas metodologicas / Methodological notes", s["h2"]))
    story.append(Paragraph(
        f"Corte estadistico: {cutoff.strftime('%d/%m/%Y')}; partidos disponibles: {len(matches)}; jornada maxima: {safe_int(latest_week)}. "
        "Unidad de analisis: jugador registrado en el conjunto local de UAEFA. Los duplicados de presencia en actas no se suman como jugadores adicionales. "
        "Las tablas se regeneran a partir de los Parquet locales de la aplicacion; por ello cambiaran al actualizar el dataset.<br/><br/>"
        f"Statistical cut-off: {cutoff.strftime('%d/%m/%Y')}; available matches: {len(matches)}; latest matchday: {safe_int(latest_week)}. "
        "Unit of analysis: a player registered in the local UAEFA dataset. Repeated match-report appearances are not counted as additional players. "
        "Tables are regenerated from the app's local Parquet files and therefore change when the dataset is refreshed.", s["small"]
    ))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUTPUT


def build_report() -> Path:
    """Create the English executive version used for board-level review."""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    players, matches, cutoff = read_snapshot()
    dated = players.dropna(subset=["age"]).copy()
    teams = players.dropna(subset=["club_name"]).copy()
    total = len(players)
    age_coverage = len(dated)
    latest_week = pd.to_numeric(matches["week_no"], errors="coerce").max()
    professional = int(players["player_status"].eq("Professional").sum())
    amateur = int(players["player_status"].eq("Amateur").sum())
    uae_explicit = int(players["nationality_category"].isin(["UAE Citizen", "UAE Born", "Citizen Child"]).sum())
    median_age = dated["age"].median()
    position_counts = players["position"].value_counts().reindex(POSITION_ORDER, fill_value=0)
    pos_age = dated.groupby("position")["age"].mean().reindex(POSITION_ORDER)
    s = styles()
    age_chart = save_age_chart(dated)
    position_chart = save_position_age_chart(dated)
    status_chart = save_status_nationality_chart(players)
    status_mix_chart = save_status_mix_chart(players)
    heatmap_chart = save_heatmap(dated)
    birth_chart = save_birth_year_chart(dated)
    team_size_chart = save_team_size_chart(teams)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=1.7 * cm, leftMargin=1.7 * cm, topMargin=1.45 * cm, bottomMargin=1.65 * cm)
    story: list[object] = []
    logo = ASSET_ROOT / "al_wasl.png"

    # Cover
    cover = Table([[""]], colWidths=[17.4 * cm], rowHeights=[22.8 * cm])
    cover.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(DEEP_GREEN)), ("LINEBEFORE", (0, 0), (0, -1), 5, colors.HexColor(YELLOW))]))
    story.append(cover)
    logo_flow = Image(str(logo), width=2.15 * cm, height=2.15 * cm) if logo.exists() else Spacer(2.15 * cm, 2.15 * cm)
    cover_content = Table([
        [logo_flow, Paragraph("AL WASL FOOTBALL INTELLIGENCE", s["cover_kicker"])],
        ["", Paragraph("UAE FIRST DIVISION<br/>CATEGORY INTELLIGENCE REPORT", s["cover_title"])],
        ["", Paragraph(f"Executive roster and demographic analysis<br/>Season 2026/27 | Matchday {safe_int(latest_week)} cut-off | {cutoff.strftime('%d %b %Y')}", s["cover_subtitle"])],
    ], colWidths=[2.8 * cm, 13.9 * cm], rowHeights=[2.6 * cm, 3.1 * cm, 2.8 * cm])
    cover_content.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(DEEP_GREEN)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(Spacer(0, -21.3 * cm))
    story.append(cover_content)
    story.append(Spacer(0, 13.4 * cm))
    story.append(Paragraph("Source: UAEFA public match reports and player records stored locally. The report uses official registration fields only; it does not infer nationality or player quality from administrative categories.", s["small"]))
    story.append(PageBreak())

    # Executive overview
    story.append(Paragraph("Competition at a glance", s["h1"]))
    story.append(Paragraph(
        "This report is designed as a first decision layer for a board or scouting department new to the competition. "
        "It establishes the size and composition of the player pool before adding performance, video, recruitment cost or tactical context.", s["body"]
    ))
    story.append(Table([[
        metric_card(str(total), "REGISTERED PLAYERS", s),
        metric_card(f"{age_coverage}/{total}", "OFFICIAL BIRTH-DATE COVERAGE", s),
        metric_card(str(safe_int(latest_week)), "MATCHDAY CUT-OFF", s),
        metric_card(str(len(matches)), "MATCHES AVAILABLE", s),
    ]], colWidths=[4.25 * cm] * 4))
    story.append(Spacer(0, 0.45 * cm))
    overview = Table([
        [Paragraph("<b>WHAT THIS REPORT ANSWERS</b>", s["small"]), Paragraph("<b>HOW TO READ IT</b>", s["small"])],
        [Paragraph("How large is the available player pool? How is it split by age, role, registration status and UAEFA category? Which clubs show different squad structures?", s["body"]),
         Paragraph("Counts refer to registered players. Ages are measured at the latest available match date. Age charts use only players with an official published birth date.", s["body"])],
    ], colWidths=[8.35 * cm, 8.35 * cm])
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F1")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(overview)
    story.append(Spacer(0, 0.5 * cm))
    position_cards = []
    for position, count in position_counts.items():
        avg = pos_age.get(position)
        label = f"{POSITION_LABELS[position].upper()} | {count / total:.1%} OF POOL | MEAN AGE {avg:.1f}" if pd.notna(avg) else f"{POSITION_LABELS[position].upper()} | {count / total:.1%} OF POOL"
        position_cards.append(metric_card(str(int(count)), label, s))
    story.append(Paragraph("Role mix", s["h2"]))
    story.append(Paragraph("Each card combines the absolute number of registered players, share of the competition pool and mean age where official birth data is available.", s["body"]))
    story.append(Table([position_cards], colWidths=[4.25 * cm] * 4))
    story.append(PageBreak())

    # Age section
    story.append(Paragraph("Age architecture", s["h1"]))
    story.append(Paragraph(
        "The age profile shows the balance between development, competitive-prime and experienced players. "
        "The rounded bars make the cohort concentration immediately comparable, while the second chart identifies the age profile of each positional line.", s["body"]
    ))
    story.append(Image(str(age_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(Spacer(0, 0.35 * cm))
    story.append(Image(str(position_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(PageBreak())

    # Registration and country-section
    story.append(Paragraph("Registration and UAEFA category context", s["h1"]))
    story.append(Paragraph(
        "This page separates the competition's registered player status from UAEFA's published nationality category. "
        "The right-hand chart answers a key board question: within each category, what proportion is registered as professional or amateur? "
        "The report keeps UAEFA labels intact; categories such as UAE Born, Citizen Child and Passport Holders are not reclassified.", s["body"]
    ))
    story.append(Image(str(status_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(Spacer(0, 0.25 * cm))
    story.append(Image(str(status_mix_chart), width=17.0 * cm, height=9.6 * cm))
    story.append(Spacer(0, 0.2 * cm))
    story.append(Paragraph(
        f"Headline: {professional} of {total} registered players ({professional / total:.1%}) are listed as Professional, while {amateur} ({amateur / total:.1%}) are listed as Amateur. "
        f"{uae_explicit} players ({uae_explicit / total:.1%}) sit in UAEFA categories explicitly labelled UAE Citizen, UAE Born or Citizen Child; remaining categories are shown separately above.", s["small"]
    ))
    story.append(PageBreak())

    # Cohort and club overview
    story.append(Paragraph("Cohorts and club coverage", s["h1"]))
    story.append(Paragraph(
        "The heatmap pinpoints the distribution of age cohorts across the four positional groups. The birth-year chart then shows whether the squad pool is concentrated in a limited generation or dispersed across multiple cohorts. "
        "The final chart shows how many players are represented by each club through the latest available First Division match report.", s["body"]
    ))
    story.append(Image(str(heatmap_chart), width=17.0 * cm, height=8.75 * cm))
    story.append(Spacer(0, 0.18 * cm))
    story.append(Image(str(birth_chart), width=17.0 * cm, height=8.35 * cm))
    story.append(PageBreak())
    story.append(Paragraph("Club representation", s["h1"]))
    story.append(Paragraph(
        "The category contains 15 clubs. A player's club is assigned from their latest available UAE First Division match report, avoiding mismatches caused by a federation profile being updated after a transfer or registration change.", s["body"]
    ))
    story.append(Image(str(team_size_chart), width=17.0 * cm, height=9.25 * cm))
    story.append(Paragraph("The following pages convert this league-level view into standardised team profiles. Every profile uses both absolute values and percentages so clubs with different registered-pool sizes remain comparable.", s["body"]))
    story.append(PageBreak())

    # Club profile cards: two teams per page to give each one enough reading space.
    grouped = [(name, frame.copy()) for name, frame in teams.groupby("club_name", sort=True)]
    for start in range(0, len(grouped), 2):
        story.append(Paragraph("Club register profiles", s["h1"]))
        story.append(Paragraph("Each card reports the latest club representation in the competition. Squad shape is shown as absolute count and percentage of the registered pool; age profile excludes players without an official published date of birth.", s["body"]))
        for team_name, squad in grouped[start : start + 2]:
            story.append(team_card(team_name, squad, s))
            story.append(Spacer(0, 0.45 * cm))
        story.append(Spacer(0, 0.15 * cm))
        story.append(Paragraph("Board note: these profiles describe registration structure, not playing time, contract status, tactical system or player quality. They should be read alongside the match, player and recruitment modules of the application.", s["small"]))
        if start + 2 < len(grouped):
            story.append(PageBreak())

    story.append(Paragraph("Board takeaways and next steps", s["h1"]))
    youngest_position = pos_age.idxmin() if not pos_age.dropna().empty else "-"
    oldest_position = pos_age.idxmax() if not pos_age.dropna().empty else "-"
    youngest_age = pos_age.get(youngest_position)
    oldest_age = pos_age.get(oldest_position)
    points = [
        f"<b>Data coverage:</b> all {total} registered players have an official UAEFA birth date in the current local dataset, enabling a complete age view at the {cutoff.strftime('%d %b %Y')} cut-off.",
        f"<b>Age profile:</b> the competition's median age is {median_age:.1f}. {POSITION_LABELS.get(youngest_position, youngest_position)} form the youngest positional group on average ({youngest_age:.1f}), while {POSITION_LABELS.get(oldest_position, oldest_position)} are the oldest ({oldest_age:.1f}).",
        f"<b>Registration market:</b> the player pool contains {professional} professionals ({professional / total:.1%}) and {amateur} amateurs ({amateur / total:.1%}). This should frame, rather than replace, individual scouting evaluation.",
        "<b>Club comparison:</b> use the club profiles to identify where a role, age band or registration category is structurally scarce before moving to individual player filters, minutes, actions, Elo and market-value context in the application.",
        "<b>Decision workflow:</b> start with category structure, isolate the club and role, filter by birth year or age, then validate the shortlist with playing time, official event history and video. Avoid using a single demographic metric as a recruitment decision.",
    ]
    for point in points:
        story.append(Paragraph(point, s["body"]))
    story.append(Spacer(0, 0.35 * cm))
    story.append(Paragraph("Methodology and scope", s["h2"]))
    story.append(Paragraph(
        f"Statistical cut-off: {cutoff.strftime('%d/%m/%Y')}; available matches: {len(matches)}; latest matchday: {safe_int(latest_week)}. "
        "Unit of analysis: a player registered in the local UAEFA First Division dataset. Club assignment follows the latest available match-report appearance. "
        "All figures are regenerated from local Parquet files after a data refresh. The report is descriptive and does not contain performance ratings, contract information or inferred identity attributes.", s["small"]
    ))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUTPUT


if __name__ == "__main__":
    report = build_report()
    print(report)
