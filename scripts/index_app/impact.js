/* ===================================================== impact metrics (port of impact.py) */
const MATCH_MINUTES = 90, MIN_WITH = 270, MIN_WITHOUT = 180, OWN_GOAL = "4";
const minWith = tm => Math.max(MIN_WITH, 0.30 * tm), minWithout = tm => Math.max(MIN_WITHOUT, 0.20 * tm);
const pointsOf = (f, a) => f > a ? 3 : f === a ? 1 : 0;
const per90 = (v, mins) => mins > 0 ? v / mins * MATCH_MINUTES : null;
const eventsOf = sc => sc._byMatch || (sc._byMatch = sc.events.reduce((m, e) => (m.get(e.m) ? m.get(e.m).push(e) : m.set(e.m, [e]), m), new Map()));

function clubGoals(evs, clubId) {
  return evs.filter(e => e.t === "goal" && isNum(e.min)).map(e => ({t: num(e.min), mine: (e.club === clubId) !== (e.gt === OWN_GOAL), o: e.o}))
    .sort((a, b) => a.t - b.t || a.o - b.o);
}

function playerImpact(sc, pid, clubId) {
  const r = {min: 0, pj: 0, gf: 0, gc: 0, teamMin: 0, teamGF: 0, teamGC: 0, teamPts: 0, ptsExit: 0, ptsGained: 0, cleanSheets: 0, csEligible: 0,
    state: {win: 0, draw: 0, loss: 0}, bench: {n: 0, gf: 0, gc: 0, pts: 0, min: 0}, starts: 0, subbedOff: 0, subMinutes: [], yellow: 0, red: 0, gcAfterRed: 0};
  const clubMatches = sc.matches.filter(m => m.hc === clubId || m.ac === clubId);
  r.teamPJ = clubMatches.length;
  const mine = new Map(sc.apps.filter(a => a.pid === pid).map(a => [a.m, a]));
  const byMatch = eventsOf(sc);
  for (const m of clubMatches) {
    const home = m.hc === clubId, tf = home ? m.hs : m.as, ta = home ? m.as : m.hs;
    r.teamMin += MATCH_MINUTES; r.teamGF += tf; r.teamGC += ta; r.teamPts += pointsOf(tf, ta);
    const a = mine.get(m.id);
    if (!a || (!a.started && !a.played)) continue;
    const evs = byMatch.get(m.id) || [], goals = clubGoals(evs, clubId), own = evs.filter(e => e.pid === pid);
    const reds = own.filter(e => e.t === "rcard" && isNum(e.min)).map(e => num(e.min));
    const entry = a.started ? 0 : (a.mi || 0);
    let exit = isNum(a.mo) && a.mo !== null ? a.mo : null;
    if (exit === null && reds.length) exit = Math.min(...reds);
    const until = exit !== null ? exit : Infinity, leftAt = exit !== null ? exit : MATCH_MINUTES;
    const played = Math.max(leftAt - entry, 0);
    if (played <= 0) continue;
    const scoreAt = lim => [goals.filter(g => g.t <= lim && g.mine).length, goals.filter(g => g.t <= lim && !g.mine).length];
    r.pj++; r.min += played;
    const gf = goals.filter(g => g.t > entry && g.t <= until && g.mine).length, gc = goals.filter(g => g.t > entry && g.t <= until && !g.mine).length;
    r.gf += gf; r.gc += gc;
    const onEntry = scoreAt(entry), onExit = exit !== null ? scoreAt(exit) : [tf, ta];
    const pExit = pointsOf(...onExit), pEntry = pointsOf(...onEntry);
    r.ptsExit += pExit; r.ptsGained += pExit - pEntry;
    if (played >= 60) { r.csEligible++; if (gc === 0) r.cleanSheets++; }
    let cursor = entry, [ahead, behind] = onEntry;
    for (const g of goals) {
      if (g.t <= entry || g.t > leftAt) continue;
      r.state[ahead > behind ? "win" : ahead === behind ? "draw" : "loss"] += g.t - cursor;
      g.mine ? ahead++ : behind++; cursor = g.t;
    }
    r.state[ahead > behind ? "win" : ahead === behind ? "draw" : "loss"] += Math.max(leftAt - cursor, 0);
    if (a.started) {
      r.starts++;
      if (exit !== null && !reds.length) { r.subbedOff++; r.subMinutes.push(exit); }
    } else { r.bench.n++; r.bench.gf += gf; r.bench.gc += gc; r.bench.pts += pExit - pEntry; r.bench.min += played; }
    r.yellow += own.filter(e => e.t === "ycard").length;
    r.red += own.filter(e => e.t === "rcard").length;
    for (const red of reds) r.gcAfterRed += goals.filter(g => !g.mine && g.t > red).length;
  }
  r.pm = r.gf - r.gc; r.offMin = r.teamMin - r.min;
  r.minWith = minWith(r.teamMin); r.minWithout = minWithout(r.teamMin);
  r.dgOn = per90(r.pm, r.min);
  r.dgOff = r.offMin >= r.minWithout ? per90((r.teamGF - r.gf) - (r.teamGC - r.gc), r.offMin) : null;
  r.onoff = r.dgOn !== null && r.dgOff !== null ? r.dgOn - r.dgOff : null;
  r.ptsExitAvg = r.pj ? r.ptsExit / r.pj : null; r.ptsGainedAvg = r.pj ? r.ptsGained / r.pj : null;
  r.teamPPG = r.teamPJ ? r.teamPts / r.teamPJ : null; r.pctMin = r.teamMin ? r.min / r.teamMin : null;
  r.subMinuteAvg = r.subMinutes.length ? r.subMinutes.reduce((s, v) => s + v, 0) / r.subMinutes.length : null;
  r.cards90 = per90(r.yellow + r.red, r.min); r.smallSample = r.min < r.minWith;
  return r;
}

