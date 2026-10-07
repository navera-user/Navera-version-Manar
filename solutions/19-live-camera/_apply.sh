#!/bin/bash
# teacher test: produce every out/ file and results.json the lab asks for (as a student would)
set -e
python3 capture.py 40
python3 gst_timing.py
python3 gst_timing.py --work-ms 50
python3 analyse.py
python3 compare_with_navera.py
bash live_demo.sh
# put this sandbox's own GStreamer numbers into the teacher report
python3 - <<'PY'
import json
r = json.load(open("results.json"))
s = open("report.md").read()
s = s.replace("{GST_FPS}", f"{r['gstreamer_w0']['fps']:.2f}").replace("{GST50_FPS}", f"{r['gstreamer_w50']['fps']:.1f}")
s = s.replace("{GST50_LOST}", str(r["gstreamer_w50"]["lost_vs_nominal"]))
open("report.md", "w").write(s)
PY
