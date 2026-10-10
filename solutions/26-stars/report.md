# Lab 26 — report

## Sidereal time

My GMST from the Meeus formula is 316.47785 degrees, only 0.04 arcseconds from astropy's mean
sidereal time, so the formula and my Julian date are right. NAVERA's gast_deg gives the apparent
sidereal time, 0.52 seconds of time later: that is the equation of the equinoxes, caused by
nutation (the small nodding of the Earth's axis). 0.52 s of time is 7.8 arcseconds of rotation,
about 0.2 km of longitude here: small next to the attitude error, but free to correct, so NAVERA
uses GAST with apparent star positions.

## Polaris

From New York over a whole sidereal day, "latitude = altitude of Polaris" is wrong by up to 0.626
degrees, about 70 km, because Polaris turns around the pole on a small circle. With the first-order
correction altitude minus p cos(H) the worst error drops to 0.0029 degrees, 0.33 km. A real
measurement would also need the atmospheric refraction correction (about 1.2 arcminutes at 41 degrees
altitude, so about 2 km) and the dip of the horizon for a sextant.

## Error budget

With a BNO085-class IMU (0.3 degrees tilt, 1.5 degrees heading) and the camera at 75 degrees, the
Monte Carlo median error is 47.4 km and the p90 is 92.6 km, with no ambiguous fix. With the camera
straight up the median is 22.6 km: a heading error only rotates the picture around the zenith, so
the pointing direction does not change and only the tilt counts. This agrees with
VALIDATION_STATUS.md (24-119 km, about 50 km typical). The clock costs 0.35 km per second at
New York, so a clock good to one second (the DS3231 RTC) is far from being the limit.

## Night geometry

For a 640 x 480 thermal camera with an 84 degree field of view, 85 percent coverage of the 512 px
reference square needs 312 m at heading 0 and 333 m at heading 45, because the turned rectangle
leaves the square's corners empty. At 300 m and 45 degrees the coverage is 0.77, exactly the case
in VALIDATION_STATUS.md where tracking ran away. The 56.7 x 48 degree camera needs 473 m, close to
the documented 480 m. The motion gate rejected the 2194 m jump in 4 s (reach 150 m): STHN can be
confident and wrong, physics cannot.

## The night replay set

Every night frame correlates at about 0.90 with exactly one day frame and about 0.10 with all the
others, and the twin is always day frame number + 8 (modulo 30). So the "thermal" frames are
darkened copies of the day replay frames, which are known to show other places than their labels.
The positions in their file names cannot be used as ground truth. A real validation needs a real
thermal camera flown with GPS logging, at night, at a height where the footprint covers the
reference.
