// NAVERA Sim Lite — the page: map, controls, and the bridge to the simulation thread (worker.js).
const $ = (id) => document.getElementById(id);
const PLACES = { 'Sousse': [35.8256, 10.6360], 'Port El Kantaoui': [35.8920, 10.5980], 'Hammam Sousse': [35.8606, 10.5944],
  'Monastir': [35.7643, 10.8113], 'Monastir harbour': [35.7778, 10.8317], 'Monastir airport': [35.7581, 10.7547], 'Skanes': [35.7560, 10.7680] };
const VEH = { drone: [15, 30], plane: [40, 100], boat: [8, 20], robot: [4, 10] };
const LESSON_ID = new URLSearchParams(location.search).get('lesson') || '';
const COLUMNS = ['t_s', 'phase', 'gps_mode', 'navera_state', 'navera_source', 'navera_lat', 'navera_lon', 'navera_err_m',
  'truth_lat', 'truth_lon', 'truth_alt_m', 'truth_speed_mps', 'ap_mode', 'ap_err_m', 'reason', 'camera'];
const SCEN_ROUTE = { start: [35.8256, 10.6385], dest: [35.8050, 10.6010] };   // sim_ctl.py's route (~4 km)
const S = { rows: [], evlines: [], runName: null, scenario: null, vehicle: 'drone', start: [35.8256, 10.6360], dest: [35.7643, 10.8113], profile: 'measured', light: 'day',
  rate: 4, src: 'mine', running: false, paused: false, busy: false, picking: null, files: null };

// ---------------------------------------------------------------- the simulation thread
const worker = new Worker('/static/simlite/worker.js');
let seq = 0; const waiting = {};
worker.onmessage = (ev) => { const w = waiting[ev.data.id]; delete waiting[ev.data.id]; if (w) (ev.data.ok ? w.ok : w.no)(ev.data.data); };
const call = (cmd, args) => new Promise((ok, no) => { const id = ++seq; waiting[id] = { ok, no }; worker.postMessage({ id, cmd, args }); });

// ---------------------------------------------------------------- map
const map = L.map('map', { zoomControl: true, attributionControl: false }).setView([35.80, 10.72], 12);
fetch('/api/simlite/map').then(r => r.json()).then(m => {
  if (!m.available) return;
  L.tileLayer('/api/simlite/tiles/{z}/{x}/{y}.jpg', { maxNativeZoom: Math.min(17, m.max_native_zoom), maxZoom: 19, minZoom: 9 }).addTo(map);
}).catch(() => {});
const legend = L.control({ position: 'topleft' });
legend.onAdd = () => { const d = L.DomUtil.create('div', 'legend'); d.innerHTML =
  '<div><i style="background:#f4f7fa"></i>True path</div><div><i style="background:#ff8f7a"></i>NAVERA — <b style="all:unset;font-weight:700">your code</b></div>' +
  '<div><b style="background:#7fe0e4"></b>GPS fixes</div><div><b style="background:#ffd27a;border-radius:2px"></b>Vision fixes</div>'; return d; };
