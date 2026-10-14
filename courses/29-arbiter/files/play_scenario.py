"""play_scenario.py — plays a scenario LIVE, over ROS 2, into YOUR running judge, and records what it says.

    python3 play_scenario.py                 the race: race.csv into your judge, compared with the reference run
    python3 play_scenario.py FILE            any scenario, live: every change of your judge, with the time
    python3 play_scenario.py --offline       the race on a simulated clock with your Arbiter (no ROS), same table

Before a live run, start YOUR judge in the background, in this terminal (lab Step 5):
    python3 -m navera_lite.ros.arbiter_node --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
and restart it before each run (a judge remembers: kill -INT %1, then start it again).

How it works: this node ("player") publishes each row of the scenario on navera_lite/fix/<source> when its
time comes (stamp = now − delay_s, mission 12's replay format, read with replay_node.read_rows), and listens
to navera_lite/status. Before t = 0 it waits until your judge listens on the four fix topics (discovery, as
replay_node's start_delay_s). The race (race.csv) is then compared with reference_run.json: the decision at
11 moments (state, source, reason; numbers in the reason are not compared) and every change of winner
(same order, within ±0.35 s: the live judge ticks at 5 Hz with its own phase). The run is saved in my_run.json.
"""
import json
import os
import re
import sys
import time

import judge_lab as jl
import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

RACE = os.path.join(jl.DATA, "race.csv")
REFERENCE = os.path.join(jl.DATA, "reference_run.json")
SWITCH_TOL_S = 0.35
START_WAIT_S = 15.0
EXTRA_DELAY_S = 1.0          # after discovery, as replay_node's start_delay_s


def _norm(text):
    return re.sub(r"[0-9.]+", "#", text or "")


def live(path):
    """Play `path` into the running judge. Returns [(t, state, source or None, message)] for every status."""
    try:
        import rclpy
        from diagnostic_msgs.msg import DiagnosticStatus
        from sensor_msgs.msg import NavSatFix
    except ImportError as e:
        sys.exit(f"ROS 2 is not available in this terminal ({e}): open a new terminal tab.")
    rp = rk.load_student("navera_lite.ros.replay_node")
    conv = rk.load_student("navera_lite.ros.convert")
    qos = rk.load_student("navera_lite.ros.qos")
    est_mod = jl.est_mod
    rows = jl._rows(path)
    rclpy.init()
    node = rclpy.create_node("player")
    pubs = {n: node.create_publisher(NavSatFix, f"/navera_lite/fix/{n}", qos.FIX_QOS) for n in est_mod.SOURCES}
    got = []                                                  # (receive time, msg)
    node.create_subscription(DiagnosticStatus, "/navera_lite/status", lambda m: got.append((time.monotonic(), m)),
                             qos.STATUS_QOS)

    def now_s():
        return node.get_clock().now().nanoseconds * 1e-9

    try:
        end = time.monotonic() + START_WAIT_S
        print("waiting for your judge (discovery)…", flush=True)
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
            if got and all(p.get_subscription_count() >= 1 for p in pubs.values()):
                break
        if not got:
            sys.exit("no status from a judge in 15 s. Start yours first, in THIS terminal:\n"
                     "  python3 -m navera_lite.ros.arbiter_node --ros-args --params-file navera_lite.yaml "
                     "> arbiter.log 2>&1 &\n(and read arbiter.log if it stopped: `tail arbiter.log`)")
        missing = [n for n, p in pubs.items() if p.get_subscription_count() < 1]
        if missing:
            sys.exit(f"the judge does not listen on navera_lite/fix/{missing[0]}: is it YOUR arbiter_node?")
        judges = node.count_publishers("/navera_lite/status")
        if judges > 1:
            sys.exit(f"{judges} judges publish on /navera_lite/status: stop the extra one (`jobs`, kill -INT %N), "
                     "then start this again.")
        first = {kv.key: kv.value for kv in got[-1][1].values}.get("state")
        if first != "STARTING":
            sys.exit(f"your judge already says {first}: it remembers an earlier run. Restart it (kill -INT %1, "
                     "then start it again, lab Step 5) and play again.")
        t_end = time.monotonic() + EXTRA_DELAY_S
        while time.monotonic() < t_end:
            rclpy.spin_once(node, timeout_sec=0.02)
        t0 = time.monotonic()
        got.clear()
        last_t = rows[-1]["t_s"] + 6.0
        print(f"playing {os.path.basename(path)}: {len(rows)} fixes in {rows[-1]['t_s']:.0f} s, listening "
              f"{last_t:.0f} s…", flush=True)
        i = 0
        while True:
            t = time.monotonic() - t0
            while i < len(rows) and rows[i]["t_s"] <= t:
                pubs[rows[i]["source"]].publish(conv.to_navsatfix(rp.row_to_estimate(rows[i], now_s())))
                i += 1
            if t > last_t:
                break
            rclpy.spin_once(node, timeout_sec=0.005)
    except KeyboardInterrupt:
        sys.exit("stopped (Ctrl+C).")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    out = []
    for tr, msg in got:
        values = {kv.key: kv.value for kv in msg.values}
        out.append((round(tr - t0, 3), values.get("state", "?"), values.get("source") or None, msg.message))
    if not out:
        sys.exit("your judge said nothing during the scenario: read arbiter.log (`tail arbiter.log`).")
    return out


