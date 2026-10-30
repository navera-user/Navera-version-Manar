# Audit memo — NAVERA's long-route bugs, and which Earth model to use where

## Route length (R-6)

The server measured the Paris → central Tunisia route with a flat approximation and said 1750 km. The
closest of my three candidates is a flat formula with cos of the START latitude (Paris, 48.85°): 1746.9 km
on the sphere (1748.9 km with 111 320 m per degree); the last 1–3 km are not explained by my end points. Paris is the northernmost point, so the east–west part is shrunk too much. With the mean latitude
the flat length is 1769.7 km, and the great circle (haversine) gives 1767.8 km, the length NAVERA now uses.
A bug report should say: "flat length with cos(start latitude) is 21 km short on a 1768 km route; use the
great-circle distance".

## Corridor (R-2)

The great circle bends towards the pole: it passes north-east of the straight lat/lon line and is up to
34.2 km away from it near the middle of the route. A ±1 km corridor around the straight line therefore
covered the real path only near the two ends, which matches the backlog's report that only a small part
of the downloaded tiles was on the real path. Cutting the route into great-circle legs of about 10 km
brings the gap down to about 1.09 m per leg, far inside the corridor.

## Which model, where

My error study compares my flat enu_flat with the exact WGS84 ENU frame. At Sousse the flat error
reaches 1 m at 477.4 m from home and 10 m at about 4.9 km. Near home the error grows like the distance
(slope 1): it is the sphere's radius, 0.2 % wrong at Sousse, not the curvature. Far away (above
100 km) the slope becomes 2 and the curvature dominates. For a drone flying 2 km around its home, a flat
frame is fine for steering if the same function converts both ways, but metres compared with real
metres (a jump gate, a stated σ) carry a few metres of error; using M and N of the home latitude
removes most of it. For a 300 km survey flight, use great-circle legs for planning and the exact
ellipsoid (or a frame re-centred often) for anything measured in metres.
