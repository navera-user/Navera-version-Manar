"""Altitude off by +40 % (hills): fixed 15 % window vs the uncertainty-widened window."""
import glob, math, os, cv2, numpy as np
from day_pkg.local_matcher import LocalMatcher
FR = os.path.expanduser('~/navera_data/vision_pkg/vision_pkg/dataset/frames_gps')
AREA = os.path.expanduser('~/.navera_sim/dayv/bench_area/images')
files = sorted(glob.glob(FR + '/*.jpg'))
truth = [(float(os.path.basename(f).split('_lat')[1].split('_')[0]), float(os.path.basename(f).split('_lon')[1].split('_')[0])) for f in files]
hav = lambda a, b: 2 * 6371000 * math.asin(math.sqrt(math.sin(math.radians(b[0] - a[0]) / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2))
M = LocalMatcher(AREA)
true_mpp = 0.62 * 0.9683 * 768 / 1536
for i, f in enumerate(files[:3]):                          # warm the map cache
    M.locate(cv2.imread(f), truth[i], 600.0, true_mpp, margin_m=300.0)
for label, factor, tol in (("altitude right, window 15 %", 1.0, 0.15),
                           ("altitude +40 %, window 15 % (before)", 1.4, 0.15),
                           ("altitude +40 %, window from GPS uncertainty (after)", 1.4, None)):
    acc = wrong = 0; errs = []; alts = []
    for i, f in enumerate(files):
        img = cv2.imread(f); prior = truth[i - 1] if i else truth[0]
        # GPS - ground at 1.4x the true height: sigma = hypot(10, 0.25*agl), window = 2 sigma / agl
        guess_mpp = true_mpp * factor
        t = tol if tol is not None else min(max(0.15, 2 * math.hypot(10, 0.25 * 140 * factor) / (140 * factor)), 0.5)
        r = M.locate(img, prior, 600.0, guess_mpp, margin_m=300.0, scale_tol=t)
        if r['accepted']:
            e = hav((r['predicted_lat'], r['predicted_lon']), truth[i]); errs.append(e); acc += 1; wrong += e > 50
            alts.append(factor * r['scale_residual'])        # measured height / true height
    med = f"median {np.median(errs):.0f} m" if errs else "-"
    alt = f", measured height / true = {np.median(alts):.3f} (spread {np.min(alts):.3f}-{np.max(alts):.3f})" if alts else ""
    print(f"{label:52s}: accepted {acc:2d}/{len(files)}, wrong {wrong}, {med}{alt}")
