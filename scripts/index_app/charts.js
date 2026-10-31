/* ============================================================ SVG charts (light theme, no dependencies) */
const AX = "#62666b", GRID = "#e1e1da", INK = "#252a2f";
function niceTicks(lo, hi, count = 5, whole = false) {
  if (hi === lo) hi = lo + 1;
  const span = hi - lo;
  let step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = span / count / step;
  step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  if (whole) step = Math.max(1, Math.ceil(step));
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step, out = [];
  for (let v = a; v <= b + step / 2; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}
const lin = (d0, d1, r0, r1) => v => d1 === d0 ? (r0 + r1) / 2 : r0 + (v - d0) * (r1 - r0) / (d1 - d0);
const txt = (x, y, s, o = {}) => `<text x="${x}" y="${y}" text-anchor="${o.a || "middle"}" font-size="${o.s || 11}" fill="${o.c || AX}" font-weight="${o.w || 400}" ${o.rot ? `transform="rotate(${o.rot} ${x} ${y})"` : ""} ${o.dy ? `dy="${o.dy}"` : ""}>${esc(s)}</text>`;
const fmtTick = v => Math.abs(v) >= 1e6 ? `${+(v / 1e6).toFixed(2)}M` : Math.abs(v) >= 1e3 ? `${+(v / 1e3).toFixed(1)}k` : String(v);
function frame(W, H, M, yTicks, y, yTitle, formatter = v => String(v)) {
  let s = `<g>`;
  for (const v of yTicks) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}" stroke="${GRID}" stroke-width="1"/>` + txt(M.l - 8, y(v), formatter(v), {a: "end", dy: "0.32em"});
  if (yTitle) s += txt(14, (M.t + H - M.b) / 2, yTitle, {rot: -90});
  return s + "</g>";
}
const chartbox = (svg, caption = "") => `${caption ? `<div class="hint">${esc(caption)}</div>` : ""}<div class="chartbox">${svg}</div>`;
const legendRow = items => `<div class="legendrow">${items.map(([label, color]) => `<span style="--col:${color}">${esc(label)}</span>`).join("")}</div>`;

/* grouped bars: categories on x, one bar per series; labels only for non-zero values */
function groupedBars({cats, series, height = 280, yTitle = "", xTitle = ""}) {
  const W = 760, H = height, M = {l: 52, r: 16, t: 20, b: 44};
  const max = Math.max(1, ...series.flatMap(s => s.vals));
  const ticks = niceTicks(0, max, 5, true), top = ticks[ticks.length - 1];
  const y = lin(0, top, H - M.b, M.t), band = (W - M.l - M.r) / cats.length;
  const bw = Math.min(26, band / (series.length + 1));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">` + frame(W, H, M, ticks, y, yTitle);
  cats.forEach((c, i) => {
    const cx = M.l + band * (i + .5);
    s += txt(cx, H - M.b + 18, c, {c: AX});
    series.forEach((se, k) => {
      const x = cx + (k - (series.length - 1) / 2) * (bw + 4) - bw / 2, v = se.vals[i];
      if (v > 0) s += `<rect x="${x}" y="${y(v)}" width="${bw}" height="${y(0) - y(v)}" rx="6" fill="${se.color}"><title>${esc(c)} · ${esc(se.name)}: ${v}</title></rect>` + txt(x + bw / 2, y(v) - 7, v, {c: INK, w: 700, s: 12});
    });
  });
  if (xTitle) s += txt((M.l + W - M.r) / 2, H - 6, xTitle);
  return s + `<line x1="${M.l}" x2="${W - M.r}" y1="${y(0)}" y2="${y(0)}" stroke="${AX}" stroke-width="1"/></svg>`;
}

