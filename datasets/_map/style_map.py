#!/usr/bin/env python3
"""Generates the Mapnik styles of the NAVERA Academy OSM map (run by make_map.py `style`).

    style_map.xml               clean cartographic style (the MBTiles tiles, render_view style="map")
    style_pseudo_ground.xml     pseudo-satellite: ground classes as flat code colours (render_view textures them)
    style_pseudo_top.xml        pseudo-satellite: roads/rail (asphalt colours) on transparent background
    style_pseudo_bld.xml        pseudo-satellite: buildings, roof colour per OSM id, on transparent background
    patterns/*.png              small fill patterns (orchard dots, wood, wetland, sand)

All XMLs contain the placeholder @DB@ for the render SQLite made by osmdata.convert().
Rules are per zoom 13..19 (scale denominators of 256-px web-mercator tiles), so the same style
also works at arbitrary scales (render_view picks the rule of the nearest zoom).
"""
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ZOOMS = list(range(13, 20))
SD = {z: 559082264.028 / 2 ** z for z in ZOOMS}


def scale_attrs(z):
    """Rule scale range for zoom z: geometric half-way to the neighbouring zooms (z13/z19 open-ended)."""
    s = ''
    if z > ZOOMS[0]:
        s += f'<MaxScaleDenominator>{SD[z] * math.sqrt(2):.1f}</MaxScaleDenominator>'
    if z < ZOOMS[-1]:
        s += f'<MinScaleDenominator>{SD[z] / math.sqrt(2):.1f}</MinScaleDenominator>'
    return s


def from_zoom(z0):
    return f'<MaxScaleDenominator>{SD[z0] * math.sqrt(2):.1f}</MaxScaleDenominator>' if z0 > ZOOMS[0] else ''


def ds(table, extra=''):
    return (f'<Datasource><Parameter name="type">sqlite</Parameter><Parameter name="file">@DB@</Parameter>'
            f'<Parameter name="table">{table}</Parameter><Parameter name="geometry_field">geom</Parameter>'
            f'<Parameter name="key_field">id</Parameter><Parameter name="wkb_format">generic</Parameter>'
            f'<Parameter name="use_spatial_index">true</Parameter>{extra}</Datasource>')


def layer(name, table, styles, ds_extra=''):
    st = ''.join(f'<StyleName>{s}</StyleName>' for s in styles)
    return f'<Layer name="{name}" srs="epsg:3857" cache-features="true">{st}{ds(table, ds_extra)}</Layer>'


