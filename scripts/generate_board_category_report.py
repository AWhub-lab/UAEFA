#!/usr/bin/env python3
"""Create the English, board-ready UAE First Division category report."""

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
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "first_division_2026_2027" / "current"
TMP = ROOT / "tmp" / "board_category_report"
OUTPUT = ROOT / "output" / "pdf" / "uae_first_division_category_board_report_en.pdf"
BRAND = ROOT / "data" / "assets" / "brand" / "al_wasl.png"

YELLOW, GOLD, GREEN, DEEP, INK = "#FFD21F", "#B98400", "#0B4A33", "#071D15", "#11151A"
MUTED, LINE, ORANGE, BLUE, RED = "#5E666E", "#DADDD8", "#E58B21", "#3277C7", "#D64C5B"
POSITIONS = ["GK", "D", "M", "A"]
POSITION_LABELS = {"GK": "Goalkeepers", "D": "Defenders", "M": "Midfielders", "A": "Attackers"}
POSITION_COLORS = {"GK": "#D69B16", "D": "#3277C7", "M": "#1B9B63", "A": "#D34F60"}
AGE_BANDS = ["<=20", "21-23", "24-27", "28-31", "32+"]


def age_at_cutoff(value: object, cutoff: pd.Timestamp) -> int | None:
    birth = pd.to_datetime(value, errors="coerce")
    if pd.isna(birth):
        return None
    return int(cutoff.year - birth.year - ((cutoff.month, cutoff.day) < (birth.month, birth.day)))


def age_band(age: object) -> str | None:
    if pd.isna(age):
        return None
    age = int(age)
    return "<=20" if age <= 20 else "21-23" if age <= 23 else "24-27" if age <= 27 else "28-31" if age <= 31 else "32+"


def snapshot() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    players = pd.read_parquet(DATA / "players.parquet")
    profiles = pd.read_parquet(DATA / "player_profiles_uaefa.parquet")
    matches = pd.read_parquet(DATA / "matches.parquet")
    appearances = pd.read_parquet(DATA / "appearances.parquet")
    clubs = pd.read_parquet(DATA / "clubs.parquet")
    cutoff = pd.to_datetime(matches["match_date"], errors="coerce").max()
    players["player_id"] = players["player_id"].astype(str)
    profiles["player_id"] = profiles["player_id"].astype(str)
    players = players.merge(profiles[["player_id", "birth_date_official"]], on="player_id", how="left")
    appearances["player_id"] = appearances["player_id"].astype(str)
    appearances["club_id"] = appearances["club_id"].astype(str)
    latest = appearances.merge(matches[["match_id", "match_date"]], on="match_id", how="left")
    latest["match_date"] = pd.to_datetime(latest["match_date"], errors="coerce")
    latest = latest.sort_values("match_date").drop_duplicates("player_id", keep="last")
    clubs["club_id"] = clubs["club_id"].astype(str)
    players = players.merge(latest[["player_id", "club_id"]], on="player_id", how="left")
    players["club_id"] = players["club_id"].astype(str)
    players = players.merge(clubs[["club_id", "club_name", "crest_file"]], on="club_id", how="left")
    players["birth_date_official"] = pd.to_datetime(players["birth_date_official"], errors="coerce")
    players["age"] = players["birth_date_official"].map(lambda value: age_at_cutoff(value, cutoff))
    players["birth_year"] = players["birth_date_official"].dt.year
    players["age_band"] = players["age"].map(age_band)
    players["position"] = players["position"].fillna("-")
    players["player_status"] = players["player_status"].fillna("Not published").astype(str).str.strip()
    players["nationality_category"] = players["nationality_category"].fillna("Not published").astype(str).str.strip()
    return players, matches, appearances, cutoff


def rounded_vertical(ax: plt.Axes, labels: list[str], values: list[float], colors_: list[str], width: float = 0.62) -> list[FancyBboxPatch]:
    patches = []
    for index, (value, color) in enumerate(zip(values, colors_)):
        patch = FancyBboxPatch((index - width / 2, 0), width, float(value), boxstyle=f"round,pad=0,rounding_size={width * .20}", linewidth=0, facecolor=color)
        ax.add_patch(patch)
        patches.append(patch)
    ax.set_xlim(-0.65, len(labels) - 0.35)
    ax.set_xticks(range(len(labels)), labels)
    return patches


