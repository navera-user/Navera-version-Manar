# Lab 19 — Timing a live camera

**Goal:** write the timing tools of a live camera: frame statistics, the camera delay from a
flash bench, and the attitude at the exposure with slerp. Check that your attitude function
matches NAVERA's own code, measure a live GStreamer source, run NAVERA's `live_camera.py` on
recorded Insta360 frames, and write a short technical report.
**Time:** about 3 h for this lab (about 3 h 45 for the whole mission with the lesson).

**What is graded:** `camera_tools.py` (8 functions), `results.json` (made by `analyse.py`), the
files in `out/`, and `report.md`.

> [!NOTE]
> **Camera or no camera?** The camera is shared by the class and by NAVERA's engineers. This lab
> does **not** need it. Every program uses **recorded frames** of the Insta360
> (`/data/academy/19-live-camera/`) when the camera is not booked, absent, or busy. The programs
> check `fuser` first and never open a busy camera. The camera check is skipped when no camera
> was used.
>
> **How to book the camera** (optional): in the dashboard, press the **Hardware** button at the
> top, then **Take** on the line **Insta360 camera**. Then open a **new terminal**: only terminals
> opened after the booking can see the camera. When you finish, open the **Hardware** menu again and
> press **Release** on the same line.
> If you do not book it, you do not need it: follow the no-camera path.

> [!WARNING]
> **Privacy.** The recorded frames were saved while the top lens looked at a calibration board
> and the bottom lens filmed people in the room. That is why the **bottom half of every recorded
> frame is pixelated**. If you use the real camera, remember that it films both sides: do not
> save or share pictures of people who did not agree.

The data of this lab:

