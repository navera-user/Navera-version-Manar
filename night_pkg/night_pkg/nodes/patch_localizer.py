#!/usr/bin/env python3
"""
patch_localizer.py — Ajoute un seuil de confiance à night_localizer.py
=======================================================================

PROBLÈME :
  localize() retourne success=True même quand conf=0.00 (prédiction
  aberrante). Le receiver utilise alors une position fausse → le drone
  saute très loin.

FIX :
  • Ajoute un paramètre conf_threshold (défaut 0.30) au constructeur.
  • Dans localize(), si conf < conf_threshold → success=False.
    Le receiver fera alors du dead-reckoning au lieu d'utiliser
    la position aberrante.

Usage (Jetson) :
    cd ~/isaac_ros_common/night_pkg/night_pkg
    cp night_localizer.py night_localizer.py.backup
    python3 patch_localizer.py night_localizer.py
"""

import sys
from pathlib import Path


def patch(path: Path):
    text = path.read_text(encoding="utf-8")
    original = text
    done = []

    # ── PATCH 1 : ajouter conf_threshold au constructeur ──────────────
    old_init = """        zoom: int = 17,
        patch_size: int = 256,
        roll_avg_n: int = 5,
        device: str = None,
    ):
        self.zoom       = zoom
        self.patch_size = patch_size"""
    new_init = """        zoom: int = 17,
        patch_size: int = 256,
        roll_avg_n: int = 5,
        device: str = None,
        conf_threshold: float = 0.30,
    ):
        self.zoom           = zoom
        self.patch_size     = patch_size
        self.conf_threshold = conf_threshold"""
    if old_init in text:
        text = text.replace(old_init, new_init)
        done.append("PATCH 1: conf_threshold ajouté au constructeur")
    else:
        print("⚠ PATCH 1 non trouvé")

    # ── PATCH 2 : rejeter si conf < seuil (juste après calcul de conf) ─
    old_conf = """        rms = float(np.sqrt((pred_px ** 2).mean()))
        max_expected_px = self.patch_size * 0.3
        conf = float(np.clip(1.0 - rms / max_expected_px, 0.0, 1.0))"""
    new_conf = """        rms = float(np.sqrt((pred_px ** 2).mean()))
        max_expected_px = self.patch_size * 0.3
        conf = float(np.clip(1.0 - rms / max_expected_px, 0.0, 1.0))

        # PATCHED: reject low-confidence predictions so the receiver can
        # fall back to dead-reckoning instead of jumping to a wrong point.
        if conf < self.conf_threshold:
            logger.warning(
                f"STHN low confidence {conf:.2f} < {self.conf_threshold:.2f} "
                f"(rms={rms:.1f}px) → rejected, receiver will dead-reckon")
            return {"success": False, "lat": prior_lat, "lon": prior_lon,
                    "conf": conf, "dt_ms": (time.perf_counter()-t0)*1000.0,
                    "rms_px": rms, "raw_lat": prior_lat, "raw_lon": prior_lon}"""
    if old_conf in text:
        text = text.replace(old_conf, new_conf)
        done.append("PATCH 2: rejet si conf < seuil")
    else:
        print("⚠ PATCH 2 non trouvé")

    if text == original:
        print("\n❌ Aucun patch appliqué.")
        return False

    path.write_text(text, encoding="utf-8")
    print("\n✅ night_localizer.py patché !")
    for d in done:
        print(f"   • {d}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 patch_localizer.py <night_localizer.py>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"❌ introuvable : {p}")
        sys.exit(1)
    sys.exit(0 if patch(p) else 2)
