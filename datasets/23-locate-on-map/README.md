# Mission 23 — locate a photo on the map

Synthetic downward photos (640 × 480, horizontal field of view 60°) rendered from the course's OpenStreetMap map of
Sousse, Tunisia (NAVERA's test area), with camera effects; their metadata and a prior position for each; the true
positions; and the DINOv2 ViT-S/14 embeddings of the zoom-17 map tiles of the test area
(lat 35.77–35.87, lon 10.55–10.68).

| File | What |
|---|---|
| `photos/pNN.jpg` | the photos |
| `photos.csv` | id, alt_m, heading_deg, hfov_deg, terrain, prior_lat, prior_lon, prior_sigma_m |
| `truth.csv` | id, lat, lon of each photo's centre |
| `dino_index.npz` | xy (tile numbers), emb (unit rows, float16), z |

Map data © OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright. DINOv2: Meta AI, Apache-2.0 (/data/models/dinov2).
