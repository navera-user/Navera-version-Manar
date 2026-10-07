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
  const m = location.hash.match(/^#lesson\/(.+)$/);
  if (m) openLesson(decodeURIComponent(m[1])); else showHome();
}

/* ------------------------------------------------------------------ home */
function moduleOf(id) {
  const i = MODULES.findIndex(m => (m.lessons || []).includes(id));
  return i < 0 ? {color: '#3b8ff0', icon: '🐦', leg: '', idx: 0} : {...MODULES[i], idx: i};
}
const XP_PER_MISSION = 100;
const RANKS = [  // [missions passed, name, icon]
  [0, 'Fledgling', '🥚'], [3, 'Glider', '🪁'], [8, 'Wayfinder', '🧭'],
  [15, 'Navigator', '🗺️'], [22, 'Falcon', '🦅'], [30, 'Migration Master', '🏆']];
function rankFor(passed) {
  let i = 0;
  RANKS.forEach((r, k) => { if (passed >= r[0]) i = k; });
  const next = RANKS[i + 1];
  return {name: RANKS[i][1], icon: RANKS[i][2], from: RANKS[i][0], next: next ? next[0] : null, nextName: next ? next[1] : null};
}
function expeditionSVG(lessons) {
  // An expedition map: sea, dunes, the Hajar mountains and Navi's flight path with one waypoint per mission.
  const W = 1000, H = 290, x0 = 80, x1 = 920, n = lessons.length;
  const pt = (t) => [x0 + (x1 - x0) * t, 150 + 50 * Math.sin(t * Math.PI * 4.2 + .3)];
  let d = '';
  for (let k = 0; k <= 200; k++) { const [x, y] = pt(k / 200); d += (k ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); }
  const next = lessons.findIndex(l => l.progress.status !== 'passed');
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Expedition map">
    <defs>
      <linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd8b0"/><stop offset=".55" stop-color="#fff0dc"/><stop offset="1" stop-color="#fff7ec"/></linearGradient>
      <linearGradient id="sea" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#1fa5a0"/><stop offset="1" stop-color="#7fd4c9"/></linearGradient>
    </defs>
    <rect width="${W}" height="${H}" fill="url(#dusk)"/>
    <circle cx="840" cy="70" r="34" fill="#ffb347" opacity=".9"/><circle cx="840" cy="70" r="52" fill="#ffb347" opacity=".18"/>
    <path d="M300 205 L360 120 L395 150 L450 95 L505 160 L560 110 L620 175 L680 135 L740 205 Z" fill="#c9a6c9" opacity=".55"/>
    <path d="M330 215 L390 150 L430 178 L480 128 L540 190 L600 150 L660 210 Z" fill="#a983b0" opacity=".55"/>
    <text x="470" y="88" font-size="12" fill="#8a6a93" text-anchor="middle">Hajar mountains</text>
    <path d="M0 236 Q90 208 190 232 T420 246 L430 290 L0 290 Z" fill="url(#sea)" opacity=".9"/>
    <text x="70" y="270" font-size="12" fill="#ffffff">Gulf of Oman</text>
    <path d="M330 290 Q360 252 470 232 Q560 224 620 246 T820 238 T1000 244 L1000 290 Z" fill="#f1c98f"/>
    <path d="M520 262 Q620 236 720 262 T920 260 L1000 266 L1000 290 L520 290 Z" fill="#e8b46e"/>
    <text x="790" y="280" font-size="12" fill="#8a5a1f">Wahiba Sands</text>
    <g fill="#fff" opacity=".85"><ellipse cx="200" cy="58" rx="44" ry="12"/><ellipse cx="216" cy="49" rx="20" ry="13"/>
      <ellipse cx="620" cy="44" rx="40" ry="11"/><ellipse cx="634" cy="36" rx="18" ry="12"/></g>
    <path d="${d}" fill="none" stroke="#14213d" stroke-opacity=".35" stroke-width="3" stroke-dasharray="1 10" stroke-linecap="round"/>
    <text x="${x0 - 24}" y="${pt(0)[1] + 4}" text-anchor="end" font-size="14" fill="#65748b">🪺 start</text>
    <text x="${x1 + 26}" y="${pt(1)[1] + 4}" font-size="14" fill="#65748b">🏁</text>`;
  lessons.forEach((l, i) => {
    const [x, y] = pt(n > 1 ? i / (n - 1) : 0);
    const m = moduleOf(l.id), done = l.progress.status === 'passed', started = l.progress.status === 'started';
    const title = `Mission ${l.number} · ${l.title}${done ? ' — complete' : started ? ' — in progress' : ''}`;
    if (done) {
      g += `<g class="wp" data-id="${esc(l.id)}"><title>${esc(title)}</title><g class="pin">
        <line x1="${x}" y1="${y}" x2="${x}" y2="${y - 26}" stroke="#14213d" stroke-width="2.5"/>
        <path d="M${x} ${y - 26} L${x + 17} ${y - 20} L${x} ${y - 14} Z" fill="${m.color}"/>
        <circle cx="${x}" cy="${y}" r="6" fill="${m.color}" stroke="#fff" stroke-width="2"/></g></g>`;
    } else {
      g += `<g class="wp" data-id="${esc(l.id)}"><title>${esc(title)}</title><g class="pin">
        <circle cx="${x}" cy="${y}" r="12" fill="#fff" stroke="${m.color}" stroke-width="3" ${started ? 'stroke-dasharray="4 3"' : ''}/>
        <text x="${x}" y="${y + 4.5}" text-anchor="middle" font-size="11.5" fill="${m.color}">${+l.number}</text></g></g>`;
    }
  });
  if (next >= 0) {
    const [x, y] = pt(n > 1 ? next / (n - 1) : 0);
    g += `<image href="/static/img/navi-pilot.svg" x="${x - 36}" y="${y - 78}" width="70" height="56"><animateTransform attributeName="transform" type="translate" values="0 0; 0 -6; 0 0" dur="1.8s" repeatCount="indefinite"/></image>`;
  } else {
    g += `<image href="/static/img/navi-pilot.svg" x="${x1 - 10}" y="${pt(1)[1] - 80}" width="76" height="60"/>`;
  }
  return g + '</svg>';
}
function achievements(lessons) {
  const st = Object.fromEntries(lessons.map(l => [l.id, l.progress.status]));
  const passed = lessons.filter(l => l.progress.status === 'passed').length;
  const list = MODULES.map(m => ({icon: m.icon || '🏅', name: m.leg ? m.leg.replace(/^Leg \d+ · /, '') : m.title,
    hint: (m.leg || '').split(' · ')[0] || 'Leg', color: m.color, on: (m.lessons || []).length > 0 && (m.lessons || []).every(id => st[id] === 'passed')}));
  list.unshift({icon: '🛫', name: 'First flight', hint: 'pass 1 mission', color: '#ff7a1a', on: passed >= 1});
  list.push({icon: '🌓', name: 'Halfway there', hint: '15 missions', color: '#1fa5a0', on: passed >= 15});
  list.push({icon: '🕵️', name: 'Spoof hunter', hint: 'mission 27', color: '#8b5cf6', on: st['27-spoofing'] === 'passed'});
  list.push({icon: '🌌', name: 'Star reader', hint: 'mission 24', color: '#1f3a68', on: st['24-night-and-stars'] === 'passed'});
  return list.map(b => `<div class="bdg ${b.on ? 'on' : ''}" style="--bc:${b.color}"><div class="m">${b.icon}</div><b>${esc(b.name)}</b><span>${b.on ? 'unlocked' : esc(b.hint)}</span></div>`).join('');
}
async function showHome() {
  try { const c = await api('/api/courses'); COURSES = c.lessons; MODULES = c.modules; } catch (e) {}
  $('work').style.display = 'none'; $('home').style.display = '';
  $('crumb').innerHTML = '';
  const passed = COURSES.filter(l => l.progress.status === 'passed').length;
  const next = COURSES.find(l => l.progress.status !== 'passed');
  const first = ME.display.split(' ')[0];
  const r = rankFor(passed), xp = passed * XP_PER_MISSION;
  const pct = r.next === null ? 100 : Math.round(100 * (passed - r.from) / (r.next - r.from));
  const brief = passed === 0
    ? `Every year a swallow like <b>Navi</b> flies thousands of kilometres with no GPS — landmarks, the sun, the stars and an inner compass,
       each checked against the others. NAVERA does the same for drones and vehicles. ${COURSES.length} missions stand between you and
       the engineering behind it. Your first mission is ready.`
    : passed === COURSES.length
    ? `Expedition complete. ${COURSES.length} missions, ${xp} XP. You have rebuilt the ideas behind NAVERA one by one — time to show your final project.`
    : `${passed} of ${COURSES.length} missions complete. Next on the map: <b>${esc(next.title)}</b>${/[.?!]$/.test(next.title) ? '' : '.'}
       Your NAVERA copy is your own aircraft — modify it freely; Reset brings back the factory version.`;
  let h = `<div class="hq"><div class="row">
      <img class="navi" src="/static/img/navi-pilot.svg" alt="Navi the swallow, pilot">
      <div class="brief"><div class="over">Expedition HQ · mission briefing</div><h1>Welcome aboard, ${esc(first)}</h1><p>${brief}</p></div>
      <div class="stats"><div class="rank"><div class="medal">${r.icon}</div><div><b>${esc(r.name)}</b><span>rank · ${xp} XP</span></div></div>
        <div class="xpbar"><i style="width:${pct}%"></i></div>
        <div class="xptext"><span>${passed}/${COURSES.length} missions</span><span>${r.next === null ? 'max rank' : `${r.next - passed} to ${esc(r.nextName)}`}</span></div>
        ${next ? `<button class="go" id="goNext">${passed ? 'Next mission ➜' : 'Start mission 1 ➜'}</button>` : ''}</div>
    </div></div>
    <div class="expmap"><div class="head"><h2>🗺️ Expedition map</h2><span>Flags mark completed missions · click any waypoint</span></div>${expeditionSVG(COURSES)}</div>
    <div class="ach"><div class="head"><h2>🏅 Achievements</h2><span>Complete a whole leg to earn its badge</span></div><div class="badges">${achievements(COURSES)}</div></div>`;
  const mods = MODULES.length ? MODULES : [{title: 'Missions', lessons: COURSES.map(l => l.id)}];
  const byId = Object.fromEntries(COURSES.map(l => [l.id, l]));
  for (const m of mods) {
    const color = m.color || '#ff7a1a';
    h += `<div class="module" style="--mcolor:${color}"><div class="mhead"><div class="micon" style="background:${color}22">${m.icon || '🐦'}</div>
      <div><div class="mtag" style="color:${color}">${esc(m.leg || '')}</div><h2>${esc(m.title)}</h2>${m.desc ? `<p class="mdesc">${esc(m.desc)}</p>` : ''}</div></div><div class="cards">`;
    for (const id of (m.lessons || [])) {
      const l = byId[id]; if (!l) continue;
      const st = l.progress.status;
      const badge = st === 'passed' ? '<span class="badge passed">✔ complete</span>' :
        st === 'started' ? '<span class="badge started">in progress</span>' : `<span class="xp">+${XP_PER_MISSION} XP</span>`;
      const res = (l.resources || []).map(r => `<span class="badge res">${r === 'sim' ? '🛩️ simulator' : r === 'camera' ? '📷 camera' : '🔌 sensors'}</span>`).join(' ');
      h += `<div class="card" data-id="${esc(id)}"><div class="num"><span class="mission">Mission ${esc(l.number)} · ${esc(l.duration || '')}</span>${badge}</div>
        <div class="title">${esc(l.title)}</div><div class="sum">${esc(l.summary || '')}</div><div>${res}</div></div>`;
    }
    h += '</div></div>';
  }
  $('home').innerHTML = h;
  $('home').querySelectorAll('.card, .wp').forEach(c => c.onclick = () => { location.hash = 'lesson/' + c.dataset.id; });
  if ($('goNext')) $('goNext').onclick = () => { location.hash = 'lesson/' + next.id; };
}

/* ------------------------------------------------------------------ lesson */
async function openLesson(id) {
  let l;
  try { l = await api('/api/lesson/' + encodeURIComponent(id)); } catch (e) { toast(e.message); location.hash = ''; return; }
  const switched = !LESSON || LESSON.id !== l.id;
  LESSON = l;
  $('home').style.display = 'none'; $('work').style.display = '';
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
  if (l.resources && l.resources.includes('sim')) {} // the sim tab is always there
}
function setStatus(p) {
  const s = $('lstatus');
  if (p && p.status === 'passed') { s.className = 'badge passed'; s.textContent = '✔ passed'; }
  else if (p && p.status === 'started') { s.className = 'badge started'; s.textContent = `tried ${p.attempts}×` + (p.total ? ` · best ${p.best}/${p.total}` : ''); }
  else { s.className = 'badge'; s.textContent = 'not checked yet'; }
}
document.querySelectorAll('.notebook .tab').forEach(t => t.onclick = () => showDoc(t.dataset.doc));
function showDoc(which) {
  DOC = which;
  document.querySelectorAll('.notebook .tab').forEach(t => t.classList.toggle('on', t.dataset.doc === which));
  renderMarkdown($('doc'), which === 'lab' ? LESSON.lab : LESSON.course);
  $('doc').scrollTop = 0;
}

marked.setOptions({gfm: true, breaks: false});
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
    const labels = {note: 'Note', tip: 'Tip', warning: 'Careful', task: 'Task', question: 'Question', bird: "🐦 Bird's-eye view"};
    first.innerHTML = m[2];
    if (!first.innerHTML.trim()) first.remove();
    const d = document.createElement('div'); d.className = 'callout ' + kind;
    d.innerHTML = `<div class="ct">${labels[kind]}</div>` + bq.innerHTML;
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
    $('rhead').textContent = r.passed ? `🎉 Well done, all checks pass${sc}` : `Not yet${sc} — read the hints below and try again`;
    $('rout').textContent = r.output.trim() || '(no output)';
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
  const up = r1.name !== r0.name ? `<span class="rankup">${r1.icon} Rank up: ${esc(r1.name)}!</span>` : '';
  const lines = ['Mission complete!', 'Clean landing!', 'Waypoint reached!', 'Navigation confirmed!'];
  p.innerHTML = `<div class="cheer"><img src="/static/img/navi-pilot.svg" alt=""><div><b>${lines[Math.floor(Math.random() * lines.length)]}</b><span>+${XP_PER_MISSION} XP · ${after}/${COURSES.length} missions</span>${up}</div></div>`;
  document.body.appendChild(p);
  setTimeout(() => p.remove(), up ? 5200 : 4200);
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
  if (p === 'terminal') { if (!Terms.list.length) Terms.add(); else Terms.fitAll(); }
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
        this.ed = monaco.editor.create($('monaco'), {theme: 'vs-dark', automaticLayout: false, fontSize: 14,
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
        model.onDidChangeContent(() => this.renderTabs());
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
      fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, monospace', theme: {background: '#1e1e1e'}});
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
$('mPw').onclick = async () => {
  const bg = await modal('Change password', `<p>Current password</p><input type="password" style="width:100%"><p>New password (6+ characters)</p><input type="password" style="width:100%">`,
    [['Cancel', false], ['Change', undefined, 'primary']]);
  if (!bg || !bg._vals) return;
  try { await api('/api/password', {method: 'POST', body: {old: bg._vals[0], new: bg._vals[1]}}); toast('Password changed'); }
  catch (e) { toast(e.message); }
};

init();
