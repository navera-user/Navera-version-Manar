#!/usr/bin/env python3
"""Table of a night screen campaign: one row per night_screen.py CSV in a folder.

    python3 navera_tools/bench/night_screen_summary.py <folder> [--md out.md]

Columns, GPS-lost phase: frames, STHN match rate (accepted by the localizer's checks),
median / p90 / max error of the accepted fixes, wrong accepts (accepted and > 100 m from
the truth or outside 3 stated sigma), share of fixes within 3 sigma, the published track
(night fix or dead reckoning) median / max error and frames with no position, ms/frame.
"""
import argparse
import csv
import glob
import os

import numpy as np


def _f(v, fmt="{:.0f}"):
    return "-" if v is None else fmt.format(v)


def stats(rows):
    lost = [r for r in rows if r["phase"] == "lost"]
    n = len(lost)
    acc = [r for r in lost if int(r["accepted"])]
    err = [float(r["err_m"]) for r in acc if r["err_m"] not in ("", None)]
    sig = [(float(r["err_m"]), float(r["sigma_m"])) for r in acc
           if r["err_m"] not in ("", None) and r["sigma_m"] not in ("", None)]
    wrong = sum(1 for r in acc if r["err_m"] not in ("", None) and (
        float(r["err_m"]) > 100.0 or (r["sigma_m"] not in ("", None) and float(r["err_m"]) > 3 * float(r["sigma_m"]))))
    pub = [float(r["navera_err_m"]) for r in lost if r["navera_err_m"] not in ("", None)]
    return dict(n=n, acc=len(acc), rate=len(acc) / n if n else None,
                med=float(np.median(err)) if err else None, p90=float(np.percentile(err, 90)) if err else None,
                max=max(err) if err else None, wrong=wrong,
                in3=sum(e <= 3 * s for e, s in sig) / len(sig) if sig else None,
                pub_med=float(np.median(pub)) if pub else None, pub_max=max(pub) if pub else None,
                nopos=sum(1 for r in lost if r["navera_err_m"] in ("", None)),
                ms=float(np.median([float(r["ms"]) for r in rows])) if rows else None,
                gps_acc=sum(1 for r in rows if r["phase"] == "gps" and int(r["accepted"])),
                gps_n=sum(1 for r in rows if r["phase"] == "gps"))


HEADER = ("| condition | GPS phase matched | lost: frames | match rate | median m | p90 m | max m | "
          "wrong (>100 m or >3σ) | within 3σ | track median / max m | no position | ms/frame |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|")


def row_md(name, s):
    return (f"| {name} | {s['gps_acc']}/{s['gps_n']} | {s['n']} | {_f(s['rate'], '{:.0%}')} | {_f(s['med'])} | "
            f"{_f(s['p90'])} | {_f(s['max'])} | {s['wrong']} | {_f(s['in3'], '{:.0%}')} | "
            f"{_f(s['pub_med'])} / {_f(s['pub_max'])} | {s['nopos']} | {_f(s['ms'])} |")


def summarize_rows(name, rows):
    """Markdown header + one row (rows as written by night_screen.py, values str or numbers)."""
    rows = [{k: ("" if v is None else v) for k, v in r.items()} for r in rows]
    return HEADER + "\n" + row_md(name, stats(rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--md", default="")
    a = ap.parse_args()
    lines = [HEADER]
    for p in sorted(glob.glob(os.path.join(a.folder, "*.csv"))):
        rows = list(csv.DictReader(open(p)))
        if rows:
            lines.append(row_md(os.path.splitext(os.path.basename(p))[0], stats(rows)))
    text = "\n".join(lines)
    print(text)
    if a.md:
        with open(a.md, "w") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
