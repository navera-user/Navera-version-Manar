"""longexp: protobuf codec, message parsing, the command channel on a fake camera, DNG/JPEG ingest (no camera)."""
import json
import math
import os
import struct
import sys
import threading
import time

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field import longexp  # noqa: E402
from navera_common.insta360_protocol import IMU_RECORD  # noqa: E402

# a notification packet as recorded from the real camera (2026-10-20 raw recording, code 8220)
REAL_NOTIFICATION = bytes.fromhex("0400001c2002ff8a43f400000801120d0800100019000000000000"
                                  "00001a0e08001085011900000020af79843f")


def test_pb_roundtrip_and_nesting():
    body = longexp.pb_encode([(1, 3), (2, 30.0), (3, "IMG_1.insp"), (4, [(1, 800), (2, -1)]), (5, b"\xff\x00")])
    f = longexp.pb_decode(body)
    assert [x["f"] for x in f] == [1, 2, 3, 4, 5]
    assert f[0]["v"] == 3 and f[1]["v"] == 30.0 and f[2]["v"] == "IMG_1.insp"
    assert f[3]["v"][0]["v"] == 800 and f[3]["v"][1]["v"] == (1 << 64) - 1
    assert longexp.pb_strings(f) == ["IMG_1.insp"]


def test_pb_start_full_is_the_known_live_stream_body():
    f = longexp.pb_decode(bytes.fromhex("10013028380040014828500f5802"))
    assert {x["f"]: x["v"] for x in f} == {2: 1, 6: 40, 7: 0, 8: 1, 9: 40, 10: 15, 11: 2}


def test_pb_rejects_garbage():
    with pytest.raises(ValueError):
        longexp.pb_decode(b"\x0a\x10ab")                 # length beyond the end


def test_pb_diff_names_the_changed_field():
    a = longexp.pb_decode(longexp.pb_encode([(1, 1), (5, [(3, 100), (4, 0.5)])]))
    b = longexp.pb_decode(longexp.pb_encode([(1, 1), (5, [(3, 800), (4, 0.5)])]))
    d = longexp.pb_diff(a, b, "X")
    assert len(d) == 1 and d[0].startswith("X.5.3") and "100 -> 800" in d[0]


def test_parse_real_notification():
    m = longexp.parse_message(REAL_NOTIFICATION)
    assert m["code"] == 8220 and m["fields"] is not None and m["fields"][0] == {"f": 1, "wt": 0, "v": 1}
    assert longexp.parse_message(b"\x01\x00\x00\x30" + bytes(20)) is None


def test_only_listed_commands_can_be_sent():
    with pytest.raises(KeyError):
        longexp.command("ERASE_SD_CARD", 1)
    pkt = longexp.command("GET_OPTIONS", 7)
    assert struct.unpack_from("<i", pkt)[0] == len(pkt)
    assert pkt[4:7] == b"\x04\x00\x00" and int.from_bytes(pkt[7:9], "little") == 8


class FakeDev:
    """Answers every command with code 200 and the same sequence number; streams IMU while live."""

    def __init__(self, reply_body=b"", up=(1.0, 0.0, 0.0)):
        self.out = []
        self.inbox = bytearray()
        self.reply_body = reply_body
        self.up = up
        self.live = False
        self.lock = threading.Lock()
        self.ms = 0

    def write(self, ep, data, timeout=None):
        n = struct.unpack_from("<i", data)[0]
        p = bytes(data[4:n])
        self.out.append(p)
        if p[:3] == b"\x04\x00\x00":
            code = int.from_bytes(p[3:5], "little")
            self.live = {1: True, 2: False}.get(code, self.live)
            reply = (b"\x04\x00\x00" + (200).to_bytes(2, "little") + b"\x02" + p[6:9] + b"\x80\x00\x00"
                     + (self.reply_body if code == 3 else b""))
            with self.lock:
                self.inbox += struct.pack("<i", len(reply) + 4) + reply
        return len(data)

    def read(self, ep, size, timeout=None):
        time.sleep(0.01)
        with self.lock:
            if self.live:
                rows = b"".join(IMU_RECORD.pack(self.ms + 2 * k, *self.up, 0.0, 0.0, 0.0) for k in range(10))
                self.ms += 20
                p = b"\x01\x00\x00\x30" + struct.pack("<I", self.ms) + bytes(4) + rows
                self.inbox += struct.pack("<i", len(p) + 4) + p
            data, self.inbox = bytes(self.inbox), bytearray()
        if not data:
            raise TimeoutError("timeout")
        return data


