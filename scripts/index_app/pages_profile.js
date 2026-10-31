/* ======================================================================= player profile */
const tone = (v, eps = 1e-4) => v === null || v === undefined || Number.isNaN(v) ? "tz" : v > eps ? "tp" : v < -eps ? "tn" : "tz";
const fold = (title, summary, body) => `<details class="fold" open><summary><span class="chev">▸</span><span class="ft">${title}</span><span class="fs">${summary}</span><span class="fh" data-open="${L("ocultar", "hide")}" data-closed="${L("ver", "show")}"></span></summary><div class="fbody">${body}</div></details>`;
const ifact = (label, value, sub = "", cls = "tz") => `<div class="ifact"><span>${label}</span><b class="${cls}">${value}</b>${sub ? `<em>${sub}</em>` : ""}</div>`;
const ifacts = (cells, columns = 3) => `<div class="ifacts" style="--c:${columns}">${cells.join("")}</div>`;
const icard = (title, sub, body, {span = 6, color = "#ffd21f", big = "", bigSub = "", bigCls = "tz"} = {}) =>
  `<div class="icard" style="--span:${span};--ic:${color}"><div class="ic-head"><div><h3>${title}</h3>${sub ? `<small>${sub}</small>` : ""}</div>${big !== "" ? `<div class="ic-big"><b class="${bigCls}">${big}</b><small>${bigSub}</small></div>` : ""}</div>${body}</div>`;
function cbar(label, value, scale, color, diverging, text) {
  let fill = "";
  if (value !== null && value !== undefined && !Number.isNaN(value)) {
    if (diverging) {
      const w = Math.min(Math.abs(value) / scale, 1) * 50, left = value >= 0 ? 50 : 50 - w;
      fill = `<i style="left:${left.toFixed(1)}%;width:${Math.max(w, 1.5).toFixed(1)}%;--col:${value >= 0 ? color : "#ff5c6c"}"></i>`;
    } else fill = `<i style="left:0;width:${(Math.min(Math.max(value, 0) / scale, 1) * 100).toFixed(1)}%;--col:${color}"></i>`;
  }
  return `<div class="cbar"><span>${label}</span><div class="tr${diverging ? " div" : ""}">${fill}</div><b class="${diverging ? tone(value) : "tz"}">${text}</b></div>`;
}
const cardico = c => `<span class="cardico ${c}"></span>`;

