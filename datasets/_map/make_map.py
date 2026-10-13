#!/usr/bin/env python3
"""Builds the NAVERA Academy OpenStreetMap map of Sousse, end to end and reproducibly.

    make_map.sh [steps...]          (sets up the private pylib + PROJ_DATA, then runs this file)

Steps (default: all, in this order):
    download   Geofabrik Tunisia extract -> $OUT/osm/tunisia-<date>.osm.pbf (+ .sha256, md5 checked)
    extract    bbox (+0.07 deg, covers the z13 tile overhang) -> $OUT/osm/sousse-bbox-<date>.osm.pbf   (kept: ODbL "data on request")
    convert    -> $OUT/osm/sousse_osm.sqlite (EPSG:3857 WKB + R-trees, sea from coastline)
    style      regenerate the Mapnik XMLs + patterns next to this file (style_map.py)
    render     -> $OUT/osm_sousse.mbtiles (z13-19, JPEG q88, TMS rows), 6 processes, metatiles
    previews   -> $OUT/previews/*.jpg|png (sample tiles + 3x3 mosaics)
    verify     tile counts per zoom, sizes; writes $OUT/osm_sousse.build.json

Environment: OSM_OUT (default ~/academy-data), OSM_PBF (use this PBF instead of downloading),
             OSM_WORKERS (default 6).
"""
import datetime
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
import urllib.request
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser(os.environ.get('OSM_OUT', '~/academy-data'))
OSMDIR = os.path.join(OUT, 'osm')
DB = os.path.join(OSMDIR, 'sousse_osm.sqlite')
MBT = os.path.join(OUT, 'osm_sousse.mbtiles')
STATE = os.path.join(OSMDIR, 'build_state.json')
BBOX = (10.47, 35.70, 10.75, 35.97)          # W, S, E, N
ZMIN, ZMAX = 13, 19
JPEG_Q = 88
WORKERS = int(os.environ.get('OSM_WORKERS', '6'))
GEOFABRIK = 'https://download.geofabrik.de/africa/tunisia-latest.osm.pbf'
R = 20037508.342789244

sys.path.insert(0, HERE)


def state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(**kw):
    s = state()
    s.update(kw)
    os.makedirs(OSMDIR, exist_ok=True)
    json.dump(s, open(STATE, 'w'), indent=1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def pbf_timestamp(path):
    import osmium
    h = osmium.io.Reader(path, osmium.osm.osm_entity_bits.NOTHING).header()
    return h.get('osmosis_replication_timestamp') or ''


# ----------------------------------------------------------------------------- steps
def step_download():
    os.makedirs(OSMDIR, exist_ok=True)
    src = os.environ.get('OSM_PBF')
    if src:
        path = os.path.abspath(src)
    else:
        # resolve tunisia-latest -> tunisia-YYMMDD (Geofabrik redirects to the dated file)
        req = urllib.request.Request(GEOFABRIK, method='HEAD', headers={'User-Agent': 'navera-academy-map/1.0'})
        url = urllib.request.urlopen(req).geturl()
        stamp = url.rsplit('-', 1)[1].split('.')[0]               # 261012
        date = f'20{stamp[:2]}-{stamp[2:4]}-{stamp[4:6]}'
        path = os.path.join(OSMDIR, f'tunisia-{date}.osm.pbf')
        if not os.path.exists(path):
            print('downloading', url)
            tmp = path + '.part'
            urllib.request.urlretrieve(url, tmp)
            md5 = urllib.request.urlopen(url + '.md5').read().decode().split()[0]
            if hashlib.md5(open(tmp, 'rb').read()).hexdigest() != md5:
                raise SystemExit('md5 mismatch for ' + url)
            os.rename(tmp, path)
    ts = pbf_timestamp(path)
    digest = sha256(path)
    with open(path + '.sha256', 'w') as f:
        f.write(f'{digest}  {os.path.basename(path)}\n')
    date = os.path.basename(path).replace('tunisia-', '').replace('.osm.pbf', '')
    save_state(pbf=path, pbf_sha256=digest, pbf_timestamp=ts, pbf_date=date, pbf_size=os.path.getsize(path))
    print('PBF', path, digest, ts)


def step_extract():
    import osmdata
    s = state()
    out = os.path.join(OSMDIR, f'sousse-bbox-{s["pbf_date"]}.osm.pbf')
    t = time.time()
    osmdata.extract_bbox(s['pbf'], out, BBOX)
    save_state(extract=out, extract_sha256=sha256(out), extract_s=round(time.time() - t, 1))
    print('extract', out, os.path.getsize(out), 'bytes', '%.0fs' % (time.time() - t))


def step_convert():
    import osmdata
    s = state()
    t = time.time()
    stats = osmdata.convert(s['extract'], DB, BBOX)
    save_state(db=DB, db_stats=stats, convert_s=round(time.time() - t, 1))
    print('convert', stats, '%.0fs' % (time.time() - t))


def step_style():
    import style_map
    style_map.main()


# ----------------------------------------------------------------------------- render
def tile_range(z):
    n = 2 ** z

    def tx(lon):
        return int((lon + 180) / 360 * n)

    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * n)
    return tx(BBOX[0]), tx(BBOX[2]), ty(BBOX[3]), ty(BBOX[1])     # x0, x1, y0, y1 (inclusive)


