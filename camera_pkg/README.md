# camera_pkg — frame source

`camera_publisher` feeds a localizer with frames, either replayed from a CSV + image folder
(test data) or from a live CSI/USB camera. The same node runs under the `day`, `thermal`
and `celestial` namespaces (launch files `day.launch.py`, `thermal.launch.py`,
`celestial.launch.py`).

## Outputs (relative to the namespace)
| Topic | Type | |
|---|---|---|
| `image_raw` | sensor_msgs/Image | the frame |
| `frame_meta` | std_msgs/String (JSON) | frame id, `image_stamp_ns` (pairing key), CSV lat/lon when GPS is "valid" in the replay, altitude/heading/speed **only when known** (else null), `image_missing` |
| `gps` | sensor_msgs/NavSatFix | replayed CSV position (NaN when not valid) |

## Inputs
`camera/start` (Bool, latched: true = go, false = pause + rewind), the localizer's
`localizer_ready` (Bool, latched) and `frame_done` (Int32 ack) — see
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5.

## Key parameters
`source` (csv | camera), `csv_path`, `images_dir`, `fps`, `flow_control` (rate | ack),
`wait_for_ready`, `start_paused`, `default_gps_valid` (replay: treat CSV lat/lon as GPS),
`image_encoding` (bgr8 | mono8 | mono16).

## Notes
- Unknown motion is never invented: a CSV row without speed/heading/altitude produces null.
- Live mode never claims GPS (the GPS is a separate node).
- A `camera_info` publisher is created but not yet populated (no calibration published).