# ----------------------------------------------------------------------------- map style
LAND_BG = '#f2efe9'
SEA = '#aad3df'
LAND = {   # kind: (fill, outline or None, pattern or None)
    'residential': ('#e5e0d8', None, None), 'commercial': ('#f2dede', '#e6c9c9', None),
    'industrial': ('#ebdbe8', '#d8c2d2', None), 'construction': ('#e3decb', None, None),
    'farmland': ('#eef0d5', '#dcdfba', None), 'farmyard': ('#f5dcba', None, None),
    'orchard': ('#d8e9bc', None, 'orchard'), 'grass': ('#cdebb0', None, None), 'park': ('#c8facc', '#a8dca8', None),
    'wood': ('#add19e', None, 'wood'), 'scrub': ('#c8d7ab', None, None), 'sand': ('#f5e9c6', None, 'sand'),
    'bare': ('#e6dccf', None, None), 'wetland': ('#d4e6dd', None, 'wetland'), 'cemetery': ('#aacbaf', '#8fb193', None),
    'military': ('#f0d6d2', '#d9a9a3', None), 'institution': ('#f5ead6', '#e0cfae', None),
    'hospital': ('#f6e3e0', '#e4c0ba', None), 'parking': ('#e2e2e2', '#cfcfcf', None),
    'pitch': ('#aae0cb', '#88c9b0', None), 'stadium': ('#dff5e6', '#b9dcc5', None), 'golf': ('#def6c0', None, None),
    'aerodrome': ('#e6e4f0', '#c9c5dc', None), 'pedestrian': ('#ddd8de', '#c4bfc6', None),
    'pier': (LAND_BG, '#c9c3b6', None), 'runway': ('#bbbbcc', None, None),
}
# road widths (fill, px) for zooms 13..19 and colours (fill, casing)
ROADW = {
    'motorway': [2.5, 3.5, 5, 8, 12, 18, 26], 'trunk': [2.2, 3, 4.5, 7, 11, 16, 24],
    'primary': [2, 3, 4.5, 7, 11, 16, 24], 'secondary': [1.6, 2.5, 4, 6.5, 10, 14, 22],
    'tertiary': [1.2, 2, 3.5, 6, 9, 13, 20], 'minor': [0.6, 1, 2, 4, 7, 11, 17],
    'pedestrian': [0, 0.6, 1.2, 2.5, 4.5, 7, 11], 'service': [0, 0.5, 1, 2, 3.5, 6, 9],
    'track': [0, 0.6, 0.8, 1.2, 1.6, 2, 3], 'path': [0, 0, 0.5, 0.8, 1.2, 1.6, 2],
    'runway': [3, 5, 8, 14, 24, 40, 70], 'taxiway': [1, 1.5, 2.5, 4, 7, 12, 20], 'pier': [0.5, 1, 2, 3, 5, 8, 12],
}
ROADC = {
    'motorway': ('#e892a2', '#c24e6b'), 'trunk': ('#f9b29c', '#c84e2f'), 'primary': ('#fcd6a4', '#a06b00'),
    'secondary': ('#f7fabf', '#707d05'), 'tertiary': ('#ffffff', '#8f8f8f'), 'minor': ('#ffffff', '#b5b0a8'),
    'pedestrian': ('#ddd8de', '#a8a3a8'), 'service': ('#ffffff', '#bdb8b0'), 'runway': ('#bbbbcc', None),
    'taxiway': ('#bbbbcc', None), 'pier': (LAND_BG, '#b5ae9f'),
}
CASE = [0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5]


