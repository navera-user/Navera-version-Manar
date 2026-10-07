# Lab 7 report — map scales around the world and NAVERA's map file

## World scales

At zoom 17 a map pixel covers 1.1940 m in Singapore and 0.5209 m in Reykjavik. Web Mercator
stretches the map by 1/cos(latitude), so a pixel of fixed size covers less ground further from the
equator; Singapore is almost on the equator and Reykjavik is at 64 degrees north, so Singapore's
pixels are 2.3 times larger. For the example camera (84 degree field of view, 1536 px) over
Singapore, zoom_for_gsd() chooses zoom 19 at 150 and 200 m, 18 at 300 and 500 m, 17 at 1000 m and
16 at 1500 and 2000 m. The map's altitude_zoom_map is up to three levels coarser (17 at 300 m, 13 at 2000 m). That is not a contradiction: my rule only says the map
should not be finer than the photo; a coarser map is also usable because the photo is shrunk to
the map scale, it is faster to match and old imagery has less irrelevant detail. I would keep the
map's table and check that the photo is always shrunk, never enlarged.

## The map file

The file is 10286944256 bytes, 10.29 GB, exactly 2511461 SQLite pages of 4096 bytes. The metadata
says estimated_size_mb = 36467, about 36 GB, which is wrong by a factor of 3.5. I trust the
measurement: metadata is text written by the tool that made the file and nobody checks it. The
file holds 1154943 tiles, 54312 of them at zoom 17. A tile is found instantly because the primary
key (zoom_level, tile_column, tile_row) has an index: EXPLAIN QUERY PLAN shows SEARCH USING INDEX,
so SQLite reads a few pages of a B-tree instead of scanning a million rows.

## The corner bug

The day-vision dataset stores the north-west corner of each tile. NAVERA published that corner as
the drone position, but the photo matches the whole tile, so the position is the tile centre. The
error is half the tile diagonal: 175.1 m at zoom 17 in Sousse. In Singapore it would be 215.9 m,
because tiles at a lower latitude cover more ground (306 m wide instead of 248 m); in Reykjavik
only 94.2 m. The fix uses
x + 0.5 and y + 0.5, and a unit test keeps it fixed.
