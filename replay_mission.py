#!/usr/bin/env python3
"""
NAVERA — Mission Replay Tool v2 (Blocking GPS-Denied)
"""
import argparse, base64, csv, io, json, os, sys, time, zipfile
from pathlib import Path
try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)


def load_from_zip(zip_path):
    frames = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        csv_name = next((n for n in zf.namelist() if n.endswith('flight_log.csv')), None)
        if not csv_name:
            print("❌ No flight_log.csv"); sys.exit(1)
        rows = list(csv.DictReader(io.StringIO(zf.read(csv_name).decode())))
        image_files = {}
        for name in zf.namelist():
            if name.lower().endswith(('.jpg','.jpeg','.png')):
                parts = os.path.basename(name).split('_')
                for i,p in enumerate(parts):
                    if p == 'frame' and i+1 < len(parts):
                        try: image_files[int(parts[i+1])] = name
                        except ValueError: pass
                        break
        print(f"📂 ZIP: {len(rows)} frames, {len(image_files)} images")
        for row in rows:
            fid = int(row['frame_id'])
            if fid not in image_files:
                print(f"   ⚠ Frame #{fid} — pas d'image, skip"); continue
            gps_valid = row['gps_valid'].strip().lower() in ('true','1','yes')
            meta = {
                'frame_id':    fid,
                'timestamp':   row['timestamp'],
                'altitude_m':  int(row['alt_m']),
                'heading_deg': int(row['heading_deg']),
                'speed_mps':   int(float(row['speed_mps'])),
                'delta_t_s':   float(row['delta_t_s']),
                'gps_valid':   gps_valid,
            }
            if gps_valid and row.get('lat') and row.get('lon'):
                meta['lat'] = float(row['lat'])
                meta['lon'] = float(row['lon'])
            frames.append({'image_b64': base64.b64encode(zf.read(image_files[fid])).decode(),
                           'metadata': meta, 'delta_t': float(row['delta_t_s'])})
    return frames


