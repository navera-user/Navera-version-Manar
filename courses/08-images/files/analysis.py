# Lab 8 analysis: your convolution and warp against OpenCV, contrast methods, heading and scale sweeps.
# Uses YOUR functions of images_lab.py (finish TODO 1-11 first). Writes results.json and analysis.png.
#     python3 analysis.py
import json
import time
import warnings

import cv2
import numpy as np

import images_lab as L

D = "/data/academy/08-images/"
FRAME = "/data/navera_data/camera_pkg/camera_pkg/data/day/frame_0005.jpeg"
info = json.load(open(D + "info.json"))
photo = cv2.imread(D + info["photo"]["file"])
mgray = cv2.cvtColor(cv2.imread(D + info["map"]["file"]), cv2.COLOR_BGR2GRAY)
heading, pmpp, mmpp = info["photo"]["heading_deg"], info["photo"]["m_per_px"], info["map"]["m_per_px"]
for name in ("to_gray", "normalise", "equalise", "convolve2d", "gaussian_kernel", "sobel", "rotation_scale_matrix",
             "warp_affine", "make_like_map"):
    if getattr(L, name)(*{"gaussian_kernel": (3, 1.0), "rotation_scale_matrix": (0, 0, 0, 1),
                          "convolve2d": (np.zeros((3, 3)), np.ones((1, 1))),
                          "warp_affine": (np.zeros((3, 3), np.uint8), np.eye(2, 3), 3, 3),
                          "make_like_map": (photo, heading, pmpp, mmpp)}.get(name, (np.zeros((3, 3), np.uint8),))) is None:
        raise SystemExit(f"{name}() still returns None: finish its TODO in images_lab.py first")

res = {}
raw_frame = cv2.imread(FRAME)
if raw_frame is None:
    raise SystemExit(f"data not found ({FRAME}) — ask the teacher to connect the data disk")
frame = L.to_gray(raw_frame)
res["dtypes"] = {"to_gray": str(frame.dtype), "normalise": str(np.asarray(L.normalise(frame)).dtype),
                 "equalise": str(np.asarray(L.equalise(frame)).dtype),
                 "convolve2d": str(L.convolve2d(frame, np.ones((3, 3)) / 9).dtype),
                 "make_like_map": str(np.asarray(L.make_like_map(photo, heading, pmpp, mmpp)).dtype)}
print("dtypes:", res["dtypes"])

k = L.gaussian_kernel(7, 1.5)
t0 = time.perf_counter(); own = L.convolve2d(frame, k); t1 = time.perf_counter()
ref = cv2.filter2D(frame.astype(np.float32), -1, np.ascontiguousarray(k[::-1, ::-1]), borderType=cv2.BORDER_REFLECT_101)
t2 = time.perf_counter()
gx, gy = L.sobel(frame)
sx, sy = cv2.Sobel(frame, cv2.CV_32F, 1, 0), cv2.Sobel(frame, cv2.CV_32F, 0, 1)
M = L.rotation_scale_matrix(frame.shape[1] / 2, frame.shape[0] / 2, 30.0, 0.7)
w_own = L.to_uint8(L.warp_affine(frame, M, frame.shape[1], frame.shape[0]))
w_cv = cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]), flags=cv2.INTER_LINEAR)
dw = np.abs(w_own.astype(np.int32) - w_cv.astype(np.int32))
res["convolution"] = {"gaussian_max_abs_diff": float(np.abs(own - ref).max()),
                      "sobel_max_abs_diff": float(max(np.abs(gx - sx).max(), np.abs(gy - sy).max())),
                      "own_ms": round((t1 - t0) * 1000, 1), "opencv_ms": round((t2 - t1) * 1000, 1)}
res["warp"] = {"mean_abs_diff": round(float(dw.mean()), 4), "max_abs_diff": int(dw.max())}
print("convolution vs OpenCV:", res["convolution"])
print("warp vs cv2.warpAffine:", res["warp"])

S = 160
mnorm = L.middle(L.normalise(mgray), S)
raw = cv2.resize(L.middle(L.to_gray(photo), S), (S, S))
res["similarity"] = {"raw": round(L.similarity(raw, mnorm), 3)}
res["difference"] = {"raw": round(L.difference(raw, mnorm), 2)}
for method in ("normalise", "equalise", "clahe"):
    c = L.middle(L.make_like_map(photo, heading, pmpp, mmpp, method), S)
    res["similarity"][method] = round(L.similarity(c, mnorm), 3)
    res["difference"][method] = round(L.difference(c, mnorm), 2)
print("similarity with the map:", res["similarity"])
print("difference with the map:", res["difference"])

heads = list(range(0, 71))
hs = [L.similarity(L.middle(L.make_like_map(photo, h, pmpp, mmpp), S), mnorm) for h in heads]
mpps = [round(0.50 + 0.01 * i, 2) for i in range(21)]
ss = [L.similarity(L.middle(L.make_like_map(photo, heading, m, mmpp), S), mnorm) for m in mpps]
res["heading_sweep"] = [[h, round(v, 4)] for h, v in zip(heads, hs)]
res["scale_sweep"] = [[m, round(v, 4)] for m, v in zip(mpps, ss)]
res["best_heading_deg"] = heads[int(np.argmax(hs))]
res["best_photo_m_per_px"] = mpps[int(np.argmax(ss))]
res["heading_for_similarity_above_0_5"] = [h for h, v in zip(heads, hs) if v > 0.5]
print("best heading:", res["best_heading_deg"], "deg   best photo m/px:", res["best_photo_m_per_px"])
ok = res["heading_for_similarity_above_0_5"]
print(f"similarity > 0.5 only for headings {ok[0]}..{ok[-1]} deg" if ok else "similarity never above 0.5")

with open("results.json", "w") as f:
    json.dump(res, f, indent=1)

import matplotlib                                   # noqa: E402
matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib.pyplot as plt                     # noqa: E402
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
a1.plot(heads, hs, "-o", ms=3, color="#0b6e8a")
a1.axvline(heading, color="#d64545", ls="--", lw=1, label=f"true heading {heading:g} deg")
a1.set_xlabel("heading used (deg)"); a1.set_ylabel("similarity with the map"); a1.legend(); a1.grid(alpha=0.3)
a2.plot(mpps, ss, "-o", ms=3, color="#2f855a")
a2.axvline(pmpp, color="#d64545", ls="--", lw=1, label=f"true {pmpp} m/px")
a2.set_xlabel("photo m/px used"); a2.set_ylabel("similarity with the map"); a2.legend(); a2.grid(alpha=0.3)
fig.savefig("analysis.png", dpi=90, bbox_inches="tight")
print("\nSaved results.json and analysis.png — click the picture in the file list.")
