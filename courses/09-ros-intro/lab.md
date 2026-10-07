# Lab 9 — Explore a live ROS graph

**Goal:** start ROS nodes, watch their topics and messages with the `ros2` command, then question
NAVERA's real arbiter. You write what you find in `answers.py`.
**Time:** about 45 minutes.

You will need **two or three terminals** at the same time: one node keeps running in a terminal, so
you need another one to look at it. In the **⌨️ Terminal** tab, click **＋ new** to open another
terminal; click on the tabs *Terminal 1*, *Terminal 2*… to switch between them. Every terminal
starts in your lab folder, `~/lessons/09-ros-intro`.

> [!TIP]
> A node runs until you stop it. To stop the program running in a terminal, click in that terminal
> and press **`Ctrl+C`**. If a terminal seems "stuck", that is usually a node working normally!

## Step 1 — Your private channel

In **Terminal 1**, print your ROS settings:

```bash
echo $ROS_DOMAIN_ID
```

```bash
echo $ROS_LOCALHOST_ONLY
```

The first number is your own **ROS_DOMAIN_ID** — nobody else in the class has it. The second, `1`,
means your ROS messages never leave this computer.

> [!TASK]
> Open [answers.py](file:./answers.py) and write your domain number in `MY_DOMAIN_ID`, **without
> quotes** (for example `MY_DOMAIN_ID = 123`). Save with `Ctrl+S`.

## Step 2 — Start a talker

ROS comes with demo nodes. Start the **talker** in Terminal 1:

```bash
ros2 run demo_nodes_py talker
```

It prints a line every second: `Publishing: "Hello World: 0"`, `1`, `2`… It is publishing
messages on a topic. Leave it running — the next commands go in another terminal.

## Step 3 — Look at the talker from outside

Click **＋ new** to open **Terminal 2**. First, which nodes are running?

```bash
ros2 node list
```

You see `/talker`. (If the list is empty, run the command again: the first `ros2` command starts a
helper program, the **ROS daemon**, which needs a second or two to discover the nodes.) Now the topics:

```bash
ros2 topic list
```

