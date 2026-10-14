#!/usr/bin/env python3
"""Make datasets/26-stars/ for mission 26 (teacher only — never copy this file into datasets/).

    python3 solutions/26-stars/make_dataset.py [--raw catalog.gz]      (on the host, from the repository root)

--raw: the Bright Star Catalogue file `catalog.gz` of CDS V/50 (Hoffleit & Warren 1991), downloaded from
https://cdsarc.cds.unistra.fr/ftp/V/50/catalog.gz when not given. Deterministic (seed 2626).

Writes:
    bright_stars.csv   the BSC subset: every star with a J2000 position and V ≤ 6.5 (hr, bayer, common, ra_deg,
                       dec_deg, vmag); common names added by hand for ~50 bright stars
    photos/night_01.png … night_06.png   SYNTHETIC star-camera photos (1280 × 960, 8-bit grey, 60° wide) from
                       NAVERA Lite's star camera (axis 20° from body up, towards the nose), rendered from that
                       catalogue precessed to the date (IAU 1976), GMST, an ideal pinhole, a Gaussian star image
                       (σ = 1.0 px), sky background, read noise σ 2.5, 40 hot pixels; photo 2 adds a light glow
                       and an aircraft trail
    photos.json        per photo: UTC time, the IMU chip's attitude (MAGNETIC north, with BNO085-class errors
                       0.3° roll, 0.3° pitch, 1.5° heading), the camera K and mount, the prior, and the truth
                       (true position and true attitude: the lab measures errors against it)
    photo01_stars.csv  where every catalogue star of photo 1 (V ≤ 6.5) really is, to the 1/1000 pixel
    README.md          neutral description and the catalogue's source and licence

The answers that depend on these files are recomputed by solutions/26-stars/make_expected.py.
"""
import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
import urllib.request

import cv2
import numpy as np
from pygeomag import GeoMag

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "datasets", "26-stars")
sys.path.insert(0, os.path.join(ROOT, "solutions", "_navera_lite"))
from navera_lite import stars as S                       # noqa: E402  (the course reference)
from navera_lite.camera import K_from_hfov               # noqa: E402
from navera_lite.rotations import q_from_axis_angle, q_from_euler_zyx, q_mul, q_to_matrix  # noqa: E402

URL = "https://cdsarc.cds.unistra.fr/ftp/V/50/catalog.gz"
W, H, HFOV = 1280, 960, 60.0
PSF_SIGMA = 1.0
F_MAG6 = 60.0                       # total signal (DN) of a V = 6.0 star
READ_NOISE = 2.5
SKY = 18.0
SIG_TILT, SIG_HEAD = 0.3, 1.5        # BNO085-class attitude errors (deg): roll and pitch each 0.3, heading 1.5
YEAR = 2026.80

COMMON = {
    "Alp CMa": "Sirius", "Alp Car": "Canopus", "Alp Boo": "Arcturus", "Alp1Cen": "Rigil Kentaurus",
    "Alp Lyr": "Vega", "Alp Aur": "Capella", "Bet Ori": "Rigel", "Alp CMi": "Procyon", "Alp Eri": "Achernar",
    "Alp Ori": "Betelgeuse", "Bet Cen": "Hadar", "Alp Aql": "Altair", "Alp1Cru": "Acrux", "Alp Tau": "Aldebaran",
    "Alp Sco": "Antares", "Alp Vir": "Spica", "Bet Gem": "Pollux", "Alp PsA": "Fomalhaut", "Alp Cyg": "Deneb",
    "Bet Cru": "Mimosa", "Alp Leo": "Regulus", "Eps CMa": "Adhara", "Alp Gem": "Castor", "Gam Cru": "Gacrux",
    "Lam Sco": "Shaula", "Gam Ori": "Bellatrix", "Bet Car": "Miaplacidus", "Eps Ori": "Alnilam",
    "Alp Gru": "Alnair", "Zet Ori": "Alnitak", "Eps UMa": "Alioth", "Alp UMa": "Dubhe", "Alp Per": "Mirfak",
    "Alp UMi": "Polaris", "Bet UMi": "Kochab", "Alp Cas": "Schedar", "Zet UMa": "Mizar", "Eta UMa": "Alkaid",
    "Alp Pav": "Peacock", "Bet Cet": "Diphda", "Alp Ari": "Hamal", "Alp Peg": "Markab", "Eps Peg": "Enif",
    "Bet Per": "Algol", "Bet Leo": "Denebola", "Alp CrB": "Alphecca", "Alp Oph": "Rasalhague",
    "Bet1Cyg": "Albireo", "Bet UMa": "Merak", "Gam Cyg": "Sadr", "Alp And": "Alpheratz", "Alp Hya": "Alphard",
    "Bet Cas": "Caph", "Bet Tau": "Elnath", "Alp Col": "Phact",
}

