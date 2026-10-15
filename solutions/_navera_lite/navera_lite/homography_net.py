"""navera_lite/homography_net.py — a small convolutional network that LEARNS to align a night (thermal-like) frame
with a day reference image: training pairs made from scenes with an exact truth, the 4-point output, the network,
its training, and the helpers that turn its output into a homography and a position. HomographyNet-style (DeTone,
Malisiewicz & Rabinovich, 2016), made small. Part of NAVERA Lite, the course's teaching stack (mission 25).
Written for the course; it is not NAVERA code.

Patch coordinates. A patch is P × P pixels (P = PATCH_PX); as everywhere in the course, a pixel's coordinates are
those of its CENTRE, so the patch's four corners are, in this order, the centres of its corner pixels:
    top-left (0, 0), top-right (P − 1, 0), bottom-right (P − 1, P − 1), bottom-left (0, P − 1)
(x to the right, y down), and its centre point is ((P − 1)/2, (P − 1)/2). A pair is two patches stacked as channels:
pair[0] = the REFERENCE patch (day aerial view, north-up, at the reference's metres per pixel), pair[1] = the THERMAL
patch (the prepared night frame).
The 4-point label: offsets = 8 numbers (x0, y0, x1, y1, x2, y2, x3, y3): corner k of the thermal patch lies at
corner k of the square + (xk, yk) in the reference patch, in reference pixels. All zeros = perfectly aligned.
The network predicts offsets / RHO_PX (numbers of about ±1); weights are saved as a state_dict and loaded with
weights_only=True: a weights file holds numbers only, never code.
"""
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# @part 25
PATCH_PX = 64          # the side of the network's input patches, pixels (≈ 496 m of ground at ≈ 7.75 m/px)
# @part 25
RHO_PX = 16.0          # the largest corner offset the training pairs contain; the network outputs offsets / RHO_PX
# @part 25
SHIFT_PX = 12.0        # training pairs: the common shift of the 4 corners (the prior's error), ± pixels
# @part 25
JITTER_PX = 4.0        # training pairs: each corner moves on its own by ± pixels (heading, height, tilt errors)
# @part 25
SQUARE = np.float32([[0, 0], [PATCH_PX - 1, 0], [PATCH_PX - 1, PATCH_PX - 1], [0, PATCH_PX - 1]])   # the 4 corners


# ====================================================================== making training pairs (session 2)

# @part 25
def thermal_camera(temp, rng, noise=1.0):
    """What a small uncooled thermal camera makes of a 'temperature' picture (0–255 = cold–hot): sensor noise
    (standard deviation `noise` grey levels), a faint column pattern (each column of the sensor reads a little
    differently), then automatic gain (AGC): the 1st–99th percentile of the picture is stretched to 0–255, so the
    absolute temperature is lost and only the contrast stays. Returns uint8 of the same shape.
    Example: thermal_camera(np.full((4, 4), 100, np.uint8), np.random.default_rng(0)).dtype → dtype('uint8')
    """
    # from mission 25 — finished: read it, use it, do not change it
    t = np.asarray(temp, np.float32)
    t = t + rng.normal(0.0, noise, t.shape) + rng.normal(0.0, 0.5 * noise, (1, t.shape[1]))
    lo, hi = np.percentile(t, (1, 99))
    g = (t - lo) / max(hi - lo, 1e-3) * 255.0
    return np.clip(g, 0, 255).astype(np.uint8)


# @part 25 todo 7
def cut_pair(ref_scene, thermal_scene, corner_xy, offsets):
    """Cut ONE training pair from a scene, with an exact truth. The reference patch is the PATCH_PX square of
    ref_scene whose top-left pixel is at corner_xy = (x0, y0) (pixel centres; x0, y0 may have decimals). The thermal frame's 4 corners lie at that square's
    corners + offsets (in scene pixels, order and meaning: see the top of this file); the thermal patch is the
    picture inside those 4 corners of thermal_scene, warped onto a PATCH_PX square (corner k → SQUARE[k]).

    Inputs: ref_scene, thermal_scene (S, S) uint8, aligned (the same ground at the same pixel); corner_xy two
    numbers; offsets 8 numbers or a (4, 2) array. Returns (ref_patch, thermal_patch): two (PATCH_PX, PATCH_PX)
    uint8 arrays.
    Example: with offsets all 0 both patches are the plain crops scene[y0:y0 + 64, x0:x0 + 64]; with every
             offset (x, y) = (5, 0) the thermal patch is the crop 5 pixels further RIGHT, scene[y0:y0 + 64, x0 + 5:x0 + 69]
    """
    x0, y0 = float(corner_xy[0]), float(corner_xy[1])
    sq = SQUARE + np.float32([x0, y0])
    quad = sq + np.asarray(offsets, np.float32).reshape(4, 2)
    h_ref = cv2.getPerspectiveTransform(sq.astype(np.float32), SQUARE)
    h_th = cv2.getPerspectiveTransform(quad.astype(np.float32), SQUARE)
    a = cv2.warpPerspective(np.asarray(ref_scene, np.uint8), h_ref, (PATCH_PX, PATCH_PX), flags=cv2.INTER_LINEAR)
    b = cv2.warpPerspective(np.asarray(thermal_scene, np.uint8), h_th, (PATCH_PX, PATCH_PX), flags=cv2.INTER_LINEAR)
    return a, b


