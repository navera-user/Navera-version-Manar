Lesson 19 dataset — recorded frames of the Insta360 ONE R (USB webcam mode, MJPG 1920x1080).

frames/frame_000..029.jpg  30 consecutive frames saved during NAVERA's lens calibration
                           (2026-10-06). Top half = top lens (the one NAVERA uses), bottom
                           half = bottom lens: it filmed people, so it is PIXELATED (privacy).
grab_times.csv             SIMULATED grab times: the calibration tool did not record when each
                           frame arrived. Spaced at 28.8 fps (what the camera gives) + jitter.
insta360_top.yaml          the real calibration of the top lens (fisheye, 1920x540,
                           latency_s 0.138 measured with navera_tools/bench/camera_latency.py).
Rebuilt by make_dataset.py.
