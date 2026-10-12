"""Builds courses/01-welcome/assets/cold_open.svg: a 15 s looping SMIL animation (no script),
so it plays inside the lesson page as a normal image."""
import math, sys
out = sys.argv[1]
T = 15                                    # seconds per loop
Y0, X0, X1 = 240, 30, 670
START, CATCH = 0.40, 0.72
def x_at(u): return X0 + u * (X1 - X0)
xs, xc = x_at(START), x_at(CATCH)
DRAG = 112                                # px north at the catch
yc = Y0 - DRAG
L1 = xs - X0; L2 = math.hypot(xc - xs, DRAG); L = L1 + L2
def anim(attr, values, key_times, mode="linear"):
    return (f'<animate attributeName="{attr}" dur="{T}s" repeatCount="indefinite" calcMode="{mode}" '
            f'values="{values}" keyTimes="{key_times}"/>')
def window(t0, t1):
    """opacity 1 between t0 and t1 (fractions of the loop), else 0"""
    if t0 <= 0:
        return anim("opacity", "1;0", f"0;{t1}", "discrete")
    if t1 >= 1:
        return anim("opacity", "0;1", f"0;{t0}", "discrete")
    return anim("opacity", "0;1;0", f"0;{t0};{t1}", "discrete")
caps = [(0, .40, "A survey drone flies along the coast. Its GPS looks perfect."),
        (.40, .52, "Over the sea, a spoofer drags the GPS north, 2 metres every second."),
        (.52, .62, "No jump, no alarm. Out here, nothing can check the GPS."),
        (.62, .72, "At the coast, the camera finds the map again…"),
        (.72, .90, "…and NAVERA catches the lie: 391 m off."),
        (.90, 1, "Today you do both: the attack, and the catch.")]