def map_xml():
    st = []
    # landuse
    rules = []
    for k, (fill, line, pat) in LAND.items():
        sym = f'<PolygonSymbolizer fill="{fill}" gamma="0.6"/>'
        if pat:
            sym += f'<PolygonPatternSymbolizer file="patterns/{pat}.png" opacity="0.9"/>'
        rules.append(f'<Rule><Filter>[kind]=\'{k}\'</Filter>{sym}</Rule>')
        if line:
            rules.append(f'<Rule>{from_zoom(15)}<Filter>[kind]=\'{k}\'</Filter><LineSymbolizer stroke="{line}" stroke-width="0.7"/></Rule>')
    st.append('<Style name="landuse">' + ''.join(rules) + '</Style>')
    st.append(f'<Style name="water"><Rule><Filter>[kind]=\'saltpond\'</Filter><PolygonSymbolizer fill="#c3dde3"/>'
              f'<LineSymbolizer stroke="#9cc3cd" stroke-width="0.8"/></Rule>'
              f'<Rule><ElseFilter/><PolygonSymbolizer fill="{SEA}"/></Rule></Style>')
    st.append(f'<Style name="sea"><Rule><PolygonSymbolizer fill="{SEA}"/>'
              f'<LineSymbolizer stroke="#8fbfcf" stroke-width="1"/></Rule></Style>')
    ww = [0.6, 0.8, 1.2, 1.8, 2.5, 3.5, 5]
    st.append('<Style name="waterways">' + ''.join(
        f'<Rule>{scale_attrs(z)}<LineSymbolizer stroke="{SEA}" stroke-width="{ww[i]}" stroke-linecap="round"/></Rule>'
        for i, z in enumerate(ZOOMS)) + '</Style>')
    # buildings
    bw = [0, 0, 0.4, 0.6, 0.8, 1.0, 1.2]
    br = []
    for i, z in enumerate(ZOOMS):
        sym = '<PolygonSymbolizer fill="#d9d0c9"/>'
        if bw[i]:
            sym += f'<LineSymbolizer stroke="#b3a495" stroke-width="{bw[i]}"/>'
        if z >= 14:
            br.append(f'<Rule>{scale_attrs(z)}{sym}</Rule>')
        else:
            br.append(f'<Rule>{scale_attrs(z)}<Filter>[area] &gt; 2000</Filter>{sym}</Rule>')
    st.append('<Style name="buildings">' + ''.join(br) + '</Style>')
    # roads: casing then fill (two styles on the same layer => all casings below all fills)
    cas, fil = [], []
    for k, ws in ROADW.items():
        for i, z in enumerate(ZOOMS):
            w = ws[i]
            if w <= 0:
                continue
            f = f'<Filter>[kind]=\'{k}\'</Filter>'
            if k == 'track':
                fil.append(f'<Rule>{scale_attrs(z)}{f}<LineSymbolizer stroke="#996600" stroke-width="{w}" '
                           f'stroke-dasharray="{3 + i},{2 + i * 0.5:.1f}" stroke-opacity="0.8"/></Rule>')
                continue
            if k == 'path':
                fil.append(f'<Rule>{scale_attrs(z)}{f}<LineSymbolizer stroke="#fa8072" stroke-width="{w}" '
                           f'stroke-dasharray="{2 + i * 0.5:.1f},{1.5 + i * 0.4:.1f}"/></Rule>')
                continue
            fc, cc = ROADC[k]
            if cc and w >= 0.9:
                cw = w + 2 * CASE[i]
                cas.append(f'<Rule>{scale_attrs(z)}{f}<LineSymbolizer stroke="{cc}" stroke-width="{cw:.2f}" '
                           f'stroke-linecap="round" stroke-linejoin="round"/></Rule>')
            col = fc if (w >= 0.9 or not cc) else cc
            fil.append(f'<Rule>{scale_attrs(z)}{f}<LineSymbolizer stroke="{col}" stroke-width="{w}" '
                       f'stroke-linecap="round" stroke-linejoin="round"/></Rule>')
    st.append('<Style name="roads-casing">' + ''.join(cas) + '</Style>')
    st.append('<Style name="roads-fill">' + ''.join(fil) + '</Style>')
    # bridges: same, but drawn last with a dark casing
    st.append('<Style name="bridge-casing">' + ''.join(r.replace('stroke-linecap="round"', 'stroke-linecap="butt"')
                                                       for r in cas) + '</Style>')
    # rail: grey line + white dashes from z15
    rw = [1, 1.5, 2, 3, 3.5, 4, 5]
    rr = []
    for i, z in enumerate(ZOOMS):
        rr.append(f'<Rule>{scale_attrs(z)}<Filter>[tunnel]=0</Filter><LineSymbolizer stroke="#707070" stroke-width="{rw[i]}"/>'
                  + (f'<LineSymbolizer stroke="#ffffff" stroke-width="{rw[i] * 0.45:.2f}" stroke-dasharray="{4 + 2 * i},{4 + 2 * i}"/>' if z >= 15 else '')
                  + '</Rule>')
        rr.append(f'<Rule>{scale_attrs(z)}<Filter>[tunnel]=1</Filter><LineSymbolizer stroke="#909090" stroke-width="{rw[i]}" stroke-dasharray="3,3"/></Rule>')
    st.append('<Style name="rail">' + ''.join(rr) + '</Style>')
    layers = [
        layer('landuse', 'landuse', ['landuse']),
        layer('water', 'water', ['water']),
        layer('waterways', 'waterways', ['waterways']),
        layer('sea', 'sea', ['sea']),
        layer('roads', '(SELECT * FROM roads WHERE bridge=0 ORDER BY zorder)', ['roads-casing', 'roads-fill']),
        layer('rail', 'rail', ['rail']),
        layer('buildings', 'buildings', ['buildings']),
        layer('bridges', '(SELECT * FROM roads WHERE bridge=1 ORDER BY zorder)', ['bridge-casing', 'roads-fill']),
    ]
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<Map srs="epsg:3857" background-color="{LAND_BG}" buffer-size="64">\n'
            + '\n'.join(st) + '\n' + '\n'.join(layers) + '\n</Map>\n')


