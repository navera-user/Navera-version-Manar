# Map memo — the course map of Sousse, its scales and the corner bug

## Scales and zooms

A web map is drawn in Web Mercator, which stretches everything by 1/cos(latitude). At zoom 17 a pixel covers
1.1943 m in Quito but only 0.5209 m in Reykjavik, and 0.9683 m in Sousse: the same zoom number is 2.3 times
coarser on the equator than at 64° north. For the lab's camera (84°, 1536 px) at 1000 m over Sousse the
ground pixel is 1.17 m and my rule picks zoom 16, the finest zoom whose pixel is still at least as large as the
photo's; the map's altitude_zoom_map picks 15. I would keep the coarser table for matching: four times fewer
tiles per level in the search circle, and small details are averaged away, while the photo is still only
shrunk, never enlarged. Zoom 19 is only usable below about 206 m with this camera.

## The map file

The map is one SQLite file of 979.6 MB (239 152 pages of 4096 bytes) with two tables, metadata and tiles.
It holds 264 585 JPEG tiles, 198 288 of them at zoom 19 and 12 444 at zoom 17. A tile is found by its primary
key (zoom, column, TMS row): EXPLAIN QUERY PLAN shows a search in the B-tree index, a few page reads instead
of a scan. The metadata bounds say 10.47 to 10.75 E and 35.70 to 35.97 N, but the zoom-13 tiles cover
10.459 to 10.767 E, because whole tiles are stored. The metadata is a label; the tiles are the measurement.

## The corner bug

NAVERA's day vision published the north-west corner of the matched zoom-17 tile instead of its centre. The
error is half the tile diagonal: 175.1 m in Sousse, always to the north-west, so no jump gate sees it. In
Quito it would be 216.0 m, because tiles near the equator cover more ground, and in Reykjavik 94.2 m. The
fix adds 0.5 to the tile numbers before converting back to latitude and longitude, and a unit test keeps it.
