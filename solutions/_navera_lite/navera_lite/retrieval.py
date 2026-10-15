"""navera_lite/retrieval.py — global retrieval: turn a whole map view into one vector (an EMBEDDING) and find the
map tiles whose vectors are the closest. Two embedders: DINOv2 ViT-S/14, a network pretrained by Meta AI (used as
it is), and TileNet, a small network you train yourself on views you generate from the map.
Part of NAVERA Lite, the course's teaching stack (mission 23). Written for the course; it is not NAVERA code.

Conventions: pictures are numpy uint8 (H, W, 3) in OpenCV's BLUE, GREEN, RED order. A "view" is a north-up square
of VIEW_PX × VIEW_PX pixels at the map's scale (zoom ZOOM), centred on the photo's centre: the same size and scale
as one map tile, so a view and a tile can be compared. Embeddings are numpy float32 rows of length 1 (unit vectors).
DINOv2 (Apache-2.0) is third-party data: its code and weights are mounted read-only in /data/models/dinov2.
Map data © OpenStreetMap contributors.
"""
import hashlib
import os
import sqlite3

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from navera_lite.tiles import MAP_PATH, TILE_PX, tile_to_latlon, tiles_in_circle

# @part 23
ZOOM = 17                                   # the map zoom every view and tile of this part uses (≈ 0.97 m/px)
# @part 23
VIEW_PX = TILE_PX                           # side of a view: one tile, 256 px ≈ 248 m at Sousse
# @part 23
DINO_DIR = os.environ.get("NAVERA_LITE_MODELS", "/data/models") + "/dinov2"   # DINOv2's code/ and weights
# @part 23
DINO_SIZE = 224                             # DINOv2's input side (a multiple of 14)
# @part 23
IMAGENET_MEAN = (0.485, 0.456, 0.406)       # RED, GREEN, BLUE: the mean of the pictures DINOv2 learned from (0..1)
# @part 23
IMAGENET_STD = (0.229, 0.224, 0.225)        # and their standard deviation, same order
# @part 23
SMALL_PX = 64                               # TileNet's input side: a tile shrunk 4 times (≈ 3.9 m per pixel)
# @part 23
DIM = 128                                   # TileNet's embedding length
# @part 23
TRAIN_AREA = (35.885, 35.965, 10.48, 10.62)  # (lat min, lat max, lon min, lon max): TileNet learns here (north)
# @part 23
VAL_AREA = (35.70, 35.755, 10.50, 10.70)     # validation pairs come from here (south) — never from the test area
# @part 23
TEST_AREA = (35.77, 35.87, 10.55, 10.68)     # the lab's photos and tile index (Sousse): never used for training


# ====================================================================== views (given)

# @part 23
def north_up(photo, heading_deg, gsd_photo_m, gsd_map_m, side=VIEW_PX):
    """A colour photo turned north-up and brought to the map's scale: a side × side view centred on the photo's
    centre, black (0) where the photo does not reach. heading_deg: where the photo's TOP points, clockwise from north.

    Example: north_up(np.full((480, 640, 3), 200, np.uint8), 30.0, 0.6, 0.97).shape → (256, 256, 3)
    """
    # given — read it and use it, no need to change it
    h, w = photo.shape[:2]
    M = cv2.getRotationMatrix2D(((w - 1) / 2.0, (h - 1) / 2.0), -float(heading_deg), gsd_photo_m / gsd_map_m)
    M[0, 2] += (side - 1) / 2.0 - (w - 1) / 2.0
    M[1, 2] += (side - 1) / 2.0 - (h - 1) / 2.0
    return cv2.warpAffine(photo, M, (side, side), flags=cv2.INTER_AREA)


# @part 23
def tile_centre(x, y, z=ZOOM):
    """(lat, lon) of the centre of tile (x, y) at zoom z, degrees.

    Example: tile_centre(69409, 51547) → about (35.82783, 10.63889)
    """
    # given — read it and use it, no need to change it
    return tile_to_latlon(x + 0.5, y + 0.5, z)


# ====================================================================== DINOv2 (session 1)

