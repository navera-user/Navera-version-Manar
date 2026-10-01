# simulation_web — web bridge, operator view, launch files

## Nodes
- `navera_web_bridge`: HTTP server on :8181 — operator view (`/operator`), mission planner
  and replay dashboard (`/`), map tiles from the MBTiles file, mission control.
- `navera_stellar_bridge`: the same for the celestial pipeline's dashboard.

Endpoints and security rules: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6. The shared
HTTP layer (token, JSON limits, tile bounds, static files) is `simulation_web/web_common.py`.

## Mission preparation on the box (`/mission`)
The page an operator uses on the vehicle, in three steps:
1. **Vehicle** — type, maximum speed, thermal camera field of view, IMU mounting,
   declination. Saved to `/var/lib/navera/settings.env` (validated keys only, atomic
   write), which every NAVERA unit loads after `/etc/navera/navera.env`; **Apply**
   try-restarts the running NAVERA units.
2. **Route** — the autopilot's mission file (Mission Planner `.waypoints`, QGroundControl
   `.plan`) or two clicks on the map; split into ≤ 10 km legs so the map follows the
   flown path.
3. **Satellite map** — generated with `prepare_area.py` into `$NAVERA_AREAS_DIR` (onboard
   MBTiles, plus downloads when `NAVERA_TILE_URL` is set), then **Activate** points
   `DAY_DATASET_DIR` at it and restarts the day pipeline.

Every change needs the control code (`NAVERA_WEB_TOKEN`); without it the page is read-only.
The only root action the web service may take is restarting NAVERA's units, through
`deploy/sudoers/navera-web` (exact commands). Logic and tests: `mission_prep.py`,
`test/test_mission_prep.py`.

## Launch files
| File | Starts |
|---|---|
| `day_pipeline.launch.py` / `night_pipeline.launch.py` / `cn_pipeline.launch.py` | camera + localizer (no bridge) |
| `bridge.launch.py` | one web bridge (topics as arguments) |
| `day_sim.launch.py` / `night_sim.launch.py` / `cn_sim.launch.py` | pipeline + bridge, single command |

Every node in these launch files ends its launch if it exits (`on_exit=Shutdown`) so the
systemd service restarts the whole pipeline.

## Key parameters (bridge)
`mbtiles_path` (default `NAVERA_MBTILES`), `web_host`, `web_port`, `control_token`
(default `NAVERA_WEB_TOKEN`; empty = read-only), `status_stale_s`, `ready_topic`.
