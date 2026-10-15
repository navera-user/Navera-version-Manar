# Mission 31 data (read only)

| File | What |
|---|---|
| `corridor/corridor.json` | the test corridor west of Sousse (Tunisia): its centre, its size, the metres per pixel of each picture, how a pixel maps to east/north metres, and the route the simulator flies |
| `corridor/day_ortho.png` | the corridor north-up, grey, 0.5 m per pixel (1000 m × 3800 m): an aerial-style drawing rendered from OpenStreetMap data. The simulated day camera takes its photos from it |
| `corridor/night_ref.png`, `corridor/night_temp.png` | the same ground at about 7.75 m per pixel: a day reference and a night "temperature" picture (mission 25's kind), aligned pixel for pixel |
| `gps_input.bin` | the bytes an autopilot received on its serial port during one simulated flight of NAVERA Lite: MAVLink 2 frames, as received |

The pictures are drawings made from OpenStreetMap data (not photographs, not real thermal images).
Pixels: (x, y) = (column, row), the centre of the top-left pixel is (0, 0).

Map data © OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright.
The renders are a produced work of that data.
