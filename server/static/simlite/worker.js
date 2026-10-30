// NAVERA Sim Lite — the simulation thread. Python (Pyodide) runs here, off the page's thread:
// NAVERA Lite's world (navera_lite/sim/world.py), the student's NAVERA Lite parts, and their flight script.
importScripts('/static/vendor/pyodide/pyodide.js');
let py = null, ready = null;

async function boot() {
  // stdlib under a .dat name: download managers (IDM…) grab .zip URLs out of the browser, and Python then
  // cannot start ("Program terminated with exit(1)")
  py = await loadPyodide({ indexURL: '/static/vendor/pyodide/', stdLibURL: '/static/vendor/pyodide/python_stdlib.dat' });
  // numpy (NAVERA Lite's parts use it): Pyodide's own wheel, served under a .dat name for the same reason, written
  // into site-packages (no .whl / .zip URL is ever fetched by the browser)
  const npBytes = new Uint8Array(await (await fetch('/static/vendor/pyodide/numpy-1.26.4-pyodide.dat')).arrayBuffer());
  await py.unpackArchive(npBytes, 'wheel', { extractDir: '/lib/python3.12/site-packages' });   // also loads its libraries
  const list = await (await fetch('/static/simlite/py/manifest.json', { cache: 'no-cache' })).json();
  for (const rel of list) {
    const text = await (await fetch('/static/simlite/py/' + rel, { cache: 'no-cache' })).text();
    const path = '/lite/' + rel;
    py.FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
    py.FS.writeFile(path, text);
  }
  py.runPython("import sys; sys.path.insert(0, '/lite'); import world, json");
}

function reply(id, ok, data) { postMessage({ id, ok, data }); }

onmessage = async (ev) => {
  const { id, cmd, args } = ev.data;
  try {
    if (!ready) ready = boot();
    await ready;
    if (cmd === 'ping') return reply(id, true, 'ready');
    if (cmd === 'load') {                     // the student's NAVERA Lite (files, the parts report, the vision profile)
      py.globals.set('_payload', py.toPy(args));
      py.runPython("world.install_lite(_payload)");
      return reply(id, true, Object.keys(args.files).length);
    }
    if (cmd === 'start') {
      py.globals.set('_cfg', py.toPy(args.cfg));
      py.globals.set('_script', args.script || '');
      py.runPython("run = world.Run(_cfg, _script)");
      return reply(id, true, JSON.parse(py.runPython("json.dumps(run.advance(0.1))")));
    }
    if (cmd === 'advance') {
      py.globals.set('_sec', args.seconds);
      return reply(id, true, JSON.parse(py.runPython("json.dumps(run.advance(_sec))")));
    }
    if (cmd === 'fault') {
      py.globals.set('_k', args.key); py.globals.set('_v', args.value);
      py.runPython("run.fault(_k, _v)");
      return reply(id, true, null);
    }
    if (cmd === 'speed') {
      py.globals.set('_s', args.mps);
      py.runPython("run.world.cruise = float(_s)");
      return reply(id, true, null);
    }
    reply(id, false, 'unknown command ' + cmd);
  } catch (e) {
    // Python errors carry the traceback: the student sees exactly where their code failed
    // (without Pyodide's own frames, which mean nothing to a student)
    const msg = String(e.message || e).split('\n');
    const out = []; for (let i = 0; i < msg.length; i++) {
      // Pyodide's frames and the simulator's own (/lite/: world.py, the rclpy stand-in) are left out:
      // the student sees their own files and the message ("…/estimator_node.py, line 12: invalid syntax")
      if (/File "\/lib\/python[^"]*\/(_pyodide|pyodide)\//.test(msg[i]) || /File "<exec>"/.test(msg[i]) || /File "\/lite\//.test(msg[i])) {
        while (msg[i + 1] && /^\s{4}/.test(msg[i + 1])) i++;     // its source line and the ^^^ marker under it
        continue;
      }
      out.push(msg[i]);
    }
    if (out.length && /^Traceback/.test(out[0]) && !(out[1] || '').startsWith('  File')) out.shift();   // no frame left to show
    reply(id, false, out.join('\n').split('/navera_lite_user/').join(''));
  }
};
