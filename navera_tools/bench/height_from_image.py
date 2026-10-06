"""Height above ground from the image alone: the 33 real aerial frames, NO height given.

Each frame is matched at heights 30-1500 m (x1.5 steps, +-30 % windows); the best match gives
the position and the height (h_tried x fitted scale). The frames' true ground resolution is
known (0.30 m/px), so their true height is known for any assumed field of view (84 deg here:
only the product height x tan(fov/2) matters to the matcher)."""
import glob, math, os, time
import cv2, numpy as np
from day_pkg.local_matcher import LocalMatcher

FR = os.path.expanduser('~/navera_data/vision_pkg/vision_pkg/dataset/frames_gps')
AREA = os.path.expanduser('~/.navera_sim/dayv/bench_area/images')
files = sorted(glob.glob(FR + '/*.jpg'))
truth = [(float(os.path.basename(f).split('_lat')[1].split('_')[0]),
          float(os.path.basename(f).split('_lon')[1].split('_')[0])) for f in files]
hav = lambda a, b: 2 * 6371000 * math.asin(math.sqrt(math.sin(math.radians(b[0] - a[0]) / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2))
HFOV = 84.0
true_mpp = 0.62 * 0.9683 * 768 / 1536
M = LocalMatcher(AREA)
ok = wrong = 0; errs, ratios, times = [], [], []
for i, f in enumerate(files):
    img = cv2.imread(f)
    true_h = true_mpp * img.shape[1] / (2 * math.tan(math.radians(HFOV) / 2))
    prior = truth[i - 1] if i else truth[0]               # where the vehicle was a frame ago
    t0 = time.time()
    r = M.locate_any_height(img, prior, 600.0, HFOV)
    times.append(time.time() - t0)
    if r["accepted"]:
        e = hav((r["predicted_lat"], r["predicted_lon"]), truth[i])
        ok += 1; wrong += e > 50; errs.append(e); ratios.append(r["altitude_m"] / true_h)
        if i < 3:
            print(f"frame {i}: true height {true_h:.0f} m -> found {r['altitude_m']:.0f} m "
                  f"(tried {r['height_tried_m']:.0f} m, {r['inliers']} inliers), position error {e:.1f} m")
print(f"no height given: located {ok}/{len(files)}, wrong {wrong}, position median {np.median(errs):.1f} m; "
      f"height found / true = {np.median(ratios):.3f} (spread {min(ratios):.3f}-{max(ratios):.3f}); "
      f"{np.median(times):.1f} s per frame")
