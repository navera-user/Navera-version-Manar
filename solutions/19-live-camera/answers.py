# Lesson 19 quiz — write the letter of your answer between the quotes, e.g.  Q1 = "b"

# Q1. NAVERA stamps each camera frame with  grab time - 0.138 s.  Why?
#   a) to make the logs look older
#   b) the picture was taken 0.138 s before NAVERA received it, and the attitude used to
#      straighten it must be the one of THAT instant
#   c) because the GPS is 0.138 s late
Q1 = "b"

# Q2. live_camera.py calls grab() for every frame, but retrieve() only for the frame it sends. Why?
#   a) decoding a 1080p MJPG frame costs about 51 ms of processor: decoding all 28.8 frames a
#      second would waste about 1.5 processor cores for one frame used per second
#   b) retrieve() may only be called once per second by law
#   c) grab() gives nicer colours
Q2 = "a"

# Q3. NAVERA asks the driver for a buffer of ONE frame and always sends the NEWEST frame. Why?
#   a) to save disk space
#   b) a frame that waited in a queue shows where the vehicle WAS, seconds ago
#   c) the Insta360 can only store one frame
Q3 = "b"

# Q4. The Insta360 sends a 1920x1080 picture made of two lenses. Which part does NAVERA's
#     live camera use on the bench box, and with which setting?
#   a) the top half, with crop "top"      b) the bottom half, with crop "bottom"
#   c) the whole picture, no crop
Q4 = "a"
