# Lab 16 — your answers. Numbers without quotes (PITCH_UP_DEG = -3.5). Text in quotes ("…").
# (Reference answers for the teacher; the EXPLAIN texts are one acceptable wording among many.)

# ======== Session 1 — Attitude reader ========
PREDICT_PITCH = "Above the horizon, because positive pitch usually means climbing."
PITCH_UP_DEG = -6.88
EXPLAIN_PITCH = ("ROS pitch is a rotation about the y axis, the left wing. By the right-hand rule, with the thumb "
                 "along the left wing the fingers curl from the top (z) towards the nose (x), so the nose goes down; "
                 "a pilot's pitch_up is the opposite sign.")
PREDICT_ORDER = "A: left wing up. B: left wing west."
EXPLAIN_ORDER = ("A is yaw first then roll about the new nose: read left to right, Rz turns the drone, then Rx turns "
                 "it about its own moving x axis. Read right to left about the fixed world axes, B rolls about the "
                 "old east axis after the yaw. The order changes the result because rotations do not commute.")
PREDICT_LOCK = "The same angles for all four, with roll 0 and yaw 45, because only yaw minus roll is defined."
LOCK_UP_YAW_DEG = 80.0
NEAR_LOCK_YAW_JUMP_DEG = 63.43
EXPLAIN_LOCK = ("At pitch 90 degrees the nose (the roll axis) lines up with the vertical yaw axis, so turning about one "
                "is the same as turning about the other: one degree of freedom is lost and only a combination of roll "
                "and yaw is defined. Apollo kept three gimbals; the computer warned near the lock and the crews "
                "steered around it, or realigned the platform on the stars.")

# ======== Session 2 — Quaternion detective ========
POSE_PITCH_UP_DEG = 12.0
POSE_HEADING_DEG = 215.0
Q360_W = -1.0
PREDICT_LERP = "About 1 degree: the error grows faster than the angle, so much more than 0.01."
LERP_ERR_DEG = 5.45
EXPLAIN_SLERP = ("Linear interpolation moves along the straight chord between q0 and q1, inside the sphere, so the "
                 "length drops below 1; after normalising, equal steps on the chord are unequal angles: it turns "
                 "slower near the ends and faster in the middle, not at a constant rate.")
EXPLAIN_ORACLE = ("SciPy is independent code written and tested by other people, and 500 random cases cover what my "
                  "own examples miss; my examples could share my own misunderstanding. The comparison had to "
                  "translate the Euler order: SciPy's ZYX takes yaw first; both use (x, y, z, w) with w last.")
PREDICT_SUSPECT = ("(a) pitch sign: nothing changes on a level pad, roll 0 heading 30. (b) conjugate: heading 150, "
                   "roll 0. (c) order swap: a 180 degree turn, so a big tilt. Only (c) can give roll 60.")
PAD_HEADING_DEG = 30.0
COLLEAGUE_PAD_ROLL_DEG = 60.0
COLLEAGUE_MAX_TILT_DEG = 174.0
FLIP_T_S = 111.4
EXPLAIN_DETECTIVE = ("The colleague read ROS (x, y, z, w) as (w, x, y, z), so the scalar w was taken from x. On the pad "
                     "the level drone shows a 60 degree roll and heading 270 instead of 30, and flying west it looks "
                     "upside down. The length of every quaternion is still 1 and the rotation between consecutive "
                     "samples is unchanged, because the same swap is applied to every sample and the dot product does "
                     "not change, so no error and no rate check sees it. The sign change at 111.4 s is not a bug: q and "
                     "−q are the same attitude, and q_angle_deg there is only 0.36 degrees.")
LOOK_BACK = ""
