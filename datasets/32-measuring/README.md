# Mission 32 — measuring

Synthetic data in NAVERA's test area, Sousse (Tunisia). Every number is synthetic.

- `flight_target.csv`, `flight_retrieval.csv`, `flight_selective.csv`: three versions of one 240 s drone
  flight, one row per second, with the decisions of NAVERA Lite's judge and the true position.
  Columns: `t_s, gps, state, source, sigma_m, lat, lon, truth_lat, truth_lon` (degrees; empty = no position).
- `shadow_bag/`: a ROS 2 bag of `sensor_msgs/NavSatFix` on `/navera_lite/fix/gps` and `/navera_lite/fix/day`
  (300 s, GPS working, both sources recorded).
- `shadow_truth.csv`: the true position of the bag's flight, 10 per second (`stamp_s` on the bag's clock).
