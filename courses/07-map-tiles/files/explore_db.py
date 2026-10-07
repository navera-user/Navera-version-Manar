# Look inside an MBTiles file (always read only). Usage:
#     python3 explore_db.py                      -> tables, schema, metadata, file size, tiles per zoom
#     python3 explore_db.py "SELECT ... "        -> runs YOUR SQL query and prints the rows (max 50)
#     python3 explore_db.py "SELECT ..." --map /data/academy/07-map-tiles/sousse_small.mbtiles
import os
import sqlite3
import sys

args = sys.argv[1:]
path = "/data/map.mbtiles"
if "--map" in args:
    i = args.index("--map")
    path = args[i + 1]
    del args[i:i + 2]

db = sqlite3.connect("file:" + path + "?mode=ro", uri=True)     # mode=ro: this program can NOT change the file
if args:
    cur = db.execute(args[0])
    print(" | ".join(d[0] for d in cur.description))
    for n, row in enumerate(cur):
        if n == 50:
            print("... (only the first 50 rows are shown)")
            break
        print(" | ".join(f"<{len(v)} bytes>" if isinstance(v, bytes) else str(v) for v in row))
else:
    print(f"File: {path}")
    print("\nSchema (sqlite_master):")
    for kind, name, sql in db.execute("SELECT type, name, sql FROM sqlite_master"):
        print(f"  {kind:<6} {name:<28} {' '.join((sql or '(automatic)').split())}")
    page_size = db.execute("PRAGMA page_size").fetchone()[0]
    page_count = db.execute("PRAGMA page_count").fetchone()[0]
    print(f"\nSQLite pages: {page_count} pages x {page_size} bytes = {page_count * page_size} bytes")
    print(f"os.path.getsize: {os.path.getsize(path)} bytes = {os.path.getsize(path) / 1e9:.2f} GB")
    print("\nmetadata:")
    for name, value in db.execute("SELECT name, value FROM metadata"):
        print(f"  {name:<18} {value}")
    print("\ntiles per zoom level (counting a million index entries can take ~20 s the first time):")
    for z, count in db.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
        print(f"  zoom {z:>2}: {count:>7} tiles")
