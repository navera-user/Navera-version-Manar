/* NAVERA Academy — student workspace */
'use strict';
const $ = (id) => document.getElementById(id);
const AS = new URLSearchParams(location.search).get('as');   // teacher viewing a student
const ME = {};
let COURSES = [], MODULES = [], LESSON = null, DOC = 'course';

function withAs(url) {
  if (!AS) return url;
  return url + (url.includes('?') ? '&' : '?') + 'as=' + encodeURIComponent(AS);
}
async function api(url, opts = {}) {
  const o = {...opts, headers: {'Content-Type': 'application/json', ...(opts.headers || {})}};
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  const r = await fetch(withAs(url), o);
  if (r.status === 401) { location.href = '/'; throw new Error('login'); }
  let d = {};
  try { d = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}
function toast(msg, ms = 3200) {
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), ms);
}
function modal(title, html, buttons) {
  return new Promise((resolve) => {
    const bg = document.createElement('div'); bg.className = 'modal-bg';
    bg.innerHTML = `<div class="modal"><h3></h3><div class="mb">${html}</div><div class="row"></div></div>`;
    bg.querySelector('h3').textContent = title;
    const row = bg.querySelector('.row');
    for (const [label, val, cls] of buttons) {
      const b = document.createElement('button'); b.textContent = label; if (cls) b.className = cls;
      b.onclick = () => { bg.remove(); resolve(val === undefined ? bg : val); };
      b.onmousedown = () => { bg._vals = [...bg.querySelectorAll('input')].map(i => i.value); };
      row.appendChild(b);
    }
    document.body.appendChild(bg);
    const i = bg.querySelector('input'); if (i) i.focus();
  });
}
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

