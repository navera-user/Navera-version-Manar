// NAVERA Sim Lite — the simulation thread. Python (Pyodide) runs here, off the page's thread:
// the world, the student's estimator from their copy, and their flight script.
importScripts('/static/vendor/pyodide/pyodide.js');
let py = null, ready = null;

async function boot() {
  py = await loadPyodide({ indexURL: '/static/vendor/pyodide/' });
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
    if (cmd === 'load') {                     // the student's NAVERA files
      py.globals.set('_files', py.toPy(args.files));
      py.runPython("world.install_navera(_files, '/navera')");
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
      py.runPython("run.world.set_fault(_k, _v)");
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
    reply(id, false, String(e.message || e));
  }
};
