# rtc_pkg — NAVERA RTC driver (DS3231)

Reads the DS3231 real-time clock over I2C and publishes it as a ROS2 time reference.

## Why

The celestial pipeline plate-solves a star image against an ephemeris: it needs the
**exposure time**. Without a network the Jetson boots with a wrong clock, and a wrong
clock silently poisons the solve — the solver does not fail, it returns a confidently
wrong position. The DS3231 is a battery-backed TCXO (±2 ppm, ≈0.17 s/day) that keeps
UTC across power cycles with no network, so the celestial fix has a time reference in
the field.

This node **reads and publishes**. It does **not** set the system clock (that needs
root and would fight NTP; binding the DS3231 as a kernel RTC device is a separate
piece of work — see *Limits* below).

## Node: `rtc_node`

Executable `rtc_node.py` (node name `rtc_node`). Subscribes to nothing.

| | Topic | Type | Rate | QoS |
|---|---|---|---|---|
| out | `/navera/sensors/rtc_time` | `sensor_msgs/TimeReference` | 1 Hz | depth 10 (reliable) |
| out | `/navera/sensors/rtc_status` | `std_msgs/String` (JSON) | 1 Hz | depth 10 (reliable) |

`TimeReference` carries **both** clocks: `header.stamp` is the system time at the
moment of the read, `time_ref` is what the DS3231 says, `source` is `"ds3231"`. The
difference between the two is the drift — consumers get it for free.

`rtc_status` JSON:

```json
{"valid": true, "lost_power": false, "temperature_c": 31.75,
 "drift_s": -0.412, "rtc_utc": "2026-07-14 08:58:43", "source": "ds3231", "reason": ""}
```

- `lost_power` — the DS3231 oscillator-stop flag (OSF): the chip lost power since its
  time was last written, so its time is **not trustworthy** (a flat backup cell
  typically leaves it reporting the year 2000).
- `valid` — `false` when `lost_power` is set or the year is implausible (< 2024). When
  invalid, the node publishes `rtc_status` but **withholds** `rtc_time`: a
  wrong-by-decades timestamp is worse for the solver than a missing one.
- `reason` — why the time is invalid (empty when valid), e.g. "holds local time".
- `temperature_c` — the DS3231's internal sensor (it is what the TCXO compensates
  against; also a free board-temperature reading).
- A chip that lost power can return a date that is not a real calendar date. The node
  survives it: `rtc_utc` becomes `"invalid"`, `drift_s` becomes `null`, and the rest of
  the status (`lost_power`, `temperature_c`) still tells you what is wrong. It never
  publishes `rtc_time` in that state.

### Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `i2c_bus` | `1` | 1 = pins 27/28, 7 = pins 3/5 |
| `publish_rate` | `1.0` | Hz — the DS3231 resolves 1 s, faster is pointless |
| `frame_id` | `rtc_link` | |
| `time_source` | `ds3231` | goes into `TimeReference.source` |
| `drift_warn_s` | `2.0` | warn past this \|RTC − system\| gap |
| `publish_when_invalid` | `false` | bench diagnostics only — see above |

Defaults are also in `config/rtc_params.yaml` (loaded by `rtc.launch.py`); the launch file
exposes `i2c_bus` and `publish_rate` as launch arguments.

The DS3231's I2C address is **fixed at 0x68 in silicon**, so there is no `i2c_address`
parameter (unlike `imu_pkg`). The module's AT24C32 EEPROM at 0x57 is unused.

## Wiring

Jetson Orin Nano 40-pin header, I2C bus 1 — **shared with the BNO085 IMU** (0x4A):

```
DS3231 SDA -> pin 27      SCL -> pin 28
DS3231 VCC -> pin 1 (3V3) GND -> pin 6
```

Two processes on one I2C bus is fine: the kernel serializes transactions.

```
$ i2cdetect -y -r 1
40: UU -- -- -- -- -- -- -- -- -- 4a -- ...   <- 4a = BNO085 IMU
50: -- -- -- -- -- -- -- 57 -- -- -- -- ...   <- 57 = AT24C32 EEPROM (unused)
60: -- -- -- -- -- -- -- -- 68 -- -- -- ...   <- 68 = DS3231
```

If `68` shows as `UU`, a kernel driver has claimed the chip and this node cannot read
it over I2C — see *Limits*.

## Run

```bash
ros2 launch rtc_pkg rtc.launch.py
ros2 topic echo /navera/sensors/rtc_time
ros2 topic echo /navera/sensors/rtc_status
```

At boot, via systemd: `deploy/systemd/navera-rtc.service` (see `deploy/README.md`), which runs
`navera_boot_rtc.sh`: `ros2 launch rtc_pkg rtc.launch.py i2c_bus:=$NAVERA_BOX_RTC_BUS
publish_rate:=1.0` (bus default 1). When the boot discovery found no DS3231
(`NAVERA_BOX_RTC=0`) the service stays up but idle.

## Convention: the DS3231 holds UTC

Not local time. Whatever writes it must respect that. To set it once from a
network-synced host: bind it to the kernel (below) and run `sudo hwclock -w -u`, or
write it from a Python one-liner using `adafruit_ds3231` with a UTC `struct_time`.

## Limits (do not oversell this)

- **1-second resolution.** The DS3231 has no sub-second register. One second of Earth
  rotation is ~15 arcsec ≈ **0.46 km** of longitude error at the equator: that is the
  precision floor this node imposes on any celestial fix. Going below it means wiring
  the DS3231 `SQW` pin (1 Hz square wave) to a GPIO and latching on its edge — **not
  done here**.
- **Drift is stated from the datasheet** (±2 ppm ≈ 0.17 s/day), **not measured** on
  NAVERA hardware. Characterize it over a long run before quoting a number.
- **The system clock is untouched.** So a Jetson that boots offline still has a wrong
  *system* clock; only the *topic* carries good time. Fixing the system clock at boot
  means binding the DS3231 as a kernel RTC device (device-tree overlay, or
  `echo ds3231 0x68 > /sys/bus/i2c/devices/i2c-1/new_device`) and letting `hwclock`
  restore it — but then the kernel owns 0x68, it shows as `UU`, and **this node can no
  longer read it over I2C**. The two approaches are mutually exclusive on the bus.
  Deliberate choice for now: userspace, no risk to the running system.
- **Consumers:** `cn_subscriber` subscribes to `rtc_time` (its `rtc_topic` parameter) and uses
  it for the current UTC when the last reading is at most 5 s old (else the system clock); `navera_tools/check_box.py` reads
  `rtc_status` in the pre-flight check.

## Local-time detection

An RTC written in local time instead of UTC is off from the system clock by a whole number of
hours. `rtc_node` reports such a clock as **invalid** (`rtc_status.reason`: "holds local
time"), because one hour is 15° of celestial longitude. Any other large drift is only warned
about: at an offline boot the system clock may be the wrong one. A transient I²C error while
connecting no longer crashes the node.