# (name, lat, lon, UTC (y, mo, d, h, mi, s), heading, pitch_up, roll, prior lat, prior lon, extras)
PHOTOS = [
    ("night_01", 35.830, 10.640, (2026, 10, 20, 20, 30, 0), 60.0, -4.0, 0.0, 36.45, 10.10, {}),
    ("night_02", 35.520, 10.930, (2026, 10, 20, 21, 10, 0), 235.0, -3.0, 8.0, 36.45, 10.10,
     {"glow": True, "trail": True}),
    ("night_03", 69.650, 18.960, (2026, 10, 20, 22, 0, 0), 0.0, -15.0, 0.0, 69.20, 19.90, {}),
    ("night_04", -33.920, 18.420, (2026, 10, 20, 20, 0, 0), 170.0, -5.0, 0.0, -33.20, 19.30, {}),
    ("night_05", -0.180, -78.470, (2026, 10, 21, 3, 0, 0), 300.0, -6.0, -3.0, 0.60, -77.80, {}),
    ("night_06", 64.150, -21.940, (2026, 10, 21, 0, 30, 0), 45.0, -15.0, 0.0, 64.00, -21.20, {}),
]


def read_bsc(raw):
    if raw is None:
        with urllib.request.urlopen(URL, timeout=60) as r:
            data = r.read()
    else:
        data = open(raw, "rb").read()
    rows = []
    for line in gzip.GzipFile(fileobj=io.BytesIO(data)).read().decode("ascii").splitlines():
        line = line.ljust(197)
        if not line[75:77].strip() or not line[102:107].strip():
            continue                                         # novae / extragalactic objects: no position
        hr = int(line[0:4])
        name = line[4:14]
        flam, greek, const = name[0:3].strip(), name[3:7].strip(), name[7:10].strip()
        if greek:
            bayer = name[3:].strip()                         # e.g. "Alp UMi", "Alp1Cen"
        elif flam:
            bayer = f"{flam} {const}"                        # Flamsteed only, e.g. "61 Cyg"
        else:
            bayer = f"HR {hr}"
        ra = (int(line[75:77]) + int(line[77:79]) / 60.0 + float(line[79:83]) / 3600.0) * 15.0
        dec = int(line[84:86]) + int(line[86:88]) / 60.0 + int(line[88:90]) / 3600.0
        if line[83] == "-":
            dec = -dec
        vmag = float(line[102:107])
        if vmag > 6.5:
            continue
        rows.append({"hr": hr, "bayer": bayer, "common": COMMON.get(bayer, ""), "ra_deg": round(ra, 5),
                     "dec_deg": round(dec, 5), "vmag": vmag})
    missing = set(COMMON) - {r["bayer"] for r in rows}
    if missing:
        raise SystemExit(f"common names not found in the catalogue: {sorted(missing)}")
    return rows


def q_true(heading, pitch_up, roll):
    return q_from_euler_zyx(math.radians(roll), -math.radians(pitch_up), math.radians(90.0 - heading))