| File in `/data/academy/19-live-camera/` | Real or synthetic | What |
|---|---|---|
| `frames/frame_*.jpg`, `insta360_top.yaml` | **real** (NAVERA bench) | 30 Insta360 frames, the top lens calibration with `latency_s: 0.138` |
| `grab_log.csv` | synthetic | 60 s of grab times at nominal 28.8 fps: jitter, drops, one stall |
| `grab_times.csv` | synthetic | the replay rhythm of the 30 recorded frames (28.8 fps + 2 ms jitter) |
| `flashes.csv`, `flash_frames.csv` | synthetic | a simulated flash bench (screen delay 20 ms, latency 105 ms — **chosen values, not the Insta360's**) |
| `turn_imu.csv`, `turn_frames.csv` | synthetic | a drone turning 150 m above a coastline: IMU at 50 Hz with an 0.8 s dropout, frames with the **true** attitude at each exposure |

The synthetic files have an exact ground truth, so you can measure the error of each
method. NAVERA's real flight data and test map cover Sousse, Tunisia, where NAVERA is
developed. The turning flight here is simulated.

## Step 1 — Find the camera (or see that it is not yours)

```bash
ls -l /dev/v4l/by-id/
```

- **Camera booked:** you see `usb-Amba_Insta360_One_R-video-index0 -> ../../video0`.
- **Not booked:** `No such file or directory`. Your sandbox contains only the devices you booked.

If the camera is there, check whether another program is using it before you do anything else:

```bash
fuser /dev/video0 /dev/video1
```

No output means that it is free. A process number means that it is busy: do not open it.

> [!NOTE]
> **No camera?** Then `fuser` prints `Specified filename /dev/video0 does not exist.` (and the
> same for `/dev/video1`). This is normal: it only means that your sandbox has no camera. Go on to
> Step 2.

## Step 2 — Part A: frames, statistics and the stamp (TODO 1–4)

Open [camera_tools.py](file:./camera_tools.py). Read the conventions at the top and the class
`FrameSource` at the bottom. `FrameSource` opens the camera exactly like NAVERA does (`CAP_V4L2`,
`MJPG`, 1920 × 1080, `BUFFERSIZE 1`), or replays the recorded frames at the camera's rhythm.

> [!TASK]
> In `camera_tools.py`, write:
> 1. `split_halves(frame)` → `(top, bottom)`. Compute the half from `frame.shape[0]` (do not write 540).
> 2. `frame_stats(grab_times)` → a dict with exactly the keys `n, fps, period_ms, median_ms,
>    jitter_ms, max_gap_ms, dropped` as defined in its docstring and in lesson section 5.
>    For fewer than 2 times, return zeros.
> 3. `exposure_time(grab_time_s, latency_s)`.
> 4. `load_latency(calib_file)` → `latency_s` as a float, `0.0` when the key is missing.

Test them:

```bash
python3 camera_tools.py
```

Lines 1–4 must show the expected values written next to them. The worked example of the lesson
(`[0, .1, .2, .4, .5]`) must give `fps 8.0`, `median_ms 100.0`, `jitter_ms 43.3`, `dropped 1`.

> [!TIP]
> Common errors: `np.std` of a Python list works, but `d.std()` needs a numpy array; the times
> are in **seconds** and the dict wants **milliseconds** (× 1000); `round()` returns an int in
> Python 3, which is what `dropped` needs.

## Step 3 — Capture frames

```bash
python3 capture.py
```

The program says where its frames come from. It grabs 60 frames (about 2 s), decodes **only the
last one**, and writes `out/`:

```
🎞️  no camera: no /dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0 (camera not booked, or unplugged)
   -> replaying the recorded frames of /data/academy/19-live-camera
camera delay from the calibration file: 0.138 s
60 frames: 28.8 fps, median period 34.7 ms, jitter ...
```

Open [out/top.jpg](file:./out/top.jpg) and [out/bottom.jpg](file:./out/bottom.jpg). The top half is
the fisheye view that NAVERA uses: straight edges look **curved**. Then look at the stamps:

```bash
head -4 out/stamps.csv
```

Each `exposure_time_s` must be exactly 0.138 s before its `grab_time_s`.

> [!NOTE]
> In replay mode the rhythm comes from `grab_times.csv` (synthetic, 28.8 fps). The sleeping of the
> replay adds the jitter of your sandbox, so your fps is close to, but not exactly, 28.8.

## Step 4 — MJPG and GStreamer, live

An MJPG stream is just a sequence of independent JPEG files. Make one with GStreamer from a
live test source at 28.8 fps (`framerate=144/5`):

```bash
mkdir -p out/mjpg && gst-launch-1.0 -q videotestsrc num-buffers=58 pattern=ball ! video/x-raw,width=960,height=540,framerate=144/5 ! jpegenc quality=85 ! multifilesink location=out/mjpg/frame_%03d.jpg
```

```bash
ls -l out/mjpg | head -5
```

Each frame is a JPEG of about 15 kB. A raw 960 × 540 BGR frame is 1.5 MB. You can open
`out/mjpg/frame_000.jpg` in the editor.

> [!NOTE]
> GStreamer may print `(Argus) Error FileOperationFailed ...`. It looks for the daemon of the
> Jetson's CSI cameras, which does not run in your sandbox. You can ignore this message.

Now measure frame timing on a live source with **NAVERA's own `GstCapture` class**. The script
uses your `frame_stats()`:

```bash
python3 gst_timing.py
```

Then simulate a slow consumer that needs 50 ms of processing per frame:

```bash
python3 gst_timing.py --work-ms 50
```

Compare the two runs. Without work you should measure about 28.8 fps with a jitter of a few
ms. With 50 ms of work the rate falls to about 19–20 fps, and the script reports how many
source frames were **never grabbed**. The appsink (`drop=true max-buffers=1`) threw away the old
frames and always gave you the newest one. This is exactly what NAVERA wants. Look also at
`dropped` from your `frame_stats()`. Why is it 0 in the second run? (Hint: what is the median
interval now?)

## Step 5 — Part B: the delay (TODO 5)

Read section 6 of the lesson and look at the figure of the flash bench again.

> [!TASK]
> Write `latency_from_flashes(flash_times, frame_times, brightness)` as specified in its docstring.
> It follows the method of `navera_tools/bench/camera_latency.py`: a "black" level before
> each flash, a "white" level after it, and the first frame above the midpoint.

```bash
python3 camera_tools.py
```

Line 5 must print `[0.15...]`. The check also tests a half-lit frame (brightness below the
midpoint) and a flash that the camera never sees, which you must skip.

## Step 6 — Part C: the attitude at the exposure (TODO 6–8)

> [!TASK]
> Write, with quaternions as numpy arrays **(w, x, y, z)**:
> 6. `quat_angle_deg(q0, q1)`: the angle between two attitudes, in degrees (lesson section 8).
> 7. `slerp(q0, q1, f)` with the three practical rules of lesson section 8.
>    You wrote it in lesson 16 (`quaternions.py`). Write it again here, so this file is complete.
> 8. `attitude_at(t, imu_times, imu_quats, max_gap_s=0.2)` with **NAVERA's rules** (docstring,
>    and "When there is no sample" in section 8).

```bash
python3 camera_tools.py
```

Lines 6–8 must give 30.0, the yaw-45° quaternion `[0.924 0 0 0.383]` and the yaw-10° quaternion.
Now compare your `attitude_at()` with NAVERA's `History.at()` on the whole turn
(663 exposures):

```bash
python3 compare_with_navera.py
```

Read [compare_with_navera.py](file:./compare_with_navera.py): it converts each sample to NAVERA's
**(x, y, z, w)** order before giving it to `History.add`. You must get
`✔ your attitude_at() gives NAVERA's attitude at every exposure`, with
`"frames_compared": 651` and `"both_unusable": 12`: 651 = 663 − 12, because the 12 exposures in
the IMU gap have no attitude on both sides, so there is nothing to compare. A difference of about 1e-6° is only rounding in `acos`.

## Step 7 — The experiment: analyse.py

```bash
python3 analyse.py
```

Read [analyse.py](file:./analyse.py) while it runs. It is the experiment:

1. `frame_stats()` on the 60 s grab log.
2. `latency_from_flashes()` on the simulated bench: median, min, max, standard deviation, and
   the frame period.
3. For each frame of the turn, three ways to choose the attitude, each compared with the truth:
   - `latest_at_grab`: the last IMU sample received before the grab (a naive program),
   - `nearest_at_exposure`: the sample nearest to tₑ = t_g − 0.138 s,
   - `slerp_at_exposure`: your `attitude_at(tₑ)`.

   The errors are turned into metres at 150 m with H·tan(δθ).
