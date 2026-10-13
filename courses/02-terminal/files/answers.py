# Lab 2 — answers. Find each answer WITH THE TERMINAL, write it here, save (Ctrl+S).
#   numbers without quotes:          Q1 = 42
#   text and paths between quotes:   Q2 = "navera_lite/example.py"
# PREDICT_… : your guess, written BEFORE you run the step (never marked right or wrong).
# EXPLAIN_… : one to three sentences in your own words (your teacher reads them).

# ============================== Session 1 — the box on the bench

# ---- Step 2: the NAVERA Lite skeleton (/data/academy/02-terminal/navera_lite_tree) ----
# Paths are relative to the skeleton's top folder, e.g. "navera_lite/geo.py".
# Q1. How many Python files (*.py) does the SOURCE package navera_lite/ hold, all sub-folders included?
Q1 = 0
# Q2. The path of the source file that will define the function mahalanobis2 (not a copy).
Q2 = ""
# Q3. How many lines, in total, do all the *.py files of navera_lite/ros/ have?
Q3 = 0
# Q4. How many systemd unit files (names ending in .service) are in deploy/systemd/?
Q4 = 0
# Q5. Which part file says that you write it in mission 17? Just its name, e.g. "geo.py".
Q5 = ""

# ---- Step 4: permissions ----
# P1. The octal mode of the serial port /dev/ttyTHS1 in the evidence (e.g. 755).
P1 = 0
# P2. The name of the group that the GPS service's user is missing.
P2 = ""
# P3. The octal mode of YOUR mission/bin/preflight.sh now, after your chmod (read it on ls -l).
P3 = 0

# ---- Step 5: environment ----
# E1. The value of ROS_DOMAIN_ID in your terminal (a number).
E1 = -1
# E2. The value of NAVERA_LITE_MAP (the path of the map), in quotes.
E2 = ""

# ---- Step 6: the orphan arbiter and the hung camera ----
# PREDICT_PKILL. Before you stop anything: what would `pkill -f navera_lite_arbiter` do on this box,
#   exactly (which processes, and what happens a second later)?
PREDICT_PKILL = ""
# ORPHAN_PPID. The PPID that ps shows for the orphan arbiter.
ORPHAN_PPID = -1
# EXPLAIN_ORPHAN. How did you know which arbiter was the orphan? Give two clues.
EXPLAIN_ORPHAN = ""
# KILL_EXIT_CODE. The exit code the supervisor wrote in the journal for the camera reader you killed.
KILL_EXIT_CODE = 0
# EXPLAIN_KILL. Why did SIGTERM not stop the camera reader while SIGKILL did, why did it write no last
#   message, and what did the supervisor do next?
EXPLAIN_KILL = ""

# ============================== Session 2 — the flight logs

# PREDICT_UNIQ. Without `sort`, how many lines would `… | cut -d' ' -f3 | uniq -c` print for the WARN
#   lines of the Sousse log: 3, about 10, about 40, or 84? Why?
PREDICT_UNIQ = ""
# Q6. In the Sousse log, which node wrote the most WARN lines? Just the name, e.g. "imu".
Q6 = ""
# Q7. In the Sousse log, at what time (Tunisian time, "HH:MM:SS") did the arbiter FIRST report "state NO_FIX"?
Q7 = ""
# Q8. How many DIFFERENT nodes wrote at least one ERROR line, in the two logs together?
Q8 = 0
