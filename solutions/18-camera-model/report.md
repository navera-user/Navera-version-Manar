# Memo — what a drone camera can measure, and what it needs to know

## Tilt

In photo T the camera was 170 m up, pitched 14° nose down and rolled 5°. Back-projecting the pad's centre
pixel (600.1, 321.8) with the full attitude puts the pad 17.9 m west and 66.0 m south of the point under the
drone. Assuming a level camera puts it at (20.8, −41.4) m, 45.9 m away: the attitude is not a detail. At 250 m
and 8° of tilt, 1° of attitude error costs 4.46 m, and a tilt error of 6.60° moves the centre point by 30 m, the σ day vision states; at 35° of tilt
4.36° is enough, because the ground distance grows like tan(tilt).

## Height

The 12 m pad is 43 px wide in photo A (height 134.0 m, ±1 px: 130.9 to 137.1 m) and only 22 px in photo B
(261.8 m, ±1 px: 250.4 to 274.3 m, a 23.9 m range). Height and scale are the same unknown: the scale a matcher
fits is the true height over the predicted one. On the plateau the predicted height was 400 m and the true one
240 m, a scale of 0.6, which a ±15 % gate refuses. A fitted scale of 1.08 at a predicted 300 m measures 324 m.

## Straightening

The homography K·R_wvᵀ·R_wc·K⁻¹ turned photo T into the view of a level, north-up camera at the same place:
the point under the drone moved from pixel (522.0, 149.9) to the image centre (480, 270) and the pad became a
square, 35 px wide (12 m / 0.354 m per px = 33.9 px). Its centre (429.2, 456.5) gives −18.0 m east and −66.1 m
north, the same as the back-projection of Step 5 within 0.1 m. Straightening needs only K and the attitude;
measuring metres in the result also needs the height above flat ground.
