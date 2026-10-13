# Lab 7 — reference answers (teacher only).

PREDICT_TILES = "about 200 000: 25 km × 30 km is 750 km², a z19 tile is 62 m × 62 m ≈ 0.0038 km²"
BIG_TILES_Z17 = 1491
EXPLAIN_TILE_SIZE = ("JPEG compresses flat, uniform areas very well. A high-zoom tile shows a small piece of the city "
                     "in detail: mostly plain colour (a roof, a road, the sea) with few edges, so it compresses to a "
                     "small file; a zoom-13 tile packs many streets and labels, much detail, a bigger file.")
KANTAOUI_TILE_Z18 = (138788, 103036)
EXPLAIN_SHARED_CORNER = ("Each tile has 2 × 2 children at the next zoom; the top-left child (both numbers even) shares "
                         "its parent's north-west corner. The zoom-15 tile 17352/12886 is even/even, so it shares the "
                         "corner of its zoom-14 parent; the zoom-14 tile 8676/6443 has an odd row, it is a bottom child.")
PREDICT_ZOOM = "finer: my rule floors log2 of the pixel ratio, the table is coarser, maybe by one level"
BEST_ZOOM_SOUSSE_1000 = 16
ALT_MAX_Z19_SOUSSE_M = 206.5
EXPLAIN_ZOOM = ("The map's table is coarser by one level (17 vs 18 at 300 m, 15 vs 16 at 1000 m). A coarser zoom means "
                "fewer tiles to compare in the search circle, so matching is faster, and small details that change "
                "on the ground are averaged away; the photo is shrunk more, which is safe, it is never enlarged.")
TMS_ROW_KANTAOUI_Z18 = 159107
EXPLAIN_GUARD = ("2**z for a huge z is an enormous number: a billion costs about 6 s of CPU and 125 MB, so a few bad "
                 "requests could stall the server; checking z first costs nothing. With ? placeholders the values "
                 "are sent as values, never as SQL text, so they cannot change what the query does.")
PREDICT_CORNER = "half at 60° (cos 60° = 0.5); Longyearbyen about 216 × cos 78.2° ≈ 44 m"
CORNER_QUITO_M = 216.0
EXPLAIN_CORNER = ("The error is half the tile diagonal. Near the equator cos(latitude) is larger, the Mercator "
                  "stretch smaller, so a zoom-17 tile covers more ground (306 m wide in Quito, 248 m in Sousse).")
EXPLAIN_FIX = ("The centre is right only if the photo's centre fell on the tile's centre; otherwise it can still be off "
               "by up to half the diagonal, 175 m at Sousse. The right position is the matched pixel itself: "
               "pixel_to_latlon(u, v, z, tx, ty), the point of the tile where the photo's centre landed.")
CIRCLE_TILES_REYKJAVIK = 62
COVER_WEST_Z13_DEG = 10.4590
EXPLAIN_BOUNDS = ("The bounds are a rectangle in degrees, but the file holds whole tiles: every tile that touches the "
                  "rectangle is stored, so the coverage snaps outwards to the tile grid. A zoom-13 tile is about 4 km "
                  "wide, so it reaches about 1 km beyond 10.47; from zoom 15 on a tile edge falls almost exactly on "
                  "10.47 and the tiles are small, so the overshoot is tiny.")
EXPLAIN_GROWTH = ("Each tile has 4 children, but at the edge of the area only the children that touch the area are kept. "
                  "At low zooms a large share of the tiles lie on the edge, so fewer than 4 children per tile are "
                  "stored; at high zooms the edge tiles are a tiny share, and the ratio tends to 4.")
LOOK_BACK = ""