/* ------------------------------------------------------------------ start */
async function init() {
  Object.assign(ME, await api('/api/me'));
  $('uname').textContent = ME.display;
  $('uinfo').innerHTML = `Logged in as <b>${esc(ME.name)}</b> · ROS domain ${ME.domain}` +
    (ME.base ? `<br>NAVERA base: ${esc(ME.base.subject.slice(0, 60))}` : '');
  if (ME.role === 'teacher') $('mTeacher').style.display = '';
  if (AS) { $('asBanner').style.display = ''; $('asBanner').textContent = 'viewing ' + AS; }
  const c = await api('/api/courses');
  COURSES = c.lessons; MODULES = c.modules;
  route();
  window.addEventListener('hashchange', route);
  pollBookings(); setInterval(pollBookings, 8000);
}
function route() {
  if (window.Tour) Tour.close();
  const m = location.hash.match(/^#lesson\/(.+)$/);
  if (m) openLesson(decodeURIComponent(m[1])); else showHome();
}

/* ------------------------------------------------------------------ home */
function moduleOf(id) {
  const i = MODULES.findIndex(m => (m.lessons || []).includes(id));
  return i < 0 ? {color: '#c8892f', leg: '', idx: 0, title: ''} : {...MODULES[i], idx: i};
}
const XP_PER_MISSION = 100;
const RANKS = [[0, 'Fledgling', 'egg'], [3, 'Glider', 'plane'], [8, 'Wayfinder', 'compass'],
  [15, 'Navigator', 'map'], [22, 'Falcon', 'eye'], [30, 'Migration Master', 'globe']];
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII'];
const LEG_ICONS = ['egg', 'map', 'flock', 'compass', 'eye', 'scales', 'globe'];
const ICONS = {
  compass: '<g fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z" fill="currentColor" stroke="none"/></g>',
  plane: '<path fill="currentColor" d="M3 13.5l7-2 4-7c.6-1 2-.8 2 .3L15 11.5l5 1.5v2L15 14.5l-1 4 1.5 1.5v1L12 19.5l-3.5 1.5v-1L10 18.5l1-4-8 1z"/>',
  egg: '<path fill="none" stroke="currentColor" stroke-width="1.8" d="M12 3c-3.6 0-6.6 5.6-6.6 10a6.6 6.6 0 0 0 13.2 0C18.6 8.6 15.6 3 12 3z"/>',
  map: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z"/><path d="M9 4v14M15 6v14"/></g>',
  flock: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2.5 10c1.6-1.2 3.2-1.2 4.5 0 1.3-1.2 2.9-1.2 4.5 0"/><path d="M11 5.5c1.3-1 2.6-1 3.7 0 1.1-1 2.4-1 3.7 0"/><path d="M12 16c1.5-1.1 3-1.1 4.2 0 1.2-1.1 2.7-1.1 4.2 0"/></g>',
  eye: '<g fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></g>',
  scales: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3v17M7 20h10M5 6h14M5 6l-3 7h6zM19 6l-3 7h6z"/></g>',
  globe: '<g fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/></g>',
  moon: '<path fill="none" stroke="currentColor" stroke-width="1.8" d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  magnify: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l6 6"/></g>',
  stars: '<path fill="currentColor" d="M9 3l1.6 4.4L15 9l-4.4 1.6L9 15l-1.6-4.4L3 9l4.4-1.6zM18 13l.8 2.2 2.2.8-2.2.8L18 19l-.8-2.2L15 16l2.2-.8z"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24">${ICONS[n] || ''}</svg>`;
const BIRD_PATH = 'M62 32 Q58.5 28.4 51 28.6 Q47 13 21 5 Q31 17 37.5 29 Q32 29.4 27 30.4 L3 22.5 Q12.5 29.4 17.5 32 Q12.5 34.6 3 41.5 L27 33.6 Q32 34.6 37.5 35 Q31 47 21 59 Q47 51 51 35.4 Q58.5 35.6 62 32 Z';
const bird = (x, y, s, fill, op = 1) => `<g transform="translate(${x} ${y}) scale(${s / 64})" opacity="${op}"><path d="${BIRD_PATH}" fill="${fill}"/></g>`;
const DUSK_DEFS = `<linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f1530"/><stop offset=".45" stop-color="#3b3a6b"/><stop offset=".72" stop-color="#c9707a"/><stop offset=".9" stop-color="#f2a65e"/><stop offset="1" stop-color="#f7c27a"/></linearGradient>
  <linearGradient id="r1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5a4a78"/><stop offset="1" stop-color="#3a3157"/></linearGradient>
  <linearGradient id="r2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a3157"/><stop offset="1" stop-color="#241f3c"/></linearGradient>
  <linearGradient id="dune" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9784a"/><stop offset="1" stop-color="#7c4a2c"/></linearGradient>
  <radialGradient id="sun" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#fff1c9"/><stop offset=".5" stop-color="#ffc77a"/><stop offset="1" stop-color="#ffc77a" stop-opacity="0"/></radialGradient>`;
function rankFor(passed) {
  let i = 0;
  RANKS.forEach((r, k) => { if (passed >= r[0]) i = k; });
  const next = RANKS[i + 1];
  return {name: RANKS[i][1], icon: RANKS[i][2], idx: i, from: RANKS[i][0], next: next ? next[0] : null, nextName: next ? next[1] : null};
}
function heroScene() {
  return `<svg class="scene" viewBox="0 0 1440 640" preserveAspectRatio="xMidYMid slice"><defs>${DUSK_DEFS}</defs>
    <rect width="1440" height="640" fill="url(#dusk)"/>
    <g fill="#fff" opacity=".8"><circle cx="120" cy="80" r="1.2"/><circle cx="260" cy="130" r="1"/><circle cx="420" cy="60" r="1.4"/><circle cx="620" cy="110" r="1"/>
      <circle cx="760" cy="50" r="1.2"/><circle cx="980" cy="90" r="1"/><circle cx="1120" cy="60" r="1.3"/><circle cx="1300" cy="120" r="1"/><circle cx="1380" cy="70" r="1.2"/><circle cx="560" cy="170" r=".9"/></g>
    <path d="M1180 112 a26 26 0 1 0 22 40 a20 20 0 1 1 -22 -40z" fill="#fff4dc" opacity=".9"/>
    <circle cx="980" cy="500" r="170" fill="url(#sun)" opacity=".8"/>
    <path d="M0 470 L120 400 L210 440 L330 350 L450 430 L560 370 L680 450 L800 370 L930 440 L1060 360 L1190 430 L1300 380 L1440 430 L1440 640 L0 640Z" fill="url(#r1)"/>
    <path d="M0 510 L140 450 L260 490 L400 420 L520 490 L660 440 L780 510 L920 450 L1060 510 L1200 460 L1440 500 L1440 640 L0 640Z" fill="url(#r2)"/>
    <path d="M0 570 Q240 520 480 565 T960 560 T1440 550 L1440 640 L0 640Z" fill="url(#dune)"/>
    <path d="M0 605 Q300 575 640 603 T1440 595 L1440 640 L0 640Z" fill="#5c3520" opacity=".7"/>
    ${bird(1030, 200, 40, '#14112a', .85)}${bird(1084, 232, 26, '#14112a', .8)}${bird(992, 246, 22, '#14112a', .75)}</svg>`;
}
function expeditionSVG(lessons) {
  const W = 1220, H = 380, n = lessons.length;
  const next = lessons.findIndex(l => l.progress.status !== 'passed');
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Expedition map"><defs>${DUSK_DEFS}
      <filter id="gl"><feGaussianBlur stdDeviation="3.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
    <rect width="${W}" height="${H}" fill="url(#dusk)"/>
    <g fill="#fff" opacity=".7"><circle cx="90" cy="40" r="1.1"/><circle cx="300" cy="70" r="1"/><circle cx="520" cy="30" r="1.3"/><circle cx="700" cy="60" r="1"/><circle cx="880" cy="25" r="1.2"/><circle cx="1060" cy="55" r="1"/><circle cx="1160" cy="30" r="1.1"/></g>
    <circle cx="1010" cy="320" r="120" fill="url(#sun)" opacity=".7"/>
    <path d="M0 290 L110 230 L200 265 L320 190 L430 255 L540 205 L650 270 L760 200 L880 265 L990 215 L1100 260 L1220 225 L1220 380 L0 380Z" fill="url(#r1)" opacity=".9"/>
    <path d="M0 320 L130 275 L250 310 L380 255 L500 310 L630 270 L760 325 L890 280 L1020 320 L1140 285 L1220 310 L1220 380 L0 380Z" fill="url(#r2)"/>
    <path d="M0 350 Q240 320 480 348 T960 342 T1220 338 L1220 380 L0 380Z" fill="url(#dune)"/>
    <path id="route" d="M50 240 C150 130 250 270 360 185 S560 90 660 170 S860 280 960 175 S1130 105 1180 150" fill="none" stroke="rgba(255,236,200,.45)" stroke-width="2" stroke-dasharray="2 8" stroke-linecap="round"/>
    <g id="wps"></g><g id="leglabels" font-family="Fraunces, serif" font-size="15" fill="rgba(255,240,215,.88)" text-anchor="middle"></g></svg>`;
  return g;
}
function placeWaypoints(lessons) {
  const p = document.getElementById('route'); if (!p) return;
  const g = document.getElementById('wps'), labels = document.getElementById('leglabels'), L = p.getTotalLength(), n = lessons.length;
  const next = lessons.findIndex(l => l.progress.status !== 'passed');
  let h = '';
  lessons.forEach((l, i) => {
    const q = p.getPointAtLength(L * i / Math.max(1, n - 1)), done = l.progress.status === 'passed', now = i === next;
    const t = `<title>Mission ${esc(l.number)} · ${esc(l.title)}${done ? ' — complete' : ''}</title>`;
    if (done) h += `<g class="wp" data-id="${esc(l.id)}">${t}<circle class="r" cx="${q.x}" cy="${q.y}" r="10" fill="#e8b25c" stroke="#fff4dc" stroke-width="0" filter="url(#gl)"/><path d="M${q.x - 4} ${q.y} l3 3 l5.5 -6" stroke="#3a2405" stroke-width="2.2" fill="none" stroke-linecap="round"/></g>`;
    else if (now) h += `<g class="wp" data-id="${esc(l.id)}">${t}<circle cx="${q.x}" cy="${q.y}" r="18" fill="rgba(255,208,138,.25)"><animate attributeName="r" values="13;22;13" dur="2.2s" repeatCount="indefinite"/></circle><circle class="r" cx="${q.x}" cy="${q.y}" r="11" fill="#fff4dc" stroke="#e8b25c" stroke-width="3"/><text x="${q.x}" y="${q.y + 4}" font-family="Inter" font-weight="700" font-size="11" text-anchor="middle" fill="#9c6a22">${+l.number}</text>${bird(q.x - 22, q.y - 60, 44, '#fff4dc', .95)}</g>`;
    else h += `<g class="wp" data-id="${esc(l.id)}">${t}<circle class="r" cx="${q.x}" cy="${q.y}" r="9.5" fill="rgba(20,17,42,.55)" stroke="rgba(255,236,200,.6)" stroke-width="1.5"/><text x="${q.x}" y="${q.y + 3.5}" font-family="Inter" font-size="9.5" font-weight="600" text-anchor="middle" fill="rgba(255,236,200,.88)">${+l.number}</text></g>`;
  });
  g.innerHTML = h;
  // a label under the middle of each leg
  let lab = '';
  MODULES.forEach((m, k) => {
    const idx = (m.lessons || []).map(id => lessons.findIndex(l => l.id === id)).filter(i => i >= 0);
    if (!idx.length) return;
    const mid = (Math.min(...idx) + Math.max(...idx)) / 2;
    const x = p.getPointAtLength(L * mid / Math.max(1, n - 1)).x;
    lab += `<text x="${x}" y="368">${ROMAN[k]} · ${esc(m.short || (m.title || '').split(/[:,]/)[0])}</text>`;
  });
  labels.innerHTML = lab;
  g.querySelectorAll('.wp').forEach(w => w.onclick = () => { location.hash = 'lesson/' + w.dataset.id; });
}
function badgesHTML(lessons) {
  const st = Object.fromEntries(lessons.map(l => [l.id, l.progress.status]));
  const passed = lessons.filter(l => l.progress.status === 'passed').length;
  const list = MODULES.map((m, i) => ({icon: LEG_ICONS[i] || 'compass', name: (m.leg || '').replace(/^Leg \d+ · /, '') || m.title,
    hint: `Leg ${ROMAN[i]}`, on: (m.lessons || []).length > 0 && (m.lessons || []).every(id => st[id] === 'passed')}));
  list.unshift({icon: 'plane', name: 'First flight', hint: 'pass 1 mission', on: passed >= 1});
  list.push({icon: 'moon', name: 'Halfway there', hint: '15 missions', on: passed >= 15});
  list.push({icon: 'magnify', name: 'Spoof hunter', hint: 'mission 27', on: st['27-spoofing'] === 'passed'});
  list.push({icon: 'stars', name: 'Star reader', hint: 'mission 24', on: st['24-night-and-stars'] === 'passed'});
  return {html: list.map(b => `<div class="md ${b.on ? 'on' : ''}"><div class="disc">${icon(b.icon)}</div><b>${esc(b.name)}</b><span>${b.on ? 'earned' : esc(b.hint)}</span></div>`).join(''),
    earned: list.filter(b => b.on).length, total: list.length};
}
async function showHome() {
  try { const c = await api('/api/courses'); COURSES = c.lessons; MODULES = c.modules; } catch (e) {}
  $('work').style.display = 'none'; $('home').style.display = '';
  document.body.classList.add('at-home');
  $('crumb').innerHTML = '';
  const passed = COURSES.filter(l => l.progress.status === 'passed').length;
  const next = COURSES.find(l => l.progress.status !== 'passed');
  const first = ME.display.split(' ')[0];
  const r = rankFor(passed), xp = passed * XP_PER_MISSION;
  const pct = r.next === null ? 100 : Math.max(3, Math.round(100 * (passed - r.from) / (r.next - r.from)));
  const b = badgesHTML(COURSES);
  const headline = passed === 0 ? `Find your way<br>when the <i>sky goes quiet.</i>` : `Welcome back,<br><i>${esc(first)}.</i>`;
  const text = passed === 0
    ? `Every autumn, swallows cross Oman without a single satellite — landmarks, the sun, the stars and an inner compass, each checked against the others. In ${COURSES.length} missions you will build the same skills for machines, on NAVERA's real code.`
    : passed === COURSES.length ? `All ${COURSES.length} missions complete — ${xp} XP. You have rebuilt the ideas behind NAVERA one by one.`
    : `${passed} of ${COURSES.length} missions complete. Next on your route: <b>${esc(next.title)}</b>. Your NAVERA copy is your own aircraft: change it freely, Reset brings back the factory version.`;
  let h = `<header class="hhero">${heroScene()}<div class="hwrap"><div class="hgrid">
      <div><div class="kicker">${next ? `${esc(moduleOf(next.id).leg || '')} · Mission ${esc(next.number)}` : 'Expedition complete'}</div>
        <h1>${headline}</h1><p>${text}</p>
        ${next ? `<button class="go hbtn" id="goNext">${passed ? `Continue mission ${+next.number}` : 'Start mission 1'} →</button>` : ''}<button class="hbtn line" id="goMap">Open the expedition map</button><button class="hbtn line" id="goIntro">▶ Watch the intro</button></div>
      <div class="glass"><div class="rank"><div class="medal">${icon(r.icon)}</div><div><b>${esc(r.name)}</b><span>Rank ${r.idx + 1} of ${RANKS.length} · ${xp} XP</span></div></div>
        <div class="bar"><i style="width:${pct}%"></i></div>
        <div class="row"><span>Missions</span><b>${passed} / ${COURSES.length}</b></div>
        <div class="row"><span>Next rank</span><b>${r.next === null ? '—' : `${esc(r.nextName)} · ${r.next - passed} mission${r.next - passed > 1 ? 's' : ''}`}</b></div>
        <div class="row"><span>Badges</span><b>${b.earned} of ${b.total}</b></div>
        ${next ? `<button class="go" id="goNext2">Next mission →</button>` : ''}</div>
    </div></div></header>
    <div class="wrap">
      <div class="shead" id="mapHead"><div class="kicker">Your route</div><h2>Expedition map</h2><p>${COURSES.length} waypoints across ${MODULES.length} legs — click any waypoint to open its mission.</p></div>
      <div class="mapcard">${expeditionSVG(COURSES)}</div>
      <div class="shead"><div class="kicker">Achievements</div><h2>Badges</h2><p>Complete a whole leg to earn its badge.</p></div>
      <div class="medals">${b.html}</div>
      <div class="shead" style="margin-bottom:0"><div class="kicker">Missions</div><h2>${MODULES.length} legs, ${COURSES.length} missions</h2></div>`;
  const byId = Object.fromEntries(COURSES.map(l => [l.id, l]));
  MODULES.forEach((m, k) => {
    const ls = (m.lessons || []).map(id => byId[id]).filter(Boolean);
    const done = ls.filter(l => l.progress.status === 'passed').length;
    h += `<div class="legblock"><div><div class="kicker">${esc(m.leg || `Leg ${ROMAN[k]}`)}</div><h3>${esc(m.title)}</h3><p class="ld">${esc(m.desc || '')}</p>
      <div class="lp"><i style="width:${ls.length ? 100 * done / ls.length : 0}%"></i></div><div class="lc">${done} of ${ls.length} complete</div></div><div class="mlist">`;
    for (const l of ls) {
      const st = l.progress.status, isNext = next && next.id === l.id;
      const cls = st === 'passed' ? 'done' : isNext ? 'now' : '';
      const status = st === 'passed' ? '<span class="status done">Complete</span>' : isNext ? `<span class="status now">${st === 'started' ? 'In progress' : 'Up next'}</span>`
        : st === 'started' ? '<span class="status next">Started</span>' : '<span class="status next">Later</span>';
      const res = (l.resources || []).map(x => x === 'sim' ? 'needs the simulator' : x === 'camera' ? 'needs the camera' : 'needs the sensors').join(' · ');
      h += `<div class="mitem ${cls}" data-id="${esc(l.id)}"><div class="no">${esc(l.number)}</div><div><h4>${esc(l.title)}</h4><p>${esc(l.summary || '')}</p>${res ? `<div class="res">${res}</div>` : ''}</div>
        <div class="dur">${esc(l.duration || '')}</div><div class="xp">+${XP_PER_MISSION} XP</div>${status}</div>`;
    }
    h += '</div></div>';
  });
  h += `<div class="foot">NAVERA Academy · NAVERA is developed by IRIS Systems · Release 0.x — field validation pending</div></div>`;
  $('home').innerHTML = h;
  placeWaypoints(COURSES);
  $('home').querySelectorAll('.mitem').forEach(c => c.onclick = () => { location.hash = 'lesson/' + c.dataset.id; });
  ['goNext', 'goNext2'].forEach(id => { if ($(id)) $(id).onclick = () => { location.hash = 'lesson/' + next.id; }; });
  $('goMap').onclick = () => $('mapHead').scrollIntoView({behavior: 'smooth'});
  $('goIntro').onclick = () => Intro.show();
  $('home').onscroll = () => document.body.classList.toggle('scrolled', $('home').scrollTop > 40);
  Intro.maybe(() => Tour.maybe('home'));
}

/* ------------------------------------------------------------------ lesson */
async function openLesson(id) {
  let l;
  try { l = await api('/api/lesson/' + encodeURIComponent(id)); } catch (e) { toast(e.message); location.hash = ''; return; }
  const switched = !LESSON || LESSON.id !== l.id;
  LESSON = l;
  $('home').style.display = 'none'; $('work').style.display = ''; document.body.classList.remove('at-home', 'scrolled');
  $('crumb').innerHTML = `Mission ${esc(l.number)} · <b>${esc(l.title)}</b>`;
  $('checkBtn').style.display = l.has_check ? '' : 'none';
  setStatus(l.progress);
  const idx = COURSES.findIndex(c => c.id === id);
  $('prevBtn').disabled = idx <= 0; $('nextBtn').disabled = idx < 0 || idx >= COURSES.length - 1;
  $('prevBtn').onclick = () => { location.hash = 'lesson/' + COURSES[idx - 1].id; };
  $('nextBtn').onclick = () => { location.hash = 'lesson/' + COURSES[idx + 1].id; };
  $('result').className = 'result';
  if (switched) { showDoc('course'); treeRoot = ''; await loadTree(); }
  else showDoc(DOC);
  if (switched && l.open) for (const f of l.open) openFile(`lessons/${l.id}/${f}`, false);
  if (switched && Terms.list.length === 0 && l.terminal !== false && document.querySelector('[data-pane=terminal].on')) Terms.add();
  Tour.maybe('mission');
}
function setStatus(p) {
  const s = $('lstatus');
  if (p && p.status === 'passed') { s.className = 'badge passed'; s.textContent = '✔ passed'; }
  else if (p && p.status === 'started') { s.className = 'badge started'; s.textContent = `tried ${p.attempts}×` + (p.total ? ` · best ${p.best}/${p.total}` : ''); }
  else { s.className = 'badge'; s.textContent = 'not checked yet'; }
}
document.querySelectorAll('.notebook .tab').forEach(t => t.onclick = () => showDoc(t.dataset.doc));
function missionHeader(which) {
  const m = moduleOf(LESSON.id);
  const tasks = ((LESSON.lab || '').match(/\[!TASK\]/g) || []).length;
  const done = LESSON.progress && LESSON.progress.status === 'passed';
  const h1 = ((which === 'lab' ? LESSON.lab : LESSON.course) || '').match(/^#\s+(.+)$/m);
  const res = (LESSON.resources || []).map(r => `<span class="chip2">${r === 'sim' ? 'Simulator' : r === 'camera' ? 'Camera' : 'Sensors'}</span>`).join('');
  return `<div class="mhero">
    <svg class="ridge" viewBox="0 0 600 70" preserveAspectRatio="none"><path d="M0 56 L60 30 L110 46 L170 18 L230 44 L290 26 L350 50 L420 22 L480 46 L540 30 L600 44 L600 70 L0 70Z" fill="#3a3157" opacity=".9"/><path d="M0 64 Q150 52 300 62 T600 60 L600 70 L0 70Z" fill="#7c4a2c" opacity=".85"/></svg>
    <span class="navi"></span>
    <div class="leg">${esc(m.leg || '')} · Mission ${esc(LESSON.number)} · ${which === 'lab' ? 'Lab' : 'Briefing'}</div>
    <h1>${esc(h1 ? h1[1] : LESSON.title)}</h1>
    <div class="chips"><span class="chip2">⏱ ${esc(LESSON.duration || '')}</span><span class="chip2">★ +${XP_PER_MISSION} XP</span>
      ${tasks ? `<span class="chip2">◎ ${tasks} task${tasks > 1 ? 's' : ''}</span>` : ''}${res}
      ${done ? '<span class="chip2 done">✔ Complete</span>' : ''}</div>
    ${LESSON.outdated ? `<div class="update">This mission was updated since you started it. <button class="go" id="getNew">Get the new lab files</button>
      <span style="color:var(--muted)">your current files are kept in a backup</span></div>` : ''}</div>`;
}
function updateReadbar() {
  const d = $('doc'), max = d.scrollHeight - d.clientHeight;
  $('readbar').firstElementChild.style.width = (max > 0 ? Math.min(100, 100 * d.scrollTop / max) : 100) + '%';
}
function showDoc(which) {
  DOC = which;
  if (which === 'lab') Tip.once('first-lab');
  document.querySelectorAll('.notebook .tab').forEach(t => t.classList.toggle('on', t.dataset.doc === which));
  renderMarkdown($('doc'), (which === 'lab' ? LESSON.lab : LESSON.course).replace(/^#\s+.+$/m, ''));
  $('doc').insertAdjacentHTML('afterbegin', missionHeader(which));
  if ($('getNew')) $('getNew').onclick = async () => {
    await api(`/api/lesson/${LESSON.id}/reset`, {method: 'POST', body: {}});
    Editor.closeUnder(`lessons/${LESSON.id}/`); LESSON = null; await openLesson(location.hash.slice(8)); await loadTree();
    toast('New lab files installed — your previous files are in a backup');
  };
  $('doc').scrollTop = 0; updateReadbar();
}

marked.setOptions({gfm: true, breaks: false});
$('doc').addEventListener('scroll', () => updateReadbar());
function renderMarkdown(el, md) {
  const lid = LESSON.id;
  md = (md || '').replace(/\]\((?:\.\/)?assets\//g, `](/course-assets/${lid}/`)
    .replace(/src="(?:\.\/)?assets\//g, `src="/course-assets/${lid}/`);
  el.innerHTML = marked.parse(md);
  // callouts:  > [!TIP] ...
  el.querySelectorAll('blockquote').forEach(bq => {
    const first = bq.firstElementChild;
    if (!first) return;
    const m = first.innerHTML.match(/^\s*\[!(NOTE|TIP|WARNING|TASK|QUESTION|BIRD)\]\s*(.*)/is);
    if (!m) return;
    const kind = m[1].toLowerCase();
    // "> [!NOTE] In short" — a short text on the marker line becomes the box title
    const firstLine = m[2].split(/\n|<br\s*\/?>/)[0].trim();
    const more = m[2].trim() !== firstLine || first.nextElementSibling;
    const custom = firstLine && firstLine.length <= 40 && !/[.:]$/.test(firstLine) && more ? firstLine : null;
    if (custom) m[2] = m[2].slice(m[2].indexOf(firstLine) + firstLine.length).replace(/^\s*(<br\s*\/?>)?/, '');
    const labels = {note: 'Note', tip: 'Tip', warning: 'Careful', task: 'Task', question: 'Question', bird: "🐦 Bird's-eye view"};
    first.innerHTML = m[2];
    if (!first.innerHTML.trim()) first.remove();
    const d = document.createElement('div'); d.className = 'callout ' + kind;
    d.innerHTML = `<div class="ct">${custom ? esc(custom) : labels[kind]}</div>` + bq.innerHTML;
    bq.replaceWith(d);
  });
  // headings that already start with an emoji get no extra feather
  el.querySelectorAll('h2').forEach(h => { if (/^\p{Extended_Pictographic}/u.test(h.textContent.trim())) h.classList.add('nofeather'); });
  el.querySelectorAll('pre code').forEach(code => {
    const pre = code.parentElement;
    const lang = (code.className.match(/language-(\S+)/) || [])[1] || '';
    try { hljs.highlightElement(code); } catch (e) {}
    const text = code.textContent;
    const b = document.createElement('button');
    if (lang === 'bash' || lang === 'sh' || lang === 'shell') {
      b.className = 'run'; b.textContent = '▶ Run'; b.title = 'Send to the terminal';
      b.onclick = () => runInTerminal(text.replace(/^\$ /gm, '').trim());
    } else {
      b.className = 'run copy'; b.textContent = 'Copy';
      b.onclick = () => { navigator.clipboard?.writeText(text); b.textContent = 'Copied'; setTimeout(() => b.textContent = 'Copy', 1200); };
    }
    pre.appendChild(b);
  });
  // links "file:lessons/..." or "file:navera/..." open in the editor
  el.querySelectorAll('a[href^="file:"]').forEach(a => {
    const p = a.getAttribute('href').slice(5).replace(/^\.\//, `lessons/${lid}/`);
    a.classList.add('file'); a.href = '#';
    a.onclick = (e) => { e.preventDefault(); showPane('editor'); openFile(p, true); };
  });
  el.querySelectorAll('a[href^="http"]').forEach(a => a.target = '_blank');
}
function runInTerminal(cmd) {
  showPane('terminal');
  const t = Terms.active() || Terms.add();
  const go = () => t.send(cmd + '\r');
  if (t.ready) go(); else t.queue.push(go);
}

$('checkBtn').onclick = async () => {
  await Editor.saveAll();
  const b = $('checkBtn'); b.disabled = true; b.textContent = '⏳ Checking…';
  try {
    const r = await api(`/api/lesson/${LESSON.id}/check`, {method: 'POST', body: {}});
    $('result').className = 'result show ' + (r.passed ? 'ok' : 'bad');
    const sc = r.score ? ` — ${r.score.passed}/${r.score.total}` : '';
    const partly = r.score && r.score.passed > 0;
    $('rimg').src = '/static/img/' + (r.passed ? 'navi-cheer' : partly ? 'navi-think' : 'navi-oops') + '.svg';
    $('rscore').textContent = r.score ? `${r.score.passed}/${r.score.total}` : (r.passed ? '✔' : '✘');
    $('rhead').innerHTML = r.passed ? 'Mission checks passed<small>Every check is green — well flown.</small>'
      : partly ? 'Almost there<small>Read the ✘ lines and their hints below, fix, save and check again.</small>'
      : 'Not yet<small>Start with the first ✘ line — its hint tells you where to look.</small>';
    $('rout').innerHTML = (r.output.trim() || '(no output)').split('\n').map(line => {
      const t = line.trim();
      const cls = /^✔/.test(t) ? 'ok' : /^✘/.test(t) ? 'ko' : /^→/.test(t) ? 'why' : /^💡/.test(t) ? 'hint'
        : /^(🎉|\d+ of \d+ checks)/.test(t) ? 'sum' : 'plain';
      return `<div class="${cls}">${esc(cls === 'plain' ? line : t)}</div>`;
    }).join('');
    setTimeout(() => Tip.once(r.passed ? 'first-pass' : 'first-fail'), r.passed ? 4800 : 600);
    if (r.passed && !(LESSON.progress && LESSON.progress.status === 'passed')) {
      const before = COURSES.filter(c => c.progress.status === 'passed').length;
      try { const c = await api('/api/courses'); COURSES = c.lessons; } catch (e) {}
      celebrate(before, COURSES.filter(c => c.progress.status === 'passed').length);
    }
    const l = await api('/api/lesson/' + LESSON.id); LESSON.progress = l.progress; setStatus(l.progress);
  } catch (e) { toast(e.message); }
  b.disabled = false; b.textContent = '✔ Check my work';
};
function celebrate(before, after) {
  const p = document.createElement('div'); p.className = 'party';
  const r0 = rankFor(before), r1 = rankFor(after);
  const up = r1.name !== r0.name ? `<span class="rankup">New rank: ${esc(r1.name)}</span>` : '';
  p.innerHTML = `<div class="cheer"><div class="medal">${icon(r1.icon)}</div><div><b>Mission complete</b><span>+${XP_PER_MISSION} XP · ${after} of ${COURSES.length} missions</span>${up}</div></div>`;
  document.body.appendChild(p);
  setTimeout(() => p.remove(), up ? 5200 : 4400);
}
$('rclose').onclick = () => $('result').className = 'result';
$('resetLesson').onclick = async () => {
  const ok = await modal('Reset the lab files?', `<p>The files of this lesson go back to how they were at the start.
    Your current version is kept in a backup (the teacher can find it).</p>`, [['Cancel', false], ['Reset', true, 'primary']]);
  if (!ok) return;
  await api(`/api/lesson/${LESSON.id}/reset`, {method: 'POST', body: {}});
  Editor.closeUnder(`lessons/${LESSON.id}/`);
  await loadTree(); toast('Lab files reset');
  if (LESSON.open) for (const f of LESSON.open) openFile(`lessons/${LESSON.id}/${f}`, false);
};

/* ------------------------------------------------------------------ panes */
document.querySelectorAll('.tools .tab').forEach(t => t.onclick = () => showPane(t.dataset.pane));
function showPane(p) {
  document.querySelectorAll('.tools .tab').forEach(t => t.classList.toggle('on', t.dataset.pane === p));
  document.querySelectorAll('.tools .pane').forEach(x => x.classList.toggle('on', x.id === 'pane-' + p));
  if (p === 'terminal') { if (!Terms.list.length) Terms.add(); else Terms.fitAll(); Tip.once('first-terminal'); }
  if (p === 'editor') Editor.layout();
  if (p === 'sim' && !$('simFrame').src) loadWeb('sim');
  if (p === 'operator' && !$('opFrame').src) loadWeb('op');
}
function loadWeb(which) {
  const host = location.hostname;
  const url = which === 'sim' ? `http://${host}:8190/` : `http://${host}:8181/operator`;
  const f = which === 'sim' ? $('simFrame') : $('opFrame');
  (which === 'sim' ? $('simUrl') : $('opUrl')).value = url;
  f.src = url;
}
$('simReload').onclick = () => { $('simFrame').src = 'about:blank'; setTimeout(() => loadWeb('sim'), 50); };
$('opReload').onclick = () => { $('opFrame').src = 'about:blank'; setTimeout(() => loadWeb('op'), 50); };
$('simOpen').onclick = () => window.open(`http://${location.hostname}:8190/`, '_blank');
$('opOpen').onclick = () => window.open(`http://${location.hostname}:8181/operator`, '_blank');

// resizable split
(() => {
  const s = $('split'); let drag = false;
  s.onmousedown = (e) => { drag = true; s.classList.add('drag'); e.preventDefault(); };
  window.addEventListener('mousemove', (e) => {
    if (!drag) return;
    const w = Math.max(280, Math.min(window.innerWidth - 320, e.clientX));
    $('notebook').style.width = w + 'px';
  });
  window.addEventListener('mouseup', () => { if (drag) { drag = false; s.classList.remove('drag'); Editor.layout(); Terms.fitAll(); } });
  window.addEventListener('resize', () => { Editor.layout(); Terms.fitAll(); });
})();

/* ------------------------------------------------------------------ file tree */
let treeRoot = '', treeSel = null;
const openDirs = new Set(['lessons']);
async function loadTree() {
  if (LESSON) { openDirs.add('lessons'); openDirs.add('lessons/' + LESSON.id); }
  const box = $('treeItems'); box.innerHTML = '';
  await renderDir('', box, 0);
}
async function renderDir(path, box, depth) {
  let d;
  try { d = await api('/api/files?path=' + encodeURIComponent(path)); } catch (e) { return; }
  for (const it of d.items) {
    const n = document.createElement('div'); n.className = 'node';
    n.style.paddingLeft = (8 + depth * 14) + 'px';
    const isOpen = openDirs.has(it.path);
    n.textContent = (it.dir ? (isOpen ? '▾ 📂 ' : '▸ 📁 ') : fileIcon(it.name) + ' ') + it.name;
    n.dataset.path = it.path;
    if (treeSel === it.path) n.classList.add('sel');
    box.appendChild(n);
    const kids = document.createElement('div'); box.appendChild(kids);
    n.onclick = async () => {
      box.parentElement.querySelectorAll('.node.sel').forEach(x => x.classList.remove('sel'));
      $('treeItems').querySelectorAll('.node.sel').forEach(x => x.classList.remove('sel'));
      n.classList.add('sel'); treeSel = it.path;
      if (it.dir) {
        if (openDirs.has(it.path)) { openDirs.delete(it.path); kids.innerHTML = ''; n.textContent = '▸ 📁 ' + it.name; }
        else { openDirs.add(it.path); n.textContent = '▾ 📂 ' + it.name; await renderDir(it.path, kids, depth + 1); }
      } else openFile(it.path, true);
    };
    if (it.dir && isOpen) await renderDir(it.path, kids, depth + 1);
  }
}
function fileIcon(n) {
  if (/\.py$/.test(n)) return '🐍';
  if (/\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(n)) return '🖼️';
  if (/\.(md|txt)$/.test(n)) return '📄';
  if (/\.(sh|bash)$/.test(n)) return '⚙️';
  if (/\.(ya?ml|json|xml|csv)$/.test(n)) return '🧾';
  return '·';
}
$('tRefresh').onclick = loadTree;
$('tNew').onclick = async () => {
  const base = treeSel ? (treeSel.includes('.') ? treeSel.replace(/\/[^/]*$/, '') : treeSel) : (LESSON ? `lessons/${LESSON.id}` : '');
  const bg = await modal('New file', `<p>Path inside your home folder:</p><input id="nf" style="width:100%" value="${esc(base ? base + '/' : '')}">`,
    [['Cancel', false], ['Create', undefined, 'primary']]);
  if (!bg) return;
  const p = (bg._vals || [])[0];
  if (!p) return;
  try { await api('/api/file/new', {method: 'POST', body: {path: p, dir: p.endsWith('/')}}); await loadTree(); if (!p.endsWith('/')) openFile(p, true); }
  catch (e) { toast(e.message); }
};
$('tDel').onclick = async () => {
  if (!treeSel) return toast('Select a file first');
  const ok = await modal('Delete?', `<p><code>${esc(treeSel)}</code> will be deleted. (Reset brings NAVERA files back.)</p>`, [['Cancel', false], ['Delete', true, 'danger']]);
  if (!ok) return;
  try { await api('/api/file/delete', {method: 'POST', body: {path: treeSel}}); Editor.closeUnder(treeSel); treeSel = null; await loadTree(); }
  catch (e) { toast(e.message); }
};

/* ------------------------------------------------------------------ editor (Monaco) */
const Editor = {
  ed: null, files: {}, current: null, ready: null,
  init() {
    if (this.ready) return this.ready;
    this.ready = new Promise((resolve) => {
      require.config({paths: {vs: '/static/vendor/monaco/min/vs'}});
      require(['vs/editor/editor.main'], () => {
        monaco.editor.defineTheme('expedition', {base: 'vs-dark', inherit: true,
          rules: [{token: 'comment', foreground: '6c7590', fontStyle: 'italic'}, {token: 'keyword', foreground: 'f2b763'},
            {token: 'string', foreground: 'e6d3a3'}, {token: 'number', foreground: '7fd1c7'}, {token: 'type', foreground: 'b7a6e0'}],
          colors: {'editor.background': '#12172b', 'editor.lineHighlightBackground': '#1b2240', 'editorLineNumber.foreground': '#454d73',
            'editorLineNumber.activeForeground': '#ffd08a', 'editorCursor.foreground': '#e0a64a', 'editor.selectionBackground': '#e0a64a40',
            'editorIndentGuide.background1': '#232a4a', 'editorWidget.background': '#1b2240'}});
        this.ed = monaco.editor.create($('monaco'), {theme: 'expedition', automaticLayout: false, fontSize: 14,
          minimap: {enabled: false}, scrollBeyondLastLine: false, tabSize: 4, renderWhitespace: 'selection'});
        this.ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => this.save());
        resolve();
      });
    });
    return this.ready;
  },
  layout() { if (this.ed) this.ed.layout(); },
  async open(path, focus) {
    const isImg = /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(path);
    if (!this.files[path]) {
      if (isImg) this.files[path] = {img: true};
      else {
        let d;
        try { d = await api('/api/file?path=' + encodeURIComponent(path)); } catch (e) { if (focus) toast(e.message); return; }
        if (d.binary) { toast(`${path}: ${d.reason}`); return; }
        await this.init();
        const model = monaco.editor.createModel(d.content, undefined, monaco.Uri.file('/' + path));
        const f = {model, saved: model.getAlternativeVersionId()};
        model.onDidChangeContent(() => { this.renderTabs(); Tip.once('first-edit'); });
        this.files[path] = f;
      }
    }
    if (focus || !this.current) this.show(path);
    else this.renderTabs();
  },
  show(path) {
    this.current = path;
    const f = this.files[path];
    $('edEmpty').style.display = 'none';
    if (f.img) {
      $('monaco').style.display = 'none'; $('imgview').style.display = 'flex';
      $('imgel').src = withAs('/api/file?raw=1&path=' + encodeURIComponent(path)) + '&t=' + Date.now();
    } else {
      $('imgview').style.display = 'none'; $('monaco').style.display = '';
      this.ed.setModel(f.model); this.layout(); this.ed.focus();
    }
    this.renderTabs();
  },
  dirty(p) { const f = this.files[p]; return f && !f.img && f.model.getAlternativeVersionId() !== f.saved; },
  renderTabs() {
    const box = $('ftabs'); box.innerHTML = '';
    for (const p of Object.keys(this.files)) {
      const t = document.createElement('div');
      t.className = 'ftab' + (p === this.current ? ' on' : '') + (this.dirty(p) ? ' dirty' : '');
      t.title = p;
      t.innerHTML = `<span class="name">${esc(p.split('/').pop())}</span><span class="x">✕</span>`;
      t.onclick = (e) => { if (e.target.classList.contains('x')) this.close(p); else this.show(p); };
      box.appendChild(t);
    }
  },
  async save(p) {
    p = p || this.current;
    const f = this.files[p];
    if (!f || f.img) return;
    const v = f.model.getAlternativeVersionId();
    try { await api('/api/file', {method: 'PUT', body: {path: p, content: f.model.getValue()}}); f.saved = v; this.renderTabs(); }
    catch (e) { toast('Not saved: ' + e.message); }
  },
  async saveAll() { for (const p of Object.keys(this.files)) if (this.dirty(p)) await this.save(p); },
  async close(p) {
    if (this.dirty(p)) {
      const ok = await modal('Unsaved changes', `<p>${esc(p)} has changes that are not saved.</p>`, [['Cancel', 0], ['Discard', 1], ['Save', 2, 'primary']]);
      if (!ok) return;
      if (ok === 2) await this.save(p);
    }
    const f = this.files[p]; if (f && f.model) f.model.dispose();
    delete this.files[p];
    if (this.current === p) {
      const rest = Object.keys(this.files);
      if (rest.length) this.show(rest[rest.length - 1]);
      else { this.current = null; $('monaco').style.display = 'none'; $('imgview').style.display = 'none'; $('edEmpty').style.display = ''; this.renderTabs(); }
    } else this.renderTabs();
  },
  closeUnder(prefix) {
    for (const p of Object.keys(this.files)) if (p === prefix || p.startsWith(prefix)) {
      const f = this.files[p]; if (f.model) f.model.dispose(); delete this.files[p];
      if (this.current === p) this.current = null;
    }
    if (!this.current) { $('monaco').style.display = 'none'; $('imgview').style.display = 'none'; $('edEmpty').style.display = ''; }
    this.renderTabs();
  },
  async reloadIfClean(p) { /* after a run, files may have changed on disk */ },
};
function openFile(p, focus) { return Editor.open(p, focus); }
window.addEventListener('beforeunload', (e) => {
  if (Object.keys(Editor.files).some(p => Editor.dirty(p))) { e.preventDefault(); e.returnValue = ''; }
});

/* ------------------------------------------------------------------ terminals */
const Terms = {
  list: [], cur: null, n: 0,
  add() {
    const id = ++this.n;
    const el = document.createElement('div'); el.className = 'term'; $('terms').appendChild(el);
    const term = new Terminal({fontSize: 14, lineHeight: 1.2, cursorBlink: true, scrollback: 5000,
      fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, monospace', theme: {background: '#12172b', foreground: '#dfe3f0',
        cursor: '#e0a64a', cursorAccent: '#12172b', selectionBackground: '#e0a64a55', yellow: '#f2b763', brightYellow: '#ffd08a',
        cyan: '#7fd4c9', brightCyan: '#a5e6dd', blue: '#7aa7ff', brightBlue: '#9fc0ff'}});
    const fit = new FitAddon.FitAddon(); term.loadAddon(fit); term.open(el);
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const cwd = LESSON ? `lessons/${LESSON.id}` : '';
    const ws = new WebSocket(withAs(`${proto}://${location.host}/ws/term?cwd=${encodeURIComponent(cwd)}`));
    const t = {id, el, term, fit, ws, ready: false, queue: [], send: (s) => ws.readyState === 1 && ws.send(s)};
    ws.onopen = () => { t.ready = true; this.resize(t); t.queue.splice(0).forEach(f => setTimeout(f, 400)); };
    ws.onmessage = (e) => term.write(e.data);
    ws.onclose = () => { t.ready = false; term.write('\r\n\x1b[90m[disconnected]\x1b[0m\r\n'); };
    term.onData((d) => { if (ws.readyState === 1) ws.send(d); else if (d === '\r') this.restart(t); });
    term.onResize(() => this.resize(t));
    this.list.push(t); this.select(t); this.renderTabs();
    return t;
  },
  restart(t) { this.close(t); this.add(); },
  resize(t) { if (t.ws.readyState === 1) t.ws.send(`\x00resize:${t.term.rows}x${t.term.cols}`); },
  select(t) {
    this.cur = t;
    this.list.forEach(x => x.el.classList.toggle('on', x === t));
    setTimeout(() => { try { t.fit.fit(); } catch (e) {} t.term.focus(); }, 30);
    this.renderTabs();
  },
  active() { return this.cur; },
  close(t) {
    try { t.ws.close(); } catch (e) {}
    t.term.dispose(); t.el.remove();
    this.list = this.list.filter(x => x !== t);
    if (this.cur === t) this.cur = this.list[this.list.length - 1] || null;
    if (this.cur) this.select(this.cur);
    this.renderTabs();
  },
  closeAll() { [...this.list].forEach(t => this.close(t)); },
  fitAll() { this.list.forEach(t => { if (t.el.classList.contains('on')) try { t.fit.fit(); } catch (e) {} }); },
  renderTabs() {
    const box = $('termtabs'); box.innerHTML = '';
    for (const t of this.list) {
      const b = document.createElement('div'); b.className = 'ttab' + (t === this.cur ? ' on' : '');
      b.innerHTML = `Terminal ${t.id} <span style="opacity:.6">✕</span>`;
      b.onclick = (e) => { if (e.target.tagName === 'SPAN') this.close(t); else this.select(t); };
      box.appendChild(b);
    }
    const plus = document.createElement('div'); plus.className = 'ttab'; plus.textContent = '＋ new'; plus.title = 'Open another terminal';
    plus.onclick = () => this.add(); box.appendChild(plus);
  },
};

/* ------------------------------------------------------------------ hardware booking */
let BOOK = {};
async function pollBookings() {
  try { BOOK = await api('/api/bookings'); } catch (e) { return; }
  const mine = Object.values(BOOK).some(b => b.holder === (AS || ME.name));
  $('bookDot').className = 'dot' + (mine ? ' mine' : '');
  renderBookMenu();
}
function renderBookMenu() {
  const me = AS || ME.name;
  let h = `<div class="hint">These are shared by the whole class: take one only while you use it, then release it.
    After taking one, open a <b>new terminal</b> to use it.</div>`;
  for (const [k, b] of Object.entries(BOOK)) {
    const state = !b.holder ? '<span class="badge">free</span>' : b.holder === me ? `<span class="badge passed">yours since ${b.since}</span>` :
      `<span class="badge started">${esc(b.holder)}</span>`;
    const btn = !b.holder ? `<button data-r="${k}" data-a="take">Take</button>` : b.holder === me || ME.role === 'teacher' ?
      `<button data-r="${k}" data-a="release">Release</button>` : '';
    h += `<div class="item"><span>${esc(b.title)}<br>${state}</span>${btn}</div>`;
  }
  $('bookMenu').innerHTML = h;
  $('bookMenu').querySelectorAll('button').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    try {
      await api('/api/book', {method: 'POST', body: {resource: b.dataset.r, action: b.dataset.a}});
      toast(b.dataset.a === 'take' ? 'Booked. Open a new terminal to use it.' : 'Released — its terminals were closed.');
    } catch (err) { toast(err.message, 5000); }
    pollBookings();
  });
}
$('bookBtn').onclick = (e) => { e.stopPropagation(); $('userMenu').classList.remove('open'); $('bookMenu').classList.toggle('open'); pollBookings(); };
$('userBtn').onclick = (e) => { e.stopPropagation(); $('bookMenu').classList.remove('open'); $('userMenu').classList.toggle('open'); };
document.addEventListener('click', (e) => {
  if (!e.target.closest('.menu')) { $('bookMenu').classList.remove('open'); $('userMenu').classList.remove('open'); }
});
$('logo').onclick = () => { location.hash = ''; };
$('mHome').onclick = () => { location.hash = ''; };
$('mTeacher').onclick = () => { location.href = '/teacher'; };
$('mLogout').onclick = async () => { await api('/api/logout', {method: 'POST', body: {}}); location.href = '/'; };
$('mResetNavera').onclick = async () => {
  const ok = await modal('Reset your NAVERA copy?', `<p>Your <code>~/navera</code> folder goes back to the original NAVERA.
    Everything you changed there is saved in a backup first. Your lesson files are not touched. Open terminals will close.</p>`,
    [['Cancel', false], ['Reset NAVERA', true, 'primary']]);
  if (!ok) return;
  toast('Resetting… (about 10 s)');
  try {
    const r = await api('/api/reset_navera', {method: 'POST', body: {}});
    Editor.closeUnder('navera/'); Terms.closeAll(); await loadTree();
    toast('NAVERA is back to the original. Backup: ' + (r.backup || 'none'), 5000);
  } catch (e) { toast(e.message); }
};
const Intro = {
  key: () => `academy:${ME.name}:intro`,
  seen() { try { return localStorage.getItem(this.key()) === '1'; } catch (e) { return false; } },
  show(then) {
    try { localStorage.setItem(this.key(), '1'); } catch (e) {}
    const bg = document.createElement('div'); bg.className = 'intro-bg';
    bg.innerHTML = `<div class="intro-box"><video src="/static/media/navera-intro.webm" controls autoplay muted playsinline></video>
      <div class="intro-bar"><b>Welcome to NAVERA Academy</b><span>80 seconds · no sound</span>
      <a href="/static/media/navera-intro.webm" download>Download</a><button class="go">Start the expedition →</button></div></div>`;
    const done = () => { bg.remove(); if (then) then(); };
    bg.querySelector('button').onclick = done;
    bg.querySelector('video').onended = () => { bg.querySelector('button').focus(); };
    bg.addEventListener('click', (e) => { if (e.target === bg) done(); });
    document.body.appendChild(bg);
  },
  maybe(then) { if (this.seen() || AS) { if (then) then(); } else this.show(then); },
};
$('mIntro').onclick = () => { $('userMenu').classList.remove('open'); Intro.show(); };
$('mTour').onclick = () => { $('userMenu').classList.remove('open'); Tour.reset(); Tour.start($('work').style.display === 'none' ? 'home' : 'mission'); };
$('mPw').onclick = async () => {
  const bg = await modal('Change password', `<p>Current password</p><input type="password" style="width:100%"><p>New password (6+ characters)</p><input type="password" style="width:100%">`,
    [['Cancel', false], ['Change', undefined, 'primary']]);
  if (!bg || !bg._vals) return;
  try { await api('/api/password', {method: 'POST', body: {old: bg._vals[0], new: bg._vals[1]}}); toast('Password changed'); }
  catch (e) { toast(e.message); }
};

init();