def chip_attitude(qt, decl, rng):
    """The IMU chip's attitude: BNO085-class errors, in a MAGNETIC-north frame (turned by +D about Up)."""
    dr, dp, dh = rng.normal(0.0, SIG_TILT), rng.normal(0.0, SIG_TILT), rng.normal(0.0, SIG_HEAD)
    q = q_mul(qt, q_from_axis_angle((1.0, 0.0, 0.0), math.radians(dr)))
    q = q_mul(q, q_from_axis_angle((0.0, 1.0, 0.0), math.radians(dp)))
    q = q_mul(q_from_axis_angle((0.0, 0.0, 1.0), math.radians(dh)), q)
    q = q_mul(q_from_axis_angle((0.0, 0.0, 1.0), math.radians(decl)), q)
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    if q[3] < 0:
        q = -q
    return q, (dr, dp, dh)


def star_pixels(cat, lat, lon, utc, qt, K):
    jd = S.julian_date(*utc)
    ra, dec = S.precess(cat["ra_deg"], cat["dec_deg"], jd)
    alt, az = S.altaz(ra, dec, lat, lon, S.gmst_deg(jd))
    a, A = np.radians(alt), np.radians(az)
    enu = np.stack([np.cos(a) * np.sin(A), np.cos(a) * np.cos(A), np.sin(a)], axis=1)
    R_wc = np.asarray(q_to_matrix(qt), dtype=float) @ S.R_BODY_STAR_CAM
    cam = enu @ R_wc
    ok = (cam[:, 2] > 0.1) & (alt > 3.0)
    uvw = cam @ K.T
    u, v = uvw[:, 0] / uvw[:, 2], uvw[:, 1] / uvw[:, 2]
    ok &= (u > -8) & (u < W + 8) & (v > -8) & (v < H + 8)
    return np.flatnonzero(ok), u, v


