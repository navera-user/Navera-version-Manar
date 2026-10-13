"""navera_lite/learned_desc.py — a small convolutional network that LEARNS a patch descriptor (PyTorch): the model,
the triplet loss, the training loop, and the helpers that turn patches into tensors and descriptors.
Part of NAVERA Lite, the course's teaching stack (mission 21). Written for the course; it is not NAVERA code.

A patch is a small grey square cut around a keypoint, uint8, PATCH_PX × PATCH_PX (the data set stores 48 × 48:
the network sees its central 32 × 32). A descriptor is DIM numbers of length 1 (a unit vector): two patches of the
same ground point should give close descriptors (small Euclidean distance), two different points far ones.
Weights are saved as a state_dict (torch.save(model.state_dict(), path)) and loaded with weights_only=True:
a weights file holds numbers only, never code.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

PATCH_PX = 32          # the network's input side, pixels
DIM = 64               # the descriptor's length


# ====================================================================== tensors (given)

# @part 21
def to_tensor(patches, device="cpu"):
    """uint8 patches (N, s, s), s ≥ PATCH_PX → float32 tensor (N, 1, PATCH_PX, PATCH_PX) on `device`: the central
    PATCH_PX × PATCH_PX crop of each patch, each one shifted and scaled to mean 0 and standard deviation 1 (so a
    darker or paler photo of the same place gives the same input).

    Example: to_tensor(np.zeros((5, 48, 48), np.uint8)).shape → torch.Size([5, 1, 32, 32])   (all zeros)
    """
    # from mission 21 — finished: read it, use it, do not change it
    p = np.asarray(patches)
    s = p.shape[-1]
    o = (s - PATCH_PX) // 2
    x = torch.as_tensor(p[:, o:o + PATCH_PX, o:o + PATCH_PX].astype(np.float32)).unsqueeze(1)
    x = x - x.mean(dim=(2, 3), keepdim=True)
    x = x / (x.std(dim=(2, 3), keepdim=True) + 1e-3)
    return x.to(device)


# ====================================================================== the network (session 2)

# @part 21 todo 7
class PatchNet(nn.Module):
    """A small CNN: one grey patch (1, 32, 32) in, one descriptor of DIM = 64 numbers of length 1 out.
    Layers, with these attribute NAMES (the check and missions 22–31 load your weights into them):

        conv1 = nn.Conv2d(1, 16, 3, padding=1)    then ReLU, then 2 × 2 max-pooling     → (16, 16, 16)
        conv2 = nn.Conv2d(16, 32, 3, padding=1)   then ReLU, then 2 × 2 max-pooling     → (32, 8, 8)
        conv3 = nn.Conv2d(32, 64, 3, padding=1)   then ReLU, then 2 × 2 max-pooling     → (64, 4, 4)
        fc    = nn.Linear(64 * 4 * 4, DIM)        on the flattened maps, then scale each output vector to length 1

    forward(x): x is a float tensor (N, 1, 32, 32) (from to_tensor); returns a tensor (N, DIM), every row of
    length 1. 88 896 parameters.
    Example: PatchNet()(torch.zeros(2, 1, 32, 32)).shape → torch.Size([2, 64]), and each row has length 1.0
    """

    def __init__(self):
        """Create the four layers of the table above, with those names (call super().__init__() first).

        Example: sum(p.numel() for p in PatchNet().parameters()) → 88896
        """
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
        self.fc = nn.Linear(64 * 4 * 4, DIM)

    def forward(self, x):
        """The descriptors of a batch: (N, 1, 32, 32) → (N, DIM), each row of length 1 (the table above, in order).

        Example: PatchNet()(torch.zeros(2, 1, 32, 32)).norm(dim=1) → tensor([1., 1.])
        """
        x = F.max_pool2d(F.relu(self.conv1(x)), 2)
        x = F.max_pool2d(F.relu(self.conv2(x)), 2)
        x = F.max_pool2d(F.relu(self.conv3(x)), 2)
        x = self.fc(x.flatten(1))
        return F.normalize(x, dim=1)


# @part 21 todo 8
def triplet_loss(da, dp, margin=0.5):
    """The in-batch triplet loss (lesson §8). da[i] and dp[i] describe the SAME ground point (two views); every
    dp[j], j ≠ i, is a different point. For each i, d_pos = ‖da[i] − dp[i]‖ and d_neg = the SMALLEST ‖da[i] − dp[j]‖
    over j ≠ i (the hardest impostor in the batch). The loss is the mean over i of max(0, margin + d_pos − d_neg).

    Inputs: da, dp float tensors (B, D), B ≥ 2. Returns a tensor with one number (it must keep its gradient: use
    torch operations only, no .item() and no numpy inside).
    Example: da = torch.tensor([[1.0, 0.0], [0.0, 1.0]]); dp = torch.tensor([[0.6, 0.8], [0.8, 0.6]])
             triplet_loss(da, dp) → tensor(0.7620)   (each point: 0.5 + 0.8944 − 0.6325; its impostor is closer!)
    """
    d = torch.cdist(da, dp)
    d_pos = d.diagonal()
    eye = torch.eye(len(da), dtype=torch.bool, device=da.device)
    d_neg = d.masked_fill(eye, float("inf")).min(dim=1).values
    return F.relu(margin + d_pos - d_neg).mean()


# @part 21 todo 9
def train(model, train_a, train_p, val_a, val_p, epochs=8, lr=1e-3, batch=256, seed=0, device="cpu", log=None):
    """Train `model` with your triplet_loss and the Adam optimiser on the pairs (train_a[i], train_p[i]) = two views
    of one ground point; after every epoch, measure the loss on the validation pairs WITHOUT learning from them.

    Inputs: train_a, train_p, val_a, val_p: float tensors (N, 1, 32, 32) (to_tensor), already on `device`; epochs
    passes over the training pairs, in a new random order each time (torch.Generator seeded with `seed`), in batches
    of `batch` pairs (the last, smaller batch too if it has ≥ 2 pairs); learning rate lr. log: None, or a function
    called as log(row) after each epoch (the runner prints the row).
    Returns the history: a list with one dict per epoch {"epoch": 1, 2, …, "train_loss": mean of that epoch's batch
    losses, "val_loss": the loss on the validation pairs, in batches of `batch`, averaged} — floats.
    Example: with 512 training and 256 validation pairs, epochs=3 → a list of 3 dicts whose "train_loss" usually
             goes down, e.g. [{"epoch": 1, "train_loss": 0.47, "val_loss": 0.45}, {"epoch": 2, …}, {"epoch": 3, …}]
    """
    g = torch.Generator().manual_seed(int(seed))
    torch.manual_seed(int(seed))
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    history = []
    n = len(train_a)
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(n, generator=g).to(train_a.device)
        losses = []
        for start in range(0, n, batch):
            idx = order[start:start + batch]
            if len(idx) < 2:
                continue
            loss = triplet_loss(model(train_a[idx]), model(train_p[idx]))
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            vl = [triplet_loss(model(val_a[s:s + batch]), model(val_p[s:s + batch])).item()
                  for s in range(0, len(val_a), batch) if len(val_a[s:s + batch]) >= 2]
        row = {"epoch": epoch, "train_loss": float(np.mean(losses)), "val_loss": float(np.mean(vl))}
        history.append(row)
        if log is not None:
            log(row)
    return history


# ====================================================================== using a trained network (given)

# @part 21
def describe(model, patches, device="cpu", batch=1024):
    """Descriptors of uint8 patches (N, s, s) with a model: numpy float32 (N, DIM), computed without gradients.

    Example: describe(PatchNet(), np.zeros((3, 48, 48), np.uint8)).shape → (3, 64)
    """
    # from mission 21 — finished: read it, use it, do not change it
    model.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(patches), batch):
            out.append(model(to_tensor(patches[s:s + batch], device)).cpu().numpy())
    return np.concatenate(out).astype(np.float32) if out else np.zeros((0, DIM), np.float32)


# @part 21
def nn_accuracy(d1, d2, metric="l2", gallery=256):
    """The matching score of a descriptor (lesson §8): d1[i] and d2[i] describe the same ground point. In groups of
    `gallery` pairs, each d1[i] is compared with the d2 of its whole group; it is right when its nearest one is d2[i].
    Returns the share of right answers (0 to 1). metric: "l2" (float descriptors) or "hamming" (ORB's uint8 rows).

    Example: nn_accuracy(np.eye(4, dtype=np.float32), np.eye(4, dtype=np.float32)) → 1.0
    """
    # from mission 21 — finished: read it, use it, do not change it
    d1, d2 = np.asarray(d1), np.asarray(d2)
    right = 0
    for s in range(0, len(d1), gallery):
        a, b = d1[s:s + gallery], d2[s:s + gallery]
        if metric == "hamming":
            x = np.bitwise_xor(a[:, None, :], b[None, :, :])
            dist = np.unpackbits(x, axis=2).sum(axis=2)
        else:
            dist = ((a[:, None, :].astype(np.float64) - b[None, :, :]) ** 2).sum(axis=2)
        right += int((dist.argmin(axis=1) == np.arange(len(a))).sum())
    return right / max(1, len(d1))


# @part 21
def load_weights(path, device="cpu"):
    """A PatchNet with the weights saved at `path` (torch.save(model.state_dict(), path)), read safely
    (weights_only=True: numbers only). Raises if the file does not fit PatchNet's layers.

    Example: load_weights("my_desc.pt") → PatchNet(...) ready for describe()
    """
    # from mission 21 — finished: read it, use it, do not change it
    model = PatchNet()
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    return model.to(device).eval()