def offline(path):
    """The same scenario through YOUR Arbiter on a simulated clock (no ROS)."""
    rows = jl._rows(path)
    try:
        run = jl.simulate(jl.arb_mod.Arbiter(dict(jl.cfg())), rows, rows[-1]["t_s"] + 6.0)
    except Exception as e:
        if isinstance(e, NotImplementedError) or "NoneType" in str(e):
            sys.exit("your Arbiter is not finished (a TODO returns None): `python3 judge_lab.py test` shows which.")
        sys.exit(f"your Arbiter stopped with {type(e).__name__}: {e}{jl._hint(e)}")
    return [(t, d.state, d.source, d.reason) for t, d, _ in run]


def changes(statuses):
    """[(t, from, to)] every time the winning source changes."""
    out, prev = [], None
    for t, _, src, _ in statuses:
        if src != prev:
            out.append((t, prev, src))
            prev = src
    return out


def print_changes(statuses):
    last = None
    for t, state, src, msg in statuses:
        key = (state, src, _norm(msg))
        if key != last:
            print(f"{t:6.1f} s  {state:8s} {msg if len(msg) < 90 else msg[:89] + '…'}")
            last = key


def race(statuses, mode):
    with open(REFERENCE) as f:
        ref = json.load(f)
    print(f"\nThe race ({mode}): your judge vs the reference run, on the same scenario.\n")
    print(f"{'t (s)':>6} | {'what happens':32s} | {'reference':38s} | {'yours':38s} |")
    good, samples = 0, []
    for s in ref["samples"]:
        mine = [x for x in statuses if x[0] <= s["t_s"]]
        t, state, src, msg = mine[-1] if mine else (None, "(none)", None, "")
        ok = (state, src, _norm(msg)) == (s["state"], s["source"], _norm(s["reason"]))
        good += ok
        samples.append({"t_s": s["t_s"], "state": state, "source": src, "reason": msg, "same": ok})
        r = f"{s['state']} {s['reason']}"
        y = f"{state} {msg}"
        print(f"{s['t_s']:6.1f} | {s['what'][:32]:32s} | {r[:38]:38s} | {y[:38]:38s} | {'✔' if ok else '✘'}")
    mine_sw = changes(statuses)
    ref_sw = [(w["t_s"], w["from"], w["to"]) for w in ref["switches"]]
    print(f"\n{'reference switch':30s} | {'yours':30s} |")
    sw_ok = len(mine_sw) == len(ref_sw)
    for k in range(max(len(mine_sw), len(ref_sw))):
        r = ref_sw[k] if k < len(ref_sw) else None
        m = mine_sw[k] if k < len(mine_sw) else None
        same = (r is not None and m is not None and r[1:] == m[1:] and abs(r[0] - m[0]) <= SWITCH_TOL_S)
        sw_ok = sw_ok and same
        fr = f"{r[1] or '—'}→{r[2] or '—'} at {r[0]:.2f} s" if r else ""
        fm = f"{m[1] or '—'}→{m[2] or '—'} at {m[0]:.2f} s" if m else ""
        print(f"{fr:30s} | {fm:30s} | {'✔' if same else '✘'}")
    n = len(ref["samples"])
    print(f"\nDecisions: {good} of {n} identical. Switches: {'all match' if sw_ok else 'they differ'} "
          f"(±{SWITCH_TOL_S} s).")
    if good == n and sw_ok:
        print("Your judge decides like the reference. 🏁")
    else:
        print("Find the first ✘: what does the reference know that your judge does not? (lesson §2–§5)")
    return {"scenario": os.path.basename(RACE), "mode": mode, "samples": samples,
            "switches": [list(x) for x in mine_sw], "decisions_same": good, "decisions": n,
            "switches_same": bool(sw_ok), "statuses": [list(x) for x in statuses]}


def main():
    args = sys.argv[1:]
    if args and args[0] == "--offline":
        result = race(offline(RACE), "offline")
        print("\n(offline: your Arbiter on a simulated clock. The live race needs your node: lab Step 6.)")
        return
    path = args[0] if args else RACE
    statuses = live(path)
    if os.path.abspath(path) != os.path.abspath(RACE):
        print_changes(statuses)
        print(f"\nchanges of winner: " + ", ".join(f"{a or '—'}→{b or '—'} at {t:.1f} s" for t, a, b in changes(statuses)))
        return
    result = race(statuses, "live")
    with open("my_run.json", "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print("Saved my_run.json (the check reads it).")


if __name__ == "__main__":
    main()