# @part 23 todo 1
def preprocess(views, size=DINO_SIZE):
    """DINOv2's input from OpenCV pictures. DINOv2 learned from RGB photos with values 0..1 normalised channel by
    channel with IMAGENET_MEAN and IMAGENET_STD (red, green, blue); its pictures must be size × size, with size a
    multiple of 14. So each view is resized to size × size (cv2.INTER_AREA), its channels put in RGB order, scaled
    to 0..1, normalised ((value − mean) / std, per channel), and laid out channels-first.

    views: numpy uint8 (N, H, W, 3), BGR. Returns a torch float32 tensor (N, 3, size, size) on the CPU.
    Example: preprocess(np.zeros((2, 256, 256, 3), np.uint8)).shape → torch.Size([2, 3, 224, 224]), and every value
             of channel 0 (red) is (0 − 0.485) / 0.229 ≈ −2.1179
    """
    v = np.asarray(views)
    out = np.empty((len(v), 3, size, size), np.float32)
    mean = np.array(IMAGENET_MEAN, np.float32)
    std = np.array(IMAGENET_STD, np.float32)
    for i, img in enumerate(v):
        rgb = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
        out[i] = ((rgb - mean) / std).transpose(2, 0, 1)
    return torch.from_numpy(out)


# @part 23
def load_dino(device="cpu"):
    """DINOv2 ViT-S/14 (22 million parameters), built from its local code and loaded with its pretrained weights
    (weights_only=True: numbers only), in evaluation mode on `device`. No internet needed.

    Example: load_dino()(torch.zeros(1, 3, 224, 224)).shape → torch.Size([1, 384])
    """
    # given — read it and use it, no need to change it
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                 # "xFormers is not available": fine, it is optional
        model = torch.hub.load(os.path.join(DINO_DIR, "code"), "dinov2_vits14", source="local", pretrained=False,
                               verbose=False)
    model.load_state_dict(torch.load(os.path.join(DINO_DIR, "dinov2_vits14_pretrain.pth"), map_location="cpu",
                                     weights_only=True))
    return model.to(device).eval()


# @part 23
def embed_dino(model, views, device="cpu", batch=32):
    """DINOv2 embeddings of views (N, H, W, 3) BGR uint8: numpy float32 (N, 384), each row of length 1 (the class
    token, divided by its length). Uses YOUR preprocess(); computed without gradients.

    Example: embed_dino(load_dino(), np.zeros((1, 256, 256, 3), np.uint8)).shape → (1, 384)
    """
    # given — read it and use it, no need to change it
    out = []
    with torch.no_grad():
        for s in range(0, len(views), batch):
            x = preprocess(views[s:s + batch]).to(device)
            out.append(F.normalize(model(x), dim=1).cpu().numpy())
    return np.concatenate(out).astype(np.float32) if out else np.zeros((0, 384), np.float32)


# ====================================================================== ranking (session 1)

# @part 23 todo 2
def rank(q, E):
    """Rank the rows of E by their COSINE SIMILARITY with the vector q (lesson §2): the largest similarity first.
    q: (D,) numbers; E: (M, D) numbers. Neither has to be of length 1 (a cosine divides by the lengths).

    Returns (order, sims): order = numpy int array (M,) of row indices, most similar first (equal similarities: the
    lower index first); sims = numpy float array (M,), the similarity of EVERY row, in E's own order (not sorted).
    Example: rank([1.0, 0.0], [[0.0, 2.0], [3.0, 3.0], [5.0, 0.0]]) → (array([2, 1, 0]), array([0.0, 0.7071, 1.0]))
    """
    q = np.asarray(q, dtype=float)
    E = np.asarray(E, dtype=float)
    sims = E @ q / (np.linalg.norm(E, axis=1) * np.linalg.norm(q) + 1e-12)
    return np.argsort(-sims, kind="stable"), sims


