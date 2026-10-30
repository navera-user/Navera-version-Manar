"""Step 10 (teacher's solution): how many metres does the wrong fix add to the length?"""
from navera_lite.track import Track, load_track

tr = load_track("/data/academy/03-python-basics/harbour_track.csv")
bad = tr.glitches(20.0)[0]                       # the first listed position is the wrong fix
clean = Track("clean")
for i in range(len(tr)):
    if i != bad:
        clean.add(tr.t_s[i], tr.e_m[i], tr.n_m[i])
print(f"{tr.length_m():.1f} m with it, {clean.length_m():.1f} m without: "
      f"GLITCH_EXTRA_M = {tr.length_m() - clean.length_m():.1f}")
