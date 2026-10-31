/* ===================================================================== shared page pieces */
function banner(page, trail) {
  const p = PAGES[page];
  const items = [["UAE First Division", "#/standings"], [SEASON, "#/standings"], [scopeLabel(), "#/matches"]];
  if (trail.length > 1) items.push([p.es, `#/${page}`], [trail[trail.length - 1], null]); else items.push([p.es, null]);
  const crumbs = items.map(([label, href], i) => `${i ? '<span class="sep">›</span>' : ""}${href ? `<a href="${href}">${esc(label)}</a>` : `<b>${esc(label)}</b>`}`).join("");
  const mark = trail.length === 1 ? `<img class="watermark" data-k="alwasl" alt="">` : "";
  return `<div class="crumbs">${crumbs}</div>
  <div class="banner"><div><div class="kicker">Sección ${p.num} · Al Wasl Football Intelligence</div><h1>${esc(trail.length > 1 ? trail[trail.length - 1] : p.es)}</h1><p>${esc(p.sub)}</p></div><div class="num">${p.num}</div>${mark}</div>`;
}

function rankingCard(p, rank, value, label, color, suffix) {
  const bl = birthLabel(p.birth, scope(S.week).refDate) || "Sin dato";
  const card = `<div class="card ranking" style="--r:${color}"><span class="rank-no">${rank}</span><div class="rank-main"><div class="rank-photo">${portrait(p)}</div>
    <div class="rank-info"><div class="rank-name">${esc(p.short)}</div><div class="rank-club">${crest(p.club_id, 18)}<span>${esc(p.club_name)}</span>${posBadge(p.pos)}</div></div></div>
    <div class="rank-foot"><div class="rank-age">Nacimiento<b>${esc(bl)}</b></div><div class="rank-value">${thousands(value)}${suffix}<small>${esc(label)}</small></div></div></div>`;
  return cardWithButton(card, `#/players/${p.id}`, "Ver ficha del jugador");
}
function rankingsBlock(list, key, title = "Rankings", hint = "Rendimiento individual · foto, club, posición, nacimiento y métrica oficial UAEFA") {
  const byMin = (a, b) => b.Minutes - a.Minutes;
  const tabs = [
    ["Más minutos", list.filter(p => p.Minutes > 0).sort((a, b) => b.Minutes - a.Minutes || b.Matches - a.Matches), "Minutes", "Minutos", "#4c9aff", "'"],
    ["Más jóvenes", list.filter(p => p.Minutes > 0 && p.Edad !== null).sort((a, b) => a.Edad - b.Edad || byMin(a, b)), "Minutes", "Minutos", "#2fd27a", "'"],
    ["Goles", list.filter(p => p.Goals > 0).sort((a, b) => b.Goals - a.Goals || byMin(a, b)), "Goals", "Goles", "#ae7800", ""],
    ["Amarillas", list.filter(p => p.Yellow > 0).sort((a, b) => b.Yellow - a.Yellow || byMin(a, b)), "Yellow", "Amarillas", "#f5a524", ""],
    ["Rojas", list.filter(p => p.Red > 0).sort((a, b) => b.Red - a.Red || byMin(a, b)), "Red", "Rojas", "#ff5c6c", ""],
  ];
  if (STATIC.on) {
    const blocks = tabs.map(([label, rows, field, lab, color, suffix], i) => `<details class="sdet" ${i === 0 ? "open" : ""}><summary>${label}</summary>${rows.length
      ? grid(5, rows.slice(0, 10).map((p, k) => rankingCard(p, k + 1, p[field], lab, color, suffix)).join(""), "rk")
      : empty("No hay registros suficientes para este ranking en el periodo seleccionado.")}</details>`).join("");
    return `${section(title, hint)}${blocks}`;
  }
  const active = S.tabs[key] ?? 0;
  const head = tabs.map(([label], i) => `<button data-tab="${key}" data-i="${i}" class="${i === active ? "on" : ""}">${label}</button>`).join("");
  const panes = tabs.map(([, rows, field, label, color, suffix], i) => `<div class="tabpane ${i === active ? "on" : ""}" data-pane="${key}" data-i="${i}">${rows.length
    ? grid(5, rows.slice(0, 10).map((p, k) => rankingCard(p, k + 1, p[field], label, color, suffix)).join(""), "rk")
    : empty("No hay registros suficientes para este ranking en el periodo seleccionado.")}</div>`).join("");
  return `${section(title, hint)}<div class="subtabs">${head}</div>${panes}`;
}

