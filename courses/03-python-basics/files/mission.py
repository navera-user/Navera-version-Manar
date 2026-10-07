# Warm-up: variables, numbers, strings and print.
# Run it with:   python3 mission.py

drone_name = "NAVERA-1"
cruise_speed_kmh = 54          # how fast the drone flies, in km/h
mission_distance_km = 12       # how far it has to go, in km

print("Drone:", drone_name)
print("Speed:", cruise_speed_kmh, "km/h")

# TODO A: compute the flight time in MINUTES from the two variables above.
#         (time in hours = distance / speed, and 1 hour = 60 minutes)
mission_time_min = 0

# TODO B: print ONE sentence built with an f-string, using the variables, for example:
#         NAVERA-1 flies 12 km at 54 km/h: 13.3 minutes
#         (the :.1f inside the braces rounds to 1 decimal)