legend.addTo(map);
const lay = {
  plan: L.polyline([], { color: '#f4f7fa', weight: 2, opacity: .45, dashArray: '3 8' }).addTo(map),
  truth: L.polyline([], { color: '#f4f7fa', weight: 3 }).addTo(map),
  nav: L.polyline([], { color: '#ff8f7a', weight: 2, opacity: .85 }).addTo(map),
  gps: L.layerGroup().addTo(map), vis: L.layerGroup().addTo(map),
};
const startM = L.circleMarker(S.start, { radius: 8, color: '#0b1730', weight: 2, fillColor: '#7fe0e4', fillOpacity: 1 }).addTo(map).bindTooltip('Start', { permanent: true, direction: 'right', className: 'chip' });
const destM = L.marker(S.dest, { icon: L.divIcon({ className: '', html: '<div style="font-size:26px;transform:translate(-4px,-22px)">🚩</div>' }) }).addTo(map).bindTooltip('Destination', { permanent: true, direction: 'right', className: 'chip', offset: [10, -12] });
const vehM = L.marker(S.start, { icon: arrow(0), zIndexOffset: 1000 }).addTo(map);
const navC = L.circleMarker(S.start, { radius: 12, color: '#ff8f7a', weight: 2, fill: false, opacity: 0 }).addTo(map);
const navTip = L.tooltip({ permanent: true, direction: 'right', className: 'chip', offset: [16, 0] });
function arrow(deg) {
  return L.divIcon({ className: '', iconSize: [28, 28], iconAnchor: [14, 14],
    html: `<svg width="28" height="28" viewBox="-14 -14 28 28" style="transform:rotate(${deg}deg)"><path d="M0 -12 L8 10 L0 5 L-8 10 Z" fill="#f4f7fa" stroke="#0b1730" stroke-width="2"/></svg>` });
}
function drawPlan() { lay.plan.setLatLngs([S.start, S.dest]); startM.setLatLng(S.start); destM.setLatLng(S.dest); vehM.setLatLng(S.start); }
map.on('click', (e) => {
  if (!S.picking) return;
  const p = [+e.latlng.lat.toFixed(6), +e.latlng.lng.toFixed(6)];
  S[S.picking] = p; addCustom(S.picking === 'start' ? 'startSel' : 'destSel', p);
  S.picking = null; map.getContainer().style.cursor = ''; drawPlan();
});

// ---------------------------------------------------------------- controls
function fillPlaces(id, sel) {
  $(id).innerHTML = Object.keys(PLACES).map(n => `<option ${n === sel ? 'selected' : ''}>${n}</option>`).join('');
  $(id).onchange = () => { const v = $(id).value; S[id === 'startSel' ? 'start' : 'dest'] = v.startsWith('📍') ? S[id === 'startSel' ? 'start' : 'dest'] : PLACES[v]; drawPlan(); };
}
function addCustom(id, p) {
  const label = `📍 ${p[0].toFixed(4)}, ${p[1].toFixed(4)}`;
  const o = document.createElement('option'); o.textContent = label; o.selected = true; $(id).appendChild(o);
}
fillPlaces('startSel', 'Sousse'); fillPlaces('destSel', 'Monastir');
$('pickStart').onclick = () => { S.picking = 'start'; map.getContainer().style.cursor = 'crosshair'; };
$('pickDest').onclick = () => { S.picking = 'dest'; map.getContainer().style.cursor = 'crosshair'; };
function setVehicle(v) {
  S.vehicle = v; $('speedIn').value = VEH[v][0]; $('maxIn').value = VEH[v][1];
  document.querySelectorAll('#vehSeg button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
}
document.querySelectorAll('#vehSeg button').forEach(b => b.onclick = () => { if (!S.running) setVehicle(b.dataset.v); });
setVehicle('drone');
document.querySelectorAll('#rateSeg button').forEach(b => b.onclick = () => {
  S.rate = +b.dataset.r; document.querySelectorAll('#rateSeg button').forEach(x => x.classList.toggle('on', x === b)); });
function opts(id, key) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
    S[key] = b.dataset.v; document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle('on', x === b)); });
}
opts('profOpts', 'profile'); opts('lightOpts', 'light');
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'p-' + b.dataset.p));
});
document.querySelectorAll('#p-faults .opts').forEach(g => g.querySelectorAll('button').forEach(b => b.onclick = async () => {
  if (!S.running) { toastLog('warn', 'Press ▶ Fly first, then inject faults during the flight.'); return; }
  try { await call('fault', { key: g.dataset.k, value: b.dataset.v }); markFault(g.dataset.k, b.dataset.v); }
  catch (e) { toastLog('bad', e); }
}));
function markFault(k, v) { document.querySelectorAll(`#p-faults .opts[data-k="${k}"] button`).forEach(x => x.classList.toggle('on', x.dataset.v === v)); }
$('toFull').onclick = () => { location.href = '/web/sim/'; };
$('script').addEventListener('keydown', (e) => {
  if (e.key !== 'Tab') return;
  e.preventDefault(); const t = e.target, a = t.selectionStart;
  t.value = t.value.slice(0, a) + '    ' + t.value.slice(t.selectionEnd); t.selectionStart = t.selectionEnd = a + 4;
});

