#!/usr/bin/env python3
"""mavlink_lab.py — decode what NAVERA sends to the autopilot, byte by byte (Part A).

    python3 mavlink_lab.py                       decode /data/academy/31-simulator/gps_input.bin
    python3 mavlink_lab.py some_other_file.bin

The file is a MAVLink 2 byte stream: one HEARTBEAT and one GPS_INPUT (id 232) per second of the
recorded sample flight, as NAVERA's vehicle_output would send them (see the lesson, section 3).
No pymavlink here: you write the decoder yourself with `struct` and bit operations.
"""
import struct
import sys
from datetime import datetime, timedelta, timezone

STREAM = "/data/academy/31-simulator/gps_input.bin"

STX_V2 = 0xFD
HEADER_LEN = 10                 # STX, len, incompat, compat, seq, sysid, compid, msgid (3 bytes)
SIGNATURE_LEN = 13              # present only when incompat_flags & 1
MSG_HEARTBEAT = 0
MSG_GPS_INPUT = 232
CRC_EXTRA = {MSG_HEARTBEAT: 50, MSG_GPS_INPUT: 151}

GPS_INPUT_FORMAT = "<QIiifffffffffHHBBBH"          # wire order (fields sorted by size)
GPS_INPUT_FIELDS = ("time_usec", "time_week_ms", "lat", "lon", "alt", "hdop", "vdop", "vn", "ve", "vd",
                    "speed_accuracy", "horiz_accuracy", "vert_accuracy", "ignore_flags", "time_week",
                    "gps_id", "fix_type", "satellites_visible", "yaw")
GPS_INPUT_LEN = struct.calcsize(GPS_INPUT_FORMAT)    # 65

IGNORE_FLAG_NAMES = ("ALT", "HDOP", "VDOP", "VEL_HORIZ", "VEL_VERT", "SPEED_ACCURACY",
                     "HORIZONTAL_ACCURACY", "VERTICAL_ACCURACY")   # bit 0, bit 1, ... bit 7

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
GPS_UTC_LEAP_S = 18


def crc_x25(data, crc=0xFFFF):
    """CRC-16/MCRF4XX ("X.25" in MAVLink) of the bytes `data`, starting from `crc`."""
    # TODO 1: for each byte b of data, apply the three lines of the lesson (section 3).
    #         Keep tmp on 8 bits (& 0xFF) and crc on 16 bits (& 0xFFFF).
    return 0


def parse_frames(data):
    """Split a MAVLink 2 byte stream into frames."""
    # TODO 2: walk through data with an index i:
    #   - data[i] != STX_V2 -> i += 1 and continue (resynchronise)
    #   - n = payload length (byte i+1); end = i + HEADER_LEN + n + 2; a signed frame (incompat & 1) has
    #     SIGNATURE_LEN more bytes after the checksum. Stop if the frame goes past the end of data.
    #   - msgid: 3 bytes little-endian at i+7, i+8, i+9 (use << and |)
    #   - crc_ok: if msgid is in CRC_EXTRA, CRC of bytes i+1 .. end of the payload, then continue the CRC
    #     with the one byte CRC_EXTRA[msgid]; compare with the 2 bytes at the end (little-endian).
    #     Unknown msgid -> crc_ok = None.
    #   - append dict(seq=..., sysid=..., compid=..., msgid=..., payload=bytes(...), crc_ok=...)
    #   - jump to the next frame
    return []


def decode_gps_input(payload):
    """The fields of a GPS_INPUT payload as a dict (lat / lon in degrees)."""
    # TODO 3: pad the payload with zero bytes up to GPS_INPUT_LEN (MAVLink 2 truncation!),
    #         struct.unpack(GPS_INPUT_FORMAT, ...), zip with GPS_INPUT_FIELDS into a dict,
    #         and convert lat / lon from degrees x 1e7 to degrees.
    return None


def ignored(flags):
    """Names of the ignore flags that are set, in bit order."""
    # TODO 4: the name IGNORE_FLAG_NAMES[bit] for every bit 0..7 set in flags (flags & (1 << bit))
    return []


def gps_time_to_utc(week, week_ms):
    """GPS week + milliseconds of the week -> UTC datetime (GPS time is 18 s ahead of UTC)."""
    # TODO 5: GPS_EPOCH + the weeks and milliseconds (datetime.timedelta), minus the leap seconds
    return None


def summarize(frames):
    """Counts for the report (see the lab, Step 4)."""
    good = [f for f in frames if f["msgid"] == MSG_GPS_INPUT and f["crc_ok"]]
    dec = [decode_gps_input(f["payload"]) for f in good]
    by_flags = {}
    for d in dec:
        if d["fix_type"] >= 3:
            by_flags[d["ignore_flags"]] = by_flags.get(d["ignore_flags"], 0) + 1
    return {
        "frames": len(frames),
        "bad_crc": sum(1 for f in frames if f["crc_ok"] is False),
        "heartbeats": sum(1 for f in frames if f["msgid"] == MSG_HEARTBEAT and f["crc_ok"]),
        "gps_input_ok": len(good),
        "fix_3d": sum(1 for d in dec if d["fix_type"] >= 3),
        "no_fix": sum(1 for d in dec if d["fix_type"] <= 1),
        "fix_by_ignore_flags": {str(k): v for k, v in sorted(by_flags.items())},
        "lost_frames": lost_frames(frames),
    }


# ---- you don't need to change anything below this line (but you can read it!) ----

def lost_frames(frames):
    """Frames missing according to the sequence numbers (seq counts 0..255 and wraps)."""
    lost = 0
    for a, b in zip(frames, frames[1:]):
        lost += (b["seq"] - a["seq"] - 1) % 256
    return lost


def main(path):
    with open(path, "rb") as f:
        data = f.read()
    print(f"{path}: {len(data)} bytes")
    print(f"crc_x25(b'123456789') = {crc_x25(b'123456789'):#06x}   (the standard check value is 0x6f91)")
    frames = parse_frames(data)
    if not frames:
        print("parse_frames() found no frame: complete TODO 2")
        return
    for f in frames[:4]:
        print(f"  seq {f['seq']:3d} sys {f['sysid']} comp {f['compid']} msgid {f['msgid']:3d} "
              f"len {len(f['payload']):2d} crc_ok {f['crc_ok']}")
    g = [f for f in frames if f["msgid"] == MSG_GPS_INPUT and f["crc_ok"]]
    if g and decode_gps_input(g[100]["payload"]) is not None:
        d = decode_gps_input(g[100]["payload"])
        print(f"GPS_INPUT #100: lat {d['lat']:.7f} lon {d['lon']:.7f} fix_type {d['fix_type']} "
              f"horiz_accuracy {d['horiz_accuracy']:.1f} m ignore {d['ignore_flags']} {ignored(d['ignore_flags'])}")
        t = gps_time_to_utc(d["time_week"], d["time_week_ms"])
        print(f"  GPS week {d['time_week']} + {d['time_week_ms']} ms = {t} UTC")
    print("summary:", summarize(frames))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else STREAM)
