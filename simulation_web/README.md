# simulation_web — web bridge, operator view, launch files

## Nodes
- `navera_web_bridge`: HTTP server on :8181 — operator view (`/operator`), mission planner
  and replay dashboard (`/`), map tiles from the MBTiles file, mission control.
- `navera_stellar_bridge`: the same for the celestial pipeline's dashboard.

Endpoints and security rules: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6. The shared
HTTP layer (token, JSON limits, tile bounds, static files) is `simulation_web/web_common.py`.

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
