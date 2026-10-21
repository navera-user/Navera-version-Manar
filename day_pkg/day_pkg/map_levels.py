"""Which map zoom a frame is matched against, when the area holds several.

A prepared area (prepare_area.py, the mission bundle's day/) says its zoom in area.json ("zoom",
and "zooms" when it holds several). Low frames need a finer map: a frame 100 m above ground with
an 80 deg lens sees ~170 m, ~180 pixels of a zoom-17 map (0.92 m/px). On a real flight over a valley
(MARS-LVIG AMvalley03, 2026-10-21, 60-140 m above ground) a zoom-18 map raised the share of frames
located from 36 % to 54 %, at every height band (60-80 m 11 -> 38 %, 120-140 m 73 -> 88 %), the
frames there being 2.4-6x finer than the zoom-18 map. High frames gain nothing from a map finer
than themselves and cost 4x the tiles per search circle.

Rule (choose_zoom): the finest zoom whose ground resolution is at least min_ratio times coarser than
the frame's (min_ratio 2: what was measured), else the coarsest. An area without area.json is
zoom 17 (the layout before the zoom was recorded).
"""
import json
import math
import os
from typing import List, Optional

DEFAULT_ZOOM = 17
EQUATOR_M = 40075016.7


def map_m_per_px(lat: float, zoom: int) -> float:
    """Ground metres per pixel of a 256-px web-mercator tile at this latitude and zoom."""
    return EQUATOR_M * math.cos(math.radians(lat)) / (2 ** zoom) / 256.0


def area_zooms(images_dir: str) -> List[int]:
    """The zooms the area's tiles exist at (area.json "zooms" / "zoom", kept only when tiles of that
    zoom are in images_dir), coarsest first; [17] for an area without area.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(images_dir)), "area.json")
    try:
        with open(path) as f:
            info = json.load(f)
    except (OSError, ValueError):
        return [DEFAULT_ZOOM]
    declared = info.get("zooms") or [info.get("zoom", DEFAULT_ZOOM)]
    zooms = sorted({int(z) for z in declared})
    if len(zooms) == 1:
        return zooms
    present = set()
    try:
        with os.scandir(images_dir) as it:
            for e in it:
                for z in zooms:
                    if z not in present and e.name.startswith(f"tile_{z}_"):
                        present.add(z)
                if len(present) == len(zooms):
                    break
    except OSError:
        return zooms[:1]
    return [z for z in zooms if z in present] or zooms[:1]


def choose_zoom(zooms: List[int], frame_m_per_px: Optional[float], lat: Optional[float],
                min_ratio: float = 2.0) -> int:
    """The zoom to match a frame of this ground resolution against (see the module doc)."""
    zooms = sorted(zooms)
    if len(zooms) == 1 or frame_m_per_px is None or lat is None or not frame_m_per_px > 0:
        return zooms[0]
    fine = [z for z in zooms if map_m_per_px(lat, z) >= min_ratio * frame_m_per_px]
    return max(fine) if fine else zooms[0]
