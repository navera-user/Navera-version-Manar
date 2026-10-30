"""OSM -> render-ready SQLite (EPSG:3857, WKB) for the NAVERA Academy Sousse map.

Used by make_map.py (steps `extract` and `convert`). Needs the private pylib (osmium, shapely),
see README.md.

Output tables (all geometries WKB in EPSG:3857 metres, column `geom`; each with an R-tree
`idx_<table>_geom(pkid,xmin,xmax,ymin,ymax)` as Mapnik's sqlite plugin expects):
    landuse(id, osm_id, kind, area)       polygons, inserted largest first
    water(id, osm_id, kind, area)         inland water polygons
    sea(id, kind)                         sea polygons built from natural=coastline
    buildings(id, osm_id, kind, area, roof, roofd)   roof/roofd: deterministic colours from osm_id
    roads(id, osm_id, kind, zorder, bridge, tunnel)
    rail(id, osm_id, kind, bridge, tunnel)
    waterways(id, osm_id, kind)
"""
import hashlib
import json
import math
import os
import sqlite3

import osmium
import shapely
from shapely import ops, wkb
from shapely.geometry import LineString, Point, box

R = 6378137.0


def lonlat_to_merc(coords):
    import numpy as np
    c = np.asarray(coords, dtype=float)
    x = R * np.radians(c[:, 0])
    y = R * np.log(np.tan(np.pi / 4 + np.radians(np.clip(c[:, 1], -85, 85)) / 2))
    return np.stack([x, y], axis=1)


def to_merc(g):
    return shapely.transform(g, lonlat_to_merc)


# ----------------------------------------------------------------------------- extract
def extract_bbox(pbf, out, bbox, margin=0.07):
    """Write all nodes inside bbox(+margin), every way touching them, the relations using those
    ways (multipolygons etc.), completed with all referenced members (osmium BackReference)."""
    w, s, e, n = bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin
    tr = osmium.IdTracker()
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE):
        lo = o.location
        if lo.valid() and w <= lo.lon <= e and s <= lo.lat <= n:
            tr.add_node(o.id)
    nodes = tr.node_ids()
    for o in osmium.FileProcessor(pbf, osmium.osm.WAY):
        if any(nr.ref in nodes for nr in o.nodes):
            tr.add_way(o.id)
    ways = tr.way_ids()
    for o in osmium.FileProcessor(pbf, osmium.osm.RELATION):
        if o.tags.get('type') not in ('multipolygon',):
            continue
        if any((m.type == 'w' and m.ref in ways) for m in o.members):
            tr.add_relation(o.id)
    tr.complete_backward_references(pbf, relation_depth=2)
    if os.path.exists(out):
        os.remove(out)
    with osmium.SimpleWriter(out) as wr:
        for o in osmium.FileProcessor(pbf).with_filter(tr.id_filter()):
            wr.add(o)


# ----------------------------------------------------------------------------- classify
LANDUSE = {
    # key=value -> kind
    'landuse': {'residential': 'residential', 'commercial': 'commercial', 'retail': 'commercial',
                'industrial': 'industrial', 'railway': 'industrial', 'port': 'industrial',
                'construction': 'construction', 'brownfield': 'construction', 'greenfield': 'grass',
                'farmland': 'farmland', 'farmyard': 'farmyard', 'orchard': 'orchard', 'vineyard': 'orchard',
                'plant_nursery': 'orchard', 'meadow': 'grass', 'grass': 'grass', 'village_green': 'grass',
                'recreation_ground': 'park', 'forest': 'wood', 'cemetery': 'cemetery', 'military': 'military',
                'allotments': 'farmland', 'greenhouse_horticulture': 'farmyard', 'landfill': 'bare',
                'quarry': 'bare', 'religious': 'institution', 'education': 'institution',
                'salt_pond': 'saltpond', 'basin': 'water', 'reservoir': 'water', 'aquaculture': 'water'},
    'natural': {'wood': 'wood', 'scrub': 'scrub', 'heath': 'scrub', 'grassland': 'grass',
                'sand': 'sand', 'beach': 'sand', 'bare_rock': 'bare', 'scree': 'bare', 'shingle': 'sand',
                'wetland': 'wetland', 'mud': 'wetland', 'water': 'water', 'bay': None},
    'leisure': {'park': 'park', 'garden': 'park', 'golf_course': 'golf', 'pitch': 'pitch',
                'stadium': 'stadium', 'sports_centre': 'stadium', 'playground': 'park',
                'nature_reserve': None, 'marina': 'water_marina', 'swimming_pool': 'water',
                'track': 'pitch'},
    'amenity': {'school': 'institution', 'university': 'institution', 'college': 'institution',
                'hospital': 'hospital', 'clinic': 'hospital', 'parking': 'parking', 'grave_yard': 'cemetery',
                'marketplace': 'commercial', 'place_of_worship': 'institution', 'fuel': 'parking'},
    'aeroway': {'aerodrome': 'aerodrome', 'apron': 'parking', 'runway': 'runway', 'taxiway': 'runway'},
    'tourism': {'zoo': 'park', 'theme_park': 'park', 'camp_site': 'grass'},
    'man_made': {'pier': 'pier', 'breakwater': 'pier', 'wastewater_plant': 'industrial', 'works': 'industrial'},
    'waterway': {'riverbank': 'water', 'dock': 'water'},
    'highway': {'pedestrian': 'pedestrian', 'footway': 'pedestrian'},   # areas only
    'place': {'square': 'pedestrian'},
}
LAND_KEYS = list(LANDUSE)