// ---------------------------------------------------------------- the student's code
document.querySelectorAll('#srcSel button').forEach(b => b.onclick = () => {
  S.src = b.dataset.s; document.querySelectorAll('#srcSel button').forEach(x => x.classList.toggle('on', x === b)); loadCode(); });
async function loadCode() {
  $('fileInfo').innerHTML = '📄 navera_estimator/nodes/estimator_node.py — loading…';
  try {
    const r = await fetch('/api/simlite/code?src=' + S.src); if (!r.ok) throw new Error('please sign in again');
    const c = await r.json();
    await call('load', { files: c.files });
    S.files = c;
    const where = c.origin === 'mine' ? 'from your copy' : 'original NAVERA';
    $('fileInfo').innerHTML = `📄 navera_estimator/nodes/estimator_node.py <span class="ok">✓ loaded ${where}</span>` +
      (c.missing.length ? ` <span class="no">missing: ${c.missing.join(', ')}</span>` : '');
    return true;
  } catch (e) {
    $('fileInfo').innerHTML = `📄 estimator_node.py <span class="no">✗ ${String(e).slice(0, 200)}</span>`;
    return false;
  }
}
$('reloadBtn').onclick = async () => { if (await loadCode()) consoleLine('ok', '✓ reloaded — press ▶ Run my code to fly with it'); };
async function loadScript() { try { $('script').value = (await (await fetch('/api/simlite/script')).json()).text; } catch (e) {} }
$('saveBtn').onclick = async () => {
  await fetch('/api/simlite/script', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: $('script').value }) });
  consoleLine('ok', '✓ flight script saved in your account');
};

// ---------------------------------------------------------------- flying
let loop = null;
async function fly(opts = {}) {
  S.runName = opts.runName || null;
  if (!S.files) { if (!(await loadCode())) { consoleLine('bad', 'Your NAVERA code could not be loaded.'); return; } }
  stop(); clearMap(); $('result').style.display = 'none'; $('log').innerHTML = ''; $('console').innerHTML = '';
  S.rows = []; S.evlines = []; $('saveRunBtn').disabled = true;
  ['gps', 'camera', 'light', 'imu'].forEach(k => markFault(k, k === 'light' ? S.light : 'ok'));
  const cfg = { vehicle: S.vehicle, start: S.start, dest: S.dest, profile: S.profile, light: S.light,
    speed: +$('speedIn').value || null, max_speed: +$('maxIn').value || null, seed: Math.floor(Math.random() * 1e6) };
  consoleLine('ok', `▶ starting: your estimator (${S.files.origin === 'mine' ? 'your copy' : 'original NAVERA'}) + flight script`);
  if (opts.cfg) Object.assign(cfg, opts.cfg);
  try { show(await call('start', { cfg, script: opts.script != null ? opts.script : $('script').value })); }
  catch (e) { consoleLine('bad', 'Your code stopped while starting:\n' + e); openTab('code'); return; }
  S.running = true; S.paused = false; setButtons();
  loop = setInterval(tick, 100);
}
async function tick() {
  if (S.busy || S.paused || !S.running) return;
  S.busy = true;
  try { show(await call('advance', { seconds: 0.1 * S.rate })); }
  catch (e) { consoleLine('bad', 'Your code stopped during the flight:\n' + e); openTab('code'); stop(); }
  S.busy = false;
}
function stop() { if (loop) clearInterval(loop); loop = null; S.running = false; setButtons(); }
function setButtons() {
  $('pauseBtn').disabled = !S.running; $('pauseBtn').textContent = S.paused ? '▶ Resume' : '⏸ Pause';
  document.querySelectorAll('#vehSeg button').forEach(b => b.disabled = S.running);
}
$('flyBtn').onclick = () => fly(); $('runBtn').onclick = () => fly();