# ----------------------------------------------------------------------------- pseudo-satellite
# ground class codes: render_view maps each code colour back to a class and paints a texture.
PSEUDO_CLASSES = ['land', 'sea', 'water', 'saltpond', 'residential', 'commercial', 'industrial', 'construction',
                  'farmland', 'farmyard', 'orchard', 'grass', 'park', 'wood', 'scrub', 'sand', 'bare', 'wetland',
                  'cemetery', 'military', 'institution', 'hospital', 'parking', 'pitch', 'stadium', 'golf',
                  'aerodrome', 'pedestrian', 'pier', 'runway']


def code_colour(i):
    return '#%02x%02x%02x' % ((i * 37) % 256, (i * 11 + 40) % 256, 200 - i * 5)


def pseudo_ground_xml():
    rules = []
    for i, k in enumerate(PSEUDO_CLASSES):
        if k in ('land', 'sea', 'water', 'saltpond'):
            continue
        rules.append(f'<Rule><Filter>[kind]=\'{k}\'</Filter><PolygonSymbolizer fill="{code_colour(i)}" gamma="0.3"/></Rule>')
    wat = (f'<Rule><Filter>[kind]=\'saltpond\'</Filter><PolygonSymbolizer fill="{code_colour(3)}" gamma="0.3"/></Rule>'
           f'<Rule><ElseFilter/><PolygonSymbolizer fill="{code_colour(2)}" gamma="0.3"/></Rule>')
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<Map srs="epsg:3857" background-color="{code_colour(0)}" buffer-size="64">\n'
            f'<Style name="landuse">{"".join(rules)}</Style>\n<Style name="water">{wat}</Style>\n'
            f'<Style name="sea"><Rule><PolygonSymbolizer fill="{code_colour(1)}" gamma="0.3"/></Rule></Style>\n'
            + layer('landuse', 'landuse', ['landuse']) + layer('water', 'water', ['water'])
            + layer('sea', 'sea', ['sea']) + '\n</Map>\n')


# ground metres for pseudo roads (real widths, scaled by render_view through scale_factor trick:
# render_view renders at ~1 px = 1 m-ish zoom so widths are given for each zoom like the map).
PROADW_M = {'motorway': 22, 'trunk': 16, 'primary': 13, 'secondary': 11, 'tertiary': 9, 'minor': 6.5,
            'pedestrian': 5, 'service': 4, 'track': 3, 'path': 1.5, 'runway': 45, 'taxiway': 18, 'pier': 6}
PROADC = {'motorway': '#5d5f61', 'trunk': '#626466', 'primary': '#67686a', 'secondary': '#6d6d6c',
          'tertiary': '#737270', 'minor': '#7d7a76', 'pedestrian': '#b9b0a3', 'service': '#8a8680',
          'track': '#b49a78', 'path': '#c4b49a', 'runway': '#55575a', 'taxiway': '#5f6164', 'pier': '#c9c2b5'}


def m_per_px(z, lat=35.83):
    return 156543.034 * math.cos(math.radians(lat)) / 2 ** z