def erf_cdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def render(cat, idx, u, v, rng, extras):
    img = np.full((H, W), SKY, dtype=np.float64)
    yy, xx = np.indices((H, W))
    img += 6.0 * (yy / H)                                    # a little more sky glow near the image bottom
    if extras.get("glow"):
        img += 70.0 * np.exp(-((xx - 1180.0) ** 2 + (yy - 880.0) ** 2) / (2 * 380.0 ** 2))
    for i in idx:
        F = F_MAG6 * 10 ** (-0.4 * (cat["vmag"][i] - 6.0))
        r = 4 if F < 2000 else 7
        x0, y0 = int(round(u[i])), int(round(v[i]))
        xs = np.arange(x0 - r, x0 + r + 1)
        ys = np.arange(y0 - r, y0 + r + 1)
        gx = erf_cdf((xs + 0.5 - u[i]) / PSF_SIGMA) - erf_cdf((xs - 0.5 - u[i]) / PSF_SIGMA)
        gy = erf_cdf((ys + 0.5 - v[i]) / PSF_SIGMA) - erf_cdf((ys - 0.5 - v[i]) / PSF_SIGMA)
        patch = F * np.outer(gy, gx)
        ok_y = (ys >= 0) & (ys < H)
        ok_x = (xs >= 0) & (xs < W)
        img[np.ix_(ys[ok_y], xs[ok_x])] += patch[np.ix_(ok_y, ok_x)]
    if extras.get("trail"):
        trail = np.zeros((H, W), dtype=np.uint8)
        cv2.line(trail, (180, 720), (520, 560), 255, 3, lineType=cv2.LINE_AA)
        img += 80.0 * trail / 255.0
    img += rng.normal(0.0, READ_NOISE, img.shape)
    hot_y, hot_x = rng.integers(0, H, 40), rng.integers(0, W, 40)
    out = np.clip(np.round(img), 0, 255).astype(np.uint8)
    out[hot_y, hot_x] = rng.integers(120, 256, 40).astype(np.uint8)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=None)
    args = ap.parse_args()
    os.makedirs(os.path.join(OUT, "photos"), exist_ok=True)
    rows = read_bsc(args.raw)
    with open(os.path.join(OUT, "bright_stars.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["hr", "bayer", "common", "ra_deg", "dec_deg", "vmag"])
        wr.writeheader()
        wr.writerows(rows)
    cat = S.load_catalogue(os.path.join(OUT, "bright_stars.csv"), mag_max=6.5)
    K = K_from_hfov(HFOV, W, H)
    rng = np.random.default_rng(2626)
    gm = GeoMag()
    meta = {"camera": {"width_px": W, "height_px": H, "hfov_deg": HFOV, "K": K.round(4).tolist(),
                       "axis_body": [round(x, 6) for x in S.CAM_AXIS_BODY],
                       "note": "ideal pinhole (no distortion); axis 20° from body up, towards the nose"},
            "imu_note": "chip_q: the IMU chip's attitude (x, y, z, w), body → ENU whose north is MAGNETIC north",
            "photos": []}
    for k, (name, lat, lon, utc, hdg, pu, roll, plat, plon, extras) in enumerate(PHOTOS):
        qt = np.asarray(q_true(hdg, pu, roll), dtype=float)
        decl = float(gm.calculate(glat=lat, glon=lon, alt=0.0, time=YEAR).d)
        qc, errs = chip_attitude(qt, decl, rng)
        idx, u, v = star_pixels(cat, lat, lon, utc, qt, K)
        img = render(cat, idx, u, v, rng, extras)
        cv2.imwrite(os.path.join(OUT, "photos", name + ".png"), img)
        meta["photos"].append({
            "file": f"photos/{name}.png", "utc": "%04d-%02d-%02dT%02d:%02d:%02d" % utc,
            "utc_parts": list(utc), "chip_q": [round(float(x), 7) for x in qc],
            "prior_lat": plat, "prior_lon": plon,
            "truth": {"lat": lat, "lon": lon, "heading_deg": hdg, "pitch_up_deg": pu, "roll_deg": roll,
                      "q": [round(float(x), 7) for x in qt]}})
        print(f"{name}: {len(idx)} catalogue stars in view; declination {decl:+.2f}°; attitude errors "
              f"roll {errs[0]:+.2f}°, pitch {errs[1]:+.2f}°, heading {errs[2]:+.2f}°")
        if k == 0:
            with open(os.path.join(OUT, "photo01_stars.csv"), "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["hr", "name", "vmag", "u_px", "v_px"])
                for i in idx:
                    if 0 <= u[i] < W and 0 <= v[i] < H:
                        wr.writerow([int(cat["hr"][i]), cat["name"][i], cat["vmag"][i], round(float(u[i]), 3),
                                     round(float(v[i]), 3)])
    with open(os.path.join(OUT, "photos.json"), "w") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    print("written:", OUT)


README = """# Mission 26 data

- `bright_stars.csv` — 8 404 stars brighter than magnitude 6.5: catalogue number `hr`, Bayer/Flamsteed name
  `bayer`, a `common` name for about 50 bright stars, position `ra_deg`, `dec_deg` (equinox and epoch J2000)
  and visual magnitude `vmag` (smaller = brighter).
- `photos/night_01.png … night_06.png` — synthetic photos from NAVERA Lite's star camera (1280 × 960 pixels,
  8-bit grey, 60° wide, ideal lens), at night, at six places.
- `photos.json` — for each photo: the UTC time, the IMU chip's attitude at the exposure (quaternion
  x, y, z, w; its north is MAGNETIC north), a prior position (the operating area), and the truth (true
  position and attitude, for measuring errors). Also the camera's K matrix and its mounting.
- `photo01_stars.csv` — where the catalogue stars fall in `night_01.png` (pixels, with their magnitude).

The photos are rendered for the course from the catalogue; they are not real sky photos.

## Source and licence of the catalogue

`bright_stars.csv` is a subset (columns and stars brighter than 6.5 kept, common names added) of
**The Bright Star Catalogue, 5th Revised Edition (Preliminary Version)**, D. Hoffleit and W. H. Warren Jr.,
Astronomical Data Center, NSSDC/ADC, 1991 — CDS catalogue V/50,
https://cdsarc.cds.unistra.fr/viz-bin/cat/V/50. The catalogue's machine-readable documentation describes it
as public domain; it is shared here for teaching with this citation. If you use it, cite it as above.
"""

if __name__ == "__main__":
    main()
