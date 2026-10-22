# Connecting a GPS

NAVERA needs **one real GPS fix at take-off**: it is NAVERA's start position, the point every
vision pipeline searches around. After that the GPS may be jammed or lost for hours — that
is what NAVERA is for — but the vehicle must leave with a GPS fix.

You can plug the GPS in any of the common ways below. With the settings left to `auto` (the
default), NAVERA finds it by itself at every boot, and also when it is plugged in after the
box has started (as long as NAVERA had no GPS yet — a working GPS is never replaced, and the
GPS is never switched while the vehicle is armed).

**NAVERA only listens to your GPS.** It never changes the receiver's configuration, and it
sends nothing on a CAN bus, unless you explicitly allow it (`NAVERA_GPS_CONFIGURE=1`,
`NAVERA_GPS_CAN_ALLOCATE=1`, see below).

ArduPilot parameter names below are those of ArduPilot 4.5 (`GPS_TYPE`, `GPS_TYPE2`); on 4.6 and
later they are `GPS1_TYPE`, `GPS2_TYPE`. Type 14 = "MAV": a GPS fed over MAVLink — that is
NAVERA.

## Which connection?

| | Your GPS goes to | NAVERA feeds the autopilot as | Choose it when |
|---|---|---|---|
| **A** | NAVERA (USB or UART), NMEA or u-blox UBX | GPS 1 (`GPS_TYPE=14`) | recommended: NAVERA sees the raw GPS and is the autopilot's only GPS |
| **B** | the autopilot, as its **second** GPS | GPS 1 (`GPS_TYPE=14`) | the GPS must stay on the autopilot |
| **C** | the autopilot, as its **first** GPS (unchanged) | GPS 2 (`GPS_TYPE2=14`) | you cannot change the autopilot's GPS setup |
| **D** | the autopilot (unchanged), plus a Y-cable tap to NAVERA | GPS 2 (`GPS_TYPE2=14`) | as C, without relying on the autopilot's telemetry |
| **E** | a DroneCAN GPS (Here3 / Here4, Holybro DroneCAN…) on a CAN bus NAVERA listens to | GPS 1 or 2 | your GPS is a CAN GPS |
| **F** | the network (NMEA or UBX over TCP / UDP) | GPS 1 | a boat or ground vehicle already shares its GPS on Ethernet |
| **G** | a ROS topic (`sensor_msgs/NavSatFix`) | — (ROS output `/navera/fix`) | a ROS robot or boat |

A and B are the configurations verified with ArduPilot SITL in flight (NAVERA as GPS 1). In C
and D NAVERA reads the GPS correctly (verified in SITL), but whether the autopilot flies on
NAVERA when its own GPS is lost depends on its GPS switching (`GPS_AUTO_SWITCH`), which has not
been verified in flight with NAVERA — prefer A or B for GPS-denied flight.