/* ================================================================ team statistics */
function teamGoalIntervals(sc, clubId) {
  const ids = new Set(sc.matches.filter(m => m.hc === clubId || m.ac === clubId).map(m => m.id));
  const f = Array(6).fill(0), a = Array(6).fill(0);
  for (const e of sc.events) {
    if (e.t !== "goal" || !ids.has(e.m)) continue;
    const m = num(e.min), i = m <= 15 ? 0 : m <= 30 ? 1 : m <= 45 ? 2 : m <= 60 ? 3 : m <= 75 ? 4 : 5;
    (e.club === clubId ? f : a)[i]++;
  }
  return {f, a};
}
function teamGoalDifference(sc, clubId) {
  const by = new Map();
  for (const m of sc.matches) {
    if (m.hc !== clubId && m.ac !== clubId) continue;
    by.set(m.week, (by.get(m.week) || 0) + (m.hc === clubId ? m.hs - m.as : m.as - m.hs));
  }
  let cum = 0;
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([week, weekly]) => ({week, weekly, cum: (cum += weekly)}));
}
function standingsEvolution(week) {
  const byClub = new Map(D.clubs.map(c => [c.id, []])), weeks = WEEKS.filter(w => w <= week);
  for (const w of weeks) for (const r of scope(w).standings) byClub.get(r.club).push({week: w, pos: r.rank});
  return {weeks, byClub};
}

/* ================================================================ player statistics */
function playerAvailability(sc, pid, clubId) {
  const mine = sc.apps.filter(a => a.pid === pid);
  return {total: sc.matches.filter(m => m.hc === clubId || m.ac === clubId).length, called: new Set(mine.map(a => a.m)).size,
    played: new Set(mine.filter(a => a.played).map(a => a.m)).size, starts: new Set(mine.filter(a => a.started).map(a => a.m)).size,
    minutes: mine.reduce((s, a) => s + appMinutes(a), 0)};
}
function playerEventIntervals(sc, pid, type) {
  const home = Array(6).fill(0), away = Array(6).fill(0);
  for (const e of sc.events) {
    if (e.t !== type || e.pid !== pid) continue;
    const m = num(e.min), i = m <= 15 ? 0 : m <= 30 ? 1 : m <= 45 ? 2 : m <= 60 ? 3 : m <= 75 ? 4 : 5;
    (e.club === matchById[e.m].hc ? home : away)[i]++;
  }
  return {home, away};
}
function playerSubstitutions(sc, pid) {
  return sc.events.filter(e => e.t === "subs" && (e.pid === pid || e.ipid === pid)).map(e => {
    const m = matchById[e.m], enters = e.ipid === pid;
    return {date: m.date, match: `${m.hn} · ${m.an}`, side: e.club === m.hc ? "Local" : "Visitante", minute: num(e.min), action: enters ? "Entra" : "Sale",
      rel: `${S.lang === "en" ? "for" : "por"} ${enters ? e.pname : e.iname}`};
  }).sort((a, b) => b.date.localeCompare(a.date) || b.minute - a.minute);
}