def rounded_horizontal(ax: plt.Axes, labels: list[str], values: list[float], colors_: list[str], height: float = 0.56) -> list[FancyBboxPatch]:
    patches = []
    for index, (value, color) in enumerate(zip(values, colors_)):
        patch = FancyBboxPatch((0, index - height / 2), float(value), height, boxstyle=f"round,pad=0,rounding_size={height * .22}", linewidth=0, facecolor=color)
        ax.add_patch(patch)
        patches.append(patch)
    ax.set_ylim(-0.7, len(labels) - 0.3)
    ax.set_yticks(range(len(labels)), labels)
    return patches


def chart_base(ax: plt.Axes, title: str, note: str = "", horizontal: bool = False) -> None:
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=15)
    if note:
        ax.text(0, 1.015, note, transform=ax.transAxes, fontsize=7.7, color=MUTED, va="bottom")
    ax.spines[["top", "right", "left" if not horizontal else "bottom"]].set_visible(False)
    ax.grid(axis="x" if horizontal else "y", color="#E8EAE6", linewidth=.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors="#46505A", labelsize=8)


def save_competition_charts(players: pd.DataFrame) -> dict[str, Path]:
    TMP.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    age = players["age_band"].value_counts().reindex(AGE_BANDS, fill_value=0)
    fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor="white")
    bars = rounded_vertical(ax, age.index.tolist(), age.values.tolist(), [YELLOW, "#E7B918", "#C8950B", "#96700A", "#5B4A16"])
    chart_base(ax, "Age distribution", "Official UAEFA birth dates; count and share of the pool")
    ax.set_ylim(0, age.max() * 1.20)
    for bar, value in zip(bars, age.values):
        ax.text(bar.get_x() + bar.get_width()/2, value + 2, f"{value}\n{value/len(players):.0%}", ha="center", fontsize=8, fontweight="bold")
    fig.tight_layout(); outputs["age"] = TMP / "age.png"; fig.savefig(outputs["age"], dpi=190, bbox_inches="tight"); plt.close(fig)

    means = players.dropna(subset=["age"]).groupby("position")["age"].agg(["mean", "count"]).reindex(POSITIONS).dropna()
    fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor="white")
    bars = rounded_vertical(ax, means.index.tolist(), means["mean"].tolist(), [POSITION_COLORS.get(p, MUTED) for p in means.index])
    chart_base(ax, "Mean age by position", "Official age at the current data cut-off")
    ax.set_ylim(0, max(40, means["mean"].max()+7))
    for bar, (mean, count) in zip(bars, means[["mean", "count"]].itertuples(index=False, name=None)):
        ax.text(bar.get_x()+bar.get_width()/2, mean+.55, f"{mean:.1f}\nn={count}", ha="center", fontsize=8, fontweight="bold")
    fig.tight_layout(); outputs["position_age"] = TMP / "position_age.png"; fig.savefig(outputs["position_age"], dpi=190, bbox_inches="tight"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.0), facecolor="white")
    counts = players["nationality_category"].value_counts().sort_values()
    bars = rounded_horizontal(ax, counts.index.tolist(), counts.values.tolist(), [GOLD] * len(counts))
    chart_base(ax, "Published UAEFA category", "Player registration category as published by UAEFA", horizontal=True)
    ax.set_xlim(0, counts.max()*1.23)
    for bar, value in zip(bars, counts.values):
        ax.text(value+2, bar.get_y()+bar.get_height()/2, f"{value}  |  {value/len(players):.0%}", va="center", fontsize=8, fontweight="bold")
    fig.tight_layout(); outputs["nationality"] = TMP / "nationality.png"; fig.savefig(outputs["nationality"], dpi=190, bbox_inches="tight"); plt.close(fig)

    matrix = pd.crosstab(players["nationality_category"], players["player_status"]).reindex(columns=["Professional", "Amateur"], fill_value=0)
    matrix["total"] = matrix.sum(axis=1); matrix = matrix.sort_values("total")
    fig, ax = plt.subplots(figsize=(7.2, 4.0), facecolor="white")
    y = list(range(len(matrix)))
    for status, offset, color in [("Professional", -.17, GREEN), ("Amateur", .17, ORANGE)]:
        values = (matrix[status] / matrix["total"] * 100).fillna(0)
        for index, value in enumerate(values):
            patch = FancyBboxPatch((0, index+offset-.12), float(value), .24, boxstyle="round,pad=0,rounding_size=.10", linewidth=0, facecolor=color)
            ax.add_patch(patch)
            if value:
                ax.text(min(value+1.6, 96), index+offset, f"{value:.0f}%", va="center", fontsize=7.4, fontweight="bold", color=INK)
    ax.set_yticks(y, matrix.index); ax.set_ylim(-.7, len(matrix)-.3); ax.set_xlim(0, 108)
    chart_base(ax, "Professional and amateur mix", "Share within each UAEFA category; green = Professional, orange = Amateur", horizontal=True)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    fig.tight_layout(); outputs["status"] = TMP / "status.png"; fig.savefig(outputs["status"], dpi=190, bbox_inches="tight"); plt.close(fig)

    matrix = pd.crosstab(players["age_band"], players["position"]).reindex(index=AGE_BANDS, columns=POSITIONS, fill_value=0)
    fig, ax = plt.subplots(figsize=(7.2, 3.5), facecolor="white")
    image = ax.imshow(matrix.values, cmap="YlGn", aspect="auto")
    ax.set_title("Age and position matrix", loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=15)
    ax.text(0, 1.015, "Registered players by age band and playing line", transform=ax.transAxes, fontsize=7.7, color=MUTED, va="bottom")
    ax.set_xticks(range(len(POSITIONS)), POSITIONS); ax.set_yticks(range(len(AGE_BANDS)), AGE_BANDS)
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]): ax.text(column, row, str(matrix.iloc[row, column]), ha="center", va="center", fontweight="bold", color=INK)
    fig.colorbar(image, ax=ax, fraction=.035, pad=.025, label="Players")
    fig.tight_layout(); outputs["heatmap"] = TMP / "heatmap.png"; fig.savefig(outputs["heatmap"], dpi=190, bbox_inches="tight"); plt.close(fig)
    return outputs


