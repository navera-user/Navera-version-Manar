# Liveness of a single navigation source, as seen by navera_estimator.
# Answers: is it there, when did we last hear it, and is it in the solution?
# One of these rows exists per watched source inside NavStatus.sources[].

# Which source this row describes.
# Values MUST match navera_msgs/PositionEstimate (append-only -- keep in sync).
uint8 source
uint8 SOURCE_UNKNOWN=0
uint8 SOURCE_GPS=1
uint8 SOURCE_DAY_VISION=2
uint8 SOURCE_NIGHT_VISION=3
uint8 SOURCE_CELESTIAL=4
uint8 SOURCE_INERTIAL=5
uint8 SOURCE_FUSED=6
uint8 SOURCE_VLM=7                       # reserved
uint8 SOURCE_EXTERNAL=8                  # reserved (datalink, operator entry)

bool alive                               # heard from within this source's liveness timeout
builtin_interfaces/Time last_seen        # stamp of the last message from this source; zero if never heard
bool contributing                        # true iff this source feeds the CURRENT published solution