// ---------------------------------------------------------------- mission 28: my_scenario.json in, my_runs/ out
const FAULT_CALL = { gps: { ok: 'sim.restore_gps()', jammed: 'sim.jam_gps()', spoof_jump: 'sim.spoof_gps("jump")',
  spoof_drift: 'sim.spoof_gps("drift")', off: 'sim.gps_off()' }, camera: { ok: 'sim.camera_ok()', failed: 'sim.camera_fail()' } };
function scenarioScript(sc) {
  const faults = sc.faults || [];
  for (const f of faults) {
    if (!Array.isArray(f) || f.length !== 3 || typeof f[0] !== 'number' || !(FAULT_CALL[f[1]] || {})[f[2]])
      throw new Error(`fault ${JSON.stringify(f)}: use [seconds, "gps", "ok|jammed|spoof_jump|spoof_drift|off"] or [seconds, "camera", "ok|failed"]`);
  }
  const last = faults.reduce((m, f) => Math.max(m, f[0]), 0), tail = +sc.tail_s || 40;
  if (last + tail > 150) throw new Error('keep the whole scenario under 150 s after "en route"');
  const lines = faults.map((f, i) => `    if e >= ${f[0]} and ${i} not in done:\n        done.add(${i}); sim.log("${f[1]} -> ${f[2]}"); ${FAULT_CALL[f[1]][f[2]]}`);
  return `# generated from my_scenario.json (${sc.name})\ndone = set()\n\ndef on_tick(sim, t):\n    e = sim.enroute_s\n    if e is None:\n        return\n` +
    (lines.length ? lines.join('\n') + '\n' : '') + `    if e >= ${last + tail}:\n        sim.stop("scenario finished")\n`;
}
async function loadScenario() {
  if (!LESSON_ID) return;
  const r = await fetch('/api/simlite/scenario?lesson=' + encodeURIComponent(LESSON_ID));
  if (r.status === 404) return;                      // this mission has no scenario file
  const d = await r.json();
  $('scenBox').style.display = '';
  if (!r.ok) { $('scenText').innerHTML = `<span class="no">${esc(d.error)}</span>`; S.scenario = null; return; }
  S.scenario = d;
  const f = (d.faults || []).map(x => `${x[0]} s: ${x[1]} → ${x[2]}`).join(' · ') || 'no fault';
  $('scenText').textContent = `“${d.name}” · vision ${d.vision || 'measured'} · ${f} · then ${d.tail_s || 40} s`;
}
$('scenReload').onclick = loadScenario;
$('scenFly').onclick = async () => {
  await loadScenario();
  if (!S.scenario) return;
  let script;
  try { script = scenarioScript(S.scenario); } catch (e) { $('scenText').innerHTML = `<span class="no">${esc(e.message)}</span>`; return; }
  const name = String(S.scenario.name || 'my_run').replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 40) || 'my_run';
  setVehicle('drone');
  fly({ runName: name, script, cfg: { vehicle: 'drone', start: SCEN_ROUTE.start, dest: SCEN_ROUTE.dest,
    profile: S.scenario.vision === 'measured' ? 'measured' : 'target' } });
};
function csvCell(v) { v = v == null ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
async function saveRun(name) {
  if (!LESSON_ID) { consoleLine('warn', 'Open Sim Lite from a mission to save into its my_runs/ folder.'); return; }
  name = name || prompt('Name of this run (letters, digits, - and _):', 'lite_run');
  if (!name) return;
  const csv = [COLUMNS.join(',')].concat(S.rows.map(r => COLUMNS.map(k => csvCell(r[k])).join(','))).join('\n') + '\n';
  const r = await fetch('/api/simlite/flight', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lesson: LESSON_ID, run: name, csv, events: S.evlines.join('\n') + '\n' }) });
  const d = await r.json();
  if (r.ok) toastLog('ok', `✓ flight saved: ${d.path} (${S.rows.length} rows) — now run python3 campaign.py`);
  else toastLog('bad', 'not saved: ' + d.error);
  S.runName = null;
}
$('saveRunBtn').onclick = () => saveRun(null);
$('pauseBtn').onclick = () => { S.paused = !S.paused; setButtons(); };
$('resetBtn').onclick = () => { stop(); clearMap(); $('result').style.display = 'none'; drawPlan(); paintCards(null); $('clock').textContent = 'T+ 00:00'; };
function trim(group, keep) { const l = group.getLayers(); for (let i = 0; i < l.length - keep; i++) group.removeLayer(l[i]); }
function clearMap() { lay.truth.setLatLngs([]); lay.nav.setLatLngs([]); lay.gps.clearLayers(); lay.vis.clearLayers(); navC.setStyle({ opacity: 0 }); navC.unbindTooltip(); errs = []; drawChart(); }
function openTab(p) { document.querySelector(`#tabs button[data-p="${p}"]`).click(); }