# @part 23
class TileIndex:
    """The embeddings of the map tiles of an area: xy (M, 2) int tile numbers at zoom z, emb (M, D) unit rows.
    search() is the retrieval step: the tiles whose CENTRE lies in the search circle, ranked by YOUR rank().

    Example: TileIndex.load("/data/academy/23-locate-on-map/dino_index.npz").search(q, 35.82, 10.62, 600.0, 3)
             → [(69403, 51552, 35.8186, 10.6214, 0.83), …]   (x, y, lat, lon, similarity), best first
    """
    # given — read it and use it, no need to change it

    def __init__(self, xy, emb, z=ZOOM):
        self.xy = np.asarray(xy, dtype=np.int64)
        self.emb = np.asarray(emb, dtype=np.float32)
        self.z = int(z)
        self.row = {(int(x), int(y)): i for i, (x, y) in enumerate(self.xy)}

    @classmethod
    def load(cls, path):
        d = np.load(path)
        return cls(d["xy"], d["emb"], int(d["z"]))

    def candidates(self, lat, lon, r_m):
        """Rows of the tiles whose centre is within r_m metres of (lat, lon) (tiles outside the index are left out)."""
        return [self.row[t] for t in tiles_in_circle(lat, lon, r_m, self.z) if t in self.row]

    def search(self, q, lat, lon, r_m, k=None):
        rows = self.candidates(lat, lon, r_m)
        if not rows:
            return []
        order, sims = rank(q, self.emb[rows])
        out = []
        for j in list(order)[:k]:
            x, y = (int(v) for v in self.xy[rows[int(j)]])
            c_lat, c_lon = tile_centre(x, y, self.z)
            out.append((x, y, c_lat, c_lon, float(sims[int(j)])))
        return out


# ====================================================================== TileNet (session 1, part 2)

# @part 23
def tile_tensor(imgs, device="cpu"):
    """TileNet's input: uint8 pictures (N, SMALL_PX, SMALL_PX, 3) BGR → float32 tensor (N, 3, SMALL_PX, SMALL_PX),
    each picture shifted and scaled to mean 0 and standard deviation 1 (over its three channels together), so a
    darker or paler photo of the same place gives the same input.

    Example: tile_tensor(np.zeros((5, 64, 64, 3), np.uint8)).shape → torch.Size([5, 3, 64, 64])   (all zeros)
    """
    # given — read it and use it, no need to change it
    x = torch.as_tensor(np.asarray(imgs).astype(np.float32)).permute(0, 3, 1, 2)
    x = x - x.mean(dim=(1, 2, 3), keepdim=True)
    x = x / (x.std(dim=(1, 2, 3), keepdim=True) + 1e-3)
    return x.contiguous().to(device)


# @part 23 todo 4
class TileNet(nn.Module):
    """A small CNN that turns a whole 64 × 64 colour view into one embedding of DIM = 128 numbers of length 1.
    The rule (derive every size from it; the check and Sim Lite load your weights into these NAMES):

        four blocks conv1, conv2, conv3, conv4. One block = a 3 × 3 nn.Conv2d that keeps the width and height
            (padding=1), then ReLU, then 2 × 2 max-pooling (half the width, half the height).
            conv1 turns the 3 colour maps into 32 maps; each next block DOUBLES the number of maps until it
            reaches DIM (the embedding's length), and from then on keeps it (halve the size, double the maps:
            each block then costs about the same).
        then the MEAN of each of the last block's maps over its width and height (global average pooling: one
            number per map, wherever in the view a road or a block was seen),
        fc = one nn.Linear from those numbers to DIM, then each output row is divided by its length.

    forward(x): x is a float tensor (N, 3, 64, 64) (from tile_tensor); returns a tensor (N, DIM), rows of length 1.
    Example: TileNet()(torch.zeros(2, 3, 64, 64)).shape → torch.Size([2, 128]), and each row has length 1.0
    """

    def __init__(self):
        """Create the five layers of the rule above, with those names (call super().__init__() first).

        Example: [name for name, _ in TileNet().named_children()] → ['conv1', 'conv2', 'conv3', 'conv4', 'fc']
        """
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=1)
        self.conv4 = nn.Conv2d(128, 128, 3, padding=1)
        self.fc = nn.Linear(128, DIM)

    def forward(self, x):
        """The embeddings of a batch: (N, 3, 64, 64) → (N, DIM), each row of length 1 (the rule above, in order).

        Example: TileNet()(torch.zeros(2, 3, 64, 64)).norm(dim=1) → tensor([1., 1.])
        """
        for conv in (self.conv1, self.conv2, self.conv3, self.conv4):
            x = F.max_pool2d(F.relu(conv(x)), 2)
        x = x.mean(dim=(2, 3))
        return F.normalize(self.fc(x), dim=1)


