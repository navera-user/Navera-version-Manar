#!/usr/bin/env python3
"""
patch_receiver.py — Dead-reckoning quand STHN échoue dans night_receiver.py
============================================================================

PROBLÈME :
  Quand STHN renvoie success=False (échec ou confiance trop basse),
  le receiver laisse le drone FIGÉ sur la dernière ancre. Sur une série
  de frames NO-GPS, le drone ne bouge pas du tout.

FIX :
  Ajoute une fonction de dead-reckoning (avance depuis la dernière
  position selon heading_deg + speed_mps × delta_t) et l'utilise dans
  la branche d'échec STHN. Le drone continue ainsi sa trajectoire
  proprement au lieu de rester bloqué ou de sauter.

Usage (Jetson) :
    cd ~/isaac_ros_common/night_pkg/night_pkg
    cp night_receiver.py night_receiver.py.backup
    python3 patch_receiver.py night_receiver.py
"""

import sys
from pathlib import Path


DR_HELPER = '''
# ─── Dead-reckoning helper (PATCHED) ──────────────────────────────────────────
def _dead_reckon(lat, lon, heading_deg, speed_mps, dt_s=10.0):
    """Advance (lat,lon) by speed*dt along heading. Returns (lat,lon)."""
    import math as _m
    if lat is None or lon is None:
        return lat, lon
    dist = float(speed_mps or 5.0) * float(dt_s or 10.0)   # metres
    hdg  = _m.radians(float(heading_deg or 0.0))
    R    = 6371000.0
    dlat = (dist * _m.cos(hdg)) / R * (180.0 / _m.pi)
    dlon = (dist * _m.sin(hdg)) / (R * _m.cos(_m.radians(lat))) * (180.0 / _m.pi)
    return lat + dlat, lon + dlon

'''


def patch(path: Path):
    text = path.read_text(encoding="utf-8")
    original = text
    done = []

    # ── PATCH 1 : insérer le helper dead-reckoning avant les Routes ───
    anchor = "# ═════════════════════════════════════════════════════════════════════════════\n#  Routes"
    if anchor in text and "_dead_reckon" not in text:
        text = text.replace(anchor, DR_HELPER + "\n" + anchor)
        done.append("PATCH 1: helper _dead_reckon inséré")
    else:
        print("⚠ PATCH 1 non trouvé (ou déjà appliqué)")

    # ── PATCH 2 : remplacer le fallback figé par du dead-reckoning ────
    old_fail = """        else:
            logger.warning(
                f"STHN failed on frame {frame_id} — falling back to anchor")
            with _gps_status_lock:
                _gps_status.update({
                    "status": "error",
                    "error":  "STHN inference failed",
                    "lat":    anchor_lat,
                    "lon":    anchor_lon,
                })
            _append_flight_row(
                frame_id, ts, img_name,
                lat=None, lon=None,
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=False,
                pred_lat=anchor_lat, pred_lon=anchor_lon,
                score=0.0,
            )"""

    new_fail = """        else:
            # PATCHED: STHN rejected/failed → dead-reckon from last position
            # (advance along heading+speed) instead of freezing on the anchor.
            dr_lat, dr_lon = _dead_reckon(anchor_lat, anchor_lon, hdg, spd, dt_s=10.0)
            # the dead-reckoned point becomes the new anchor for chaining
            _last_valid_lat = dr_lat
            _last_valid_lon = dr_lon
            logger.warning(
                f"STHN rejected on frame {frame_id} → dead-reckon "
                f"({dr_lat:.6f}, {dr_lon:.6f})")
            with _fix_lock:
                latest_fix.update({
                    "lat": dr_lat, "lon": dr_lon, "conf": 0.0,
                    "source": "dead_reckoning", "ts": time.time(),
                    "dt_ms": 0.0, "rms_px": 0.0,
                })
            with _gps_status_lock:
                _gps_status.update({
                    "status":          "predicted",
                    "lat":             dr_lat,
                    "lon":             dr_lon,
                    "last_valid_lat":  anchor_lat,
                    "last_valid_lon":  anchor_lon,
                    "score":           0.0,
                    "total_ms":        0,
                    "dataset_ms":      0,
                    "dataset_images":  1,
                    "match":           f"dead_reckoning_frame_{frame_id}",
                    "search_radius_m": 300,
                    "error":           "",
                })
            _append_flight_row(
                frame_id, ts, img_name,
                lat=None, lon=None,
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=False,
                pred_lat=dr_lat, pred_lon=dr_lon,
                score=0.0,
            )"""

    if old_fail in text:
        text = text.replace(old_fail, new_fail)
        done.append("PATCH 2: fallback → dead-reckoning")
    else:
        print("⚠ PATCH 2 non trouvé (vérifier la branche else de STHN)")

    if text == original:
        print("\n❌ Aucun patch appliqué.")
        return False

    path.write_text(text, encoding="utf-8")
    print("\n✅ night_receiver.py patché !")
    for d in done:
        print(f"   • {d}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 patch_receiver.py <night_receiver.py>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"❌ introuvable : {p}")
        sys.exit(1)
    sys.exit(0 if patch(p) else 2)