You see `/chatter` (the talker's topic) and the two topics that always exist, `/parameter_events`
and `/rosout`. Ask for details about `/chatter`:

```bash
ros2 topic info /chatter
```

It prints the **type** of the messages and how many nodes publish and subscribe. Now look at the
messages themselves:

```bash
ros2 topic echo /chatter
```

Each message is printed as `data: 'Hello World: 12'` followed by `---`. Stop it with `Ctrl+C`.
Finally, measure the rate:

```bash
ros2 topic hz /chatter
```

Wait for a few `average rate:` lines, then `Ctrl+C`.

> [!NOTE]
> If you see `WARNING: topic [/chatter] does not appear to be published yet` or
> `Could not determine the type`, the ros2 tool has not discovered the talker yet. Wait two
> seconds and run the command again.
>
> If any `ros2` command prints a long error ending with `!rclpy.ok()`, the ROS daemon (the helper
> program that remembers the graph) is stuck: run `ros2 daemon stop`, then your command again.

> [!TASK]
> In `answers.py`, fill `CHATTER_TYPE` (the exact text after `Type:`, between quotes) and
> `TALKER_HZ` (the average rate, a number).

## Step 4 — Add a listener

Open **Terminal 3** with **＋ new** and start the demo **listener**:

```bash
ros2 run demo_nodes_py listener
```

It prints `I heard: [Hello World: 25]` — the talker's messages. The talker was **not** changed or
restarted: it does not even know the listener exists. That is publish/subscribe.

Go back to **Terminal 2** (make sure no `ros2 topic echo` is running there) and look at the topic
again:

```bash
ros2 topic info /chatter
```

`Subscription count` went up. You can also ask the listener node what it does:

```bash
ros2 node info /listener
```

Under `Subscribers:` you find `/chatter: std_msgs/msg/String`.

> [!TASK]
> Fill `CHATTER_SUBSCRIBERS`: the subscription count of `/chatter` while exactly one listener runs
> (and no `echo`).

## Step 5 — Save a message, and send your own

Still in Terminal 2, save **one** message into a file. `--once` means "print one message, then
stop", and `>` sends the output into a file instead of the screen (lesson 2):

```bash
ros2 topic echo --once /chatter > chatter.txt
```

Open [chatter.txt](file:./chatter.txt) in the editor: it holds one message.

Now **you** become a publisher. Change the name and run:

```bash
ros2 topic pub --once /chatter std_msgs/msg/String "{data: 'Hello from Sarra'}"
```

Look at Terminal 3: the listener printed `I heard: [Hello from Sarra]`. For a moment the topic had
two publishers — the talker and you — and the listener could not tell the difference. This is how
engineers test a node: they feed it hand-made messages.

Now stop the talker (Terminal 1) and the listener (Terminal 3) with `Ctrl+C`.

## Step 6 — Read message types

A message type is described by a short text file. Show the simplest one:

```bash
ros2 interface show std_msgs/msg/String
```

One field: `string data`. (The comments say this type is *deprecated* — "old-fashioned, make your
own instead". It is perfect for a demo; real products like NAVERA define their own meaningful types.)

Now NAVERA's own messages. They are long, with many comments (`#`). Scroll with the mouse wheel:

```bash
ros2 interface show navera_msgs/msg/PositionEstimate
```

```bash
ros2 interface show navera_msgs/msg/NavStatus
```

Find the **constants** (lines with `=`): `SOURCE_…`, `MODE_…` in PositionEstimate, `STATE_…` in
NavStatus. The same files are in your NAVERA copy:
[PositionEstimate.msg](file:navera/navera_msgs/msg/PositionEstimate.msg) and
[NavStatus.msg](file:navera/navera_msgs/msg/NavStatus.msg).

> [!TASK]
> Fill `MODE_REPLAYED` and `STATE_FIX` with the numbers you found (without quotes).

## Step 7 — Question NAVERA's arbiter

Time to look at the real thing. In **Terminal 1**, start the arbiter of **your NAVERA copy**:

```bash
ros2 run navera_estimator estimator_node.py
```

It prints `estimator up (v3 GPS>day>night>cn) …`: the priority order of its sources, and its
**freshness windows** (how old a position may be before it is thrown away). Leave it running and go
to **Terminal 2**:

```bash
ros2 node info /estimator_node
```

Read the lists `Subscribers:` (what it listens to) and `Publishers:` (what it sends). Compare with
the picture in the course. Now listen to its status:

```bash
ros2 topic echo --once /navera/nav_status
```

No source is running, so the arbiter has heard nothing. Look at the `state:` number and at the last
line, `reason:`. Each source appears in `sources:` with `alive: false`. How often does it speak?

```bash
ros2 topic hz /navera/nav_status
```

About 5 times per second (`Ctrl+C` to stop) — it keeps telling the world its state even when nothing
happens, so a silent arbiter can be noticed. Is there a position?

```bash
ros2 topic echo --once /navera/position
```

This one waits forever — press `Ctrl+C`. The arbiter publishes a position **only when it has one**.
It never repeats an old position as if it were new: a design rule of NAVERA.

> [!TASK]
> Fill `ESTIMATOR_SUBSCRIBES` (5 topics), `ESTIMATOR_PUBLISHES` (the 2 topics starting with
> `/navera`) and `FIRST_STATE` (the `state` number you saw). Then answer the quiz `Q1`, `Q2`, `Q3`.

Stop the arbiter in Terminal 1 with `Ctrl+C`.

## Step 8 — Check your work

Save `answers.py` and press **✔ Check my work**. The checker starts its own talker to compare your
answers with what ROS really says. Fix anything red and check again.

## Going further (optional)

- **Rename a topic without changing code.** Start a listener that listens to `/news` instead of
  `/chatter`: `ros2 run demo_nodes_py listener --ros-args -r chatter:=/news`. Then publish on
  `/news` with `ros2 topic pub`. This is called **remapping** — NAVERA uses it to plug into a
  vehicle whose topics have other names.
- **Publish repeatedly**: `ros2 topic pub -r 2 /chatter std_msgs/msg/String "{data: 'tick'}"`
  publishes 2 times per second until `Ctrl+C`. Measure it with `ros2 topic hz`.
- Run `ros2 interface show sensor_msgs/msg/NavSatFix` — the standard GPS message. You will publish
  it yourself in the next lesson.
