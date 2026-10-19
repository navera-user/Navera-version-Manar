#!/usr/bin/env python3
"""Table of a real-screen celestial campaign (celestial_screen.py results, one or more JSON files).

    python3 navera_tools/bench/summarise_celestial_screen.py OUT/*.json [--md table.md]

Per condition x star limit: runs, identified, right, accepted, WRONG ACCEPTS (accepted and wrong: must be 0),
false rejects (right but refused by allsky.accept), median centre error of the accepted right answers,
median spots seen / stars drawn, and the gate's most common reason. Totals at the end.
"""
import argparse
import collections
import json
import statistics


def rows_of(paths):
    out = []
    for p in paths:
        try:
            with open(p) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        for r in d.get("results", []):
            r["_file"] = p
            out.append(r)
    return out


def table(rows):
    by = collections.OrderedDict()
    for r in rows:
        by.setdefault((r["condition"], r["limit_mag"]), []).append(r)
    lines = ["| condition | limit mag | runs | identified | right | accepted | WRONG ACCEPTS | false rejects | "
             "median err deg (accepted) | spots / drawn | gate reason (most common) |", "|" + "---|" * 11]
    tot = collections.Counter()
    for (cond, lim), rs in by.items():
        ident = [r for r in rs if r.get("identified")]
        right = [r for r in ident if r.get("correct")]
        acc = [r for r in ident if r.get("accepted")]
        wrong_acc = [r for r in acc if not r.get("correct")]
        false_rej = [r for r in right if not r.get("accepted")]
        errs = [r["centre_err_deg"] for r in acc if r.get("correct")]
        why = collections.Counter(str(r.get("gate_why")).split("(")[0].strip() for r in rs if not r.get("accepted"))
        sp = statistics.median([r.get("spots", 0) for r in rs])
        dr = statistics.median([r.get("stars_drawn", 0) for r in rs])
        lines.append(f"| {cond} | {lim:g} | {len(rs)} | {len(ident)} | {len(right)} | {len(acc)} | **{len(wrong_acc)}** | "
                     f"{len(false_rej)} | {statistics.median(errs):.3f} | {sp:g} / {dr:g} | "
                     f"{why.most_common(1)[0][0] if why else '-'} |" if errs else
                     f"| {cond} | {lim:g} | {len(rs)} | {len(ident)} | {len(right)} | {len(acc)} | **{len(wrong_acc)}** | "
                     f"{len(false_rej)} | - | {sp:g} / {dr:g} | {why.most_common(1)[0][0] if why else '-'} |")
        tot.update(runs=len(rs), ident=len(ident), right=len(right), acc=len(acc), wrong_acc=len(wrong_acc),
                   false_rej=len(false_rej), wrong=len(ident) - len(right))
    lines.append("")
    lines.append(f"TOTAL: {tot['runs']} runs, {tot['ident']} identified, {tot['right']} right, {tot['wrong']} wrong "
                 f"identifications, {tot['acc']} accepted, WRONG ACCEPTS {tot['wrong_acc']} (must be 0), "
                 f"false rejects {tot['false_rej']} of {tot['right']} right answers")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--md", default="")
    a = ap.parse_args()
    t = table(rows_of(a.files))
    print(t)
    if a.md:
        with open(a.md, "w") as f:
            f.write(t + "\n")


if __name__ == "__main__":
    main()
