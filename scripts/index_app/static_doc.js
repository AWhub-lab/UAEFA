/* ============================================ static edition: the whole app drawn once, no JavaScript needed */
const STATIC_LANG = process.argv[3] || "en";
STATIC.on = true;
STATIC.minFull = Number(process.argv[4] || 270);  // full profile only from this many minutes (keeps the file light for phones)
S.lang = STATIC_LANG;
S.week = MAX_WEEK;

const plain = html => html.replace(/<a\b/g, "<div").replace(/<\/a>/g, "</div>").replace(/ href="#\/[^"]*"/g, "");
const sc = scope(MAX_WEEK);
const staticClubName = id => clubs[id].name;

function standingsSection() {
  const goals = sc.events.filter(e => e.t === "goal").length;
  return `<section id="s-standings">${banner("standings", ["Clasificación"])}` +
    kpis([["Partidos", sc.matches.length, "#ffd21f"], ["Goles", goals, "#ff5c6c"], ["Media por partido", (goals / Math.max(sc.matches.length, 1)).toFixed(2), "#2fd27a"], ["Jugadores", sc.players.length, "#4c9aff"]]) +
    section("Clasificación provisional", `Acumulada hasta ${scopeLabel()}`) + standingsTable(sc.standings) +
    section("Evolución de posiciones", "Top 5 de la jornada por defecto · compara hasta cinco equipos") + bumpyBlock(sc) +
    rankingsBlock(sc.players, "league") + `</section>`;
}
function matchesSection() {
  const blocks = WEEKS.slice().reverse().map(w => {
    S.week = w;
    const list = weekMatches(w);
    const items = list.map(m => `<details class="mdet"><summary>${matchRowHtml(m, "")}</summary><div class="rbody">${matchReportHtml(m)}</div></details>`).join("");
    S.week = MAX_WEEK;
    return `<details class="wdet" ${w === MAX_WEEK ? "open" : ""}><summary><span class="chev">▸</span>${t("Jornada")} ${w}<small>${list.length} ${L("partidos", "matches")}</small></summary><div class="match-list">${items}</div></details>`;
  }).join("");
  return `<section id="s-matches">${banner("matches", ["Partidos"])}${section(L("Todas las jornadas", "All matchdays"), L("Pulsa un partido para abrir su acta", "Tap a match to open its report"))}${blocks}</section>`;
}
function teamsSection() {
  const items = sc.standings.map(r => {
    const club = clubs[r.club];
    return `<details class="tdet"><summary><span class="chev">▸</span>${crest(club.id, 44)}<b>${esc(club.name)}</b><span class="chip y">#${r.rank}</span><span class="chip">${r.Pts} Pts</span><span class="chip">${r.GF}-${r.GA}</span></summary><div class="rbody">${teamBodyHtml(sc, club, false, false)}<div class="hint">${L("La plantilla de cada club está en la sección Jugadores.", "Each club's squad is in the Players section.")}</div></div></details>`;
  }).join("");
  return `<section id="s-teams">${banner("teams", ["Equipos"])}${section(L(`Los ${D.clubs.length} clubes`, `${D.clubs.length} teams`), L("Ordenados por clasificación · pulsa un club", "Sorted by standings · tap a club"))}${items}</section>`;
}
function scatterStatic() {
  const [xl, xf] = METRICS.minutes, [yl, yf] = METRICS.goals;
  const pts = sc.players.map(p => ({p, x: xf(p), y: yf(p)})).filter(o => o.x > 0 && o.y > 0);
  const data = pts.map(o => ({id: o.p.id, pos: o.p.pos, x: o.x, y: o.y, tip: `${o.p.name} · ${o.p.club_name} · ${o.p.pos} · ${birthLabel(o.p.birth, sc.refDate) || "—"} · ${Math.round(o.p.Minutes)}' · ${o.p.Goals} ${t("Goles")}`}));
  const {svg, mx, my} = scatterChart({pts: data, xLabel: t(xl), yLabel: t(yl), colors: SCATTER_COLORS});
  return `${section("Comparador de jugadores", "Minutos frente a goles · jugadores con ambos valores positivos")}${chartbox(svg)}${legendRow(["GK", "D", "M", "A"].map(c => [c, SCATTER_COLORS[c]]))}<div class="hint" style="text-transform:none;letter-spacing:0">${pts.length} / ${sc.players.length} ${t("jugadores visibles")} · ${t("Medias del gráfico")}: ${t(xl).toLowerCase()} ${mx.toFixed(1)} · ${t(yl).toLowerCase()} ${my.toFixed(1)}.</div>`;
}
function playersSection() {
  const clubList = [...D.clubs].sort((a, b) => a.name.localeCompare(b.name));
  const order = {GK: 0, D: 1, M: 2, A: 3};
  const groups = clubList.map(club => {
    const squad = sc.players.filter(p => p.club_id === club.id).sort((a, b) => (order[a.pos] ?? 9) - (order[b.pos] ?? 9) || b.Minutes - a.Minutes || a.short.localeCompare(b.short));
    let last = null, body = "";
    for (const p of squad) {
      if (p.pos !== last) { last = p.pos; const [label, color] = POSITIONS[p.pos] || [p.pos, "#8b95a3"]; body += `<div class="posgroup" style="--c:${color}">${posBadge(p.pos)}<h3>${label}</h3><small>${squad.filter(q => q.pos === p.pos).length} jugadores</small></div>`; }
      body += `<details class="pdet"><summary>${playerCard(p)}</summary><div class="rbody">${profileBodyHtml(sc, p, p.Minutes >= STATIC.minFull)}</div></details>`;
    }
    return `<details class="cdet"><summary><span class="chev">▸</span>${crest(club.id, 44)}<b>${esc(club.name)}</b><span class="chip">${squad.length} ${L("jugadores", "players")}</span></summary><div class="rbody">${body}</div></details>`;
  }).join("");
  return `<section id="s-players">${banner("players", ["Jugadores"])}${scatterStatic()}${section(L("Plantillas", "Squads"), L("Elige un club y luego un jugador para abrir su ficha", "Pick a club, then a player to open the profile"))}${groups}</section>`;
}

const doc = [standingsSection(), matchesSection(), teamsSection(), playersSection()].map(plain).join("\n");
const nav = Object.entries(PAGES).map(([k, p]) => `<a href="#s-${k}">${svgIconStatic(k)}<span>${t(p.es)}</span></a>`).join("");
function svgIconStatic(k) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`; }
const bar = `<div class="brand-left">${brand()}<div><div class="brand-title">Al Wasl <b>·</b> First Division Hub</div><div class="brand-sub">UAE First Division · Temporada ${SEASON}</div></div></div>
  <div class="brand-right"><div class="here"><i></i><span>${L("Instantánea estática", "Static snapshot")} · ${scopeLabel()}</span></div></div>`;
const footer = `<div class="fl">${brand()}</div><span>${t("Fuente: UAEFA public API")} · ${L("Instantánea estática: sin filtros ni selector de jornada. Fija la jornada", "Static snapshot: no filters or matchday selector. Fixed at matchday")} ${MAX_WEEK}.</span>`;
const note = L("Edición estática para ver en cualquier dispositivo, también en la vista previa de iOS. Pulsa los títulos para desplegar cada sección.", "Static edition for any device, including the iOS preview. Tap the headings to expand each section.");
const out = tr(`<header class="brandbar">${bar}</header><div class="wrap"><nav class="navtabs snav">${nav}</nav><div class="nojs" style="display:block">${note}</div>${doc}<footer class="footer">${footer}</footer></div>`);
require("fs").writeFileSync(process.argv[2] + "/out.html", out);
