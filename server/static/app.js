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
function routeSVG(lessons) {
  // Navi's migration: one stop per lesson along a wavy flight path.
  const W = 1000, H = 250, x0 = 95, x1 = 905, n = lessons.length;
  const pt = (t) => [x0 + (x1 - x0) * t, 128 + 52 * Math.sin(t * Math.PI * 4.4)];
  let d = '';
  for (let k = 0; k <= 200; k++) { const [x, y] = pt(k / 200); d += (k ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); }
  const next = lessons.findIndex(l => l.progress.status !== 'passed');
  let g = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Navi's migration route">
    <defs><linearGradient id="skyg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#dff3ff"/><stop offset="1" stop-color="#f6fcff"/></linearGradient></defs>
    <rect x="0" y="0" width="${W}" height="${H}" rx="22" fill="url(#skyg)"/>
    <circle cx="955" cy="40" r="26" fill="#ffd25e"/><circle cx="955" cy="40" r="36" fill="#ffd25e" opacity=".25"/>
    <g fill="#fff" opacity=".9"><ellipse cx="190" cy="40" rx="46" ry="13"/><ellipse cx="208" cy="31" rx="22" ry="15"/>
      <ellipse cx="610" cy="222" rx="54" ry="13"/><ellipse cx="630" cy="212" rx="24" ry="15"/></g>
    <path d="${d}" fill="none" stroke="#9fc9ee" stroke-width="5" stroke-dasharray="2 12" stroke-linecap="round"/>
    <text x="${x0 - 22}" y="${pt(0)[1] + 5}" text-anchor="end" font-size="15" fill="#5f7187">🪺 nest</text>
    <text x="${x1 + 22}" y="${pt(1)[1] + 5}" font-size="15" fill="#5f7187">🌍 Africa!</text>`;
  lessons.forEach((l, i) => {
    const [x, y] = pt(n > 1 ? i / (n - 1) : 0);
    const m = moduleOf(l.id), done = l.progress.status === 'passed', started = l.progress.status === 'started';
    const fill = done ? m.color : '#fff';
    g += `<g class="stop" data-id="${esc(l.id)}"><title>Lesson ${esc(l.number)} · ${esc(l.title)}${done ? ' — passed' : ''}</title>
      <circle class="ring" cx="${x}" cy="${y}" r="13" fill="${fill}" stroke="${m.color}" stroke-width="3.5" ${started ? 'stroke-dasharray="5 3"' : ''}/>
      <text x="${x}" y="${y + 5}" text-anchor="middle" font-size="${done ? 14 : 12}" fill="${done ? '#fff' : m.color}">${done ? '✓' : (+l.number)}</text></g>`;
  });
  if (next >= 0) {
    const [x, y] = pt(n > 1 ? next / (n - 1) : 0);
    g += `<image href="/static/img/navi.svg" x="${x - 34}" y="${y - 70}" width="64" height="52"><animateTransform attributeName="transform" type="translate" values="0 0; 0 -6; 0 0" dur="1.6s" repeatCount="indefinite"/></image>`;
  } else {
    g += `<image href="/static/img/navi.svg" x="${x1 - 30}" y="${pt(1)[1] - 72}" width="70" height="56"/>`;
  }
  return g + '</svg>';
}
async function showHome() {
  try { const c = await api('/api/courses'); COURSES = c.lessons; MODULES = c.modules; } catch (e) {}
  $('work').style.display = 'none'; $('home').style.display = '';
  $('crumb').innerHTML = '';
  const passed = COURSES.filter(l => l.progress.status === 'passed').length;
  const next = COURSES.find(l => l.progress.status !== 'passed');
  const first = ME.display.split(' ')[0];
  const line = passed === 0 ? `I'm <b>Navi</b>, a little swallow. Every year I fly from Europe to Africa without any GPS — I use my eyes,
      the sun, the stars and my inner compass. NAVERA was born from that idea: a vehicle that finds its way like a bird.
      Fly with me through ${COURSES.length} lessons and you will build it yourself!`
    : passed === COURSES.length ? `We made it to Africa! 🎉 You finished all ${COURSES.length} lessons. You now know how NAVERA finds its way like a bird.`
    : `Great flying! ${passed} of ${COURSES.length} stops done. Next stop: <b>${esc(next.title)}</b>${/[.?!]$/.test(next.title) ? '' : '.'} Your NAVERA copy is yours — break it, fix it, and press Reset whenever you want.`;
  let h = `<div class="hero"><div class="cloud c1"></div><div class="cloud c2"></div>
    <img class="navi" src="/static/img/navi.svg" alt="Navi the swallow">
    <div class="say"><h1>Hi ${esc(first)}! 👋</h1><p>${line}</p></div>
    <div class="score"><b>${passed}/${COURSES.length}</b><span>stops reached</span>${next ? `<div style="margin-top:8px"><button class="go" id="goNext">Fly on ➜</button></div>` : ''}</div></div>
    <div class="route"><h2>🗺️ Navi's migration route</h2><p>Each stop is a lesson. Pass its lab to fill it in — click any stop to fly there.</p>${routeSVG(COURSES)}</div>`;
  const mods = MODULES.length ? MODULES : [{title: 'Lessons', lessons: COURSES.map(l => l.id)}];
  const byId = Object.fromEntries(COURSES.map(l => [l.id, l]));
  for (const m of mods) {
    const color = m.color || '#3b8ff0';
    h += `<div class="module" style="--mcolor:${color}"><div class="mhead"><div class="micon" style="background:${color}22">${m.icon || '🐦'}</div>
      <div><div class="mtag" style="color:${color}">${esc(m.leg || '')}</div><h2>${esc(m.title)}</h2>${m.desc ? `<p class="mdesc">${esc(m.desc)}</p>` : ''}</div></div><div class="cards">`;
    for (const id of (m.lessons || [])) {
      const l = byId[id]; if (!l) continue;
      const st = l.progress.status;
      const badge = st === 'passed' ? '<span class="badge passed">✔ passed</span>' :
        st === 'started' ? '<span class="badge started">in progress</span>' : '';
      const res = (l.resources || []).map(r => `<span class="badge res">${r === 'sim' ? '🛩️ simulator' : r === 'camera' ? '📷 camera' : '🔌 sensors'}</span>`).join(' ');
      h += `<div class="card" data-id="${esc(id)}"><div class="num"><span><span class="bubble">${esc(+l.number)}</span>${esc(l.duration || '')}</span>${badge}</div>
        <div class="title">${esc(l.title)}</div><div class="sum">${esc(l.summary || '')}</div><div>${res}</div></div>`;
    }
    h += '</div></div>';
  }
  $('home').innerHTML = h;
  $('home').querySelectorAll('.card, .stop').forEach(c => c.onclick = () => { location.hash = 'lesson/' + c.dataset.id; });
  if ($('goNext')) $('goNext').onclick = () => { location.hash = 'lesson/' + next.id; };
}

