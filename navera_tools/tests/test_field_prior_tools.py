"""navera_tools.field resolve_prior and deepstack (SIMULATION ONLY: a rendered 360 frame, synthetic stacks)."""
import json
from datetime import datetime, timezone

import numpy as np
import pytest


def test_deepstack_finish_drops_the_brightest_and_keeps_the_level():
    from navera_tools.field import deepstack
    rng = np.random.default_rng(0)
    frames = [20.0 + rng.normal(0, 2.0, (64, 64)).astype(np.float32) for _ in range(16)]
    frames[3][10, 10] = 250.0                                       # a plane crossing one pixel in one frame
    acc, top = np.zeros((64, 64), np.float32), np.zeros((64, 64), np.float32)
    for f in frames:
        acc += f
        np.maximum(top, f, out=top)
    out, mean = deepstack.finish(acc, top, len(frames))
    assert abs(float(mean.mean()) - 20.0) < 0.5 and mean[10, 10] < 30.0
    assert float(mean.std()) < 2.0 / 3.0                             # noise down ~ sqrt(15)
    assert abs(float(out.mean()) - float(mean.mean())) < 0.5          # the gain is about the background


def test_resolve_prior_on_a_simulated_session(tmp_path, capsys):
    try:
        from navera_tools.sim import celestial360_conditions as cc
    except ImportError:
        pytest.skip("simulator not on the path")
    import cv2
    from navera_tools.field import resolve_prior
    cond = cc.Condition("baseline mag<=3")
    sc = cc.Scene(cond, 0)
    frame = cc.render(sc)
    up, _ = cc.solver_up(sc)
    (tmp_path / "frames").mkdir()
    cv2.imwrite(str(tmp_path / "frames" / "f0.png"), frame)
    t = datetime.strptime(sc.utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    row = {"idx": 0, "t": t, "t_exp": t, "image": "frames/f0.png", "up_imu": list(map(float, up))}
    (tmp_path / "frames.jsonl").write_text(json.dumps(row) + "\n")
    out = tmp_path / "res.jsonl"
    assert resolve_prior.main([str(tmp_path), "--prior", f"{cond.lat + 0.2},{cond.lon},30",
                               "--truth", f"{cond.lat},{cond.lon},50", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "lost-in-space: 1 frames, 1 fixes, 0 wrong" in text and "prior: 1 frames, 1 fixes, 0 wrong" in text
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["mode"] for r in rows] == ["lost-in-space", "prior"]
    assert rows[1]["p_chance"] <= rows[0]["p_chance"]
