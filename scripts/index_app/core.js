"use strict";
window.addEventListener("error", e => { const b = document.getElementById("booterr"); if (b) b.textContent = "Error: " + e.message; });
/* ===================================================================== data */
const D = JSON.parse(document.getElementById("data").textContent);
const IMG = JSON.parse(document.getElementById("imgs").textContent);
const SEASON = D.season;
const POSITIONS = {GK: ["Goalkeeper", "#f5a524"], D: ["Defense", "#4c9aff"], M: ["Midfielder", "#2fd27a"], A: ["Attacker", "#ff5c6c"]};
const POSITION_LINES = ["A", "M", "D", "GK"];
const GRID_PAGE = 24;
const STATIC = {on: false, minFull: 270};  // true while building the no-JavaScript snapshot
const INTERVALS = ["01-15'", "16-30'", "31-45'", "46-60'", "61-75'", "76-90+'"];
const ICON = {
  standings: '<path d="M6 4h12v4a6 6 0 0 1-12 0V4zM9 20h6M12 14v6M6 6H3v2a3 3 0 0 0 3 3M18 6h3v2a3 3 0 0 1-3 3"/>',
  matches: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M12 5v14M3 12h4M17 12h4"/>',
  teams: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/>',
  players: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
};
const PAGES = {
  standings: {es: "Clasificación", num: "01", sub: "Clasificación y goleadores de la jornada"},
  matches: {es: "Partidos", num: "02", sub: "Actas, alineaciones y cronología de cada partido"},
  teams: {es: "Equipos", num: "03", sub: "Club por club: plantilla vista y cuerpo técnico"},
  players: {es: "Jugadores", num: "04", sub: "Catálogo y ficha individual de cada jugador"},
};

const clubs = Object.fromEntries(D.clubs.map(c => [c.id, c]));
const players = Object.fromEntries(D.players.map(p => [p.id, p]));
const matchById = Object.fromEntries(D.matches.map(m => [m.id, m]));
const WEEKS = [...new Set(D.matches.map(m => m.week))].sort((a, b) => a - b);
const MAX_WEEK = WEEKS[WEEKS.length - 1];

/* ============================================================== state & i18n */
const S = {lang: "en", week: MAX_WEEK, shown: GRID_PAGE, prev: "#/standings", bumpy: null, bumpyWeek: null, tabs: {}, F: {q: "", pos: "Todas", cat: "Todas", club: "Todos", ageMin: "", ageMax: "", minMin: 0, status: "Todos", played: false}, X: {x: "minutes", y: "goals", pos: ["GK", "D", "M", "A"], nulls: true}};
try {
  const saved = JSON.parse(localStorage.getItem("uaeHub") || "{}");
  if (saved.lang === "en" || saved.lang === "es") S.lang = saved.lang;
} catch (e) { /* storage can be blocked */ }
const persist = () => { try { localStorage.setItem("uaeHub", JSON.stringify({lang: S.lang})); } catch (e) { /* ignore */ } };

const TR = Object.entries(D.tr).sort((a, b) => b[0].length - a[0].length);
const t = s => S.lang === "en" ? (D.tr[s] ?? s) : s;
const L = (es, en) => S.lang === "en" ? en : es;
/* mirrors the app's translate_markup: Spanish source markup, English on demand */
function tr(markup) {
  if (S.lang !== "en") return markup;
  let out = markup;
  for (const [es, en] of TR) if (out.includes(es)) out = out.split(es).join(en);
  return out;
}
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const num = v => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
const isNum = v => v !== null && v !== undefined && Number.isFinite(Number(v));
const fnum = (v, d = 2, signed = false) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  let s = (signed && v > 0 ? "+" : "") + v.toFixed(d);
  return S.lang === "en" ? s : s.replace(".", ",");
};
const thousands = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

