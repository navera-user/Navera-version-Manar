"""Local feature matching (day vision): a synthetic textured world, no real map needed."""
import math

import cv2
import numpy as np
import pytest

from day_pkg.local_matcher import LocalMatcher, map_m_per_px, tile_px_to_latlon, tile_xy

Z = 17
LAT0, LON0 = 35.83, 10.62                # the world's centre (Sousse)
N_TILES = 10                             # the world is N x N tiles


def haversine(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """A textured world cut into z17 tiles (images/tile_17_x_y.jpg) and its pixel origin."""
    rng = np.random.default_rng(7)
    size = N_TILES * 256
    img = np.full((size, size), 120, np.uint8)
    for _ in range(2500):                                       # buildings, fields, roads
        x, y = rng.integers(0, size, 2)
        w, h = rng.integers(6, 40, 2)
        cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), int(rng.integers(20, 235)), -1)
    for _ in range(300):
        p1, p2 = rng.integers(0, size, 2), rng.integers(0, size, 2)
        cv2.line(img, tuple(int(v) for v in p1), tuple(int(v) for v in p2), int(rng.integers(0, 255)), int(rng.integers(1, 4)))
    img = cv2.GaussianBlur(img, (3, 3), 0)
    cx, cy = tile_xy(LAT0, LON0, Z)
    x0, y0 = int(cx) - N_TILES // 2, int(cy) - N_TILES // 2
    d = tmp_path_factory.mktemp("area") / "images"
    d.mkdir()
    for i in range(N_TILES):
        for j in range(N_TILES):
            cv2.imwrite(str(d / f"tile_{Z}_{x0 + i}_{y0 + j}.jpg"), img[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256])
    return str(d), img, (x0 * 256, y0 * 256)


def camera_frame(img, origin, lat, lon, rot_deg, frame_mpp, size=(640, 480), gain=0.8, noise=6.0):
    """The world seen by a nadir camera centred on (lat, lon): rotated, at frame_mpp m/px."""
    gx, gy = tile_xy(lat, lon, Z)
    px, py = gx * 256 - origin[0], gy * 256 - origin[1]
    s = map_m_per_px(lat, Z) / frame_mpp                         # map px → frame px
    M = cv2.getRotationMatrix2D((px, py), rot_deg, s)
    M[0, 2] += size[0] / 2 - px
    M[1, 2] += size[1] / 2 - py
    f = cv2.warpAffine(img, M, size, flags=cv2.INTER_LINEAR, borderValue=120).astype(np.float32)
    f = f * gain + 20 + np.random.default_rng(1).normal(0, noise, f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


@pytest.mark.parametrize("rot,frame_mpp", [(0, 1.0), (37, 1.6), (-120, 0.7), (180, 2.2)])
def test_finds_the_frame_centre(world, rot, frame_mpp):
    d, img, origin = world
    truth = tile_px_to_latlon(origin[0] + 1300, origin[1] + 1250, Z)
    prior = (truth[0] + 0.003, truth[1] - 0.002)                 # ~400 m away
    f = camera_frame(img, origin, *truth, rot, frame_mpp)
    r = LocalMatcher(d, device="cpu").locate(f, prior, 600.0, frame_mpp)
    assert r["accepted"], r.get("reason")
    assert haversine((r["predicted_lat"], r["predicted_lon"]), truth) < 5.0
    assert abs(r["scale_residual"] - 1.0) < 0.05


def test_gpu_and_cpu_matching_agree(world):
    d, img, origin = world
    truth = tile_px_to_latlon(origin[0] + 1100, origin[1] + 1400, Z)
    f = camera_frame(img, origin, *truth, 20, 1.2)
    cpu = LocalMatcher(d, device="cpu").locate(f, truth, 600.0, 1.2)
    gpu = LocalMatcher(d, device="auto").locate(f, truth, 600.0, 1.2)
    assert cpu["accepted"] and gpu["accepted"]
    assert haversine((cpu["predicted_lat"], cpu["predicted_lon"]), (gpu["predicted_lat"], gpu["predicted_lon"])) < 3.0


def test_wrong_altitude_is_refused(world):
    """Told the frame is at 1.8x its real resolution, the fit's scale gives it away."""
    d, img, origin = world
    truth = tile_px_to_latlon(origin[0] + 1200, origin[1] + 1200, Z)
    f = camera_frame(img, origin, *truth, 10, 1.0)
    r = LocalMatcher(d, device="cpu").locate(f, truth, 600.0, 1.8)
    assert not r["accepted"]


def test_prior_elsewhere_is_refused(world):
    """The search circle does not contain the frame: no position, not a wrong one."""
    d, img, origin = world
    truth = tile_px_to_latlon(origin[0] + 300, origin[1] + 300, Z)
    far = tile_px_to_latlon(origin[0] + 2200, origin[1] + 2200, Z)    # ~2.5 km away
    f = camera_frame(img, origin, *truth, 0, 1.0)
    r = LocalMatcher(d, device="cpu").locate(f, far, 300.0, 1.0)
    assert not r["accepted"]


def test_uniform_ground_gives_no_position(world):
    d, _, origin = world
    truth = tile_px_to_latlon(origin[0] + 1280, origin[1] + 1280, Z)
    flat = np.full((480, 640), 128, np.uint8)
    r = LocalMatcher(d, device="cpu").locate(flat, truth, 600.0, 1.0)
    assert not r["accepted"] and r.get("reason")


def test_outside_the_area_reports_empty(world):
    d, img, origin = world
    r = LocalMatcher(d, device="cpu").locate(np.zeros((480, 640), np.uint8), (0.5, 0.5), 600.0, 1.0)
    assert r["spatial_empty"] and not r["accepted"]


def test_gpu_matching_in_blocks_gives_the_same_neighbours(world):
    """Map descriptors are compared in blocks on the GPU: the merge must keep the true two nearest."""
    d, _, _ = world
    m = LocalMatcher(d, device="auto")
    if m.torch is None:
        pytest.skip("no CUDA")
    rng = np.random.default_rng(3)
    dq, dm = rng.random((300, 128), np.float32), rng.random((5000, 128), np.float32)
    m.GPU_BLOCK = 700                                         # several blocks, a partial last one
    gi, gv = m._knn2(dq, dm)
    m.torch = None
    ci, cv = m._knn2(dq, dm)
    assert np.array_equal(gi[:, 0], ci[:, 0])
    assert np.allclose(gv, cv, atol=1e-3)
