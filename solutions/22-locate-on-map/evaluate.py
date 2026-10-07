# Lesson 22 — locate every photo of the dataset and measure the error in meters.
# Run:  python3 evaluate.py      → prints a table, writes results.csv and errors.png
import csv
import time

import cv2

import navmap
from locate import DATA, locate, read_truth


def error_m(res, row):
    """Distance in meters between the answer and the truth, or None when there is no answer."""
    # TODO 5: None when the photo was not accepted, else the haversine distance (navmap.haversine_m)
    if not res.get("accepted"):
        return None
    return navmap.haversine_m(res["lat"], res["lon"], float(row["true_lat"]), float(row["true_lon"]))


def median(values):
    """The middle value of a list of numbers (the mean of the two middle ones for an even count)."""
    # TODO 6: sort, then take the middle; None for an empty list
    v = sorted(values)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


# ---- you don't need to change anything below this line ----
def run(write=True):
    rows_out = []
    for row in read_truth():
        photo = cv2.imread(f"{DATA}/{row['file']}")
        t0 = time.time()
        res = locate(photo, float(row["prior_lat"]), float(row["prior_lon"]), float(row["altitude_m"]),
                     float(row["hfov_deg"]), float(row["search_m"]))
        ms = (time.time() - t0) * 1000
        err = error_m(res, row)
        prior_err = navmap.haversine_m(float(row["prior_lat"]), float(row["prior_lon"]),
                                       float(row["true_lat"]), float(row["true_lon"]))
        name = row["file"].split("/")[-1][:-4]
        rows_out.append(dict(photo=name, source=row["source"], accepted=bool(res.get("accepted")),
                             inliers=res.get("inliers", 0), scale=res.get("scale"),
                             prior_error_m=round(prior_err, 1),
                             error_m=None if err is None else round(err, 1),
                             time_ms=round(ms), reason=res.get("reason", "")))
        r = rows_out[-1]
        print(f"{name:13s} {r['source']:7s} {'ACCEPTED' if r['accepted'] else 'no fix  '} "
              f"inliers {r['inliers']:4d}  prior off {r['prior_error_m']:6.1f} m  "
              f"error {'   -  ' if err is None else f'{err:6.1f}'} m  {ms:5.0f} ms  {r['reason']}")
    errs = [r["error_m"] for r in rows_out if r["error_m"] is not None]
    med = median(errs)
    print(f"\naccepted {len(errs)}/{len(rows_out)} photos, median error "
          f"{'-' if med is None else f'{med:.1f}'} m, worst {max(errs) if errs else '-'} m")
    if write:
        with open("results.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0]))
            w.writeheader()
            w.writerows(rows_out)
        plot(rows_out, med)
        print("written: results.csv and errors.png")
    return rows_out, med


def plot(rows, med):
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4))
    names = [r["photo"] for r in rows]
    vals = [r["error_m"] if r["error_m"] is not None else 0 for r in rows]
    colours = ["#0b6e8a" if r["source"] == "map" else "#f2a33a" for r in rows]
    ax.bar(names, vals, color=colours)
    for i, r in enumerate(rows):
        if r["error_m"] is None:
            ax.text(i, 0, "no fix", ha="center", va="bottom", rotation=90, color="#d64545")
    if med is not None:
        ax.axhline(med, color="#d64545", ls="--", label=f"median {med:.2f} m")
        ax.legend()
    ax.set_ylabel("error (m)")
    ax.set_title("Error of each photo (blue: cut from the map, orange: older imagery)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig("errors.png", dpi=90)


if __name__ == "__main__":
    try:
        run()
    except NotImplementedError as e:
        print(f"Not written yet: {e} — fill in that TODO (in locate.py or evaluate.py) and run again.")
