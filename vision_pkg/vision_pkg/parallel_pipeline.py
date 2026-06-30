#!/usr/bin/env python3
"""
parallel_pipeline.py — Pipeline parallèle Dataset + Descriptors + Matching
═══════════════════════════════════════════════════════════════════════════
Architecture :
  Stage 1 (parallel) : generate_dataset pour chaque WP → N threads simultanés
  Stage 2 (parallel) : index_descriptors sur les nouveaux WPs → dès qu'un WP est prêt
  Stage 3 (stream)   : matching prêt dès le 1er WP indexé → ~105ms

Usage :
  from parallel_pipeline import ParallelPipeline
  pp = ParallelPipeline(mbtiles_path, output_dir)
  pp.run(waypoints, altitude, zoom, radius_m, overlap)
"""
import os
import time
import threading
import queue
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

# ── Imports projet ────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent))
from dataset_gen import generate_dataset
from gps_localizer import _get_localizer, precollect_dataset

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_PARALLEL_DATASETS = 4   # Nb de WPs générés en parallèle
MAX_PARALLEL_INDEX    = 2   # Nb de WPs indexés en parallèle

class ParallelPipeline:
    """
    Pipeline 3 stages en parallèle :
      Stage 1 : generate_dataset  (N WPs en parallèle)
      Stage 2 : build_descriptors (dès qu'un WP est prêt)
      Stage 3 : matching ready    (dès le 1er WP indexé)
    """

    def __init__(self, mbtiles_path: str, output_dir: str):
        self.mbtiles_path = mbtiles_path
        self.output_dir   = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Queues inter-stages
        self._gen_queue   = queue.Queue()   # WP prêts pour indexation
        self._index_queue = queue.Queue()   # WP indexés

        # État
        self._lock         = threading.Lock()
        self._done_wps     = []
        self._indexed_wps  = []
        self._errors       = []
        self._total_wps    = 0
        self._gen_done     = threading.Event()
        self._index_done   = threading.Event()

        # Stats
        self.stats = {
            'gen_ms':   [],
            'idx_ms':   [],
            'total_ms': 0,
        }

    def run(self,
            waypoints:  List[Dict] = None,
            bbox:       Dict       = None,
            altitude_m: int   = 400,
            zoom:       int   = 17,
            radius_m:   float = 300,
            overlap:    float = 0.70,
            verbose:    bool  = True) -> Dict:
        """
        Lance le pipeline complet en parallèle.
        Si bbox est fourni, on ignore waypoints et on génère tout le rectangle.
        Sinon, on utilise la liste de waypoints.
        """
        t_start = time.time()

        if bbox:
            # Pour la bbox, on peut la traiter comme un seul "gros" WP ou la découper.
            # Ici on va la passer directement à dataset_gen.
            self._total_wps = 1
            work_items = [{'bbox': bbox}]
        else:
            self._total_wps = len(waypoints) if waypoints else 0
            work_items = waypoints

        if verbose:
            print(f"\n🚀 Pipeline parallèle — {'BBox' if bbox else f'{self._total_wps} waypoints'}")
            print(f"   Stage 1 : dataset_gen  × {MAX_PARALLEL_DATASETS} threads")
            print(f"   Stage 2 : descriptors  × {MAX_PARALLEL_INDEX} threads")
            print(f"   Stage 3 : matching prêt dès 1er WP indexé\n")

        # Lancer les 3 stages en parallèle
        t1 = threading.Thread(target=self._stage1_generate,
                              args=(work_items, altitude_m, zoom, radius_m, overlap, verbose),
                              daemon=True)
        t2 = threading.Thread(target=self._stage2_index,
                              args=(verbose,),
                              daemon=True)
        t3 = threading.Thread(target=self._stage3_merge,
                              args=(verbose,),
                              daemon=True)

        t1.start(); t2.start(); t3.start()
        t1.join();  t2.join();  t3.join()

        self.stats['total_ms'] = round((time.time() - t_start) * 1000)

        if verbose:
            print(f"\n✅ Pipeline terminé en {self.stats['total_ms']}ms")
            print(f"   WPs générés  : {len(self._done_wps)}/{self._total_wps}")
            print(f"   WPs indexés  : {len(self._indexed_wps)}")
            if self.stats['gen_ms']:
                print(f"   Temps gen    : {sum(self.stats['gen_ms'])//len(self.stats['gen_ms'])}ms/WP (moy)")
            if self.stats['idx_ms']:
                print(f"   Temps index  : {sum(self.stats['idx_ms'])//len(self.stats['idx_ms'])}ms/WP (moy)")
            cache = self.output_dir / "descriptors_cache.npz"
            print(f"   Cache prêt   : {'✅ '+str(cache) if cache.exists() else '❌'}")

        return {
            'done_wps':    len(self._done_wps),
            'indexed_wps': len(self._indexed_wps),
            'errors':      self._errors,
            'total_ms':    self.stats['total_ms'],
            'cache_ready': (self.output_dir / "descriptors_cache.npz").exists(),
            'output_dir':  str(self.output_dir),
        }

    # ── STAGE 1 : generate_dataset en parallèle ───────────────────────────────
    def _stage1_generate(self, work_items, altitude_m, zoom, radius_m, overlap, verbose):
        """Génère les datasets pour tous les items (WPs ou BBox) en parallèle."""
        def gen_one(item, idx):
            t = time.time()
            try:
                wp_dir = self.output_dir / f"wp_{idx:04d}"

                # Check if it's a BBox or a standard WP
                if 'bbox' in item:
                    result = generate_dataset(
                        lat        = 0, lon = 0, # Not used for BBox
                        altitude_m = altitude_m,
                        mbtiles_path = self.mbtiles_path,
                        output_dir = str(self.output_dir),  # ★ Sauvegarder directement dans output_dir pour bbox
                        bbox       = item['bbox'],
                        verbose    = False
                    )
                else:
                    result = generate_dataset(
                        lat        = item['lat'],
                        lon        = item['lon'],
                        altitude_m = altitude_m,
                        mbtiles_path = self.mbtiles_path,
                        output_dir = str(wp_dir),
                        search_radius_m = radius_m,
                        verbose    = False
                    )
                elapsed = round((time.time() - t) * 1000)
                with self._lock:
                    self.stats['gen_ms'].append(elapsed)
                    self._done_wps.append(idx)
                if verbose:
                    print(f"  ✅ Stage1 WP{idx} — {result.total_images} imgs · {elapsed}ms")
                # Envoyer au stage 2
                self._gen_queue.put({'idx': idx, 'dir': str(wp_dir), 'result': result})
                return True
            except Exception as e:
                with self._lock:
                    self._errors.append(f"WP{idx}: {e}")
                if verbose:
                    print(f"  ❌ Stage1 WP{idx} — {e}")
                self._gen_queue.put(None)  # signal d'erreur
                return False

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_DATASETS) as ex:
            futures = {ex.submit(gen_one, item, i): i for i, item in enumerate(work_items)}
            for f in as_completed(futures):
                pass  # résultats gérés dans gen_one

        self._gen_done.set()
        self._gen_queue.put(None)  # sentinel

    # ── STAGE 2 : build descriptors dès qu'un WP est prêt ────────────────────
    def _stage2_index(self, verbose):
        """Indexe les descripteurs dès que chaque WP est généré."""
        pending = []

        def index_wp(wp_info):
            t = time.time()
            try:
                # Charger le localizer pour ce WP (construit les descripteurs)
                localizer = _get_localizer(wp_info['dir'])
                elapsed = round((time.time() - t) * 1000)
                with self._lock:
                    self.stats['idx_ms'].append(elapsed)
                    self._indexed_wps.append(wp_info['idx'])
                if verbose:
                    print(f"  ✅ Stage2 WP{wp_info['idx']} indexé · {elapsed}ms")
                self._index_queue.put(wp_info)
                return True
            except Exception as e:
                with self._lock:
                    self._errors.append(f"Index WP{wp_info['idx']}: {e}")
                if verbose:
                    print(f"  ❌ Stage2 WP{wp_info['idx']} — {e}")
                return False

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_INDEX) as ex:
            futures = []
            while True:
                try:
                    item = self._gen_queue.get(timeout=60)
                except queue.Empty:
                    break
                if item is None:
                    # Attendre que tous les futures soient terminés
                    for f in as_completed(futures):
                        pass
                    break
                futures.append(ex.submit(index_wp, item))

        self._index_done.set()
        self._index_queue.put(None)  # sentinel

    # ── STAGE 3 : merge tous les caches en un seul ───────────────────────────
    def _stage3_merge(self, verbose):
        """
        Merge tous les descripteurs WP en un seul cache global.
        Commence dès que le 1er WP est indexé → matching possible très tôt.
        """
        all_nv      = []
        all_dino    = []
        all_coords  = []
        all_fns     = []
        all_metadata = []

        master_images_dir = self.output_dir / "images"
        master_images_dir.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                item = self._index_queue.get(timeout=60)
            except queue.Empty:
                break
            if item is None:
                break

            wp_dir = Path(item['dir'])
            cache_path = wp_dir / "descriptors_cache.npz"
            meta_path  = wp_dir / "metadata.csv"

            if not cache_path.exists() or not meta_path.exists():
                continue

            try:
                # 1. Merger descriptors
                data = np.load(str(cache_path), allow_pickle=True)

                # On préfixe les filenames par le dossier du WP pour éviter les collisions
                wp_prefix = f"wp_{item['idx']:04d}_"
                wp_fns = data['filenames'].tolist()
                prefixed_fns = [wp_prefix + fn for fn in wp_fns]

                all_nv.append(data['netvlad'])
                all_dino.append(data['dino'])
                all_coords.append(data['coords'])
                all_fns.extend(prefixed_fns)

                # 2. Déplacer/Copier les images vers le dossier master
                wp_images_dir = wp_dir / "images"
                if wp_images_dir.exists():
                    for fn in wp_fns:
                        src = wp_images_dir / fn
                        dst = master_images_dir / (wp_prefix + fn)
                        if src.exists():
                            import shutil
                            shutil.move(str(src), str(dst))

                # 3. Merger metadata
                import pandas as pd
                df = pd.read_csv(str(meta_path))
                df['filename'] = wp_prefix + df['filename']
                all_metadata.append(df)

                # Sauvegarder le cache global et metadata dès que possible
                if all_nv:
                    # Save descriptors
                    merged_nv    = np.vstack(all_nv)
                    merged_dino  = np.vstack(all_dino)
                    merged_coords = np.vstack(all_coords)

                    global_cache = self.output_dir / "descriptors_cache.npz"
                    np.savez(str(global_cache),
                             netvlad   = merged_nv,
                             dino      = merged_dino,
                             coords    = merged_coords,
                             filenames = np.array(all_fns))

                    # Save metadata
                    master_df = pd.concat(all_metadata, ignore_index=True)
                    master_df.to_csv(str(self.output_dir / "metadata.csv"), index=False)

                    if verbose:
                        print(f"  ✅ Stage3 cache global — {merged_nv.shape[0]} images indexées")
            except Exception as e:
                with self._lock:
                    self._errors.append(f"Merge WP{item['idx']}: {e}")
                if verbose:
                    print(f"  ❌ Stage3 merge — {e}")


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    MBTILES = "/home/nour-el-houda-mokded/pfeAutonomTest/ros2_ws/src/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles"
    OUTPUT  = "/home/nour-el-houda-mokded/pfeAutonomTest/ros2_ws/src/vision_pkg/vision_pkg/dataset/fallback_dataset"

    # Test avec 3 waypoints
    wps = [
        {'lat': 35.8354, 'lon': 10.6341},
        {'lat': 35.8430, 'lon': 10.6297},
        {'lat': 35.8506, 'lon': 10.6253},
    ]

    pp = ParallelPipeline(MBTILES, OUTPUT)
    result = pp.run(wps, altitude_m=400, zoom=17, radius_m=300, verbose=True)
    print("\n📊 Résultat final:", result)
