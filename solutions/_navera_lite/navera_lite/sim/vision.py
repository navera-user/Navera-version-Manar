"""navera_lite/sim/vision.py — your trained networks IN the simulation loop (vision "mine"): every second the
simulated camera cuts a picture from the corridor at the place it really looks at, and the vision pipelines of
missions 22 and 25 locate it with YOUR weights. Part of NAVERA Lite, the course's teaching stack (mission 31).
Written for the course; it is not NAVERA code.

  day    a 480 × 360 photo (camera 90° wide, the vehicle's true heading) resampled from day_ortho.png, light camera
         noise; the map patch is 400 × 400 px at 1.0 m/px around the PRIOR (the judge's last position); matching =
         mission 22's learned_pairs with YOUR PatchNet weights (my_desc.pt; ratio 0.8), RANSAC similarity and the
         gates; the fix = where the photo's centre lands on the map.
  night  mission 25's way: the 64 × 64 reference patch around the prior (night_ref.png, ≈ 7.75 m/px) and the
         thermal patch at the true place (night_temp.png through thermal_camera), north-up; YOUR HomographyNet
         weights (my_homography.pt) give the 4 corner offsets; the fix = the prior + the centre's shift.
Both need the prior within reach (day: the photo inside the map patch; night: about ±12 px ≈ ±90 m, what the
network was trained on). This is the simulator's camera: the photos are cut from the very pictures the matcher
uses, so the errors are optimistic (lesson §6).
"""
import json
import math
import os

import cv2
import numpy as np

# @part 31
PHOTO_W, PHOTO_H, PHOTO_HFOV_DEG = 480, 360, 90.0
# @part 31
MAP_PX, MAP_MPP = 400, 1.0
# @part 31
LEARNED_RATIO = 0.8
# @part 31
HEADING_SIGMA_DEG = 2.0          # the heading the matcher is told: the true one + this much noise (the IMU's)
# @part 31
TILT_SIGMA_DEG = 1.0             # the day camera's tilt, unknown to the pipeline (each axis)


