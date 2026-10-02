import glob, math, os, sqlite3, sys, time
import cv2, numpy as np
sys.path.insert(0, os.path.expanduser('~/Navera/navera_tools/sim'))
from physical_camera import PhysicalCamera, SIM_LENS
from navera_common.camera_model import CameraModel
from navera_common.frame_builder import FrameBuilder
from day_pkg.local_matcher import LocalMatcher
db = sqlite3.connect(os.path.expanduser('~/navera_data_map.mbtiles'))
def get_tile(z, x, y):
    r = db.execute('select tile_data from tiles where zoom_level=? and tile_column=? and tile_row=?', (z, x, 2 ** z - 1 - y)).fetchone()
    return r[0] if r else None
FR = os.path.expanduser('~/navera_data/vision_pkg/vision_pkg/dataset/frames_gps')
truth = [(float(os.path.basename(f).split('_lat')[1].split('_')[0]), float(os.path.basename(f).split('_lon')[1].split('_')[0])) for f in sorted(glob.glob(FR + '/*.jpg'))]
M = LocalMatcher(os.path.expanduser('~/.navera_sim/dayv/bench_area/images'))
cam = PhysicalCamera(SIM_LENS, get_tile, seed=3)
fb = FrameBuilder(CameraModel.from_calibration(SIM_LENS), max_tilt_deg=60)
def q_body(roll, up, hdg):
    r, p, y = math.radians(roll), -math.radians(up), math.radians(90 - hdg)
    cr, sr, cp, sp, cy, sy = math.cos(r/2), math.sin(r/2), math.cos(p/2), math.sin(p/2), math.cos(y/2), math.sin(y/2)
    return (sr*cp*cy - cr*sp*sy, cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy, cr*cp*cy + sr*sp*sy)
hav = lambda a, b: 2 * 6371000 * math.asin(math.sqrt(math.sin(math.radians(b[0] - a[0]) / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2))
rng = np.random.default_rng(7)
mode = sys.argv[1] if len(sys.argv) > 1 else "chain"
res = {"ok": 0, "wrong": 0, "err": [], "t_render": [], "t_build": []}
for i, (lat, lon) in enumerate(truth):
    roll, up, hdg, agl = rng.uniform(-3, 3), -float(os.environ.get("PITCH_DOWN", "0")) + rng.uniform(-2, 2), rng.uniform(0, 360), rng.uniform(120, 250)
    q = q_body(roll, up, hdg)
    t0 = time.time(); raw = cam.render(lat, lon, agl, q, speed_mps=15, heading_deg=hdg); res["t_render"].append(time.time() - t0)
    if mode == "nostraighten": q_imu = None
    else: q_imu = q_body(roll + rng.normal(0, 0.3), up + rng.normal(0, 0.3), hdg + rng.normal(0, 1.5))   # BNO085-class bias
    t0 = time.time(); out, meta = fb.build(raw, i, 0, q_imu, altitude=(agl, 3, "x")); res["t_build"].append(time.time() - t0)
    if not meta["usable"]: continue
    if i == 5: cv2.imwrite('/tmp/claude-1000/-home-shadow-team/9c5e54c8-7738-4a52-b6e1-799f1d7c83b3/scratchpad/raw.jpg', raw); cv2.imwrite('/tmp/claude-1000/-home-shadow-team/9c5e54c8-7738-4a52-b6e1-799f1d7c83b3/scratchpad/built.jpg', out)
    mpp = 2 * agl * math.tan(math.radians(meta['camera_hfov_deg']) / 2) / out.shape[1]
    r = M.locate(out, (lat + 0.002, lon - 0.002), 600.0, mpp, scale_tol=0.15)
    if r['accepted']:
        e = hav((r['predicted_lat'], r['predicted_lon']), (lat, lon)); res['err'].append(e); res['ok'] += 1; res['wrong'] += e > 50
e = sorted(res['err'])
print(f"{mode}: located {res['ok']}/{len(truth)}, wrong {res['wrong']}, median {np.median(e) if e else float('nan'):.1f} m, p90 {e[int(.9*len(e))-1] if e else float('nan'):.1f} m | render {1000*np.median(res['t_render']):.0f} ms, build {1000*np.median(res['t_build']):.0f} ms")
