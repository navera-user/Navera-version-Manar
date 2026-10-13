"""Synthetic downward camera views of Sousse from OpenStreetMap data (NAVERA Academy).

    import sys; sys.path.insert(0, '<repo>/datasets/_map')
    from render_view import render_view
    img = render_view(35.8277, 10.6388, heading_deg=30, alt_m=300, out_px=512, seed=1,
                      style='pseudo', effects='medium')          # numpy BGR uint8
    img, meta = render_view(..., return_meta=True)               # + true pose, corner lat/lon, homography

style='map'    : the cartographic style of osm_sousse.mbtiles (same Mapnik XML, same per-zoom rules)
style='pseudo' : "pseudo-satellite": procedural textures per land class, fixed in world coordinates
                 (the same place looks the same in every view, whatever the seed), roof colour per
                 building from its OSM id, offset shadows, tree crowns, sea texture, and a synthetic
                 urban fabric inside residential/commercial/industrial areas where OSM has no buildings
                 (Sousse OSM has ~10k buildings only). It is NOT imagery: it is a deterministic drawing.

Camera: pinhole, square pixels, horizontal FOV `fov_deg` (default 60). Give either alt_m (height above
ground) or ground_size_m (width of the nadir footprint); default alt 300 m. heading_deg = direction of
the image top, clockwise from north (0 = north up).

effects: None | 'light' | 'medium' | 'strong' (random parameters drawn from `seed`) | dict. Dict keys:
    pitch_deg, roll_deg   camera tilt (perspective)               yaw_err_deg  heading error
    scale_err             relative altitude error (+0.1 = 10 % higher than nominal)
    blur                  gaussian sigma px                        motion_blur  kernel length px
    noise                 gaussian sensor noise sigma (0-255)      gamma        e.g. 0.8 .. 1.25
    color                 per-channel gain jitter amplitude (0.05) brightness   gain (1 = none)
    illum                 illumination gradient strength (0..0.5)  vignette     0..0.6
    jpeg                  JPEG quality (e.g. 40)                   clouds       coverage 0..1
    occlusion             number of dark occluding blobs at the image border (props, gear, dirt)
Unknown keys raise. With a preset, the drawn values are returned in meta['effects'].

Needs: numpy (system 1.x), opencv (cv2) and the private pylib with mapnik (~/osmrender/pylib, or env
NAVERA_OSM_PYLIB). The pylib is put on sys.path and PROJ_DATA is set automatically on first use.
Data: env NAVERA_OSM_DB or ~/academy-data/osm/sousse_osm.sqlite (made by make_map.py convert).
"""
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PYLIB = os.path.expanduser(os.environ.get('NAVERA_OSM_PYLIB', '~/osmrender/pylib'))
DB = os.path.expanduser(os.environ.get('NAVERA_OSM_DB', '~/academy-data/osm/sousse_osm.sqlite'))
R = 6378137.0
LAT_REF = 35.83                          # texture world frame: mercator metres * cos(LAT_REF) ~ metres
COS_REF = math.cos(math.radians(LAT_REF))
SUN_SHADOW = (-0.62, 0.78)               # unit ENU direction shadows fall to (sun in the south-east)
MAX_ORTHO = 3600                         # px, cap of the intermediate orthophoto side

_MAPS = {}


def _mapnik():
    if PYLIB not in sys.path and os.path.isdir(PYLIB):
        sys.path.insert(0, PYLIB)
    os.environ.setdefault('PROJ_DATA', os.path.join(PYLIB, 'mapnik', 'share', 'proj'))
    import mapnik
    return mapnik


def _get_map(name):
    if name not in _MAPS:
        mapnik = _mapnik()
        xml = open(os.path.join(HERE, name)).read().replace('@DB@', DB)
        m = mapnik.Map(256, 256)
        mapnik.load_map_from_string(m, xml, False, HERE + '/')
        _MAPS[name] = m
    return _MAPS[name]


def _render(name, box_merc, w, h):
    """Render a Mapnik style over a mercator box; returns RGBA uint8 (straight alpha)."""
    mapnik = _mapnik()
    m = _get_map(name)
    m.resize(w, h)
    m.zoom_to_box(mapnik.Box2d(*box_merc))
    im = mapnik.Image(w, h)
    mapnik.render(m, im)
    im.demultiply()
    return np.frombuffer(im.to_string(), np.uint8).reshape(h, w, 4).copy()


