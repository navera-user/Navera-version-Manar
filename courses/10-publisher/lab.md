# Lab 10 — Build a fake GPS

**Goal:** complete [fake_gps.py](file:./fake_gps.py) so that it publishes a `NavSatFix` on
`/fake_gps/fix`, 2 times per second, for a vehicle driving north-east at 5 m/s from Sousse.
**Time:** about 1 hour.

You will need two terminals (**＋ new** in the Terminal tab). Remember: `Ctrl+C` stops a node.

## Step 1 — Run the starter

The file is already open in the editor. Read it from top to bottom: settings, three functions,
the node class, and `main()`. Then run it:

```bash
python3 fake_gps.py
```

It prints `fake GPS publishing on /fake_gps/fix at 2.0 Hz`… and then nothing. In Terminal 2, check:

```bash
ros2 node list
```

(If the list is empty, run the command again: the first `ros2` command of a session starts a
helper program, the **ROS daemon**, which needs a second or two to discover the nodes.)
Your node `/fake_gps` exists! But it publishes nothing yet: it has no publisher and no timer.
Stop it with `Ctrl+C` in Terminal 1.

## Step 2 — Metres to degrees (TODO 1)

> [!TASK]
> **TODO 1** — complete `meters_to_degrees(north_m, east_m, lat_deg)`. It returns a pair
> `(dlat, dlon)`: 111 195 m north must give `dlat = 1.0`; east metres are divided by the length of a
> degree of longitude, which is `m_per_deg_lat * math.cos(math.radians(lat_deg))`.

Test your function **without ROS**, directly in Python. This command imports your file and calls
the function (the node does not start, because `main()` only runs when the file is the main program):

```bash
python3 -c "from fake_gps import *; print(meters_to_degrees(111195, 0, 35.8)); print(meters_to_degrees(0, 1000, 60))"
```

You should see about `(1.0, 0.0)` and `(0.0, 0.01798…)` — at 60° of latitude, 1 km east is twice as
many degrees as at the equator.

## Step 3 — Where am I at time t? (TODO 2)

> [!TASK]
> **TODO 2** — complete `position_at(t_s)`: compute `north_m` and `east_m` from the speeds and the
> time, turn them into degrees with `meters_to_degrees(...)` at `START_LAT`, and return
> `(START_LAT + dlat, START_LON + dlon)`.

Test it:

```bash
python3 -c "from fake_gps import *; print(position_at(0)); print(position_at(10))"
```

`position_at(0)` must be the start `(35.8256, 10.6084)`; after 10 s the latitude and the longitude
have both grown a little (50 m north-east).

## Step 4 — Fill the message (TODO 3)

> [!TASK]
> **TODO 3** — in `make_fix(lat, lon, stamp)`, fill `status.status`, `status.service`, `latitude`,
> `longitude`, `altitude`, the 9 numbers of `position_covariance` (variance `SIGMA_M ** 2` east and
> north, `(2 * SIGMA_M) ** 2` up) and `position_covariance_type`. The course's NavSatFix table and
> the NAVERA excerpt show every field.

Print one message to see it — ROS messages print themselves with all their fields:

```bash
python3 -c "from fake_gps import *; from builtin_interfaces.msg import Time; print(make_fix(35.8256, 10.6084, Time()))"
```

(`Time()` is an empty time stamp, 0 seconds — good enough to print a message.) Look for
`latitude=35.8256`, `status=…status=0, service=1`, and your covariance list.

## Step 5 — Publisher and timer (TODO 4 and 5)

> [!TASK]
> **TODO 4** — in `__init__`, create the publisher: `self.create_publisher(...)` with the message
> type `NavSatFix`, the topic `TOPIC` and the queue depth `10`, and store it in `self.pub`.
> **TODO 5** — create a timer that calls `self.on_timer` every `1.0 / RATE_HZ` seconds.

Run your node in Terminal 1:

```bash
python3 fake_gps.py
```

Every 5 seconds it logs `fix 11: lat … lon …` (it logs one fix in ten, not to flood the screen).

## Step 6 — Watch it from outside

In Terminal 2, look at the topic exactly like in lesson 9:

```bash
ros2 topic info /fake_gps/fix
```

```bash
ros2 topic hz /fake_gps/fix
```

The average rate must be about `2.000` (`Ctrl+C` to stop). Now print one message:

```bash
ros2 topic echo --once /fake_gps/fix
```

Check every field: the stamp, `status: 0`, `service: 1`, your latitude and longitude, the
covariance. Run it again a few seconds later: the latitude and longitude have grown — your vehicle
is driving!

You can also print only one field — very handy:

```bash
ros2 topic echo /fake_gps/fix --field latitude
```

The latitude grows by about 0.000018° per message (0.5 s × 4 m/s = 2 m north). `Ctrl+C` to stop.

## Step 7 — Check your work

Stop your node (`Ctrl+C` in Terminal 1) — the checker starts its own copy — and press
**✔ Check my work**. It runs your node for about 15 seconds, then checks the topic name, the node
name, the rate, the fields and the speed of the vehicle.

> [!WARNING]
> If the checker says "no message arrived", run `python3 fake_gps.py` yourself and read the error:
> a mistake inside `on_timer` (for example in `make_fix`) only shows up when the timer rings, as a
> red Python error in the terminal.

## Going further (optional)

- **A turning vehicle.** Change `position_at` so the vehicle drives in a circle of 200 m radius
  around the start (hint: `north = r × cos(ω t)`, `east = r × sin(ω t)` with `ω = speed / r`).
  Watch the latitude go up and down with `--field latitude`.
- **A failing GPS.** Every 20 seconds, publish 5 seconds of `STATUS_NO_FIX` (like a tunnel). In
  lesson 11 you will see how NAVERA reacts.
- **Count your messages.** Run `ros2 topic echo /fake_gps/fix --field header.stamp.sec` and see the
  seconds tick twice per value.
