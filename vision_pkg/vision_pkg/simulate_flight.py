#!/usr/bin/env python3
"""
simulate_flight.py
Rejoue le CSV de vol ligne par ligne sur ROS2
— publie chaque frame sur /drone/gps et /drone/altitude
— quand NaN détecté → le gps_trigger_node se déclenche automatiquement

USAGE:
    python3 simulate_flight.py
    ou
    python3 simulate_flight.py --csv /chemin/vers/ton/fichier.csv --delay 1.7
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Float32

import csv
import math
import time
import argparse
from io import StringIO

# ── Données CSV intégrées (ton vol) ──────────────────────────────────────────
FLIGHT_CSV = """frame,lat,lon,alt_m,heading_deg,timestamp
1,35.825400,10.636000,600,296,2026-03-02T12:19:35.951Z
2,35.826503,10.633243,545,296,2026-03-02T12:19:37.674Z
3,35.827691,10.631454,500,52,2026-03-02T12:19:39.393Z
4,35.829280,10.633811,492,42,2026-03-02T12:19:41.150Z
5,35.831212,10.635281,454,337,2026-03-02T12:19:42.872Z
6,35.833502,10.634063,479,337,2026-03-02T12:19:44.605Z
7,35.835667,10.632666,502,302,2026-03-02T12:19:46.340Z
8,35.836977,10.630047,521,302,2026-03-02T12:19:48.087Z
9,35.838285,10.627429,540,302,2026-03-02T12:19:49.812Z
10,35.839692,10.624893,564,308,2026-03-02T12:19:51.537Z
11,35.841215,10.622456,594,308,2026-03-02T12:19:53.271Z
12,35.842738,10.620020,625,308,2026-03-02T12:19:55.008Z
13,35.844224,10.617552,653,302,2026-03-02T12:19:56.754Z
14,35.845533,10.614934,669,302,2026-03-02T12:19:58.475Z
15,35.846842,10.612315,686,302,2026-03-02T12:20:00.212Z
16,35.848225,10.609775,703,321,2026-03-02T12:20:01.936Z
17,35.850163,10.607837,727,321,2026-03-02T12:20:03.672Z
18,35.851876,10.606041,750,165,2026-03-02T12:20:05.423Z
19,NaN,NaN,744,165,2026-03-02T12:20:07.158Z
20,NaN,NaN,737,165,2026-03-02T12:20:08.887Z
21,NaN,NaN,731,165,2026-03-02T12:20:10.601Z
22,NaN,NaN,725,165,2026-03-02T12:20:12.342Z
23,NaN,NaN,719,165,2026-03-02T12:20:14.086Z
24,NaN,NaN,713,165,2026-03-02T12:20:15.799Z
25,NaN,NaN,706,165,2026-03-02T12:20:17.536Z
26,NaN,NaN,700,165,2026-03-02T12:20:19.270Z
27,NaN,NaN,694,165,2026-03-02T12:20:21.009Z
28,NaN,NaN,688,165,2026-03-02T12:20:22.755Z
29,NaN,NaN,682,165,2026-03-02T12:20:24.477Z
30,NaN,NaN,676,165,2026-03-02T12:20:26.204Z
31,NaN,NaN,669,165,2026-03-02T12:20:27.940Z
32,NaN,NaN,663,165,2026-03-02T12:20:29.685Z
33,NaN,NaN,657,165,2026-03-02T12:20:31.403Z
34,NaN,NaN,651,165,2026-03-02T12:20:33.148Z
"""


class FlightSimulator(Node):
    def __init__(self, csv_data: str, delay: float = 1.7):
        super().__init__('flight_simulator')

        self.delay = delay  # secondes entre chaque frame

        # Publishers
        self.gps_pub = self.create_publisher(NavSatFix, '/drone/gps', 10)
        self.alt_pub = self.create_publisher(Float32,   '/drone/altitude', 10)

        # Parse CSV
        self.frames = self._parse_csv(csv_data)

        self.get_logger().info(f'✈️  Flight Simulator prêt — {len(self.frames)} frames')
        self.get_logger().info(f'   Délai entre frames : {self.delay}s')
        self.get_logger().info(f'   Topic GPS     : /drone/gps')
        self.get_logger().info(f'   Topic Altitude: /drone/altitude')
        self.get_logger().info('─' * 50)

        # Lance la simulation après 1 seconde
        self.timer = self.create_timer(1.0, self._start_simulation)
        self._started = False

    def _parse_csv(self, data: str) -> list:
        frames = []
        reader = csv.DictReader(StringIO(data))
        for row in reader:
            frames.append({
                'frame'  : int(row['frame']),
                'lat'    : row['lat'].strip(),
                'lon'    : row['lon'].strip(),
                'alt_m'  : float(row['alt_m']),
                'heading': float(row['heading_deg']),
                'ts'     : row['timestamp'].strip()
            })
        return frames

    def _start_simulation(self):
        if self._started:
            return
        self._started = True
        self.timer.cancel()

        for frame in self.frames:
            if not rclpy.ok():
                break

            frame_id = frame['frame']
            lat_str  = frame['lat']
            lon_str  = frame['lon']
            alt      = frame['alt_m']
            ts       = frame['ts']

            is_nan = (lat_str.lower() == 'nan' or lon_str.lower() == 'nan')

            # ── Publie l'altitude (toujours valide) ──────────────────────────
            alt_msg      = Float32()
            alt_msg.data = alt
            self.alt_pub.publish(alt_msg)

            # ── Publie le GPS ─────────────────────────────────────────────────
            gps_msg = NavSatFix()
            gps_msg.header.stamp    = self.get_clock().now().to_msg()
            gps_msg.header.frame_id = 'simulator'

            if not is_nan:
                # ✅ GPS valide
                gps_msg.status.status  = NavSatStatus.STATUS_FIX
                gps_msg.status.service = NavSatStatus.SERVICE_GPS
                gps_msg.latitude       = float(lat_str)
                gps_msg.longitude      = float(lon_str)
                gps_msg.altitude       = alt

                self.get_logger().info(
                    f'  Frame {frame_id:>2} | ✅ GPS  '
                    f'lat={float(lat_str):.6f}  lon={float(lon_str):.6f}  '
                    f'alt={alt:.0f}m  [{ts}]'
                )
            else:
                # ❌ GPS perdu — on envoie STATUS_NO_FIX
                gps_msg.status.status  = NavSatStatus.STATUS_NO_FIX
                gps_msg.status.service = NavSatStatus.SERVICE_GPS
                gps_msg.latitude       = 0.0
                gps_msg.longitude      = 0.0
                gps_msg.altitude       = alt

                self.get_logger().warn(
                    f'  Frame {frame_id:>2} | ❌ NaN  '
                    f'alt={alt:.0f}m  [{ts}]'
                )

            self.gps_pub.publish(gps_msg)

            # Délai entre frames
            time.sleep(self.delay)

        self.get_logger().info('─' * 50)
        self.get_logger().info('✅ Simulation terminée — toutes les frames publiées')


def main():
    parser = argparse.ArgumentParser(description='Simulateur de vol drone')
    parser.add_argument('--csv',   type=str,   default=None,
                        help='Chemin vers un fichier CSV (défaut: données intégrées)')
    parser.add_argument('--delay', type=float, default=1.7,
                        help='Délai entre frames en secondes (défaut: 1.7)')
    args = parser.parse_args()

    # Charge le CSV
    if args.csv:
        with open(args.csv, 'r') as f:
            csv_data = f.read()
        print(f'📂 CSV chargé : {args.csv}')
    else:
        csv_data = FLIGHT_CSV
        print('📂 CSV intégré utilisé')

    rclpy.init()
    node = FlightSimulator(csv_data=csv_data, delay=args.delay)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
