#!/usr/bin/env python3
"""
rtc_node.py — NAVERA real-time-clock driver for the DS3231 (TCXO, ±2 ppm).

Reads the DS3231 over I2C through the Adafruit Blinka / CircuitPython stack and
publishes:
    /navera/sensors/rtc_time     sensor_msgs/TimeReference
    /navera/sensors/rtc_status   std_msgs/String (JSON)

Purpose: give the celestial pipeline a time reference that survives a boot with no
network. Astrometry needs the exposure time; without NTP the Jetson boots with a
wrong clock, and a wrong clock silently poisons the plate-solve.

Why TimeReference and not builtin_interfaces/Time: the message carries BOTH clocks —
`header.stamp` is the system time at the moment of the read, `time_ref` is what the
DS3231 says. Their difference IS the drift, so consumers get it for free.

The DS3231 holds a whole second, no sub-second field: the time reference is only
accurate to ±1 s. One second of Earth rotation is ~15 arcsec, i.e. roughly 0.46 km of
longitude error at the equator — that is the precision floor this node imposes on
celestial fixes. Going below it requires wiring the DS3231 SQW pin (1 Hz square wave)
to a GPIO and latching on its edge; that is NOT done here.

Convention: the DS3231 is assumed to hold **UTC**, not local time. Whatever writes it
(`hwclock -w -u`, or a future GPS/NTP sync node) must respect that.

Wiring (Jetson Orin Nano, 40-pin header, I2C bus 1 — shared with the BNO085 IMU):
    DS3231 SDA -> pin 27      SCL -> pin 28
    DS3231 VCC -> pin 1 (3V3) GND -> pin 6

The DS3231 I2C address is fixed at 0x68 in silicon and is not configurable, so unlike
imu_node there is no `i2c_address` parameter. (The module's AT24C32 EEPROM sits at 0x57
and is not used.)

Parameters:
    i2c_bus                (default 1)          — 1 (pins 27/28) or 7 (pins 3/5)
    publish_rate           (default 1.0)        — Hz; the DS3231 resolves 1 s, faster is pointless
    frame_id               (default "rtc_link")
    time_source            (default "ds3231")   — TimeReference.source
    drift_warn_s           (default 2.0)        — log a warning past this |RTC - system| gap
    publish_when_invalid   (default False)      — see below

`publish_when_invalid`: the DS3231 raises an oscillator-stop flag (OSF, exposed as
`lost_power`) when it has lost power since the time was last set — a flat backup cell
typically leaves it reporting the year 2000. Such a reading is worse than no reading:
a plausible-looking timestamp that is wrong by decades. By default the node therefore
publishes rtc_status (with valid=false) but withholds rtc_time. Set the parameter to
True only for bench diagnostics.
"""
import json
import time as time_mod
from datetime import datetime, timezone
from typing import Optional, Tuple

import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import TimeReference
from std_msgs.msg import String

import board
import busio
import adafruit_ds3231

# I2C bus number -> (SCL pin, SDA pin) on the Jetson 40-pin header.
# Blinka addresses the bus by pin pair, not by /dev/i2c-N number.
_BUS_PINS = {
    1: ("SCL_1", "SDA_1"),  # pins 28 / 27
    7: ("SCL", "SDA"),      # pins  5 /  3
}

# Consecutive read failures tolerated before the RTC is re-initialized.
_MAX_READ_FAILURES = 5

# A DS3231 whose backup cell died reports 2000-01-01. Anything before this year is a
# reset chip, not a plausible mission time — belt and braces alongside the OSF flag.
_MIN_PLAUSIBLE_YEAR = 2024