def latlon_to_merc(lat, lon):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def merc_to_latlon(x, y):
    return math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2), math.degrees(x / R)


# ----------------------------------------------------------------------------- procedural noise
def _hash(ix, iy, k):
    """Deterministic integer lattice hash -> float in [0,1). ix, iy int64 arrays."""
    h = (ix.astype(np.uint64) * np.uint64(0x9E3779B1) ^ iy.astype(np.uint64) * np.uint64(0x85EBCA77)
         ^ np.uint64((k * 0xC2B2AE3D) & 0xFFFFFFFF))
    h ^= h >> np.uint64(15)
    h *= np.uint64(0x2C1B3C6D)
    h ^= h >> np.uint64(12)
    h *= np.uint64(0x297A2D39)
    h ^= h >> np.uint64(15)
    return (h & np.uint64(0xFFFFFF)).astype(np.float32) / np.float32(0x1000000)


def _vnoise(wx, wy, cell, k):
    """Value noise (smooth) on a lattice of `cell` metres, in [0,1)."""
    x = wx / cell
    y = wy / cell
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    fx = (x - ix).astype(np.float32)
    fy = (y - iy).astype(np.float32)
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = _hash(ix, iy, k)
    b = _hash(ix + 1, iy, k)
    c = _hash(ix, iy + 1, k)
    d = _hash(ix + 1, iy + 1, k)
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy


def _fbm(wx, wy, cell, k, res, octaves=4):
    """Fractal noise in [-1,1]; octaves finer than ~1.5 px are dropped (no aliasing)."""
    s = np.zeros(wx.shape, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        c = cell / 2 ** o
        if c < 1.5 * res:
            break
        s += amp * (_vnoise(wx, wy, c, k + 101 * o) * 2 - 1)
        tot += amp
        amp *= 0.5
    return s / tot if tot else s


# ----------------------------------------------------------------------------- pseudo-satellite
# RGB base colours of the ground classes
BASE = {
    'land': (186, 168, 138), 'sea': (38, 92, 118), 'water': (52, 88, 92), 'saltpond': (205, 205, 196),
    'residential': (178, 166, 148), 'commercial': (168, 164, 160), 'industrial': (165, 160, 152),
    'construction': (192, 176, 150), 'farmland': (170, 150, 112), 'farmyard': (172, 160, 136),
    'orchard': (182, 163, 128), 'grass': (128, 140, 92), 'park': (104, 128, 80), 'wood': (70, 92, 58),
    'scrub': (140, 138, 102), 'sand': (222, 208, 176), 'bare': (196, 182, 160), 'wetland': (150, 152, 130),
    'cemetery': (190, 182, 166), 'military': (176, 164, 140), 'institution': (184, 176, 160),
    'hospital': (186, 180, 168), 'parking': (128, 128, 126), 'pitch': (88, 132, 82), 'stadium': (150, 150, 140),
    'golf': (96, 136, 76), 'aerodrome': (170, 160, 128), 'pedestrian': (196, 188, 174), 'pier': (176, 172, 164),
    'runway': (92, 94, 96),
}
FABRIC = {'residential': (13.0, 0.80), 'commercial': (24.0, 0.70), 'industrial': (34.0, 0.65),
          'institution': (22.0, 0.35), 'hospital': (22.0, 0.45), 'military': (30.0, 0.25),
          'farmyard': (20.0, 0.25)}            # cell metres, built fraction
ROOFS = np.array([(236, 233, 224), (222, 214, 198), (205, 196, 182), (188, 186, 182), (214, 200, 170),
                  (170, 100, 78), (150, 150, 150), (176, 196, 200), (242, 242, 238)], np.float32)
ROOF_CDF = np.cumsum([0.30, 0.18, 0.14, 0.12, 0.08, 0.06, 0.05, 0.04, 0.03])   # same weights as osmdata.roof_colours


def _classify(rgba, classes, code_rgb):
    rgb = rgba[..., :3].astype(np.int32)
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    uniq, inv = np.unique(key.ravel(), return_inverse=True)
    u = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], 1).astype(np.float32)
    d = ((u[:, None, :] - code_rgb[None, :, :]) ** 2).sum(2)
    return np.argmin(d, 1)[inv].reshape(key.shape)