ROADS = {'motorway': 'motorway', 'motorway_link': 'motorway', 'trunk': 'trunk', 'trunk_link': 'trunk',
         'primary': 'primary', 'primary_link': 'primary', 'secondary': 'secondary',
         'secondary_link': 'secondary', 'tertiary': 'tertiary', 'tertiary_link': 'tertiary',
         'residential': 'minor', 'unclassified': 'minor', 'living_street': 'minor', 'road': 'minor',
         'service': 'service', 'pedestrian': 'pedestrian', 'track': 'track', 'footway': 'path',
         'path': 'path', 'cycleway': 'path', 'steps': 'path', 'bridleway': 'path', 'busway': 'minor',
         'raceway': 'minor'}
ZORDER = {'motorway': 9, 'trunk': 8, 'primary': 7, 'secondary': 6, 'tertiary': 5, 'minor': 4,
          'pedestrian': 3, 'service': 2, 'track': 1, 'path': 0}


def land_kind(tags):
    if tags.get('natural') == 'water' and tags.get('water') in ('salt_pool', 'lagoon') or tags.get('salt') == 'yes':
        return 'saltpond' if tags.get('natural') == 'water' else None
    for k in LAND_KEYS:
        v = tags.get(k)
        if v is not None and v in LANDUSE[k]:
            kind = LANDUSE[k][v]
            if kind:
                if kind == 'water_marina':
                    return None
                return kind
    return None


def roof_colours(osm_id):
    """Deterministic roof colour (hex) + a darker variant, from the OSM id. Sousse roofs: mostly
    white/cream terraces, some beige, grey concrete, a few terracotta and light blue/green."""
    h = hashlib.blake2b(str(osm_id).encode(), digest_size=8).digest()
    r0 = h[0] / 255.0
    palette = [((236, 233, 224), 0.30), ((222, 214, 198), 0.18), ((205, 196, 182), 0.14),
               ((188, 186, 182), 0.12), ((214, 200, 170), 0.08), ((170, 100, 78), 0.06),
               ((150, 150, 150), 0.05), ((176, 196, 200), 0.04), ((242, 242, 238), 0.03)]
    acc = 0.0
    base = palette[-1][0]
    for col, p in palette:
        acc += p
        if r0 <= acc:
            base = col
            break
    j = [(h[i] / 255.0 - 0.5) * 8 for i in (1, 2, 3)]
    lum = (h[4] / 255.0 - 0.5) * 24
    c = [int(max(0, min(255, base[i] + j[i] + lum))) for i in range(3)]
    d = [int(v * 0.82) for v in c]
    return '#%02x%02x%02x' % tuple(c), '#%02x%02x%02x' % tuple(d)


# ----------------------------------------------------------------------------- convert
SCHEMA = {
    'landuse': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, area REAL, geom BLOB',
    'water': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, area REAL, geom BLOB',
    'sea': 'id INTEGER PRIMARY KEY, kind TEXT, geom BLOB',
    'buildings': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, area REAL, roof TEXT, roofd TEXT, geom BLOB',
    'roads': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, zorder INTEGER, bridge INTEGER, tunnel INTEGER, geom BLOB',
    'rail': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, bridge INTEGER, tunnel INTEGER, geom BLOB',
    'waterways': 'id INTEGER PRIMARY KEY, osm_id INTEGER, kind TEXT, geom BLOB',
}


def build_sea(coast_lines, bbox):
    """Sea polygons inside bbox from coastline ways (land on the left of the way direction)."""
    w, s, e, n = bbox
    frame = box(w, s, e, n)
    big = box(w - 0.5, s - 0.5, e + 0.5, n + 0.5)
    if not coast_lines:
        return []
    merged = ops.linemerge(shapely.MultiLineString(coast_lines))
    lines = list(merged.geoms) if hasattr(merged, 'geoms') else [merged]
    lines = [l for l in lines if l.intersects(big)]
    pieces = ops.split(frame, shapely.MultiLineString(lines)).geoms
    segs = []
    for l in lines:
        c = list(l.coords)
        segs += [(c[i], c[i + 1]) for i in range(len(c) - 1)]
    import numpy as np
    A = np.array([s_[0] for s_ in segs])
    B = np.array([s_[1] for s_ in segs])
    sea = []
    for p in pieces:
        q = p.representative_point()
        P = np.array([q.x, q.y])
        AB = B - A
        t = np.clip(((P - A) * AB).sum(1) / np.maximum((AB * AB).sum(1), 1e-18), 0, 1)
        proj = A + AB * t[:, None]
        d = ((proj - P) ** 2).sum(1)
        i = int(np.argmin(d))
        cross = AB[i, 0] * (P[1] - A[i, 1]) - AB[i, 1] * (P[0] - A[i, 0])
        if cross < 0:          # right of the coastline -> water
            sea.append(p)
    return sea


