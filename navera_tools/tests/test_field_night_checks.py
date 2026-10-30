"""navera_tools.field forcedcheck and fixedspots (SIMULATION ONLY: Gaussian-noise frames, injected stars)."""
import json
from datetime import datetime, timezone

import numpy as np

UTC = "2026-10-30 02:30:00"
LAT, LON = 35.83, 10.64
UP = np.array([-0.076, -0.996, 0.051])          # the right lens looks up, as on the windowsill


def _frames(tmp_path, n, amp_dn, psi=100.0, seed=0):
    """n noise frames (8-bit, sigma 2 DN around 20) with the mag <= 3 stars + planets injected at heading psi."""
    import cv2
    from cn_pkg import allsky, sky360
    from cn_pkg.allsky_mount import zenith_icrs
    from navera_tools.field import forcedcheck
    rng = np.random.default_rng(seed)
    cat = allsky.Catalogue(limit_mag=3.0, path=allsky.BUNDLED_CATALOGUE)
    vec, _ = forcedcheck.points(cat, UTC, LAT, LON, 3.0)
    z = zenith_icrs(LAT, LON, UTC)
    up = UP / np.linalg.norm(UP)
    t0 = datetime.strptime(UTC, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    (tmp_path / "frames").mkdir()
    rows = []
    for i in range(n):
        img = (20.0 + rng.normal(0, 2.0, (1920, 3840))).astype(np.float32)
        if amp_dn:
            for L in sky360.default_lenses():
                img = forcedcheck.inject(img, L, up, z, psi, vec, amp_dn)
        cv2.imwrite(str(tmp_path / "frames" / f"f{i}.png"), np.clip(img, 0, 255).astype(np.uint8))
        rows.append({"idx": i, "t": t0, "t_exp": t0, "image": f"frames/f{i}.png", "up_imu": list(UP)})
    (tmp_path / "frames.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_forcedcheck_finds_stars_below_the_detector_and_nothing_in_noise(tmp_path, capsys):
    from cn_pkg import allsky, sky360
    from navera_tools.field import forcedcheck
    _frames(tmp_path, 4, 2.5)                                  # peak 1.25 sigma: never a 6-sigma detection
    import cv2
    img = cv2.imread(str(tmp_path / "frames" / "f0.png"), cv2.IMREAD_GRAYSCALE)
    assert len(allsky.detect_spots(img, sky360.default_lenses()[1])) < 5
    assert forcedcheck.main([str(tmp_path), "--at", f"{LAT},{LON}", "--lens", "both"]) == 0
    out = capsys.readouterr().out.splitlines()[-1]
    assert "STARLIGHT" in out and "heading 100.0" in out


def test_forcedcheck_pure_noise_is_not_starlight(tmp_path, capsys):
    from navera_tools.field import forcedcheck
    _frames(tmp_path, 4, 0.0, seed=1)
    assert forcedcheck.main([str(tmp_path), "--at", f"{LAT},{LON}", "--lens", "both"]) == 0
    assert "no starlight" in capsys.readouterr().out.splitlines()[-1]


def test_fixedspots_keeps_moving_stars_and_masks_fixed_junk():
    from navera_tools.field import fixedspots
    t = np.arange(0, 7200, 600.0)                              # a frame every 10 min for 2 h
    junk = [(ti, 500.0 + 0.5 * (i % 2), 700.0) for i, ti in enumerate(t)]          # a lamp, 0.5 px jitter
    star = [(ti, 1500.0 + 2.4 * ti / 60.0, 900.0) for ti in t]                     # drifts 2.4 px/min
    sp = np.array(junk + star)
    fx = fixedspots.fixed_spots(sp, 1800.0, 3.0, 3)
    assert fx[:len(junk)].all() and not fx[len(junk):].any()
    mask = fixedspots.make_mask((1920, 3840), sp[fx, 1:3])
    assert mask[700, 500] == 255 and mask[900, 1500] == 0
    img = np.full((1920, 3840), 10, np.uint8)
    img[699:702, 499:502] = 200
    clean = fixedspots.apply_mask(img, mask)
    assert clean[700, 500] == 10 and clean[0, 0] == 10


def test_fixedspots_few_far_frames_mask_nothing():
    from navera_tools.field import fixedspots
    sp = np.array([(0.0, 10.0, 10.0), (100.0, 10.0, 10.0), (200.0, 10.0, 10.0)])   # all within 30 min
    assert not fixedspots.fixed_spots(sp, 1800.0, 3.0, 3).any()