/* team goal rhythm: goals for above the axis, against below */
function divergingBars({cats, up, down, height = 300}) {
  const W = 760, H = height, M = {l: 52, r: 16, t: 20, b: 40};
  const mx = Math.max(1, ...up.vals), mn = Math.max(1, ...down.vals);
  const ticks = niceTicks(-mn, mx, 6, true), y = lin(ticks[0], ticks[ticks.length - 1], H - M.b, M.t), band = (W - M.l - M.r) / cats.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">` + frame(W, H, M, ticks, y, "Goles", v => String(Math.abs(v)));
  cats.forEach((c, i) => {
    const cx = M.l + band * (i + .5), bw = Math.min(30, band * .5);
    s += txt(cx, H - 12, c);
    if (up.vals[i] > 0) s += `<rect x="${cx - bw / 2}" y="${y(up.vals[i])}" width="${bw}" height="${y(0) - y(up.vals[i])}" rx="8" fill="${up.color}"><title>${esc(c)} · ${esc(up.name)}: ${up.vals[i]}</title></rect>` + txt(cx, y(up.vals[i]) - 7, up.vals[i], {c: "#16633f", w: 700, s: 12});
    if (down.vals[i] > 0) s += `<rect x="${cx - bw / 2}" y="${y(0)}" width="${bw}" height="${y(-down.vals[i]) - y(0)}" rx="8" fill="${down.color}"><title>${esc(c)} · ${esc(down.name)}: ${down.vals[i]}</title></rect>` + txt(cx, y(-down.vals[i]) + 17, down.vals[i], {c: "#a42f40", w: 700, s: 12});
  });
  return s + `<line x1="${M.l}" x2="${W - M.r}" y1="${y(0)}" y2="${y(0)}" stroke="${AX}"/></svg>`;
}

/* goal difference per matchday (bars) and cumulative (line split at zero) */
function goalDiffChart(rows, labels) {
  const W = 760, H = 300, M = {l: 52, r: 24, t: 24, b: 40};
  const vals = rows.flatMap(r => [r.weekly, r.cum, 0]);
  const ticks = niceTicks(Math.min(...vals), Math.max(...vals), 6, true), y = lin(ticks[0], ticks[ticks.length - 1], H - M.b, M.t);
  const xs = rows.map(r => r.week), x0 = Math.min(...xs), x1 = Math.max(...xs), span = Math.max(1, x1 - x0);
  const x = lin(x0 - .5, x1 + .5, M.l, W - M.r), bw = Math.min(30, (W - M.l - M.r) / (span + 1) * .55);
  const POS = "#2fd27a", NEG = "#ff5c6c";
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">` + frame(W, H, M, ticks, y, labels.title);
  rows.forEach(r => {
    s += txt(x(r.week), H - 12, r.week) + `<rect x="${x(r.week) - bw / 2}" y="${Math.min(y(r.weekly), y(0))}" width="${bw}" height="${Math.max(2, Math.abs(y(r.weekly) - y(0)))}" rx="6" fill="${r.weekly >= 0 ? POS : NEG}" opacity=".85"><title>${labels.week} ${r.week}: ${r.weekly}</title></rect>`;
  });
  s += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(0)}" y2="${y(0)}" stroke="${AX}"/>`;
  for (let i = 0; i < rows.length - 1; i++) {   // a crossing is split exactly at zero, zero belongs to the negative side
    const [a, b] = [rows[i], rows[i + 1]];
    const seg = (xa, ya, xb, yb, pos) => `<line x1="${x(xa)}" y1="${y(ya)}" x2="${x(xb)}" y2="${y(yb)}" stroke="${pos ? POS : NEG}" stroke-width="3" stroke-linecap="round"/>`;
    if ((a.cum <= 0 && b.cum > 0) || (b.cum <= 0 && a.cum > 0)) {
      const cx = a.week + (0 - a.cum) * (b.week - a.week) / (b.cum - a.cum);
      s += seg(a.week, a.cum, cx, 0, false) + seg(cx, 0, b.week, b.cum, b.cum > 0);
    } else s += seg(a.week, a.cum, b.week, b.cum, b.cum > 0);
  }
  rows.forEach(r => { s += `<circle cx="${x(r.week)}" cy="${y(r.cum)}" r="5" fill="${r.cum > 0 ? POS : NEG}"><title>${labels.cum} ${r.week}: ${r.cum}</title></circle>` + txt(x(r.week) + 10, y(r.cum) - 10, r.cum, {c: INK, w: 700, a: "start", s: 12}); });
  return s + "</svg>";
}

/* a single series over categorical years (market value / Elo) */
function lineChart({points, color, fmt = v => String(v), yTitle = "", height = 245}) {
  const W = 760, H = height, M = {l: 62, r: 30, t: 30, b: 36};
  const vs = points.map(p => p.y), ticks = niceTicks(Math.min(...vs) * .9, Math.max(...vs) * 1.08, 5), y = lin(ticks[0], ticks[ticks.length - 1], H - M.b, M.t);
  const x = i => points.length === 1 ? (M.l + W - M.r) / 2 : M.l + i * (W - M.l - M.r) / (points.length - 1);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">` + frame(W, H, M, ticks, y, yTitle, fmtTick);
  s += `<polyline fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round" points="${points.map((p, i) => `${x(i)},${y(p.y)}`).join(" ")}"/>`;
  points.forEach((p, i) => { s += txt(x(i), H - 12, p.x) + `<circle cx="${x(i)}" cy="${y(p.y)}" r="5" fill="${color}"><title>${esc(p.x)}: ${esc(fmt(p.y))}</title></circle>` + txt(x(i), y(p.y) - 12, fmt(p.y), {c: INK, w: 700, s: 12}); });
  return s + "</svg>";
}

