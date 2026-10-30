#!/usr/bin/env python3
"""Long-exposure stills from the Insta360 One RS over USB (Android mode), for the 360 star solver.

    python3 -m navera_tools.field.longexp probe [--out probe.json]          # read-only: options, file list
    python3 -m navera_tools.field.longexp shoot --out DIR [--wait S] [--set-hex HEX]
    python3 -m navera_tools.field.longexp ingest PHOTOS... --out DIR [--up X,Y,Z] [--t-exp UNIX]
    python3 -m navera_tools.field.longexp noise IMAGE [IMAGE ...]          # dark level + noise (outside the circles)

Why: the live H.264 stream erases everything under ~1 DN (2026-10-29 night: a star must reach ~1 DN in ONE
frame before stacking can help). The camera's own photo mode has Manual exposure (shutter up to 120 s, ISO
100-3200) and RAW (DNG): one 20-30 s exposure collects ~500x the light of one 1/18 s video frame, without the
encoder.

What is known about the protocol (state on 2026-10-30, nothing downloaded):
- Verified on this camera: framing, sync, keepalive, message header, StartLiveStream (1) / StopLiveStream (2),
  the IMU and video packets (insta360_usb.py), and the camera's notification messages (code 8220 seen in every
  raw recording: `04 00 00 1c 20 02 <seq 3> ...` + protobuf).
- From the reference implementation (RigacciOrg/insta360-wifi-api, insta360.py: the Wi-Fi app protocol the
  USB link speaks) as recalled - its copy is NOT on this disk any more, the numbers below are UNVERIFIED and
  every one is tried read-only first by `probe`: TAKE_PICTURE 3, SET_OPTIONS 7, GET_OPTIONS 8,
  SET_PHOTOGRAPHY_OPTIONS 9, GET_PHOTOGRAPHY_OPTIONS 10, GET_FILE_LIST 13, GET_CURRENT_CAPTURE_STATUS 15.
  Reply code 200 = OK. Only codes listed in COMMANDS can ever be sent (the reference also has codes that
  erase the SD card or reboot the camera: never sent, not even listed).
- The field numbers of the exposure settings (program, shutter, ISO, RAW) are NOT known on disk. Two ways:
  (1) set Manual 30 s / ISO 800 / RAW once on the camera's touch screen (the camera keeps it) and only send
  TAKE_PICTURE; (2) `probe` before and after changing one setting on the screen: the field that changed is
  the setting, and `shoot --set-hex` sends it back.
- Download over USB: the reference fetches files over HTTP on Wi-Fi; over the USB link no download message is
  known. Until one is found: copy the .insp/.dng from the SD card (or USB mode "U-disk") and `ingest` them.

The navera-field service opens the camera itself as soon as it is plugged in (Camera360 retries every 3 s); while
it holds the USB interface this tool gets "Resource busy" and says so.

`ingest` writes DIR/index.jsonl rows {"image", "up_imu", "t_exp", ...} and 3840x1920 gray PNGs in the live
stream's geometry (the calibrated lens model then applies; the photo's 6080x3040 is binned down, which also
lowers the noise): `resolve_prior <session> --images DIR` and `starcheck` solve them like stream frames.
"""
import argparse
import json
import math
import os
import struct
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_common.insta360_protocol import (  # noqa: E402
    EP_IN, EP_OUT, IMU_RECORD, KIND_IMU, PKT_KEEPALIVE, PKT_SYNC, START_FULL, VENDOR, frame_packet, message_payload,
    split_packets)

