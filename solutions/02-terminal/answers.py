# Lab 2 — answers (solution). E1, P3 and ORPHAN_PPID are written by _apply.sh (they depend on the sandbox).

Q1 = 54
Q2 = "navera_lite/uncertainty.py"
Q3 = 134
Q4 = 4
Q5 = "imu.py"

P1 = 660
P2 = "dialout"
P3 = 0

E1 = -1
E2 = "/data/map.mbtiles"

PREDICT_PKILL = "Both arbiters get SIGTERM; the supervisor restarts its own one a second later, the orphan stays dead."
ORPHAN_PPID = 1
EXPLAIN_ORPHAN = ("Its PPID was 1: the simulator launcher that started it had ended, while the other arbiter's "
                  "parent was the box's supervisor. Its command line used sim.yaml, and the journal shows "
                  "sim_launcher started it. It was the younger one, so 'kill the oldest' would have been wrong.")
KILL_EXIT_CODE = 137
EXPLAIN_KILL = ("The hung reader caught SIGTERM and kept waiting for the driver; SIGKILL cannot be caught, so "
                "the kernel ended it at once without a last message. The supervisor saw exit code 137 and "
                "started a new reader that works.")

PREDICT_UNIQ = "About 40: uniq only merges neighbouring identical lines, and the nodes alternate."
Q6 = "day_vision"
Q7 = "08:45:24"
Q8 = 3