In every wiring: **NAVERA never uses a GPS it feeds itself** (an autopilot GPS of type 14, or of
type 5 — NMEA — while NAVERA's NMEA output is on). It would be checking its own output against
itself.

---

## A — GPS directly to NAVERA (USB or UART)

```
   GPS receiver                         NAVERA box (Jetson)
  ┌────────────┐   USB cable           ┌──────────────────────┐
  │  u-blox /  │══════════════════════>│ USB  (/dev/ttyACM0,  │
  │  any NMEA  │                       │       /dev/ttyUSB0)  │
  └────────────┘                       │                      │      autopilot
        or, on the UART (3.3 V):        │                      │   ┌────────────┐
  GPS TX ─────────────────────────────> │ RX  /dev/ttyTHS1     │   │            │
  GPS RX <───────────────────────────── │ TX                   │   │            │
  GND    ────────────────────────────── │ GND                  │   │            │
  5 V    <───────── power ───────────── │                      │   │            │
                                        │ TELEM UART / USB ════│══>│ TELEM port │
                                        └──────────────────────┘   └────────────┘
                                          NAVERA's position = the autopilot's GPS 1
```

**Automatic:** the port, the baud rate (4800 – 921600) and the protocol. NMEA (with satellite
data) and u-blox UBX (`NAV-PVT`) are both recognised, even mixed. With UBX NAVERA uses the
receiver's own accuracy (`hAcc` / `vAcc`), its velocity and its time. u-blox 6 receivers have no
`NAV-PVT`: use their NMEA output.

**On the autopilot (ArduPilot):** `GPS_TYPE=14` (NAVERA as GPS 1), the MAVLink port to NAVERA,
and the other settings of the ArduPilot integration guide (`EK3_SRC1_VELXY=0`,
`EK3_SRC1_VELZ=0`, `GPS_DELAY_MS`).

**Optional:** `NAVERA_GPS_CONFIGURE=1` lets NAVERA turn on `NAV-PVT` / `NAV-DOP` in a u-blox
that only sends NMEA (in the receiver's RAM only; its saved configuration is not changed).

## B — GPS on the autopilot as its second GPS

```
   GPS receiver           autopilot                         NAVERA box
  ┌──────────┐  GPS 2   ┌──────────────────┐  MAVLink      ┌──────────────┐
  │   GPS    │═════════>│ GPS2 port         │<═════════════>│ TELEM link   │
  └──────────┘          │ GPS_TYPE2 = real  │  GPS2_RAW  ──>│ reads GPS 2  │
                        │ GPS_TYPE  = 14    │<── GPS_INPUT  │ feeds GPS 1  │
                        └──────────────────┘               └──────────────┘
```

**Automatic:** NAVERA finds the autopilot (serial, UDP 14550/14551, TCP 127.0.0.1:5760),
reads its GPS types, and uses its second GPS (`GPS2_RAW`) when `GPS_TYPE2` is a real
receiver.

**On the autopilot:** `GPS_TYPE=14` (NAVERA), `GPS_TYPE2` = your receiver's type (1 = auto,
2 = u-blox, 9 = DroneCAN…), `SERIALn_PROTOCOL=5` on the port of the real GPS. To keep the
autopilot on NAVERA only (and not on a GPS NAVERA refused as spoofed): `GPS_AUTO_SWITCH=0`,
`GPS_PRIMARY=0` — weigh it against your failsafe strategy.

## C — GPS on the autopilot as its first GPS, NAVERA as GPS 2

```
   GPS receiver           autopilot                         NAVERA box
  ┌──────────┐  GPS 1   ┌──────────────────┐  MAVLink      ┌──────────────┐
  │   GPS    │═════════>│ GPS port          │<═════════════>│ TELEM link   │
  └──────────┘          │ GPS_TYPE  = real  │ GPS_RAW_INT ─>│ reads GPS 1  │
                        │ GPS_TYPE2 = 14    │<── GPS_INPUT  │ feeds GPS 2  │
                        └──────────────────┘               └──────────────┘
```

**Automatic:** NAVERA reads the autopilot's first GPS (`GPS_RAW_INT`) **only while the
autopilot's own `GPS_TYPE` says it is not NAVERA** (not 14). It checks again every 30 s and at
every reconnection, and stops at once if `GPS_TYPE` becomes 14. `NAVERA_GPS_MONITOR_GPS1=0`
forbids this source.

**On the autopilot:** nothing changes for your GPS; `GPS_TYPE2=14` for NAVERA. See the note
above on `GPS_AUTO_SWITCH` (not verified in flight).

## D — Passive tap (Y-cable) on the GPS wire to the autopilot

```
   GPS receiver                         autopilot
  ┌────────────┐  TX ─────┬──────────> RX  GPS port (GPS_TYPE = 1 / 2: UBX at 230400)
  │  u-blox    │  RX <────┼─────────── TX
  │            │  GND ────┼──┬──────── GND
  └────────────┘          │  │
                          │  │         NAVERA box
                          └──┼──────>  RX  /dev/ttyTHS1  (or a USB-serial adapter's RX)
                             └──────── GND
                     NAVERA's TX is NOT connected: NAVERA only listens
```

**Automatic:** NAVERA recognises the u-blox binary stream ArduPilot configured (UBX `NAV-PVT`,
usually at 230400 baud) or NMEA, and uses it exactly as in A. It never sends anything to the
receiver — the autopilot stays the only one configuring it.

**On the autopilot:** nothing changes for your GPS; NAVERA's output as `GPS_TYPE2=14` (as C).

**Wiring rules:** connect only the GPS's TX and GND to NAVERA. The voltages must match (the
Jetson's UART is 3.3 V; most GPS modules' TX is 3.3 V). Keep the tap short.

## E — DroneCAN GPS (Here3, Here4, Holybro DroneCAN GNSS…)

```
  On the vehicle's CAN bus (shared with the autopilot):

   120 Ω                                                                  120 Ω
    ├────────── CAN H / CAN L ───────────┬───────────────────────────────────┤
    │                                    │                                   │
  ┌─┴────────┐                      ┌────┴──────┐                     ┌──────┴──────┐
  │ Here3 /  │  Fix2 messages ────> │ autopilot │                     │ NAVERA box  │
  │ Here4    │                      │ (node 10) │                     │ can0, listen│
  └──────────┘                      └───────────┘                     │ only        │
                                                                      └─────────────┘
  or alone on NAVERA's CAN bus:     Here3 ═══ CAN ═══ NAVERA (NAVERA_GPS_CAN_ALLOCATE=1)
```

The Jetson's CAN controller needs a CAN transceiver (3.3 V, e.g. SN65HVD230) on the carrier
board's CAN pins, or use a USB-CAN adapter (`slcan:/dev/ttyACM0`, or a SocketCAN adapter that
appears as `can1`). The bus needs a 120 Ω terminator at each end.

**Once, at installation (needs root):** bring the CAN interface up at 1 Mbit/s:

```bash
sudo ip link set can0 up type can bitrate 1000000 restart-ms 100       # now
sudo install -m 0644 deploy/can/80-navera-can0.network /etc/systemd/network/
sudo systemctl enable --now systemd-networkd                           # at every boot
```

