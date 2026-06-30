# Vision Package — Satellite Map Server

## 📦 Project Structure

```
vision_pkg/vision_pkg/
├── server.py              ← Flask REST API server
├── navera.html            ← Web UI (Leaflet map)
├── dataset/
│   ├── sousse_satellite.mbtiles   (10GB satellite map)
│   ├── flight_log.csv             (flight data)
│   ├── gps_status.json            (current GPS + waypoints)
│   └── precollected/              (reference images for localization)
├── gps_localizer.py       ← Visual localization engine
├── vision_node.py         ← ROS 2 node
├── Dockerfile             ← Container image
└── requirements-server.txt ← Python dependencies
```

## 🚀 Running the Server

### Local Development

```bash
cd vision_pkg/vision_pkg
python3 server.py
# Server runs on http://localhost:8080
```

### Docker

```bash
cd vision_pkg
docker build -t vision-pkg -f vision_pkg/Dockerfile .
docker run -p 8080:8080 -v $(pwd)/vision_pkg/dataset:/app/dataset vision-pkg
```

### Docker Compose

```bash
cd vision_pkg
docker-compose up
# Access at http://localhost:8080
```

## 🗺️ API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI (Leaflet map) |
| `/health` | GET | Health check |
| `/tiles/{z}/{x}/{y}.png` | GET | Satellite tile (XYZ format, TMS→XYZ conversion applied) |
| `/api/gps-status` | GET | Current position, predicted position, waypoints |
| `/api/flight-log` | GET | Flight log CSV as JSON |

## 📊 Data Files

### `gps_status.json`
Current GPS status and waypoints:
```json
{
  "current_position": {lat, lon, alt_m, heading_deg, speed_mps},
  "predicted_position": {lat, lon, confidence},
  "waypoints": [{id, lat, lon, alt_m}, ...],
  "satellites": 12,
  "hdop": 1.2
}
```

### `flight_log.csv`
Flight data with columns:
- `frame_id`, `timestamp`, `image_file`
- `lat`, `lon`, `alt_m`
- `heading_deg`, `speed_mps`
- `gps_valid`, `predicted_lat`, `predicted_lon`, `match_score`

## 🗂️ Dataset Details

- **MBTiles**: Sousse, Tunisia satellite map (13-19 zoom, 1.15M tiles)
- **Precollected**: Reference images for visual localization with GPS coordinates
- **Flight Log**: Sparse (header only), can be populated at runtime

## 🔧 Configuration

All paths are relative to `vision_pkg/vision_pkg/`:
- Dataset: `./dataset/`
- MBTiles: `./dataset/sousse_satellite.mbtiles`
- GPS Status: `./dataset/gps_status.json`
- Flight Log: `./dataset/flight_log.csv`

## 🧪 Testing Endpoints

```bash
# Health check
curl http://localhost:8080/health

# GPS status
curl http://localhost:8080/api/gps-status | jq

# Flight log
curl http://localhost:8080/api/flight-log | jq

# Satellite tile (XYZ coordinates)
curl -o tile.png http://localhost:8080/tiles/13/4330/3229.png
```

## 🌐 Web UI Features

- **Real-time GPS Display**: Shows current position, altitude, heading, speed
- **Satellite Map**: Leaflet-based interactive map centered on Sousse, Tunisia
- **Markers**:
  - 🔵 Current GPS position
  - 🟣 Predicted position
  - 🔴 Point A
  - 🔵 Point B
  - 🟢 Waypoints
- **Auto-Refresh**: Updates every 5 seconds
- **Popup Details**: Click markers for detailed information

## 🚢 Production Deployment

The `docker-compose.yml` includes optional Nginx reverse proxy for production. Uncomment to enable.

## 📝 Notes

- MBTiles uses TMS coordinate system (Y-axis inverted) — server automatically converts to XYZ for Leaflet
- All endpoints support CORS
- Server runs in production mode (debug=False) by default
- Tile caching is optimized (5000 pragma cache)
