"""NAVERA - Isaac Sim flight: a vehicle with NAVERA's downward camera over a real place in 3-D.

Run with Isaac Sim's own Python (Windows, Isaac Sim 6.0), normally by run_isaac_flight.sh:

    D:\\isaac\\isaacsim-6.0\\python.bat isaac_flight.py --out D:\\navera_isaac\\runs\\<name>
        --scene D:\\navera_isaac\\scenes\\kalaa [--traj traj_plane.csv] [--date 2026-10-21 --time 08:30]
        [--duration 420] [--fps 10] [--mount-err 1.5,-1.0,2.0] [--clouds 0.25]

Scene (prepare_scene.py; Z up, metres, X east / Y north about the scene origin, Z 0 = the
DEM at the origin): the terrain from the public DEM (SRTM-class, 257 x 257 grid) textured
with the scene imagery (Esri Wayback 2022: NOT the map NAVERA matches against), ~8 000
buildings extruded from footprints (roofs carry the imagery at their place, walls plain),
the sun at its true position for --date/--time at the place (soft shadows), a sky light,
and cloud shadows: a cut-out cloud layer at --cloud-height drifting with the wind.

The vehicle follows a flight recorded from ArduPilot SITL (--traj: real autopilot, wind,
turbulence; flight_profile.Trajectory) or, without --traj, the scripted circuit
(flight_profile.Profile). Its camera looks straight down through the body (NAVERA's nadir
mount, image top = nose) with a mounting error --mount-err (roll, pitch, yaw deg) NAVERA
does not know. The camera is rendered as a wide distortion-free pinhole (--render-hfov,
--width x --height-px); the NAVERA link turns it into the real lens (fisheye distortion,
exposure, noise, blur, H.264) — Isaac Sim's own lens and sensor models are not used.

Output (--out): session.json (t0 on this PC's clock, what was simulated), frames/*.jpg +
frames.jsonl (index, time since t0, file, truth), video/*.jpg (the chase view), done.json.
Isaac Sim data appear one update after the pose is set (measured), so each frame carries
the pose time of the previous update.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flight_profile import GeoRef, LiveFeed, Profile, Trajectory, rpy_to_quat  # noqa: E402

ap = argparse.ArgumentParser(description="NAVERA - Isaac Sim flight")
ap.add_argument("--out", required=True)
ap.add_argument("--scene", required=True, help="prepare_scene.py --scene-out directory")
ap.add_argument("--traj", default="", help="sitl_record.py CSV (else the scripted circuit)")
ap.add_argument("--pose-udp", type=int, default=0,
                help="UDP port of the LIVE vehicle state (sitl_demo.py: ArduPilot SITL flying now)")
ap.add_argument("--radius", type=float, default=900.0)
ap.add_argument("--speed", type=float, default=40.0)
ap.add_argument("--height", type=float, default=500.0)
ap.add_argument("--duration", type=float, default=420.0)
ap.add_argument("--fps", type=float, default=10.0, help="camera frames written per second")
ap.add_argument("--video-fps", type=float, default=10.0)
ap.add_argument("--render-hfov", type=float, default=100.0, help="wide pinhole the real lens is cut from")
ap.add_argument("--width", type=int, default=1920)
ap.add_argument("--height-px", type=int, default=1080)
ap.add_argument("--mount-err", default="1.5,-1.0,2.0", help="camera mount error roll,pitch,yaw deg")
ap.add_argument("--date", default="2026-10-21")
ap.add_argument("--time", default="08:30", help="local time (UTC + --utc-offset)")
ap.add_argument("--utc-offset", type=float, default=1.0)
ap.add_argument("--sun", type=float, default=3000.0, help="sun intensity at zenith (RTX units)")
ap.add_argument("--sky", type=float, default=300.0)
ap.add_argument("--clouds", type=float, default=0.25, help="cloud cover fraction 0-1 (shadows)")
ap.add_argument("--cloud-height", type=float, default=1500.0, help="m above the vehicle's ground")
ap.add_argument("--wind", default="", help="speed@dir_from_deg for the clouds (default: the trajectory's)")
ap.add_argument("--linger", type=float, default=30.0, help="s the window stays after the flight")
ap.add_argument("--stop-file", default="", help="ends the linger early when this file exists")
ap.add_argument("--gimbal", action="store_true", help="camera on a 2-axis stabiliser (level, heading follows)")
ap.add_argument("--low-clouds", type=float, default=0.0, help="cover 0-1 of an opaque cloud layer BELOW the vehicle")
ap.add_argument("--low-cloud-agl", type=float, default=150.0, help="m above the origin's ground")
ap.add_argument("--obstacles", default="", help="comma list: birds,aircraft,powerlines,cars,smoke")
ap.add_argument("--extra-buildings", type=int, default=0, help="new buildings that are not in the map")
ap.add_argument("--shake", type=float, default=0.0, help="camera vibration, deg (high-frequency jitter)")
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--vehicle-scale", type=float, default=2.5, help="visual size only")
args, _ = ap.parse_known_args()

from isaacsim import SimulationApp  # noqa: E402

TITLE = "NAVERA - Isaac Sim flight"
app = SimulationApp({"headless": False, "width": 1600, "height": 900,
                     "extra_args": [f"--/app/window/title={TITLE}", "--/app/window/x=0", "--/app/window/y=0",
                                    "--/app/window/width=1600", "--/app/window/height=900"]})

import carb  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import omni.timeline  # noqa: E402
import omni.usd  # noqa: E402
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade, Vt  # noqa: E402


def sun_position(lat, lon, when_utc):
    """(elevation, compass azimuth) in degrees, NOAA's solar position equations."""
    doy = when_utc.timetuple().tm_yday
    hour = when_utc.hour + when_utc.minute / 60 + when_utc.second / 3600
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cz)))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(decl) * math.cos(la))) + 180
    return 90 - math.degrees(zen), az % 360


