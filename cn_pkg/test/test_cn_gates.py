"""cn_subscriber gates that refuse to solve: a frame the camera marked unusable (frozen picture)."""
import json

import numpy as np
import pytest

rclpy = pytest.importorskip("rclpy")
from cn_pkg.nodes import cn_subscriber as cs   # noqa: E402


@pytest.fixture
def node():
    rclpy.init()
    n = cs.CNSubscriber()
    n.sent = []
    n.pub_est.publish = n.sent.append
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _process(n, meta):
    assert n._busy_lock.acquire(blocking=False)        # _dispatch holds it; _process_frame releases it
    n._process_frame(meta["frame_id"], np.zeros((60, 80, 3), np.uint8), meta)
    return n.sent[-1]


def test_a_frozen_star_picture_is_never_solved(node):
    """D24 / H-01b: a stale sky with a new time is a wrong position — declared invalid, not solved."""
    est = _process(node, {"frame_id": 7, "usable": False, "image_stamp_ns": 1,
                          "reason": "camera image frozen: picture identical to the previous one"})
    assert not est.valid and "camera image frozen" in est.reason
    assert "frozen" in json.loads(est.details_json)["error"]