# @part 25
def random_pair(ref_scene, thermal_scene, rng, shift_px=SHIFT_PX, jitter_px=JITTER_PX, noise=1.0):
    """One random training pair from a scene: a random square position (far enough from the edges), random offsets
    (a common shift ±shift_px plus ±jitter_px per corner), YOUR cut_pair, then thermal_camera on the thermal patch.
    Returns (pair, offsets): pair (2, PATCH_PX, PATCH_PX) uint8 [reference, thermal], offsets (8,) float32 pixels.
    Example: random_pair(np.zeros((160, 160), np.uint8), np.zeros((160, 160), np.uint8), np.random.default_rng(0))[0].shape
             → (2, 64, 64)
    """
    # from mission 25 — finished: read it, use it, do not change it
    s = np.asarray(ref_scene).shape[0]
    margin = shift_px + jitter_px
    x0, y0 = rng.uniform(margin, s - PATCH_PX - margin, 2)
    off = rng.uniform(-shift_px, shift_px, (1, 2)) + rng.uniform(-jitter_px, jitter_px, (4, 2))
    a, b = cut_pair(ref_scene, thermal_scene, (x0, y0), off)
    return np.stack([np.asarray(a, np.uint8), thermal_camera(b, rng, noise)]), off.reshape(8).astype(np.float32)


# @part 25
def make_pairs(ref_scenes, thermal_scenes, n, seed=0, augment=True, noise=1.0, shift_px=SHIFT_PX,
               jitter_px=JITTER_PX):
    """n random pairs from a set of scenes, scene after scene (pair i comes from scene i % len(scenes)).
    augment: also turn each scene by a random multiple of 90° and mirror it half of the time (the same for both
    pictures) — more variety from the same ground. Returns (pairs (n, 2, P, P) uint8, offsets (n, 8) float32).
    Example: make_pairs(np.zeros((3, 160, 160), np.uint8), np.zeros((3, 160, 160), np.uint8), 5)[0].shape → (5, 2, 64, 64)
    """
    # from mission 25 — finished: read it, use it, do not change it
    rng = np.random.default_rng(seed)
    xs = np.zeros((n, 2, PATCH_PX, PATCH_PX), np.uint8)
    ys = np.zeros((n, 8), np.float32)
    for i in range(n):
        a, b = ref_scenes[i % len(ref_scenes)], thermal_scenes[i % len(thermal_scenes)]
        if augment:
            k = int(rng.integers(4))
            a, b = np.rot90(a, k), np.rot90(b, k)
            if rng.integers(2):
                a, b = a[:, ::-1], b[:, ::-1]
            a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
        xs[i], ys[i] = random_pair(a, b, rng, shift_px, jitter_px, noise)
    return xs, ys


# ====================================================================== the network

# @part 25 todo 8
def to_input(pairs, device="cpu"):
    """uint8 pairs (N, 2, P, P) (numpy or tensor) → the network's input: a float32 tensor of the same shape on
    `device`, where EACH channel of EACH pair is shifted and scaled on its own: (x − its mean) / (its std + 1.0),
    with torch's .std() (its default). The + 1.0 (one grey level) keeps a uniform patch (calm sea) at 0 instead of
    blowing its noise up. Use torch operations (the runner calls it on GPU batches).
    Example: to_input(np.array([[[[0, 2], [4, 6]], [[9, 9], [9, 9]]]], np.uint8))
             → tensor([[[[-0.8375, -0.2792], [0.2792, 0.8375]], [[0., 0.], [0., 0.]]]])
    """
    x = pairs if torch.is_tensor(pairs) else torch.as_tensor(np.asarray(pairs))
    x = x.to(device).float()
    m = x.mean(dim=(2, 3), keepdim=True)
    s = x.std(dim=(2, 3), keepdim=True)
    return (x - m) / (s + 1.0)