class RTCNode(Node):
    """Publishes DS3231 wall-clock time as a TimeReference, plus a health status."""

    def __init__(self) -> None:
        super().__init__("rtc_node")

        self.declare_parameter("i2c_bus", 1)
        self.declare_parameter("publish_rate", 1.0)
        self.declare_parameter("frame_id", "rtc_link")
        self.declare_parameter("time_source", "ds3231")
        self.declare_parameter("drift_warn_s", 2.0)
        self.declare_parameter("publish_when_invalid", False)

        self.bus_num = int(self.get_parameter("i2c_bus").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.time_source = str(self.get_parameter("time_source").value)
        self.drift_warn_s = float(self.get_parameter("drift_warn_s").value)
        self.publish_when_invalid = bool(self.get_parameter("publish_when_invalid").value)
        rate = float(self.get_parameter("publish_rate").value)

        self.pub_time = self.create_publisher(TimeReference, "/navera/sensors/rtc_time", 10)
        self.pub_status = self.create_publisher(String, "/navera/sensors/rtc_status", 10)

        self.rtc: Optional[adafruit_ds3231.DS3231] = None
        self.read_failures = 0
        self.sample_count = 0

        self._connect()
        self.timer = self.create_timer(1.0 / rate, self.publish_rtc)
        self.get_logger().info(
            f"RTC node running at {rate:.1f} Hz "
            f"(source='{self.time_source}', resolution 1 s, UTC assumed)"
        )

    def _connect(self) -> bool:
        """Open the I2C bus and probe the DS3231. Returns True on success."""
        if self.bus_num not in _BUS_PINS:
            self.get_logger().error(
                f"Unsupported i2c_bus={self.bus_num}; expected one of {sorted(_BUS_PINS)}"
            )
            return False

        scl_name, sda_name = _BUS_PINS[self.bus_num]
        try:
            i2c = busio.I2C(getattr(board, scl_name), getattr(board, sda_name))
            rtc = adafruit_ds3231.DS3231(i2c)
            _ = rtc.datetime  # probe: fails here if nothing answers at 0x68
            lost_power = bool(rtc.lost_power)   # inside the try: a transient I2C
                                                # error here must not crash the node
        except Exception as exc:  # I2C bus, wiring or missing-device failure
            self.get_logger().error(
                f"DS3231 init failed on I2C bus {self.bus_num} @ 0x68: {exc}"
            )
            self.rtc = None
            return False

        self.rtc = rtc
        self.read_failures = 0
        self.get_logger().info(
            f"DS3231 ready on I2C bus {self.bus_num} ({scl_name}/{sda_name}) @ 0x68"
        )
        if lost_power:
            self.get_logger().error(
                "DS3231 oscillator-stop flag is SET: it lost power since the time was "
                "last written, so its time is NOT trustworthy. Check the backup cell, "
                "then write UTC to it (e.g. `sudo hwclock -w -u` once bound, or a sync "
                "node). Publishing rtc_time is suppressed until then."
            )
        return True

    @staticmethod
    def _decode(stamp: time_mod.struct_time) -> Optional[Tuple[float, str]]:
        """Convert a DS3231 struct_time (UTC) to (epoch_seconds, "YYYY-MM-DD HH:MM:SS").

        Returns None when the chip hands back something that is not a real calendar date.

        Two traps, both fatal to the naive version:
        * adafruit_register ALWAYS builds the struct_time with tm_yday = -1 (it never
          computes the day-of-year), and time.strftime rejects that outright with
          "day of year out of range" — on every read, healthy battery or not.
        * a DS3231 that lost power returns garbage BCD, so tm_mon can be 13 and
          calendar.timegm() raises "month must be in 1..12".

        Rebuilding a datetime from the six fields we actually care about dodges both:
        it ignores tm_yday, and it validates the rest.
        """
        try:
            dt = datetime(
                stamp.tm_year, stamp.tm_mon, stamp.tm_mday,
                stamp.tm_hour, stamp.tm_min, stamp.tm_sec,
                tzinfo=timezone.utc,          # the DS3231 holds UTC by convention
            )
        except (ValueError, OverflowError, TypeError):
            return None
        return dt.timestamp(), dt.strftime("%Y-%m-%d %H:%M:%S")

    def _read(self) -> Optional[tuple]:
        """Read one sample. Returns (struct_time, lost_power, temperature) or None."""
        try:
            stamp = self.rtc.datetime          # time.struct_time, interpreted as UTC
            lost_power = bool(self.rtc.lost_power)
            temperature = float(self.rtc.temperature)  # degC, internal TCXO sensor
        except Exception as exc:  # transient I2C errors
            self.read_failures += 1
            self.get_logger().warn(
                f"DS3231 read error ({self.read_failures}/{_MAX_READ_FAILURES}): {exc}",
                throttle_duration_sec=5.0,
            )
            return None

        self.read_failures = 0
        return stamp, lost_power, temperature

    def publish_rtc(self) -> None:
        """Timer callback: read the DS3231, publish its time and its health."""
        if self.rtc is None:
            self.get_logger().warn(
                "DS3231 not connected, retrying init...", throttle_duration_sec=10.0
            )
            self._connect()
            return

        sample = self._read()
        if sample is None:
            if self.read_failures >= _MAX_READ_FAILURES:
                self.get_logger().error(
                    f"{self.read_failures} consecutive read failures — reinitializing DS3231"
                )
                self.rtc = None
            return

        stamp, lost_power, temperature = sample
        sys_epoch = time_mod.time()
        decoded = self._decode(stamp)

        if decoded is None:  # corrupted date: no usable time, but the chip still talks
            rtc_epoch, rtc_utc, drift_s = None, "invalid", None
            plausible = False
        else:
            rtc_epoch, rtc_utc = decoded
            drift_s = rtc_epoch - sys_epoch
            plausible = stamp.tm_year >= _MIN_PLAUSIBLE_YEAR

        # An RTC written in LOCAL time is off from UTC by a whole number of
        # hours (Tunisia: +1 h = 15° of celestial longitude). Neither clock can
        # prove the other right, but that signature is unambiguous.
        local_time_hours = None
        if drift_s is not None and abs(drift_s) >= 3600 - 1:
            hours = round(drift_s / 3600.0)
            if abs(drift_s - hours * 3600.0) <= 1.5:
                local_time_hours = hours
        valid = (not lost_power) and plausible and local_time_hours is None
        if lost_power:
            reason = "oscillator stopped (lost power) — time not trustworthy"
        elif not plausible:
            reason = "implausible date"
        elif local_time_hours is not None:
            reason = f"RTC is {local_time_hours:+d} h from the system clock — it holds local time, not UTC"
        else:
            reason = ""

        now = self.get_clock().now().to_msg()

        status = {
            "valid": valid,
            "lost_power": lost_power,
            "temperature_c": round(temperature, 2),
            "drift_s": round(drift_s, 3) if drift_s is not None else None,
            "rtc_utc": rtc_utc,
            "source": self.time_source,
            "reason": reason,
        }
        status_msg = String()
        status_msg.data = json.dumps(status)
        self.pub_status.publish(status_msg)

        if not valid and not self.publish_when_invalid:
            self.get_logger().error(
                f"DS3231 time is NOT valid ({reason}; rtc_utc={rtc_utc}) — withholding rtc_time",
                throttle_duration_sec=30.0,
            )
            return

        if rtc_epoch is None:
            # publish_when_invalid=True, but the date does not decode: there is no
            # honest value to put in time_ref. rtc_status already carries the diagnosis.
            self.get_logger().error(
                "DS3231 returned a corrupted date — no rtc_time to publish",
                throttle_duration_sec=30.0,
            )
            return

        msg = TimeReference()
        msg.header.stamp = now              # system clock when the read happened
        msg.header.frame_id = self.frame_id
        msg.time_ref.sec = int(rtc_epoch)   # DS3231 wall clock, UTC, 1 s resolution
        msg.time_ref.nanosec = 0
        msg.source = self.time_source
        self.pub_time.publish(msg)

        if abs(drift_s) > self.drift_warn_s:
            self.get_logger().warn(
                f"RTC drifts {drift_s:+.1f} s from the system clock "
                f"(RTC {status['rtc_utc']} UTC). One of the two is wrong.",
                throttle_duration_sec=30.0,
            )

        self.sample_count += 1
        if self.sample_count == 1 or self.sample_count % 60 == 0:
            self.get_logger().info(
                f"RTC #{self.sample_count}: {status['rtc_utc']} UTC "
                f"drift={drift_s:+.3f}s temp={temperature:.2f}degC valid={valid}"
            )


def main(args=None) -> None:
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = RTCNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