/* ============================================================ season scopes */
const scopeCache = new Map();
function ageAt(birth, ref) {
  if (!birth || !ref) return null;
  const b = new Date(birth), r = new Date(ref);
  if (isNaN(b) || isNaN(r)) return null;
  let age = r.getFullYear() - b.getFullYear();
  if (r.getMonth() < b.getMonth() || (r.getMonth() === b.getMonth() && r.getDate() < b.getDate())) age--;
  return age;
}
const birthLabel = (birth, ref) => {
  if (!birth) return null;
  const age = ageAt(birth, ref), year = new Date(birth).getFullYear();
  return age !== null ? `${year} (${age} ${t("años")})` : String(year);
};
function appMinutes(a) {
  if (a.started) return a.mo > 0 ? a.mo : 90;
  if (a.played) return Math.max((a.mo > 0 ? a.mo : 90) - (a.mi || 0), 0);
  return 0;
}
function buildStandings(matches) {
  const rows = new Map(D.clubs.map(c => [c.id, {club: c.id, name: c.name, P: 0, W: 0, D: 0, L: 0, GF: 0, GA: 0, Pts: 0}]));
  for (const m of matches) {
    for (const [id, gf, ga] of [[m.hc, m.hs, m.as], [m.ac, m.as, m.hs]]) {
      const r = rows.get(id);
      r.P++; r.GF += gf; r.GA += ga;
      if (gf > ga) { r.W++; r.Pts += 3; } else if (gf === ga) { r.D++; r.Pts += 1; } else r.L++;
    }
  }
  const out = [...rows.values()].map(r => ({...r, GD: r.GF - r.GA}));
  out.sort((a, b) => b.Pts - a.Pts || b.GD - a.GD || b.GF - a.GF || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  out.forEach((r, i) => { r.rank = i + 1; });
  return out;
}
function scope(week) {
  if (scopeCache.has(week)) return scopeCache.get(week);
  const matches = D.matches.filter(m => m.week <= week).sort((a, b) => (a.date + a.time + a.id).localeCompare(b.date + b.time + b.id));
  const ids = new Set(matches.map(m => m.id));
  const apps = D.apps.filter(a => ids.has(a.m));
  const events = D.events.filter(e => ids.has(e.m));
  const staff = D.staff.filter(s => ids.has(s.m));
  const refDate = matches.reduce((mx, m) => m.date > mx ? m.date : mx, "");
  const tot = new Map();
  for (const a of apps) {
    let r = tot.get(a.pid);
    if (!r) { r = {Matches: 0, Starts: 0, Minutes: 0, ms: new Set(), club_id: a.club, dorsal: null, Goals: 0, Yellow: 0, Red: 0}; tot.set(a.pid, r); }
    if (a.played) r.Matches++;
    if (a.started) r.Starts++;
    r.Minutes += appMinutes(a);
    r.ms.add(a.m);
    if (r.dorsal === null && a.dorsal) r.dorsal = a.dorsal;
  }
  for (const e of events) {
    const r = e.pid && tot.get(e.pid);
    if (!r) continue;
    if (e.t === "goal") r.Goals++; else if (e.t === "ycard") r.Yellow++; else if (e.t === "rcard") r.Red++;
  }
  const list = [];
  for (const [pid, r] of tot) {
    const p = players[pid];
    if (!p) continue;
    list.push({...p, Matches: r.Matches, Starts: r.Starts, Minutes: r.Minutes, Squad: r.ms.size, club_id: r.club_id, dorsal: r.dorsal, Goals: r.Goals, Yellow: r.Yellow, Red: r.Red,
      club_name: clubs[r.club_id] ? clubs[r.club_id].name : "-", Edad: ageAt(p.birth, refDate), teamElo: clubs[r.club_id] ? clubs[r.club_id].elo : null});
  }
  // individual Elo percentile among the visible players (average rank for ties, like pandas rank(pct=True))
  const withElo = list.filter(p => isNum(p.elo)).sort((a, b) => a.elo - b.elo);
  const pct = new Map();
  for (let i = 0; i < withElo.length;) {
    let j = i; while (j < withElo.length && withElo[j].elo === withElo[i].elo) j++;
    const avg = (i + 1 + j) / 2;
    for (let k = i; k < j; k++) pct.set(withElo[k].id, avg / withElo.length);
    i = j;
  }
  list.forEach(p => { p.eloPct = pct.has(p.id) ? pct.get(p.id) : null; });
  const sc = {week, matches, ids, apps, events, staff, refDate, players: list, byId: Object.fromEntries(list.map(p => [p.id, p])), standings: buildStandings(matches)};
  scopeCache.set(week, sc);
  return sc;
}
const weekMatches = week => D.matches.filter(m => m.week === week).sort((a, b) => (a.date + a.time + a.id).localeCompare(b.date + b.time + b.id));
const scopeLabel = () => `${t("Jornada")} ${S.week}`;

/* ================================================================ components */
const UAE_FLAG = `<img class="flag" src="data:image/svg+xml;base64,${btoa(D.uaeFlag)}" alt="UAE" title="United Arab Emirates">`;
const brand = () => `<img data-k="alwasl" alt="Al Wasl">`;
function crest(id, size = 36) {
  const c = clubs[id];
  return c && IMG[c.crest] ? `<img class="crest" data-k="${c.crest}" style="--s:${size}px" alt="">` : `<span class="crest crest-empty" style="--s:${size}px"></span>`;
}
function crestElo(id, size = 120) {
  const c = clubs[id];
  const badge = c && isNum(c.elo) ? `<span class="elo-orb">Elo<br><b>${Math.round(c.elo)}</b></span>` : "";
  return `<div class="crest-elo" style="--crest-size:${size}px">${crest(id, size)}${badge}</div>`;
}
const portrait = (p, extra = "") => p && p.photo && IMG[p.photo] ? `<div class="ph ${extra}"><img data-k="${p.photo}" alt=""></div>` : `<div class="ph ${extra}"><span class="ph-empty">?</span></div>`;
function posBadge(code, full = false) {
  code = code ? String(code).trim() : "-";
  const [label, color] = POSITIONS[code] || [code, "#8b95a3"];
  return `<span class="pos" style="--c:${color}" title="${esc(label)}">${esc(full ? `${code} · ${label}` : code)}</span>`;
}
const marketValue = v => !isNum(v) ? null : v >= 1e6 ? `€${(v / 1e6).toFixed(2)}m` : `€${(v / 1e3).toFixed(0)}k`;
const isUaeCountry = c => ["united arab emirates", "u a e", "uae"].includes(String(c || "").trim().toLowerCase());
const countryFlag = c => !c ? "🌐" : (D.flags[String(c).trim().toLowerCase()] || "🌐");
function identityChips(p) {
  const label = p.nat ? String(p.nat) : String(p.cat || "-");
  if (isUaeCountry(label)) return `<span class="chip nat" title="Registro UAEFA · Nacionalidad: United Arab Emirates">${UAE_FLAG} UAEFA</span>`;
  return `<span class="chip nat">${UAE_FLAG} UAEFA</span><span class="country-flag" title="Nacionalidad: ${esc(label)}" aria-label="Nacionalidad: ${esc(label)}">${countryFlag(label)}</span>`;
}
function eloOrb(p) {
  if (!isNum(p.elo) || p.eloPct === null) return "";
  const bands = [[.2, "#d64558", "low band"], [.4, "#df7a32", "medium-low band"], [.6, "#c29400", "medium band"], [.8, "#6a9f2f", "medium-high band"], [1, "#148a54", "high band"]];
  let [, color, label] = bands[bands.length - 1];
  for (const b of bands) if (p.eloPct <= b[0]) { [, color, label] = b; break; }
  return `<span class="elo-player" style="--elo:${color}" title="Individual Elo · ${label}">${Math.round(p.elo)}</span>`;
}
const section = (title, hint = "") => `<div class="section"><h2>${esc(title)}</h2>${hint ? `<small>${esc(hint)}</small>` : ""}</div>`;
const kpis = items => `<div class="kpis" style="--n:${items.length}">${items.map(([l, v, c]) => `<div class="kpi" style="--k:${c}"><label>${esc(l)}</label><div>${v}</div></div>`).join("")}</div>`;
const grid = (cols, inner, cls = "") => `<div class="grid g${cols} ${cls}" style="--cols:${cols}">${inner}</div>`;
const staffCells = list => list.map(s => `<div class="sc2"><small>${esc(s.role)}</small><b>${esc(s.name)}</b></div>`).join("");
const empty = msg => `<div class="empty">${msg}</div>`;

function playerCard(p, href = null) {
  const posColor = (POSITIONS[String(p.pos || "").trim()] || ["", "#8b95a3"])[1];
  const dorsal = p.dorsal ? `<span class="dorsal">${esc(p.dorsal)}</span>` : "";
  const stats = `<div class="stat"><b>${p.Matches}</b><small>PJ</small></div><div class="stat"><b>${Math.round(p.Minutes)}</b><small>Min</small></div><div class="stat g"><b>${p.Goals}</b><small>Goles</small></div><div class="stat y"><b>${p.Yellow}</b><small>TA</small></div><div class="stat r"><b>${p.Red}</b><small>TR</small></div>`;
  const value = marketValue(p.mv);
  const enrich = value ? `<span class="chip ext">💰 ${esc(value)}</span>` : "";
  const bl = birthLabel(p.birth, scope(S.week).refDate);
  const birth = bl ? `<span class="age-inline">${esc(bl)}</span>` : "";
  return `<div class="card pcard" style="--pos-c:${posColor}"><div class="pc-head"><div class="thumb">${portrait(p)}${dorsal}</div>
    <div class="info"><div class="nm">${esc(p.short)}</div><div class="meta">${crest(p.club_id, 18)}<span>${esc(p.club_name)}</span>${birth}</div><div class="tags">${identityChips(p)}${enrich}</div></div>${eloOrb(p)}</div>
    <div class="stats">${stats}</div></div>`;
}
/* a card with the app's "View profile" button underneath; the whole thing is a link */
const cardWithButton = (inner, href, label = "Ver ficha") => STATIC.on ? inner : `<div class="cwrap"><a href="${href}" style="display:block">${inner}</a><a class="btn" href="${href}">${label}</a></div>`;