# ── commands ─────────────────────────────────────────────────────────────
# name: (code, provenance, read_only)
COMMANDS: Dict[str, Tuple[int, str, bool]] = {
    "START_LIVE_STREAM": (1, "verified", False),
    "STOP_LIVE_STREAM": (2, "verified", False),
    "TAKE_PICTURE": (3, "reference, unverified", False),
    "SET_OPTIONS": (7, "reference, unverified", False),
    "GET_OPTIONS": (8, "reference, unverified", True),
    "SET_PHOTOGRAPHY_OPTIONS": (9, "reference, unverified", False),
    "GET_PHOTOGRAPHY_OPTIONS": (10, "reference, unverified", True),
    "GET_FILE_LIST": (13, "reference, unverified", True),
    "GET_CURRENT_CAPTURE_STATUS": (15, "reference, unverified", True),
}
RESPONSE_OK = 200
NOTIFICATION_MIN = 8193            # camera-initiated messages (8220 seen on this camera)
OUT_SIZE = (3840, 1920)            # the live stream's dual fisheye: the calibrated lens model's geometry
PHOTO_SIZES = {(6080, 3040), (3040, 1520), (5760, 2880), (3840, 1920)}

# ── protobuf wire format (no schema: the .proto files are not on disk) ───────────


def _varint(n: int) -> bytes:
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _read_varint(b: bytes, i: int) -> Tuple[int, int]:
    n = shift = 0
    while True:
        if i >= len(b) or shift > 63:
            raise ValueError("truncated varint")
        c = b[i]
        n |= (c & 0x7F) << shift
        i, shift = i + 1, shift + 7
        if not c & 0x80:
            return n, i


def pb_encode(fields: List[Tuple[int, object]]) -> bytes:
    """[(field number, value)] → protobuf bytes: int → varint, float → fixed64 double, bytes/str → length-delimited,
    list of pairs → nested message."""
    out = bytearray()
    for num, v in fields:
        if isinstance(v, bool) or isinstance(v, int):
            out += _varint(num << 3) + _varint(int(v))
        elif isinstance(v, float):
            out += _varint(num << 3 | 1) + struct.pack("<d", v)
        elif isinstance(v, (bytes, str, list)):
            data = v.encode() if isinstance(v, str) else pb_encode(v) if isinstance(v, list) else v
            out += _varint(num << 3 | 2) + _varint(len(data)) + data
        else:
            raise TypeError(f"field {num}: {type(v).__name__}")
    return bytes(out)


def pb_decode(b: bytes, depth: int = 0) -> List[dict]:
    """Protobuf bytes → [{"f", "wt", "v"}], length-delimited values shown as a nested message when they parse
    as one, else as text when printable, else hex. Raises ValueError on bytes that are not a message."""
    out, i = [], 0
    while i < len(b):
        key, i = _read_varint(b, i)
        num, wt = key >> 3, key & 7
        if num == 0:
            raise ValueError("field 0")
        if wt == 0:
            v, i = _read_varint(b, i)
        elif wt == 1:
            if i + 8 > len(b):
                raise ValueError("truncated fixed64")
            v, i = struct.unpack_from("<d", b, i)[0], i + 8
        elif wt == 5:
            if i + 4 > len(b):
                raise ValueError("truncated fixed32")
            v, i = struct.unpack_from("<f", b, i)[0], i + 4
        elif wt == 2:
            n, i = _read_varint(b, i)
            if i + n > len(b):
                raise ValueError("truncated bytes")
            raw, i = b[i:i + n], i + n
            v = _show_bytes(raw, depth)
        else:
            raise ValueError(f"wire type {wt}")
        out.append({"f": num, "wt": wt, "v": v})
    return out


def _show_bytes(raw: bytes, depth: int):
    if raw and all(32 <= c < 127 for c in raw):
        return raw.decode()
    if depth < 6:
        try:
            return pb_decode(raw, depth + 1)
        except ValueError:
            pass
    return {"hex": raw.hex()}


def pb_strings(fields) -> List[str]:
    """Every text value anywhere in a decoded message (file names such as /DCIM/Camera01/IMG_....insp)."""
    out = []
    for f in fields if isinstance(fields, list) else []:
        v = f["v"]
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out += pb_strings(v)
    return out


