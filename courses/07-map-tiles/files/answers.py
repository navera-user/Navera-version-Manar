# Lab 7 — your answers. Numbers without quotes (BIG_TILES_Z17 = 1234). Text in quotes ("…").
# A tile is a pair in brackets: KANTAOUI_TILE_Z18 = (138000, 103000).
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Cartographer (projection, tiles, scales) ========

# ---- Step 0: how big is the map? --------------------------------------------------------------------
PREDICT_TILES = ""          # the course map covers about 25 km × 30 km around Sousse. How many zoom-19 tiles
                            # does it hold? (an order of magnitude is fine)

# ---- Step 1: look inside the map (python3 run_tiles.py explore "…your SQL…") -------------------------
BIG_TILES_Z17 = 0           # how many zoom-17 tiles are larger than 10 000 bytes? (your own SQL query)
EXPLAIN_TILE_SIZE = ""      # why are the tiles of higher zooms smaller files, although all are 256 × 256 px?

# ---- Step 3: tile numbers ---------------------------------------------------------------------------
KANTAOUI_TILE_Z18 = (0, 0)  # (x, y) of the zoom-18 tile that holds Port El Kantaoui marina (35.8930, 10.5965)
EXPLAIN_SHARED_CORNER = ""  # why do zooms 14 and 15 give the Ribat's tile the same NW corner, but not 13 and 14?

# ---- Step 4: scales and zooms -----------------------------------------------------------------------
PREDICT_ZOOM = ""           # before you call best_zoom: at 1000 m over Sousse, is your rule finer or coarser
                            # than the map's altitude_zoom_map, and by how many zoom levels?
BEST_ZOOM_SOUSSE_1000 = 0   # best_zoom for the lab's camera (84°, 1536 px) at 1000 m over Sousse
ALT_MAX_Z19_SOUSSE_M = 0.0  # the highest flying height (m) at which best_zoom still gives 19 over Sousse
EXPLAIN_ZOOM = ""           # compare your rule with the map's table at 300 m and 1000 m: which is coarser,
                            # and why can that be a good choice for matching photos?

# ======== Session 2 — Tile hunter (the map file, mosaics, the corner bug) ========

# ---- Step 5: read a tile ----------------------------------------------------------------------------
TMS_ROW_KANTAOUI_Z18 = 0    # the tile_row stored in the file for your KANTAOUI_TILE_Z18

# ---- Step 6: impossible addresses (python3 run_tiles.py guard) --------------------------------------
EXPLAIN_GUARD = ""          # why check z before computing 2**z? and why pass z, x, y as ? values instead of
                            # writing them into the SQL text?

# ---- Step 7: the corner bug and the search circle ---------------------------------------------------
PREDICT_CORNER = ""         # before the run: at which latitude is the zoom-17 corner bug half of its size on
                            # the equator? about how many metres at Longyearbyen (78.2° N)?
CORNER_QUITO_M = 0.0        # corner -> centre distance of Quito's zoom-17 tile (m), computed by you
EXPLAIN_CORNER = ""         # why is the same bug larger near the equator?
EXPLAIN_FIX = ""            # how far off can "publish the tile's centre" still be? what is the right position?
CIRCLE_TILES_REYKJAVIK = 0  # tiles_in_circle(Reykjavik, 600 m, zoom 17): how many tiles?

# ---- Step 8: metadata against measurement -----------------------------------------------------------
COVER_WEST_Z13_DEG = 0.0    # the west edge (longitude) of the zoom-13 tiles, from your SQL + tile_to_latlon
EXPLAIN_BOUNDS = ""         # why do the zoom-13 tiles reach further west than 10.47°, and why the match from 15 on?
EXPLAIN_GROWTH = ""         # tiles per zoom grow by 3.56 … 4.00: why not exactly 4 at low zooms?

# ---- Step 10: look back (not graded; for you and your teacher) --------------------------------------
LOOK_BACK = ""
