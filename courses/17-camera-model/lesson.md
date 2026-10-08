# The camera as a measuring instrument

> [!NOTE] In short
> - A camera is a point in the air that looks along **rays**: the **pinhole model** and the
>   **intrinsic matrix K** turn a 3D point into a pixel.
> - You will learn to go back from a pixel to the ground, and to find the **footprint** of a tilted camera.
> - You will compute how many metres one pixel covers (**GSD**) and which map zoom fits the photo.
> - You will see how a height error becomes a **scale** error, and a tilt error becomes a position error.
> - In the lab you build these functions, compare them with NAVERA's code, and measure a landing pad in drone photos.

A survey drone flies at 300 m over a coastal city. Its GPS is jammed. The
camera under the drone takes a photo of roads, trees and roofs, and NAVERA must find this
photo on its satellite map. Before any image matching can start, NAVERA needs to answer three
geometric questions:

1. **Which ground point does each pixel show?** The camera is not a picture frame laid on the
   map: it is a point in the air that looks along rays.
2. **How many metres of ground does one pixel cover?** The map has a fixed resolution per zoom
   level; the photo's resolution depends on the height. If the two do not agree, nothing matches.
3. **How wrong can these answers be?** The height is never known exactly, and the drone is never
   perfectly level.

This lesson gives you the mathematical model that answers all three: the **pinhole camera** with
its **intrinsic matrix K** and its **pose (R, C)**. You will project 3D points into the image,
shoot rays from pixels back to the ground, compute the **footprint** of a tilted camera, and see
how an error in height becomes an error in **scale**. Distortion of real lenses (fisheye) is the
topic of lesson 18; here the camera is ideal.

## 1. Three coordinate frames

A **coordinate frame** is an origin plus three perpendicular axes. We need three of them; NAVERA
uses exactly these conventions (`navera_common/camera_model.py`):

| Frame | Axes | Used for |
|---|---|---|
| **world (ENU)** | x = east, y = north, z = up, in metres. In this lesson the origin is **on the ground under the drone**, so the ground is the plane z = 0 | positions on the ground |
| **body (FLU)** | x = forward (nose), y = left, z = up | the drone's attitude (lesson 16) |
| **camera (OpenCV)** | x = image right, y = image **down**, z = **optical axis** (where the camera looks) | pixels |

The **camera centre** C is the position of the pinhole in the world: for a drone at height h,
C = (0, 0, h). The **orientation** is a rotation matrix **R_wc** ("world from camera"): it turns a
vector written in camera axes into the same vector written in world axes:

```
v_world = R_wc · v_cam          v_cam = R_wcᵀ · v_world        (R⁻¹ = Rᵀ for a rotation, lesson 16)
```

The columns of R_wc are the camera axes written in world coordinates. Example: a camera looking
straight down from a drone whose nose points north. The image right is east, the image down is
**south**, the optical axis is **down**:

```
         x_cam  y_cam  z_cam
R_wc = [  1      0      0  ]     (east)
       [  0     -1      0  ]     (north)
       [  0      0     -1  ]     (up)
```

In the lab, `camera_rotation(heading, pitch, roll)` builds R_wc for any attitude with lesson 16's
angles (heading clockwise from north, pitch positive nose up, roll positive right wing down):
R_wc = Rz(90° − heading) · Ry(−pitch) · Rx(roll) · R_body→camera. It is NAVERA's own formula.

## 2. The pinhole model and the intrinsic matrix K

![Pinhole projection: the image point divides X and Y by the depth Z](assets/pinhole.svg)

In the camera frame a 3D point has coordinates X_c = (X, Y, Z), where Z is its **depth** along
the optical axis. All light rays pass through the camera centre, and the image plane is at a
distance **f** in front of it. By similar triangles, the point appears at

```
u = fx · X / Z + cx
v = fy · Y / Z + cy
```