# @part 25 todo 9
class HomographyNet(nn.Module):
    """A small CNN: one pair (2, 64, 64) in, the 4-point offsets / RHO_PX out (8 numbers). Layers, with these
    attribute NAMES (the check and Sim Lite load your weights into them):

        layer   kind                          channels in → out    then
        conv1   3 × 3 convolution, size kept   2 → 16             ReLU, 2 × 2 max-pooling   → (16, 32, 32)
        conv2   3 × 3 convolution, size kept   16 → 32            ReLU, 2 × 2 max-pooling
        conv3   3 × 3 convolution, size kept   32 → 64            ReLU, 2 × 2 max-pooling
        conv4   3 × 3 convolution, size kept   64 → 64            ReLU, 2 × 2 max-pooling   → (64, ?, ?)
        fc1     linear, on the flattened maps  ? → 128            ReLU        (? = every number conv4's block gives)
        fc2     linear                         128 → 8            nothing: offsets can be negative

    "Size kept": the convolution must not shrink the 64 × 64 picture (which nn.Conv2d argument does that?).

    forward(x): x a float tensor (N, 2, 64, 64) from to_input; returns (N, 8). 192 600 parameters.
    Example: HomographyNet()(torch.zeros(3, 2, 64, 64)).shape → torch.Size([3, 8])
    """

    def __init__(self):
        """Create the six layers of the table above, with those names (call super().__init__() first).

        Example: sum(p.numel() for p in HomographyNet().parameters()) → 192600
        """
        super().__init__()
        self.conv1 = nn.Conv2d(2, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
        self.conv4 = nn.Conv2d(64, 64, 3, padding=1)
        self.fc1 = nn.Linear(64 * 4 * 4, 128)
        self.fc2 = nn.Linear(128, 8)

    def forward(self, x):
        """The 4-point output of a batch: (N, 2, 64, 64) → (N, 8) (the table above, in order).

        Example: HomographyNet()(torch.zeros(1, 2, 64, 64)) → a tensor of shape (1, 8) (small random numbers)
        """
        for conv in (self.conv1, self.conv2, self.conv3, self.conv4):
            x = F.max_pool2d(F.relu(conv(x)), 2)
        return self.fc2(F.relu(self.fc1(x.flatten(1))))


# @part 25 todo 10
def offsets_to_H(offsets, side=PATCH_PX):
    """The 3 × 3 homography that sends a point of the THERMAL patch to the REFERENCE patch, from the 4-point
    offsets (8 numbers or (4, 2), pixels): corner k of the square goes to corner k + its offset. Four point pairs
    fix the 8 unknowns of H (mission 18); OpenCV's getPerspectiveTransform solves them (float32 points).

    Returns a numpy (3, 3) float64 array with H[2, 2] = 1.
    Example: offsets_to_H([2, -1] * 4) → [[1, 0, 2], [0, 1, -1], [0, 0, 1]]   (every corner moved 2 right, 1 up)
    """
    e = side - 1
    sq = np.float32([[0, 0], [e, 0], [e, e], [0, e]])
    quad = sq + np.asarray(offsets, np.float32).reshape(4, 2)
    return cv2.getPerspectiveTransform(sq, quad.astype(np.float32)).astype(np.float64)


# @part 25
def centre_shift(H, side=PATCH_PX):
    """Where the ground point under the thermal patch's centre point ((side − 1)/2, (side − 1)/2) lands in the
    reference patch, minus
    the reference patch's centre: (dx, dy) in pixels (dx > 0: east of the reference centre, dy > 0: SOUTH, for
    north-up patches). This is the position the night fix reports, relative to the prior.
    Example: centre_shift(np.array([[1.0, 0, 2], [0, 1, -1], [0, 0, 1]])) → (2.0, -1.0)
    """
    # from mission 25 — finished: read it, use it, do not change it
    m = (side - 1) / 2.0
    c = np.asarray(H, np.float64) @ np.array([m, m, 1.0])
    return float(c[0] / c[2] - m), float(c[1] / c[2] - m)


# @part 25 todo 11
def train(model, train_x, train_y, val_x, val_y, epochs=15, lr=1e-3, batch=128, seed=0, device="cpu", log=None):
    """Train `model` to predict the 4-point offsets: the loss is the mean squared error between model(input) and
    offsets / RHO_PX, with the Adam optimiser; after every epoch, measure the same loss on the validation pairs
    WITHOUT learning from them.

    Inputs: train_x, val_x uint8 (N, 2, P, P) tensors on the CPU (move each BATCH to `device` with your to_input:
    the whole set may not fit on a shared GPU); train_y, val_y float32 (N, 8) tensors, pixels, on the CPU. epochs
    passes over the training pairs in a new random order each time (torch.Generator seeded with `seed`), batches of
    `batch` pairs (the last, smaller one too); learning rate lr. log: None, or a function called as log(row) after
    each epoch.
    Returns the history: one dict per epoch {"epoch": 1, 2, …, "train_loss": mean of the epoch's batch losses,
    "val_loss": the validation loss (batches of `batch`, averaged)} — floats.
    Example: 512 training and 128 validation pairs, epochs=3 → 3 dicts whose "train_loss" usually goes down from
             about 0.21 (the loss of always answering 0, lesson §8), e.g. [{"epoch": 1, "train_loss": 0.21, "val_loss": 0.19}, …]
    """
    g = torch.Generator().manual_seed(int(seed))
    torch.manual_seed(int(seed))
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    history = []
    n = len(train_x)
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(n, generator=g)
        losses = []
        for start in range(0, n, batch):
            idx = order[start:start + batch]
            pred = model(to_input(train_x[idx], device))
            loss = F.mse_loss(pred, train_y[idx].to(device) / RHO_PX)
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            vl = [F.mse_loss(model(to_input(val_x[s:s + batch], device)), val_y[s:s + batch].to(device) / RHO_PX).item()
                  for s in range(0, len(val_x), batch)]
        row = {"epoch": epoch, "train_loss": float(np.mean(losses)), "val_loss": float(np.mean(vl))}
        history.append(row)
        if log is not None:
            log(row)
    return history


# ====================================================================== using a trained network (given)

# @part 25
def predict(model, pairs, device="cpu", batch=256):
    """The predicted offsets, in pixels: numpy float32 (N, 8), computed without gradients.
    Example: predict(HomographyNet(), np.zeros((3, 2, 64, 64), np.uint8)).shape → (3, 8)
    """
    # from mission 25 — finished: read it, use it, do not change it
    model.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(pairs), batch):
            out.append((model(to_input(pairs[s:s + batch], device)) * RHO_PX).cpu().numpy())
    return np.concatenate(out).astype(np.float32) if out else np.zeros((0, 8), np.float32)


