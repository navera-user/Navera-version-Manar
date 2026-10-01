# Third-party notices — NAVERA

NAVERA is proprietary software of IRIS Systems (see `LICENSE`). A NAVERA unit
also contains the third-party components below, each under its own licence.
Their licences apply to those components only, and nothing in the IRIS Systems
licence restricts the rights they grant. A copy of this file must accompany
every unit (user manual and the unit itself).

## Components shipped on the unit

| Component | Use in NAVERA | Licence | Copyright |
|---|---|---|---|
| STHN (ARPL) — code and one_stage weights | Night localisation | MIT | © 2024 ARPL |
| DINOv2 (Meta) — model weights and code via torch.hub | Day localisation | Apache-2.0 | © Meta Platforms, Inc. |
| PyTorch 2.8 (Jetson build) | Model inference | BSD-3-Clause | © Meta Platforms and PyTorch contributors |
| torchvision | Image models | BSD-3-Clause | © Soumith Chintala and contributors |
| kornia | Geometric image ops (STHN) | Apache-2.0 | © Kornia contributors |
| OpenCV | Image processing, camera capture | Apache-2.0 | © OpenCV team |
| NumPy, SciPy | Numerics | BSD-3-Clause | © NumPy / SciPy developers |
| Pillow | Image I/O | HPND (MIT-CMU) | © Jeffrey A. Clark and contributors |
| astropy | Celestial time and frames | BSD-3-Clause | © Astropy Developers |
| astrometry.net (`solve-field`) and its star index files | Celestial plate-solving (units with the celestial option) | BSD-3-Clause; some parts GPL — confirm for the installed build. Index files derive from the Tycho-2 / 2MASS catalogues | © Dustin Lang, David W. Hogg et al. |
| pygeomag (World Magnetic Model 2025, NOAA/NCEI coefficients) | IMU: magnetic → true heading | MIT (model coefficients: US public domain) | © 2023 Justin Myers |
| pymavlink | MAVLink vehicle output | **LGPL-3.0** | © ArduPilot / MAVLink developers |
| Leaflet | Dashboard map | BSD-2-Clause | © Vladimir Agafonkin, CloudMade |
| ROS 2 Humble (rclpy, rosbag2, message packages) | Middleware | Apache-2.0 (some parts BSD-3-Clause) | © Open Robotics and contributors |
| Ubuntu 22.04 / NVIDIA JetPack 6 (L4T) | Operating system | GPL-2.0 (Linux kernel), LGPL, other open-source licences; NVIDIA software under the NVIDIA Jetson Software License | © Canonical, NVIDIA and contributors |

### Obligations to meet before shipping units

- **Notices.** Ship this file and the full licence texts (MIT, Apache-2.0, BSD,
  LGPL-3.0, GPL-2.0) with every unit.
- **pymavlink (LGPL-3.0).** Installed unmodified as a separate Python package;
  the purchaser's right to replace it with another version must not be blocked.
  Provide its source (or a written offer) on request.
- **Linux kernel and other GPL/LGPL OS components.** Shipping a unit distributes
  them: include a written offer, valid for 3 years, to supply the corresponding
  source code (NVIDIA publishes the L4T sources).
- **NVIDIA Jetson Software License.** Permits redistribution of JetPack only on
  Jetson hardware — which a NAVERA unit is.
- **Satellite imagery — ESRI World Imagery.** The map database on the unit is built
  from ESRI World Imagery. ESRI's terms generally do **not** allow storing imagery
  offline and redistributing it commercially without an ESRI licence. **A licence
  (or another imagery provider licensed for offline commercial use) is required
  before units ship with a map.** This is the single biggest licensing risk.

## Development-only components (not installed on the unit)

`isaac_*` directories, `Dockerfile.navera`, `docker/` and `scripts/` come from
NVIDIA Isaac ROS (NVIDIA Isaac ROS Software License —
`LICENSES/NVIDIA-Isaac-ROS-Software-License.txt` — or Apache-2.0 as stated in
each package). They are not built (COLCON_IGNORE) and not deployed.

*This list is a technical inventory, not legal advice. Have it reviewed by
counsel before commercial shipment.*
