# Lab 9 — Measure a live ROS 2 graph, then question NAVERA

**Goal:** start ROS 2 nodes, observe discovery, ports, message sizes and QoS with your own
measurements, use a service and an action, then question NAVERA's real arbiter. You record every
result in [answers.py](file:./answers.py) and write a short analysis in [report.md](file:./report.md).
**Time:** about 2 h 30.

You need **three terminals** at the same time. In the **⌨️ Terminal** tab, click **＋ new** to open
another one, and click *Terminal 1*, *Terminal 2*… to switch. Every terminal starts in
`~/lessons/09-ros-intro`. A node runs until you stop it: click in its terminal and press **`Ctrl+C`**.

> [!TIP]
> Values in `answers.py`: text between quotes (`"RELIABLE"`), numbers without quotes (`24`),
> `True` / `False` with a capital letter, lists in brackets (`["/a", "/b"]`). Save with `Ctrl+S`.

## Step 1 — Your domain and its ports

In **Terminal 1**:

```bash
echo "domain $ROS_DOMAIN_ID, localhost only: $ROS_LOCALHOST_ONLY"
```

Compute your discovery port with the formula of the course (the shell can do arithmetic):

```bash
echo $((7400 + 250 * ROS_DOMAIN_ID))
```

> [!TASK]
> Fill `MY_DOMAIN_ID` and `DISCOVERY_PORT` in `answers.py`.

## Step 2 — A talker, seen from outside

Start the demo **talker** in Terminal 1. It publishes `Hello World: N` once per second:

```bash
ros2 run demo_nodes_py talker
```

Open **Terminal 2**. Which nodes and topics exist?

```bash
ros2 node list
```

```bash
ros2 topic list
```

You see `/talker`, `/chatter` and two topics that every graph has: `/rosout` (log messages) and
`/parameter_events` (parameter changes). If a list is empty, wait two seconds and run it again:
discovery takes a moment. Now the details of `/chatter`, **with QoS** (`-v` = verbose):

```bash
ros2 topic info -v /chatter
```

Read the type, then under the publisher's `QoS profile:` the `Reliability` and `Durability` lines.
Measure the rate (wait for a few `average rate:` lines, then `Ctrl+C`):

```bash
ros2 topic hz /chatter
```

and the bandwidth and message size (a few lines, then `Ctrl+C`):

```bash
ros2 topic bw /chatter
```

Compare `Message size mean` with the course's CDR calculation (section 2).

> [!TASK]
> Fill `CHATTER_TYPE`, `CHATTER_RELIABILITY`, `CHATTER_DURABILITY` (one word each, as printed),
> `TALKER_HZ` and `CHATTER_MSG_BYTES` (the mean size in bytes).

Now look at the real UDP sockets of your domain. This command lists the ports between your
discovery port and the next domain's:

```bash
ss -uln | awk -v lo=$((7400 + 250 * ROS_DOMAIN_ID)) '{n = split($4, a, ":"); p = a[n] + 0; if (p >= lo && p < lo + 250) print p}' | sort -nu
```

You should find your discovery port, then pairs `lo + 10 + 2p` / `lo + 11 + 2p` for each
participant p (the talker, the ros2 daemon, …). The formula of the course is in front of you.

How the command works: `ss -uln` lists the UDP ports that are open on this machine (column 4 is
`address:port`); `awk` reads it line by line, keeps the number after the last `:` (`split` cuts the
text at each `:`, `a[n]` is the last piece) and prints it only if it is inside your domain's range
`lo … lo + 249`; `sort -nu` sorts the numbers and removes duplicates. You do not need to write such a
line yourself.

> [!TASK]
> Copy the port numbers into `DDS_PORTS` (a list of numbers).

## Step 3 — Subscribers and a hand-made message

Open **Terminal 3** and start the demo **listener**:

```bash
ros2 run demo_nodes_py listener
```

It prints `I heard: [Hello World: 25]`. The talker was not changed: it does not know the listener
exists. In **Terminal 2**:

```bash
ros2 topic info /chatter
```

`Subscription count` is now 1. Save **one** message in a file (`--once` = one message, then stop):

```bash
ros2 topic echo --once /chatter > chatter.txt
```