**Automatic:** NAVERA listens to every CAN interface that is up for GPS fixes
(`uavcan.equipment.gnss.Fix2`), without a node id — it sends nothing on the bus. The
autopilot's own re-broadcast of its GPS (a node that also commands motors) is never taken.
Several GPS: NAVERA picks one and says so (`NAVERA_GPS_CAN_NODE` to choose).

**A DroneCAN GPS alone on NAVERA's bus** gets no node id (the autopilot normally gives it):
set `NAVERA_GPS_CAN_ALLOCATE=1`, and NAVERA becomes the bus's node-id allocator (it then
transmits, as node 125). The discovery report tells you when a device is waiting for an id.

**On the autopilot:** for a GPS it also uses, nothing changes. NAVERA's output: `GPS_TYPE=14`
if the CAN GPS is the autopilot's second GPS (`GPS_TYPE2=9`, as B), or `GPS_TYPE2=14` if it is
its first (as C).

## F — GPS over the network

```
  ship / vehicle network                     NAVERA box
  ┌────────────────────┐  NMEA or UBX       ┌──────────────┐
  │ GPS / NMEA server  │ ── TCP 10110 ────> │ Ethernet     │
  │ (or UDP broadcast) │ ── UDP 10110 ────> │              │
  └────────────────────┘                    └──────────────┘
```

**Automatic, once you give the address** (NAVERA never connects to an address it was not
given): `NAVERA_DISCOVER_GPS_URLS=tcp:192.168.1.50` (its ports 10110, 2000, 4001 are tried),
`tcp:192.168.1.50:5017`, or `udp` / `udp:10110` (NAVERA listens). Or impose it:
`NAVERA_GPS_SOURCE=network`, `NAVERA_GPS_URL=tcp:192.168.1.50:10110`.

## G — ROS GPS topic

`NAVERA_GPS_SOURCE=auto` finds a `sensor_msgs/NavSatFix` topic on NAVERA's ROS domain (or set
`NAVERA_GPS_SOURCE=ros`, `NAVERA_ROS_GPS_TOPIC=/your/gps/fix`). Give it a covariance: without
one NAVERA treats the GPS as "uncertainty unknown" (DEGRADED).

---

## Imposing the GPS by hand

Write in `/etc/navera/navera.env` instead of `auto` (a written value is always kept):

| Setting | Values |
|---|---|
| `NAVERA_GPS_SOURCE` | `serial`, `network`, `dronecan`, `vehicle` (autopilot GPS 2), `vehicle_gps1` (autopilot GPS 1), `ros` |
| `NAVERA_GPS_PORT`, `NAVERA_GPS_BAUD` | serial port and baud (`serial`) |
| `NAVERA_GPS_URL` | `tcp:<host>:<port>` or `udp:<port>` (`network`) |
| `NAVERA_GPS_CAN_IFACE`, `NAVERA_GPS_CAN_NODE` | CAN interface and node id, 0 = any (`dronecan`) |
| `NAVERA_GPS_CONFIGURE=1` | NAVERA may turn on UBX `NAV-PVT` in the receiver (RAM only) |
| `NAVERA_GPS_CAN_ALLOCATE=1` | NAVERA gives DroneCAN node ids (a GPS alone on its CAN) |
| `NAVERA_GPS_MONITOR_GPS1=0` | never use the autopilot's first GPS |

Then `sudo systemctl restart navera-gps navera-vehicle-link`.

## Checking that it works

1. **Before the flight, outdoors, with a clear sky:**
   ```bash
   python3 navera_tools/check_box.py
   ```
   The first lines are the discovery report, e.g.
   `GPS: serial — the receiver on /dev/ttyUSB0 (u-blox UBX)`,
   `GPS: dronecan — DroneCAN GNSS node 124 on can0`,
   `GPS: vehicle_gps1 — the autopilot's first GPS (type 2; NAVERA does not feed it: NAVERA is its second GPS, type 14)`.
   Lines with `NO` or `CHECK` need your attention (no GPS found, several receivers, a CAN
   interface down, a DroneCAN GPS waiting for a node id…). Then the live check must show
   `GPS … fixes` and `NAVERA FIX`.
2. **The full report:** `cat /var/lib/navera/discovery.json` (what was found where), and
   `journalctl -u navera-hotplug` for a GPS connected after boot.
3. **The GPS itself:** `ros2 topic echo /navera/estimate/gps --once` — `valid: true`, your
   position, and a covariance (the receiver's accuracy); `journalctl -u navera-gps -f` shows
   `FIX #…` lines.
4. **The operator page** (`http://<box>:8181/operator`) shows the GPS as the active source
   with its accuracy, before take-off.

If NAVERA found no GPS, the GPS service waits (`journalctl -u navera-gps`: "GPS idle"): plug
the GPS in and wait a few seconds (or up to a minute for a receiver powered after the box, or
a CAN GPS) — with the vehicle **disarmed** if NAVERA is connected to an autopilot.