_M = None


def _init():
    global _M
    import mapnik
    xml = open(os.path.join(HERE, 'style_map.xml')).read().replace('@DB@', DB)
    _M = mapnik.Map(256, 256)
    mapnik.load_map_from_string(_M, xml, False, HERE + '/')


def _render_meta(job):
    """Render one metatile (k x k tiles) and cut it into JPEG tiles."""
    import mapnik
    z, mx, my, k, x1, y1 = job
    n = 2 ** z
    s = 2 * R / n
    _M.resize(256 * k, 256 * k)
    _M.zoom_to_box(mapnik.Box2d(-R + mx * s, R - (my + k) * s, -R + (mx + k) * s, R - my * s))
    im = mapnik.Image(256 * k, 256 * k)
    mapnik.render(_M, im)
    out = []
    for dy in range(k):
        for dx in range(k):
            x, y = mx + dx, my + dy
            if x > x1 or y > y1:
                continue
            data = im.view(dx * 256, dy * 256, 256, 256).to_string(f'jpeg{JPEG_Q}')
            out.append((z, x, n - 1 - y, data))
    return out


def mbtiles_metadata(s):
    return {
        'name': 'Sousse - OpenStreetMap (NAVERA Academy)',
        'type': 'baselayer',
        'version': '1.1',
        'description': 'Sousse and surroundings, rendered from OpenStreetMap data by IRIS Systems for NAVERA Academy',
        'format': 'jpg',
        'bounds': ','.join(str(v) for v in BBOX),
        'center': '10.6388,35.8277,16',
        'minzoom': str(ZMIN),
        'maxzoom': str(ZMAX),
        'altitude_min': '150',
        'altitude_max': '2000',
        'altitude_zoom_map': '{"2000": 13, "1500": 14, "1000": 15, "500": 16, "300": 17, "200": 18, "150": 19}',
        'region': 'Sousse, Tunisia',
        'attribution': '© OpenStreetMap contributors',
        'attribution_url': 'https://www.openstreetmap.org/copyright',
        'attribution_html': '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>',
        'license': 'Map data ODbL (OpenStreetMap); rendered tiles: produced work',
        'source': ('OpenStreetMap data, Geofabrik Tunisia extract %s (data timestamp %s, sha256 %s); '
                   'rendered with Mapnik, style datasets/_map/style_map.xml' %
                   (os.path.basename(s.get('pbf', '')), s.get('pbf_timestamp', ''), s.get('pbf_sha256', ''))),
        'osm_data_date': s.get('pbf_timestamp', ''),
        'osm_pbf': os.path.basename(s.get('pbf', '')),
        'osm_pbf_sha256': s.get('pbf_sha256', ''),
        'jpeg_quality': str(JPEG_Q),
        'scheme': 'tms',
        'created': datetime.datetime.now().isoformat(timespec='seconds'),
    }


def step_render():
    s = state()
    jobs = []
    for z in range(ZMIN, ZMAX + 1):
        x0, x1, y0, y1 = tile_range(z)
        k = 8 if z >= 16 else 4
        for my in range(y0, y1 + 1, k):
            for mx in range(x0, x1 + 1, k):
                jobs.append((z, mx, my, k, x1, y1))
    tmp = MBT + '.part'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)')
    con.execute('CREATE TABLE tiles (zoom_level INTEGER NOT NULL, tile_column INTEGER NOT NULL, '
                'tile_row INTEGER NOT NULL, tile_data BLOB NOT NULL, PRIMARY KEY (zoom_level, tile_column, tile_row))')
    con.executemany('INSERT INTO metadata VALUES (?,?)', mbtiles_metadata(s).items())
    t = time.time()
    done = 0
    ntiles = 0
    with Pool(WORKERS, initializer=_init) as pool:
        for tiles in pool.imap_unordered(_render_meta, jobs, chunksize=2):
            con.executemany('INSERT INTO tiles VALUES (?,?,?,?)', tiles)
            ntiles += len(tiles)
            done += 1
            if done % 200 == 0:
                con.commit()
                el = time.time() - t
                print(f'  {done}/{len(jobs)} metatiles, {ntiles} tiles, {el:.0f}s, eta {el / done * (len(jobs) - done):.0f}s',
                      flush=True)
    con.commit()
    el = time.time() - t
    con.execute('CREATE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)')
    con.commit()
    con.close()
    os.replace(tmp, MBT)
    save_state(render_s=round(el, 1), render_tiles=ntiles, render_workers=WORKERS)
    print(f'render: {ntiles} tiles in {el:.0f}s -> {MBT}')


