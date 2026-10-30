# Mission 29 — scenarios for the judge

Scenario files in the replay format of mission 12 (`t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s`):
`race.csv` (31 s, every source), `revival.csv`, `lockout.csv`, `flapping.csv`.
`reference_run.json`: what the course's reference judge decided on `race.csv` (simulated clock, 5 Hz ticks):
the state, source and reason at 11 moments, and the instants where the winner changed.
Positions are in NAVERA's test area, Sousse (Tunisia); every number is synthetic.