def pb_diff(a, b, path: str = "") -> List[str]:
    """Fields that differ between two decoded messages (probe before / after a change on the camera's screen)."""
    out = []
    da = {(f["f"], k): f["v"] for k, f in enumerate(a or [])}
    db = {(f["f"], k): f["v"] for k, f in enumerate(b or [])}
    for key in sorted(set(da) | set(db)):
        va, vb = da.get(key), db.get(key)
        p = f"{path}.{key[0]}"
        if isinstance(va, list) and isinstance(vb, list):
            out += pb_diff(va, vb, p)
        elif va != vb:
            out.append(f"{p}: {va!r} -> {vb!r}")
    return out


# ── messages ──────────────────────────────────────────────────────────────


def parse_message(p: bytes) -> Optional[dict]:
    """A message packet (04 00 00 <code u16> 02 <seq u24> <3 bytes> <protobuf>) → {"code", "seq", "body", "fields"};
    None for stream packets and anything shorter than a header."""
    if len(p) < 12 or p[:3] != b"\x04\x00\x00":
        return None
    code = int.from_bytes(p[3:5], "little")
    seq = int.from_bytes(p[6:9], "little")
    body = bytes(p[12:])
    try:
        fields = pb_decode(body)
    except ValueError:
        fields = None
    return {"code": code, "seq": seq, "body": body.hex(), "fields": fields}


def command(name: str, seq: int, body: bytes = b"") -> bytes:
    """The framed bytes for a listed command (anything else is refused: no guessing codes on a real camera)."""
    if name not in COMMANDS:
        raise KeyError(f"{name}: not a listed command")
    return frame_packet(message_payload(COMMANDS[name][0], seq, body))


def mean_up(imu_rows: List[Tuple], acc_bias=None, acc_scale=None) -> Optional[np.ndarray]:
    """'up' (unit, IMU frame: the axis that reads +1 g at rest) from IMU records (ms, ax, ay, az, wx, wy, wz)."""
    if not imu_rows:
        return None
    a = np.array([r[1:4] for r in imu_rows], float)
    if acc_bias is not None:
        a = (a - np.asarray(acc_bias)) * np.asarray(acc_scale if acc_scale is not None else 1.0)
    m = a.mean(axis=0)
    n = float(np.linalg.norm(m))
    return m / n if n > 0.5 else None


class LongExpCamera:
    """The camera's command channel: request(name, body) waits for the reply with the same sequence number.
    IMU records arriving meanwhile (while a live stream runs) are kept for 'up'."""

    def __init__(self, dev=None):
        if dev is None:
            import usb.core
            import usb.util
            dev = usb.core.find(idVendor=VENDOR)
            if dev is None:
                raise RuntimeError("Insta360 not found: plug it in, USB mode 'Android' (lsusb shows 2e1a:0002)")
            try:
                usb.util.claim_interface(dev, 0)
            except usb.core.USBError as e:
                if getattr(e, "errno", None) == 16:
                    raise RuntimeError("camera busy: the navera-field service holds it (it opens the camera as "
                                       "soon as it is plugged in); stop the service first") from e
                raise
        self.dev = dev
        self._seq = 1
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._replies: Dict[int, dict] = {}
        self.notifications: List[dict] = []
        self.imu: List[Tuple] = []
        self._stop = False
        self._cv = threading.Condition()
        self.dev.write(EP_OUT, frame_packet(PKT_SYNC), timeout=1000)
        self._threads = [threading.Thread(target=f, daemon=True) for f in (self._reader, self._keepalive)]
        for t in self._threads:
            t.start()

    def close(self):
        self._stop = True

    def _keepalive(self):
        while not self._stop:
            time.sleep(1.0)
            try:
                self.dev.write(EP_OUT, frame_packet(PKT_KEEPALIVE), timeout=1000)
            except Exception:
                pass

    def _reader(self):
        while not self._stop:
            try:
                self._buf += bytes(self.dev.read(EP_IN, 262144, timeout=500))
            except Exception as e:
                if "timeout" in str(e).lower() or type(e).__name__ == "USBTimeoutError":
                    continue
                time.sleep(0.2)
                continue
            for p in split_packets(self._buf):
                self.on_packet(p)

    def on_packet(self, p: bytes):
        if p[:1] == b"\x01" and len(p) >= 12 and p[3] == KIND_IMU:
            body = p[12:]
            rows = [IMU_RECORD.unpack_from(body, k) for k in range(0, len(body) - IMU_RECORD.size + 1, IMU_RECORD.size)]
            with self._lock:
                self.imu += rows
                del self.imu[:-5000]
            return
        m = parse_message(p)
        if m is None:
            return
        m["t"] = time.time()
        with self._cv:
            if m["code"] >= NOTIFICATION_MIN:
                self.notifications.append(m)
            else:
                self._replies[m["seq"]] = m
            self._cv.notify_all()

    def send(self, name: str, body: bytes = b"") -> int:
        with self._lock:
            seq, self._seq = self._seq, self._seq + 1
        self.dev.write(EP_OUT, command(name, seq, body), timeout=1000)
        return seq

    def request(self, name: str, body: bytes = b"", timeout: float = 5.0) -> Optional[dict]:
        seq = self.send(name, body)
        end = time.time() + timeout
        with self._cv:
            while seq not in self._replies:
                left = end - time.time()
                if left <= 0:
                    return None
                self._cv.wait(left)
            return self._replies.pop(seq)

    def up(self, seconds: float = 1.0) -> Optional[np.ndarray]:
        with self._lock:
            rows = list(self.imu)
        if not rows:
            return None
        last = rows[-1][0]
        return mean_up([r for r in rows if r[0] >= last - seconds * 1000.0])