def set_title():
    try:
        import omni.appwindow
        import carb.windowing
        w = omni.appwindow.get_default_app_window()
        carb.windowing.acquire_windowing_interface().set_window_title(w.get_window(), TITLE)
    except Exception as e:      # noqa: BLE001 — cosmetic
        carb.log_warn(f"window title not set: {e}")


def bring_to_front():
    """Windows: this process' main window maximised and in front (the user is watching)."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid() and u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0:
                found.append(hwnd)
            return True
        u.EnumWindows(cb, 0)
        for hwnd in found[:1]:
            u.SetWindowTextW(hwnd, TITLE)
            u.ShowWindow(hwnd, 3)                                  # SW_MAXIMIZE
            u.keybd_event(0x12, 0, 0, 0)                           # ALT: lets SetForegroundWindow work
            u.SetForegroundWindow(hwnd)
            u.keybd_event(0x12, 0, 2, 0)
            u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 3)                # topmost, then normal: raised
            u.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 3)
        return bool(found)
    except Exception as e:      # noqa: BLE001 — cosmetic
        carb.log_warn(f"window not raised: {e}")
        return False


def preview_material(stage, path, color=None, texture=None, rough=0.9, opacity_tex=None):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/pbr")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    st = None
    if texture or opacity_tex:
        st = UsdShade.Shader.Define(stage, path + "/st")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        st.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    if texture:
        tx = UsdShade.Shader.Define(stage, path + "/tex")
        tx.CreateIdAttr("UsdUVTexture")
        tx.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture)
        tx.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        tx.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        tx.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tx.ConnectableAPI(), "rgb")
    else:
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    if opacity_tex:
        ot = UsdShade.Shader.Define(stage, path + "/opac")
        ot.CreateIdAttr("UsdUVTexture")
        ot.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(opacity_tex)
        ot.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        ot.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        ot.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        ot.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        ot.CreateOutput("r", Sdf.ValueTypeNames.Float)
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(ot.ConnectableAPI(), "r")
        sh.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.5)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def box(stage, path, centre, size, mat, rot_z_deg=0.0):
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(1.0)
    x = UsdGeom.Xformable(c)
    x.AddTranslateOp().Set(Gf.Vec3d(*centre))
    x.AddRotateZOp().Set(rot_z_deg)
    x.AddScaleOp().Set(Gf.Vec3f(*size))
    bind(c.GetPrim(), mat)
    return c


def mesh(stage, path, points, counts, indices, st=None, normals=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(points, np.float32)))
    m.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.ascontiguousarray(counts, np.int32)))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.ascontiguousarray(indices, np.int32)))
    m.CreateSubdivisionSchemeAttr("none")
    if normals is not None:
        m.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(normals, np.float32)))
        m.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    if st is not None:
        pv = UsdGeom.PrimvarsAPI(m).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        pv.Set(Vt.Vec2fArray.FromNumpy(np.ascontiguousarray(st, np.float32)))
    return m


def quat_wxyz(q_xyzw):
    x, y, z, w = q_xyzw
    return Gf.Quatd(w, Gf.Vec3d(x, y, z))


def cloud_texture(path, cover, seed=5, size=1024):
    """Tileable cloud mask (white = cloud), ~cover of the area, soft-edged blobs."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((size, size), np.float32)
    for octave, w in ((8, 1.0), (16, 0.5), (32, 0.25)):
        n = rng.random((octave, octave)).astype(np.float32)
        acc += w * cv2.resize(np.tile(n, (3, 3)), (3 * size, 3 * size), interpolation=cv2.INTER_CUBIC)[size:2 * size, size:2 * size]
    thr = np.quantile(acc, 1.0 - cover)
    mask = np.clip((acc - thr) / 0.08 + 0.5, 0, 1)
    cv2.imwrite(path, (mask * 255).astype(np.uint8))


