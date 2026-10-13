# Lab 13 — teacher solution (measured in the sandbox, 2026-10-13). Written answers are examples.

# ======== Session 1 — Guard the knobs ========
PREDICT_INT = "I think the judge will refuse the integer and stop, or maybe convert 30 to 30.0 silently."
SET_REPORTED_OK = True
STATE_AFTER_SET = "FIX"
EXPLAIN_SILENT = ("The judge reads its settings only once when it starts and builds its rules from them, so the "
                  "set changed the stored value but not the value it uses; it needs a restart.")

PREDICT_GUARDS = "rate_hz refused as read-only, 500 refused by the range, 150 at start refused by the range too."
RATE_SET_OK = False
SPEED_500_OK = False
START_150_RUNS = False

BOAT_25_OK = False
ATTACK_SPEED = 25.0
EXPLAIN_GUARDS = ("The callback is only called for changes made after it is registered, and start values are "
                  "declared before; only the range of the descriptor acts at start, so the start values need "
                  "their own check, like check_settings.")

N_INTEGRATOR_PROBLEMS = 4

# ======== Session 2 — One command ========
PREDICT_PRECEDENCE = "10.0, 18.0, 25.0, 18.0, 25.0"
SPEED_DEFAULT = 10.0
SPEED_FILE = 18.0
SPEED_FILE_THEN_P = 18.0
SPEED_P_THEN_FILE = 18.0
SPEED_TWO_FILES = 25.0
EXPLAIN_PRECEDENCE = ("-p writes into the /** row, which my_gps.yaml created above the /drone/fake_gps row, so "
                      "the lower drone row wins with 18.0; fast.yaml uses the same section name, so it "
                      "overwrites the drone row in place with 25.0.")

PREDICT_NO_BOAT = "The judge will say NO_FIX because the boat is missing."
NO_BOAT_STATE = "STARTING"
EXPLAIN_REMAP = ("The judge is remapped to /boat/navera_lite/fix/gps but no node publishes on that topic, so it "
                 "never receives a position and waits forever; no process crashed, so nothing warns the "
                 "operator.")

PREDICT_PLANE = "The jump gate will refuse the plane's fixes and the judge will lose GPS."
PLANE_STATE_30 = "NO_FIX"
PLANE_STATE_100 = "FIX"
EXPLAIN_R1 = ("With max_speed_mps 30 the jump gate allows 80 m per second but the plane flies 85 m, so its real "
              "fixes are refused as jumps and GPS goes stale; check_settings refuses a plane below 100 m/s "
              "before take-off.")

SIGMA_STATE = "DEGRADED"
SIGMA_MESSAGE = "gps: σ 3.0 m > 2.0 m"
