import rclpy
from rclpy.node import Node
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import subprocess
import sys
import os
import base64
import tempfile
from datetime import datetime, timezone

PORT = 5002
SOLVER = os.path.join(os.path.dirname(__file__), 'drone_sky_prep.py')

class FrameHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        if self.path == '/frame':
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length))
            result = self._solve(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path in ('/api/set_mission', '/api/precollect'):
            # Accept but ignore — not needed for stellar mode
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'source': 'stellar'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/api/cache_status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'ready': True,
                'source': 'stellar',
                'cached_images': 1,
                'message': '🌟 Stellar solver ready'
            }).encode())
        elif self.path == '/api/precollect_progress':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'done': True, 'total': 1, 'progress': 100
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _solve(self, body):
        try:
            image_b64 = body.get('image_b64', '')
            tilt      = body.get('tilt', None)
            azimuth   = body.get('azimuth', None)
            utc_time  = body.get('utc_time', None)

            if not image_b64:
                return {'success': False, 'error': 'No image_b64 provided'}

            # Write image to temp file
            img_bytes = base64.b64decode(image_b64)
            with tempfile.NamedTemporaryFile(suffix='.jpeg', delete=False) as f:
                f.write(img_bytes)
                img_path = f.name

            # Build UTC time string
            if utc_time:
                dt_str   = utc_time  # expect "YYYY-MM-DD HH:MM:SS"
                date_str = dt_str.split(' ')[0]
                time_str = dt_str.split(' ')[1]
            else:
                now      = datetime.now(timezone.utc)
                date_str = now.strftime('%Y-%m-%d')
                time_str = now.strftime('%H:%M:%S')

            # Build command
            cmd = [sys.executable, SOLVER, img_path, date_str, time_str]
            if tilt is not None and azimuth is not None:
                cmd += [str(tilt), str(azimuth)]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            os.unlink(img_path)

            # Parse output
            lat, lon = None, None
            ra, dec  = None, None
            for line in result.stdout.splitlines():
                if 'Latitude' in line and '°' in line:
                    import re
                    m = re.search(r'([\d.]+)°\s*([NS])', line)
                    if m:
                        lat = float(m.group(1))
                        if m.group(2) == 'S': lat = -lat
                if 'Longitude' in line and '°' in line:
                    import re
                    m = re.search(r'([\d.]+)°\s*([EW])', line)
                    if m:
                        lon = float(m.group(1))
                        if m.group(2) == 'W': lon = -lon
                if 'RA ' in line:
                    import re
                    m = re.search(r'([\d.]+)°', line)
                    if m: ra = float(m.group(1))
                if 'Dec ' in line:
                    import re
                    m = re.search(r'([\d.]+)°', line)
                    if m: dec = float(m.group(1))

            if lat is None or lon is None:
                return {
                    'success': False,
                    'error': 'solve-field failed',
                    'stdout': result.stdout[-500:],
                    'stderr': result.stderr[-300:]
                }

            return {
                'success': True,
                'predicted_lat': lat,
                'predicted_lon': lon,
                'ra_deg': ra,
                'dec_deg': dec,
                'source': 'stellar',
                'match_score': 0.95
            }

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'solve-field timeout (120s)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class CelestialNode(Node):
    def __init__(self):
        super().__init__('celestial_node')
        self.get_logger().info(f'🌟 cn_pkg — Celestial Navigation Node starting on port {PORT}')
        server = HTTPServer(('0.0.0.0', PORT), FrameHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        self.get_logger().info(f'✅ HTTP server listening on http://0.0.0.0:{PORT}')

def main(args=None):
    rclpy.init(args=args)
    node = CelestialNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
