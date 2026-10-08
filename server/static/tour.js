/* NAVERA Academy — guided tours and one-time tips for beginners.
 *
 *   Tour.maybe('home')     start the home tour once per user (remembered in this browser)
 *   Tour.start('mission')  start a tour now (menu: "Show the tour again")
 *   Tip.once('first-fail') show a closable tip once
 */
'use strict';
(() => {
  const me = () => (typeof ME !== 'undefined' ? ME : null);   // ME and Prefs are defined by app.js
  const who = () => (me() && me().name) || 'anon';
  const key = (k) => `academy:${who()}:${k}`;
  const seen = (k) => { if (me() && me().prefs && me().prefs[k.replace(/[^a-z0-9_-]/g, '_')]) return true; try { return localStorage.getItem(key(k)) === '1'; } catch (e) { return false; } };
  const mark = (k) => { try { localStorage.setItem(key(k), '1'); } catch (e) {} if (typeof Prefs !== 'undefined') Prefs.set(k.replace(/[^a-z0-9_-]/g, '_')); };
  const q = (sel) => (typeof sel === 'function' ? sel() : document.querySelector(sel));
  const visible = (el) => el && el.offsetParent !== null && el.getBoundingClientRect().width > 0;

  const TOURS = {
    home: [
      {title: 'Welcome to the expedition', text: 'This short tour shows you around. It takes one minute. You can close it at any time and replay it from your name menu (top right).', target: null},
      {target: '.glass', title: 'Your rank and progress', text: 'Every mission you pass gives you 100 XP. Your rank grows from Fledgling to Migration Master. The bar shows how far you are from the next rank.'},
      {target: '#goNext', title: 'Continue where you stopped', text: 'This button always opens your next mission.'},
      {target: '.mapwide', title: 'The expedition map', text: 'Each waypoint is a mission. Filled waypoints are done; the glowing one is your next mission. Click any waypoint to open it.', scroll: true},
      {target: '.medals', title: 'Badges', text: 'Finish a whole leg of the journey to earn its badge. Some special badges reward key missions.', scroll: true},
      {target: '.legblock', title: 'Missions, leg by leg', text: 'The 30 missions are grouped in 7 legs. Each row shows the time to plan, the XP and your status. Missions build on each other: take them in order.', scroll: true},
      {target: '#bookBtn', title: 'Shared hardware', text: 'The simulator and the camera exist only once for the whole class. Book them here only when a mission needs them, and release them when you finish.'},
      {target: '#userBtn', title: 'Your menu', text: 'Change your password, reset your NAVERA copy if you broke it (a backup is kept), or replay this tour. Ready? Start your first mission!'},
    ],
    mission: [
      {title: 'Your mission workspace', text: 'Left: the mission text. Right: your tools — code editor, terminal and simulator. Let us look at each part.', target: null},
      {target: '.mhero', title: 'The mission header', text: 'The leg, the mission number, the time to plan, the XP and the number of tasks. It turns green with "Complete" when you pass.'},
      {target: '.notebook .tabs', title: 'Course, then Lab', text: 'Read the Course tab first: it explains the ideas. Then open the Lab tab: it tells you step by step what to do.'},
      {target: () => document.querySelector('.doc pre .run:not(.copy)'), title: 'Run buttons', text: 'Grey boxes with a ▶ Run button contain a command. Click Run and it is typed in your terminal for you.', optional: true},
      {target: '#tree', title: 'Your files', text: 'lessons/ holds the files of each mission; navera/ is your own copy of the real NAVERA code. Click a file to open it in the editor.'},
      {target: '[data-pane=terminal]', title: 'The terminal', text: 'A real Linux terminal on the NAVERA computer, inside your own safe sandbox. Ctrl+C stops a program; the ↑ key repeats an earlier command.'},
      {target: '#checkBtn', title: 'Check my work', text: 'When you finish the tasks, press Check. You get a field report: ✔ green lines are correct, ✘ red lines come with a hint. You can check as many times as you want.'},
      {target: '#resetLesson', title: 'Start a lab again', text: 'Reset lab files puts this mission\'s files back as they were. Your current version is kept in a backup — nothing is lost.'},
      {target: '#nextBtn', title: 'Move between missions', text: 'Use these arrows to go to the previous or next mission. Good luck, navigator!'},
    ],
  };

  const TIPS = {
    'first-fail': {title: 'How to read the field report', text: 'Start with the first red ✘ line. Read the line under it (what was wrong) and the gold hint box (where to look). Fix one thing, save with Ctrl+S, and check again.'},
    'first-pass': {title: 'Mission complete!', text: 'Your XP and rank on the home page went up. Before you move on, read the "Going further" part of the lab if you want an extra challenge.'},
    'first-terminal': {title: 'Terminal tips', text: 'Ctrl+C stops a running program. ↑ repeats a command. Tab completes file names. If the terminal closes, press Enter to open it again.'},
    'first-lab': {title: 'How to do a lab', text: 'Follow the steps in order. Gold "Task" boxes are what the Check grades. Run each command and compare with the expected output written in the lab.'},
    'first-edit': {title: 'Remember to save', text: 'An orange dot on a tab means "not saved". Press Ctrl+S to save before you run your code or press Check.'},
  };

  let layer = null;
  function close() { if (layer) { layer.remove(); layer = null; } window.removeEventListener('resize', relayout); }
  let cur = null;
  function relayout() { if (cur) show(cur.name, cur.i, true); }

  function show(name, i, again) {
    const steps = TOURS[name];
    while (i < steps.length && steps[i].target && !visible(q(steps[i].target))) i++;   // skip absent elements
    if (i >= steps.length) { mark('tour-' + name); close(); return; }
    cur = {name, i};
    const s = steps[i];
    const el = s.target ? q(s.target) : null;
    if (el && s.scroll && !again) el.scrollIntoView({block: 'center'});
    close();
    layer = document.createElement('div');
    layer.className = 'tour';
    const count = steps.filter(x => !x.target || visible(q(x.target))).length;
    const pos = steps.slice(0, i + 1).filter(x => !x.target || visible(q(x.target))).length;
    layer.innerHTML = `<div class="tour-shade"></div><div class="tour-spot"></div>
      <div class="tour-card" role="dialog" aria-label="${s.title}">
        <div class="tour-step">Step ${pos} of ${count}</div><h4>${s.title}</h4><p>${s.text}</p>
        <div class="tour-btns"><button class="tour-skip">Close</button><span></span>
          ${pos > 1 ? '<button class="tour-back">Back</button>' : ''}<button class="go tour-next">${pos === count ? 'Finish' : 'Next'}</button></div></div>`;
    document.body.appendChild(layer);
    const spot = layer.querySelector('.tour-spot'), card = layer.querySelector('.tour-card');
    requestAnimationFrame(() => {
      if (el) {
        const r = el.getBoundingClientRect(), pad = 6;
        Object.assign(spot.style, {left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + 2 * pad + 'px', height: r.height + 2 * pad + 'px'});
        layer.querySelector('.tour-shade').style.display = 'none';
        const cw = card.offsetWidth, ch = card.offsetHeight, W = innerWidth, H = innerHeight;
        let x = r.left, y = r.bottom + 14;
        if (y + ch > H - 10) y = r.top - ch - 14;                 // above
        if (y < 10) { y = Math.max(10, r.top); x = r.right + 14; } // right
        if (x + cw > W - 10) x = Math.max(10, r.left - cw - 14);  // left
        x = Math.min(Math.max(10, x), W - cw - 10);
        y = Math.min(Math.max(10, y), H - ch - 10);
        Object.assign(card.style, {left: x + 'px', top: y + 'px'});
      } else {
        spot.style.display = 'none';
        Object.assign(card.style, {left: '50%', top: '50%', transform: 'translate(-50%, -50%)'});
      }
    });
    layer.querySelector('.tour-skip').onclick = () => { mark('tour-' + name); close(); };
    layer.querySelector('.tour-next').onclick = () => show(name, i + 1);
    const back = layer.querySelector('.tour-back');
    if (back) back.onclick = () => {
      let j = i - 1;
      while (j > 0 && steps[j].target && !visible(q(steps[j].target))) j--;
      show(name, Math.max(0, j));
    };
    if (!again) window.addEventListener('resize', relayout);
  }

  window.Tour = {
    close() { cur = null; close(); },
    start(name) { if (TOURS[name]) setTimeout(() => show(name, 0), 50); },
    maybe(name) { if (!seen('tour-' + name) && !(typeof AS !== 'undefined' && AS)) setTimeout(() => { if (!seen('tour-' + name)) show(name, 0); }, 900); },
    reset() { Object.keys(TOURS).forEach(n => { try { localStorage.removeItem(key('tour-' + n)); } catch (e) {} if (me() && me().prefs) { delete me().prefs['tour-' + n]; if (typeof Prefs !== 'undefined') Prefs.set('tour-' + n, false); } });
      Object.keys(TIPS).forEach(n => { try { localStorage.removeItem(key('tip-' + n)); } catch (e) {} }); },
  };
  window.Tip = {
    once(name) {
      if (seen('tip-' + name) || layer || !TIPS[name]) return;
      mark('tip-' + name);
      const t = TIPS[name], box = document.createElement('div');
      box.className = 'tip-card';
      box.innerHTML = `<div class="tip-k">Tip</div><b>${t.title}</b><p>${t.text}</p><button class="tip-x" aria-label="Close">✕</button>`;
      box.querySelector('.tip-x').onclick = () => box.remove();
      document.body.appendChild(box);
      setTimeout(() => box.classList.add('in'), 20);
    },
  };
})();
