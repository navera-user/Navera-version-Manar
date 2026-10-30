# NAVERA Lite — the skeleton

This is the map of the stack you build in this course, one part per mission. Every file is here
with its name and a one-line description of what it will hold; there is no code yet (`...`).
Names may still change a little: in each mission, your lesson folder is the reference.

| Folder | What |
|---|---|
| `navera_lite/` | the Python package: one file per part (`geo.py` in mission 06, …) |
| `navera_lite/ros/` | the ROS 2 nodes (missions 09–31) |
| `navera_lite/sim/` | the headless simulator (mission 31) |
| `navera_lite/tests/` | the tests (pytest, mission 14) |
| `navera_lite.yaml` | the settings, a ROS 2 params file |
| `config/` | settings of single nodes |
| `deploy/` | how a box runs it: systemd units, site settings |
| `build/`, `install/` | COPIES made by a packaging tool: never edit them |

NAVERA's own code is IRIS's property and is not part of the course. NAVERA Lite has the same
shape (witnesses → judge → messenger), written for the course.
