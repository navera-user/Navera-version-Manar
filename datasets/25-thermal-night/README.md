# Mission 25 data (read only)

| File | What |
|---|---|
| `scenes_train.npz` | arrays `ref`, `night` (N × 160 × 160, uint8), `lat`, `lon`, `m_per_px`: squares of ground of the Sousse area (Tunisia), north up, about 7.75 m per pixel (about 1.24 km wide). `ref` is a day aerial-style view, `night` a night "temperature" picture of the same ground (0 = cold, 255 = hot), aligned pixel for pixel |
| `scenes_val.npz` | the same for other places (no ground shared with `scenes_train.npz`), plus `day` (a thermal-like picture at noon) and `crossover` (at dawn, when everything has about the same temperature) |
| `scenes_coast.npz` | `ref`, `night` of coastal places, half or more of them sea |
| `flight/frame_NN.png` | 640 × 512 thermal-like frames of a simulated night flight (camera 75° × 63°) |
| `flight/frames.csv` | per frame: time, the prior position (where the drone believed it was), height above ground, heading, and the true position |
| `flight/ref_area.png`, `ref_area.json` | the day reference of the flight's area, north up, and the latitude/longitude of its top-left corner and its metres per pixel |
| `night_fixes.csv` | positions reported by a night matcher on another flight: time, lat, lon, its score |
| `replay/night_NN.jpg`, `replay/day_NN.jpg` | NAVERA's replay frames (night and day sets), copied as data and reduced to 768 px wide |
| `replay/night_labels.csv`, `replay/day_labels.csv` | the labels the replay sets carry: frame, lat, lon, altitude_m, heading_deg |

The views are drawings made from OpenStreetMap data (they are not photographs and not real thermal images).
Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