def wait_for_prediction(status_url, frame_id, poll_interval=0.1, timeout_s=10.0):
    t0 = time.perf_counter()
    last_st = None
    print(f"\n  ⏳ #{frame_id:04d} GPS LOST — attente prédiction CV", end='', flush=True)
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed > timeout_s:
            print(f"\n  ⚠️  Timeout {timeout_s:.0f}s")
            return {"status": "timeout", "elapsed_ms": elapsed*1000}
        try:
            resp = requests.get(status_url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                st   = data.get("status","")
                if st != last_st:
                    last_st = st
                    if st == "searching":
                        print(f"\n  🔍 Searching (R={data.get('search_radius_m',0):.0f}m)", end='', flush=True)
                    elif st in ("predicted","active"):
                        ms  = (time.perf_counter()-t0)*1000
                        lat = data.get('lat',0); lon = data.get('lon',0)
                        score = data.get('score',0)
                        print(f"\n  ✅ PRÉDIT en {ms:.0f}ms | "
                              f"lat={lat:.5f} lon={lon:.5f} score={score:.3f}")
                        return {**data, "elapsed_ms": ms}
                else:
                    print('.', end='', flush=True)
        except Exception as e:
            print(f"[poll:{e}]", end='', flush=True)
        time.sleep(poll_interval)


def replay(frames, receiver_url, status_url, speed=1.0, timeout=30, poll=0.3):
    total = len(frames)
    sent_ok = sent_fail = 0
    pred_times = []
    gps_was_valid = True

    print(f"\n{'═'*62}")
    print(f"  NAVERA Replay v2 — Blocking GPS-Denied")
    print(f"  Receiver : {receiver_url}")
    print(f"  Status   : {status_url}")
    print(f"  Frames   : {total}  |  Speed GPS frames: {speed}x")
    print(f"{'═'*62}\n")

    for i, frame in enumerate(frames):
        meta      = frame['metadata']
        fid       = meta['frame_id']
        gps_valid = meta['gps_valid']

        # Log GPS transitions
        if gps_was_valid and not gps_valid:
            print(f"\n  ⚡⚡⚡ GPS LOST à frame #{fid:04d} ⚡⚡⚡")
        elif not gps_was_valid and gps_valid:
            print(f"\n  ✅✅✅ GPS RESTORED frame #{fid:04d}  "
                  f"lat={meta.get('lat','?')} lon={meta.get('lon','?')} ✅✅✅\n")
        gps_was_valid = gps_valid

        # Délai inter-frames (GPS seulement)
        if i > 0 and gps_valid:
            wait = max(0.5, frame['delta_t'] / speed)
            if wait > 1.0:
                print(f"  ⏳ {wait:.1f}s ...", end='', flush=True)
            time.sleep(wait)
            if wait > 1.0:
                print(" go")

        gps_str = f"lat={meta['lat']:.5f} lon={meta['lon']:.5f}" if gps_valid else "NO GPS"
        print(f"  [{i+1:3d}/{total}] {'📍' if gps_valid else '⚠️ '} #{fid:04d}  "
              f"hdg={meta['heading_deg']:3d}°  {gps_str}", end='  ')

        try:
            t_send = time.perf_counter()
            resp = requests.post(receiver_url,
                                 json={'image_b64': frame['image_b64'], 'metadata': meta},
                                 timeout=timeout,
                                 headers={'Content-Type': 'application/json'})
            ms = (time.perf_counter()-t_send)*1000
            if resp.status_code == 200:
                sent_ok += 1
                total_frame_ms = ms
                print(f"→ ✅ Send {ms:.0f}ms", end='  ')
                
                # If GPS was just lost, wait for prediction before next frame
                if not gps_valid and (i == 0 or meta['gps_valid'] != frames[i-1]['metadata']['gps_valid']):
                    pred_result = wait_for_prediction(status_url, fid, poll_interval=poll, timeout_s=10.0)
                    if 'elapsed_ms' in pred_result:
                        pred_times.append(pred_result['elapsed_ms'])
                    print(f"⏱️  Frame TOTAL: {total_frame_ms + pred_result.get('elapsed_ms', 0):.0f}ms (target <400ms)")
                else:
                    print(f"⏱️  Frame TOTAL: {total_frame_ms:.0f}ms (target <400ms)")
            else:
                sent_fail += 1
                print(f"→ ❌ HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            sent_fail += 1
            print("→ ❌ CONNECTION REFUSED")
            if i == 0:
                if input("  Continue? (y/n): ").lower() != 'y': return
            continue
        except Exception as e:
            sent_fail += 1; print(f"→ ❌ {e}"); continue

    # Résumé
    gf = sum(1 for f in frames if f['metadata']['gps_valid'])
    print(f"\n{'═'*62}")
    print(f"  ✅ Replay terminé")
    print(f"  Frames: {total}  |  OK: {sent_ok}  |  Fail: {sent_fail}")
    print(f"  GPS valides: {gf}  |  GPS perdus: {total-gf}")
    if pred_times:
        print(f"{'─'*62}")
        print(f"  ⏱  Temps prédiction CV (N={len(pred_times)}):")
        print(f"     Min : {min(pred_times):.0f}ms")
        print(f"     Avg : {sum(pred_times)/len(pred_times):.0f}ms")
        print(f"     Max : {max(pred_times):.0f}ms")
        print(f"     Détail : {[f'{t:.0f}ms' for t in pred_times]}")
    print(f"{'═'*62}\n")


def main():
    p = argparse.ArgumentParser(description="NAVERA Replay v2 — Blocking GPS-Denied")
    p.add_argument('source')
    p.add_argument('--url',    '-u', default='http://localhost:5000/frame')
    p.add_argument('--status', '-S', default='http://localhost:5000/gps_status.json')
    p.add_argument('--speed',  '-s', type=float, default=1.0,
                   help='Vitesse frames GPS: 0.5=2x lent, 1=réel, 2=2x rapide')
    p.add_argument('--poll',   '-p', type=float, default=0.3,
                   help='Polling prédiction (secondes, default 0.3)')
    p.add_argument('--timeout','-t', type=int, default=30)
    args = p.parse_args()

    src = Path(args.source)
    if not src.exists():
        print(f"❌ Introuvable: {src}"); sys.exit(1)
    if src.suffix != '.zip':
        print("❌ Fournir un .zip"); sys.exit(1)

    frames = load_from_zip(src)
    if not frames:
        print("❌ Aucun frame"); sys.exit(1)

    gf = sum(1 for f in frames if f['metadata']['gps_valid'])
    breaks = []
    prev = True
    for f in frames:
        curr = f['metadata']['gps_valid']
        if prev and not curr:
            breaks.append(f"#{f['metadata']['frame_id']:04d}")
        prev = curr

    total_t = sum(f['delta_t'] for f in frames)
    print(f"\n  📋 Mission: {len(frames)} frames")
    print(f"     GPS valides : {gf} 📍")
    print(f"     GPS perdus  : {len(frames)-gf} ⚠️  ({', '.join(breaks)})")
    print(f"     Durée réelle: {total_t:.0f}s")
    print(f"     Durée replay: ~{total_t/args.speed:.0f}s frames GPS + temps CV blocage")
    print(f"\n  ⚠️  BLOQUANT sur GPS-DENIED : le replay attend la prédiction CV")
    print(f"     avant chaque frame suivant.")
    print()
    input("  Appuie sur Entrée pour démarrer... ")

    replay(frames, args.url, args.status, args.speed, args.timeout, args.poll)

if __name__ == '__main__':
    main()
