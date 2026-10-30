# Mission 21 data (read only)

| File | What |
|---|---|
| `terrain_*.png` | six 512 × 512 px map patches of the Sousse area (Tunisia), north up, about 0.97 m per pixel (about 500 m of ground): an aerial-style drawing rendered from OpenStreetMap data |
| `terrain.csv` | one line per patch: file, terrain, lat, lon, m_per_px |
| `pair_*.jpg` | 640 × 480 px simulated drone photos of the centre of a map patch, turned and/or closer, with camera effects |
| `pairs.json` | for each photo: its map patch, the photo's heading and zoom, and the exact 3 × 3 matrix `H` that maps a pixel (x, y) of the map patch to the photo |
| `drone_city.jpg`, `drone_city_dark.jpg` | a simulated drone view of the city, clear and at dusk with motion blur |
| `house.png` | a synthetic top view of one house on flat ground |
| `real_coast.jpg`, `real_town.jpg` | two real aerial frames from NAVERA's day-camera test data, 1536 × 730 px |
| `patches_train.npz` | arrays `a`, `b`: 12 288 pairs of 32 × 32 grey patches (uint8); `a[i]` and `b[i]` show the same ground point, `a` in a map-like view, `b` in a simulated drone photo (turned, scaled, tilted, blurred, darker or brighter, noisy) |
| `patches_val.npz` | arrays `a`, `b`: 2 048 more pairs, 48 × 48, from other places (no ground shared with the training pairs) |

Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0); the centre point of a picture w px wide
and h px high is ((w − 1)/2, (h − 1)/2).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
