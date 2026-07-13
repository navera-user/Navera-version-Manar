#!/usr/bin/env python3
"""
imu_node.py — NAVERA IMU sensor driver.

Reads three I2C sensors on the same bus and publishes:
    /navera/sensors/imu             sensor_msgs/Imu          (MPU6050: accel + gyro)
    /navera/sensors/mag             sensor_msgs/MagneticField (QMC5883L: 3-axis mag)
    /navera/sensors/altitude_baro   std_msgs/Float64          (BMP180: barometric altitude)

Parameters:
    i2c_bus       (default 7)     — I2C bus number (Jetson Orin Nano = 7, others may differ)
    publish_rate  (default 10.0)  — Hz
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Float64
import smbus2
import time
import math

# ── MPU6050 registers ──────────────────────────────────────
MPU_ADDR   = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT = 0x3B
GYRO_XOUT  = 0x43
TEMP_OUT   = 0x41

# ── BMP180 registers ───────────────────────────────────────
BMP_ADDR   = 0x77
BMP_CTRL   = 0xF4
BMP_DATA   = 0xF6
BMP_CALIB  = 0xAA

# ── QMC5883L registers ─────────────────────────────────────
QMC_ADDR   = 0x0D
QMC_DATA   = 0x00
QMC_CTRL1  = 0x09
QMC_SET    = 0x0B


class IMUNode(Node):
    def __init__(self):
        super().__init__('imu_node')
        self.declare_parameter('i2c_bus', 7)
        self.declare_parameter('publish_rate', 10.0)

        bus_num = self.get_parameter('i2c_bus').value
        rate    = self.get_parameter('publish_rate').value

        self.bus = smbus2.SMBus(bus_num)
        self.get_logger().info(f'IMU node started on I2C bus {bus_num}')

        self.pub_imu  = self.create_publisher(Imu,           '/navera/sensors/imu',           10)
        self.pub_mag  = self.create_publisher(MagneticField, '/navera/sensors/mag',           10)
        self.pub_alt  = self.create_publisher(Float64,       '/navera/sensors/altitude_baro', 10)

        self._init_mpu6050()
        self._init_bmp180()
        self._init_qmc5883l()

        self.timer = self.create_timer(1.0 / rate, self.publish_all)
        self.get_logger().info('All sensors initialized')

    # ── MPU6050 ──────────────────────────────────────────────
    def _init_mpu6050(self):
        self.bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0x00)
        self.bus.write_byte_data(MPU_ADDR, 0x37, 0x02)  # enable I2C bypass for QMC5883L
        time.sleep(0.1)

    def _read_mpu6050(self):
        raw = self.bus.read_i2c_block_data(MPU_ADDR, ACCEL_XOUT, 14)
        def s16(h, l): v = (h << 8) | l; return v - 65536 if v > 32767 else v
        ax = s16(raw[0],  raw[1])  / 16384.0 * 9.81
        ay = s16(raw[2],  raw[3])  / 16384.0 * 9.81
        az = s16(raw[4],  raw[5])  / 16384.0 * 9.81
        temp = (s16(raw[6], raw[7]) / 340.0) + 36.53
        gx = s16(raw[8],  raw[9])  / 131.0 * math.pi / 180
        gy = s16(raw[10], raw[11]) / 131.0 * math.pi / 180
        gz = s16(raw[12], raw[13]) / 131.0 * math.pi / 180
        return ax, ay, az, gx, gy, gz, temp

    # ── BMP180 ───────────────────────────────────────────────
    def _init_bmp180(self):
        cal = self.bus.read_i2c_block_data(BMP_ADDR, BMP_CALIB, 22)
        def s16b(i): v = (cal[i] << 8) | cal[i+1]; return v - 65536 if v > 32767 else v
        def u16b(i): return (cal[i] << 8) | cal[i+1]
        self.bmp_cal = {
            'AC1': s16b(0),  'AC2': s16b(2),  'AC3': s16b(4),
            'AC4': u16b(6),  'AC5': u16b(8),  'AC6': u16b(10),
            'B1':  s16b(12), 'B2':  s16b(14), 'MB':  s16b(16),
            'MC':  s16b(18), 'MD':  s16b(20)
        }

    def _read_bmp180(self):
        try:
            c = self.bmp_cal
            self.bus.write_byte_data(BMP_ADDR, BMP_CTRL, 0x2E)
            time.sleep(0.005)
            d = self.bus.read_i2c_block_data(BMP_ADDR, BMP_DATA, 2)
            UT = (d[0] << 8) | d[1]
            X1 = ((UT - c['AC6']) * c['AC5']) >> 15
            X2 = (c['MC'] << 11) // (X1 + c['MD'])
            B5 = X1 + X2
            temp = (B5 + 8) / 16.0 / 10.0

            self.bus.write_byte_data(BMP_ADDR, BMP_CTRL, 0x34)
            time.sleep(0.005)
            d = self.bus.read_i2c_block_data(BMP_ADDR, BMP_DATA, 3)
            UP = ((d[0] << 16) | (d[1] << 8) | d[2]) >> 8

            B6 = B5 - 4000
            X1 = (c['B2'] * (B6*B6 >> 12)) >> 11
            X2 = c['AC2'] * B6 >> 11
            X3 = X1 + X2
            B3 = (((c['AC1']*4 + X3)) + 2) >> 2
            X1 = c['AC3'] * B6 >> 13
            X2 = (c['B1'] * (B6*B6 >> 12)) >> 16
            X3 = ((X1 + X2) + 2) >> 2
            B4 = c['AC4'] * (X3 + 32768) >> 15
            B7 = (UP - B3) * 50000
            p  = (B7*2) // B4 if B7 < 0x80000000 else (B7 // B4) * 2
            X1 = (p >> 8) ** 2
            X1 = (X1 * 3038) >> 16
            X2 = (-7357 * p) >> 16
            pressure = p + ((X1 + X2 + 3791) >> 4)

            altitude = 44330.0 * (1.0 - (pressure / 101325.0) ** (1/5.255))
            return temp, pressure, altitude
        except Exception as e:
            self.get_logger().warn(f'BMP180 read error: {e}')
            return 0.0, 101325.0, 0.0

    # ── QMC5883L ─────────────────────────────────────────────
    def _init_qmc5883l(self):
        try:
            self.bus.write_byte_data(QMC_ADDR, QMC_SET,  0x01)
            self.bus.write_byte_data(QMC_ADDR, QMC_CTRL1, 0x1D)
            time.sleep(0.05)
        except Exception as e:
            self.get_logger().warn(f'QMC5883L init: {e}')

    def _read_qmc5883l(self):
        try:
            raw = self.bus.read_i2c_block_data(QMC_ADDR, QMC_DATA, 6)
            def s16(l, h): v = (h << 8) | l; return v - 65536 if v > 32767 else v
            mx = s16(raw[0], raw[1]) * 1e-7
            my = s16(raw[2], raw[3]) * 1e-7
            mz = s16(raw[4], raw[5]) * 1e-7
            return mx, my, mz
        except Exception as e:
            self.get_logger().warn(f'QMC read error: {e}')
            return 0.0, 0.0, 0.0

    # ── Publish ──────────────────────────────────────────────
    def publish_all(self):
        now = self.get_clock().now().to_msg()

        ax, ay, az, gx, gy, gz, _ = self._read_mpu6050()
        mx, my, mz                 = self._read_qmc5883l()
        _, _, altitude             = self._read_bmp180()

        imu_msg = Imu()
        imu_msg.header.stamp    = now
        imu_msg.header.frame_id = 'imu'
        imu_msg.linear_acceleration.x = ax
        imu_msg.linear_acceleration.y = ay
        imu_msg.linear_acceleration.z = az
        imu_msg.angular_velocity.x    = gx
        imu_msg.angular_velocity.y    = gy
        imu_msg.angular_velocity.z    = gz
        imu_msg.orientation_covariance[0] = -1.0
        self.pub_imu.publish(imu_msg)

        mag_msg = MagneticField()
        mag_msg.header.stamp    = now
        mag_msg.header.frame_id = 'imu'
        mag_msg.magnetic_field.x = mx
        mag_msg.magnetic_field.y = my
        mag_msg.magnetic_field.z = mz
        self.pub_mag.publish(mag_msg)

        alt_msg = Float64()
        alt_msg.data = altitude
        self.pub_alt.publish(alt_msg)


def main(args=None):
    rclpy.init(args=args)
    node = IMUNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
