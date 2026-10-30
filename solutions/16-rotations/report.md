# Bug memo — the colleague's attitude table

## What the colleague saw

The colleague's table of the 150 s flight shows the drone on the pad rolled 60° with a heading of 270°,
and later, on the west-south-west leg, tilted up to 174° from level: almost upside down. The pilot says the
flight was normal, and no program printed an error.

## The cause

The log stores each orientation as ROS does, (x, y, z, w), with the scalar w last. The colleague's script
read the four numbers as (w, x, y, z). I reproduced the colleague's table from the log with this one swap:
my misread() plus rpy_human matches every row to 0.05°, which is the rounding of the table. Read correctly,
the drone is level on the pad with a heading of 30.0°, and its largest tilt in flight is 13.5°. For a
level drone the misread quaternion has w = 0, a 180° turn whose axis is tipped by the yaw angle, so the
fake tilt grows with the yaw: 60° on the pad (yaw 60°), close to 180° when the drone flies west.

## How to catch it next time

The usual sanity checks do not see this bug. Every misread quaternion still has length 1.000000, and the
rotation between consecutive samples is identical in both readings (largest difference 0), because the
same swap is applied to every sample. One sign change of the four numbers at t = 111.4 s is normal (q and
−q are the same attitude) and is not the bug either. What catches it is a test with a known, non-trivial
attitude at the point where the data enters: a level vehicle at heading 30° must give roll 0 and
heading 30, not roll 60. I would add that as a unit test of the reading function (mission 14 style), and
compare the heading with an independent source, such as the compass or the camera, during the first
minutes of every flight.