// ---------------------------------------------------------------- drawing a picture from the simulation
let errs = [];
function show(s) {
  const mm = Math.floor(s.t / 60), ss = Math.floor(s.t % 60);
  $('clock').textContent = `T+ ${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
  s.trail.forEach(p => lay.truth.addLatLng(p));
  s.nav_pts.forEach(p => lay.nav.addLatLng([p[0], p[1]]));
  // only the recent sensor fixes stay on the map (the lines keep the whole story)
  s.gps_pts.forEach(p => { if (p) L.circleMarker([p[0], p[1]], { radius: 2.5, stroke: false, fillColor: p[2] ? '#ffb070' : '#7fe0e4', fillOpacity: .9 }).addTo(lay.gps); });
  s.vis_pts.forEach(p => L.marker([p[0], p[1]], { icon: L.divIcon({ className: '', iconSize: [10, 10], html: `<div style="width:9px;height:9px;transform:rotate(45deg);background:${p[2] === 'night' ? '#b9a6ff' : '#ffd27a'};border:1px solid #0b1730"></div>` }) }).addTo(lay.vis));
  trim(lay.gps, 150); trim(lay.vis, 12);
  vehM.setLatLng(s.truth); vehM.setIcon(arrow(s.heading));
  if (s.nav.lat != null) {
    navC.setLatLng([s.nav.lat, s.nav.lon]).setStyle({ opacity: .9 });
    if (!navC.getTooltip()) navC.bindTooltip(navTip);
    navC.setTooltipContent(`NAVERA: ${s.nav.state} · ${s.nav.source}`);
  }
  if (lay.truth.getLatLngs().length && !map.getBounds().pad(-0.1).contains(s.truth)) map.panTo(s.truth);
  s.rows.forEach(r => S.rows.push(r));
  s.events.forEach(e => S.evlines.push(`T+${e.t.toFixed(1)} [${e.level === 'script' ? 'inject' : e.level}] ${e.text}`));
  if (S.rows.length) $('saveRunBtn').disabled = false;
  s.events.forEach(e => logLine(e.level, `T+${e.t.toFixed(1).padStart(6)}  ${e.text}`));
  s.logs.forEach(l => logLine(l.level === 'info' ? 'node' : l.level, `        [${l.node}] ${l.text}`));
  if (s.script_error) consoleLine('bad', 'flight script:\n' + s.script_error);
  s.events.filter(e => e.level === 'script' || e.level === 'bad').forEach(e => consoleLine(e.level, `T+${e.t.toFixed(1)}  ${e.text}`));
  s.err_hist.forEach(p => errs.push(p)); drawChart();
  paintCards(s);
  if (s.phase === 'stopped') {
    stop();
    if (S.runName) saveRun(S.runName);
  }
  if (s.phase === 'arrived' && s.arrival) {
    stop();
    if (S.runName) saveRun(S.runName);
    const good = s.arrival.miss_m < 50;
    $('result').className = 'result' + (good ? '' : ' badr');
    $('result').innerHTML = `${good ? '✅' : '⚠️'} Arrived after ${Math.round(s.arrival.t)} s — the vehicle believes it is there; it is really <b>${Math.round(s.arrival.miss_m)} m</b> from the destination.`;
    $('result').style.display = 'block';
  }
}
function paintCards(s) {
  if (!s) { ['cGps', 'cNav', 'cErr', 'cVeh'].forEach(i => { $(i).textContent = '—'; $(i).className = 'v'; }); return; }
  const g = s.faults.gps, gname = { ok: 'Normal', jammed: 'Jammed', spoof_jump: 'Spoofed', spoof_drift: 'Spoofed', off: 'Off' }[g];
  $('cGps').textContent = gname; $('cGps').className = 'v ' + (g === 'ok' ? 'good' : 'bad');
  $('nGps').textContent = g === 'spoof_drift' ? 'slow drift' : g === 'spoof_jump' ? '2 km jump' : g === 'ok' ? 'fix every 0.2 s' : 'no usable fix';
  $('cNav').textContent = s.nav.source === 'none' ? s.nav.state : s.nav.source.replace(' VISION', ' vision').replace('GPS', 'GPS');
  $('cNav').className = 'v ' + (s.nav.state === 'FIX' ? 'good' : s.nav.state === 'DEGRADED' ? 'mid-c' : 'bad');
  $('nNav').textContent = s.nav.state + (s.nav.age != null ? ` · last ${s.nav.age.toFixed(1)} s ago` : '');
  $('cErr').textContent = s.error_m == null ? '—' : (s.error_m >= 1000 ? (s.error_m / 1000).toFixed(2) + ' km' : s.error_m.toFixed(1) + ' m');
  $('cErr').className = 'v ' + (s.error_m == null ? '' : s.error_m < 30 ? 'good' : s.error_m < 300 ? 'mid-c' : 'bad');
  $('cVeh').textContent = `${s.speed.toFixed(0)} m/s`;
  $('nVeh').textContent = `${s.phase} · ${(s.togo_m / 1000).toFixed(1)} km to go`;
}
function drawChart() {
  const svg = $('chart');
  if (errs.length < 2) { svg.innerHTML = ''; return; }
  const t0 = errs[0][0], t1 = errs[errs.length - 1][0] || 1, emax = Math.max(50, ...errs.map(e => e[1]));
  const pts = errs.map(([t, e]) => `${((t - t0) / Math.max(1, t1 - t0) * 300).toFixed(1)},${(54 - e / emax * 50).toFixed(1)}`).join(' ');
  svg.innerHTML = `<polyline points="${pts}" fill="none" stroke="#ff8f7a" stroke-width="2" vector-effect="non-scaling-stroke"/>` +
    `<text x="296" y="10" text-anchor="end" fill="#8fa3bb" font-size="9" font-family="Inter">max ${emax >= 1000 ? (emax / 1000).toFixed(1) + ' km' : Math.round(emax) + ' m'}</text>`;
}
function esc(t) { return String(t).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function logLine(level, text) { const d = $('log'); d.insertAdjacentHTML('beforeend', `<div class="l-${level}">${esc(text)}</div>`); if (d.children.length > 600) d.firstChild.remove(); d.parentElement.scrollTop = d.parentElement.scrollHeight; }
function consoleLine(level, text) { const d = $('console'); d.insertAdjacentHTML('beforeend', `<div class="l-${level}">${esc(text)}</div>`); d.scrollTop = d.scrollHeight; }
function toastLog(level, text) { consoleLine(level, text); logLine(level, text); }

// ---------------------------------------------------------------- start
drawPlan(); loadScript(); loadScenario();
fetch('/api/me').then(r => r.json()).then(me => { if (me.role === 'teacher') $('modeSeg').style.display = ''; }).catch(() => {});
call('ping').then(async () => { $('veilText').textContent = 'Loading your NAVERA code…'; await loadCode(); $('veil').style.display = 'none'; })
  .catch(e => { $('veilText').textContent = 'The simulator could not start in this browser: ' + e; });