# ----------------------------------------------------------------------------- previews / verify
def xyz(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * n)


def step_previews():
    import cv2
    import numpy as np
    pdir = os.path.join(OUT, 'previews')
    os.makedirs(pdir, exist_ok=True)
    con = sqlite3.connect(MBT)

    def get(z, x, y):
        r = con.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                        (z, x, 2 ** z - 1 - y)).fetchone()
        if r is None:
            return np.full((256, 256, 3), 255, np.uint8)
        return cv2.imdecode(np.frombuffer(r[0], np.uint8), cv2.IMREAD_COLOR)
    ribat = (35.8277, 10.6388)
    written = []
    for f in os.listdir(pdir):                       # previews of this step only (render_view adds its own)
        if f.startswith(('tile_z', 'mosaic3x3_', 'overview_')):
            os.remove(os.path.join(pdir, f))
    for z in (13, 14, 16, 17, 19):
        x, y = xyz(*ribat, z)
        if z == 17:
            x, y = 69409, 51547                      # the Ribat tile (XYZ)
        p = os.path.join(pdir, f'tile_z{z}_{x}_{y}.jpg')
        r = con.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                        (z, x, 2 ** z - 1 - y)).fetchone()
        open(p, 'wb').write(r[0])                    # exactly as stored in the MBTiles
        mosaic = np.vstack([np.hstack([get(z, x + dx, y + dy) for dx in (-1, 0, 1)]) for dy in (-1, 0, 1)])
        p2 = os.path.join(pdir, f'mosaic3x3_z{z}_ribat.png')
        cv2.imwrite(p2, mosaic)
        written += [p, p2]
    # z13 overview of the whole area
    x0, x1, y0, y1 = tile_range(13)
    ov = np.vstack([np.hstack([get(13, x, y) for x in range(x0, x1 + 1)]) for y in range(y0, y1 + 1)])
    p = os.path.join(pdir, 'overview_z13_full_area.jpg')
    cv2.imwrite(p, ov, [cv2.IMWRITE_JPEG_QUALITY, 90])
    written.append(p)
    print('\n'.join(written))


def step_verify():
    s = state()
    con = sqlite3.connect(MBT)
    per = {}
    for z in range(ZMIN, ZMAX + 1):
        x0, x1, y0, y1 = tile_range(z)
        exp = (x1 - x0 + 1) * (y1 - y0 + 1)
        got, size = con.execute('SELECT count(*), sum(length(tile_data)) FROM tiles WHERE zoom_level=?', (z,)).fetchone()
        per[z] = {'expected': exp, 'tiles': got, 'mb': round((size or 0) / 1e6, 1)}
        print(f'z{z}: {got}/{exp} tiles, {per[z]["mb"]} MB')
        assert got == exp, f'missing tiles at z{z}'
    bad = con.execute("SELECT count(*) FROM tiles WHERE substr(hex(tile_data),1,6) != 'FFD8FF'").fetchone()[0]
    assert bad == 0, 'non-JPEG tiles'
    md = dict(con.execute('SELECT name, value FROM metadata'))
    for k in ('name', 'format', 'bounds', 'minzoom', 'maxzoom', 'attribution', 'license'):
        assert md.get(k), k
    info = {'mbtiles': MBT, 'mbtiles_mb': round(os.path.getsize(MBT) / 1e6, 1), 'per_zoom': per,
            'total_tiles': sum(v['tiles'] for v in per.values()), 'metadata': md, 'build': s}
    json.dump(info, open(os.path.join(OUT, 'osm_sousse.build.json'), 'w'), indent=1, ensure_ascii=False)
    print('total', info['total_tiles'], 'tiles,', info['mbtiles_mb'], 'MB')


STEPS = ['download', 'extract', 'convert', 'style', 'render', 'previews', 'verify']

if __name__ == '__main__':
    steps = sys.argv[1:] or STEPS
    for st in steps:
        t = time.time()
        print(f'== {st}', flush=True)
        globals()['step_' + st]()
        print(f'== {st} done in {time.time() - t:.0f}s', flush=True)