# @part 23 todo 5
def info_nce(za, zp, tau=0.1):
    """The contrastive loss InfoNCE (lesson §6). za[i] (a map tile) and zp[i] (a view of a place inside that tile)
    belong together; every zp[j], j ≠ i, is another place. For each i, the similarities za[i]·zp[j] of ALL j are
    divided by the temperature tau and turned into probabilities with a softmax over j; the loss of i is
    −log(the probability of j = i). The loss is the mean over i.

    Inputs: za, zp float tensors (B, D), rows of length 1, B ≥ 2. Returns a tensor with one number that keeps its
    gradient (torch operations only: no .item(), no numpy, no loop over i needed).
    Example: za = torch.tensor([[1.0, 0.0], [0.0, 1.0]]); zp = torch.tensor([[0.8, 0.6], [0.6, 0.8]])
             info_nce(za, zp, tau=0.5) → tensor(0.5130)   (each tile: −log(e^1.6 / (e^1.6 + e^1.2)))
    """
    logits = za @ zp.T / tau
    return F.cross_entropy(logits, torch.arange(len(za), device=za.device))


# ====================================================================== training data (given)

# @part 23
class SmallTiles:
    """The tiles of the course map at zoom ZOOM, read from the MBTiles file and shrunk to SMALL_PX × SMALL_PX
    (INTER_AREA), kept in memory once read (about 12 kB each). tile(x, y) → uint8 (64, 64, 3) BGR; a tile missing
    from the map is grey (40). mosaic(x, y) → the 3 × 3 tiles around (x, y), uint8 (192, 192, 3).

    Example: SmallTiles().tile(69409, 51547).shape → (64, 64, 3)
    """
    # given — read it and use it, no need to change it

    def __init__(self, path=None, z=ZOOM):
        self.path = path or MAP_PATH
        self.z = int(z)
        self.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.cache = {}

    def tile(self, x, y):
        key = (int(x), int(y))
        if key not in self.cache:
            row = self.db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                                  (self.z, key[0], 2 ** self.z - 1 - key[1])).fetchone()
            img = cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR) if row else None
            if img is None:
                img = np.full((TILE_PX, TILE_PX, 3), 40, np.uint8)
            self.cache[key] = cv2.resize(img, (SMALL_PX, SMALL_PX), interpolation=cv2.INTER_AREA)
        return self.cache[key]

    def mosaic(self, x, y):
        return np.vstack([np.hstack([self.tile(x + i, y + j) for i in (-1, 0, 1)]) for j in (-1, 0, 1)])


# @part 23
def area_tiles(area, z=ZOOM):
    """Every tile (x, y) at zoom z of an area (lat min, lat max, lon min, lon max), row by row from the north-west.

    Example: len(area_tiles(TEST_AREA)) → 2208
    """
    # given — read it and use it, no need to change it
    from navera_lite.tiles import tile_xy
    x0, y1 = (int(v) for v in tile_xy(area[0], area[2], z))
    x1, y0 = (int(v) for v in tile_xy(area[1], area[3], z))
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


