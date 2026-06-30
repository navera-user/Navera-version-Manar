#!/usr/bin/env python3
import os, cv2, torch, timm, numpy as np, pandas as pd, torch.nn as nn
import argparse, time
from pathlib import Path
from torchvision import transforms
from sklearn.metrics.pairwise import cosine_similarity

TOP_K_CANDIDATES = 50
device = "cuda" if torch.cuda.is_available() else "cpu"

transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
])

def load_image(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Image introuvable: {path}")
    return transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

class NetVLAD(nn.Module):
    def __init__(self, num_clusters=64, dim=2048):
        super().__init__()
        self.conv = nn.Conv2d(dim, num_clusters, 1)
        self.centroids = nn.Parameter(torch.rand(num_clusters, dim))
        self.num_clusters = num_clusters
    def forward(self, x):
        N,C,H,W = x.shape
        soft_assign = torch.softmax(self.conv(x).view(N,self.num_clusters,-1), dim=1)
        x_flat = x.view(N,C,-1)
        vlad = []
        for k in range(self.num_clusters):
            residual = x_flat - self.centroids[k:k+1].unsqueeze(-1)
            vlad.append((soft_assign[:,k:k+1]*residual).sum(-1))
        return torch.nn.functional.normalize(torch.cat(vlad,1), p=2, dim=1)

class BackboneNetVLAD(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = timm.create_model("resnet50", pretrained=True, features_only=True)
        dim = self.backbone.feature_info[-1]['num_chs']
        self.netvlad = NetVLAD(64, dim)
    def forward(self, x):
        return self.netvlad(self.backbone(x)[-1])

class GeM(nn.Module):
    def __init__(self, p=3.0, eps=1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.ones(1)*p)
        self.eps = eps
    def forward(self, x):
        return x.clamp(min=self.eps).pow(self.p).mean((-2,-1)).pow(1./self.p)

class DINOv2GeM(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = torch.hub.load("facebookresearch/dinov2","dinov2_vits14",pretrained=True)
        self.gem = GeM()
    def forward(self, x):
        out = self.backbone.get_intermediate_layers(x,n=1)[0]
        B,N,C = out.shape
        H=W=int(N**0.5)
        out = self.gem(out.reshape(B,H,W,C).permute(0,3,1,2))
        return torch.nn.functional.normalize(out,p=2,dim=1)

class VisualLocalizer:
    def __init__(self, dataset_dir):
        self.dataset_dir = Path(dataset_dir)
        self.images_dir  = self.dataset_dir / "images"
        self.csv_path    = self.dataset_dir / "metadata.csv"
        print(f"\n{'='*60}")
        print(f"  VISUAL LOCALIZER — device: {device}")
        print(f"  Dataset: {self.dataset_dir.name}")
        print(f"{'='*60}")
        self.df = pd.read_csv(self.csv_path)
        print(f"  {len(self.df)} images dans le dataset")
        print("  Chargement modeles...")
        t0 = time.time()
        self.netvlad_model = BackboneNetVLAD().to(device).eval()
        self.dinov2_model  = DINOv2GeM().to(device).eval()
        print(f"  Modeles charges en {(time.time()-t0)*1000:.0f}ms")
        cache_path = self.dataset_dir / "descriptors_cache.npz"
        if cache_path.exists():
            print("  Cache trouve -> chargement...")
            cache = np.load(cache_path, allow_pickle=True)
            self.netvlad_desc = cache["netvlad"]
            self.dinov2_desc  = cache["dino"]
            self.coords       = cache["coords"]
            self.filenames    = list(cache["filenames"])
            print(f"  {len(self.coords)} descripteurs charges")
        else:
            print("  Extraction features (premiere fois)...")
            self._index_dataset(cache_path)
        print(f"{'='*60}\n")

    def _index_dataset(self, cache_path):
        nv_list, dino_list, coords_list, fn_list = [], [], [], []
        t0 = time.time()
        with torch.no_grad():
            for i, row in self.df.iterrows():
                img_path = self.images_dir / row["filename"]
                if not img_path.exists():
                    continue
                t = load_image(str(img_path)).unsqueeze(0).to(device)
                nv_list.append(self.netvlad_model(t).cpu().numpy()[0])
                dino_list.append(self.dinov2_model(t).cpu().numpy()[0])
                coords_list.append([float(row["center_lat"]), float(row["center_lon"])])
                fn_list.append(row["filename"])
                if (i+1) % 50 == 0 or (i+1) == len(self.df):
                    elapsed = time.time()-t0
                    rate = (i+1)/elapsed
                    print(f"  [{i+1:>4}/{len(self.df)}]  {rate:.1f} img/s  ETA: {(len(self.df)-i-1)/rate:.0f}s")
        self.netvlad_desc = np.array(nv_list)
        self.dinov2_desc  = np.array(dino_list)
        self.coords       = np.array(coords_list)
        self.filenames    = fn_list
        np.savez(cache_path, netvlad=self.netvlad_desc, dino=self.dinov2_desc,
                 coords=self.coords, filenames=np.array(self.filenames))
        print(f"  Cache sauvegarde: {cache_path.name}")

    def localize(self, query_path, ref_lat=None, ref_lon=None, radius_m=None):
        print(f"\n  LOCALISATION: {Path(query_path).name}")
        print(f"  {'-'*50}")
        t0 = time.time()

        # --- Step 1: Spatial Filtering ---
        if ref_lat is not None and ref_lon is not None and radius_m is not None:
            d_lat = self.coords[:, 0] - ref_lat
            d_lon = self.coords[:, 1] - ref_lon
            m_per_deg_lat = 111320.0
            m_per_deg_lon = 111320.0 * np.cos(np.radians(ref_lat))
            dist_sq = (d_lat * m_per_deg_lat)**2 + (d_lon * m_per_deg_lon)**2
            mask = dist_sq <= radius_m**2

            f_nv    = self.netvlad_desc[mask]
            f_dino  = self.dinov2_desc[mask]
            f_coords = self.coords[mask]
            f_fns   = [self.filenames[i] for i, m in enumerate(mask) if m]

            if len(f_fns) == 0:
                print(f"  ⚠️ No images within {radius_m}m. Using full dataset.")
                f_nv, f_dino, f_coords, f_fns = self.netvlad_desc, self.dinov2_desc, self.coords, self.filenames
            else:
                print(f"  🎯 Spatial filter: {len(f_fns)}/{len(self.filenames)} images (radius {radius_m}m)")
        else:
            f_nv, f_dino, f_coords, f_fns = self.netvlad_desc, self.dinov2_desc, self.coords, self.filenames

        qt = load_image(query_path).unsqueeze(0).to(device)
        with torch.no_grad():
            q_nv   = self.netvlad_model(qt).cpu().numpy()[0]
            q_dino = self.dinov2_model(qt).cpu().numpy()[0]

        # Stage 1 — NetVLAD (on filtered set)
        nv_sims  = cosine_similarity(q_nv.reshape(1,-1), f_nv)[0]
        actual_top_k = min(TOP_K_CANDIDATES, len(f_nv))
        cand_idx = nv_sims.argsort()[-actual_top_k:][::-1]

        print(f"  Stage 1 NetVLAD -> Top-{actual_top_k} candidats")
        print(f"  Meilleur score NetVLAD: {nv_sims[cand_idx[0]]:.4f}")

        # Stage 2 — DINOv2
        dino_sims      = cosine_similarity(q_dino.reshape(1,-1), f_dino[cand_idx])[0]
        best_local_idx = dino_sims.argmax()
        best_idx       = cand_idx[best_local_idx]

        lat   = float(f_coords[best_idx][0])
        lon   = float(f_coords[best_idx][1])
        score = float(dino_sims[best_local_idx])
        best_img = f_fns[best_idx]
        elapsed  = (time.time()-t0)*1000
        top5_local = dino_sims.argsort()[-5:][::-1]
        top5 = [{"rank":r+1,"filename":f_fns[cand_idx[li]],
                 "lat":float(f_coords[cand_idx[li]][0]),
                 "lon":float(f_coords[cand_idx[li]][1]),
                 "score":float(dino_sims[li])}
                for r,li in enumerate(top5_local)]
        print(f"\n  {'='*50}")
        print(f"  POSITION ESTIMEE")
        print(f"  {'='*50}")
        print(f"  Latitude  : {lat:.6f}")
        print(f"  Longitude : {lon:.6f}")
        print(f"  Score     : {score:.4f}  (1.0 = parfait)")
        print(f"  Best match: {best_img}")
        print(f"  Temps     : {elapsed:.0f} ms")
        print(f"\n  TOP 5 CANDIDATS:")
        for c in top5:
            print(f"    #{c['rank']}  score={c['score']:.4f}  lat={c['lat']:.6f}  lon={c['lon']:.6f}  -> {c['filename']}")
        print(f"  {'='*50}\n")
        return {"lat":lat,"lon":lon,"score":score,"match":best_img,"best_match_image":best_img,"elapsed_ms":elapsed,"top5":top5}

    def visualize_result(self, query_path, result, output_path):
        query_img = cv2.imread(query_path)
        best_img  = cv2.imread(str(self.images_dir / result["best_match_image"]))
        if query_img is None or best_img is None:
            print("  Impossible de generer la visualisation")
            return
        H = 400
        q = cv2.resize(query_img, (H,H))
        b = cv2.resize(best_img,  (H,H))
        def label(img, txt, col):
            out = img.copy()
            cv2.rectangle(out,(0,H-40),(H,H),(0,0,0),-1)
            cv2.putText(out,txt,(8,H-12),cv2.FONT_HERSHEY_SIMPLEX,0.5,col,1)
            return out
        q = label(q, f"QUERY: {Path(query_path).name}", (100,255,100))
        b = label(b, f"BEST MATCH score={result['score']:.3f}", (100,200,255))
        sep = np.zeros((H,6,3),dtype=np.uint8); sep[:]=(0,0,200)
        combined = np.hstack([q,sep,b])
        info = np.zeros((55,combined.shape[1],3),dtype=np.uint8)
        cv2.putText(info,
            f"GPS: lat={result['lat']:.6f}  lon={result['lon']:.6f}  score={result['score']:.4f}  time={result['elapsed_ms']:.0f}ms",
            (10,35),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
        cv2.imwrite(output_path, np.vstack([combined,info]))
        print(f"  Visualisation sauvegardee: {output_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query",   type=str, required=True)
    parser.add_argument("--dataset", type=str, required=True)
    parser.add_argument("--output",  type=str, default="/tmp/result_frame019.jpg")
    args = parser.parse_args()
    if not os.path.exists(args.query):
        print(f"Image query introuvable: {args.query}"); exit(1)
    if not os.path.exists(args.dataset):
        print(f"Dataset introuvable: {args.dataset}"); exit(1)
    loc    = VisualLocalizer(args.dataset)
    result = loc.localize(args.query)
    loc.visualize_result(args.query, result, args.output)
    print(f"RESULTAT FINAL -> lat={result['lat']:.6f}  lon={result['lon']:.6f}  score={result['score']:.4f}")

if __name__ == "__main__":
    main()