def build_vehicle(stage, kind):
    shape = UsdGeom.Xform.Define(stage, "/World/vehicle/shape")
    UsdGeom.Xformable(shape).AddScaleOp().Set(Gf.Vec3f(args.vehicle_scale, args.vehicle_scale, args.vehicle_scale))
    white = preview_material(stage, "/World/Looks/white", color=(0.92, 0.92, 0.95), rough=0.4)
    orange = preview_material(stage, "/World/Looks/orange", color=(1.0, 0.45, 0.05), rough=0.5)
    dark = preview_material(stage, "/World/Looks/dark", color=(0.08, 0.08, 0.1), rough=0.6)
    p = "/World/vehicle/shape/"
    if kind == "copter":
        box(stage, p + "body", (0, 0, 0), (0.5, 0.35, 0.18), white)
        box(stage, p + "nose", (0.28, 0, 0), (0.08, 0.2, 0.1), orange)
        for k, (bx, by) in enumerate(((0.45, 0.45), (0.45, -0.45), (-0.45, 0.45), (-0.45, -0.45))):
            box(stage, p + f"arm{k}", (bx / 2, by / 2, 0.02), (0.68, 0.05, 0.04), dark,
                math.degrees(math.atan2(by, bx)))
            box(stage, p + f"rotor{k}", (bx, by, 0.08), (0.42, 0.42, 0.01), dark, 45.0)
    else:
        box(stage, p + "fuselage", (0, 0, 0), (1.8, 0.2, 0.2), white)
        box(stage, p + "wing", (0.15, 0, 0.08), (0.3, 2.8, 0.04), white)
        box(stage, p + "tailplane", (-0.8, 0, 0.1), (0.2, 0.7, 0.03), orange)
        box(stage, p + "fin", (-0.8, 0, 0.25), (0.22, 0.03, 0.3), orange)
        box(stage, p + "prop", (0.92, 0, 0), (0.02, 0.5, 0.05), dark)


