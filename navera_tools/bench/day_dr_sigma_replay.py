"""Dead-reckoning sigma check on the real camera campaign: outages replayed on the logged vision fixes.

    python3 navera_tools/bench/day_dr_sigma_replay.py linear|quad     (env ACC, HDG, RAD)

Each run's vision errors are put on the circuit's true track (RAD m radius; RAD=1e9 = straight),
TrackVelocity is fed the fixes up to an instant, then propagated 5-60 s with the true heading change
(what the camera gyro gives); error vs stated sigma.
"""
import csv, glob, math, os, re, sys, statistics as st
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0]=[os.path.join(ROOT,"navera_common"),os.path.join(ROOT,"day_pkg"),ROOT]
import numpy as np
from navera_common import track as T
from day_pkg.local_matcher import fix_sigma_m
from day_pkg.vision_nav import _move, _en
LAT0,LON0,R=35.82227,10.61691,float(os.environ.get("RAD","900"))
MPP=156543.03392*math.cos(math.radians(LAT0))/2**17
MODE=sys.argv[1] if len(sys.argv)>1 else "linear"
orig=T.TrackVelocity.propagate
def prop_quad(self, t_now, heading_change_deg=0.0):
    r=orig(self,t_now,heading_change_deg)
    if r is None: return r
    ve,vn,sig_v=self.velocity(t_now); t_last,lat,lon,sig0=self._pts[-1]; dt=t_now-t_last; sp=math.hypot(ve,vn)
    sig=math.sqrt(sig0**2+(sig_v*dt)**2+(self.heading_sigma*sp*dt)**2+(0.5*self.accel*dt*dt)**2+(0.5*abs(math.radians(heading_change_deg or 0))*sp*dt)**2)
    return r[0],r[1],sig
if MODE=="quad": T.TrackVelocity.propagate=prop_quad
res={dt:[] for dt in (5,10,20,40,60)}
for p in sorted(glob.glob(os.path.expanduser("~/navera-field/day_real_2026-10-19/*_v*.csv"))):
    n=os.path.basename(p)
    if n.startswith(("night","worst")): continue
    v=float(re.search(r"_v(\d+)\.csv",n).group(1)); w=v/R
    rows=list(csv.DictReader(open(p)))
    g=[r for r in rows if r["phase"]=="gps" and r["vis_de"] not in("","None")]
    if len(g)<3: continue
    ax=(st.median(float(r["vis_de"]) for r in g), st.median(float(r["vis_dn"]) for r in g))
    fx=[(float(r["t"]), float(r["vis_de"])-ax[0], float(r["vis_dn"])-ax[1], int(float(r["inliers"] or 0))) for r in rows if r["vis_de"] not in("","None")]
    truth=lambda t:_move((LAT0,LON0),R*math.sin(w*t),R*(1-math.cos(w*t)))
    tend=fx[-1][0]
    for k in range(10,len(fx),6):
        t0=fx[k][0]
        tv=T.TrackVelocity(accel_mps2=float(os.environ.get("ACC","0.5")), heading_sigma_deg=float(os.environ.get("HDG","5")))
        for t,de,dn,inl in fx[:k+1]:
            z=_move(truth(t),de,dn); tv.add(t,z[0],z[1],fix_sigma_m(inl,MPP))
        for dt in res:
            if t0+dt>tend+60: continue
            out=tv.propagate(t0+dt,-math.degrees(w*dt))
            if out is None: continue
            err=math.hypot(*_en(out[:2],truth(t0+dt))); res[dt].append((err,out[2]))
for dt,L in res.items():
    e=np.array([a for a,_ in L]); s=np.array([b for _,b in L])
    print(f"{MODE} dt {dt:3d}s n={len(L):4d} err med {np.median(e):6.1f} p95 {np.percentile(e,95):6.1f} | sigma med {np.median(s):6.1f} | within 3 sigma {np.mean(e<=3*s):.3f} | ratio sig/err med {np.median(s/np.maximum(e,0.1)):.1f}")