/* ------------------------------------------------------------------ lesson */
async function openLesson(id) {
  let l;
  try { l = await api('/api/lesson/' + encodeURIComponent(id)); } catch (e) { toast(e.message); location.hash = ''; return; }
  const switched = !LESSON || LESSON.id !== l.id;
  LESSON = l;
  $('home').style.display = 'none'; $('work').style.display = '';
  $('crumb').innerHTML = `Lesson ${esc(l.number)} · <b>${esc(l.title)}</b>`;
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
    const labels = {note: 'ℹ️ Note', tip: '💡 Tip', warning: '⚠️ Careful', task: '🎯 Your turn', question: '❓ Think', bird: "🐦 Bird's-eye view"};
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
  const b = $('checkBtn'); b.disabled = true; b.textContent = '🐦 Navi is checking…';
  try {
    const r = await api(`/api/lesson/${LESSON.id}/check`, {method: 'POST', body: {}});
    $('result').className = 'result show ' + (r.passed ? 'ok' : 'bad');
    const sc = r.score ? ` — ${r.score.passed}/${r.score.total}` : '';
    $('rhead').textContent = r.passed ? `🎉 Well done, all checks pass${sc}` : `Not yet${sc} — read Navi's hints below and try again`;
    $('rout').textContent = r.output.trim() || '(no output)';
    if (r.passed) celebrate();
    const l = await api('/api/lesson/' + LESSON.id); LESSON.progress = l.progress; setStatus(l.progress);
  } catch (e) { toast(e.message); }
  b.disabled = false; b.textContent = '✔ Check my work';
};
function celebrate() {
  const p = document.createElement('div'); p.className = 'party';
  const icons = ['🪶', '🪶', '🪶', '⭐', '✨', '🪶'];
  for (let i = 0; i < 34; i++) {
    const f = document.createElement('div'); f.className = 'feather';
    f.textContent = icons[i % icons.length];
    f.style.left = (Math.random() * 100) + 'vw';
    f.style.animationDuration = (2.2 + Math.random() * 2) + 's';
    f.style.animationDelay = (Math.random() * .8) + 's';
    p.appendChild(f);
  }
  const lines = ['Great flying!', 'Perfect landing!', 'You found the way!', 'Navi is proud of you!'];
  p.insertAdjacentHTML('beforeend', `<div class="cheer"><img src="/static/img/navi.svg" alt=""><div><b>${lines[Math.floor(Math.random() * lines.length)]}</b><span>Lab passed — one more stop on the route.</span></div></div>`);
  document.body.appendChild(p);
  setTimeout(() => p.remove(), 4200);
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