/* ========================================================================== standings */
function standingsTable(rows) {
  const head = ["#", "Club", "PJ", "G", "E", "P", "GF", "GC", "DG", "Pts"].map((l, i) => `<div class="pc${i >= 2 && i <= 5 ? ` c${i}` : ""}">${l}</div>`).join("");
  const body = rows.map(r => {
    const gd = r.GD > 0 ? "pos-up" : r.GD < 0 ? "neg" : "dim";
    return `<a class="prow${r.rank === 1 ? " lead" : ""}" href="#/teams/${r.club}"><div class="pc rank">${r.rank}</div><div class="pc club">${crest(r.club, 38)}<span>${esc(r.name)}</span></div>
      <div class="pc c2">${r.P}</div><div class="pc c3">${r.W}</div><div class="pc c4">${r.D}</div><div class="pc c5">${r.L}</div><div class="pc">${r.GF}</div><div class="pc">${r.GA}</div><div class="pc ${gd}">${r.GD > 0 ? "+" : ""}${r.GD}</div><div class="pc pts">${r.Pts}</div></a>`;
  }).join("");
  return `<div class="scroll-x"><div class="ptable"><div class="prow phead">${head}</div>${body}</div></div>`;
}
function bumpyBlock(sc) {
  const {weeks, byClub} = standingsEvolution(S.week);
  if (weeks.length < 2) return `<div class="empty">${t("La evolución de posiciones aparecerá cuando haya al menos dos jornadas disputadas.")}</div>`;
  const order = sc.standings.map(r => r.club);
  if (S.bumpyWeek !== S.week) { S.bumpy = order.slice(0, 5); S.bumpyWeek = S.week; }
  const palette = ["#ae7800", "#256abf", "#148a54", "#c85d24", "#8b5bb8"];
  const colors = {};
  S.bumpy.forEach((id, i) => { colors[id] = palette[i]; });
  if (STATIC.on) {
    const legend = S.bumpy.map(id => `<span class="pickchip on" style="--bc:${colors[id]}">${crest(id, 20)}${esc(clubs[id].name)}</span>`).join("");
    return `<div class="pickrow">${legend}</div>${chartbox(bumpyChart({weeks, byClub, selected: S.bumpy, colors, teamCount: Math.max(D.clubs.length, 1)}))}`;
  }
  const chips = order.map(id => {
    const on = S.bumpy.includes(id);
    return `<button class="pickchip ${on ? "on" : ""}" data-bumpy="${id}" style="--bc:${colors[id] || "#9aa0a6"}">${crest(id, 20)}${esc(clubs[id].name)}</button>`;
  }).join("");
  const chart = S.bumpy.length
    ? chartbox(bumpyChart({weeks, byClub, selected: S.bumpy, colors, teamCount: Math.max(D.clubs.length, 1)}))
    : `<div class="empty">${t("Selecciona entre uno y cinco equipos para comparar su posición.")}</div>`;
  return `<div class="flab">${t("Comparar equipos")} · ${t("Máximo cinco equipos para mantener el gráfico legible.")}</div><div class="pickrow">${chips}</div>${chart}`;
}
function pageStandings() {
  const sc = scope(S.week), goals = sc.events.filter(e => e.t === "goal").length;
  return {detail: null, trail: ["Clasificación"], html: banner("standings", ["Clasificación"]) +
    kpis([["Partidos", sc.matches.length, "#ffd21f"], ["Goles", goals, "#ff5c6c"], ["Media por partido", (goals / Math.max(sc.matches.length, 1)).toFixed(2), "#2fd27a"], ["Jugadores", sc.players.length, "#4c9aff"]]) +
    section("Clasificación provisional", `Acumulada hasta ${scopeLabel()}`) + standingsTable(sc.standings) +
    section("Evolución de posiciones", "Top 5 de la jornada por defecto · compara hasta cinco equipos") + `<div id="bumpy">${bumpyBlock(sc)}</div>` +
    rankingsBlock(sc.players, "league")};
}

