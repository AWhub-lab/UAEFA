/* ============================================================================ teams */
function pageTeam(id) {
  const sc = scope(S.week);
  const list = [...D.clubs].sort((a, b) => a.name.localeCompare(b.name));
  const club = clubs[id] || list[0];
  const tiles = list.map(c => `<div class="cwrap"><a class="card ctile${c.id === club.id ? " sel" : ""}" href="#/teams/${c.id}">${crest(c.id, 64)}<b>${esc(c.name)}</b></a>
    <a class="btn ${c.id === club.id ? "primary" : ""}" href="#/teams/${c.id}">${c.id === club.id ? "Abierto" : "Ver club"}</a></div>`).join("");
  return {detail: club.name, trail: ["Equipos", club.name], html: banner("teams", ["Equipos", club.name]) +
    section(L(`Los ${list.length} clubes`, `${list.length} teams`), L("Elige un club para abrir su ficha", "Choose a club to open its profile")) + grid(7, tiles) + teamBodyHtml(sc, club)};
}
function teamBodyHtml(sc, club, withSquad = true, withRankings = true) {
  const st = sc.standings.find(r => r.club === club.id);
  const gd = teamGoalDifference(sc, club.id), iv = teamGoalIntervals(sc, club.id);
  const left = chartbox(divergingBars({cats: INTERVALS, up: {name: t("Goles a favor"), color: "#2fd27a", vals: iv.f}, down: {name: t("Goles en contra"), color: "#ff5c6c", vals: iv.a}}),
    t("GOLES POR TRAMOS DE 15' · A FAVOR ARRIBA / EN CONTRA ABAJO")) + legendRow([[t("Goles a favor"), "#2fd27a"], [t("Goles en contra"), "#ff5c6c"]]);
  const right = chartbox(gd.length ? goalDiffChart(gd, {title: t("Diferencia por jornada"), week: t("Jornada"), cum: t("Diferencia acumulada")}) : "", t("DIFERENCIA POR JORNADA Y ACUMULADA")) +
    legendRow([[t("Diferencia jornada"), "#2fd27a"], [t("Diferencia acumulada"), "#148a54"]]);
  const squad = sc.players.filter(p => p.club_id === club.id && p.Squad > 0).sort((a, b) => b.Minutes - a.Minutes || b.Goals - a.Goals || a.short.localeCompare(b.short));
  const groups = ["GK", "D", "M", "A"].map(code => {
    const g = squad.filter(p => p.pos === code);
    if (!g.length) return "";
    const [label, color] = POSITIONS[code];
    return `<div class="posgroup" style="--c:${color}">${posBadge(code)}<h3>${label}</h3><small>${g.length} jugadores</small></div>` +
      grid(3, g.map(p => cardWithButton(playerCard(p), `#/players/${p.id}`)).join(""));
  }).join("");
  const seen = new Set();
  const staff = sc.staff.filter(s => s.club === club.id).sort((a, b) => a.order - b.order).filter(s => !seen.has(s.person) && seen.add(s.person));
  return `<div class="banner" style="margin-top:1.4rem"><div class="clubhero">${crestElo(club.id, 120)}<div><div class="kicker">Ficha del club</div><h1 style="margin-bottom:0">${esc(club.name)}</h1></div></div></div>` +
    kpis([["Posición", `#${st.rank}`, "#ffd21f"], ["Puntos", st.Pts, "#ffd21f"], ["Goles a favor / en contra", `${st.GF} / ${st.GA}`, "#ff5c6c"], ["Diferencia", `${st.GD > 0 ? "+" : ""}${st.GD}`, "#2fd27a"]]) +
    section("Ritmo de gol", "Eventos y marcadores oficiales UAEFA") + `<div class="two3"><div>${left}</div><div>${right}${gd.length < 2 ? `<div class="empty" style="margin-top:.6rem">${L("Selecciona una jornada posterior en el selector superior para ver la evolución entre jornadas.", "Select a later matchday in the top selector to see progression across matchdays.")}</div>` : ""}</div></div>` +
    (withSquad ? section("Plantilla vista", `${squad.length} jugadores en acta · por posición y minutos`) + groups : "") +
    section("Cuerpo técnico", "Banquillo registrado en el acta") + `<div class="staff staff4">${staffCells(staff)}</div>` +
    (withRankings ? rankingsBlock(squad, `club_${club.id}`, `Rankings · ${club.name}`, "Rendimiento de la plantilla en el periodo seleccionado") : "");
}