def probe(cam: LongExpCamera) -> dict:
    """Every read-only command once; the decoded replies (or None when the camera does not answer)."""
    out = {}
    for name, (code, prov, ro) in COMMANDS.items():
        if not ro:
            continue
        r = cam.request(name, b"", timeout=3.0)
        out[name] = {"code": code, "provenance": prov, "reply": r and {k: r[k] for k in ("code", "body", "fields")}}
    out["notifications"] = [{k: n[k] for k in ("code", "body", "fields")} for n in cam.notifications[-10:]]
    return out


def shoot(cam: LongExpCamera, wait_s: float, set_body: Optional[bytes] = None, imu_s: float = 4.0) -> dict:
    """One still: 'up' from the camera's IMU (live stream with gyro on for imu_s before and after), optional
    SET_PHOTOGRAPHY_OPTIONS body, TAKE_PICTURE, wait for the reply (the exposure + saving). The reply's text
    fields hold the file name on the SD card."""
    rec = {"t_request": time.time()}
    cam.send("START_LIVE_STREAM", START_FULL)
    time.sleep(imu_s)
    rec["up_before"] = _list(cam.up())
    cam.send("STOP_LIVE_STREAM")
    time.sleep(0.5)
    if set_body:
        r = cam.request("SET_PHOTOGRAPHY_OPTIONS", set_body)
        rec["set_reply"] = r and r["code"]
    t0 = time.time()
    r = cam.request("TAKE_PICTURE", b"", timeout=wait_s + 30.0)
    t1 = time.time()
    rec.update(t_sent=t0, t_reply=t1, reply=r and {k: r[k] for k in ("code", "body", "fields")},
               files=pb_strings(r["fields"]) if r and r["fields"] else [])
    cam.send("START_LIVE_STREAM", START_FULL)
    time.sleep(imu_s)
    rec["up_after"] = _list(cam.up())
    cam.send("STOP_LIVE_STREAM")
    ups = [np.array(u) for u in (rec["up_before"], rec["up_after"]) if u]
    if len(ups) == 2:
        rec["up_change_deg"] = math.degrees(math.acos(float(np.clip(ups[0] @ ups[1], -1, 1))))
    if ups:
        m = sum(ups)
        rec["up_imu"] = _list(m / np.linalg.norm(m))
    # the exposure ends some time before the reply (saving); its middle is taken as wait_s / 2 after the request
    rec["t_exp"] = t0 + wait_s / 2.0
    return rec