function seasonBlock(sc, p) {
  const mine = sc.apps.filter(a => a.pid === p.id).map(a => ({a, m: matchById[a.m]})).sort((x, y) => (x.m.date + x.m.time).localeCompare(y.m.date + y.m.time));
  const own = sc.events.filter(e => e.pid === p.id);
  let goals = 0, yellows = 0, reds = 0;
  const rows = mine.map(({a, m}) => {
    const home = m.hc === a.club, rivalId = home ? m.ac : m.hc, rival = home ? m.an : m.hn, gf = home ? m.hs : m.as, ga = home ? m.as : m.hs;
    const result = gf > ga ? "W" : gf === ga ? "D" : "L", minutes = appMinutes(a);
    const role = a.started ? L("Titular", "Starter") + (isNum(a.mo) && a.mo < 90 ? ` · ${L("sale", "off")} ${a.mo}'` : "")
      : a.played ? `${L("Entra", "On")} ${a.mi}'` + (isNum(a.mo) ? ` · ${L("sale", "off")} ${a.mo}'` : "") : L("No jugó", "Did not play");
    const ev = own.filter(e => e.m === m.id), og = ev.filter(e => e.t === "goal" && e.gt === OWN_GOAL).length, sc_ = ev.filter(e => e.t === "goal").length - og;
    const y = ev.filter(e => e.t === "ycard").length, r = ev.filter(e => e.t === "rcard").length;
    goals += sc_; yellows += y; reds += r;
    const icons = "⚽".repeat(sc_) + '<span class="chip">OG</span>'.repeat(og) + cardico("y").repeat(y) + cardico("r").repeat(r);
    return `<a class="srow" href="#/matches/${m.id}"><span class="j">J${m.week}</span><span class="ha chip ${home ? "home" : "away"}">${home ? L("Casa", "Home") : L("Fuera", "Away")}</span>
      <span class="rival">${crest(rivalId, 30)}<span>${esc(rival)}</span></span><span class="res">${gf}-${ga}<span class="wdl ${result}">${{W: L("V", "W"), D: L("E", "D"), L: L("D", "L")}[result]}</span></span>
      <span class="role">${role}</span><span class="mbar"><span class="t"><i style="width:${Math.min(minutes / 90 * 100, 100).toFixed(0)}%"></i></span><b>${minutes}'</b></span><span class="evs">${icons}</span></a>`;
  });
  const played = mine.filter(x => x.a.played), totalMin = mine.reduce((s, x) => s + appMinutes(x.a), 0), perMatch = played.length ? Math.round(totalMin / played.length) : 0;
  const summary = icard(L("Resumen", "Summary"), `${mine.length} ${L("convocatorias", "call-ups")}`, ifacts([
    ifact(L("Jugados", "Played"), played.length), ifact(L("Titular", "Starts"), mine.filter(x => x.a.started).length), ifact(L("Goles", "Goals"), goals, "", goals ? "tp" : "tz"),
    ifact(L("Tarjetas", "Cards"), `${cardico("y")} ${yellows} &nbsp;${cardico("r")} ${reds}`)], 4), {span: 12, color: "#2fd27a", big: `${totalMin}'`, bigSub: `${perMatch}' ${L("por partido", "per match")}`});
  const list = `<div class="icard" style="--ic:#ffd21f"><div class="ic-head"><div><h3>${L("Partidos", "Matches")}</h3><small>${L("Ordenados por fecha", "Sorted by date")}</small></div></div><div style="border-top:1px solid var(--line)">${rows.join("") || `<div class="empty-in">${L("Sin participaciones registradas.", "No appearances recorded.")}</div>`}</div></div>`;
  return fold(L("Temporada", "Season"), `${played.length} ${L("partidos", "matches")} · ${totalMin}' · ${goals} ${L("goles", "goals")}`, `<div class="season-top"><div class="impact-grid">${summary}</div></div>${list}`);
}

