Mission 04 — flight-test campaign of 15 September 2026 (SYNTHETIC: made for the course,
placed in NAVERA's test area around Sousse and Monastir, Tunisia). Read only.

campaign.csv      the logger's file, one row every 2 s, four flights of the drone LITE-2. Columns:
                  flight_id, time_s (the logger's clock, seconds since 00:00), lat, lon (degrees),
                  alt_m, speed_mps (logged by the autopilot), battery_pct, gps_valid (1/0),
                  source (gps | day | none), state (FIX | DEGRADED | NO_FIX)
flight_sheet.csv  the test director's sheet, times in UTC (hh:mm:ss): take-off, landing and
                  the window when the range's GPS jammer was switched on
