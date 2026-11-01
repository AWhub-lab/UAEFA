"""Build a single self-contained, responsive index.html that mirrors the Streamlit app.

The data comes from ``app.load_data()`` (so the page always shows exactly what the app shows,
including UAEFA profiles and validated BeSoccer enrichment), the styles from ``app.CSS`` and the
logic from ``scripts/index_app/*.js``. Club crests and player portraits are embedded as base64,
so the result is one file that opens offline on a computer, a tablet or a phone.

    python3 scripts/build_index_html.py [--output index.html]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)  # Streamlit warns when imported outside `streamlit run`

import app  # noqa: E402  (reuses the exact loading, patching and styling of the app)

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_JS = ["core.js", "charts.js", "impact.js", "pages_standings.js", "pages_teams.js", "pages_players.js", "pages_profile.js"]
JS_FILES = SHARED_JS + ["main.js"]


def uri(path: Path, kind: str) -> str:
    image = Image.open(path).convert("RGBA")
    buffer = io.BytesIO()
    if kind == "photo":
        image.thumbnail((150, 200))
        image.convert("RGB").save(buffer, format="WEBP", quality=72, method=6)
        mime = "image/webp"
    else:
        image.thumbnail((140, 140))
        image.save(buffer, format="PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


def clean(value: object) -> object:
    """NaN/NA to None and numpy scalars to Python, so the JSON stays plain."""
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def text(value: object) -> str | None:
    value = clean(value)
    return None if value is None else str(value)


def number(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def history(raw: object) -> list[dict]:
    try:
        return json.loads(raw) if isinstance(raw, str) else []
    except json.JSONDecodeError:
        return []


def build() -> tuple[dict, dict[str, str]]:
    data = app.load_data(app.ACTIVE_COMPETITION.key)
    images: dict[str, str] = {"alwasl": uri(app.BRAND_ROOT / "al_wasl.png", "crest")}

    clubs = []
    for club in data["clubs"].itertuples(index=False):
        path = app.asset_path(club.crest_file)
        if path:
            images[f"c{club.club_id}"] = uri(path, "crest")
        clubs.append({"id": str(club.club_id), "name": club.club_name, "crest": f"c{club.club_id}", "elo": number(club.elo_current)})

    players = []
    for p in data["players"].itertuples(index=False):
        path = app.asset_path(p.photo_file)
        key = None
        if path:
            key = f"p{p.player_id}"
            images[key] = uri(path, "photo")
        players.append({
            "id": str(p.player_id), "name": p.name_en, "short": (p.shortname_en or "").strip(), "nameOff": text(p.name_en_official), "ar": text(p.name_ar),
            "pos": text(p.position), "cat": (text(p.nationality_category) or "").strip(), "natId": text(p.nationality_id), "nat": text(p.nationality_official),
            "status": text(p.player_status), "team": text(p.team_en), "birth": text(p.birth_date_official), "photo": key,
            "mv": number(p.market_value_current_eur), "mvh": history(p.market_value_history_json),
            "elo": number(p.elo_current), "eloh": history(p.elo_history_json),
        })

    matches = [{
        "id": str(m.match_id), "week": int(m.week_no), "date": m.match_date, "time": m.match_time, "hc": str(m.home_club_id), "ac": str(m.away_club_id),
        "hn": m.home_club_name, "an": m.away_club_name, "hs": int(m.home_score), "as": int(m.away_score), "h1": text(m.home_score_h1), "a1": text(m.away_score_h1),
        "pg": text(m.playground), "att": text(m.attendance),
    } for m in data["matches"].itertuples(index=False)]

    events = [{
        "m": str(e.match_id), "o": int(e.event_order), "t": e.event_type, "min": text(e.minute), "side": text(e.club_side), "club": text(e.club_id),
        "pid": text(e.player_id), "pname": text(e.player_name), "ipid": text(e.in_player_id), "iname": text(e.in_player_name), "gt": text(e.goal_type_id),
    } for e in data["events"].itertuples(index=False)]

    apps = [{
        "m": str(a.match_id), "club": str(a.club_id), "pid": str(a.player_id), "started": bool(a.started), "played": bool(a.has_played), "dorsal": text(a.dorsal),
        "pos": text(a.position), "fpos": text(a.formation_position), "cap": bool(a.captain), "mi": number(a.minute_in), "mo": number(a.minute_out),
    } for a in data["appearances"].itertuples(index=False)]

    staff = [{
        "m": str(s.match_id), "club": str(s.club_id), "person": str(s.person_id), "name": s.name_en, "role": s.role, "order": number(s.role_order) or 0,
    } for s in data["staff"].itertuples(index=False)]

    payload = {
        "season": app.SEASON, "clubs": clubs, "players": players, "matches": matches, "events": events, "apps": apps, "staff": staff,
        "tr": app.TRANSLATIONS, "flags": app.COUNTRY_FLAGS, "uaeFlag": app._FLAG_SVG,
    }
    return payload, images


STUB_JS = r"""
const fs = require("fs"), dir = process.argv[2];
const els = {};
class El {
  constructor(id) { this.id = id; this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {}; this.classList = {toggle() {}, add() {}, remove() {}}; }
  querySelector() { return new El(); } querySelectorAll() { return []; } addEventListener() {} removeAttribute() {} closest() { return null; } remove() {}
}
global.document = {getElementById: id => els[id] || (els[id] = new El(id)), documentElement: {lang: "en"}, addEventListener() {}, querySelectorAll() { return []; }, title: ""};
els.data = Object.assign(new El("data"), {textContent: fs.readFileSync(dir + "/data.json", "utf8")});
els.imgs = Object.assign(new El("imgs"), {textContent: fs.readFileSync(dir + "/imgs.json", "utf8")});
global.window = {addEventListener() {}, scrollTo() {}};
global.location = {hash: ""};
global.localStorage = {getItem: () => null, setItem() {}};
"""
STUB_END = 'process.stdout.write(JSON.stringify({bar: els.bar.innerHTML, controls: els.controls.innerHTML, app: els.app.innerHTML, footer: els.footer.innerHTML, bnav: els.bnav.innerHTML}));'


def prerender(data_json: str, images: dict[str, str], script: str) -> dict[str, str]:
    """Draw the first screen (Standings) once at build time.

    Viewers that do not run JavaScript (iOS Quick Look, WhatsApp/Files previews) then still show
    real content instead of a blank page; the live script replaces it as soon as it runs.
    """
    node = shutil.which("node")
    if not node:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "data.json").write_text(data_json, encoding="utf-8")
        (folder / "imgs.json").write_text(json.dumps(images), encoding="utf-8")
        (folder / "bundle.js").write_text(STUB_JS + script + "\n" + STUB_END, encoding="utf-8")
        done = subprocess.run([node, str(folder / "bundle.js"), str(folder)], capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        print("prerender skipped:", done.stderr.strip()[:300])
        return {}
    parts = json.loads(done.stdout)
    return {key: re.sub(r'data-k="([^"]+)"', lambda m: f'src="{images[m.group(1)]}"' if m.group(1) in images else "", html) for key, html in parts.items()}


def static_edition(payload: dict, images: dict[str, str], lang: str, output: Path, min_full: int = 270) -> None:
    """The same app drawn once as plain HTML (native <details>, no JavaScript) for viewers that cannot run scripts."""
    script = "\n".join((SCRIPT_DIR / "index_app" / name).read_text(encoding="utf-8") for name in SHARED_JS + ["static_doc.js"])
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to build the static edition")
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "data.json").write_text(data_json, encoding="utf-8")
        (folder / "imgs.json").write_text(json.dumps(images), encoding="utf-8")
        (folder / "bundle.js").write_text(STUB_JS + script, encoding="utf-8")
        done = subprocess.run([node, str(folder / "bundle.js"), str(folder), lang, str(min_full)], capture_output=True, text=True, timeout=900)
        if done.returncode != 0:
            raise SystemExit(f"static build failed: {done.stderr[-600:]}")
        body = (folder / "out.html").read_text(encoding="utf-8")

    used: set[str] = set()

    def as_class(match: re.Match) -> str:
        before, key, after = match.group(1), match.group(2), match.group(3)
        attrs = before + after
        cls = re.search(r'class="([^"]*)"', attrs)
        style = re.search(r'style="([^"]*)"', attrs)
        classes = cls.group(1).split() if cls else []
        if key == "alwasl" and not classes:
            classes = ["brandlogo"]
        classes += ["imc" if key.startswith("c") or key == "alwasl" else "imp", f"k{key}"]
        used.add(key)
        return f'<i class="{" ".join(classes)}"{f" style=" + chr(34) + style.group(1) + chr(34) if style else ""}></i>'

    body = re.sub(r'<img([^>]*?)data-k="([^"]+)"([^>]*)>', as_class, body)
    image_css = "\n".join(
        f'.k{key}{{background-image:url("{images[key]}")}}' for key in sorted(used) if key in images
    )
    css = re.sub(r"</?style>", "", app.CSS).strip()
    extra = (SCRIPT_DIR / "index_app" / "extra.css").read_text(encoding="utf-8") + "\n" + (SCRIPT_DIR / "index_app" / "static.css").read_text(encoding="utf-8")
    template = (SCRIPT_DIR / "index_app" / "static_template.html").read_text(encoding="utf-8")
    page = (
        template.replace("__LANG__", lang).replace("__FAVICON__", images["alwasl"])
        .replace("__CSS__", css + "\n" + extra + "\n" + image_css).replace("__BODY__", body)
    )
    output.write_text(page, encoding="utf-8")
    print(f"{output} -> {output.stat().st_size / 1e6:.2f} MB · static edition ({lang}) · {len(used)} images shared")


def render(output: Path) -> None:
    payload, images = build()
    css = re.sub(r"</?style>", "", app.CSS).strip()
    extra_css = (SCRIPT_DIR / "index_app" / "extra.css").read_text(encoding="utf-8")
    script = "\n".join((SCRIPT_DIR / "index_app" / name).read_text(encoding="utf-8") for name in JS_FILES)
    template = (SCRIPT_DIR / "index_app" / "template.html").read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    static = prerender(data_json, images, script)
    page = (
        template.replace("__CSS__", css + "\n" + extra_css)
        .replace("__BAR__", static.get("bar", ""))
        .replace("__CONTROLS__", static.get("controls", ""))
        .replace("__APP__", static.get("app", ""))
        .replace("__FOOTER__", static.get("footer", ""))
        .replace("__BNAV__", static.get("bnav", ""))
        .replace("__FAVICON__", images["alwasl"])
        .replace("__DATA__", data_json.replace("</", "<\\/"))
        .replace("__IMGS__", json.dumps(images, separators=(",", ":")))
        .replace("__SCRIPT__", script)
    )
    output.write_text(page, encoding="utf-8")
    print(f"{output} -> {output.stat().st_size / 1e6:.2f} MB · {len(payload['players'])} players · {len(payload['matches'])} matches · {len(images)} images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "index.html")
    parser.add_argument("--static", action="store_true", help="also build the no-JavaScript editions (en and es)")
    parser.add_argument("--min-full", type=int, default=270, help="static edition: full player profile from this many minutes")
    args = parser.parse_args()
    render(args.output)
    if args.static:
        payload_, images_ = build()
        for language in ("en", "es"):
            static_edition(payload_, images_, language, ROOT / f"al_wasl_uae_snapshot_{language}.html", args.min_full)
