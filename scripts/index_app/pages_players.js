/* ======================================================================= players: catalogue */
const METRICS = {
  age: ["Edad", p => p.Edad], squad: ["Convocatorias", p => p.Squad], matches: ["Partidos jugados", p => p.Matches], starts: ["Titularidades", p => p.Starts],
  minutes: ["Minutos", p => p.Minutes], goals: ["Goles", p => p.Goals], yellow: ["Tarjetas amarillas", p => p.Yellow], red: ["Tarjetas rojas", p => p.Red],
  player_elo: ["Elo del jugador", p => isNum(p.elo) ? p.elo : null], market_value: ["Valor de mercado", p => isNum(p.mv) ? p.mv : null], team_elo: ["Elo del equipo", p => isNum(p.teamElo) ? p.teamElo : null],
};
const SCATTER_COLORS = {GK: "#ae7800", D: "#256abf", M: "#148a54", A: "#cf4054"};

function filterPool(sc, withPosition) {
  const F = S.F, q = F.q.trim().toLowerCase();
  const lo = F.ageMin === "" ? null : Number(F.ageMin), hi = F.ageMax === "" ? null : Number(F.ageMax);
  return sc.players.filter(p =>
    (!q || [p.name, p.short, p.nameOff].some(v => v && v.toLowerCase().includes(q))) &&
    (!withPosition || F.pos === "Todas" || p.pos === F.pos) &&
    (F.cat === "Todas" || p.cat === F.cat) && (F.club === "Todos" || p.club_name === F.club) &&
    (lo === null || (p.Edad !== null && p.Edad >= lo)) && (hi === null || (p.Edad !== null && p.Edad <= hi)) &&
    (!F.minMin || p.Minutes >= F.minMin) && (F.status === "Todos" || p.status === F.status) && (!F.played || p.Minutes > 0));
}
function glossaryHtml(sample) {
  const items = S.lang === "en"
    ? ["The photo and squad number identify the player in official match reports.", "The border and soft shading identify the role: goalkeeper, defender, midfielder or attacker.", "`UAEFA` confirms the player is in the official ecosystem; the adjacent flag shows the published nationality.", "Birth year displays the official year and age calculated using the visible matchday cut-off date.", "The coloured circle is the <b>individual Elo</b> when it is published and the identity match is validated: red is the lower range and green the upper range among available Elo values.", "`PJ`, `MIN`, `Goles`, `TA` and `TR` are official UAEFA matches played, minutes, goals, yellow cards and red cards."]
    : ["La foto y el dorsal identifican al jugador en las actas oficiales.", "El borde y sombreado suave indican su posición: portero, defensa, mediocampista o atacante.", "`UAEFA` confirma su presencia en el ecosistema oficial; la bandera contigua indica la nacionalidad publicada.", "El nacimiento muestra el año oficial y la edad calculada con la fecha de corte de la jornada visible.", "El círculo de color es el <b>Elo individual</b> cuando está publicado y el cruce de identidad está validado: rojo representa el tramo inferior y verde el superior dentro de los Elo disponibles.", "`PJ`, `MIN`, `Goles`, `TA` y `TR` son partidos jugados, minutos, goles, tarjetas amarillas y tarjetas rojas oficiales UAEFA."];
  return `<details class="glossary"><summary>${t("Glosario · cómo leer una tarjeta de jugador")}</summary><div class="gbody">
    <div>${sample ? playerCard(sample) : empty(t("El ejemplo aparecerá al obtener al menos un jugador con los filtros aplicados."))}</div>
    <div><b>${L("Ejemplo de lectura", "How to read this card")}</b><ul>${items.map(i => `<li>${i.replace(/`([^`]+)`/g, "<code>$1</code>")}</li>`).join("")}</ul></div></div></details>`;
}
function scatterBlock(pool) {
  const X = S.X, [xl, xf] = METRICS[X.x], [yl, yf] = METRICS[X.y];
  const ref = scope(S.week).refDate;
  let pts = pool.filter(p => X.pos.includes(p.pos)).map(p => ({p, x: xf(p), y: yf(p)})).filter(o => o.x !== null && o.y !== null);
  if (X.nulls) pts = pts.filter(o => o.x > 0 && o.y > 0);
  const opts = Object.entries(METRICS).map(([k, [lab]]) => `<option value="${k}" %S%>${t(lab)}</option>`);
  const select = (id, cur) => `<select class="fin" id="${id}">${opts.map(o => o.replace("%S%", o.includes(`value="${cur}"`) ? "selected" : "")).join("")}</select>`;
  const posBtns = ["GK", "D", "M", "A"].map(c => `<button data-xpos="${c}" class="${X.pos.includes(c) ? "on" : ""}" style="--c:${SCATTER_COLORS[c]}">${{GK: t("Porteros"), D: t("Defensas"), M: t("Mediocampistas"), A: t("Atacantes")}[c]}</button>`).join("");
  let body, note = "";
  if (!pts.length) body = empty(t("No hay jugadores con valores positivos y publicados para la combinación de métricas elegida."));
  else {
    const data = pts.map(o => ({id: o.p.id, pos: o.p.pos, x: o.x, y: o.y, tip: `${o.p.name} · ${o.p.club_name} · ${o.p.pos} · ${birthLabel(o.p.birth, ref) || "—"} · ${Math.round(o.p.Minutes)}' · ${o.p.Goals} ${t("Goles")}`}));
    const {svg, mx, my} = scatterChart({pts: data, xLabel: t(xl), yLabel: t(yl), colors: SCATTER_COLORS});
    body = chartbox(svg) + legendRow(["GK", "D", "M", "A"].map(c => [c, SCATTER_COLORS[c]]));
    note = `${pts.length} / ${pool.length} ${t("jugadores visibles")} · ${X.nulls ? t("Se ocultan los ceros y datos sin publicar.") : t("Se muestran los ceros; solo se omiten coordenadas no publicadas.")} ${t("Medias del gráfico")}: ${t(xl).toLowerCase()} ${mx.toFixed(1)} · ${t(yl).toLowerCase()} ${my.toFixed(1)}.`;
  }
  return `<div class="fpanel"><div class="filter-shell"><span>ANÁLISIS MULTIVARIABLE</span><b>Explora perfiles y cuadrantes de rendimiento</b></div>
    <div class="fgrid"><div><label class="flab">${t("Eje X")}</label>${select("sx", X.x)}</div><div><label class="flab">${t("Eje Y")}</label>${select("sy", X.y)}</div>
    <div><label class="flab">${t("Posiciones en el gráfico")}</label><div class="posseg">${posBtns}</div></div>
    <label class="chk"><input type="checkbox" id="snulls" ${X.nulls ? "checked" : ""}>${t("Excluir 0 y sin dato")}</label></div>${body}${note ? `<div class="hint" style="text-transform:none;letter-spacing:0">${note}</div>` : ""}</div>`;
}
function paintCatalogue() {
  const sc = scope(S.week), box = document.getElementById("explore");
  if (!box) return;
  const filtered = filterPool(sc, true).sort((a, b) => b.Goals - a.Goals || b.Minutes - a.Minutes || b.Starts - a.Starts || a.name.localeCompare(b.name));
  const shown = Math.min(S.shown, filtered.length);
  const cards = filtered.length ? grid(3, filtered.slice(0, shown).map(p => cardWithButton(playerCard(p), `#/players/${p.id}`)).join("")) +
    (shown < filtered.length ? `<div class="more"><button class="btn primary" id="more">${t("Mostrar más")} (${filtered.length - shown} ${t("restantes")})</button></div>` : "") : empty("No hay jugadores que cumplan los filtros seleccionados.");
  box.innerHTML = renderMarkup(glossaryHtml(filtered[0]) + section("Comparador de jugadores", "Selecciona las variables de cada eje. Elo y valor solo aparecen si el dato externo está publicado y validado") + scatterBlock(filterPool(sc, false)) +
    section("Jugadores identificados", `${filtered.length} resultados · goleadores primero`) + cards);
  bindImages(box);
  const sx = box.querySelector("#sx"), sy = box.querySelector("#sy"), sn = box.querySelector("#snulls");
  sx.onchange = e => { S.X.x = e.target.value; paintCatalogue(); };
  sy.onchange = e => { S.X.y = e.target.value; paintCatalogue(); };
  sn.onchange = e => { S.X.nulls = e.target.checked; paintCatalogue(); };
  box.querySelectorAll("[data-xpos]").forEach(b => b.onclick = () => { const c = b.dataset.xpos; S.X.pos = S.X.pos.includes(c) ? S.X.pos.filter(x => x !== c) : [...S.X.pos, c]; paintCatalogue(); });
  const more = box.querySelector("#more");
  if (more) more.onclick = () => { S.shown += GRID_PAGE; paintCatalogue(); };
}
function pageCatalogue() {
  const sc = scope(S.week), F = S.F;
  const opt = (value, label, cur) => `<option value="${esc(value)}" ${cur === value ? "selected" : ""}>${esc(label)}</option>`;
  const cats = [...new Set(sc.players.map(p => p.cat).filter(Boolean))].sort();
  const clubNames = [...new Set(sc.players.map(p => p.club_name))].sort();
  const statuses = [...new Set(sc.players.map(p => p.status).filter(Boolean))].sort();
  const ages = sc.players.map(p => p.Edad).filter(a => a !== null);
  const posLabel = {Todas: t("Todas las posiciones"), GK: `GK · ${t("Portero")}`, D: `D · ${t("Defensa")}`, M: `M · ${t("Mediocampista")}`, A: `A · ${t("Atacante")}`};
  const labelled = sc.players.slice().sort((a, b) => a.name.localeCompare(b.name) || a.club_name.localeCompare(b.club_name));
  const html = banner("players", ["Jugadores", "Catálogo"]) +
    `<div class="fpanel" style="margin-top:1rem"><div class="quick-open"><div><b>Abrir ficha de jugador</b><span>Busca directamente un jugador para consultar su perfil completo.</span></div><i></i></div>
      <select class="fin" id="quick"><option value="">${t("Selecciona un jugador...")}</option>${labelled.map(p => `<option value="${p.id}">${esc(p.name)} · ${esc(p.club_name)}</option>`).join("")}</select></div>` +
    section("Filtros de búsqueda", "Combina perfil, club y rendimiento para localizar jugadores concretos") +
    `<div class="fpanel"><div class="filter-shell"><span>EXPLORADOR DE PLANTILLAS</span><b>Filtra y combina criterios sin perder contexto</b></div>
      <div class="fgrid"><div><label class="flab">${t("Buscar jugador")}</label><input class="fin" id="fq" type="search" placeholder="${t("Nombre o apellidos")}" value="${esc(F.q)}"></div>
        <div><label class="flab">${t("Posición")}</label><select class="fin" id="fpos">${["Todas", "GK", "D", "M", "A"].map(c => opt(c, posLabel[c], F.pos)).join("")}</select></div>
        <div><label class="flab">${t("Categoría UAEFA")}</label><select class="fin" id="fcat">${opt("Todas", t("Todas"), F.cat)}${cats.map(c => opt(c, c, F.cat)).join("")}</select></div>
        <div><label class="flab">${t("Club")}</label><select class="fin" id="fclub">${opt("Todos", t("Todos"), F.club)}${clubNames.map(c => opt(c, c, F.club)).join("")}</select></div></div>
      <div class="fgrid"><div><label class="flab">${t("Rango de edad")}</label><div class="agepair"><input class="fin" id="fa0" type="number" inputmode="numeric" placeholder="${ages.length ? Math.min(...ages) : ""}" value="${F.ageMin}"><input class="fin" id="fa1" type="number" inputmode="numeric" placeholder="${ages.length ? Math.max(...ages) : ""}" value="${F.ageMax}"></div></div>
        <div><label class="flab">${t("Minutos mínimos")}</label><input class="fin" id="fmin" type="number" min="0" step="30" value="${F.minMin}"></div>
        <div><label class="flab">${t("Estatus")}</label><select class="fin" id="fst">${opt("Todos", t("Todos"), F.status)}${statuses.map(c => opt(c, c, F.status)).join("")}</select></div>
        <div><label class="flab">${t("DISPONIBILIDAD")}</label><label class="chk"><input type="checkbox" id="fplayed" ${F.played ? "checked" : ""}>${t("Solo jugadores con minutos")}</label></div></div>
      <div class="filter-legend">${["GK", "D", "M", "A"].map(c => posBadge(c, true)).join("")}</div></div><div id="explore"></div>`;
  return {detail: "Catálogo", trail: ["Jugadores", "Catálogo"], html, after() {
    const bind = (id, key, ev, get) => { const el = document.getElementById(id); el.addEventListener(ev, e => { S.F[key] = get(e.target); S.shown = GRID_PAGE; paintCatalogue(); }); };
    bind("fq", "q", "input", el => el.value); bind("fpos", "pos", "change", el => el.value); bind("fcat", "cat", "change", el => el.value); bind("fclub", "club", "change", el => el.value);
    bind("fa0", "ageMin", "input", el => el.value); bind("fa1", "ageMax", "input", el => el.value); bind("fmin", "minMin", "input", el => Number(el.value) || 0);
    bind("fst", "status", "change", el => el.value); bind("fplayed", "played", "change", el => el.checked);
    document.getElementById("quick").onchange = e => { if (e.target.value) location.hash = `#/players/${e.target.value}`; };
    paintCatalogue();
  }};
}