# @part 31
class NetworkVision:
    """locate(seen_en, prior_en, light, heading_deg, alt_m, rng) → ((e, n), stated σ) or (None, reason), like
    world.ProfileVision, but computed by the networks on pictures (see the top of this file).
    stated: the σ (m) each source states: {"day": …, "night": …} (default the target profile's 15 and 25 m;
    my_vision_profile.json, when it exists, gives the σ you measured).
    """

    def __init__(self, data_dir, day_weights, night_weights, stated=None):
        import torch
        torch.set_num_threads(2)
        from navera_lite import homography_net, learned_desc
        with open(os.path.join(data_dir, "corridor", "corridor.json")) as f:
            self.c = json.load(f)
        d = os.path.join(data_dir, "corridor")
        self.ortho = cv2.imread(os.path.join(d, "day_ortho.png"), cv2.IMREAD_GRAYSCALE)
        f = self.c["day_m_per_px"] / MAP_MPP
        self.map = cv2.resize(self.ortho, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        self.nref = cv2.imread(os.path.join(d, "night_ref.png"), cv2.IMREAD_GRAYSCALE)
        self.ntemp = cv2.imread(os.path.join(d, "night_temp.png"), cv2.IMREAD_GRAYSCALE)
        self.desc = learned_desc.load_weights(day_weights)
        with open(day_weights, "rb") as f:
            import hashlib
            self.desc_sha = hashlib.sha1(f.read()).hexdigest()[:12]
        self.hnet = homography_net.load_weights(night_weights)
        self.stated = {"day": 15.0, "night": 25.0}
        if stated:
            self.stated.update(stated)
        self.np_rng = np.random.default_rng(31)
        self.last_reason = ""

    def px(self, e, n, mpp):
        """Pixel-centre (x, y) of east/north metres in a corridor picture of mpp m/px."""
        return (e + self.c["half_east_m"]) / mpp - 0.5, (self.c["half_north_m"] - n) / mpp - 0.5

    def photo(self, seen_en, heading_deg, alt_m):
        gsd = 2.0 * alt_m * math.tan(math.radians(PHOTO_HFOV_DEG / 2)) / PHOTO_W
        mpp = self.c["day_m_per_px"]
        p = math.radians(heading_deg)
        s, c = math.sin(p), math.cos(p)
        # photo pixel (u, v) → ground metres from the seen point → ortho pixel
        A = np.array([[c * gsd, -s * gsd], [-s * gsd, -c * gsd]])      # (u, v) offsets → (east, north)
        ox, oy = self.px(seen_en[0], seen_en[1], mpp)
        cu, cv_ = (PHOTO_W - 1) / 2.0, (PHOTO_H - 1) / 2.0
        # ortho x = ox + east/mpp, ortho y = oy − north/mpp
        M = np.array([[A[0, 0] / mpp, A[0, 1] / mpp, 0.0], [-A[1, 0] / mpp, -A[1, 1] / mpp, 0.0]])
        M[:, 2] = [ox, oy] - M[:, :2] @ np.array([cu, cv_])
        src = self.ortho
        if gsd > mpp:
            src = cv2.GaussianBlur(src, (0, 0), 0.45 * math.sqrt((gsd / mpp) ** 2 - 1.0))
        img = cv2.warpAffine(src, M, (PHOTO_W, PHOTO_H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REFLECT)
        img = cv2.GaussianBlur(img, (0, 0), 0.8).astype(np.float32)          # optics, a little motion
        img = 255.0 * (img / 255.0) ** self.np_rng.uniform(0.85, 1.15) * self.np_rng.uniform(0.85, 1.1)
        img = img + self.np_rng.normal(0, 4.0, img.shape)
        return np.clip(np.rint(img), 0, 255).astype(np.uint8), gsd

    def map_features(self):
        """Keypoints and YOUR descriptors of the whole 1 m/px map, computed once (the map is fixed: a real system
        prepares its map before the flight too). About 20 s on the CPU."""
        from navera_lite.learned_desc import describe
        from navera_lite.learned_match import keypoints, patches_at
        cache = os.path.join("my_runs", ".map_features_" + self.desc_sha + ".npz")
        if os.path.exists(cache):
            with np.load(cache) as z:
                self.map_pts, self.map_des = z["pts"], z["des"]
            return
        h, w = self.map.shape
        pts = []
        for y0 in range(0, h, 200):
            for x0 in range(0, w, 200):
                y1, x1 = min(h, y0 + 248), min(w, x0 + 248)
                p = keypoints(self.map[y0:y1, x0:x1], n=300, margin=0)
                p = p[(p[:, 0] < 200) & (p[:, 1] < 200)] + np.float32([x0, y0])
                pts.append(p)
        pts = np.concatenate(pts)
        m = 24
        pts = pts[(pts[:, 0] >= m) & (pts[:, 1] >= m) & (pts[:, 0] <= w - 1 - m) & (pts[:, 1] <= h - 1 - m)]
        self.map_pts = pts
        self.map_des = describe(self.desc, patches_at(self.map, pts))
        try:
            os.makedirs("my_runs", exist_ok=True)
            np.savez(cache, pts=self.map_pts, des=self.map_des)
        except OSError:
            pass

    def day(self, seen_en, prior_en, heading_deg, alt_m, rng):
        """Mission 22's learned matching, with the map's descriptors computed once (map_features)."""
        from navera_lite.features import warp_points
        from navera_lite.learned_desc import describe
        from navera_lite.learned_match import RANSAC_ITERS, RANSAC_PX, keypoints, patches_at, upright
        from navera_lite.match import distance_matrix, gates, ransac_similarity, ratio_test
        if not hasattr(self, "map_pts"):
            self.map_features()
        # the camera is never exactly vertical (σ 1° on each axis): the photo's centre lies alt·tan(tilt) away from
        # the point below the vehicle, and the pipeline does not know it (mission 18's tilt error)
        te, tn = (alt_m * math.tan(math.radians(rng.gauss(0.0, TILT_SIGMA_DEG))) for _ in range(2))
        photo, gsd = self.photo((seen_en[0] + te, seen_en[1] + tn), heading_deg, alt_m)
        zoom = MAP_MPP / gsd
        told = heading_deg + rng.gauss(0.0, HEADING_SIGMA_DEG)
        px, py = self.px(prior_en[0], prior_en[1], MAP_MPP)
        r = MAP_PX / 2.0
        near = ((np.abs(self.map_pts[:, 0] - px) <= r) & (np.abs(self.map_pts[:, 1] - py) <= r))
        p1, d1 = self.map_pts[near], self.map_des[near]
        up, valid, A = upright(photo, told, zoom)
        p2 = keypoints(up, n=600, valid=valid)
        if len(p1) < 2 or len(p2) < 2:
            return None, "too few keypoints"
        d = distance_matrix(d1, describe(self.desc, patches_at(up, p2)))
        k = np.asarray(ratio_test(d, LEARNED_RATIO)).reshape(-1, 2)
        if len(k) < 2:
            return None, "too few pairs"
        src = p1[k[:, 0]].astype(np.float64)                        # absolute map pixels
        dst = warp_points(np.linalg.inv(A), p2[k[:, 1]])            # photo pixels
        fit, inl = ransac_similarity(src, dst, RANSAC_PX, RANSAC_ITERS, np.random.default_rng(0))
        ok, why = gates(fit, dst[inl] if len(dst) else dst, photo.shape, zoom)
        if not ok:
            return None, why
        s_, th, tx, ty = fit
        c, s = s_ * math.cos(math.radians(th)), s_ * math.sin(math.radians(th))
        M = np.array([[c, -s, tx], [s, c, ty], [0.0, 0.0, 1.0]])    # map pixel → photo pixel
        x, y, _ = np.linalg.solve(M, np.array([(PHOTO_W - 1) / 2.0, (PHOTO_H - 1) / 2.0, 1.0]))
        e = (x + 0.5) * MAP_MPP - self.c["half_east_m"]
        n = self.c["half_north_m"] - (y + 0.5) * MAP_MPP
        return (e, n), self.stated["day"]

    def night(self, seen_en, prior_en):
        from navera_lite.homography_net import PATCH_PX, RHO_PX, SQUARE, centre_shift, predict, thermal_camera
        nm = self.c["night_m_per_px"]
        P = (PATCH_PX, PATCH_PX)
        rx, ry = self.px(prior_en[0], prior_en[1], nm)
        tx, ty = self.px(seen_en[0], seen_en[1], nm)
        ref = cv2.getRectSubPix(self.nref, P, (float(rx), float(ry)))
        th = thermal_camera(cv2.getRectSubPix(self.ntemp, P, (float(tx), float(ty))), self.np_rng)
        off = predict(self.hnet, np.stack([ref, th])[None])[0]
        if np.abs(off).max() > 2.0 * RHO_PX:
            return None, "offsets out of range"
        H = cv2.getPerspectiveTransform(SQUARE, (SQUARE + off.reshape(4, 2)).astype(np.float32))
        dx, dy = centre_shift(H)
        return (prior_en[0] + dx * nm, prior_en[1] - dy * nm), self.stated["night"]

    def locate(self, seen_en, prior_en, light, heading_deg, alt_m, rng):
        if light == "day":
            return self.day(seen_en, prior_en, heading_deg, alt_m, rng)
        return self.night(seen_en, prior_en)
