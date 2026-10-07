# Nodes and topics: how robot programs talk

Open the NAVERA box on a drone and count the programs running inside. One reads the GPS receiver.
One reads the attitude sensor. One grabs pictures from the camera. One compares those pictures with
the satellite map. One decides which position to trust. One sends that position to the autopilot.
One shows it on the operator's screen. That is about **ten programs, all running at the same time**,
and all of them need information from the others — many times per second.

How do they talk to each other? If every program had to know every other program ("hey, camera
program, send your picture to the vision program and to the screen program and…"), adding one new
program would mean changing all the others. Robot engineers solved this problem years ago with a
tool called **ROS**. In this lesson you will learn its four key words — **node, topic, message,
publish/subscribe** — and you will look at a live ROS system with your own eyes.

## ROS 2: a post office for robot programs

**ROS** means *Robot Operating System*. Despite the name, it is not an operating system like Linux
or Windows: it is a **toolkit** that runs on top of Linux and gives robot programs a common way to
exchange data. NAVERA uses **ROS 2 Humble**, a version released in 2022 that is used by thousands of
companies and universities. If you work on robots one day, you will very likely meet it again.

The best picture of ROS is a **post office**:

- the programs are the **people** who send and receive letters;
- each kind of news has its own **mailbox**, with a name written on it;
- every letter follows a **form** with fixed boxes to fill in;
- the post office delivers each letter to everybody who asked to receive that mailbox's news.

In ROS words, the people are **nodes**, the mailboxes are **topics**, the forms are **message types**,
and the delivery rule is **publish/subscribe**. Let's take them one by one.

## Nodes: one program, one job

A **node** is a running program that does one job and is connected to ROS. Each node has a name.
In NAVERA:

| Node name | Its one job |
|---|---|
| `gps_node` | read the GPS receiver on the serial port |
| `imu_node` | read the attitude sensor (which way the box is tilted and turned) |
| `day_subscriber` | find the drone's position from a day camera picture |
| `estimator_node` | the **arbiter**: decide which position to trust |
| `vehicle_output` | send the chosen position to the autopilot |

Small nodes with one job each are easier to write, to test, and to replace. When IRIS Systems added
night vision, nobody had to change the GPS node: they added a new node.

## Topics: named mailboxes

A **topic** is a named channel where data flows. Its name looks like a folder path:
`/navera/position`, `/navera/sensors/imu`, `/chatter`. A node can **publish** (send) on a topic,
**subscribe** (listen) to a topic, or both.

The important idea: **nodes never talk to each other directly — they only talk to topics.**
The GPS node does not know that the arbiter exists. It just publishes its positions on
`/navera/estimate/gps`. The arbiter does not know where the GPS positions come from: it subscribes
to `/navera/estimate/gps` and receives whatever is published there.

![A talker publishes on /chatter; every subscriber receives every message](assets/pubsub.svg)

This is called **publish/subscribe**. It is like a newspaper: the newspaper prints one edition, and
every subscriber gets a copy. The newspaper does not phone each reader. If 3 people subscribe, 3
copies are delivered; if nobody subscribes, the paper is printed anyway and nobody reads it. It has
three big advantages for a robot:

1. **Adding a listener changes nothing for the sender.** You can plug a debugging tool on any topic
   while the robot runs.
2. **A sender can be replaced.** In the lab of lesson 10 you will write a *fake* GPS. As long as it
   publishes the same message type on the same topic, the rest of the system cannot tell the
   difference — that is exactly how NAVERA is tested on a bench without a real GPS.
3. **Programs can crash and restart** without bringing the others down.

> [!NOTE]
> Your computer finds the other nodes **automatically**. When a node starts, it announces itself
> ("I am `talker`, I publish `/chatter`"); the others hear it and connect. This is called
> **discovery**. The software doing the delivery underneath is called **DDS** — you will see this
> word in error messages, but you never have to use it directly.

## Messages: a form with fixed boxes

A **message** is one piece of data sent on a topic. Every topic has exactly one **message type**,
and a message type is a fixed list of **fields**, each with a name and a type — like a form with
labelled boxes. The simplest one, `std_msgs/msg/String`, has a single field:

```
string data
```

A message type's full name has three parts: `package/msg/Name`. `std_msgs` is the package of
standard messages that comes with ROS; `sensor_msgs` has messages for sensors (GPS, IMU, camera…);
`navera_msgs` is **NAVERA's own package** of messages.

Here is the beginning of NAVERA's most important message, `navera_msgs/msg/PositionEstimate`
(you will study it field by field in lesson 12):

```
std_msgs/Header header        # when it was published, from which sensor
float64 latitude              # deg, WGS84
float64 longitude             # deg, WGS84
float64 altitude              # m above the WGS84 ellipsoid; NaN if unknown
...
uint8 source
uint8 SOURCE_UNKNOWN=0
uint8 SOURCE_GPS=1
uint8 SOURCE_DAY_VISION=2
...
```

Read it like this:

- `float64 latitude` — a field called `latitude` holding a decimal number (a `float64` is a Python
  `float`).
- `uint8 source` — a field called `source` holding a small whole number from 0 to 255 (`uint8` =
  "unsigned integer on 8 bits").
- `uint8 SOURCE_GPS=1` — with an `=` sign, it is **not** a field but a **constant**: a name for a
  value. It says "in the `source` field, **1 means GPS**". Constants make code readable:
  `msg.source == PositionEstimate.SOURCE_GPS` instead of a mysterious `msg.source == 1`.
- `std_msgs/Header header` — a field whose type is another message: messages can contain messages.

Because the format is fixed, every node that uses `PositionEstimate` agrees on what each number
means. No node can "invent its own format" — that is what makes it safe for the arbiter to compare
positions coming from very different sources.

## Your own private ROS: ROS_DOMAIN_ID

Discovery is automatic… so what stops your talker from talking to the student next to you, who is
working on the same computer? The **ROS_DOMAIN_ID**: a number between 0 and 232, like the
**channel of a walkie-talkie**. Nodes only discover nodes that use the same domain number.

- In this academy, **every student has their own domain**. You will never see another student's
  topics, and they will never see yours.
- A NAVERA box runs on its own domain too, and with `ROS_LOCALHOST_ONLY=1` its messages never
  leave the box: operators reach it through a web page, not through ROS. (Both are written in the
  box's settings — `docs/ARCHITECTURE.md` §1 explains it.)

Your terminal already has both settings. You will print them in the lab.

## The ros2 command: a stethoscope for robots

ROS comes with a command, `ros2`, to look inside a running system. These are the ones you need today:

| Command | What it shows |
|---|---|
| `ros2 run <package> <program>` | start a node |
| `ros2 node list` | the names of all running nodes |
| `ros2 node info /name` | what one node publishes and subscribes to |
| `ros2 topic list` | the names of all topics |
| `ros2 topic info /topic` | the topic's type, how many publishers and subscribers |
| `ros2 topic echo /topic` | print every message as it arrives (`Ctrl+C` to stop) |
| `ros2 topic hz /topic` | how many messages per second (**hertz**, Hz) |
| `ros2 topic pub /topic <type> "<data>"` | publish a message by hand |
| `ros2 interface show <type>` | the fields of a message type |

> [!TIP]
> `ros2` has an autocompletion: type `ros2 topic ec` then press `Tab`. Press `Tab` twice to see
> the choices. It also completes topic names!

Two topics appear even when you start nothing special: `/rosout` (every node's log messages) and
`/parameter_events` (changes of settings, lesson 13). You can ignore them today.

## In NAVERA

The whole NAVERA graph is drawn in `docs/ARCHITECTURE.md` of your copy
([open it](file:navera/docs/ARCHITECTURE.md)). Here is the heart of it, simplified:

![NAVERA's ROS graph: sources publish estimates, the arbiter publishes position and status](assets/navera_graph.svg)

Every position source publishes the **same message type**, `PositionEstimate`, on its own topic
`/navera/estimate/<source>`. The arbiter subscribes to all of them. In
[navera_estimator/…/estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py)
you can find these lines:

```python
self.sub_gps = self.create_subscription(
    PositionEstimate, "/navera/estimate/gps", self._on_gps, 10)
self.sub_day = self.create_subscription(
    PositionEstimate, "/navera/estimate/day", self._on_day, 10)
...
self.pub_pos = self.create_publisher(PositionEstimate, "/navera/position", 10)
self.pub_status = self.create_publisher(NavStatus, "/navera/nav_status", 10)
```

Even without knowing Python ROS yet, you can read them: "subscribe to `PositionEstimate` messages on
`/navera/estimate/gps` and call the function `_on_gps` for each one", and "I will publish
`PositionEstimate` on `/navera/position` and `NavStatus` on `/navera/nav_status`". You will write
lines exactly like these in lessons 10 and 11.

The arbiter publishes two answers:

- `/navera/position` — the winning position, only when there is one;
- `/navera/nav_status` — 5 times per second, the **state** of navigation: `INITIALIZING` (nothing
  heard yet), `NO_FIX` (no usable source), `FIX` (a measured position with a known accuracy) or
  `DEGRADED` (a position, but with reduced trust), plus the reason in plain words. In the message,
  the state is a number — the constants of `navera_msgs/msg/NavStatus` tell you which number is which.

In the lab you will start the real arbiter of your NAVERA copy and ask it these questions yourself.

## Words to remember

| Word | Meaning |
|---|---|
| **ROS 2** | a toolkit that lets robot programs exchange data; NAVERA uses ROS 2 Humble |
| **node** | a running program connected to ROS, with one job and a name |
| **topic** | a named channel (`/navera/position`) where messages flow |
| **message** | one piece of data sent on a topic |
| **message type** | the fixed list of fields of a message, e.g. `std_msgs/msg/String` |
| **field** | one named box of a message (`latitude`, `source`…) |
| **constant** | a name for a value in a message type (`SOURCE_GPS=1`) |
| **publish / subscribe** | send to a topic / receive everything sent to a topic |
| **discovery** | nodes finding each other automatically |
| **ROS_DOMAIN_ID** | the "walkie-talkie channel": only nodes with the same number see each other |
| **Hz (hertz)** | "times per second" |

## Check what you learned

<details><summary>1. The GPS node publishes on /navera/estimate/gps. Does it need to know the name of the arbiter node?</summary>
No. Publishers only know the topic. Any node that subscribes to <code>/navera/estimate/gps</code>
receives the messages — the arbiter, a logging tool, or <code>ros2 topic echo</code>.
</details>

<details><summary>2. In a message type, what is the difference between <code>uint8 source</code> and <code>uint8 SOURCE_GPS=1</code>?</summary>
The first is a field: a box that each message fills with a value. The second is a constant: a
readable name for the value 1 in that box. It is not sent in the message.
</details>

<details><summary>3. You run <code>ros2 topic list</code> and see nothing of your friend's NAVERA, although you are on the same computer. Why?</summary>
You have different ROS_DOMAIN_ID numbers, so your nodes never discover each other.
</details>

<details><summary>4. Why do all NAVERA sources publish the same message type?</summary>
So the arbiter can compare them with one single rule, whatever the source: same fields, same units,
same meaning. Lesson 12 is all about this "contract".
</details>

Now open the **🛠️ Lab** tab.
