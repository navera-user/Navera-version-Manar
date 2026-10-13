"""Step 5 (teacher's solution): winds from 020° in 0.5 m/s steps until the first NO-GO; the last GO speed is the limit."""
from navera_lite.vehicle import endurance_s, heading_for_track, heading_vector

endurance = endurance_s(160.0, 350.0, 0.2)
e, n = heading_vector(200.0)                     # self-test: from 020° = towards 200°
print("wind for 6 m/s:", round(6 * e, 2), round(6 * n, 2))   # must be -2.05 -5.64
last_go = None
for i in range(25):                              # 0.0, 0.5, … 12.0 m/s
    speed = i * 0.5
    e, n = heading_vector(200.0)                 # from 020° = towards 200°
    we, wn = speed * e, speed * n
    try:
        _, gs_out = heading_for_track(30.0, 12.0, we, wn)
        _, gs_back = heading_for_track(210.0, 12.0, we, wn)
    except ValueError as err:
        print(f"{speed:4.1f} m/s  impossible: {err}")
        break
    trip = 7500.0 / gs_out + 7500.0 / gs_back
    go = trip <= endurance
    print(f"{speed:4.1f} m/s  round trip {trip / 60:6.2f} min  {'GO' if go else 'NO-GO'}")
    if not go:
        break                                    # the first NO-GO: stop
    last_go = speed
print("MAX_WIND_MPS =", last_go)
