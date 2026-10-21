"""STHN (one stage) as one GPU graph: the same network and iterations, no CPU round trips, exportable.

STHN's IHN.forward refines four corner displacements in 6 iterations; each one turns them into a
homography with kornia.get_perspective_transform (an 8x8 linear solve). On JetPack 6 torch cannot load
CUDA linear algebra, so those solves run on the CPU: 6 GPU -> CPU -> GPU round trips per frame
(night_localizer._ensure_cuda_linalg). The corners always start from the same rectangle of the 64 x 64
feature grid, and the homography from a rectangle to a quadrilateral has a closed form (Heckbert 1989,
square-to-quad), so here it is computed with plain arithmetic on the GPU: same result within float
rounding, no solve, no synchronisation, and the whole forward exports to ONNX / TensorRT.

STHNCore(netG)(image1, image2) -> four_point_disp (B, 2, 2, 2), the network's `four_pred`:
image1 is the satellite patch already resized to 256 (STHN.set_input's antialiased resize, done by the
caller in torch), image2 the thermal query at 256, both RGB in [0, 1].

A step whose homography is not finite keeps the previous displacement, as IHN.forward does when its
solve fails.
"""
import torch
import torch.nn as nn


def rect_to_quad_points(disp: torch.Tensor, h: int, w: int) -> torch.Tensor:
    """Grid points (B, 2, h, w) of an h x w grid mapped by the homography taking the rectangle
    (0, 0), (w-1, 0), (0, h-1), (w-1, h-1) to itself moved by disp (B, 2, 2, 2): [b, coord x|y, row, col].
    """
    b = disp.shape[0]
    x0 = disp[:, 0, 0, 0]
    y0 = disp[:, 1, 0, 0]
    x1 = disp[:, 0, 0, 1] + (w - 1)
    y1 = disp[:, 1, 0, 1]
    x3 = disp[:, 0, 1, 0]
    y3 = disp[:, 1, 1, 0] + (h - 1)
    x2 = disp[:, 0, 1, 1] + (w - 1)
    y2 = disp[:, 1, 1, 1] + (h - 1)
    # unit square (0,0) (1,0) (1,1) (0,1) -> p0 p1 p2 p3 (top-left, top-right, bottom-right, bottom-left)
    sx = x0 - x1 + x2 - x3
    sy = y0 - y1 + y2 - y3
    dx1, dx2 = x1 - x2, x3 - x2
    dy1, dy2 = y1 - y2, y3 - y2
    den = dx1 * dy2 - dx2 * dy1
    g = (sx * dy2 - dx2 * sy) / den
    k = (dx1 * sy - sx * dy1) / den
    a = x1 - x0 + g * x1
    bb = x3 - x0 + k * x3
    d = y1 - y0 + g * y1
    e = y3 - y0 + k * y3
    v = torch.linspace(0.0, 1.0, h, device=disp.device, dtype=disp.dtype).view(1, h, 1)
    u = torch.linspace(0.0, 1.0, w, device=disp.device, dtype=disp.dtype).view(1, 1, w)

    def c(t):
        return t.view(b, 1, 1)
    den_p = c(g) * u + c(k) * v + 1.0
    px = (c(a) * u + c(bb) * v + c(x0)) / den_p
    py = (c(d) * u + c(e) * v + c(y0)) / den_p
    return torch.stack([px, py], dim=1)


class STHNCore(nn.Module):
    """IHN.forward of a loaded STHN netG (one stage, lev0, no weight head) without CPU solves."""

    def __init__(self, netG: nn.Module, iters: int = 6, corr_level: int = 4, corr_radius: int = 4):
        super().__init__()
        if getattr(netG.args, "weight", False) or getattr(netG.args, "fnet_cat", False):
            raise ValueError("STHNCore: only the one-stage IHN without weight head / fnet_cat")
        self.fnet1 = netG.fnet1
        self.update_block_4 = netG.update_block_4
        self.iters, self.corr_level, self.corr_radius = int(iters), int(corr_level), int(corr_radius)
        self.CorrBlock = type(netG).forward.__globals__["CorrBlock"]   # STHN's own correlation lookup
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, image1: torch.Tensor, image2: torch.Tensor) -> torch.Tensor:
        image1 = (image1 - self.mean) / self.std
        image2 = (image2 - self.mean) / self.std
        fmap1 = self.fnet1(image1).float()
        fmap2 = self.fnet1(image2).float()
        corr_fn = self.CorrBlock(fmap1, fmap2, num_levels=self.corr_level, radius=self.corr_radius)
        n, _, h, w = fmap1.shape
        ys = torch.arange(h, device=fmap1.device, dtype=torch.float32).view(1, h, 1).expand(1, h, w)
        xs = torch.arange(w, device=fmap1.device, dtype=torch.float32).view(1, 1, w).expand(1, h, w)
        coords0 = torch.stack([xs, ys], dim=1).expand(n, 2, h, w)
        coords1 = coords0
        disp = torch.zeros((n, 2, 2, 2), device=fmap1.device, dtype=torch.float32)
        for _ in range(self.iters):
            corr = corr_fn(coords1)
            flow = coords1 - coords0
            delta = self.update_block_4(corr, flow).float()
            new = disp + delta
            pts = rect_to_quad_points(new / 4.0, h, w)
            ok = torch.isfinite(pts).flatten(1).all(dim=1).view(n, 1, 1, 1)
            disp = torch.where(ok, new, disp)
            coords1 = torch.where(ok, pts, coords1)
        return disp
