# Lab 24 — report

Write each section in your own words (at least 40 words each). Quote the numbers your programs
printed (they are also in results.json). Delete the comment lines `<!-- ... -->` if you like:
the check ignores them.

## Sidereal time

<!-- How far is your GMST from astropy's (arcseconds)? What is the difference between GMST and
NAVERA's GAST (in seconds of time), what causes it, and how many km of longitude would it cost
if you ignored it? -->

## Polaris

<!-- Worst latitude error over a whole night from Muscat with "latitude = altitude", and with the
p·cos(H) correction. What else would a real sextant or camera measurement need to correct
(hint: the atmosphere bends light near the horizon)? -->

## Error budget

<!-- Your Monte Carlo median and p90 for the camera at 75° and at 90°. Why does the heading error
hardly matter when the camera points straight up? Compare with docs/VALIDATION_STATUS.md
("24-119 km, ~50 km typical"). What clock accuracy is needed so that the clock is not the
limit? -->

## Night geometry

<!-- The minimum flying height for 85 % coverage at heading 0° and at 45° (84° camera), and for
the 56.7° x 48° camera. Compare with VALIDATION_STATUS.md (0.77 at 300 m diagonal, ~350 m,
~480 m). Which motion-gate decision did you see, and why is the gate needed at all? -->

## The night replay set

<!-- What did find_day_twin show (best and second-best NCC, the frame-number offset)? What does
it mean for the positions written in the night frames' file names? What would you need to
validate NAVERA's night vision for real? -->