errs = [(0, .40, "0 m"), (.40, .48, "≈ 50 m"), (.48, .56, "≈ 150 m"), (.56, .64, "≈ 250 m"), (.64, .72, "≈ 350 m"), (.72, 1, "391 m")]
s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 420" font-family="Inter, Segoe UI, sans-serif">',
     '<defs><linearGradient id="sea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#1d4e6b"/><stop offset="1" stop-color="#13284a"/></linearGradient>',
     '<radialGradient id="glow"><stop offset="0" stop-color="#ff8f7a" stop-opacity=".9"/><stop offset="1" stop-color="#ff8f7a" stop-opacity="0"/></radialGradient></defs>',
     '<rect width="720" height="420" fill="#0b1730"/><rect width="720" height="360" fill="url(#sea)"/>',
     '<path d="M0 360 L0 205 C60 196 120 214 190 206 C215 204 228 214 236 230 L236 360 Z" fill="#2f5a4d"/>',
     '<path d="M484 360 L484 232 C494 214 512 206 540 208 C610 214 660 196 720 204 L720 360 Z" fill="#2f5a4d"/>',
     '<path d="M0 205 C60 196 120 214 190 206 C215 204 228 214 236 230" fill="none" stroke="#f6c7a8" stroke-width="2" opacity=".7"/>',
     '<path d="M484 232 C494 214 512 206 540 208 C610 214 660 196 720 204" fill="none" stroke="#f6c7a8" stroke-width="2" opacity=".7"/>',
     '<text x="40" y="285" fill="#cfe3d9" font-size="13" opacity=".85">land: vision matches</text>',
     '<text x="292" y="305" fill="#9fc4d8" font-size="13" opacity=".85">sea: no vision match</text>',
     '<text x="556" y="285" fill="#cfe3d9" font-size="13" opacity=".85">land again</text>',
     '<text x="20" y="28" fill="#ffb3a3" font-size="11.5" font-weight="700" letter-spacing="3">MISSION 01 · GHOST POSITION</text>',
     '<circle cx="28" cy="50" r="5" fill="#ff8f7a" stroke="#fff" stroke-width="1.5"/><text x="40" y="54" fill="#e8f0f5" font-size="12.5">where the GPS says you are</text>',
     '<path d="M23 72 L33 72 M28 67 L28 77" stroke="#7fe0d3" stroke-width="2.5" stroke-linecap="round"/><text x="40" y="76" fill="#e8f0f5" font-size="12.5">where the drone really is</text>',
     f'<line x1="{X0}" y1="{Y0}" x2="700" y2="{Y0}" stroke="#7fe0d3" stroke-width="2" stroke-dasharray="6 6" opacity=".55"/>',
     # gps trail drawn progressively
     f'<path d="M{X0} {Y0} L{xs:.1f} {Y0} L{xc:.1f} {yc}" fill="none" stroke="#ff8f7a" stroke-width="2.5" stroke-dasharray="{L:.1f}" stroke-dashoffset="{L:.1f}">'
     + anim("stroke-dashoffset", f"{L:.1f};{L - L1:.1f};0;0", f"0;{START};{CATCH};1") + '</path>',
     # gap line after the catch
     f'<line x1="{xc:.1f}" y1="{Y0}" x2="{xc:.1f}" y2="{yc}" stroke="#ffd166" stroke-width="1.5" stroke-dasharray="3 4" opacity="0">' + window(CATCH, 1) + '</line>',
     # drone
     '<g><g>' + '<circle r="18" fill="#7fe0d3" opacity=".18"/><path d="M-9 0 L9 0 M0 -9 L0 9" stroke="#7fe0d3" stroke-width="3" stroke-linecap="round"/>'
     + ''.join(f'<circle cx="{a}" cy="{b}" r="4" fill="none" stroke="#7fe0d3" stroke-width="2"/>' for a, b in ((-9, 0), (9, 0), (0, -9), (0, 9)))
     + f'<animateTransform attributeName="transform" type="translate" dur="{T}s" repeatCount="indefinite" values="{X0} {Y0};{X1} {Y0}"/></g></g>',
     # gps dot
     '<g><circle r="22" fill="url(#glow)"/><circle r="6" fill="#ff8f7a" stroke="#fff" stroke-width="2"/>'
     + f'<animateTransform attributeName="transform" type="translate" dur="{T}s" repeatCount="indefinite" '
       f'values="{X0} {Y0};{xs:.1f} {Y0};{xc:.1f} {yc};{xc:.1f} {yc}" keyTimes="0;{START};{CATCH};1"/></g>',
     # caught ring
     f'<g transform="translate({xc:.1f},{yc})" opacity="0"><circle r="26" fill="none" stroke="#ffd166" stroke-width="3"/>'
     f'<text x="32" y="6" fill="#ffd166" font-size="16" font-weight="700">CAUGHT</text>' + window(CATCH, 1) + '</g>',
     # HUD
     '<rect x="566" y="14" width="140" height="66" rx="12" fill="#0b1730" fill-opacity=".7" stroke="#ffffff" stroke-opacity=".15"/>',
     '<text x="694" y="34" text-anchor="end" fill="#cfe3ea" font-size="12" font-family="ui-monospace, Menlo, monospace">GPS error</text>']
for t0, t1, txt in errs:
    s.append(f'<text x="694" y="56" text-anchor="end" fill="#ff8f7a" font-size="18" font-weight="700" font-family="ui-monospace, Menlo, monospace" opacity="0">{txt}{window(t0, t1)}</text>')
s.append(f'<text x="694" y="72" text-anchor="end" fill="#7fe0d3" font-size="11.5" font-weight="700" font-family="ui-monospace, Menlo, monospace" opacity="0">GPS · FIX{window(0, CATCH)}</text>')
s.append(f'<text x="694" y="72" text-anchor="end" fill="#ffd166" font-size="11.5" font-weight="700" font-family="ui-monospace, Menlo, monospace" opacity="0">GPS · REFUSED{window(CATCH, 1)}</text>')
for t0, t1, txt in caps:
    s.append(f'<text x="22" y="398" fill="#ffffff" font-size="20" font-family="Fraunces, Georgia, serif" opacity="0">{txt}{window(t0, t1)}</text>')
s.append('</svg>')
open(out, "w").write("\n".join(s))
print("ok", out)