def pseudo_top_xml():
    rules = []
    for k, wm in PROADW_M.items():
        for z in ZOOMS:
            w = max(wm / m_per_px(z), 0.6)
            f = f'<Filter>[kind]=\'{k}\'</Filter>'
            rules.append(f'<Rule>{scale_attrs(z)}{f}<LineSymbolizer stroke="{PROADC[k]}" stroke-width="{w:.2f}" '
                         f'stroke-linecap="butt" stroke-linejoin="round"/>'
                         + (f'<LineSymbolizer stroke="#e8e6df" stroke-width="{max(0.15 / m_per_px(z), 0.4):.2f}" '
                            f'stroke-dasharray="{3 / m_per_px(z):.1f},{6 / m_per_px(z):.1f}" stroke-opacity="0.85"/>'
                            if k in ('motorway', 'trunk', 'primary', 'secondary') and z >= 17 else '')
                         + '</Rule>')
    rail = ''.join(f'<Rule>{scale_attrs(z)}<LineSymbolizer stroke="#6b625a" stroke-width="{max(4 / m_per_px(z), 0.8):.2f}"/>'
                   f'<LineSymbolizer stroke="#3f3a36" stroke-width="{max(1.6 / m_per_px(z), 0.4):.2f}"/></Rule>' for z in ZOOMS)
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Map srs="epsg:3857" background-color="transparent" buffer-size="64">\n'
            f'<Style name="roads">{"".join(rules)}</Style>\n<Style name="rail">{rail}</Style>\n'
            + layer('roads', '(SELECT * FROM roads WHERE tunnel=0 ORDER BY zorder)', ['roads'])
            + layer('rail', '(SELECT * FROM rail WHERE tunnel=0)', ['rail']) + '\n</Map>\n')


def pseudo_bld_xml():
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Map srs="epsg:3857" background-color="transparent" buffer-size="64">\n'
            '<Style name="b"><Rule><PolygonSymbolizer fill="[roof]"/><LineSymbolizer stroke="[roofd]" stroke-width="1"/></Rule></Style>\n'
            + layer('buildings', 'buildings', ['b']) + '\n</Map>\n')


# ----------------------------------------------------------------------------- patterns
def make_patterns(d):
    import cv2
    os.makedirs(d, exist_ok=True)
    rng = np.random.default_rng(7)

    def save(name, img):
        cv2.imwrite(os.path.join(d, name + '.png'), img)

    # orchard: regular rows of small dark-green dots (olive groves)
    a = np.zeros((16, 16, 4), np.uint8)
    for (x, y) in ((4, 4), (12, 12)):
        cv2.circle(a, (x, y), 2, (90, 150, 110, 200), -1, cv2.LINE_AA)
    save('orchard', a)
    # wood: irregular tree crowns
    a = np.zeros((32, 32, 4), np.uint8)
    for _ in range(7):
        x, y = rng.integers(3, 29, 2)
        cv2.circle(a, (int(x), int(y)), int(rng.integers(2, 4)), (100, 160, 120, 150), -1, cv2.LINE_AA)
    save('wood', a)
    # wetland: short horizontal blue dashes
    a = np.zeros((16, 24, 4), np.uint8)
    cv2.line(a, (2, 4), (9, 4), (190, 160, 110, 220), 1)
    cv2.line(a, (14, 12), (21, 12), (190, 160, 110, 220), 1)
    save('wetland', a)
    # sand: sparse dots
    a = np.zeros((16, 16, 4), np.uint8)
    for _ in range(5):
        x, y = rng.integers(0, 16, 2)
        a[y, x] = (120, 190, 215, 220)
    save('sand', a)


def main():
    make_patterns(os.path.join(HERE, 'patterns'))
    for name, xml in (('style_map.xml', map_xml()), ('style_pseudo_ground.xml', pseudo_ground_xml()),
                      ('style_pseudo_top.xml', pseudo_top_xml()), ('style_pseudo_bld.xml', pseudo_bld_xml())):
        with open(os.path.join(HERE, name), 'w') as f:
            f.write(xml)
        print('wrote', name, len(xml), 'bytes')


if __name__ == '__main__':
    main()
