Mission 20 — live camera: data

bench/frame_000..029.jpg  REAL frames of NAVERA's Insta360 ONE R (USB webcam mode, MJPG 1920 x 1080), recorded on
                          NAVERA's bench on 2026-10-06 while its top lens was being calibrated. Top half = top lens,
                          bottom half = bottom lens (pixelated: it filmed people in the room).
bench/insta360_top.yaml   the real calibration file of that top lens (copied as data).

The other files are SYNTHETIC (simulated, seeded), made for this lab:
grab_log.csv              60 s of grab times of a USB camera (a monotonic clock, seconds).
flashes.csv               a screen-flash bench: when the program asked the screen to turn white.
bench_frames.csv          the same bench: grab time and centre brightness (0-255) of every frame.
flight/imu.csv            a survey plane's attitude at 50 Hz: t_s, then a quaternion (x, y, z, w), body -> ENU.
flight/frames.csv         the frames of that flight: grab_s = when the program received the frame (same clock as
                          imu.csv), and the TRUE pose at the frame's exposure (east/north/height in metres from the
                          map centre, attitude x, y, z, w).
flight/map.jpg, map.json  the ground under the flight (Sousse, Tunisia), drawn from OpenStreetMap data:
                          © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).