- **fx, fy** — the **focal length in pixels** (horizontal and vertical). For square pixels fx = fy = f.
- **(cx, cy)** — the **principal point**, the pixel where the optical axis meets the image; for an
  ideal camera it is the image centre (w/2, h/2).
- The division by Z is the **perspective division**: far objects look smaller.

Engineers write this as one matrix product with **homogeneous coordinates** (a pixel (u, v) is
written [u, v, 1] and is defined up to a scale factor λ):

```
λ · [u, v, 1]ᵀ = K · X_c ,        K = [ fx   s   cx ]
                                      [  0   fy  cy ]
                                      [  0   0    1 ]
```

**K** is the **intrinsic matrix**: it contains only properties of the camera (s is the **skew**,
0 for every modern sensor). Combining with the pose gives the full **projection**:

```
X_c = R_wcᵀ · (X_world − C)            (world → camera: the extrinsics)
λ · [u, v, 1]ᵀ = K · X_c                (camera → pixel: the intrinsics)
```

Often this is written λ·x = K [R | t] X with R = R_wcᵀ and t = −R_wcᵀ C: it is the same thing.
If Z ≤ 0 the point is **behind** the camera and has no image.

### Field of view

The **horizontal field of view** (HFOV) is the angle between the rays of the left and right image
edges. The right half of the image (w/2 pixels) is seen under HFOV/2, so

```
tan(HFOV / 2) = (w / 2) / f        ⇔        f = (w / 2) / tan(HFOV / 2)
VFOV = 2 · atan((h / 2) / f)       (the same f, the image height h in pixels)
```

| Camera | Size (px) | HFOV | f (px) | VFOV |
|---|---|---|---|---|
| the lab's synthetic camera | 960 × 540 | 90° | 480 | 58.7° |
| NAVERA's Insta360 top lens, straightened | 1920 × 540 | 111° | 659.8 | 44.5° |
| a narrow zoom camera | 1920 × 1080 | 30° | 3583 | 17.2° |

> [!NOTE]
> The second line is NAVERA's real camera. The top lens of the Insta360 ONE R was calibrated on
> the bench (lesson 18) with **fx ≈ 660 px**. NAVERA straightens its picture into an ideal pinhole
> view of 1920 × 540 px, 111° wide: 2·atan(960 / 660) ≈ 111°. A wider straight view would stretch
> the edges and lose detail in the centre — lesson 18 explains this trade-off.

> [!WARNING]
> Python's `math.tan()` and numpy's `np.tan()` take **radians**: `math.tan(math.radians(45))` is
> 1.0, but `math.tan(45)` is 1.62. This is the most frequent bug in this lab.

### Worked example 1 — projecting a ground point

The lab camera (K with f = 480, cx = 480, cy = 270) looks straight down from h = 150 m, nose
north. Where does the ground point X = (30, 45, 0) — 30 m east, 45 m north — appear?

```
X − C   = (30, 45, −150)
X_c     = R_wcᵀ (X − C) = (30, −45, 150)       (x = east, y = south, z = down: depth 150 m)
u       = 480 · 30 / 150 + 480 = 576
v       = 480 · (−45) / 150 + 270 = 126
```

The point is right of the centre (east) and above it (north): the image top points north.

## 3. Back-projection: from a pixel to the ground

The opposite question — *which ground point does pixel (u, v) show?* — is what NAVERA needs to
place a photo on the map. A single pixel does not give a 3D point, only a **ray** (the depth is
lost). The ray leaves C in the direction

```
d = R_wc · K⁻¹ · [u, v, 1]ᵀ          (direction in the world frame)
X(λ) = C + λ · d,   λ > 0
```

To find where it hits the **ground plane** z = 0, solve C_z + λ · d_z = 0:

```
λ = −C_z / d_z = −h / d_z          valid only if d_z < 0 (the ray goes down)
X_ground = C + λ · d
```

