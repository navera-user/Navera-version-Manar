# Write the letter of your answer between the quotes, e.g.  Q1 = "b"

# Q1. The Insta360 top lens sees about 166 degrees, but NAVERA publishes a straightened
#     picture only 111 degrees wide. Why?
#   a) wider than that, a straight picture stretches the edges so much that the centre gets
#      FEWER pixels per degree than the lens gives (and the calibration is not trusted
#      far out at the edges)
#   b) the Jetson is too slow to compute more than 111 degrees
#   c) satellite map tiles are only 111 degrees wide
Q1 = "a"

# Q2. The calibration file was made for the 1920x540 top half. Someone sets the camera to
#     1280x720. What happens?
#   a) nothing, the lens is the same so the file still works
#   b) the numbers in K are in pixels of 1920x540, so they are wrong now: live_camera.py
#      refuses the file and the camera must be calibrated again at the new size
#   c) NAVERA divides everything by 2 automatically
Q2 = "b"

# Q3. The calibration reports "RMS 0.525 px". It means:
#   a) NAVERA's position will be wrong by about 0.5 meters
#   b) on average, the corners the lens model predicts land about half a pixel away from
#      where the camera really saw them
#   c) half of the photos of the chessboard were thrown away
Q3 = "b"