# @part 25
def corner_error(pred, truth):
    """The mean distance, in pixels, between the 4 predicted and the 4 true corners of each pair: (N,) float array.
    Example: corner_error(np.zeros((1, 8)), np.array([[3, 4] * 4])) → array([5.])
    """
    # from mission 25 — finished: read it, use it, do not change it
    d = (np.asarray(pred, np.float64) - np.asarray(truth, np.float64)).reshape(-1, 4, 2)
    return np.linalg.norm(d, axis=2).mean(axis=1)


# @part 25
def centre_error(pred, truth, side=PATCH_PX):
    """The distance, in pixels, between the predicted and the true ground point under the thermal patch's centre
    (what a position fix needs): (N,) float array, through offsets_to_H and centre_shift.
    Example: centre_error(np.zeros((1, 8)), np.array([[3, 4] * 4])) → array([5.])
    """
    # from mission 25 — finished: read it, use it, do not change it
    out = []
    for p, t in zip(np.asarray(pred), np.asarray(truth)):
        a = centre_shift(offsets_to_H(p, side), side)
        b = centre_shift(offsets_to_H(t, side), side)
        out.append(np.hypot(a[0] - b[0], a[1] - b[1]))
    return np.array(out)


# @part 25
def load_weights(path, device="cpu"):
    """A HomographyNet with the weights saved at `path` (torch.save(model.state_dict(), path)), read safely
    (weights_only=True: numbers only) and STRICTLY: every layer must find its weights, or this raises. (Loading
    with strict=False silently keeps random weights for the layers whose names do not match: lesson §9.)
    Example: load_weights("my_homography.pt") → HomographyNet(...) ready for predict()
    """
    # from mission 25 — finished: read it, use it, do not change it
    model = HomographyNet()
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    return model.to(device).eval()
