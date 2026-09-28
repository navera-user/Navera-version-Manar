"""MAVLink GPS_INPUT (id 232) fields for PX4 / ArduPilot (GPS_TYPE = MAV).

Accuracies are sent as stated (1-sigma, m); anything unknown is marked with the
corresponding ignore flag instead of a made-up number. Velocity is not known
from NAVERA positions and is always ignored.
"""
import math
from datetime import datetime, timezone

from navera_output.policy import KIND_ESTIMATED, KIND_FIX, Output

# GPS_INPUT_IGNORE_FLAGS
IGNORE_ALT = 1
IGNORE_HDOP = 2
IGNORE_VDOP = 4
IGNORE_VEL_HORIZ = 8
IGNORE_VEL_VERT = 16
IGNORE_SPEED_ACCURACY = 32
IGNORE_HORIZONTAL_ACCURACY = 64
IGNORE_VERTICAL_ACCURACY = 128

# GPS_FIX_TYPE
FIX_NO_FIX = 1
FIX_2D = 2
FIX_3D = 3

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
GPS_UTC_LEAP_S = 18        # GPS - UTC since 2017-01-01
UERE_M = 2.0


def gps_week_time(t_utc: datetime):
    """(week, ms of week) in GPS time."""
    s = (t_utc - GPS_EPOCH).total_seconds() + GPS_UTC_LEAP_S
    week = int(s // (7 * 86400))
    return week, int(round((s - week * 7 * 86400) * 1000))


def gps_input_fields(out: Output, t_utc: datetime) -> dict:
    """Keyword arguments for mav.gps_input_send()."""
    week, week_ms = gps_week_time(t_utc)
    ignore = IGNORE_VEL_HORIZ | IGNORE_VEL_VERT | IGNORE_SPEED_ACCURACY
    fields = dict(time_usec=int(t_utc.timestamp() * 1e6), gps_id=0, time_week_ms=week_ms,
                  time_week=week, lat=0, lon=0, alt=0.0, hdop=0.0, vdop=0.0,
                  vn=0.0, ve=0.0, vd=0.0, speed_accuracy=0.0, horiz_accuracy=0.0,
                  vert_accuracy=0.0, satellites_visible=0)
    if out.kind not in (KIND_FIX, KIND_ESTIMATED):
        fields.update(fix_type=FIX_NO_FIX,
                      ignore_flags=ignore | IGNORE_ALT | IGNORE_HDOP | IGNORE_VDOP
                      | IGNORE_HORIZONTAL_ACCURACY | IGNORE_VERTICAL_ACCURACY)
        return fields

    fields.update(lat=int(round(out.lat * 1e7)), lon=int(round(out.lon * 1e7)),
                  satellites_visible=out.satellites if out.satellites is not None else 0)
    msl = out.alt_msl_m
    if math.isfinite(msl):
        fields["alt"] = float(msl)
        fix_type = FIX_3D
    else:
        ignore |= IGNORE_ALT
        fix_type = FIX_2D
    if math.isfinite(out.sigma_h_m):
        fields["horiz_accuracy"] = float(out.sigma_h_m)
        fields["hdop"] = float(min(out.sigma_h_m / UERE_M, 99.9))
    else:
        ignore |= IGNORE_HORIZONTAL_ACCURACY | IGNORE_HDOP
    if math.isfinite(out.sigma_v_m):
        fields["vert_accuracy"] = float(out.sigma_v_m)
        fields["vdop"] = float(min(out.sigma_v_m / UERE_M, 99.9))
    else:
        ignore |= IGNORE_VERTICAL_ACCURACY | IGNORE_VDOP
    fields.update(fix_type=fix_type, ignore_flags=ignore)
    return fields