/* position progression ("bumpy" chart): grey for everyone, colour for the chosen clubs */
function bumpyChart({weeks, byClub, selected, colors, teamCount}) {
  const W = 880, H = 440, M = {l: 44, r: 150, t: 20, b: 36};
  const x = lin(weeks[0], weeks[weeks.length - 1], M.l, W - M.r), y = lin(.5, teamCount + .5, M.t, H - M.b);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (let p = 1; p <= teamCount; p++) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(p)}" y2="${y(p)}" stroke="${GRID}"/>` + txt(M.l - 10, y(p), p, {a: "end", dy: "0.32em"});
  weeks.forEach(w => { s += txt(x(w), H - 12, w); });
  const line = (id, c, sw, op) => {
    const pts = byClub.get(id) || [];
    return `<polyline fill="none" stroke="${c}" stroke-width="${sw}" opacity="${op}" stroke-linejoin="round" points="${pts.map(q => `${x(q.week)},${y(q.pos)}`).join(" ")}"/>`;
  };
  for (const id of byClub.keys()) if (!selected.includes(id)) s += line(id, "#303842", 1.2, .5) + (byClub.get(id) || []).map(q => `<circle cx="${x(q.week)}" cy="${y(q.pos)}" r="2.6" fill="#303842" opacity=".7"/>`).join("");
  for (const id of selected) {
    const pts = byClub.get(id) || [], c = colors[id];
    s += line(id, c, 3.2, 1) + pts.map(q => `<circle cx="${x(q.week)}" cy="${y(q.pos)}" r="5.5" fill="${c}"><title>${esc(clubs[id].name)} · ${t("Jornada")} ${q.week} · ${t("Posición")} ${q.pos}</title></circle>`).join("");
    const last = pts[pts.length - 1];
    if (last) s += txt(x(last.week) + 12, y(last.pos) + 4, clubs[id].name, {a: "start", c, w: 700, s: 12});
  }
  return s + "</svg>";
}

/* scatter plot with dashed mean lines and tooltips */
function scatterChart({pts, xLabel, yLabel, colors}) {
  const W = 860, H = 400, M = {l: 66, r: 20, t: 20, b: 52};
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const whole = a => a.every(Number.isInteger);
  const xt = niceTicks(Math.min(...xs), Math.max(...xs), 7, whole(xs)), yt = niceTicks(Math.min(...ys), Math.max(...ys), 6, whole(ys));
  const x = lin(xt[0], xt[xt.length - 1], M.l, W - M.r), y = lin(yt[0], yt[yt.length - 1], H - M.b, M.t);
  const mean = a => a.reduce((s, v) => s + v, 0) / a.length, mx = mean(xs), my = mean(ys);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img"><rect x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${H - M.t - M.b}" fill="none" stroke="#e1e1da"/>`;
  for (const v of yt) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}" stroke="#ecece7"/>` + txt(M.l - 8, y(v), fmtTick(v), {a: "end", dy: "0.32em"});
  for (const v of xt) s += `<line y1="${M.t}" y2="${H - M.b}" x1="${x(v)}" x2="${x(v)}" stroke="#ecece7"/>` + txt(x(v), H - M.b + 18, fmtTick(v));
  s += txt((M.l + W - M.r) / 2, H - 8, xLabel, {c: "#30343a", w: 600}) + txt(16, (M.t + H - M.b) / 2, yLabel, {rot: -90, c: "#30343a", w: 600});
  s += `<line x1="${x(mx)}" x2="${x(mx)}" y1="${M.t}" y2="${H - M.b}" stroke="#657083" stroke-dasharray="7 6" opacity=".92"/><line x1="${M.l}" x2="${W - M.r}" y1="${y(my)}" y2="${y(my)}" stroke="#657083" stroke-dasharray="7 6" opacity=".92"/>`;
  for (const p of pts) {
    const dot = `<circle cx="${x(p.x)}" cy="${y(p.y)}" r="6.5" fill="${colors[p.pos] || "#888"}" stroke="#fff" stroke-width="1.5" opacity=".88"><title>${esc(p.tip)}</title></circle>`;
    s += STATIC.on ? dot : `<a href="#/players/${p.id}">${dot}</a>`;
  }
  return {svg: s + "</svg>", mx, my};
}
