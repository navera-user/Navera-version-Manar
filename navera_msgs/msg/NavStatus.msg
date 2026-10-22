# The navigation system's decisional summary, published by navera_estimator.
# This is the ONE authoritative answer to three operator questions:
#   1. Do we have a usable position right now, and how much do we trust it?  -> state
#   2. Who is providing it, and is it a real measurement or an echo?         -> active_source, active_mode
#   3. Which sources are alive, and when did we last hear from each?         -> sources[]
#
# The same two rules that govern PositionEstimate govern this message:
#   1. It is TYPED. Nothing downstream may make a decision on free text.
#      If a value becomes decisional, it is a field here, not prose in reason.
#   2. "No source" is a first-class state (INITIALIZING / NO_FIX), never a
#      crash and never a stale point held in silence.

# stamp = instant this status was computed.
std_msgs/Header header

# ---------- 1. DO WE HAVE A FIX, AND HOW GOOD? ----------

uint8 state
uint8 STATE_INITIALIZING=0   # since boot / before mission start: no solution YET. Expected, transient.
uint8 STATE_NO_FIX=1         # running, but NO source is currently usable. First-class, not an error.
uint8 STATE_FIX=2            # a fresh MEASURED position whose uncertainty is BOUNDED
                             # (position_covariance_type != UNKNOWN). The green light means
                             # "you may rely on this AND on its stated error" -- e.g. a GPS fix.
uint8 STATE_DEGRADED=3       # a position is published but trust is reduced. Two triggers today:
                             #   1. MEASURED but uncertainty UNKNOWN -- a real fix we cannot yet
                             #      bound (e.g. day vision: DINOv2 recognises terrain but has no
                             #      validated sigma). Reporting it as FIX would let a ~500 m guess
                             #      wear the same green label as a metric GPS lock -- the exact
                             #      mislabelling this contract exists to prevent.
                             #   2. PROPAGATED / HELD -- dead-reckoned or re-emitted, not fresh.
                             # NOTE: "single source" is DELIBERATELY NOT a trigger. In GPS-denied
                             # nav exactly one source contributes at a time (source hierarchy), so
                             # single-source => DEGRADED would make STATE_FIX unreachable -- a state
                             # that can never fire carries no information. The single-source clause
                             # only becomes meaningful once SOURCE_FUSED exists and FIX can mean
                             # "corroborated by several sources".

# ---------- 2. WHO IS PROVIDING IT, AND HOW FRESH? ----------

# The source that owns the currently published solution. SOURCE_UNKNOWN while
# state is INITIALIZING or NO_FIX.
# Values MUST match navera_msgs/PositionEstimate (append-only -- keep in sync).
uint8 active_source
uint8 SOURCE_UNKNOWN=0
uint8 SOURCE_GPS=1
uint8 SOURCE_DAY_VISION=2
uint8 SOURCE_NIGHT_VISION=3
uint8 SOURCE_CELESTIAL=4
uint8 SOURCE_INERTIAL=5
uint8 SOURCE_FUSED=6
uint8 SOURCE_VLM=7                      # reserved
uint8 SOURCE_EXTERNAL=8                 # reserved (datalink, operator entry)

# Freshness of the current solution, mirrored from the winning estimate.
# A HELD or REPLAYED solution can NEVER be reported as MEASURED.
# Values MUST match navera_msgs/PositionEstimate (append-only -- keep in sync).
uint8 active_mode
uint8 MODE_MEASURED=0                    # freshly computed by the active source
uint8 MODE_PROPAGATED=1                  # dead-reckoned from an earlier fix
uint8 MODE_HELD=2                        # last value re-emitted; NO new information
uint8 MODE_REPLAYED=3                    # dataset ground truth; NEVER a real-flight fix

# ---------- 3. WHO IS ALIVE? ----------

# One entry per source the estimator watches (GPS, day, night, celestial, IMU...).
# Liveness only: a source can be alive without contributing a position -- the IMU
# today proves it is alive but publishes no fix (contributing = false).
SourceHealth[] sources

# ---------- 4. ARE WE STILL OVER THE MAP? (mission-area guard: reported, never acted on) ----------

# Day vision matches against the mission's map only: past its edge it has nothing to match.
# Computed from the published position against the map's tiles (navera_common.map_area).
uint8 map_area
uint8 MAP_AREA_UNKNOWN=0                # no map loaded, or no position
uint8 MAP_AREA_INSIDE=1
uint8 MAP_AREA_NEAR_EDGE=2              # closer to the edge than map_edge_warn_m (estimator parameter)
uint8 MAP_AREA_OUTSIDE=3                # beyond the mapped area
float32 map_edge_m                      # distance to the map's edge, m: > 0 inside, < 0 outside, NaN unknown

# ---------- FOR HUMANS ----------

string reason                           # one line explaining the current state; for display, never parsed
