# Lab 20 — the teacher's answers (reference run on the course's Jetson, 2026-10-13). Numbers recomputed by the
# reference stack; DECODE_MS depends on the computer (the check only tests that CORES_ALL_FRAMES matches it).

PREDICT_ERROR = "About 8 m: 4 degrees of roll error seen from 120 m."

DECODE_MS = 15.6
CORES_ALL_FRAMES = 0.45
EXPLAIN_DECODE = ("Decoding a 1080p JPEG costs about 16 ms of CPU each time; decoding all 28.8 frames per second "
                  "would keep half a core busy for nothing, because vision only needs one frame per second. Grabbing "
                  "every frame is cheap and keeps the newest frame and its time.")

FPS_LOG = 28.27
DROPPED_LOG = 32
JITTER_40S_MS = 5.00
JITTER_60S_MS = 9.72
EXPLAIN_JITTER = ("The last 20 s contain a 0.38 s stall; the standard deviation squares every difference, so one "
                  "long gap almost doubles it. The median period (34.8 ms) describes the normal rhythm; the jitter "
                  "and the largest gap describe the risk of having no picture.")

PREDICT_DELAY = "No, they will spread by a few tens of milliseconds."
DELAY_MEDIAN_MS = 156.3
DELAY_MIN_MS = 141.1
UNSEEN_FLASH = 8
OUTLIER_FLASH = 14
EXPLAIN_SPREAD = ("The flash happens at a random moment between two exposures, so the camera waits between 0 and one "
                  "frame period (34.7 ms) for the next exposure that sees it; that wait w is random even with "
                  "perfect clocks.")

PREDICT_PHASE = "About −1: a flash later in the frame period waits less for the next exposure."
PHASE_SLOPE = -0.99
EXPLAIN_PHASE = ("A slope of −1 means the spread is not noise: each millisecond the flash comes later after the last "
                 "grab, it waits one millisecond less for the next exposure. The delays spread over one frame period "
                 "because of where the flash falls between two frames.")

LATENCY_SETTING_S = 0.119
EXPLAIN_LATENCY = ("The median 156.3 ms still contains the screen's own delay (20 ms) and on average half a frame "
                   "period (17.4 ms) of waiting for the next exposure, so L = 156.3 − 17.4 − 20 = 119 ms. The "
                   "minimum minus the screen (121 ms) agrees, but it rests on one flash.")

BUDGET_500_M = 13.64
ALONG_60_M = 2.08
DT_FOR_30M_S = 0.45
EXPLAIN_BUDGET = ("The ground error is h·tan(ω·δt): the same angle error moves a point farther on the ground when the "
                  "camera is higher, and the angle error itself is the rotation rate times the time error, so it is "
                  "zero in straight, level flight and grows in a turn.")

PREDICT_METHODS = "Worst: held at the grab; then the nearest sample; best: slerp at the exposure, for both settings."
GRAB_MEDIAN_M = 3.28
COPIED_MEDIAN_M = 0.54
MINE_MEDIAN_M = 0.05
EXPLAIN_TURN = ("It is most wrong when the plane rolls into or out of a bank, at 3–5 s and 17–18 s: the attitude "
                "changes fast then, and the sample held at the grab is the attitude 0.12 s after the exposure, so "
                "its error is the rotation rate times the delay.")

STEADY_RATE_DPS = 12.98
EXPLAIN_STEADY = ("A banked plane is turning: its heading changes at g·tan(30°)/25 m/s = 0.227 rad/s = 13 °/s, so the "
                  "attitude still rotates although the roll is constant. The sample held at the grab is 0.12 s too new, "
                  "13 × 0.12 ≈ 1.5° of heading-and-bank error, about 3.5–4 m at 150 m.")

N_TURNING = 23
N_TILTED = 69
N_NO_ATTITUDE = 7
EXPLAIN_REFUSE = ("What is left of the timing error is not zero: the delay is known to a few ms, the exposure lasts "
                  "a few ms (blur) and a rolling shutter exposes rows at different times. Each leftover millisecond "
                  "costs h·tan(ω·δt), which grows with the rate: at 60 °/s it is too large.")

BEST_LATENCY_S = 0.118
EXPLAIN_SCAN = ("The flight prefers 0.118 s, close to my bench setting of 0.119 s, so the bench and its correction "
                "agree. A real plane cannot run this scan because it has no true attitude to compare with; only a "
                "simulator knows the truth.")

QUEUE_WAITED_S = 1.98
EXPLAIN_QUEUE = ("With a queue the frame waited about 2 s in the buffer before the program took it, but the program "
                 "stamps it now − latency, so the stamp does not know about the waiting time and the attitude is read "
                 "2 s too late. The refusal rules only look at the attitude and rate at the stamped instant, which "
                 "look normal (a steady bank, 13 °/s): nothing in them knows that the frame is old, so every stale "
                 "frame is accepted.")

LOOK_BACK = ""