# @part 23
def _photometric(img, rng):
    """Camera-like changes of a small view: brightness, colour cast, gamma, blur, a cloud, sensor noise."""
    out = img.astype(np.float32) * rng.uniform(0.75, 1.15) + rng.normal(0, 8, 3)
    out = 255.0 * np.clip(out / 255.0, 0, 1) ** rng.uniform(0.8, 1.25)
    if rng.uniform() < 0.5:
        out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.3, 0.8))
    if rng.uniform() < 0.3:
        m = np.zeros((SMALL_PX, SMALL_PX), np.float32)
        cv2.circle(m, (int(rng.uniform(0, SMALL_PX)), int(rng.uniform(0, SMALL_PX))), int(rng.uniform(6, 16)), 1, -1)
        m = cv2.GaussianBlur(m, (0, 0), 3) * rng.uniform(0.4, 0.9)
        out = out * (1 - m[:, :, None]) + 255.0 * m[:, :, None]
    out += rng.normal(0, rng.uniform(0, 5), out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


# @part 23
def _footprint(img, rng):
    """Black outside a turned rectangle the size of a photo's footprint (what north_up leaves), sometimes a dark
    blob (a propeller or a leg in the picture)."""
    w = rng.uniform(75, 125)
    box = cv2.boxPoints((((SMALL_PX - 1) / 2, (SMALL_PX - 1) / 2), (w, 0.75 * w), rng.uniform(0, 180)))
    m = np.zeros((SMALL_PX, SMALL_PX), np.uint8)
    cv2.fillConvexPoly(m, box.astype(np.int32), 1)
    img = img * m[:, :, None]
    if rng.uniform() < 0.3:
        cv2.circle(img, (int(rng.uniform(0, SMALL_PX)), int(rng.uniform(0, SMALL_PX))), int(rng.uniform(5, 12)),
                   (20, 20, 20), -1)
    return img


# @part 23
def make_pairs(tiles_src, area, n, seed=0, augment=True, shift=0.5, min_std=3.0):
    """Training pairs made from the map (no photo needed): anchors[i] = one map tile, views[i] = a view of a place
    INSIDE that tile, as the drone would see it. Both uint8 (n, SMALL_PX, SMALL_PX, 3) BGR.

    The view is centred on a random point up to `shift` tiles from the tile's centre in x and in y (0.5 = anywhere
    in the tile, as a real photo is); with augment=True it is also turned by up to ±6° (heading error), scaled by
    ±8 % (height error), given camera effects (light, colour, blur, a cloud, noise) and a photo footprint (black
    corners). Tiles that are almost uniform (grey standard deviation below min_std: sea, empty land) are skipped:
    they look all alike, so they cannot teach which place is which. Same seed → same pairs.
    Example: a, v = make_pairs(SmallTiles(), TRAIN_AREA, 4); a.shape → (4, 64, 64, 3)
    """
    # given — read it and use it, no need to change it
    rng = np.random.default_rng(seed)
    keep = [t for t in area_tiles(area, tiles_src.z)
            if cv2.cvtColor(tiles_src.tile(*t), cv2.COLOR_BGR2GRAY).std() >= min_std]
    S = SMALL_PX
    anchors = np.zeros((n, S, S, 3), np.uint8)
    views = np.zeros_like(anchors)
    for i in range(n):
        x, y = keep[rng.integers(len(keep))]
        mos = tiles_src.mosaic(x, y)
        anchors[i] = mos[S:2 * S, S:2 * S]
        cx, cy = S + (S - 1) / 2 + rng.uniform(-shift, shift) * S, S + (S - 1) / 2 + rng.uniform(-shift, shift) * S
        turn, scale = (rng.uniform(-6, 6), rng.uniform(0.92, 1.08)) if augment else (0.0, 1.0)
        M = cv2.getRotationMatrix2D((cx, cy), turn, scale)
        M[0, 2] += (S - 1) / 2 - cx
        M[1, 2] += (S - 1) / 2 - cy
        v = cv2.warpAffine(mos, M, (S, S), flags=cv2.INTER_LINEAR)
        views[i] = _footprint(_photometric(v, rng), rng) if augment else v
    return anchors, views


# @part 23
def train_tilenet(model, train_a, train_v, val_a, val_v, epochs=12, lr=1e-3, batch=64, tau=0.1, seed=0,
                  device="cpu", log=None):
    """Train `model` with YOUR info_nce and Adam on the pairs (train_a[i], train_v[i]); after each epoch, the loss on
    the validation pairs (no learning) and the validation recall: the share of validation views whose own tile is
    the nearest of 256 tiles. Inputs are the uint8 pictures of make_pairs (kept on the CPU as they are: 8 000 pairs
    take 197 MB; each batch is turned into tensors by tile_tensor on `device`).
    Returns the history: one dict per epoch {"epoch", "train_loss", "val_loss", "val_recall"} (floats).

    Example: train_tilenet(TileNet(), a, v, va, vv, epochs=2) → [{"epoch": 1, "train_loss": 4.1, …}, {…}]
    """
    # given — read it and use it, no need to change it (it is mission 21's training loop, with InfoNCE)
    g = torch.Generator().manual_seed(int(seed))
    torch.manual_seed(int(seed))
    model.to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(train_a), generator=g)
        losses = []
        for start in range(0, len(train_a), batch):
            idx = order[start:start + batch]
            if len(idx) < 2:
                continue
            idx = idx.numpy()
            loss = info_nce(model(tile_tensor(train_a[idx], device)), model(tile_tensor(train_v[idx], device)), tau)
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            vl = [info_nce(model(tile_tensor(val_a[s:s + batch], device)), model(tile_tensor(val_v[s:s + batch], device)),
                           tau).item() for s in range(0, len(val_a), batch) if len(val_a[s:s + batch]) >= 2]
            za = torch.cat([model(tile_tensor(val_a[s:min(s + batch, 256)], device)) for s in range(0, 256, batch)])
            zv = torch.cat([model(tile_tensor(val_v[s:min(s + batch, 256)], device)) for s in range(0, 256, batch)])
            recall = (torch.argmax(zv @ za.T, dim=1) == torch.arange(len(za), device=device)).float().mean().item()
        row = {"epoch": epoch, "train_loss": float(np.mean(losses)), "val_loss": float(np.mean(vl)),
               "val_recall": float(recall)}
        history.append(row)
        if log is not None:
            log(row)
    return history


