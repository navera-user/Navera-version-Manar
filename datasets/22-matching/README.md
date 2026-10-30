# Mission 22 data (read only)

| File | What |
|---|---|
| `map_*.png` | 512 × 512 px map patches of the Sousse area (Tunisia), north up, about 0.97 m per pixel: an aerial-style drawing rendered from OpenStreetMap data |
| `photos/*.jpg` | 640 × 480 px simulated drone photos, with camera effects (noise, blur, shake, brightness) |
| `pairs.json` | session 1: eight named pairs: map, photo, the drone's prior (heading, its uncertainty, zoom) and the exact 3 × 3 matrix `H` from a map pixel to a photo pixel (`null` when the photo shows another place) |
| `curve.json`, `envelope.json`, `mission.json` | session 2: the pairs and scenarios of lab Steps 9–11, same fields |

zoom = map metres per pixel ÷ photo metres per pixel; heading = where the photo's top points, clockwise from north.
Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