function impactBlock(sc, p) {
  const r = playerImpact(sc, p.id, p.club_id);
  if (!r.pj) return fold(L("Impacto en el campo", "On-pitch impact"), "", `<div class="empty-in">${L("Aún no ha jugado minutos en el periodo seleccionado.", "No minutes played yet in the selected period.")}</div>`);
  const minutes = Math.round(r.min), pj = r.pj;
  const onoffSub = r.onoff !== null ? L("con él menos sin él, por 90", "with minus without him, per 90") : L(`sin minutos suficientes sin él (mín. ${Math.round(r.minWithout)}')`, `not enough minutes without him (min. ${Math.round(r.minWithout)}')`);
  const withHim = icard(L("Con él en el campo", "With him on the pitch"), `${minutes}' · ${pj} ${L("partidos", "matches")}`, ifacts([
    ifact(L("Goles a favor", "Goals for"), r.gf, "", "tp"), ifact(L("Goles en contra", "Goals against"), r.gc, "", "tn"),
    ifact("On/Off", r.onoff !== null ? fnum(r.onoff, 2, true) : "—", onoffSub, tone(r.onoff)),
    ifact(L("Puntos a la salida", "Points at exit"), fnum(r.ptsExitAvg), `${L("por partido", "per match")} · ${L("equipo", "team")} ${fnum(r.teamPPG)}`, "tw"),
    ifact(L("Puntos ganados", "Points gained"), fnum(r.ptsGained, 0, true), `${fnum(r.ptsGainedAvg, 2, true)} ${L("por partido", "per match")}`, tone(r.ptsGained)),
    ifact(L("Porterías a cero", "Clean sheets"), `${r.cleanSheets}/${r.csEligible}`, L("partidos de 60' o más", "matches of 60' or more"))]),
    {span: 7, color: "#2fd27a", big: fnum(r.pm, 0, true), bigSub: `${fnum(r.dgOn, 2, true)} ${L("por 90", "per 90")}`, bigCls: tone(r.pm)});
  const comparison = icard(L("Comparativa", "Comparison"), L("con él / sin él / equipo", "with him / without him / team"),
    `<div class="cmp"><h4>${L("Diferencia de goles por 90", "Goal difference per 90")}</h4>` +
    cbar(L("Con él", "With him"), r.dgOn, 1.5, "#2fd27a", true, fnum(r.dgOn, 2, true)) + cbar(L("Sin él", "Without him"), r.dgOff, 1.5, "#2fd27a", true, fnum(r.dgOff, 2, true)) + cbar("On/Off", r.onoff, 1.5, "#2fd27a", true, fnum(r.onoff, 2, true)) +
    `<div class="cmp-rule"></div><h4>${L("Puntos por partido", "Points per match")}</h4>` + cbar(L("A su salida", "At exit"), r.ptsExitAvg, 3, "#ffb020", false, fnum(r.ptsExitAvg)) + cbar(L("Media equipo", "Team average"), r.teamPPG, 3, "#4c9aff", false, fnum(r.teamPPG)) + "</div>",
    {span: 5, color: "#4c9aff"});
  const st = r.state, total = (st.win + st.draw + st.loss) || 1;
  const segs = [["win", L("Ganando", "Winning"), "#2fd27a"], ["draw", L("Empatando", "Drawing"), "#ffb020"], ["loss", L("Perdiendo", "Losing"), "#ff5c6c"]];
  const dom = segs.reduce((a, b) => st[b[0]] > st[a[0]] ? b : a);
  const byState = icard(L("Minutos según el marcador", "Minutes by scoreline"), `${minutes}' ${L("en el campo", "on the pitch")}`,
    `<div class="stack-top">${segs.filter(s => st[s[0]] > 0).map(s => `<span style="flex:${st[s[0]].toFixed(3)}">${Math.round(st[s[0]])}'</span>`).join("")}</div>
     <div class="stack">${segs.filter(s => st[s[0]] > 0).map(s => `<i style="flex:${st[s[0]].toFixed(3)};background:${s[2]}">${Math.round(st[s[0]] / total * 100)}%</i>`).join("")}</div>
     <div class="legend2">${segs.map(s => `<span style="--col:${s[2]}">${s[1]}</span>`).join("")}</div>`,
    {span: 6, color: "#ffb020", big: `${Math.round(st[dom[0]] / total * 100)}%`, bigSub: dom[1].toLowerCase(), bigCls: "tw"});
  const trust = icard(L("Confianza del entrenador", "Coach's trust"), L("uso del jugador", "player usage"), ifacts([
    ifact(L("Titularidades", "Starts"), `${r.starts}/${r.teamPJ}`), ifact(L("Sustituido", "Substituted"), r.subbedOff, L(`de ${r.starts} de titular`, `of ${r.starts} starts`)),
    ifact(L("Minuto medio de cambio", "Average substitution minute"), r.subMinuteAvg !== null ? `${fnum(r.subMinuteAvg, 0)}'` : "—", r.subMinuteAvg !== null ? "" : L("nunca sustituido", "never substituted"))]),
    {span: 6, color: "#2fd27a", big: `${Math.round((r.pctMin || 0) * 100)}%`, bigSub: L("de los minutos posibles", "of possible minutes"), bigCls: "tp"});
  const b = r.bench;
  const benchBody = b.n ? ifacts([ifact(L("Entradas", "Appearances"), b.n, `${Math.round(b.min)}' ${L("en total", "in total")}`), ifact(L("Goles a favor / en contra", "Goals for / against"), `${b.gf} / ${b.gc}`, "", tone(b.gf - b.gc)),
    ifact(L("Puntos ganados", "Points gained"), fnum(b.pts, 0, true), "", tone(b.pts))]) : `<div class="empty-in">${L("No ha entrado como suplente en el periodo seleccionado.", "No substitute appearances in the selected period.")}</div>`;
  const bench = icard(L("Desde el banquillo", "From the bench"), "", benchBody, {span: 6, color: "#4c9aff"});
  const discipline = icard(L("Disciplina", "Discipline"), `${r.yellow} ${L("amarillas", "yellow")} · ${r.red} ${L("rojas", "red")}`, ifacts([
    ifact(L("Amarillas", "Yellow cards"), r.yellow, "", "ty"), ifact(L("Rojas", "Red cards"), r.red, "", r.red ? "tn" : "tz"),
    ifact(L("GC tras su roja", "Goals against after his red"), r.red ? r.gcAfterRed : "—", r.red ? "" : L("sin expulsiones", "no sending-offs"))]),
    {span: 6, color: "#ff5c6c", big: fnum(r.cards90), bigSub: L("tarjetas por 90", "cards per 90"), bigCls: (r.cards90 || 0) > 0 ? "tn" : "tz"});
  const notice = r.smallSample ? `<div class="sample"><i>!</i><span>${L("Muestra pequeña", "Small sample")}: ${minutes}' ${L("de", "of")} ${Math.round(r.minWith)}' ${L("mínimos. Las cifras aún pueden moverse mucho con cada partido.", "minimum. Figures can still swing a lot with every match.")}</span></div>` : "";
  const note = `<p class="foot-note">ⓘ ${L("Partidos del equipo en el periodo seleccionado", "Team matches in the selected period")} · ${L("mínimos", "minimum")} ${Math.round(r.minWith)}' ${L("con él y", "with him and")} ${Math.round(r.minWithout)}' ${L("sin él para el On/Off", "without him for On/Off")} · ${L("sin minutos de descuento; un gol en el minuto de un cambio cuenta para quien sale; los autogoles cuentan para quien se benefician", "no stoppage minutes; a goal at the minute of a substitution counts for the player leaving; own goals count for the beneficiary")}.</p>`;
  return fold(L("Impacto en el campo", "On-pitch impact"), `+/- <b>${fnum(r.pm, 0, true)}</b> · ${L("puntos a la salida", "points at exit")} <b>${fnum(r.ptsExitAvg)}</b>`, `${notice}<div class="impact-grid">${withHim}${comparison}${byState}${trust}${bench}${discipline}</div>${note}`);
}

