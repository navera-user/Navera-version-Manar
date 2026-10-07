# Look inside an MBTiles file (read only). Usage:
#     python3 explore_db.py                      -> metadata + number of tiles per zoom
#     python3 explore_db.py "SELECT ... "        -> runs YOUR SQL query and prints the rows
#     python3 explore_db.py "SELECT ..." --map /data/academy/07-map-tiles/sousse_small.mbtiles
import sqlite3
import sys

args = sys.argv[1:]
path = "/data/map.mbtiles"
if "--map" in args:
    i = args.index("--map")
    path = args[i + 1]
    del args[i:i + 2]

db = sqlite3.connect("file:" + path + "?mode=ro", uri=True)     # mode=ro: we can NOT change the file
if args:
    cur = db.execute(args[0])
    print(" | ".join(d[0] for d in cur.description))
    for n, row in enumerate(cur):
        if n == 50:
            print("... (only the first 50 rows are shown)")
            break
        print(" | ".join(f"<{len(v)} bytes>" if isinstance(v, bytes) else str(v) for v in row))
else:
    print(f"File: {path}\n\nTables:", [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")])
    print("\nmetadata:")
    for name, value in db.execute("SELECT name, value FROM metadata"):
        print(f"  {name:<18} {value}")
    print("\ntiles per zoom level:")
    for z, count in db.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
        print(f"  zoom {z:>2}: {count:>7} tiles")