def convert(osm_file, db, bbox):
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    for t, cols in SCHEMA.items():
        con.execute(f'CREATE TABLE {t} ({cols})')
    gf = osmium.geom.WKBFactory()
    clip = box(*lonlat_to_merc([[bbox[0] - 0.07, bbox[1] - 0.07]])[0],
               *lonlat_to_merc([[bbox[2] + 0.07, bbox[3] + 0.07]])[0])
    rows = {t: [] for t in SCHEMA}
    coast = []
    stats = {}
    keys = ('building', 'highway', 'railway', 'waterway', 'natural', 'landuse', 'leisure', 'amenity',
            'aeroway', 'tourism', 'man_made', 'place', 'water')
    fp = osmium.FileProcessor(osm_file).with_areas().with_locations().with_filter(osmium.filter.KeyFilter(*keys))
    for o in fp:
        if o.is_node():
            continue
        tags = dict(o.tags)
        try:
            if o.is_area():
                oid = o.orig_id()
                g = to_merc(wkb.loads(gf.create_multipolygon(o), hex=True))
                if not g.is_valid:
                    g = shapely.make_valid(g)
                if not g.intersects(clip):
                    continue
                g = g.intersection(clip) if not clip.contains(g) else g
                if g.is_empty:
                    continue
                b = tags.get('building') or (tags.get('building:part') and None)
                if b and b != 'no':
                    rf, rd = roof_colours(oid)
                    rows['buildings'].append((oid, b, g.area, rf, rd, g.wkb))
                    continue
                k = land_kind(tags)
                if k in ('water', 'saltpond'):
                    rows['water'].append((oid, k, g.area, g.wkb))
                elif k:
                    rows['landuse'].append((oid, k, g.area, g.wkb))
            elif o.is_way():
                hw, rw, ww = tags.get('highway'), tags.get('railway'), tags.get('waterway')
                nat = tags.get('natural')
                if not (hw in ROADS or rw or ww or nat == 'coastline' or tags.get('man_made') in ('pier', 'breakwater')
                        or tags.get('aeroway') in ('runway', 'taxiway')):
                    continue
                if tags.get('area') == 'yes':
                    continue
                gl = wkb.loads(gf.create_linestring(o), hex=True)
                if nat == 'coastline':
                    coast.append(gl)
                    continue
                g = to_merc(gl)
                if not g.intersects(clip):
                    continue
                br = 1 if tags.get('bridge') not in (None, 'no') else 0
                tn = 1 if tags.get('tunnel') not in (None, 'no') or tags.get('covered') == 'yes' else 0
                if hw in ROADS:
                    k = ROADS[hw]
                    rows['roads'].append((o.id, k, ZORDER[k] + 10 * br - 10 * tn, br, tn, g.wkb))
                elif tags.get('aeroway') in ('runway', 'taxiway'):
                    rows['roads'].append((o.id, tags['aeroway'], 1, 0, 0, g.wkb))
                elif tags.get('man_made') in ('pier', 'breakwater'):
                    rows['roads'].append((o.id, 'pier', 0, 0, 0, g.wkb))
                elif rw in ('rail', 'light_rail', 'narrow_gauge', 'tram', 'subway', 'disused', 'abandoned'):
                    if rw in ('disused', 'abandoned'):
                        continue
                    rows['rail'].append((o.id, rw, br, tn, g.wkb))
                elif ww in ('river', 'stream', 'canal', 'drain', 'ditch', 'wadi'):
                    rows['waterways'].append((o.id, ww, g.wkb))
        except Exception as ex:          # broken geometry in OSM: skip, but count
            stats['skipped'] = stats.get('skipped', 0) + 1
    # sea
    sea = build_sea(coast, bbox=(bbox[0] - 0.07, bbox[1] - 0.07, bbox[2] + 0.07, bbox[3] + 0.07))
    for p in sea:
        rows['sea'].append(('sea', to_merc(p).wkb))
    # insert (landuse/water largest first so small features draw on top)
    rows['landuse'].sort(key=lambda r: -r[2])
    rows['water'].sort(key=lambda r: -r[2])
    rows['roads'].sort(key=lambda r: r[2])
    for t, rs in rows.items():
        cols = [c.split()[0] for c in SCHEMA[t].split(', ')][1:]
        con.executemany(f'INSERT INTO {t} ({",".join(cols)}) VALUES ({",".join("?" * len(cols))})', rs)
        con.execute(f'CREATE VIRTUAL TABLE idx_{t}_geom USING rtree(pkid, xmin, xmax, ymin, ymax)')
        idx = []
        for rid, gb in con.execute(f'SELECT id, geom FROM {t}'):
            x0, y0, x1, y1 = wkb.loads(gb).bounds
            idx.append((rid, x0, x1, y0, y1))
        con.executemany(f'INSERT INTO idx_{t}_geom VALUES (?,?,?,?,?)', idx)
        stats[t] = len(rs)
    con.commit()
    con.execute('VACUUM')
    con.close()
    return stats
