# Lab 2 — answers. Find each answer WITH THE TERMINAL, write it here, save (Ctrl+S).
#   - numbers without quotes:            Q1 = 42
#   - text and paths between quotes:     Q2 = "navera_msgs/msg/Example.msg"
# Paths: "~/navera/x", "/home/student/navera/x" and "x" (from inside ~/navera) are the SAME
# file, and all three forms are accepted. ~ is a short name for /home/student.

# ---- Environment variables (echo $NAME) ----
# E1. The value of ROS_DOMAIN_ID in your terminal (a number).
E1 = -1
# E2. The value of NAVERA_MBTILES (the path of the satellite map), in quotes.
E2 = ""

# ---- Exploring ~/navera (find, grep, wc, xargs) ----
# Q1. How many Python files (*.py) are in ~/navera/day_pkg, ALL sub-folders included?
Q1 = 0
# Q2. The path of the source file PositionEstimate.msg (not a copy in build/ or install/).
Q2 = ""
# Q3. How many lines of Python, in total, in all the *.py files of ~/navera/navera_estimator?
Q3 = 0
# Q4. How many systemd unit files (names ending in .service) are in ~/navera/deploy/systemd?
Q4 = 0
# Q5. Which package folder of ~/navera holds the file nmea.py? Just the name, e.g. "camera_pkg".
Q5 = ""

# ---- Reading the flight logs ----
# Q6. In the Sousse log, which node wrote the most WARN lines? Just the name, e.g. "imu_node".
Q6 = ""
# Q7. In the Sousse log, at what time (Tunisian time, "HH:MM:SS") did the arbiter FIRST report
#     "state NO_FIX"?
Q7 = ""

# ---- Permissions and signals ----
# Q8. The octal (number) form of the permissions  rw-r-----  (e.g. 755).
Q8 = 0
# Q9. The name of the signal that Ctrl+C sends to the program in the foreground, e.g. "SIGHUP".
Q9 = ""