def test_request_reply_and_shoot_on_fake_camera():
    dev = FakeDev(reply_body=longexp.pb_encode([(1, [(1, "/DCIM/Camera01/IMG_20261030_120000_00_001.insp")])]),
                  up=(0.0, 0.6, 0.8))
    cam = longexp.LongExpCamera(dev)
    try:
        r = cam.request("GET_OPTIONS")
        assert r["code"] == 200
        rec = longexp.shoot(cam, wait_s=1.0, imu_s=0.3)
    finally:
        cam.close()
    assert rec["files"] == ["/DCIM/Camera01/IMG_20261030_120000_00_001.insp"]
    assert np.allclose(rec["up_imu"], [0.0, 0.6, 0.8], atol=1e-6) and rec["up_change_deg"] < 1e-3
    assert rec["t_sent"] <= rec["t_exp"] <= rec["t_sent"] + 1.0
    sent = [int.from_bytes(p[3:5], "little") for p in dev.out if p[:3] == b"\x04\x00\x00"]
    assert sent == [8, 1, 2, 3, 1, 2]


def _dng(path, mosaic, black=64):
    """A minimal uncompressed little-endian DNG: IFD0 (thumbnail-less) with a SubIFD holding the CFA."""
    h, w = mosaic.shape
    data = mosaic.astype("<u2").tobytes()

    def ifd(entries, at):
        out = struct.pack("<H", len(entries))
        extra, extra_at = b"", at + 2 + 12 * len(entries) + 4
        for tag, typ, vals in entries:
            fmt = {3: "H", 4: "I"}[typ]
            raw = struct.pack("<" + fmt * len(vals), *vals)
            if len(raw) <= 4:
                out += struct.pack("<HHI", tag, typ, len(vals)) + raw.ljust(4, b"\0")
            else:
                out += struct.pack("<HHII", tag, typ, len(vals), extra_at + len(extra))
                extra += raw
        return out + struct.pack("<I", 0) + extra

    sub_at = 8 + 200
    data_at = 1000
    ifd0 = ifd([(254, 4, [1]), (330, 4, [sub_at])], 8)
    sub = ifd([(254, 4, [0]), (256, 4, [w]), (257, 4, [h]), (258, 3, [16]), (259, 3, [1]), (262, 3, [32803]),
               (273, 4, [data_at]), (279, 4, [len(data)]), (50714, 4, [black])], sub_at)
    buf = bytearray(b"II" + struct.pack("<HI", 42, 8))
    buf += ifd0
    buf = buf.ljust(sub_at, b"\0") + sub
    buf = buf.ljust(data_at, b"\0") + data
    with open(path, "wb") as fh:
        fh.write(buf)


def test_read_dng_and_bin(tmp_path):
    rng = np.random.default_rng(1)
    m = (64 + rng.integers(0, 100, (40, 80))).astype(np.uint16)
    p = str(tmp_path / "a.dng")
    _dng(p, m)
    got = longexp.read_dng(p)
    assert np.array_equal(got, m.astype(np.float32) - 64)
    g = longexp.cfa_to_gray(got)
    assert g.shape == (20, 40) and math.isclose(float(g[0, 0]), float(got[:2, :2].sum()))


def test_ingest_photo_gives_solver_rows(tmp_path):
    import cv2
    from navera_tools.field.resolve_prior import rows_of
    rng = np.random.default_rng(2)
    img = np.clip(rng.normal(20, 2, (3040, 6080)), 0, 255).astype(np.uint8)
    img[1500:1503, 1500:1503] = 250                             # a star inside the left circle
    src = str(tmp_path / "IMG_20261030_120000_00_001.insp")
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 98])
    enc.tofile(src)
    shots = [{"files": ["/DCIM/Camera01/IMG_20261030_120000_00_001.insp"], "up_imu": [1.0, 0.0, 0.0],
              "t_exp": 1793367600.0}]
    out = str(tmp_path / "stills")
    rows = longexp.ingest([src], out, shots=shots)
    assert rows[0]["up_imu"] == [1.0, 0.0, 0.0] and rows[0]["t_exp"] == 1793367600.0
    assert rows[0]["size_in"] == [6080, 3040] and abs(rows[0]["dark"] - 20) < 1.0
    # binning 6080 -> 3840 lowers the noise of white noise (sigma 2 → ~1.3 plus JPEG)
    assert rows[0]["noise"] < 2.0
    png = cv2.imread(os.path.join(out, rows[0]["image"]), cv2.IMREAD_GRAYSCALE)
    assert png.shape == (1920, 3840)
    y, x = np.unravel_index(np.argmax(png), png.shape)
    assert abs(x - 1500 * 3840 / 6080) < 3 and abs(y - 1500 * 1920 / 3040) < 3
    listed = list(rows_of(None, out))
    assert len(listed) == 1 and listed[0][1]["image"] == rows[0]["image"]
    with open(os.path.join(out, "index.jsonl")) as fh:
        assert json.loads(fh.readline())["kind"] == "jpeg"


def test_noise_stats_outside_circles():
    rng = np.random.default_rng(3)
    g = rng.normal(16.0, 0.8, (1920, 3840)).astype(np.float32)
    s = longexp.noise_stats(g)
    assert abs(s["dark"] - 16.0) < 0.05 and abs(s["noise"] - 0.8) < 0.05 and s["n"] > 10000
