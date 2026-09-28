#!/usr/bin/env python3
"""
NAVERA - sensor_sim : simulateur de capteurs (banc de test, AUCUN materiel requis).

Publie des donnees capteurs simulees sur les topics reels afin de verifier la
chaine complete : estimator -> /navera/position -> bridge web -> /operator,
sans GPS, IMU ni RTC branches.

HONNETETE (regle du projet) : tout ce que publie ce noeud est etiquete
producer="sensor_sim" et details_json contient {"simulated": true}.
  --mode measured  (defaut) : simule un vrai GPS -> l'arbitre doit produire un FIX.
  --mode replayed            : l'arbitre doit REFUSER la position (demo du contrat).
Ceci est un banc de test, jamais un mode de vol.

Usage (sur le Jetson, environnement ROS source) :
  cd ~/isaac_ros_common
  source /opt/ros/humble/setup.bash && source install/setup.bash
  NAVERA_ALLOW_SIM=1 python3 navera_tools/sensor_sim.py [--mode measured|replayed]

Arret : Ctrl-C, ou kill <PID> (le PID est affiche au demarrage).
"""
import argparse
import json
import math
import os
import sys
import time

# This tool publishes FAKE sensor data on the real topics. Refuse to run unless
# explicitly allowed, so it can never feed a live box by accident.
if os.environ.get("NAVERA_ALLOW_SIM") != "1":
    sys.exit("refusing to run: this publishes simulated sensor data on the real "
             "NAVERA topics. Set NAVERA_ALLOW_SIM=1 on a test machine to allow it.")

import rclpy  # noqa: E402
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Imu, NavSatFix, NavSatStatus, TimeReference
from geometry_msgs.msg import TwistStamped
from navera_msgs.msg import PositionEstimate

# ---- parametres du circuit simule (Sousse, au-dessus de la zone des tuiles) ----
LAT0, LON0 = 35.8288, 10.6360   # centre du cercle
RADIUS_M = 800.0                # rayon (m)
SPEED_MPS = 30.0                # vitesse sol (m/s)
SIGMA_M = 1.5                   # ecart-type GPS simule (m)
ALT_M = 400.0                   # altitude (m)
M_PER_DEG_LAT = 111320.0


class SensorSim(Node):
    def __init__(self, mode: str):
        super().__init__("sensor_sim")
        self.sim_mode = (PositionEstimate.MODE_REPLAYED if mode == "replayed"
                         else PositionEstimate.MODE_MEASURED)
        self.pub_est = self.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.pub_fix = self.create_publisher(NavSatFix, "/navera/sensors/gps_fix", 10)
        self.pub_vel = self.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)
        self.pub_rtc = self.create_publisher(TimeReference, "/navera/sensors/rtc_time", 10)
        self.pub_rtcs = self.create_publisher(String, "/navera/sensors/rtc_status", 10)
        self.t0 = time.monotonic()
        self.create_timer(0.20, self.tick_gps)   # 5 Hz
        self.create_timer(0.05, self.tick_imu)   # 20 Hz
        self.create_timer(1.00, self.tick_rtc)   # 1 Hz
        label = ("REPLAYED (l'arbitre doit REFUSER)"
                 if self.sim_mode == PositionEstimate.MODE_REPLAYED
                 else "MEASURED (banc de test -> FIX attendu)")
        self.get_logger().info(
            f"SIMULATION capteurs demarree [PID {os.getpid()}] mode={label} "
            f"cercle r={RADIUS_M:.0f} m @ {SPEED_MPS:.0f} m/s autour de {LAT0:.4f},{LON0:.4f}")

    # ---- etat du vehicule : cercle parcouru a vitesse constante ----
    def state(self):
        t = time.monotonic() - self.t0
        omega = SPEED_MPS / RADIUS_M          # rad/s
        th = omega * t
        east = RADIUS_M * math.cos(th)
        north = RADIUS_M * math.sin(th)
        lat = LAT0 + north / M_PER_DEG_LAT
        lon = LON0 + east / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))
        v_east = -SPEED_MPS * math.sin(th)
        v_north = SPEED_MPS * math.cos(th)
        yaw = math.atan2(v_north, v_east)     # ENU, 0 = est, CCW
        return lat, lon, v_east, v_north, yaw, omega, th

    def _stamp(self):
        return self.get_clock().now().to_msg()

    def tick_gps(self):
        lat, lon, v_e, v_n, _, _, _ = self.state()
        now = self._stamp()
        cov = [SIGMA_M**2, 0.0, 0.0, 0.0, SIGMA_M**2, 0.0, 0.0, 0.0, (2*SIGMA_M)**2]

        est = PositionEstimate()
        est.header.stamp = now
        est.header.frame_id = "gps_link"
        est.latitude, est.longitude, est.altitude = lat, lon, ALT_M
        est.position_covariance = cov
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
        est.source = PositionEstimate.SOURCE_GPS
        est.mode = self.sim_mode
        est.valid = True
        est.confidence = 0.95
        est.reason = "" if self.sim_mode == PositionEstimate.MODE_MEASURED else "simulated replay"
        est.sensor_stamp = now
        est.producer = "sensor_sim"
        est.model_id = "sim-v1"
        est.frame_index = -1
        est.details_json = json.dumps({"simulated": True, "num_sats": 12, "hdop": 0.7})
        self.pub_est.publish(est)

        fix = NavSatFix()
        fix.header.stamp = now
        fix.header.frame_id = "gps_link"
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = NavSatStatus.SERVICE_GPS
        fix.latitude, fix.longitude, fix.altitude = lat, lon, ALT_M
        fix.position_covariance = cov
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self.pub_fix.publish(fix)

        vel = TwistStamped()
        vel.header.stamp = now
        vel.header.frame_id = "gps_link"
        vel.twist.linear.x = v_e
        vel.twist.linear.y = v_n
        self.pub_vel.publish(vel)

    def tick_imu(self):
        _, _, _, _, yaw, omega, th = self.state()
        imu = Imu()
        imu.header.stamp = self._stamp()
        imu.header.frame_id = "imu_link"
        imu.orientation.z = math.sin(yaw / 2.0)
        imu.orientation.w = math.cos(yaw / 2.0)
        imu.angular_velocity.z = omega
        # acceleration centripete (vers le centre) + gravite sur z
        a_c = SPEED_MPS * omega
        imu.linear_acceleration.x = -a_c * math.cos(th)
        imu.linear_acceleration.y = -a_c * math.sin(th)
        imu.linear_acceleration.z = 9.81
        imu.orientation_covariance = [0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.01]
        imu.angular_velocity_covariance = [1e-3, 0.0, 0.0, 0.0, 1e-3, 0.0, 0.0, 0.0, 1e-3]
        imu.linear_acceleration_covariance = [1e-2, 0.0, 0.0, 0.0, 1e-2, 0.0, 0.0, 0.0, 1e-2]
        self.pub_imu.publish(imu)

    def tick_rtc(self):
        now = self._stamp()
        tr = TimeReference()
        tr.header.stamp = now
        tr.header.frame_id = "rtc_link"
        tr.time_ref = now
        tr.source = "sensor_sim"
        self.pub_rtc.publish(tr)
        st = String()
        st.data = json.dumps({"valid": True, "simulated": True, "source": "sensor_sim"})
        self.pub_rtcs.publish(st)


def main():
    ap = argparse.ArgumentParser(description="NAVERA sensor simulator (test bench)")
    ap.add_argument("--mode", choices=["measured", "replayed"], default="measured")
    args = ap.parse_args()
    rclpy.init()
    node = SensorSim(args.mode)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info("sensor_sim: arret propre")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
