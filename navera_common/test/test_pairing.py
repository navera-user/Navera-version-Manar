"""Unit tests for navera_common.pairing.FramePairer."""
from navera_common.pairing import FramePairer


def meta(i, stamp, **kw):
    return {"frame_id": i, "image_stamp_ns": stamp, **kw}


def test_pairs_in_either_order():
    p = FramePairer()
    assert p.add_image(100, "img1") is None
    assert p.add_meta(meta(1, 100)) == ("img1", meta(1, 100))
    assert p.add_meta(meta(2, 200)) is None
    assert p.add_image(200, "img2") == ("img2", meta(2, 200))


def test_lost_image_does_not_shift_later_frames():
    """Regression: with latest-of-each, frame 3's image got frame 2's meta forever."""
    p = FramePairer()
    assert p.add_meta(meta(2, 200)) is None          # image 2 never arrives
    assert p.add_image(300, "img3") is None
    assert p.add_meta(meta(3, 300)) == ("img3", meta(3, 300))
    assert p.add_image(400, "img4") is None
    assert p.add_meta(meta(4, 400)) == ("img4", meta(4, 400))


def test_lost_meta_does_not_shift_later_frames():
    p = FramePairer()
    assert p.add_image(200, "img2") is None          # meta 2 never arrives
    assert p.add_image(300, "img3") is None
    assert p.add_meta(meta(3, 300)) == ("img3", meta(3, 300))


def test_image_missing_is_returned_for_ack():
    p = FramePairer()
    assert p.add_meta(meta(5, 500, image_missing=True)) == (None, meta(5, 500, image_missing=True))


def test_undecodable_image_still_pairs():
    p = FramePairer()
    p.add_image(600, None)
    assert p.add_meta(meta(6, 600)) == (None, meta(6, 600))


def test_pending_buffer_is_bounded():
    p = FramePairer(max_pending=3)
    for s in range(10):
        p.add_meta(meta(s, s))
    assert len(p._metas) == 3


def test_legacy_meta_without_stamp_uses_latest_image():
    p = FramePairer()
    p.add_image(1, "img")
    assert p.add_meta({"frame_id": 1}) == ("img", {"frame_id": 1})
    assert p.add_meta({"frame_id": 2}) is None
    assert p.add_image(2, "img2") == ("img2", {"frame_id": 2})