def _list(v):
    return None if v is None else [round(float(x), 6) for x in v]


# ── files: .insp / .jpg (JPEG) and .dng (uncompressed CFA only) ──────────────────

_TIFF_TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 5: "II", 7: "B", 9: "i", 10: "ii", 11: "f", 12: "d", 16: "Q"}


def _tiff_ifds(b: bytes):
    """Every IFD of a TIFF/DNG (SubIFDs included) as {tag: values}."""
    end = "<" if b[:2] == b"II" else ">"
    if struct.unpack_from(end + "H", b, 2)[0] != 42:
        raise ValueError("not a TIFF/DNG")
    todo, seen, out = [struct.unpack_from(end + "I", b, 4)[0]], set(), []
    while todo:
        off = todo.pop(0)
        if not off or off in seen or off + 2 > len(b):
            continue
        seen.add(off)
        n = struct.unpack_from(end + "H", b, off)[0]
        tags = {}
        for k in range(n):
            e = off + 2 + 12 * k
            tag, typ, cnt = struct.unpack_from(end + "HHI", b, e)
            fmt = _TIFF_TYPES.get(typ)
            if fmt is None:
                continue
            size = struct.calcsize(end + fmt) * cnt
            at = e + 8 if size <= 4 else struct.unpack_from(end + "I", b, e + 8)[0]
            vals = struct.unpack_from(end + fmt * cnt, b, at) if typ != 2 else (b[at:at + cnt],)
            tags[tag] = vals
        out.append(tags)
        if 330 in tags:                                    # SubIFDs
            todo += list(tags[330])
        todo.append(struct.unpack_from(end + "I", b, off + 2 + 12 * n)[0])
    return out, end


