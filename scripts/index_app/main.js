/* ===================================================================== shell, routing, events */
const renderMarkup = tr;
function bindImages(root) {
  root.querySelectorAll("img[data-k]").forEach(img => { const u = IMG[img.dataset.k]; if (u) img.src = u; img.removeAttribute("data-k"); });
}
const svgIcon = k => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;
function setChrome(page, detail) {
  const here = t(PAGES[page].es) + (detail ? ` · ${detail}` : "");
  const set = (id, html) => { const el = document.getElementById(id); el.innerHTML = tr(html); bindImages(el); return el; };
  set("bar", `<div class="brand-left">${brand()}<div><div class="brand-title">Al Wasl <b>·</b> First Division Hub</div><div class="brand-sub">UAE First Division · Temporada ${SEASON}</div></div></div>
    <div class="brand-right"><div class="here"><i></i><span>${esc(here)}</span></div></div>`);
  const links = Object.entries(PAGES).map(([k, p]) => `<a href="#/${k}" class="${k === page ? "on" : ""}">${svgIcon(k)}<span>${p.es}</span></a>`).join("");
  const ctl = set("controls", `<div class="navtabs">${links}</div>
    <div class="scope"><div class="scope-panel"><i></i><span>Jornada de corte</span><b>Vista activa</b></div>
      <div class="mday"><button class="sbtn" id="prevw" ${S.week === WEEKS[0] ? "disabled" : ""}>‹</button><div class="cur">${esc(scopeLabel())}</div><button class="sbtn" id="nextw" ${S.week === MAX_WEEK ? "disabled" : ""}>›</button></div></div>
    <div class="langsel"><select class="fin" id="lang" aria-label="Language"><option value="en" ${S.lang === "en" ? "selected" : ""}>English</option><option value="es" ${S.lang === "es" ? "selected" : ""}>Español</option></select></div>`);
  set("bnav", links);
  ctl.querySelector("#prevw").onclick = () => shiftWeek(-1);
  ctl.querySelector("#nextw").onclick = () => shiftWeek(1);
  ctl.querySelector("#lang").onchange = e => { S.lang = e.target.value; persist(); document.documentElement.lang = S.lang; render(false); };
  set("footer", `<div class="fl">${brand()}</div><span>${t("Fuente: UAEFA public API")} · ${L("Instantánea estática generada con los datos locales.", "Static snapshot built from the local data.")}</span>`);
}
function shiftWeek(step) {
  const i = WEEKS.indexOf(S.week) + step;
  if (i < 0 || i >= WEEKS.length) return;
  S.week = WEEKS[i]; S.shown = GRID_PAGE; persist(); render(false);
}

let lastHash = null;
function parseRoute() {
  const [page = "standings", id] = location.hash.replace(/^#\/?/, "").split("/");
  return {page: PAGES[page] ? page : "standings", id};
}
function render(navigated) {
  const {page, id} = parseRoute();
  if (page === "matches" && id && matchById[id] && matchById[id].week !== S.week) { S.week = matchById[id].week; persist(); }
  let view;
  if (page === "standings") view = pageStandings();
  else if (page === "matches") view = pageMatch(id);
  else if (page === "teams") view = pageTeam(id);
  else view = id ? pageProfile(id) : pageCatalogue();
  setChrome(page, view.detail);
  const app = document.getElementById("app");
  app.innerHTML = tr(view.html);
  bindImages(app);
  document.title = `${t(PAGES[page].es)}${view.detail ? " · " + t(view.detail) : ""} | Al Wasl`;
  if (view.after) view.after();
  if (navigated) window.scrollTo(0, 0);
}
window.addEventListener("hashchange", () => {
  if (lastHash !== null && lastHash !== location.hash) S.prev = lastHash;
  lastHash = location.hash;
  render(true);
});

document.addEventListener("click", e => {
  const tab = e.target.closest("[data-tab]");
  if (tab) {
    const key = tab.dataset.tab, i = Number(tab.dataset.i);
    S.tabs[key] = i;
    document.querySelectorAll(`[data-tab="${key}"]`).forEach(b => b.classList.toggle("on", Number(b.dataset.i) === i));
    document.querySelectorAll(`[data-pane="${key}"]`).forEach(p => p.classList.toggle("on", Number(p.dataset.i) === i));
    return;
  }
  const chip = e.target.closest("[data-bumpy]");
  if (chip) {
    const id = chip.dataset.bumpy;
    if (S.bumpy.includes(id)) S.bumpy = S.bumpy.filter(x => x !== id); else if (S.bumpy.length < 5) S.bumpy = [...S.bumpy, id];
    const box = document.getElementById("bumpy");
    box.innerHTML = tr(bumpyBlock(scope(S.week)));
    bindImages(box);
  }
});

lastHash = location.hash;
document.documentElement.lang = S.lang;
try {
  render(false);
  const boot = document.getElementById("boot");
  if (boot) boot.remove();   // the app is running: the "only the first screen" notice no longer applies
} catch (err) {
  const e = document.getElementById("booterr");
  if (e) e.textContent = "Error: " + (err && err.message ? err.message : err);
  throw err;
}
