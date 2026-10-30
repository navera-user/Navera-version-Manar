# Lab 27 — reference answers (teacher only). Numbers from the reference run (solutions/27-uncertainty/TEACHER.md).

PREDICT_INSIDE = "About 39: on a map the error has two chances to be large, so fewer fall inside 3 m than the 68 % of one axis."

PREDICT_CLOUD = "North is worse (wider range); east and north look negatively correlated (ρ < 0)."

ELLIPSE_A_M = 3.36
ELLIPSE_B_M = 1.53
ELLIPSE_ANGLE_DEG = -57.3
LONG_AXIS_BEARING_DEG = 147.3
JUDGE_SIGMA_M = 2.95

PREDICT_CIRCLE = "The ellipse: at k = 3 the circle (8.8 m) is shorter than the ellipse's long axis (10.1 m), so far fixes along that axis escape it."
INSIDE_1SIGMA_PCT = 38.5
INSIDE_3SIGMA_PCT = 99.2
CIRCLE_3_PCT = 98.8
SIM_P95 = 6.03
EXPLAIN_CHI2 = ("On a map d² = x² + y² adds two squared normal errors, so it is larger than one axis alone: only 39 % "
                "stay below 1 against 68 % for x² alone, and the 95 % threshold is 5.99 instead of 3.84 (1.96²) — "
                "the mean of d² is 2, one per dimension. At k = 3 the circle's radius (3 × 2.95 m) is shorter than the "
                "long axis (3 × 3.36 m): the far fixes along the long axis escape it.")

PREDICT_RADAR = "a = r × σβ in radians = 3000 × 0.01745 = 52.4 m"
RADAR_A_M = 52.4
MC_A_M = 52.2
PREDICT_WIDE = "Fewer than 95 %, maybe 70 %: the cloud bends."
WIDE_INSIDE_PCT = 46.7
EXPLAIN_RADAR = ("A bearing error moves the target sideways by r·σβ, 52 m at 3 km, while the range error is only 8 m "
                 "along the line of sight. With 10° the positions lie on a curved arc of the range circle, and the "
                 "straight-line Jacobian (linearisation) gives a thin straight ellipse that misses the banana.")

PREDICT_JUDGE = "A, C and F; B, D and E are across the track or too far."
D2_A = 6.23
N_ACCEPT_99 = 3
EXPLAIN_JUDGE = ("E is only 79 m away but across the track, where the predicted uncertainty is small (25 m), so its d² "
                 "is 9.65 > 9.21; A is 150 m along the track where the odometry drift is large (60 m). The never-grown "
                 "predictor refuses A, the truth, and will keep refusing every later fix: it is locked out. The 160 m "
                 "circle accepts the spoofer B.")

PREDICT_ATTACK = "Along the track: √(9.21 × 3609) ≈ 182 m at bearing 120°/300°; across √(9.21 × 634) ≈ 76 m at 30°/210°."
ATTACK_MAX_M = 182.3
ATTACK_MIN_M = 76.4
EXPLAIN_ATTACK = ("The attacker goes along the long axis of S, along the track (bearing 120° or 300°): the largest "
                  "accepted offset is √(9.21·λ1) = 182 m, across √(9.21·λ2) = 76 m. A smaller S (a better predictor) or "
                  "a lower p shrinks it, but a smaller gate refuses more honest fixes (false alarms).")

PREDICT_FUSE = "Larger: a few wrong vision matches drag the fused position far away."
RMS_GPS_M = 19.0
RMS_ALL_M = 33.3
RMS_GATED_M = 12.1
COVER_GATED_PCT = 93.0
COVER_LIAR_PCT = 75.5
LIAR_REFUSED = 159
EXPLAIN_FUSE = ("Fusion improves most seconds (p95 26 m against 44 m) but the 24 outliers, fused with weight in the "
                "canyon, move the result by up to 300 m, and the RMS squares those big errors. A liar stating 5 m "
                "makes the fused σ too small: coverage falls to 75 %, and the gate, with S too small, refuses 159 good "
                "vision fixes as false alarms.")

STATED_SIGMA_M = 22.8
WORST_SIGMA_M = 29.3
FALSE_FIX_S = 64
EXPLAIN_PUBLISH = ("The judge reads the largest diagonal variance (east 519 m²), but the ellipse is tilted 40° along the "
                   "street, so the long axis (eigenvalue) is longer: up to √2 more. The judge should read √λ1, the "
                   "eigenvalue, or the source should state its worst axis.")

LOOK_BACK = "A too-small σ makes the filter's gate refuse the fixes until it times out."