def main():
    os.makedirs(os.path.join(args.out, "frames"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "video"), exist_ok=True)
    scene = json.load(open(os.path.join(args.scene, "scene.json")))
    mos = scene["mosaic"]
    geo = GeoRef(scene["lat0"], scene["lon0"])
    z_ref = float(scene["z_ref_m"])
    live = None
    if args.pose_udp:
        prof = live = LiveFeed(args.pose_udp, geo, z_ref)
        while not live.ready():                          # SITL streams from its boot
            live.poll()
            app.update()
        vehicle, wind = live.vehicle, "4@290"
    elif args.traj:
        prof = Trajectory(args.traj, geo, z_ref)
        vehicle = prof.vehicle
        wind = prof.meta.get("wind", "7@290")
    else:
        prof = Profile(radius_m=args.radius, speed_mps=args.speed, height_m=args.height)
        vehicle, wind = "scripted", "5@290"
    wind = args.wind or wind
    wind_spd, wind_dir = (float(v) for v in wind.split("@"))
    duration = min(args.duration, prof.duration_s() if args.traj else args.duration)

    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")

    # ── terrain: DEM grid textured with the scene imagery ──
    xw, ys = geo.to_en(mos["lat_s"], mos["lon_w"])
    xe, yn = geo.to_en(mos["lat_n"], mos["lon_e"])
    hgt = np.load(os.path.join(args.scene, "terrain.npy"))          # rows south -> north
    n = hgt.shape[0]
    gx, gy = np.meshgrid(np.linspace(xw, xe, n), np.linspace(ys, yn, n))
    pts = np.stack([gx, gy, hgt], -1).reshape(-1, 3)
    st = np.stack([(gx - xw) / (xe - xw), (gy - ys) / (yn - ys)], -1).reshape(-1, 2)
    dzdx = np.gradient(hgt, axis=1) / ((xe - xw) / (n - 1))
    dzdy = np.gradient(hgt, axis=0) / ((yn - ys) / (n - 1))
    nrm = np.stack([-dzdx, -dzdy, np.ones_like(hgt)], -1)
    nrm = (nrm / np.linalg.norm(nrm, axis=-1, keepdims=True)).reshape(-1, 3)
    i = np.arange(n - 1)
    a_ = (i[:, None] * n + i[None, :]).ravel()
    quads = np.stack([a_, a_ + 1, a_ + n + 1, a_ + n], -1)
    ground = mesh(stage, "/World/terrain", pts, np.full(len(quads), 4), quads.ravel(), st, nrm)
    map_mat = preview_material(stage, "/World/Looks/map", texture=os.path.join(args.scene, "mosaic.jpg"))
    bind(ground.GetPrim(), map_mat)

    # ── buildings: roofs textured with the imagery at their place, plain walls ──
    b = np.load(os.path.join(args.scene, "buildings.npz"))
    roofs = mesh(stage, "/World/buildings/roofs", b["roof_points"], np.full(len(b["roof_tris"]), 3),
                 b["roof_tris"].ravel(), b["roof_uv"])
    bind(roofs.GetPrim(), map_mat)
    walls = mesh(stage, "/World/buildings/walls", b["wall_points"], np.full(len(b["wall_quads"]), 4),
                 b["wall_quads"].ravel())
    bind(walls.GetPrim(), preview_material(stage, "/World/Looks/wall", color=(0.78, 0.74, 0.66), rough=0.95))

    def ground_z(e, n):
        k = hgt.shape[0] - 1
        fx = min(max((e - xw) / (xe - xw) * k, 0), k - 1e-6)
        fy = min(max((n - ys) / (yn - ys) * k, 0), k - 1e-6)
        return float(hgt[int(fy), int(fx)])

    rnd = np.random.default_rng(args.seed)
    if args.extra_buildings:                # built after the map was made: not in NAVERA's map
        new_mat = preview_material(stage, "/World/Looks/newroof", color=(0.85, 0.83, 0.8), rough=0.8)
        for i in range(args.extra_buildings):
            a, d = rnd.uniform(0, 2 * math.pi), rnd.uniform(100, 1300)
            ce, cn = d * math.cos(a), d * math.sin(a)
            w_, l_, h_ = rnd.uniform(15, 50), rnd.uniform(15, 70), rnd.uniform(6, 25)
            box(stage, f"/World/new_buildings/b{i:03d}", (ce, cn, ground_z(ce, cn) + h_ / 2), (w_, l_, h_),
                new_mat, float(rnd.uniform(0, 90)))
    movers = []                             # (op, function t -> position)
    for ob in [o for o in args.obstacles.split(",") if o]:
        if ob == "birds":                   # flocks circling 60-120 m above the ground
            dark = preview_material(stage, "/World/Looks/bird", color=(0.1, 0.1, 0.1))
            for f in range(4):
                c0 = rnd.uniform(-600, 600, 2)
                for b in range(25):
                    x = UsdGeom.Xformable(box(stage, f"/World/birds/f{f}_{b}", (0, 0, 0), (0.9, 0.9, 0.15), dark))
                    op = x.GetOrderedXformOps()[0]
                    off, ph, r_, z_ = rnd.uniform(-25, 25, 2), rnd.uniform(0, 6.28), rnd.uniform(80, 200), rnd.uniform(60, 120)
                    movers.append((op, lambda t, c0=c0, off=off, ph=ph, r_=r_, z_=z_: (
                        c0[0] + r_ * math.cos(ph + 0.08 * t) + off[0], c0[1] + r_ * math.sin(ph + 0.08 * t) + off[1],
                        ground_z(c0[0], c0[1]) + z_)))
        elif ob == "aircraft":              # another aircraft crossing ~70 m below, back and forth
            wm = preview_material(stage, "/World/Looks/other", color=(0.9, 0.2, 0.2), rough=0.4)
            x = UsdGeom.Xformable(box(stage, "/World/other_aircraft/body", (0, 0, 0), (12, 14, 2.5), wm))
            op = x.GetOrderedXformOps()[0]
            movers.append(("rel", op, lambda t, s_: (s_.e + 400 * math.sin(0.05 * t), s_.n + 60 * math.cos(0.11 * t),
                                                     s_.u - 70)))
        elif ob == "powerlines":            # a 3 km line of pylons + 3 cables across the circuit
            steel = preview_material(stage, "/World/Looks/steel", color=(0.55, 0.57, 0.6), rough=0.5)
            az = rnd.uniform(0, math.pi)
            for k in range(-8, 9):
                pe, pn = k * 200 * math.cos(az), k * 200 * math.sin(az)
                gz = ground_z(pe, pn)
                box(stage, f"/World/power/pylon{k + 8}", (pe, pn, gz + 17), (2.5, 2.5, 34), steel)
                box(stage, f"/World/power/arm{k + 8}", (pe, pn, gz + 32), (1, 14, 1), steel,
                    math.degrees(az))
                if k < 8:
                    qe, qn = (k + 1) * 200 * math.cos(az), (k + 1) * 200 * math.sin(az)
                    for c in (-6, 0, 6):
                        oe, on = -c * math.sin(az), c * math.cos(az)
                        box(stage, f"/World/power/cable{k + 8}_{c + 6}", ((pe + qe) / 2 + oe, (pn + qn) / 2 + on,
                            (gz + ground_z(qe, qn)) / 2 + 31), (200, 0.4, 0.4), steel, math.degrees(az))
        elif ob == "cars":                  # 80 vehicles driving straight lines at 10-25 m/s
            for c in range(80):
                col = preview_material(stage, f"/World/Looks/car{c % 6}", color=[(0.9, 0.9, 0.9), (0.1, 0.1, 0.1),
                                       (0.7, 0.1, 0.1), (0.2, 0.3, 0.7), (0.6, 0.6, 0.6), (0.9, 0.8, 0.2)][c % 6])
                big = c % 7 == 0
                x = UsdGeom.Xformable(box(stage, f"/World/cars/c{c}", (0, 0, 0),
                                          (12, 2.5, 3.5) if big else (4.5, 1.8, 1.5), col))
                op = x.GetOrderedXformOps()[0]
                p0, hd, sp = rnd.uniform(-1500, 1500, 2), rnd.uniform(0, 2 * math.pi), rnd.uniform(10, 25)
                movers.append((op, lambda t, p0=p0, hd=hd, sp=sp: (
                    p0[0] + ((sp * t) % 3000 - 1500) * math.cos(hd), p0[1] + ((sp * t) % 3000 - 1500) * math.sin(hd),
                    ground_z(p0[0] + ((sp * t) % 3000 - 1500) * math.cos(hd),
                             p0[1] + ((sp * t) % 3000 - 1500) * math.sin(hd)) + 1.0)))
        elif ob == "smoke":                 # a plume: grey blobs rising and drifting downwind
            sm = preview_material(stage, "/World/Looks/smoke", color=(0.45, 0.45, 0.47), rough=1.0)
            src = rnd.uniform(-400, 400, 2)
            for k in range(30):
                sz = 15 + 4 * k
                x = UsdGeom.Xformable(box(stage, f"/World/smoke/p{k}", (0, 0, 0), (sz, sz, sz * 0.6), sm,
                                          float(rnd.uniform(0, 90))))
                op = x.GetOrderedXformOps()[0]
                movers.append((op, lambda t, k=k, src=src: (src[0] + 6.0 * k + 3 * math.sin(0.3 * t + k),
                                                            src[1] + 4.0 * k, ground_z(src[0], src[1]) + 10 + 7.0 * k)))

    # ── sun at its true position, sky ──
    hh, mm = (int(v) for v in args.time.split(":"))
    when = dt.datetime.fromisoformat(args.date).replace(hour=hh, minute=mm) - dt.timedelta(hours=args.utc_offset)
    sun_el, sun_az = sun_position(scene["lat0"], scene["lon0"], when)
    sun = UsdLux.DistantLight.Define(stage, "/World/sun")
    # irradiance on the ground follows the sun's elevation (air mass), the sky light less so
    sun.CreateIntensityAttr(args.sun * max(0.05, math.sin(math.radians(max(sun_el, 1.0)))) ** 0.3)
    sun.CreateAngleAttr(0.53)
    warm = max(0.0, min(1.0, (25.0 - sun_el) / 25.0))
    sun.CreateColorAttr(Gf.Vec3f(1.0, 0.95 - 0.12 * warm, 0.88 - 0.25 * warm))
    el, az = math.radians(sun_el), math.radians(sun_az)
    to_sun = Gf.Vec3d(math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))
    UsdGeom.Xformable(sun).AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(
        Gf.Rotation(Gf.Vec3d(0, 0, 1), to_sun).GetQuat())
    sky = UsdLux.DomeLight.Define(stage, "/World/sky")
    sky.CreateIntensityAttr(args.sky)
    sky.CreateColorAttr(Gf.Vec3f(0.72, 0.83, 1.0))

    # ── cloud layer (shadows only: above every camera), drifting with the wind ──
    op_cloud = None
    if args.clouds > 0:
        tex = os.path.join(args.out, "clouds.png")
        cloud_texture(tex, args.clouds)
        size = 12000.0
        cz = args.cloud_height + (prof.state(0).u if (args.traj or live) else 0.0)
        cl = mesh(stage, "/World/clouds", [(-size / 2, -size / 2, 0), (size / 2, -size / 2, 0),
                                           (size / 2, size / 2, 0), (-size / 2, size / 2, 0)],
                  [4], [0, 1, 2, 3], [(0, 0), (4, 0), (4, 4), (0, 4)])
        bind(cl.GetPrim(), preview_material(stage, "/World/Looks/cloud", color=(1, 1, 1), opacity_tex=tex))
        op_cloud = UsdGeom.Xformable(cl).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        op_cloud.Set(Gf.Vec3d(0, 0, cz))
    op_low = None
    if args.low_clouds > 0:                 # low cloud below the vehicle: hides the ground
        tex2 = os.path.join(args.out, "low_clouds.png")
        cloud_texture(tex2, args.low_clouds, seed=args.seed + 11)
        size = 12000.0
        lc = mesh(stage, "/World/low_clouds", [(-size / 2, -size / 2, 0), (size / 2, -size / 2, 0),
                                               (size / 2, size / 2, 0), (-size / 2, size / 2, 0)],
                  [4], [0, 1, 2, 3], [(0, 0), (5, 0), (5, 5), (0, 5)])
        bind(lc.GetPrim(), preview_material(stage, "/World/Looks/low_cloud", color=(0.93, 0.94, 0.96),
                                            opacity_tex=tex2, rough=1.0))
        op_low = UsdGeom.Xformable(lc).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        op_low.Set(Gf.Vec3d(0, 0, args.low_cloud_agl))
    wd = math.radians(wind_dir + 180.0)                         # the clouds move downwind
    cloud_v = (wind_spd * 1.5 * math.sin(wd), wind_spd * 1.5 * math.cos(wd))   # wind aloft ~1.5x

    # ── the vehicle and NAVERA's nadir camera (with its mounting error) ──
    veh = UsdGeom.Xform.Define(stage, "/World/vehicle")
    vx = UsdGeom.Xformable(veh)
    op_t = vx.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
    op_q = vx.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
    build_vehicle(stage, vehicle)

    from isaacsim.sensors.experimental.rtx import CameraSensor, RtxCamera
    mr, mp, my = (float(v) for v in args.mount_err.split(","))
    # USD camera (looks along -Z, image up +Y) in the body: image up = nose -> -90 deg about z;
    # the mount error is a small body-frame rotation applied before (roll x, pitch y, yaw z)
    r_mount = (Gf.Rotation(Gf.Vec3d(0, 0, 1), my) * Gf.Rotation(Gf.Vec3d(0, 1, 0), -mp)
               * Gf.Rotation(Gf.Vec3d(1, 0, 0), mr))
    r_cam = Gf.Rotation(Gf.Vec3d(0, 0, 1), -90.0) * r_mount
    q = r_cam.GetQuat()
    cam_parent = "/World/vehicle"
    if args.gimbal:                         # stabilised camera: level, turned only with the heading
        gim = UsdGeom.Xform.Define(stage, "/World/gimbal")
        op_gt = UsdGeom.Xformable(gim).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        op_gq = UsdGeom.Xformable(gim).AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
        cam_parent = "/World/gimbal"
    shk = UsdGeom.Xform.Define(stage, cam_parent + "/shake")
    op_shake = UsdGeom.Xformable(shk).AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
    cam_parent += "/shake"
    cam = RtxCamera(cam_parent + "/navera_cam", translations=np.array([0.0, 0.0, -0.3]),
                    orientations=np.array([q.GetReal(), *q.GetImaginary()]))
    ucam = UsdGeom.Camera(cam.prims[0])
    hap = 20.955
    ucam.GetHorizontalApertureAttr().Set(hap)
    ucam.GetVerticalApertureAttr().Set(hap * args.height_px / args.width)
    ucam.GetFocalLengthAttr().Set(hap / (2 * math.tan(math.radians(args.render_hfov) / 2)))
    ucam.GetClippingRangeAttr().Set(Gf.Vec2f(5.0, 30000.0))
    sensor = CameraSensor(cam, resolution=(args.height_px, args.width), annotators=["rgb"])

    chase = UsdGeom.Camera.Define(stage, "/World/chase")
    chase.CreateFocalLengthAttr(24.0)
    chase.CreateHorizontalApertureAttr(20.955)
    chase.CreateVerticalApertureAttr(20.955 * 9 / 16)
    chase.CreateClippingRangeAttr(Gf.Vec2f(1.0, 30000.0))
    op_chase = UsdGeom.Xformable(chase).AddTransformOp()
    import omni.replicator.core as rep
    rp = rep.create.render_product("/World/chase", (960, 540))
    vid = rep.AnnotatorRegistry.get_annotator("rgb")
    vid.attach([rp])
    try:
        from omni.kit.viewport.utility import get_active_viewport
        get_active_viewport().camera_path = "/World/chase"
    except Exception as e:      # noqa: BLE001
        carb.log_warn(f"viewport camera not set: {e}")
    set_title()

    chase_eye = [None]

    def pose(t):
        s_ = prof.state(t)
        op_t.Set(Gf.Vec3d(s_.e, s_.n, s_.u))
        op_q.Set(quat_wxyz(s_.quat_enu()))
        if args.gimbal:
            op_gt.Set(Gf.Vec3d(s_.e, s_.n, s_.u))
            op_gq.Set(quat_wxyz(rpy_to_quat(0.0, 0.0, s_.yaw)))
        if op_cloud is not None:
            op_cloud.Set(Gf.Vec3d(cloud_v[0] * t, cloud_v[1] * t, op_cloud.Get()[2]))
        if op_low is not None:
            op_low.Set(Gf.Vec3d(cloud_v[0] * t / 1.5, cloud_v[1] * t / 1.5, args.low_cloud_agl))
        if args.shake > 0:                  # engine / airframe vibration: random jitter of the camera
            j = rnd.normal(0.0, args.shake, 3)
            op_shake.Set(quat_wxyz(rpy_to_quat(j[0], j[1], j[2])))
        for m_ in movers:
            if m_[0] == "rel":
                m_[1].Set(Gf.Vec3d(*m_[2](t, s_)))
            else:
                m_[0].Set(Gf.Vec3d(*m_[1](t)))
        # chase: 38 m behind along the track, 11 m above, smoothed, looking at the vehicle
        v = math.hypot(s_.ve, s_.vn) or 1.0
        want = Gf.Vec3d(s_.e - 38 * s_.ve / v, s_.n - 38 * s_.vn / v, s_.u + 11)
        e = chase_eye[0] = want if chase_eye[0] is None else chase_eye[0] + (want - chase_eye[0]) * 0.15
        view = Gf.Matrix4d().SetLookAt(e, Gf.Vec3d(s_.e, s_.n, s_.u - 6), Gf.Vec3d(0, 0, 1))
        op_chase.Set(view.GetInverse())

    omni.timeline.get_timeline_interface().play()
    pose(0.0 if not live else live.latest_t())
    for k in range(120):                    # shaders, textures, exposure settle
        if live:
            live.poll()
            pose(live.latest_t())
        app.update()
        if k in (5, 60, 119):
            bring_to_front()

    t0 = time.time() if not live else float(live.last["t0"])
    session = dict(t0_wall=t0, lat0=scene["lat0"], lon0=scene["lon0"], z_ref_m=z_ref, vehicle=vehicle,
                   traj=os.path.basename(args.traj) if args.traj else None,
                   live_udp=args.pose_udp or None,
                   profile=None if args.traj else dict(radius_m=args.radius, speed_mps=args.speed,
                                                       height_m=args.height),
                   duration_s=duration,
                   render=dict(hfov_deg=args.render_hfov, width=args.width, height=args.height_px, fps=args.fps,
                               mount="nadir, image top = nose" + (", 2-axis gimbal (level)" if args.gimbal else ""),
                               gimbal=bool(args.gimbal), mount_err_rpy_deg=[mr, mp, my]),
                   sun=dict(date=args.date, local_time=args.time, utc_offset_h=args.utc_offset,
                            elev_deg=round(sun_el, 2), az_deg=round(sun_az, 2)),
                   clouds=dict(cover=args.clouds, height_m=args.cloud_height, drift_mps=list(cloud_v),
                               low_cover=args.low_clouds, low_agl_m=args.low_cloud_agl),
                   obstacles=args.obstacles, extra_buildings=args.extra_buildings, shake_deg=args.shake,
                   sun_intensity=args.sun, sky_intensity=args.sky,
                   wind=dict(speed_mps=wind_spd, from_deg=wind_dir), scene=scene,
                   renderer="Isaac Sim 6.0 RTX (real-time)", frame_lag_updates=1)
    json.dump(session, open(os.path.join(args.out, "session.json"), "w"), indent=1)
    meta = open(os.path.join(args.out, "frames.jsonl"), "a")
    from concurrent.futures import ThreadPoolExecutor
    writer = ThreadPoolExecutor(1)          # one thread: frames written in order, off the render loop

    def save_frame(rgb, i, t, ps):
        name = f"f_{i:06d}.jpg"
        tmp = os.path.join(args.out, "frames", name + ".tmp")
        with open(tmp, "wb") as fh:          # written whole, then renamed: never read half
            fh.write(cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())
        os.replace(tmp, os.path.join(args.out, "frames", name))
        lat, lon = geo.to_latlon(ps.e, ps.n)
        meta.write(json.dumps(dict(i=i, t=round(t, 4), file=name, lat=lat, lon=lon, z=round(ps.u, 2),
                                   roll=round(ps.roll, 2), pitch=round(ps.pitch, 2),
                                   heading=round(ps.heading, 2))) + "\n")
        meta.flush()
    n_frame = n_vid = 0
    next_cap, next_vid = 0.0, 0.0
    prev_t = None
    upd = []
    while app.is_running():
        if live:
            live.poll()
            if live.last.get("done"):
                break
            t = live.latest_t()
        else:
            t = time.time() - t0
        if t > duration:
            break
        pose(t)
        u0 = time.time()
        app.update()
        upd.append(time.time() - u0)
        if prev_t is not None:
            if prev_t >= next_cap:
                data, _ = sensor.get_data("rgb")
                if data is not None:
                    ps = prof.state(prev_t)
                    writer.submit(save_frame, data.numpy()[:, :, :3].copy(), n_frame, prev_t, ps)
                    n_frame += 1
                    next_cap = max(next_cap + 1.0 / args.fps, prev_t)
            if prev_t >= next_vid:
                v = vid.get_data()
                if v is not None and getattr(v, "size", 0):
                    cv2.imwrite(os.path.join(args.out, "video", f"v_{n_vid:06d}.jpg"),
                                cv2.cvtColor(np.asarray(v)[:, :, :3], cv2.COLOR_RGB2BGR),
                                [cv2.IMWRITE_JPEG_QUALITY, 85])
                    n_vid += 1
                    next_vid = max(next_vid + 1.0 / args.video_fps, prev_t)
        prev_t = t
    writer.shutdown(wait=True)
    upd.sort()
    json.dump(dict(frames=n_frame, video_frames=n_vid, updates=len(upd),
                   update_ms_median=round(1000 * upd[len(upd) // 2], 1) if upd else None,
                   update_ms_p95=round(1000 * upd[int(len(upd) * 0.95)], 1) if upd else None),
              open(os.path.join(args.out, "done.json"), "w"), indent=1)
    t_end = time.time()
    while app.is_running() and time.time() - t_end < args.linger \
            and not (args.stop_file and os.path.exists(args.stop_file)):  # the user keeps watching a moment
        if live:
            live.poll()
            pose(live.latest_t())
        else:
            pose(duration + (time.time() - t_end))
        app.update()


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    with open(os.path.join(args.out, "error.txt"), "w") as f:
        f.write(traceback.format_exc())
sys.stdout.flush()
os._exit(0)                               # SimulationApp.close() can hang on this PC
