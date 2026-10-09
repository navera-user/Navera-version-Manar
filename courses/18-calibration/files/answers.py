# Write the letter of your answer between the quotes, e.g.  Q1 = "b"

# Q1. Zhang's method needs several views of the board because...
#   a) one view gives one homography H, i.e. only 2 equations on the 5 unknowns of K
#      (fx, fy, cx, cy, skew): at least 3 views are needed, and many more to beat noise
#   b) OpenCV crashes with fewer than 8 photos
#   c) each view measures a different distortion coefficient
Q1 = ""

# Q2. Your calibration has a train RMS of 0.5 px. On views it has never seen, the error is
#     larger. What does this tell you?
#   a) the calibration is wrong and must be thrown away
#   b) the train RMS is optimistic: the parameters were tuned on those very corners; the error
#      on new views is the honest estimate of the model's accuracy
#   c) the test views were taken with another camera
Q2 = ""

# Q3. The calibration file was made for the 1920x540 top half. Someone sets the camera to
#     1280x720. What happens?
#   a) nothing, the lens is the same so the file still works
#   b) NAVERA divides everything by 2 automatically
#   c) K is in pixels of 1920x540, so it is wrong now: live_camera.py refuses the file and the
#      camera must be calibrated again at the new size
Q3 = ""