function actionsBlock(sc, p) {
  const av = playerAvailability(sc, p.id, p.club_id), pc = (n, d) => d ? Math.round(n / d * 100) : 0;
  const called = av.called, totalMin = av.total * 90, calledMin = called * 90;
  const details = S.lang === "en"
    ? [`${called} of ${av.total} league matches`, `${pc(av.played, called)}% of selections · ${av.played} of ${called}`, `${pc(av.starts, called)}% of selections · ${av.starts} of ${called}`, `${pc(av.minutes, calledMin)}% of selected-player minutes · ${av.minutes}' of ${calledMin}'`]
    : [`${called} de ${av.total} partidos de liga`, `${pc(av.played, called)}% de convocatorias · ${av.played} de ${called}`, `${pc(av.starts, called)}% de convocatorias · ${av.starts} de ${called}`, `${pc(av.minutes, calledMin)}% de minutos convocado · ${av.minutes}' de ${calledMin}'`];
  const items = [["Convocado", called, pc(called, av.total), details[0], "#ffd21f"], ["Partidos jugados", av.played, pc(av.played, av.total), details[1], "#4c9aff"], ["Partidos titular", av.starts, pc(av.starts, av.total), details[2], "#2fd27a"], ["Minutos jugados", `${av.minutes}'`, pc(av.minutes, totalMin), details[3], "#ff8a54"]];
  const cards = items.map(([l, v, rate, d, c]) => `<div class="availability-card" style="--a:${c}"><label>${l}</label><b>${v}</b><span class="main-rate">${rate}% del total de liga</span><small>${d}</small></div>`).join("");
  const intervalPane = (type, label, colors, caption) => {
    const {home, away} = playerEventIntervals(sc, p.id, type);
    const body = home.concat(away).some(v => v > 0)
      ? chartbox(groupedBars({cats: INTERVALS, series: [{name: t("Local"), color: colors[0], vals: home}, {name: t("Visitante"), color: colors[1], vals: away}], xTitle: t("Tramo"), yTitle: label}), caption) + legendRow([[t("Local"), colors[0]], [t("Visitante"), colors[1]]])
      : empty(S.lang === "en" ? `No ${label.toLowerCase()} recorded in the selected period.` : `No hay ${label.toLowerCase()} registradas en el periodo seleccionado.`);
    return body;
  };
  const subs = playerSubstitutions(sc, p.id);
  let subsPane;
  if (!subs.length) subsPane = empty(t("Sin cambios que involucren al jugador en el periodo seleccionado."));
  else {
    const minsList = [...new Set(subs.map(s => s.minute))].sort((a, b) => a - b);
    const chart = chartbox(groupedBars({cats: minsList.map(String), series: ["Entra", "Sale"].map((a, i) => ({name: t(a), color: i ? "#ff5c6c" : "#2fd27a", vals: minsList.map(m => subs.filter(s => s.minute === m && s.action === a).length)})), xTitle: t("Minuto"), yTitle: t("Cambios"), height: 260}), t("MINUTOS DE ENTRADA Y SALIDA"));
    const head = ["Fecha", "Partido", "Sede", "Min.", "Acción", "Relación"].map(l => `<div class="pc">${t(l)}</div>`).join("");
    subsPane = chart + section("Matriz de cambios", "Entrada o salida y jugador relacionado") + `<div class="hrow phead">${head}</div>` +
      subs.map(s => `<div class="hrow"><div class="pc d">${esc(s.date)}</div><div class="pc">${esc(s.match)}</div><div class="pc">${t(s.side)}</div><div class="pc">${s.minute}'</div><div class="pc" style="color:${s.action === "Entra" ? "#2fd27a" : "#ff5c6c"}">${t(s.action)}</div><div class="pc">${esc(s.rel)}</div></div>`).join("");
  }
  const tabs = ["Goles", "Amarillas", "Rojas", "Cambios"], active = S.tabs.act ?? 0;
  const staticMode = STATIC.on;
  const panes = [intervalPane("goal", t("Goles"), ["#2fd27a", "#4c9aff"], t("GOLES POR TRAMOS DE 15' · LOCAL Y VISITANTE")), intervalPane("ycard", t("Amarillas"), ["#ffd21f", "#f5a524"], t("TARJETAS AMARILLAS POR TRAMOS DE 15' · LOCAL Y VISITANTE")),
    intervalPane("rcard", t("Rojas"), ["#ff5c6c", "#ff8a97"], t("TARJETAS ROJAS POR TRAMOS DE 15' · LOCAL Y VISITANTE")), subsPane];
  if (staticMode) {
    return section("Acciones", "Disponibilidad, producción y disciplina oficial UAEFA") + `<div class="availability avail4">${cards}</div>` +
      panes.map((h, i) => `<details class="sdet" ${i === 0 ? "open" : ""}><summary>${t(tabs[i])}</summary>${h}</details>`).join("");
  }
  return section("Acciones", "Disponibilidad, producción y disciplina oficial UAEFA") + `<div class="availability avail4">${cards}</div>` +
    `<div class="subtabs" style="margin-top:1rem">${tabs.map((l, i) => `<button data-tab="act" data-i="${i}" class="${i === active ? "on" : ""}">${t(l)}</button>`).join("")}</div>` +
    panes.map((h, i) => `<div class="tabpane ${i === active ? "on" : ""}" data-pane="act" data-i="${i}">${h}</div>`).join("");
}