If d_z ≥ 0 the ray goes to the horizon or the sky and never touches the ground. This is a
**ray–plane intersection**; for a general plane n·X = c, λ = (c − n·C) / (n·d). We assume flat
ground; over mountains that is a strong assumption (a digital elevation model would
be needed).

![A nose-down drone: the down-looking camera sees the ground behind it](assets/tilt.svg)

### Worked example 2 — a tilted camera

The drone flies north at h = 150 m and pitches **nose down 20°** to accelerate. The camera is fixed
to the body, so its optical axis also rotates by 20° — and because the nose goes down, the belly
(and the camera) turns **backwards**. For the image centre, K⁻¹[480, 270, 1]ᵀ = (0, 0, 1) and

```
d = R_wc · (0, 0, 1) = (0, −sin 20°, −cos 20°) = (0, −0.342, −0.940)
λ = −150 / −0.940 = 159.6 m                 (the slant range)
X_ground = (0, 0, 150) + 159.6 · d = (0, −54.6, 0)
```

The image centre shows the ground **54.6 m behind** the drone (h · tan 20°). If NAVERA matched this
photo and said "the drone is at the image centre", it would be 55 m wrong. Many people guess
"in front" — draw it once and you will not forget.

## 4. The footprint

The **footprint** is the part of the ground the image covers: back-project the four image corners
and join them.

**Nadir camera** (looking straight down): the footprint is a rectangle

```
W = 2 h tan(HFOV/2)        H = 2 h tan(VFOV/2)        area = W · H
```

The lab camera at 150 m covers 300 m × 168.75 m = 50 625 m². The Insta360 view at 150 m covers
436.5 m × 122.8 m.

**Tilted camera**: the footprint becomes a **trapezoid**. In the plane of the tilt θ, the near and
far edges are at h·tan(θ − VFOV/2) and h·tan(θ + VFOV/2) from the point under the drone; in the
example above, 25 m **ahead** and 175 m **behind**. The far side is much wider than the near side
because it is further away (perspective). When θ + VFOV/2 reaches 90°, the far edge looks at the
horizon and the footprint is infinite. The area of any polygon with vertices (x_i, y_i) is given
by the **shoelace formula**:

```
A = ½ · | Σ_i ( x_i · y_(i+1) − x_(i+1) · y_i ) |       (indices modulo N)
```

| Pitch (nose down), h = 150 m, lab camera | 0° | −10° | −20° | −30° |
|---|---|---|---|---|
| image centre behind the drone (m) | 0 | 26.4 | 54.6 | 86.6 |
| footprint area (m²) | 50 625 | 54 063 | 66 466 | 97 405 |

You will draw these four footprints in the lab.

## 5. Ground sampling distance (GSD)

The **ground sampling distance** is the ground size of one pixel. For a nadir camera:

```
GSD = W / w = 2 h tan(HFOV/2) / w = h / f          (metres per pixel)
```

The Insta360 view at 150 m: 150 / 659.8 = **0.227 m/px** (a 4.5 m car is about 20 px long). The
GSD is **proportional to the height**: twice as high, half the detail.

For a tilted camera the GSD changes across the image. At the image centre the slant range is
h / cos θ; a pixel there covers h / (f cos θ) across the tilt direction and h / (f cos² θ) along it
(the ground is seen at a grazing angle). At 150 m and θ = 20°: 0.333 m and 0.354 m instead of 0.3125 m.
This non-uniform scale is one more reason why NAVERA **straightens** tilted frames into the view of
a level nadir camera before matching (see *In NAVERA* below).

## 6. Matching the map's zoom level

NAVERA's map is a **Web Mercator** tile pyramid (lesson 07): 256 × 256 px tiles, and at zoom z the
whole world is 256 · 2^z pixels wide **along every parallel**. A parallel at latitude φ is shorter
than the equator by cos φ, so

```
map_mpp(φ, z) = 40 075 016.7 · cos φ / (256 · 2^z)       (metres per pixel)
```