# @part 23
def embed_tilenet(model, imgs, device="cpu", batch=64):
    """TileNet embeddings of pictures (N, H, W, 3) BGR uint8 of any size (shrunk to 64 × 64 with INTER_AREA first):
    numpy float32 (N, DIM), rows of length 1, computed without gradients.

    Example: embed_tilenet(TileNet(), np.zeros((3, 256, 256, 3), np.uint8)).shape → (3, 128)
    """
    # given — read it and use it, no need to change it
    model.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(imgs), batch):
            small = np.stack([im if im.shape[0] == SMALL_PX else
                              cv2.resize(im, (SMALL_PX, SMALL_PX), interpolation=cv2.INTER_AREA)
                              for im in imgs[s:s + batch]])
            out.append(model(tile_tensor(small, device)).cpu().numpy())
    return np.concatenate(out).astype(np.float32) if out else np.zeros((0, DIM), np.float32)


# @part 23
def load_tilenet(path, device="cpu"):
    """A TileNet with the weights saved at `path` (torch.save(model.state_dict(), path)), read safely
    (weights_only=True: numbers only). Raises if the file does not fit TileNet's layers.

    Example: load_tilenet("my_tiles.pt") → TileNet(...) ready for embed_tilenet()
    """
    # given — read it and use it, no need to change it
    model = TileNet()
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    return model.to(device).eval()


# @part 23
def tilenet_index(model, tiles_src, xy, device="cpu"):
    """A TileIndex of the tiles xy embedded with a TileNet (the tiles read through tiles_src, a SmallTiles).

    Example: tilenet_index(load_tilenet("my_tiles.pt"), SmallTiles(), area_tiles(TEST_AREA)).emb.shape → (2208, 128)
    """
    # given — read it and use it, no need to change it
    imgs = np.stack([tiles_src.tile(x, y) for x, y in xy])
    return TileIndex(xy, embed_tilenet(model, imgs, device), tiles_src.z)


# @part 23
def sha256(path):
    """The SHA-256 fingerprint of a file (hex string): two files with the same fingerprint have the same bytes."""
    # given — read it and use it, no need to change it
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
