# Lab 3 — Mission planner's report

## Wind triangle

The wind blows 5 m/s towards the south-west, so on the outbound track 030° it is almost a
headwind with a small push to the left. To stay on the track, the quad must fly a heading of
32.9°, about 2.9° to the right of the track. Its ground speed is only 7.0 m/s out, and
16.9 m/s back, because the headwind becomes a tailwind.

## Endurance and round trip

With 160 Wh, 350 W and a 20 % reserve the quad has 21.9 minutes of endurance, but the round
trip takes 30.2 min, so it cannot do the mission. The fixed wing needs 16.0 min and has
32.7 min of endurance, so it can do it; it needs about 71 m of radius to turn at 30° of bank.

## Track analysis

The survey track has 263 points and is 3270 m long. The median speed is 12.1 m/s, which is
the real cruise speed, but the maximum is 54.3 m/s: impossible for this quad. It comes from
a glitch at t = 150 s, a fix about 40 m off the route. The glitch adds roughly 80 m to the
length and makes the maximum speed useless, so the median is the better summary.
