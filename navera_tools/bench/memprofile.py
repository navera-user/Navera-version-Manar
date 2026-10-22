#!/usr/bin/env python3
"""Run a NAVERA node under a memory profiler (development only, not product code).

    python3 navera_tools/bench/memprofile.py --out PROFILE.jsonl [--every 60] [--depth 8]
        [--no-trace] MODULE [node arguments, e.g. --ros-args -p k:=v]

MODULE is the node's module (e.g. day_pkg.nodes.day_subscriber); its main() is run in this
process. Every --every seconds one JSON line is appended to --out:

  rss_mib, vms_mib            /proc/self/status
  py_traced_mib               tracemalloc's current total (Python + numpy allocations)
  top                         the 25 source lines whose traced memory grew most since the first
                              snapshot (size and count difference) — the growth's origin
  torch                       torch.cuda memory_allocated / memory_reserved (MiB), if torch is loaded
  gc_top                      the 15 most numerous Python object types (count) and their change
  containers                  the length of every list / deque / dict attribute of the node
                              objects that grew by more than 50 entries since the first snapshot

tracemalloc slows allocation-heavy Python ~1.3-2x; --no-trace keeps only RSS / torch / gc.
"""
import argparse
import collections
import gc
import importlib
import json
import sys
import threading
import time
import tracemalloc


def _status():
    out = {}
    with open("/proc/self/status") as f:
        for line in f:
            k, _, v = line.partition(":")
            if k in ("VmRSS", "VmSize", "RssAnon", "RssFile", "RssShmem"):
                out[k] = round(int(v.split()[0]) / 1024.0, 1)
    return out


def _short(path):
    """A source path without its site-packages / workspace prefix."""
    return path.split("/site-packages/")[-1].split("/build/")[-1]


def _containers(roots):
    """{path: len} of the list / deque / dict / set attributes of the given objects (one level deep,
    and one level into their plain-object attributes)."""
    out = {}
    for rname, obj in roots:
        for k, v in list(vars(obj).items()):
            if isinstance(v, (list, dict, set, collections.deque)):
                out[f"{rname}.{k}"] = len(v)
            elif hasattr(v, "__dict__") and not isinstance(v, type) and type(v).__module__.split(".")[0] in (
                    "day_pkg", "navera_common", "navera_estimator", "camera_pkg", "navera_output"):
                for k2, v2 in list(vars(v).items()):
                    if isinstance(v2, (list, dict, set, collections.deque)):
                        out[f"{rname}.{k}.{k2}"] = len(v2)
    return out


def _nodes():
    """The rclpy Node objects alive in this process."""
    try:
        from rclpy.node import Node
    except ImportError:
        return []
    return [(type(o).__name__, o) for o in gc.get_objects() if isinstance(o, Node)]


def sampler(a, t_start):
    first = None
    gc_first = None
    cont_first = None
    while True:
        time.sleep(a.every)
        rec = dict(t=round(time.time() - t_start, 1), wall=round(time.time(), 1))
        st = _status()
        rec.update(rss_mib=st.get("VmRSS"), vms_mib=st.get("VmSize"), rss_anon_mib=st.get("RssAnon"),
                   rss_file_mib=st.get("RssFile"), rss_shmem_mib=st.get("RssShmem"))
        if "torch" in sys.modules:
            try:
                import torch
                if torch.cuda.is_available() and torch.cuda.is_initialized():
                    rec["torch"] = dict(alloc_mib=round(torch.cuda.memory_allocated() / 2 ** 20, 1),
                                        reserved_mib=round(torch.cuda.memory_reserved() / 2 ** 20, 1))
            except Exception as e:                       # noqa: BLE001 — a profile, not the product
                rec["torch"] = repr(e)
        if tracemalloc.is_tracing():
            snap = tracemalloc.take_snapshot().filter_traces((tracemalloc.Filter(False, tracemalloc.__file__),))
            rec["py_traced_mib"] = round(tracemalloc.get_traced_memory()[0] / 2 ** 20, 1)
            if first is None:
                first = snap
            else:
                stats = snap.compare_to(first, "traceback")
                rec["top"] = [dict(kib=round(s.size_diff / 1024.0, 1), n=s.count_diff,
                                   where=[f"{_short(fr.filename)}:{fr.lineno}" for fr in s.traceback[-a.depth:]])
                              for s in stats[:25] if s.size_diff > 0]
        counts = collections.Counter(type(o).__name__ for o in gc.get_objects())
        if gc_first is None:
            gc_first = counts
        rec["gc_top"] = [(k, n, n - gc_first.get(k, 0)) for k, n in counts.most_common(15)]
        rec["gc_grew"] = sorted(((k, n - gc_first.get(k, 0)) for k, n in counts.items()
                                 if n - gc_first.get(k, 0) > 200), key=lambda x: -x[1])[:15]
        try:
            cont = _containers(_nodes())
            if cont_first is None:
                cont_first = cont
            rec["containers"] = {k: [v, v - cont_first.get(k, 0)] for k, v in cont.items()
                                 if v - cont_first.get(k, 0) > 50}
        except Exception as e:                           # noqa: BLE001
            rec["containers"] = repr(e)
        with open(a.out, "a") as f:
            f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=60.0)
    ap.add_argument("--depth", type=int, default=8, help="traceback frames kept per allocation")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("module")
    a, rest = ap.parse_known_args()
    if not a.no_trace:
        tracemalloc.start(a.depth)
    threading.Thread(target=sampler, args=(a, time.time()), daemon=True).start()
    sys.argv = [a.module] + rest
    mod = importlib.import_module(a.module)
    return mod.main()


if __name__ == "__main__":
    sys.exit(main())
