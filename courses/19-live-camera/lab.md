# Lab 19 — Read the real camera

**Goal:** read frames from NAVERA's Insta360 (or from recorded frames when it is not yours), measure
the frame rate, stamp each frame with its exposure time, cut out the two lenses — then run NAVERA's
**own** live camera node and look at what it publishes.
**Time:** about 1 h 15.

> [!NOTE]
> **Camera or no camera?** The camera is shared. If you have **booked** it in the dashboard (and
> nobody's test is using it), the programs read the real camera. Otherwise they automatically read
> **recorded frames** of the same camera, in `/data/academy/19-live-camera/`. Everything in this lab
> works both ways, and **✔ Check my work** can pass without the camera (the camera-only check is then
> skipped).

> [!WARNING]
> **Privacy.** The recorded frames were saved while the camera's top lens looked at a calibration
> chessboard — and its bottom lens filmed the people sitting in the room. That is why the **bottom
> half of every recorded frame is pixelated**. When you use the real camera, remember it films
> both sides: don't save or share pictures of people who did not agree.

## Step 1 — Is there a camera?

Cameras live in `/dev`. Ask for the stable names:

```bash
ls -l /dev/v4l/by-id/
```

- **Camera booked:** you see `usb-Amba_Insta360_One_R-video-index0 -> ../../video0` (and `index1`).
- **Not booked:** `No such file or directory`. Your sandbox only contains the devices you booked —
  that is how the dashboard shares one camera between a whole class.

Also try:

```bash
ls /dev/video*
```

## Step 2 — Write the four camera tools

Open [camera_tools.py](file:./camera_tools.py). Read the class `FrameSource` at the bottom first:
it opens the camera exactly like NAVERA does (`CAP_V4L2`, `MJPG`, 1920 × 1080, `BUFFERSIZE 1`), and
when the camera is missing or busy it plays the recorded frames **at the rhythm of the camera**
instead. Like `live_camera.py`, it splits reading into `grab()` (cheap, gives the grab time) and
`retrieve()` (decodes the picture).

Now the TODOs:

> [!TASK]
> In `camera_tools.py`:
> 1. `split_halves(frame)` returns `(top, bottom)`: the upper and lower halves of the picture.
>    Compute the half from `frame.shape[0]` — don't write 540, it must work for any size.
> 2. `measure_fps(grab_times)` returns `(number of times − 1) / (last time − first time)`, and `0.0`
>    when there are fewer than 2 times.
> 3. `exposure_time(grab_time_s, latency_s)` returns when the picture was really taken.
> 4. `load_latency(calib_file)` returns the `latency_s` of the calibration file as a float, `0.0` when
>    the key is missing (use `calib.get(...)`).

Test them:

```bash
python3 camera_tools.py
```

You should see the top half black (mean 0.0), the bottom white (mean 255.0), `10.0`, `99.862`
and `0.138`.

## Step 3 — Capture frames

```bash
python3 capture.py
```

The program says where its frames come from, then grabs 60 of them (about 2 seconds), decodes
**only the last one**, and saves everything in `out/`:

```
🎞️  no camera: no /dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0 (camera not booked, or unplugged)
   -> reading the recorded frames of /data/academy/19-live-camera
camera delay from the calibration file: 0.138 s
60 frames in 2.05 s -> 28.8 fps
saved out/full.jpg 1920x1080, out/top.jpg 1920x540, out/bottom.jpg 1920x540, out/stamps.csv, ...
```

Open the pictures in the editor (click them in the file list): [out/full.jpg](file:./out/full.jpg),
[out/top.jpg](file:./out/top.jpg), [out/bottom.jpg](file:./out/bottom.jpg). In `top.jpg` you see the
office through the fisheye: the edges of the screen are **curved**, the room looks stretched on the
sides. That is the 166°-wide top lens NAVERA uses.

> [!TASK]
> Run `python3 capture.py` once your four functions are done, so that `out/top.jpg`,
> `out/bottom.jpg` (1920 × 540 each), `out/stamps.csv` and `out/capture_info.json` exist.

## Step 4 — Look at the stamps

```bash
head -5 out/stamps.csv
```

```
frame,grab_time_s,exposure_time_s
0,1791366581.5235,1791366581.3855
1,1791366581.5582,1791366581.4202
...
```

The times are in seconds since 1 January 1970 (the usual computer clock). Check two things with your
own eyes: two grab times are about **0.035 s** apart (28.8 fps), and each exposure is exactly
**0.138 s** before its grab. That second column is what NAVERA uses to pick the attitude of the
picture.

> [!NOTE]
> With the recorded frames, the rhythm comes from `/data/academy/19-live-camera/grab_times.csv`.
> Be aware: those grab times are **simulated** at the 28.8 fps the camera gives — the calibration tool
> that saved these frames did not record when each one arrived. With the real camera, the rhythm is
> the camera's own.

## Step 5 — With the real camera (only if you booked it)

If step 1 showed the camera, grab 150 frames (about 5 s):

```bash
python3 capture.py 150
```

Read the frame rate. Is it 28.8? Then open `out/top.jpg` and `out/bottom.jpg`: you see both sides of
the camera, right now. Wave your hand in front of one lens and capture again.

If it prints *"the camera is there but sends nothing (busy?)"*, someone else's program is streaming
from it (one program at a time!). The recorded frames are used instead — that's fine for the lab.

## Step 6 — Run NAVERA's live camera node

Now the real thing: `camera_pkg/nodes/live_camera.py` from **your NAVERA copy**. Without the camera, we
feed it the recorded frames through a ROS topic — its `input:=ros` mode, the one a vehicle with its own
camera uses. One command starts three programs:

```bash
bash live_demo.sh
```

| Program | Role |
|---|---|
| [replay_camera.py](file:./replay_camera.py) | publishes the recorded frames (2 per second) on `/vehicle/camera/image_raw`, and a fake **level** IMU on `/navera/sensors/imu` |
| `live_camera.py` (NAVERA) | grabs, stamps (− 0.138 s), crops the top half, undistorts, straightens, publishes on `/day/...` |
| [watch_live.py](file:./watch_live.py) | receives 3 frames like day vision does, sends the "done" acknowledgement, saves the last one in `out/` |

Open [live_demo.sh](file:./live_demo.sh) to see how NAVERA's node is started:

```
ros2 run camera_pkg live_camera.py --ros-args -r __ns:=/day \
    -p input:=ros -p input_topic:=/vehicle/camera/image_raw \
    -p width:=1920 -p height:=1080 -p crop:=top \
    -p calibration_file:=/data/academy/19-live-camera/insta360_top.yaml -p wait_for_ready:=false -p fps:=1.0
```

You should see, among NAVERA's log lines:

```
[day.live_camera]: camera delay 0.138 s (from /data/academy/19-live-camera/insta360_top.yaml)
[day.live_camera]: live camera: input=ros 1920x1080, lens calibrated (fisheye), published field of view 110.9 deg ...
frame 0: usable=True straightened=True tilt=0.0 deg  heading=0.0 deg  field of view=110.944 deg  attitude=imu
...
camera message stamped 1791366585.259 s -> exposure stamp 1791366585.121 s : 0.138 s earlier
saved out/live_view.jpg (1920x540) and out/live_meta.json
```

NAVERA found the delay in the calibration file by itself, and moved every stamp 0.138 s back.
(A heading of `360.0` is the same direction as `0.0`: north.)

Now compare [out/top.jpg](file:./out/top.jpg) (the raw top lens) with
[out/live_view.jpg](file:./out/live_view.jpg) (what NAVERA publishes): the curved edges of the screen are
**straight** now, and the picture is 111° wide instead of 166°. Then read the description:

```bash
cat out/live_meta.json
```

Find `image_stamp_ns` (the exposure stamp, in nanoseconds), `camera_hfov_deg`, `tilt_deg`,
`straightened`, `attitude_source`, and `altitude_m: null` — no height source is running, so a real
day vision would not know the scale of this frame yet (lesson 17).

> [!TASK]
> Run `bash live_demo.sh` so that `out/live_meta.json` (straightened, 111° wide, attitude from the IMU)
> and `out/live_view.jpg` (1920 × 540) exist.

## Step 7 — Tilt the vehicle

`replay_camera.py` can pretend the vehicle is tilted. Nose 15° up:

```bash
bash live_demo.sh --pitch 15
```

The meta now says `tilt=15.0 deg`, and `out/live_view.jpg` is **warped**: NAVERA turned the picture into
the view of a level camera looking straight down (here the camera really looks at a wall, so the result
looks strange — on a drone looking at the ground, it makes the picture match the map).

Run the level version again before checking, so your saved files are the straight ones:

```bash
bash live_demo.sh
```

## Step 8 — Quiz

Open [answers.py](file:./answers.py) and answer the four questions.

> [!TASK]
> Answer Q1–Q4 in `answers.py`. The course tab has everything you need.

Press **✔ Check my work**.

## Going further (optional)

- **Too tilted.** Run `bash live_demo.sh --pitch 60`. What do `usable` and the reason say? Which setting
  of NAVERA decides the limit? (Look for `max_tilt_deg` in `live_camera.py`.) Run `bash live_demo.sh`
  again afterwards.
- **What does decoding cost?** Time the decoding of one recorded JPEG frame and compare with the 51 ms
  measured on the box (our file was re-saved as JPEG for this lab, so its size is not exactly what the camera sends):

  ```bash
  python3 -c "import cv2, numpy as np, time; b = np.fromfile('/data/academy/19-live-camera/frames/frame_000.jpg', np.uint8); t = time.time(); [cv2.imdecode(b, 1) for _ in range(20)]; print(len(b) // 1000, 'kB, decode', round((time.time() - t) / 20 * 1000, 1), 'ms')"
  ```

  How many processor-seconds per second would decoding all 28.8 frames cost?
- **A frozen IMU.** In `replay_camera.py`, the IMU adds a tiny noise to every sample. Find in
  `live_camera.py` (`_on_imu`) what NAVERA does when 50 samples in a row are *exactly* the same, and why
  a real sensor never does that.