4. Your GStreamer runs, and the time to decode one recorded 1080p JPEG on this machine.

It writes `results.json` and three plots. Open [out/attitude_error.png](file:./out/attitude_error.png),
[out/jitter.png](file:./out/jitter.png) and [out/latency.png](file:./out/latency.png).

> [!QUESTION]
> In `attitude_error.png`, the red points (latest at grab) peak at about 4–5.5 s and 15–16.5 s.
> What does the drone do then? Use δθ ≈ ω·δt to check the size of the peak. Why does slerp have
> its largest errors just before and after the gap at 17–17.8 s?

## Step 8 — NAVERA's live camera node

Now run the real node, `camera_pkg/nodes/live_camera.py` from your NAVERA copy. Without the
camera we feed it the recorded frames through a ROS topic, its `input:=ros` mode. A vehicle with
its own camera uses the same mode. One command starts three programs:

```bash
bash live_demo.sh
```

| Program | Role |
|---|---|
| [replay_camera.py](file:./replay_camera.py) | publishes the recorded frames (2 per second) on `/vehicle/camera/image_raw` and a simulated IMU at 50 Hz on `/navera/sensors/imu` |
| `live_camera.py` (NAVERA) | stamps (− 0.138 s), crops the top half, interpolates the attitude, undistorts, straightens, publishes `/day/...` |
| [watch_live.py](file:./watch_live.py) | receives 3 frames like day vision does, sends the `frame_done` acknowledgement, saves the last one in `out/` |

You should see NAVERA's log `camera delay 0.138 s (from .../insta360_top.yaml)`, three lines
`frame N: usable=True straightened=True tilt=0.0 deg ...` and
`camera message stamped ... -> exposure stamp ... : 0.138 s earlier`. (A heading of 360.0 is
north, the same as 0.0.) Compare [out/top.jpg](file:./out/top.jpg) (raw fisheye) with
[out/live_view.jpg](file:./out/live_view.jpg) (what NAVERA publishes: undistorted, 111° wide).

```bash
cat out/live_meta.json
```

Find `image_stamp_ns`, `source_stamp_ns`, `tilt_deg`, `rate_dps`, `camera_hfov_deg` and
`attitude_source`.

Now make the vehicle turn at 40 °/s:

```bash
bash live_demo.sh --turn-rate 40
```

Every frame is now `usable=False`, with the reason `vehicle turning 40 deg/s at the exposure (max 30)`.
For a fixed camera NAVERA refuses frames taken during fast rotations. Your error analysis shows
why: at 40 °/s, even a 25 ms timing error is 1°. Finally run the level version again, so that
your saved files are the usable ones that the check reads:

```bash
bash live_demo.sh
```

> [!TASK]
> `out/live_meta.json` must describe a **usable, straightened** frame, 111° wide, with an IMU
> attitude, and `out/live_view.jpg` must be 1920 × 540.

## Step 9 — The report

> [!TASK]
> Complete [report.md](file:./report.md): keep its four sections (`## Frame timing`,
> `## Camera delay`, `## Attitude at the exposure`, `## Recommendation`), replace every TODO, and
> write at least 250 words. Quote numbers from `results.json` with units. The check looks for
> these numbers: the grab-log **fps** (2 decimals), the **median delay** of the bench (ms or s), the
> **median ground error of `latest_at_grab`** (m), and **your own GStreamer fps** without work.

If you run `gst_timing.py` again later, run `analyse.py` again and update the fps in your
report.

## Step 10 — With the real camera (only if you booked it and it is free)

If step 1 showed the camera and `fuser` showed no process, grab 150 frames (about 5 s):

```bash
python3 capture.py 150
```

Is the frame rate 28.8? What are the jitter and the time of `retrieve()` (the MJPG decode)?
Write these numbers in your report. If the program says that the camera is used by another
program, it replays the recorded frames instead. That is fine for the lab.

Press **✔ Check my work**.

## Going further (optional)

- **Robust jitter.** Add `p99_ms` and a robust spread to `frame_stats()`:
  MAD = median(|dᵢ − m|) × 1.4826. Compare MAD and σ on `grab_log.csv`. Which one would you use to
  set an alarm for a "stuttering camera"?
- **How many flashes?** Draw 5, 10 and 20 flashes at random from the bench (many times) and plot
  the spread of the median. Is the √N rule of the lesson right? What would you change in
  `camera_latency.py` to estimate L + s and not L + s + T/2?
- **Clock offset from data.** The camera and the IMU may use different clocks. Shift the IMU
  times of `turn_imu.csv` by −50…+50 ms, and for each shift compute the median slerp error against
  the truth. The minimum gives the offset. On a real drone, without truth, the same search can
  compare the image rotation measured by vision (lessons 21–23) with the gyroscope.
- **Decode cost.** `results.json` contains `mjpg_decode_ms` measured in your sandbox. How many CPU
  cores would decoding every frame at 28.8 fps use? Compare with the 51 ms that NAVERA's engineers
  measured on the box.