def save_team_dashboard(name: str, squad: pd.DataFrame) -> Path:
    """One deep, visual club profile with only rounded-end bar marks."""
    safe_name = "".join(char if char.isalnum() else "_" for char in name)
    path = TMP / f"team_{safe_name}.png"
    fig, axes = plt.subplots(2, 2, figsize=(10.7, 7.25), facecolor="#FCFCF9")
    fig.subplots_adjust(hspace=.56, wspace=.42, left=.08, right=.96, bottom=.09, top=.90)
    total = len(squad)
    position = squad["position"].value_counts().reindex(POSITIONS, fill_value=0)
    bars = rounded_vertical(axes[0, 0], position.index.tolist(), position.values.tolist(), [POSITION_COLORS[p] for p in position.index])
    chart_base(axes[0, 0], "Squad shape", "Count and share by playing line")
    axes[0, 0].set_ylim(0, max(position.max()*1.27, 4))
    for bar, value in zip(bars, position.values): axes[0, 0].text(bar.get_x()+bar.get_width()/2, value+.38, f"{value}\n{value/total:.0%}", ha="center", fontsize=8, fontweight="bold")

    age = squad["age_band"].value_counts().reindex(AGE_BANDS, fill_value=0)
    bars = rounded_vertical(axes[0, 1], age.index.tolist(), age.values.tolist(), [YELLOW, "#E7B918", "#C8950B", "#96700A", "#5B4A16"])
    chart_base(axes[0, 1], "Age profile", "Official UAEFA birth dates")
    axes[0, 1].set_ylim(0, max(age.max()*1.30, 4))
    for bar, value in zip(bars, age.values):
        if value: axes[0, 1].text(bar.get_x()+bar.get_width()/2, value+.30, f"{value}\n{value/total:.0%}", ha="center", fontsize=8, fontweight="bold")

    status = squad["player_status"].value_counts().reindex(["Professional", "Amateur"], fill_value=0)
    bars = rounded_horizontal(axes[1, 0], status.index.tolist(), status.values.tolist(), [GREEN, ORANGE])
    chart_base(axes[1, 0], "Registration status", "Published UAEFA registration field", horizontal=True)
    axes[1, 0].set_xlim(0, max(status.max()*1.30, 4))
    for bar, value in zip(bars, status.values): axes[1, 0].text(value+.25, bar.get_y()+bar.get_height()/2, f"{value}  |  {value/total:.0%}", va="center", fontsize=8, fontweight="bold")

    category = squad["nationality_category"].value_counts().sort_values()
    palette = [GOLD, "#D9A816", "#E2BD4C", "#92711F", "#6A5422", "#4D4231"]
    bars = rounded_horizontal(axes[1, 1], category.index.tolist(), category.values.tolist(), palette[:len(category)])
    chart_base(axes[1, 1], "UAEFA category", "Published registration classification", horizontal=True)
    axes[1, 1].set_xlim(0, max(category.max()*1.30, 4))
    for bar, value in zip(bars, category.values): axes[1, 1].text(value+.23, bar.get_y()+bar.get_height()/2, f"{value}  |  {value/total:.0%}", va="center", fontsize=7.5, fontweight="bold")
    fig.suptitle(f"{name.upper()} | SQUAD STRUCTURE", x=.08, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.savefig(path, dpi=190, bbox_inches="tight", facecolor=fig.get_facecolor()); plt.close(fig)
    return path


def player_totals(players: pd.DataFrame, appearances: pd.DataFrame) -> pd.DataFrame:
    apps = appearances.copy(); apps["player_id"] = apps["player_id"].astype(str)
    apps["started"] = pd.to_numeric(apps["started"], errors="coerce").fillna(0)
    apps["has_played"] = pd.to_numeric(apps["has_played"], errors="coerce").fillna(0)
    minute_in = pd.to_numeric(apps["minute_in"], errors="coerce").fillna(0)
    minute_out = pd.to_numeric(apps["minute_out"], errors="coerce").fillna(0)
    minutes = pd.Series(0.0, index=apps.index)
    minutes.loc[apps["started"].eq(1)] = minute_out.where(minute_out.gt(0), 90).loc[apps["started"].eq(1)]
    sub = apps["started"].ne(1) & apps["has_played"].eq(1)
    minutes.loc[sub] = (minute_out.where(minute_out.gt(0), 90) - minute_in).loc[sub].clip(lower=0)
    apps["minutes"] = minutes
    agg = apps.groupby("player_id").agg(matches=("match_id", "nunique"), minutes=("minutes", "sum"), starts=("started", "sum"))
    events = pd.read_parquet(DATA / "events.parquet"); events["player_id"] = events["player_id"].astype(str)
    for event, column in [("goal", "goals"), ("ycard", "yellows"), ("rcard", "reds")]:
        series = events.loc[events["event_type"].eq(event)].groupby("player_id").size().rename(column)
        agg = agg.join(series, how="left")
    return players.merge(agg.reset_index(), on="player_id", how="left").fillna({"matches": 0, "minutes": 0, "starts": 0, "goals": 0, "yellows": 0, "reds": 0})


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle("cover_kicker", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=colors.HexColor(YELLOW), alignment=TA_CENTER),
        "cover_title": ParagraphStyle("cover_title", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=29, leading=33, textColor=colors.white, alignment=TA_CENTER),
        "cover_sub": ParagraphStyle("cover_sub", parent=sample["Normal"], fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor("#D5DDD8"), alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", parent=sample["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor(INK), spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=sample["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor(GREEN), spaceBefore=6, spaceAfter=5),
        "body": ParagraphStyle("body", parent=sample["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=colors.HexColor("#343B42"), spaceAfter=7),
        "small": ParagraphStyle("small", parent=sample["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED)),
        "metric": ParagraphStyle("metric", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=19, leading=20, textColor=colors.HexColor(INK), alignment=TA_CENTER),
        "metric_label": ParagraphStyle("metric_label", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=6.1, leading=7.2, textColor=colors.HexColor(MUTED), alignment=TA_CENTER),
        "rank_name": ParagraphStyle("rank_name", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=10.3, textColor=colors.HexColor(INK)),
        "rank_value": ParagraphStyle("rank_value", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=8, textColor=colors.HexColor(INK), alignment=TA_CENTER),
    }


def metric(value: str, label: str, s: dict[str, ParagraphStyle]) -> Table:
    card = Table([[Paragraph(value, s["metric"])], [Paragraph(label, s["metric_label"])]], colWidths=[3.95*cm], rowHeights=[.72*cm, .88*cm])
    card.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F6F7F3")), ("BOX", (0,0), (-1,-1), .7, colors.HexColor(LINE)), ("LINEBEFORE", (0,0), (0,-1), 3, colors.HexColor(YELLOW)), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    return card


def footer(canvas, doc) -> None:
    canvas.saveState(); canvas.setStrokeColor(colors.HexColor(YELLOW)); canvas.setLineWidth(2); canvas.line(1.7*cm, 1.25*cm, A4[0]-1.7*cm, 1.25*cm)
    canvas.setFillColor(colors.HexColor(MUTED)); canvas.setFont("Helvetica", 7.5); canvas.drawString(1.7*cm, .82*cm, "Al Wasl Football Intelligence | UAE First Division 2026/27")
    canvas.drawRightString(A4[0]-1.7*cm, .82*cm, str(doc.page)); canvas.restoreState()


def full_cover(canvas, doc, back: bool = False) -> None:
    """Draw a true full-bleed cover, rather than a card placed on an A4 page."""
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor(DEEP))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor(YELLOW))
    canvas.rect(0, 0, .18 * cm, height, fill=1, stroke=0)
    if BRAND.exists():
        canvas.drawImage(str(BRAND), width / 2 - 1.45 * cm, height / 2 + (0 if back else 2.1 * cm), width=2.9 * cm, height=2.9 * cm, preserveAspectRatio=True, mask="auto")
    if not back:
        canvas.setFillColor(colors.HexColor(YELLOW)); canvas.setFont("Helvetica-Bold", 10)
        canvas.drawCentredString(width / 2, height / 2 + .95 * cm, "AL WASL FOOTBALL INTELLIGENCE")
        canvas.setFillColor(colors.white); canvas.setFont("Helvetica-Bold", 28)
        canvas.drawCentredString(width / 2, height / 2 + .10 * cm, "UAE FIRST DIVISION")
        canvas.drawCentredString(width / 2, height / 2 - .88 * cm, "CATEGORY INTELLIGENCE REPORT")
        canvas.setFillColor(colors.HexColor("#D5DDD8")); canvas.setFont("Helvetica", 11)
        canvas.drawCentredString(width / 2, height / 2 - 1.75 * cm, "A board-ready view of squad structure, player age and registration context")
        canvas.drawCentredString(width / 2, height / 2 - 2.38 * cm, "Season 2026/27 | Matchday 7 | Data cut-off 18 Oct 2026")
    canvas.restoreState()


def player_image(value: object, width: float = .8*cm) -> object:
    path = ROOT / str(value) if pd.notna(value) else None
    # Keep original portrait proportions inside a square slot; never stretch faces.
    return Image(str(path), width=width, height=width, kind="proportional") if path and path.exists() else Spacer(width, width)


def ranking_panel(title: str, subtitle: str, data: pd.DataFrame, value_column: str, value_label: str, s: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(f"<b>{title.upper()}</b><br/><font size=7 color='#5E666E'>{subtitle}</font>", s["body"])]]
    for rank, (_, row) in enumerate(data.iterrows(), 1):
        crest_path = ROOT / str(row["crest_file"]) if pd.notna(row.get("crest_file")) else None
        crest = Image(str(crest_path), width=.42*cm, height=.42*cm) if crest_path and crest_path.exists() else Spacer(.42*cm,.42*cm)
        detail = f"<b>{rank}. {row.get('shortname_en') or row.get('name_en')}</b><br/><font size=6.6 color='#5E666E'>{row.get('club_name','-')} | {row.get('position','-')} | Born {int(row['birth_year']) if pd.notna(row.get('birth_year')) else '-'} | Age {int(row['age']) if pd.notna(row.get('age')) else '-'}</font>"
        value = f"<b>{int(row[value_column])}</b><br/><font size=6.2 color='#5E666E'>{value_label[:3]}</font>"
        rows.append([Table([[player_image(row.get("photo_file"), .62*cm), Paragraph(detail, s["rank_name"]), crest, Paragraph(value, s["rank_name"])]], colWidths=[.82*cm, 12.1*cm, .62*cm, 2.25*cm])])
    panel = Table(rows, colWidths=[16.7*cm], rowHeights=[.82*cm]+[.76*cm]*len(data))
    panel.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F4F6F1")), ("BOX", (0,0), (-1,-1), .7, colors.HexColor(LINE)), ("INNERGRID", (0,1), (-1,-1), .35, colors.HexColor(LINE)), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    return panel


def club_ranking_panel(title: str, subtitle: str, data: pd.DataFrame, value_column: str, value_label: str, s: dict[str, ParagraphStyle]) -> Table:
    """A compact, symmetric Top 5 panel for an individual club profile."""
    rows = [[Paragraph(f"<b>{title.upper()}</b><br/><font size=6.5 color='#5E666E'>{subtitle}</font>", s["small"]), "", ""]]
    for rank, (_, row) in enumerate(data.head(5).iterrows(), 1):
        name = row.get("shortname_en") or row.get("name_en") or "Not published"
        birth = int(row["birth_year"]) if pd.notna(row.get("birth_year")) else "-"
        age = int(row["age"]) if pd.notna(row.get("age")) else "-"
        detail = Paragraph(
            f"<b>{rank}. {name}</b><br/><font size=5.8 color='#5E666E'>{row.get('position', '-')} | Born {birth} | Age {age}</font>",
            s["rank_name"],
        )
        # The panel title names the measure; the fixed numeric column only
        # needs the value, which prevents narrow labels from wrapping.
        value = Paragraph(f"<b>{int(row[value_column])}</b>", s["rank_value"])
        rows.append([player_image(row.get("photo_file"), .57*cm), detail, value])
    while len(rows) < 6:
        rows.append(["", "", ""])
    panel = Table(rows, colWidths=[.78*cm, 4.87*cm, 1.05*cm], rowHeights=[.82*cm] + [.72*cm] * 5)
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F1")),
        ("SPAN", (0, 0), (-1, 0)),
        ("BOX", (0, 0), (-1, -1), .65, colors.HexColor(LINE)),
        ("INNERGRID", (0, 1), (-1, -1), .3, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return panel


def team_header(name: str, squad: pd.DataFrame, s: dict[str, ParagraphStyle]) -> Table:
    crest_file = squad["crest_file"].dropna().iloc[0] if squad["crest_file"].notna().any() else None
    crest_path = ROOT / str(crest_file) if crest_file else None
    crest = Image(str(crest_path), width=1.45*cm, height=1.45*cm) if crest_path and crest_path.exists() else Spacer(1.45*cm, 1.45*cm)
    age = squad["age"].dropna()
    content = Paragraph(f"<font color='#B98400' size=7><b>CLUB PROFILE</b></font><br/><br/><font size=17><b>{name.upper()}</b></font><br/><font color='#5E666E' size=8>{len(squad)} registered players | Mean age {age.mean():.1f} | Median age {age.median():.1f}</font>", s["body"])
    table = Table([[crest, content]], colWidths=[2.1*cm, 14.6*cm], rowHeights=[2.0*cm])
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F7F2")), ("LINEBEFORE", (0,0), (0,-1), 4, colors.HexColor(YELLOW)), ("BOX", (0,0), (-1,-1), .6, colors.HexColor(LINE)), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 12)]))
    return table


def build() -> Path:
    TMP.mkdir(parents=True, exist_ok=True); OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    players, matches, appearances, cutoff = snapshot(); dated = players.dropna(subset=["age"]); teams = players.dropna(subset=["club_name"])
    totals = player_totals(players, appearances)
    charts = save_competition_charts(players)
    latest_week = int(pd.to_numeric(matches["week_no"], errors="coerce").max())
    s = styles(); doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=1.7*cm, leftMargin=1.7*cm, topMargin=1.45*cm, bottomMargin=1.65*cm)
    story: list[object] = []
    total = len(players); professional = int(players["player_status"].eq("Professional").sum()); amateur = int(players["player_status"].eq("Amateur").sum())
    uae = int(players["nationality_category"].isin(["UAE Citizen", "UAE Born", "Citizen Child"]).sum())

    # The cover is drawn directly on the page canvas so it fills the full A4.
    story += [Spacer(0, .1*cm), PageBreak()]

    story += [Paragraph("Contents", s["h1"])]
    toc = [["01", "Competition at a glance", "3"], ["02", "Age architecture", "4"], ["03", "Registration and UAEFA category", "5"], ["04", "Player rankings", "6–7"], ["05", "Individual club profiles", "8–22"], ["06", "Methodology", "23"]]
    contents = Table(toc, colWidths=[1.5*cm, 12.5*cm, 2.7*cm], rowHeights=[1.1*cm]*len(toc))
    contents.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F7F2")), ("GRID", (0,0), (-1,-1), .5, colors.HexColor(LINE)), ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 10), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor(GOLD)), ("ALIGN", (2,0), (2,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10)]))
    story += [Paragraph("A visual guide to the competition's player register, prepared from the current local UAEFA snapshot.", s["body"]), Spacer(0,.5*cm), contents, Spacer(0,.6*cm), Paragraph("Reading note", s["h2"]), Paragraph("The report uses the UAEFA registration fields as published. Percentages accompany the absolute count so team profiles remain comparable despite different squad-pool sizes. All bar charts use rounded ends to improve scanability and retain a consistent visual language.", s["body"]), PageBreak()]

    story += [Paragraph("Competition at a glance", s["h1"]), Paragraph("The current data pool combines official player records with the latest available First Division match reports. These cards set the context before the deeper age, registration and club-level pages.", s["body"])]
    cards = [metric(str(total), "REGISTERED PLAYERS", s), metric(str(teams["club_name"].nunique()), "CLUBS REPRESENTED", s), metric(str(len(matches)), "MATCHES AVAILABLE", s), metric(str(latest_week), "LATEST MATCHDAY", s), metric(f"{dated['age'].median():.1f}", "MEDIAN AGE", s), metric(f"{professional/total:.0%}", "PROFESSIONAL", s), metric(f"{amateur/total:.0%}", "AMATEUR", s), metric(f"{uae/total:.0%}", "EXPLICITLY UAE-LABELLED CATEGORIES", s)]
    story += [Table([cards[:4], cards[4:]], colWidths=[4.25*cm]*4, rowHeights=[2.15*cm,2.15*cm]), Spacer(0,.55*cm), Paragraph("Role mix", s["h2"])]
    role_cards=[]
    for pos in POSITIONS:
        count = int(players["position"].eq(pos).sum()); mean = dated.loc[dated["position"].eq(pos), "age"].mean()
        role_cards.append(metric(str(count), f"{POSITION_LABELS[pos].upper()} | {count/total:.0%} | MEAN AGE {mean:.1f}", s))
    story += [Table([role_cards], colWidths=[4.25*cm]*4), Spacer(0,.45*cm), Paragraph("The category has complete official birth-date coverage in this local snapshot. Club assignment follows each player's latest available First Division match report, maintaining a competition-specific view when a federation profile has since changed.", s["body"]), PageBreak()]

    story += [Paragraph("Age architecture", s["h1"]), Paragraph("The upper chart shows the player pool by age band. The lower chart puts the age profile of each playing line side by side, helping an analyst distinguish development, prime and experience concentration before filtering individual targets.", s["body"]), Image(str(charts["age"]), width=17.0*cm, height=7.55*cm), Spacer(0,.25*cm), Image(str(charts["position_age"]), width=17.0*cm, height=7.55*cm), Spacer(0,.2*cm), Image(str(charts["heatmap"]), width=17.0*cm, height=8.25*cm), PageBreak()]

    story += [Paragraph("Registration and UAEFA category", s["h1"]), Paragraph("UAEFA status and category fields are presented without reclassification. The percentage labels in the professional/amateur chart make the mix within each category directly readable, while the second graphic preserves the absolute scale of the published categories.", s["body"]), Image(str(charts["nationality"]), width=17.0*cm, height=8.6*cm), Spacer(0,.2*cm), Image(str(charts["status"]), width=17.0*cm, height=8.6*cm), PageBreak()]

    rankings = [("Most minutes", "Top five by calculated minutes from UAEFA match reports", totals.sort_values(["minutes", "matches"], ascending=False).head(5), "minutes", "MINUTES"), ("Youngest players with minutes", "Top five youngest players with recorded playing time", totals.loc[totals["minutes"].gt(0)].sort_values(["age", "minutes"], ascending=[True, False]).head(5), "age", "AGE"), ("Goals", "Top five scorers in official match events", totals.sort_values(["goals", "minutes"], ascending=False).head(5), "goals", "GOALS"), ("Yellow cards", "Top five by official yellow-card events", totals.sort_values(["yellows", "minutes"], ascending=False).head(5), "yellows", "YELLOW"), ("Red cards", "Top five by official red-card events", totals.sort_values(["reds", "minutes"], ascending=False).head(5), "reds", "RED")]
    for start in range(0, len(rankings), 3):
        story += [Paragraph("Player rankings", s["h1"]), Paragraph("Each ranking combines the official event or appearance total with a visual identity card: player photo, club crest, position, birth year and age at the current cut-off.", s["body"])]
        ranking_stack = Table(
            [[ranking_panel(title, subtitle, frame, column, label, s)] for title, subtitle, frame, column, label in rankings[start:start+3]],
            colWidths=[16.7*cm],
        )
        ranking_stack.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story += [ranking_stack]
        if start+3 < len(rankings): story.append(PageBreak())

    groups = [(name, frame.copy()) for name, frame in teams.groupby("club_name", sort=True)]
    for name, squad in groups:
        chart = save_team_dashboard(name, squad)
        pro = int(squad["player_status"].eq("Professional").sum())
        mean_age = squad["age"].mean()
        club_players = totals.loc[totals["club_name"].eq(name)].copy()
        youngest_with_minutes = club_players.loc[club_players["minutes"].gt(0)].sort_values(["age", "minutes"], ascending=[True, False]).head(5)
        top_scorers = club_players.loc[club_players["goals"].gt(0)].sort_values(["goals", "minutes"], ascending=False).head(5)
        rankings = Table([[
            club_ranking_panel("Youngest with minutes", "Top 5 youngest players with recorded minutes", youngest_with_minutes, "age", "AGE", s),
            club_ranking_panel("Top scorers", "Top 5 official scorers in the current data set", top_scorers, "goals", "GOALS", s),
        ]], colWidths=[8.35*cm, 8.35*cm])
        rankings.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [
            PageBreak(), team_header(name, squad, s), Spacer(0,.35*cm),
            Table([[metric(str(len(squad)), "REGISTERED PLAYERS", s), metric(f"{mean_age:.1f}", "MEAN AGE", s), metric(f"{pro/len(squad):.0%}", "PROFESSIONAL", s), metric(f"{squad['age'].median():.1f}", "MEDIAN AGE", s)]], colWidths=[4.25*cm]*4),
            Spacer(0,.28*cm),
            Paragraph("A club-level profile makes the structural questions visible before individual scouting begins: how the squad is distributed by line, where its age sits, and which registration categories make up the player pool. Values are both absolute and proportional to the club's registered players.", s["body"]),
            Image(str(chart), width=17.0*cm, height=9.95*cm), Spacer(0,.18*cm), rankings,
        ]

    story += [PageBreak(), Paragraph("Methodology", s["h1"]), Paragraph(f"Statistical cut-off: {cutoff.strftime('%d %B %Y')}. Available First Division matches: {len(matches)}. Latest matchday: {latest_week}. Unit of analysis: a player in the local UAEFA First Division dataset. Player club assignment follows the latest available match-report appearance. Age is calculated at the stated cut-off using UAEFA's official published date of birth. Minutes are calculated from starting status and recorded substitution timings, using 90 minutes when a recorded player has no exit time. This report is descriptive and should be combined with match context, video and qualitative recruitment assessment.", s["body"]), PageBreak(), Spacer(0, .1*cm)]

    def later_page(canvas, document) -> None:
        if document.page == 24:
            full_cover(canvas, document, back=True)
        else:
            footer(canvas, document)

    doc.build(story, onFirstPage=full_cover, onLaterPages=later_page)
    return OUTPUT


if __name__ == "__main__":
    print(build())