function pageProfile(id) {
  const sc = scope(S.week), p = sc.byId[id];
  if (!p) return pageCatalogue();
  const back = S.prev && !S.prev.startsWith("#/players/") ? S.prev : "#/players";
  const html = banner("players", ["Jugadores", p.short]) +
    `<div class="back"><a class="btn primary pill" href="${back}">${t("← Volver")}</a></div>` + profileBodyHtml(sc, p);
  return {detail: p.short, trail: ["Jugadores", p.short], html};
}

function profileBodyHtml(sc, p, full = true) {
  const club = clubs[p.club_id], ref = sc.refDate, bl = birthLabel(p.birth, ref);
  const tags = `${identityChips(p)}${bl ? `<span class="chip age">Nacimiento ${esc(bl)}</span>` : ""}<span class="chip y">${esc(p.cat)}</span><span class="chip">${esc(p.status)}</span><span class="chip">${esc(p.team)}</span>${p.dorsal ? `<span class="chip">Dorsal #${esc(p.dorsal)}</span>` : ""}`;
  const enrich = [];
  if (isNum(p.elo)) enrich.push(["Elo del jugador", Math.round(p.elo), "#4c9aff"]);
  if (marketValue(p.mv)) enrich.push(["Valor de mercado", marketValue(p.mv), "#2fd27a"]);
  if (club && isNum(club.elo)) enrich.push(["Elo del equipo", Math.round(club.elo), "#4c9aff"]);
  const charts = [];
  if (p.mvh && p.mvh.length) charts.push(section("Evolución de valor de mercado", "Datos externos · histórico publicado") + chartbox(lineChart({points: p.mvh.map(h => ({x: String(h.year), y: h.value_eur})), color: "#2fd27a", fmt: marketValue, yTitle: t("Euros")})));
  if (p.eloh && p.eloh.length) charts.push(section("Evolución de Elo", "Datos externos · histórico publicado del jugador") + chartbox(lineChart({points: p.eloh.map(h => ({x: String(h.year), y: h.elo})), color: "#4c9aff", fmt: v => String(Math.round(v)), yTitle: "Elo"})));
  return     `<div class="profile"><div>${portrait(p)}</div><div>${posBadge(p.pos, true)}<h2>${esc(p.name)}</h2>${p.ar ? `<div class="ar">${esc(p.ar)}</div>` : ""}
      <div class="clubline">${crest(p.club_id, 44)}<span>${esc(p.club_name)}</span></div><div class="tags">${tags}</div></div></div>` +
    kpis([["Partidos", p.Matches, "#4c9aff"], ["Titular", p.Starts, "#2fd27a"], ["Minutos", Math.round(p.Minutes), "#ffd21f"], ["Goles", p.Goals, "#ffd21f"], ["Amarillas", p.Yellow, "#ffd21f"], ["Rojas", p.Red, "#ff5c6c"]]) +
    (enrich.length ? section("Enriquecimiento validado", "Datos externos · identidad confirmada con UAEFA") + kpis(enrich) : "") + charts.join("") +
    (full ? seasonBlock(sc, p) + impactBlock(sc, p) + actionsBlock(sc, p)
      : `<div class="sample" style="margin-top:1rem"><i>!</i><span>${L(`Impacto, temporada y acciones solo se incluyen aquí para jugadores con ${STATIC.minFull}' o más. Están completos para todos en la versión interactiva (index.html).`, `Impact, season and actions are only included here for players with ${STATIC.minFull}' or more. They are complete for everyone in the interactive version (index.html).`)}</span></div>`);
}
