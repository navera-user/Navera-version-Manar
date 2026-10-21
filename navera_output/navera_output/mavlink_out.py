"""MAVLink GPS_INPUT (id 232) fields for PX4 / ArduPilot (GPS_TYPE = MAV).

Accuracies are sent as stated (1-sigma, m); anything unknown is marked with the
corresponding ignore flag instead of a made-up number — except the horizontal velocity.

Horizontal velocity (F28): every non-GNSS position goes out with one and its
speed_accuracy — NAVERA's own track velocity, or, when NAVERA does not know it,
"unknown": 0 m/s with the vehicle's top speed as its accuracy; a GPS position with the
receiver's. A GPS fix without a receiver velocity is the only position sent with the
flag set (an "unknown" accuracy > 1 m/s would keep ArduPilot from setting its origin),
and a "no fix" message (fix_type 1, which ArduPilot's EKF never reads). Otherwise the
flag is never used: ArduPilot's MAVLink GPS (AP_GPS_MAV.cpp) keeps the last velocity
and the last speed accuracy it received when a message flags them ignored, and EKF3
resets its velocity to that value (with that accuracy, or 0.3 m/s without one) when a
position comes back after a timeout (ResetVelocity) — even with EK3_SRC1_VELXY = 0.
Vertical velocity is never sent: NAVERA measures none (vision has no height, NMEA RMC
none), and ArduPilot never clears its have_vertical_velocity once one was received.

fix_type without altitude: a vision or celestial position has no altitude
(IGNORE_ALT is set). A 2D fix is the literal label, but ArduPilot and PX4 only
fuse a GPS position at fix_type >= 3, so a 2D fix is never used. The default
(3) sends such a position as 3D with the altitude flagged ignored: the
autopilot must then take its height from the barometer (ArduPilot
EK3_SRC1_POSZ = 1, the default; PX4 EKF2_HGT_REF = baro).

Only a satellite (GNSS) position ever carries an altitude: a non-GNSS one is always
sent with IGNORE_ALT, even if its producer attached a height, so NAVERA can never
hand the autopilot a vision height (F7). ArduPilot then reads the altitude as 0 m:
harmless with EK3_SRC1_POSZ = 1 (verified in SITL, navera_tools/tests/sitl_f7_height.py),
wrong with EK3_SRC1_POSZ = 3 or EK3_OGN_HGT_MASK, which must therefore never be set.
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


def gps_input_fields(out: Output, t_utc: datetime, fix_type_without_alt: int = FIX_3D) -> dict:
    """Keyword arguments for mav.gps_input_send()."""
    if fix_type_without_alt not in (FIX_2D, FIX_3D):
        raise ValueError("fix_type_without_alt must be 2 or 3")
    week, week_ms = gps_week_time(t_utc)
    ignore = IGNORE_VEL_VERT | IGNORE_SPEED_ACCURACY
    fields = dict(time_usec=int(t_utc.timestamp() * 1e6), gps_id=0, time_week_ms=week_ms,
                  time_week=week, lat=0, lon=0, alt=0.0, hdop=0.0, vdop=0.0,
                  vn=0.0, ve=0.0, vd=0.0, speed_accuracy=0.0, horiz_accuracy=0.0,
                  vert_accuracy=0.0, satellites_visible=0)
    if out.kind not in (KIND_FIX, KIND_ESTIMATED):
        fields.update(fix_type=FIX_NO_FIX,
                      ignore_flags=ignore | IGNORE_VEL_HORIZ | IGNORE_ALT | IGNORE_HDOP | IGNORE_VDOP
                      | IGNORE_HORIZONTAL_ACCURACY | IGNORE_VERTICAL_ACCURACY)
        return fields

    fields.update(lat=int(round(out.lat * 1e7)), lon=int(round(out.lon * 1e7)),
                  satellites_visible=out.satellites if out.satellites is not None else 0)
    msl = out.alt_msl_m if out.gnss else math.nan
    if math.isfinite(msl):
        fields["alt"] = float(msl)
        fix_type = FIX_3D
    else:
        ignore |= IGNORE_ALT
        fix_type = fix_type_without_alt
    if out.has_velocity:
        fields.update(vn=float(out.vel_n_mps), ve=float(out.vel_e_mps))
    if math.isfinite(out.vel_sigma_mps):
        fields["speed_accuracy"] = float(out.vel_sigma_mps)     # unknown: vn = ve = 0 +- this
        ignore &= ~IGNORE_SPEED_ACCURACY
    elif not out.has_velocity:
        ignore |= IGNORE_VEL_HORIZ                              # nothing stated at all
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