def read_dng(path: str) -> np.ndarray:
    """The raw CFA mosaic of an uncompressed DNG (8/16-bit strips or tiles) as float32, black level subtracted.
    Compressed DNGs (lossless JPEG) need a decoder that is not installed: ValueError says so."""
    with open(path, "rb") as fh:
        b = fh.read()
    ifds, end = _tiff_ifds(b)
    cfa = [t for t in ifds if t.get(262, (0,))[0] == 32803]          # PhotometricInterpretation = CFA
    if not cfa:
        raise ValueError("no CFA image in this DNG")
    t = cfa[0]
    w, h, bits = t[256][0], t[257][0], t[258][0]
    if t.get(259, (1,))[0] != 1:
        raise ValueError(f"compressed DNG (compression {t[259][0]}): no decoder installed")
    if bits not in (8, 16):
        raise ValueError(f"{bits}-bit packed DNG not supported")
    dt = np.dtype(np.uint8 if bits == 8 else (end + "u2"))
    if 273 in t:
        data = b"".join(b[o:o + n] for o, n in zip(t[273], t[279]))
        img = np.frombuffer(data, dt, count=w * h).reshape(h, w)
    else:
        tw, th = t[322][0], t[323][0]
        img = np.zeros((h, w), dt)
        per_row = -(-w // tw)
        for k, (o, n) in enumerate(zip(t[324], t[325])):
            y, x = (k // per_row) * th, (k % per_row) * tw
            tile = np.frombuffer(b[o:o + n], dt, count=tw * th).reshape(th, tw)
            img[y:y + th, x:x + tw] = tile[:min(th, h - y), :min(tw, w - x)]
    black = float(np.mean(t[50714])) if 50714 in t else 0.0
    return img.astype(np.float32) - black


def cfa_to_gray(mosaic: np.ndarray) -> np.ndarray:
    """2x2 Bayer cells summed (half resolution: no demosaicking artefacts on point sources)."""
    h, w = mosaic.shape[0] // 2 * 2, mosaic.shape[1] // 2 * 2
    m = mosaic[:h, :w]
    return m[0::2, 0::2] + m[0::2, 1::2] + m[1::2, 0::2] + m[1::2, 1::2]


def load_photo(path: str) -> Tuple[np.ndarray, str]:
    """A photo as a float32 gray image (linear for DNG, the JPEG's DN for .insp/.jpg) and its kind."""
    import cv2
    if path.lower().endswith(".dng"):
        return cfa_to_gray(read_dng(path)), "dng"
    data = np.fromfile(path, np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)                  # .insp = JPEG + Insta360's trailer
    if img is None:
        raise ValueError(f"{path}: not a JPEG/INSP")
    return img.astype(np.float32), "jpeg"


def to_stream_geometry(gray: np.ndarray) -> np.ndarray:
    """Any 2:1 dual-fisheye photo resampled to 3840x1920 (area average: binning lowers the noise)."""
    import cv2
    h, w = gray.shape[:2]
    if abs(w / h - 2.0) > 0.02:
        raise ValueError(f"{w}x{h}: not a 2:1 dual-fisheye frame")
    if (w, h) == OUT_SIZE:
        return gray.astype(np.float32)
    interp = cv2.INTER_AREA if w > OUT_SIZE[0] else cv2.INTER_LINEAR
    return cv2.resize(gray.astype(np.float32), OUT_SIZE, interpolation=interp)


def to_8bit(gray: np.ndarray, dark: float, noise: float, top_sigma: float = 200.0) -> np.ndarray:
    """Linear stretch for the 8-bit solver: dark level → 8 DN, noise → ~1 DN (the stream's noise, so the detector's
    thresholds keep their meaning), clipped at top_sigma noise."""
    s = 1.0 / max(noise, 1e-6)
    out = 8.0 + (gray - dark) * s
    return np.clip(out, 0, min(255.0, 8.0 + top_sigma)).astype(np.uint8)


def circle_mask(shape, margin: float = 1.06) -> np.ndarray:
    """True outside both fisheye circles (with a margin): pixels that never see light, for the dark level."""
    from cn_pkg.sky360 import default_lenses
    h, w = shape[:2]
    sx, sy = w / OUT_SIZE[0], h / OUT_SIZE[1]
    yy, xx = np.mgrid[0:h, 0:w]
    out = np.ones((h, w), bool)
    for L in default_lenses():
        r = (L.f * sx) * (math.radians(100.0)) * margin
        out &= np.hypot(xx - L.cx * sx, yy - L.cy * sy) > r
    return out


def noise_stats(gray: np.ndarray, mask: Optional[np.ndarray] = None) -> dict:
    """Dark level (median) and noise (robust sigma of pixel-to-pixel differences / sqrt 2) where mask is True
    (default: outside both circles: pure sensor + encoder)."""
    g = np.asarray(gray, np.float32)
    if mask is None:
        if "cn_pkg" not in sys.modules:
            sys.path.insert(0, os.path.join(ROOT, "cn_pkg"))
        mask = circle_mask(g.shape)
    d = (g[:, 1:] - g[:, :-1])[mask[:, 1:] & mask[:, :-1]]
    v = g[mask]
    if v.size < 100:
        return {"n": int(v.size)}
    mad = float(np.median(np.abs(d - np.median(d))))
    return {"n": int(v.size), "dark": float(np.median(v)), "noise": 1.4826 * mad / math.sqrt(2.0),
            "std": float(v.std()), "p99_9": float(np.percentile(v, 99.9))}


def ingest(paths: List[str], out: str, up: Optional[List[float]] = None, t_exp: Optional[float] = None,
           shots: Optional[List[dict]] = None) -> List[dict]:
    """Photos → out/index.jsonl + 8-bit PNGs in the stream's geometry (and a float .npy of each for deep work).
    'up' and the exposure time: from the matching `shoot` record (same file name), else up / t_exp given, else
    the file's modification time (marked)."""
    import cv2
    if "cn_pkg" not in sys.modules:
        sys.path.insert(0, os.path.join(ROOT, "cn_pkg"))
    os.makedirs(out, exist_ok=True)
    by_name = {}
    for s in shots or []:
        for f in s.get("files", []):
            by_name[os.path.basename(f)] = s
    rows = []
    for k, p in enumerate(sorted(paths)):
        gray, kind = load_photo(p)
        g = to_stream_geometry(gray)
        st = noise_stats(g)
        if "dark" not in st:
            raise ValueError(f"{p}: no pixels outside the circles for the dark level")
        name = f"still_{k:04d}"
        # DNG: linear sensor units, stretched so its noise is ~1 DN; JPEG/INSP: already the camera's 8-bit DN (its
        # compression can flatten the dark noise to 0 DN, measured on the stream: no stretch by that)
        scale = max(st["noise"], 1e-3) if kind == "dng" else 1.0
        cv2.imwrite(os.path.join(out, name + ".png"), to_8bit(g, st["dark"], scale))
        np.save(os.path.join(out, name + ".npy"), g.astype(np.float32))
        s = by_name.get(os.path.basename(p), {})
        row = {"image": name + ".png", "source": os.path.abspath(p), "kind": kind,
               "size_in": [int(gray.shape[1]), int(gray.shape[0])], "dark": round(st["dark"], 3),
               "noise": round(st["noise"], 4)}
        row["up_imu"] = s.get("up_imu") or up
        if s.get("t_exp"):
            row["t_exp"], row["time_source"] = s["t_exp"], "shoot record"
        elif t_exp is not None:
            row["t_exp"], row["time_source"] = t_exp, "given"
        else:
            row["t_exp"], row["time_source"] = os.path.getmtime(p), "file time (check the camera clock)"
        rows.append(row)
    with open(os.path.join(out, "index.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--out")
    p.add_argument("--diff", help="an earlier probe JSON: print the fields that changed")
    p = sub.add_parser("shoot")
    p.add_argument("--out", required=True)
    p.add_argument("--wait", type=float, default=35.0, help="exposure + saving time to wait for the reply (s)")
    p.add_argument("--set-hex", help="SET_PHOTOGRAPHY_OPTIONS body (hex), found with probe --diff")
    p = sub.add_parser("ingest")
    p.add_argument("photos", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--up", help="X,Y,Z 'up' in the IMU frame when no shoot record has it")
    p.add_argument("--t-exp", type=float)
    p.add_argument("--shots", help="shots.jsonl written by shoot")
    p = sub.add_parser("noise")
    p.add_argument("images", nargs="+")
    a = ap.parse_args(argv)

    if a.cmd == "noise":
        for path in a.images:
            if path.endswith(".npy"):
                g = np.load(path)
            else:
                g = to_stream_geometry(load_photo(path)[0])
            print(path, json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in noise_stats(g).items()}))
        return 0
    if a.cmd == "ingest":
        shots = []
        if a.shots:
            with open(a.shots) as fh:
                shots = [json.loads(line) for line in fh if line.strip()]
        up = [float(v) for v in a.up.split(",")] if a.up else None
        for r in ingest(a.photos, a.out, up, a.t_exp, shots):
            print(json.dumps(r))
        return 0
    cam = LongExpCamera()
    try:
        if a.cmd == "probe":
            res = probe(cam)
            text = json.dumps(res, indent=1)
            if a.out:
                with open(a.out, "w") as fh:
                    fh.write(text)
            print(text)
            if a.diff:
                with open(a.diff) as fh:
                    old = json.load(fh)
                for name in res:
                    if name == "notifications":
                        continue
                    o = ((old.get(name) or {}).get("reply") or {}).get("fields")
                    n = ((res.get(name) or {}).get("reply") or {}).get("fields")
                    for line in pb_diff(o, n, name):
                        print("CHANGED", line)
        else:
            os.makedirs(a.out, exist_ok=True)
            rec = shoot(cam, a.wait, bytes.fromhex(a.set_hex) if a.set_hex else None)
            with open(os.path.join(a.out, "shots.jsonl"), "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(json.dumps(rec, indent=1))
    finally:
        cam.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