| zoom | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|
| Singapore (1.3° N) | 4.78 | 2.39 | 1.19 | 0.597 | 0.299 |
| Sousse (35.8° N) | 3.87 | 1.94 | 0.968 | 0.484 | 0.242 |
| Reykjavik (64.2° N) | 2.08 | 1.04 | 0.521 | 0.260 | 0.130 |

The same zoom level is **coarse near the equator and fine near the poles**: a zoom-17 pixel covers
1.19 m in Singapore but only 0.52 m in Reykjavik. NAVERA's test map covers Sousse, Tunisia (where
NAVERA is developed), so the lab photos come from there; the formulas are the same for a map of
any other place.

To compare a photo with the map, both must have the same metres per pixel. NAVERA keeps the map
and **resizes the photo** by

```
s = GSD_photo / map_mpp        (s < 1: the photo is shrunk)
```

The **best zoom** for a given height is the one closest in **ratio** — minimise |log(map_mpp / GSD)|,
because a map twice too fine and a map twice too coarse are equally bad. Equivalently,
z* ≈ log₂(40 075 016.7 · cos φ / (256 · GSD)), rounded. At 300 m the Insta360 GSD is 0.455 m/px:
zoom 18 in Singapore (0.597) and in Sousse (0.484), but zoom 17 in Reykjavik (0.521). The height at
which the photo has exactly the zoom-17 resolution is h = f · map_mpp: 788 m over Singapore, 639 m
over Sousse, 344 m over Reykjavik.

## 7. Uncertainty: from height error to scale error

Everything above needs h, the height **above the ground** (AGL). It is never exact. Since GSD ∝ h,

```
s_true / s_assumed = h_true / h_assumed         ⇒        δs / s = δh / h
```

A 10 % height error is a 10 % scale error. Feature matching tolerates only a limited scale
difference, and NAVERA uses the scale as a **sanity check**: a match is fitted with a
rotation + scale + translation, and the fitted scale must be 1 ± 15 % (the scale the height
predicts). A wrong place almost never matches at the right scale. In NAVERA's validation document,
on 33 labelled replay frames around Sousse, adding this scale check took the wrong accepted
matches from 1 to 0 (measured on replay data, not in flight).

The check also works backwards: if the match is right, the fitted scale **measures the height**:
h_true = h_assumed · s. A fitted scale of 1.2 at an assumed 150 m means the drone was at 180 m.

How large is δh in practice? NAVERA's `altitude.py` ranks the sources: a **rangefinder** (laser,
best), then the height measured by earlier matches, then a reference altitude minus the ground
height at take-off (barometer or GPS), whose uncertainty grows with height because the terrain
changes. When the height is uncertain, NAVERA widens the gate to 2·σh/h, at most 35 %.

**A mountain example.** A drone takes off in a mountain valley, for example in the Alps (ground
about 500 m above sea level), climbs to 2 300 m GPS altitude and flies over a high plateau (ground
about 2 000 m). "GPS
altitude − take-off ground" says 1 800 m AGL; the truth is 300 m. The photo shows 6 times less
ground than predicted: the matcher would need a scale of 0.17, far outside any gate. Only a
rangefinder, a terrain model or a height measured from the image can save this flight.

Attitude errors matter too. The image centre lands h·tan θ from the point under the drone, so an
error δθ moves it by about h·δθ/cos²θ: at 150 m and θ = 10°, **1° of attitude error is 2.7 m**
on the ground. Lesson 16's IMU accuracy limits the position accuracy.

## 8. 🐦 How birds do it

From high above a coastal lagoon such as the Camargue in France, a flock of flamingos sees
kilometres of mudflat; low over the water, a tern sees a few square metres — but every small fish in them. That is this lesson's rule
for any eye: **footprint and detail trade against each other**, and the trade is set by height.

Birds of prey push the detail. Their retina has a deep central **fovea** packed with
photoreceptors (many raptors have a second, shallower one for looking sideways), and the best
eagles resolve detail roughly twice as fine as a person. Golden eagles, from the Alps to the
Rocky Mountains, scan the ground from great heights and still spot small prey: like a camera with a long focal
length in the middle of a wide field of view.