def _pseudo(box_merc, w, h, res):
    import style_map
    classes = style_map.PSEUDO_CLASSES
    codes = np.array([[int(style_map.code_colour(i)[j:j + 2], 16) for j in (1, 3, 5)]
                      for i in range(len(classes))], np.float32)
    cls = _classify(_render('style_pseudo_ground.xml', box_merc, w, h), classes, codes)
    # world coordinates (metres, fixed frame) of each pixel
    resm = (box_merc[2] - box_merc[0]) / w
    xs = (box_merc[0] + (np.arange(w) + 0.5) * resm) * COS_REF
    ys = (box_merc[3] - (np.arange(h) + 0.5) * resm) * COS_REF
    wx, wy = np.meshgrid(xs, ys)
    wx = wx.astype(np.float64)
    wy = wy.astype(np.float64)
    n_lo = _fbm(wx, wy, 180.0, 11, res, 3)
    n_mid = _fbm(wx, wy, 24.0, 12, res, 3)
    n_hi = _fbm(wx, wy, 4.0, 13, res, 3)
    img = np.zeros((h, w, 3), np.float32)
    for i, k in enumerate(classes):
        m = cls == i
        if not m.any():
            continue
        img[m] = BASE.get(k, BASE['land'])
    lum = 1 + 0.10 * n_lo + 0.07 * n_mid + 0.06 * n_hi
    tint = np.stack([1 + 0.04 * n_mid, 1 + 0.02 * n_lo, 1 - 0.04 * n_mid], -1)
    img *= lum[..., None] * tint
    C = {k: classes.index(k) for k in classes}
    shade = np.zeros((h, w), np.float32)          # objects that cast shadows (roof/tree height mask)
    top = np.zeros((h, w, 3), np.float32)
    topm = np.zeros((h, w), np.float32)
    # sea and water: waves + depth tint
    for k in ('sea', 'water'):
        m = cls == C[k]
        if m.any():
            wave = np.sin((wx[m] * 0.8 + wy[m] * 0.6) / 3.0 + 3 * n_mid[m]) * 0.04 + 0.08 * n_hi[m]
            img[m] = np.array(BASE[k], np.float32) * (1 + 0.15 * n_lo[m] + wave)[:, None]
    # untagged land (most of the rural Sahel): procedural parcels (~110 m, warped borders) of bare soil,
    # ploughed strips, olive groves (planted 9 m grid) or green crops
    m = cls == C['land']
    olive_land = np.zeros((h, w), bool)
    if m.any():
        px_ = np.floor((wx[m] + 45 * n_lo[m]) / 110).astype(np.int64)
        py_ = np.floor((wy[m] + 45 * n_mid[m] * 0.5 + 30 * n_lo[m]) / 95).astype(np.int64)
        ptype = _hash(px_, py_, 23)
        tone = (0.88 + 0.24 * _hash(px_, py_, 24))[:, None]
        base = np.array(BASE['land'], np.float32) * tone
        ang = _hash(px_, py_, 25) * np.pi
        t = wx[m] * np.cos(ang) + wy[m] * np.sin(ang)
        plough = (ptype >= 0.35) & (ptype < 0.55)
        stripe = np.where(plough, np.sin(t / 1.8) * 0.07, 0) if res < 1.2 else 0
        crop = ptype >= 0.92
        base = np.where(crop[:, None], np.array([128, 140, 88], np.float32) * tone, base)
        img[m] = base * (1 + stripe + 0.06 * n_mid[m] + 0.05 * n_hi[m])[:, None]
        olive = (ptype >= 0.55) & (ptype < 0.92)
        idx = np.nonzero(m)
        olive_land[idx[0][olive], idx[1][olive]] = True
    # farmland: field strips, orientation per ~150 m block
    m = cls == C['farmland']
    if m.any():
        ang = _hash(np.floor(wx[m] / 150).astype(np.int64), np.floor(wy[m] / 150).astype(np.int64), 21) * np.pi
        t = wx[m] * np.cos(ang) + wy[m] * np.sin(ang)
        stripe = np.sin(t / 2.5) * 0.06 if res < 1.5 else 0
        green = _hash(np.floor(wx[m] / 150).astype(np.int64), np.floor(wy[m] / 150).astype(np.int64), 22)
        base = np.where(green[:, None] > 0.6, np.array([120, 132, 84], np.float32), np.array(BASE['farmland'], np.float32))
        img[m] = base * (1 + stripe + 0.08 * n_mid[m])[:, None]
    # trees: orchards (olive grid ~7 m), woods/parks (dense random crowns), scattered shrubs on land
    for k, spacing, radius, keep in (('orchard', 7.0, 2.3, 0.92), ('wood', 4.5, 2.4, 0.95), ('park', 9.0, 3.0, 0.55),
                                     ('golf', 25.0, 3.5, 0.4), ('cemetery', 12.0, 2.0, 0.3), ('land', 22.0, 1.8, 0.08),
                                     ('olive_land', 9.0, 2.6, 0.9),
                                     ('scrub', 6.0, 1.6, 0.6), ('residential', 30.0, 2.5, 0.18), ('grass', 18.0, 2.2, 0.25)):
        m = olive_land if k == 'olive_land' else cls == C[k]
        if not m.any() or radius < 0.6 * res:
            continue
        gx = np.floor(wx[m] / spacing).astype(np.int64)
        gy = np.floor(wy[m] / spacing).astype(np.int64)
        jit = 0.5 if k in ('orchard', 'olive_land') else 1.6
        cx = (gx + 0.5 + (_hash(gx, gy, 31) - 0.5) * 0.3 * jit) * spacing
        cy = (gy + 0.5 + (_hash(gx, gy, 32) - 0.5) * 0.3 * jit) * spacing
        rr = radius * (0.75 + 0.5 * _hash(gx, gy, 33))
        present = _hash(gx, gy, 34) < keep
        d = np.hypot(wx[m] - cx, wy[m] - cy) / rr
        a = np.clip((1 - d) * rr / max(res, 0.3), 0, 1) * present
        if not a.any():
            continue
        tree = np.array([62, 84, 50], np.float32) * (0.85 + 0.3 * _hash(gx, gy, 35))[:, None]
        tree = tree * (1 + 0.25 * (1 - d.clip(0, 1)))[:, None]          # lit crown centre
        idx = np.nonzero(m)
        top[idx] = top[idx] * (1 - a[:, None]) + tree * a[:, None]
        topm[idx] = np.maximum(topm[idx], a)
        shade[idx] = np.maximum(shade[idx], a * 0.8)
    # synthetic urban fabric (roof cells) where OSM buildings are missing
    for k, (cell, frac) in FABRIC.items():
        m = cls == C[k]
        if not m.any():
            continue
        # each ~160 m block gets its own street-grid orientation; cells of `cell` metres split into
        # 1-3 roofs along u, with a 0.7-1.2 m gap (alleys, walls between houses)
        bx = np.floor(wx[m] / 160).astype(np.int64)
        by = np.floor(wy[m] / 160).astype(np.int64)
        ang = _hash(bx, by, 40) * (np.pi / 2)
        u = wx[m] * np.cos(ang) + wy[m] * np.sin(ang)
        v = -wx[m] * np.sin(ang) + wy[m] * np.cos(ang)
        cv_ = cell * (0.8 + 0.5 * _hash(bx, by, 45))
        gy = np.floor(v / cv_).astype(np.int64)
        fy = v / cv_ - gy
        cu = cv_ * (0.6 + 0.8 * _hash(gy, by, 46))              # row-dependent house width
        gx = np.floor(u / cu).astype(np.int64)
        fx = u / cu - gx
        gxs, fxs = gx, fx
        gap = (0.7 + 0.5 * _hash(gx, gy, 41)) / cv_
        gapu = gap * cv_ / cu
        inside = (fxs > gapu) & (fxs < 1 - gapu) & (fy > gap) & (fy < 1 - gap)
        present = _hash(gxs, gy, 42) < frac * (0.85 + 0.3 * (n_lo[m] + 1) / 2)
        a = (inside & present).astype(np.float32)
        if not a.any():
            continue
        ri = np.searchsorted(ROOF_CDF, _hash(gxs, gy, 43)).clip(0, len(ROOFS) - 1)
        col = ROOFS[ri] * (0.9 + 0.2 * _hash(gxs, gy, 44))[:, None]
        if k in ('industrial', 'commercial'):
            col = col * 0.5 + np.array([160, 162, 165], np.float32) * 0.5
        idx = np.nonzero(m)
        top[idx] = top[idx] * (1 - a[:, None]) + col * a[:, None]
        topm[idx] = np.maximum(topm[idx], a)
        shade[idx] = np.maximum(shade[idx], a)
    # roads/rail (asphalt with noise), drawn above ground but below roofs/trees
    rd = _render('style_pseudo_top.xml', box_merc, w, h).astype(np.float32)
    ra = rd[..., 3:] / 255.0
    asphalt = rd[..., :3] * (1 + 0.06 * n_hi + 0.05 * n_mid)[..., None]
    img = img * (1 - ra) + asphalt * ra
    roads_a = ra[..., 0]
    top_keep = topm * (1 - roads_a)                    # roads cut through synthetic fabric/trees
    shade *= (1 - roads_a)
    # OSM buildings: roof colour per OSM id + texture
    bd = _render('style_pseudo_bld.xml', box_merc, w, h).astype(np.float32)
    ba = bd[..., 3] / 255.0
    roof = bd[..., :3] * (1 + 0.05 * n_hi)[..., None]
    shade = np.maximum(shade, ba)
    # shadows: shift object masks along the sun direction (in pixels, world-fixed direction)
    for mask_len_m, strength in ((4.5, 0.45),):
        L = mask_len_m / res
        M = np.float32([[1, 0, SUN_SHADOW[0] * L], [0, 1, -SUN_SHADOW[1] * L]])
        sh = cv2.warpAffine(shade, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        sh = cv2.GaussianBlur(sh, (0, 0), max(0.6, 0.6 / res))
        img *= (1 - strength * sh)[..., None]
    img = img * (1 - top_keep[..., None]) + top * top_keep[..., None]
    img = img * (1 - ba[..., None]) + roof * ba[..., None]
    rgb = np.clip(img, 0, 255).astype(np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ----------------------------------------------------------------------------- camera
def _camera(heading, pitch, roll, alt, f, cx, cy):
    """Homography ENU ground (E, N, 1) -> image pixels, plus camera rotation."""
    ps = math.radians(heading)
    z = np.array([0.0, 0.0, -1.0])
    yv = np.array([-math.sin(ps), -math.cos(ps), 0.0])      # image down = opposite of heading
    xv = np.cross(yv, z)
    Rwc = np.stack([xv, yv, z], 1)                          # columns: camera axes in world
    def rot(axis, a):
        a = math.radians(a)
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K
    # pitch: nose up (top of image looks further ahead); roll: right side down
    Rwc = rot(Rwc[:, 0], pitch) @ Rwc
    Rwc = rot(Rwc[:, 1], -roll) @ Rwc
    Rcw = Rwc.T
    C = np.array([0.0, 0.0, alt])
    t = -Rcw @ C
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    H = K @ np.stack([Rcw[:, 0], Rcw[:, 1], t], 1)
    return H / H[2, 2], Rwc


PRESETS = {
    'light': dict(tilt=3, yaw=2, scale=0.03, blur=(0, 0.8), motion=0, noise=(1, 3), gamma=0.08, color=0.03,
                  bright=0.08, illum=0.1, vignette=0.15, jpeg=(80, 95), clouds=0.0, occl=0),
    'medium': dict(tilt=8, yaw=5, scale=0.08, blur=(0.3, 1.5), motion=5, noise=(2, 6), gamma=0.15, color=0.06,
                   bright=0.15, illum=0.25, vignette=0.3, jpeg=(55, 90), clouds=0.25, occl=1),
    'strong': dict(tilt=15, yaw=12, scale=0.15, blur=(0.8, 2.5), motion=9, noise=(4, 12), gamma=0.25, color=0.1,
                   bright=0.25, illum=0.4, vignette=0.5, jpeg=(30, 70), clouds=0.5, occl=2),
}
EFFECT_KEYS = {'pitch_deg', 'roll_deg', 'yaw_err_deg', 'scale_err', 'blur', 'motion_blur', 'noise', 'gamma',
               'color', 'brightness', 'illum', 'vignette', 'jpeg', 'clouds', 'occlusion'}


def _draw_effects(name, rng):
    p = PRESETS[name]
    u = rng.uniform
    e = {'pitch_deg': u(-p['tilt'], p['tilt']), 'roll_deg': u(-p['tilt'], p['tilt']),
         'yaw_err_deg': u(-p['yaw'], p['yaw']), 'scale_err': u(-p['scale'], p['scale']),
         'blur': u(*p['blur']), 'noise': u(*p['noise']), 'gamma': float(np.exp(u(-p['gamma'], p['gamma']))),
         'color': p['color'], 'brightness': 1 + u(-p['bright'], p['bright']), 'illum': u(0, p['illum']),
         'vignette': u(0, p['vignette']), 'jpeg': int(u(*p['jpeg']))}
    if p['motion'] and rng.random() < 0.4:
        e['motion_blur'] = int(rng.integers(3, p['motion'] + 1))
    if p['clouds'] and rng.random() < 0.5:
        e['clouds'] = u(0.05, p['clouds'])
    if p['occl'] and rng.random() < 0.35:
        e['occlusion'] = int(rng.integers(1, p['occl'] + 1))
    return e


def _apply_photometric(img, e, rng):
    h, w = img.shape[:2]
    x = img.astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xn, yn = (xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)
    if e.get('clouds'):
        cov = e['clouds']
        off = rng.uniform(0, 1e4, 2)
        n = _fbm(xx.astype(np.float64) + off[0], yy.astype(np.float64) + off[1], w * 0.6, int(rng.integers(1e6)), 1.0, 5)
        a = np.clip((n - (1 - 2 * cov) * 0.6) / 0.35, 0, 1) ** 1.5
        sh = np.roll(np.roll(a, int(0.06 * w), 1), int(0.05 * h), 0)
        x = x * (1 - 0.35 * sh[..., None])
        x = x * (1 - a[..., None]) + np.float32(0.93) * a[..., None]
    if e.get('occlusion'):
        occ = np.zeros((h, w), np.float32)
        for _ in range(int(e['occlusion'])):
            side = rng.integers(4)
            cx = [rng.uniform(0, w), w, rng.uniform(0, w), 0][side]
            cy = [0, rng.uniform(0, h), h, rng.uniform(0, h)][side]
            ax = int(rng.uniform(0.1, 0.3) * w)
            ay = int(rng.uniform(0.05, 0.2) * h)
            cv2.ellipse(occ, (int(cx), int(cy)), (ax, ay), rng.uniform(0, 180), 0, 360, 1.0, -1, cv2.LINE_AA)
        occ = cv2.GaussianBlur(occ, (0, 0), 0.01 * w + 1)
        x = x * (1 - occ[..., None]) + np.float32(0.08) * occ[..., None]
    if e.get('illum'):
        ang = rng.uniform(0, 2 * np.pi)
        g = 1 + e['illum'] * (np.cos(ang) * xn + np.sin(ang) * yn) / 2
        x = x * g[..., None]
    if e.get('color'):
        x = x * (1 + rng.uniform(-e['color'], e['color'], 3)).astype(np.float32)
    if e.get('brightness'):
        x = x * e['brightness']
    if e.get('vignette'):
        x = x * (1 - e['vignette'] * np.clip(xn ** 2 + yn ** 2, 0, 2) / 2)[..., None]
    if e.get('gamma'):
        x = np.clip(x, 0, 1) ** (1.0 / e['gamma'])
    x = np.clip(x * 255, 0, 255)
    if e.get('motion_blur'):
        L = int(e['motion_blur'])
        k = np.zeros((L, L), np.float32)
        k[L // 2, :] = 1.0 / L
        M = cv2.getRotationMatrix2D(((L - 1) / 2, (L - 1) / 2), rng.uniform(0, 180), 1)
        k = cv2.warpAffine(k, M, (L, L))
        x = cv2.filter2D(x, -1, k / max(k.sum(), 1e-6))
    if e.get('blur'):
        x = cv2.GaussianBlur(x, (0, 0), e['blur'])
    if e.get('noise'):
        x = x + rng.normal(0, e['noise'], x.shape).astype(np.float32) * np.sqrt(np.clip(x, 8, 255) / 128.0)
    out = np.clip(x, 0, 255).astype(np.uint8)
    if e.get('jpeg'):
        ok, buf = cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, int(e['jpeg'])])
        out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


def render_view(lat, lon, heading_deg=0.0, alt_m=None, ground_size_m=None, out_px=512, seed=0,
                style='pseudo', effects=None, fov_deg=60.0, return_meta=False):
    """Synthetic downward camera image (numpy BGR uint8) centred on (lat, lon). See module doc."""
    if style not in ('pseudo', 'map'):
        raise ValueError("style must be 'pseudo' or 'map'")
    W, H = (out_px, out_px) if np.isscalar(out_px) else (int(out_px[0]), int(out_px[1]))
    rng = np.random.default_rng(seed)
    if effects is None:
        e = {}
    elif isinstance(effects, str):
        e = _draw_effects(effects, rng)
    else:
        bad = set(effects) - EFFECT_KEYS
        if bad:
            raise ValueError(f'unknown effects {sorted(bad)}')
        e = dict(effects)
    th = math.radians(fov_deg) / 2
    if alt_m is None:
        alt_m = ground_size_m / (2 * math.tan(th)) if ground_size_m else 300.0
    nominal_ground = 2 * alt_m * math.tan(th)
    alt_true = alt_m * (1 + e.get('scale_err', 0.0))
    head_true = heading_deg + e.get('yaw_err_deg', 0.0)
    pitch, roll = e.get('pitch_deg', 0.0), e.get('roll_deg', 0.0)
    if math.radians(abs(pitch)) + th > math.radians(75) or math.radians(abs(roll)) + th > math.radians(75):
        raise ValueError('tilt too large: the view would reach the horizon')
    f = (W / 2) / math.tan(th)
    Hg, Rwc = _camera(head_true, pitch, roll, alt_true, f, W / 2, H / 2)
    Hinv = np.linalg.inv(Hg)
    corners = np.array([[0, 0, 1], [W, 0, 1], [W, H, 1], [0, H, 1]], float)
    g = (Hinv @ corners.T).T
    g = g[:, :2] / g[:, 2:3]                                # ENU metres of the image corners
    res = alt_true * 2 * math.tan(th) / W                     # nadir ground sampling distance (m/px)
    pad = 6 * res + 10
    e0, e1 = g[:, 0].min() - pad, g[:, 0].max() + pad
    n0, n1 = g[:, 1].min() - pad, g[:, 1].max() + pad
    ores = max(res, max(e1 - e0, n1 - n0) / MAX_ORTHO)
    ow, oh = int(math.ceil((e1 - e0) / ores)), int(math.ceil((n1 - n0) / ores))
    mx, my = latlon_to_merc(lat, lon)
    k = 1 / math.cos(math.radians(lat))                      # mercator metres per ground metre
    box = (mx + e0 * k, my + (n1 - oh * ores) * k, mx + (e0 + ow * ores) * k, my + n1 * k)
    if style == 'map':
        rgba = _render('style_map.xml', box, ow, oh)
        ortho = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2BGR)
    else:
        ortho = _pseudo(box, ow, oh, ores)
    # image pixel -> ortho pixel: A (ENU -> ortho px) @ Hinv
    A = np.array([[1 / ores, 0, -e0 / ores], [0, -1 / ores, n1 / ores], [0, 0, 1]])
    M = A @ Hinv
    img = cv2.warpPerspective(ortho, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)
    img = _apply_photometric(img, e, rng) if e else img
    if not return_meta:
        return img
    corners_ll = [merc_to_latlon(mx + E * k, my + N * k) for E, N in g]
    meta = {'lat': lat, 'lon': lon, 'heading_deg': heading_deg, 'heading_true_deg': head_true,
            'alt_m': alt_m, 'alt_true_m': alt_true, 'fov_deg': fov_deg, 'focal_px': f,
            'ground_size_m': nominal_ground, 'gsd_m': res, 'pitch_deg': pitch, 'roll_deg': roll,
            'style': style, 'effects': e, 'seed': seed,
            'H_enu_to_px': Hg.tolist(),                       # (E, N, 1) metres from (lat, lon) -> pixel
            'corners_latlon': corners_ll,                     # TL, TR, BR, BL
            'attribution': '© OpenStreetMap contributors'}
    return img, meta


def _demo(outdir):
    os.makedirs(outdir, exist_ok=True)
    ribat = (35.8277, 10.6388)
    jobs = [('pseudo', 'none', None, 300), ('map', 'none', None, 300), ('pseudo', 'medium', 'medium', 300),
            ('pseudo', 'strong', 'strong', 300), ('map', 'medium', 'medium', 300), ('pseudo', 'none', None, 120),
            ('pseudo', 'none', None, 1200)]
    for style, tag, eff, alt in jobs:
        img, meta = render_view(*ribat, heading_deg=25, alt_m=alt, out_px=640, seed=3, style=style,
                                effects=eff, return_meta=True)
        p = os.path.join(outdir, f'view_{style}_{tag}_alt{alt}.jpg')
        cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(p, {k: round(v, 2) if isinstance(v, float) else v for k, v in meta['effects'].items()})


if __name__ == '__main__':
    _demo(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/academy-data/previews'))
