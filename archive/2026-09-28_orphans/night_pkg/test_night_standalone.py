#!/usr/bin/env python3
"""
test_night_standalone.py  —  Test night_pkg WITHOUT ROS2
Tests the STHN inference pipeline directly with a synthetic query image.

Usage:
    cd ~/isaac_ros_common/night_pkg
    python3 test_night_standalone.py \
        --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
        --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
        --mbtiles  ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles \
        --lat 35.8288 --lon 10.6360

    # Or with a real image:
    python3 test_night_standalone.py ... --image /path/to/frame.jpg
"""

import argparse
import sys
import time
import logging
from pathlib import Path

import numpy as np
import cv2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_night")


def make_synthetic_query(size=512):
    """Generate a fake night drone image (random bright dots on dark background)."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for _ in range(80):
        cx = np.random.randint(20, size - 20)
        cy = np.random.randint(20, size - 20)
        r  = np.random.randint(2, 10)
        brightness = np.random.randint(120, 255)
        cv2.circle(img, (cx, cy), r, (brightness, brightness, brightness), -1)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sthn-dir",  required=True,
                        help="Path to cloned arplaboratory/STHN repo")
    parser.add_argument("--weights",   required=True,
                        help="Path to model_best.pth checkpoint")
    # FIXED: correct default mbtiles path on navera-desktop
    parser.add_argument("--mbtiles",
                        default=str(Path.home() /
                            "isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles"),
                        help="Path to sousse_satellite.mbtiles")
    parser.add_argument("--lat",  type=float, default=35.8288,
                        help="Prior latitude  (Sousse default)")
    parser.add_argument("--lon",  type=float, default=10.6360,
                        help="Prior longitude (Sousse default)")
    parser.add_argument("--zoom", type=int,   default=17)
    parser.add_argument("--image", default=None,
                        help="Path to real query image (omit for synthetic)")
    parser.add_argument("--n",    type=int,   default=3,
                        help="Number of inference iterations")
    args = parser.parse_args()

    # Validate all paths
    for p, name in [
        (args.sthn_dir, "--sthn-dir"),
        (args.weights,  "--weights"),
        (args.mbtiles,  "--mbtiles"),
    ]:
        if not Path(p).exists():
            logger.error(f"Not found: {name} = {p}")
            sys.exit(1)

    # Load NightLocalizer
    sys.path.insert(0, str(Path(__file__).parent / "night_pkg"))
    sys.path.insert(0, str(Path(__file__).parent))
    from night_localizer import NightLocalizer

    logger.info("Loading NightLocalizer…")
    loc = NightLocalizer(
        sthn_dir=args.sthn_dir,
        weights=args.weights,
        mbtiles=args.mbtiles,
        zoom=args.zoom,
    )
    logger.info("✓ Model loaded")

    # Load or generate query image
    if args.image:
        query = cv2.imread(args.image)
        if query is None:
            logger.error(f"Cannot read image: {args.image}")
            sys.exit(1)
        logger.info(f"Query image: {args.image}  shape={query.shape}")
    else:
        query = make_synthetic_query()
        logger.info("Using synthetic night image (random bright dots)")

    # Run inference N times
    print(f"\n{'='*60}")
    print(f" STHN Night Localization Test")
    print(f" Prior: ({args.lat:.6f}, {args.lon:.6f})  zoom={args.zoom}")
    print(f"{'='*60}")

    for i in range(args.n):
        result = loc.localize(query, args.lat, args.lon)
        status = "✓" if result["success"] else "✗"
        if result["success"]:
            dlat = (result["lat"] - args.lat) * 111320
            dlon = (result["lon"] - args.lon) * 111320 * 0.82   # cos(35°)
            dist = (dlat**2 + dlon**2) ** 0.5
            print(
                f"  [{i+1}] {status}  fix=({result['lat']:.6f}, {result['lon']:.6f})  "
                f"Δ={dist:.1f}m  conf={result['conf']:.2f}  "
                f"rms={result['rms_px']:.1f}px  dt={result['dt_ms']:.0f}ms"
            )
        else:
            print(f"  [{i+1}] {status}  FAILED — check STHN path and weights")

    print(f"{'='*60}\n")
    logger.info("Test complete.")


if __name__ == "__main__":
    main()