The **common kestrel**, seen from Europe to Africa and Asia, solves the other problem of this lesson — the pose.
When it **hovers** into the wind, its wings and tail work constantly, but its **head stays almost
perfectly still** in space. A fixed viewpoint means a stable projection: any small movement in the
image is the prey, not the bird. NAVERA cannot hold its camera still, so it measures the pose with
the IMU and computes the projection instead. Navi, our swallow, does not hover; she trusts her
fast eyes and keeps low — a small GSD.

## In NAVERA

The formulas of this lesson are in your NAVERA copy, almost word for word.

[navera_common/camera_model.py](file:navera/navera_common/navera_common/camera_model.py) builds K for
an ideal lens and the camera rotation from the attitude:

```python
    @classmethod
    def ideal(cls, hfov_deg: float, size: Tuple[int, int]) -> "CameraModel":
        w, h = int(size[0]), int(size[1])
        f = (w / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        return cls([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1]], [], (w, h), "pinhole", hfov_deg)

def camera_rotation(q_body_enu, mount_rpy_deg=(0.0, 0.0, 0.0)) -> np.ndarray:
    R_wb = quat_to_matrix(q_body_enu)
    R_mount = rpy_to_matrix(*(math.radians(float(a)) for a in mount_rpy_deg))
    return R_wb @ R_mount @ R_BODY_NADIR_CAM

def tilt_deg(R_world_cam: np.ndarray) -> float:
    """Angle between the optical axis and straight down (deg)."""
    z = R_world_cam @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.acos(max(-1.0, min(1.0, -z[2]))))

def ground_m_per_px(altitude_agl_m: float, hfov_deg: float, width_px: int) -> float:
    return 2.0 * altitude_agl_m * math.tan(math.radians(hfov_deg) / 2.0) / width_px

def altitude_from_scale(predicted_altitude_m: float, fitted_scale: float) -> float:
    return predicted_altitude_m * fitted_scale
```

The same file has `nadir_homography(K, R)`: x_virt ~ K · R_virt←cam · K⁻¹ · x_cam, the image
transform that turns a tilted frame into the view of a level nadir camera at the same place, so
that **the image centre is the point under the drone**. In the lab you will verify this with your
own `project()`. [navera_common/frame_builder.py](file:navera/navera_common/navera_common/frame_builder.py)
applies it to every live frame and refuses frames tilted more than `max_tilt_deg` (45° by default).

[day_pkg/local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py), the day-vision matcher:

```python
def map_m_per_px(lat: float, z: int) -> float:
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0
...
        mpp_map = map_m_per_px(prior[0], self.z)
        s = frame_m_per_px / mpp_map                     # frame pixels → map pixels
        if not (math.isfinite(s) and 0.02 < s < 50):
            res.update(error=f"frame scale {s:.3f} of the map resolution is not plausible")
...
        scale = math.hypot(A[0, 0], A[1, 0])              # 1.0 when the altitude/FOV prediction is right
...
        elif abs(scale - 1.0) > tol:
            res["reason"] = (f"fitted scale {scale:.2f} ≠ 1 expected from the altitude (±{tol:.0%}): "
                             "wrong place")
```

Its `locate_any_height()` handles a completely unknown height: it tries heights from 30 m to
1500 m, each 1.5 × the previous, with a ±30 % scale window, and returns the height measured by the
best match (h_tried × fitted scale).

[day_pkg/nodes/day_subscriber.py](file:navera/day_pkg/day_pkg/nodes/day_subscriber.py) widens the
scale gate with the height uncertainty and refuses to guess the GSD:

```python
    def _scale_tol(self, meta):
        tol = self.local.scale_tol
        rel = 2.0 * float(meta.get("altitude_sigma_m")) / float(meta.get("altitude_m"))
        if math.isfinite(rel):
            tol = min(max(tol, rel), self.local_scale_tol_max)     # 0.15 ... 0.35
    ...
    def _frame_m_per_px(self, img, meta):
        if not math.isfinite(hfov) or not 1.0 < hfov < 179.0:
            return None, "camera_hfov_deg unknown"
        if not (math.isfinite(alt) and alt > 5.0):
            return None, "frame altitude unknown or on the ground"
        return LocalMatcher.frame_m_per_px(img.shape[1], alt, hfov), None
```

(Excerpts are shortened; open the files to read the full code.)

## Glossary

| Term | Meaning |
|---|---|
| **coordinate frame** | an origin and three perpendicular axes (world ENU, body FLU, camera OpenCV) |
| **camera centre C** | the position of the pinhole in the world |
| **R_wc** | rotation matrix from camera axes to world axes; R_wcᵀ goes back |
| **extrinsics** | the pose of the camera (R, C or R, t) |
| **intrinsic matrix K** | the 3×3 matrix with fx, fy, cx, cy (and skew s) |
| **focal length in pixels (f)** | distance from the pinhole to the image plane, measured in pixels |
| **principal point (cx, cy)** | the pixel where the optical axis crosses the image |
| **homogeneous coordinates** | [u, v, 1], defined up to a scale factor λ |
| **perspective division** | dividing by the depth Z: far things look small |
| **back-projection** | from a pixel to the ray of 3D points that project there |
| **ray–plane intersection** | the point where a ray meets a plane: λ = −h / d_z for the ground |
| **field of view (HFOV, VFOV)** | the angle seen across the image width / height |
| **footprint** | the ground area covered by the image |
| **GSD** | ground sampling distance: metres of ground per pixel (h / f at nadir) |
| **nadir** | the direction straight down |
| **AGL** | above ground level: height above the ground below, not above the sea |
| **scale gate** | NAVERA's rule that a match's fitted scale must be 1 ± tolerance |

## Check what you learned

<details><summary>1. A camera has HFOV 60° on 1280 px. What is f? What is its VFOV if the image is 720 px high?</summary>
f = 640 / tan 30° = 1108.5 px. VFOV = 2·atan(360 / 1108.5) = 2 · 18.0° = <b>36.0°</b>.
</details>

<details><summary>2. With f = 480, cx = 480, cy = 270, a point in camera coordinates X_c = (−20, 10, 200). Which pixel?</summary>
u = 480·(−20)/200 + 480 = <b>432</b>, v = 480·10/200 + 270 = <b>294</b>.
</details>

<details><summary>3. A ray from C = (0, 0, 120) has world direction d = (0.2, 0.1, −0.8). Where does it hit the ground?</summary>
λ = −120 / −0.8 = 150; X = (0 + 150·0.2, 0 + 150·0.1, 0) = <b>(30 m east, 15 m north)</b>.
</details>

<details><summary>4. A drone flying east pitches nose down 15° at 200 m. Where is the ground point at the image centre?</summary>
Behind the drone: 200 · tan 15° ≈ <b>54 m west</b> of the point under the drone (the belly turns backwards).
</details>

<details><summary>5. Which zoom matches the Insta360 view (f = 659.8 px) at 600 m over Reykjavik?</summary>
GSD = 600 / 659.8 = 0.909 m/px. Zoom 16 is 1.041 m/px (ratio 1.15), zoom 17 is 0.521 (ratio 0.57):
|log 1.15| = 0.14 < |log 0.57| = 0.56, so <b>zoom 16</b> (over Sousse it would be zoom 17).
</details>

<details><summary>6. NAVERA assumes 250 m, the fitted scale is 0.92 and the gate is 15 %. Accepted? What height does it measure?</summary>
|0.92 − 1| = 0.08 ≤ 0.15: <b>accepted</b>. Measured height = 250 · 0.92 = <b>230 m</b>.
</details>

Now open the **🛠️ Lab** tab.
