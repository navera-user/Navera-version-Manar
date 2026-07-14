# A geodetic position estimate produced by ONE source, carrying its provenance
# and its uncertainty. This is the single contract consumed by the arbiter
# (navera_estimator) and by the operator interface.
#
# Two rules govern this message:
#   1. position_covariance is the only quantity that may be fused mathematically.
#      confidence is source-local and NOT comparable across sources.
#   2. Nothing may make a decision based on details_json. If a value becomes
#      decisional, promote it to a typed field.

# ---------- WHERE ----------

# stamp = publication instant. frame_id = the sensor frame this came from.
std_msgs/Header header

float64 latitude                        # deg, WGS84
float64 longitude                       # deg, WGS84
float64 altitude                        # m above the WGS84 ellipsoid; NaN if unknown

# 3x3 ENU (east, north, up) covariance, row-major, in m^2. Same convention as
# sensor_msgs/NavSatFix, so the adapter to robot_localization is an array copy.
float64[9] position_covariance

# How much position_covariance can be trusted. Publish UNKNOWN rather than an
# invented matrix: a fabricated covariance is indistinguishable from a measured
# one downstream.
uint8 position_covariance_type
uint8 COVARIANCE_TYPE_UNKNOWN=0
uint8 COVARIANCE_TYPE_APPROXIMATED=1
uint8 COVARIANCE_TYPE_DIAGONAL_KNOWN=2
uint8 COVARIANCE_TYPE_KNOWN=3

# ---------- WHO ----------

uint8 source
uint8 SOURCE_UNKNOWN=0
uint8 SOURCE_GPS=1
uint8 SOURCE_DAY_VISION=2
uint8 SOURCE_NIGHT_VISION=3
uint8 SOURCE_CELESTIAL=4
uint8 SOURCE_INERTIAL=5
uint8 SOURCE_FUSED=6
uint8 SOURCE_VLM=7                      # reserved
uint8 SOURCE_EXTERNAL=8                 # reserved (datalink, operator entry)

# ---------- HOW ----------

# Whether this position is a fresh measurement, an extrapolation, a stale echo,
# or replayed ground truth. A MODE_REPLAYED or MODE_HELD estimate must never be
# able to pass itself off as a measurement.
uint8 mode
uint8 MODE_MEASURED=0                   # freshly computed by the source
uint8 MODE_PROPAGATED=1                 # dead-reckoned from an earlier fix
uint8 MODE_HELD=2                       # last value re-emitted; NO new information
uint8 MODE_REPLAYED=3                   # dataset ground truth; NEVER valid in flight

# ---------- WHAT IT IS WORTH ----------

bool valid                              # false = do not use this position
float64 confidence                      # [0,1], source-local, NOT cross-comparable
string reason                           # why rejected/degraded; for humans, never parsed

# ---------- WHEN ----------

# Instant of the MEASUREMENT itself (image exposure, NMEA sentence), as opposed
# to header.stamp which is the publication instant. The difference is the
# latency an estimator needs in order to fuse correctly.
builtin_interfaces/Time sensor_stamp

# ---------- TRACEABILITY ----------

string producer                         # emitting node, e.g. "day_subscriber"
string model_id                         # algorithm/weights version, e.g. "dinov2_vits14+gem"
int32 frame_index                       # camera pipeline frame_id; -1 if not applicable

# Escape hatch for source-specific extras (GPS hdop/num_sats, DINOv2 top5,
# STHN rms_px). Diagnostic and traceability only — see rule 2 above.
string details_json