/* =========================================================================== matches */
function eventCell(e, side) {
  let icon, body, cls = "";
  if (e.t === "goal") { icon = '<span class="ic ball">⚽</span>'; body = `<b>${esc(e.pname)}</b>`; cls = " goal"; }
  else if (e.t === "ycard") { icon = '<span class="ic y"></span>'; body = esc(e.pname); }
  else if (e.t === "rcard") { icon = '<span class="ic r"></span>'; body = esc(e.pname); }
  else { icon = '<span class="ic sub">⇄</span>'; body = `<span><b>${esc(e.iname)}</b><small>${L("por", "for")} ${esc(e.pname)}</small></span>`; }
  return `<div class="cell ${side}${cls}">${side === "h" ? body + icon : icon + body}</div>`;
}
function timelineHtml(evs) {
  const rows = [...evs].sort((a, b) => num(a.min) - num(b.min) || a.o - b.o).map(e => {
    const home = e.side === "H";
    return `<div class="ev">${home ? eventCell(e, "h") : '<div class="cell empty"></div>'}<div class="min">${esc(e.min)}'</div>${home ? '<div class="cell empty"></div>' : eventCell(e, "a")}</div>`;
  }).join("");
  return rows ? `<div class="tl">${rows}</div>` : empty("Sin eventos registrados.");
}
function pitchHtml(roster, subsOut, refDate) {
  const key = a => parseInt((String(a.fpos).match(/\d+/) || [0])[0], 10);
  const starters = roster.filter(a => a.started);
  return `<div class="pitch">${POSITION_LINES.map(code => {
    const g = starters.filter(a => a.pos === code).sort((a, b) => key(a) - key(b) || num(a.dorsal) - num(b.dorsal));
    if (!g.length) return "";
    return `<div class="line">${g.map(a => {
      const p = players[a.pid] || {}, bl = birthLabel(p.birth, refDate);
      return `<a class="pl" href="#/players/${a.pid}"><div class="av">${portrait(p, "round")}<span class="num">${esc(a.dorsal)}</span>${a.cap ? '<span class="cap">C</span>' : ""}${subsOut[a.pid] ? `<span class="out">↓${esc(subsOut[a.pid])}'</span>` : ""}</div>
        <div class="pn"><span class="player-name">${esc(p.short)}</span>${bl ? `<small>${esc(bl)}</small>` : ""}</div></a>`;
    }).join("")}</div>`;
  }).join("")}</div>`;
}
function benchHtml(roster, refDate) {
  const subs = roster.filter(a => !a.started).sort((a, b) => num(a.dorsal) - num(b.dorsal));
  return `<div class="bench">${subs.map(a => {
    const p = players[a.pid] || {}, bl = birthLabel(p.birth, refDate);
    return `<a class="bn${a.played ? " played" : ""}" href="#/players/${a.pid}"><div class="av">${portrait(p, "round")}</div><div class="t"><b>${esc(p.short)}</b><small>#${esc(a.dorsal)} · ${posBadge(a.pos)}${bl ? ` · ${esc(bl)}` : ""}</small></div>${a.played && a.mi ? `<span class="dn">↑${esc(a.mi)}'</span>` : ""}</a>`;
  }).join("")}</div>`;
}
function pageMatch(id) {
  const list = weekMatches(S.week), sel = list.find(m => m.id === id) || list[0];
  if (!sel) return {detail: null, trail: ["Partidos"], html: banner("matches", ["Partidos"]) + empty("Sin eventos registrados.")};
  const label = `${sel.hn} ${sel.hs}-${sel.as} ${sel.an}`;
  const rows = list.map(m => `<div class="cwrap">${matchRowHtml(m, sel.id)}
    <a class="btn ${m.id === sel.id ? "primary" : ""}" href="#/matches/${m.id}">${m.id === sel.id ? "Acta abierta" : "Abrir acta"}</a></div>`).join("");
  return {detail: label, trail: ["Partidos", label], html: banner("matches", ["Partidos", label]) +
    section(scopeLabel(), "Resultados y acceso a cada acta") + `<div class="match-list">${rows}</div>` + matchReportHtml(sel)};
}
const matchRowHtml = (m, selId) => `<a class="card match-row${m.id === selId ? " sel" : ""}" href="#/matches/${m.id}"><div class="date">${esc(m.date)}<br>${esc(m.time)}</div>
    <div class="team home"><span>${esc(m.hn)}</span>${crest(m.hc, 42)}</div><div class="result">${m.hs}<i>:</i>${m.as}</div><div class="team">${crest(m.ac, 42)}<span>${esc(m.an)}</span></div><div class="meta">${esc(m.pg)}</div></a>`;
function matchReportHtml(sel) {
  const evs = eventsOf(scope(S.week)).get(sel.id) || [];
  const gl = {H: [], A: []};
  evs.filter(e => e.t === "goal").sort((a, b) => a.o - b.o).forEach(e => gl[e.side].push(`⚽ ${esc(e.pname)} ${esc(e.min)}'`));
  const board = `<div class="board" style="margin-top:1.4rem"><div class="row"><div class="team">${crest(sel.hc, 116)}<h3>${esc(sel.hn)}</h3><div class="scorers">${gl.H.join("<br>")}</div></div>
    <div class="mid"><div class="when">${t("Jornada")} ${sel.week} · ${esc(sel.date)} · ${esc(sel.time)}</div><div class="big">${sel.hs}<i>:</i>${sel.as}</div>
    <div class="info"><span class="chip y">HT ${esc(sel.h1)}-${esc(sel.a1)}</span><span class="chip">${esc(sel.pg)}</span><span class="chip">${t("Asistencia")} ${esc(sel.att)}</span></div></div>
    <div class="team">${crest(sel.ac, 116)}<h3>${esc(sel.an)}</h3><div class="scorers">${gl.A.join("<br>")}</div></div></div></div>`;
  const subsOut = Object.fromEntries(evs.filter(e => e.t === "subs").map(e => [e.pid, e.min]));
  const sides = [[sel.hc, sel.hn], [sel.ac, sel.an]];
  const lineups = sides.map(([cid, name]) => {
    const roster = scope(S.week).apps.filter(a => a.m === sel.id && a.club === cid);
    return `<div><div class="teamhead">${crest(cid, 44)}<h3>${esc(name)}</h3></div>${pitchHtml(roster, subsOut, sel.date)}${benchHtml(roster, sel.date)}</div>`;
  }).join("");
  const staff = sides.map(([cid, name]) => `<div><div class="teamhead">${crest(cid, 34)}<h3 style="font-size:1.25rem">${esc(name)}</h3></div><div class="staff">${staffCells(scope(S.week).staff.filter(s => s.m === sel.id && s.club === cid).sort((a, b) => a.order - b.order))}</div></div>`).join("");
  return board + section("Cronología", "Eventos oficiales del acta") + timelineHtml(evs) +
    section("Alineaciones", "Once inicial sobre el campo y banquillo") + `<div class="two">${lineups}</div>` +
    section("Cuerpo técnico", "Staff registrado en el acta") + `<div class="two">${staff}</div>`;
}