Now publish your own message, 3 times (`-t 3`, one per second). Change the name to yours:

```bash
ros2 topic pub -t 3 /chatter std_msgs/msg/String "{data: 'Hello from Salim'}"
```

Terminal 3 prints `I heard: [Hello from Salim]`. Why three times and not `--once`? A single message
can be published before the listener has matched your new publisher (course, section 3: discovery
is asymmetric) and is then lost. If you try `--once` and nothing arrives, that is the reason — not
a mistake of yours.

> [!TASK]
> Fill `CHATTER_SUBSCRIBERS` (the subscription count with exactly one listener and no `echo`).
> `chatter.txt` must hold one message.

Stop the listener (Terminal 3) with `Ctrl+C`. Keep the talker running.

## Step 4 — Another domain is another world

In **Terminal 2**, list the topics as seen from another domain. The variable is changed for this
one command only:

```bash
ROS_DOMAIN_ID=$((ROS_DOMAIN_ID + 110)) ros2 topic list --no-daemon --spin-time 3
```

> [!NOTE]
> The domain `yours + 110` is between 111 and 211: private to you, and it collides with no other
> student (the teacher's automatic tests use 200–232, but never while you are working). As the course explains, such domains use ephemeral ports — fine for a 3-second test,
> not for a product.

> [!TASK]
> Fill `OTHER_DOMAIN_SEES_CHATTER` (`True` or `False`). Then stop the talker in Terminal 1.

## Step 5 — QoS experiments

**Reliability.** In **Terminal 1**, publish twice per second with BEST_EFFORT:

```bash
ros2 topic pub -r 2 /qos_test std_msgs/msg/String "{data: 'best effort'}" --qos-reliability best_effort
```

In **Terminal 2**, subscribe with RELIABLE. Wait 5 seconds, read, then `Ctrl+C`:

```bash
ros2 topic echo /qos_test --qos-reliability reliable
```

Now subscribe with BEST_EFFORT (`Ctrl+C` after a few messages):

```bash
ros2 topic echo /qos_test --qos-reliability best_effort
```

Stop the publisher in Terminal 1.

**Durability.** In **Terminal 1**, publish **one** latched message and keep it for 60 s
(`-w 0`: do not wait for a subscriber; depth 1: keep the last message):

```bash
ros2 topic pub --once -w 0 --keep-alive 60 --qos-depth 1 --qos-durability transient_local /mission_start std_msgs/msg/String "{data: 'go'}"
```

In **Terminal 2**, a few seconds later — a late subscriber — first with TRANSIENT_LOCAL:

```bash
ros2 topic echo --once /mission_start --qos-durability transient_local --qos-reliability reliable
```

then with VOLATILE (wait 5 s, then `Ctrl+C` if nothing comes):

```bash
ros2 topic echo --once /mission_start --qos-durability volatile --qos-reliability reliable
```

> [!NOTE]
> Why `--qos-reliability reliable` here? DDS sends the stored ("historical") samples only to
> RELIABLE subscribers: a BEST_EFFORT + TRANSIENT_LOCAL subscriber is matched but receives only new
> messages. Try it without the option and see.

> [!TASK]
> Fill the four booleans `BE_PUB_RELIABLE_SUB_RECEIVED`, `BE_PUB_BE_SUB_RECEIVED`,
> `LATCHED_TRANSIENT_RECEIVED` and `LATCHED_VOLATILE_RECEIVED` with what you observed, and copy the
> warning line you saw in the RELIABLE case into `report.md`.

## Step 6 — A service and an action

Start a demo **service** server in **Terminal 1** (it adds two integers):

```bash
ros2 run examples_rclpy_minimal_service service
```

In **Terminal 2**, list services (ignore the `…/describe_parameters`-style ones: that is the
parameter machinery) and call it with `a` = your domain number and `b` = 1000:

```bash
ros2 service list
```

```bash
ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: $ROS_DOMAIN_ID, b: 1000}"
```

Stop the server. Now an **action**: a server that computes a Fibonacci sequence slowly, with
feedback after each step. In **Terminal 1**:

```bash
ros2 run action_tutorials_py fibonacci_action_server
```

In **Terminal 2** (it takes about 8 seconds; watch the feedback):

```bash
ros2 action send_goal --feedback /fibonacci action_tutorials_interfaces/action/Fibonacci "{order: 8}"
```

> [!TASK]
> Fill `SERVICE_SUM` and `FIBONACCI_8` (the final `sequence`, as a Python list of numbers). Stop the
> action server.

## Step 7 — Message types of NAVERA

```bash
ros2 interface show navera_msgs/msg/PositionEstimate
```

```bash
ros2 interface show navera_msgs/msg/NavStatus
```

Find the constants (lines with `=`). The same files are in your copy:
[PositionEstimate.msg](file:navera/navera_msgs/msg/PositionEstimate.msg),
[NavStatus.msg](file:navera/navera_msgs/msg/NavStatus.msg).

> [!TASK]
> Fill `MODE_REPLAYED` and `STATE_FIX` (numbers).

## Step 8 — Question NAVERA's arbiter

In **Terminal 1**, start the arbiter of **your NAVERA copy**:

```bash
ros2 run navera_estimator estimator_node.py
```

It prints `estimator up (v3 GPS>day>night>cn) …` with its freshness windows. In **Terminal 2**:

```bash
ros2 node info /estimator_node
```

Compare `Subscribers:` and `Publishers:` with the course's picture. Its status, once:

```bash
ros2 topic echo --once /navera/nav_status
```

No source runs, so it has heard nothing: read `state:` and `reason:`. `state:` is printed as a
**number**, not a name: the names are constants of the message (`ros2 interface show
navera_msgs/msg/NavStatus` lists them: `STATE_INITIALIZING=0`, `STATE_NO_FIX=1`…). `FIRST_STATE` is that
number. Its rate (`Ctrl+C` after a
few lines):

```bash
ros2 topic hz /navera/nav_status
```

A parameter, read through the **service** behind it:

```bash
ros2 service call /estimator_node/get_parameters rcl_interfaces/srv/GetParameters "{names: ['fix_max_sigma_m']}"
```

The answer contains `double_value=25.0`: `ros2 param get` does exactly this call for you. Finally,
is there a position?

```bash
ros2 topic echo --once /navera/position
```

This one waits forever — press `Ctrl+C`. The arbiter publishes a position **only when it has one**;
it never repeats an old one as if it were new.

> [!TASK]
> Fill `ESTIMATOR_SUBSCRIBES` (5 topics), `ESTIMATOR_PUBLISHES` (the 2 topics starting with
> `/navera`), `FIRST_STATE` (the number after `state:`), `NAV_STATUS_HZ` and `FIX_MAX_SIGMA_M`. Answer the quiz `Q1`–`Q3`.
> Stop the arbiter.

## Step 9 — Write the analysis

Open [report.md](file:./report.md) and write its three sections, in your own words (at least 40
words each):

- **Discovery** — your discovery port and the ports you saw, explained with the formula; why the
  other domain saw nothing.
- **QoS** — what happened in each of the four experiments of step 5 and why (use the words
  RELIABLE, BEST_EFFORT, TRANSIENT_LOCAL, VOLATILE), and the warning line.
- **NAVERA** — what the arbiter subscribes to and publishes, what it said with no source, and one
  design rule you noticed.

Press **✔ Check my work**. The checker starts its own talker and compares your answers with what ROS
really says.

## Going further (optional)

- **Remapping.** `ros2 run demo_nodes_py listener --ros-args -r chatter:=/news` listens to `/news`
  without changing the code; publish on `/news` with `ros2 topic pub -t 3`. NAVERA uses remapping to
  plug into vehicles whose topics have other names (lesson 13).
- **Depth and late joiners.** Publish three latched messages with
  `ros2 topic pub -t 3 -w 0 --keep-alive 60 --qos-depth 3 --qos-durability transient_local /hist std_msgs/msg/String "{data: x}"`,
  then start a late `ros2 topic echo /hist --qos-durability transient_local --qos-reliability reliable --qos-depth 10`. How many
  messages does it receive? Repeat with `--qos-depth 1` on the publisher and explain.
- **Participants.** Start two more listeners and run the `ss` command of step 2 again: count the new
  port pairs and match them with participant indices.
