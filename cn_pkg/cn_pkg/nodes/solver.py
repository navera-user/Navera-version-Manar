import subprocess
import os
import sys
import re
import tempfile
import base64

CFG = os.path.join(os.path.dirname(__file__), 'astrometry.cfg')
# Real geolocation solver (RA/Dec + tilt/azimuth + UTC → ground lat/lon).
DRONE_SKY_PREP = os.path.join(os.path.dirname(__file__), 'drone_sky_prep.py')

def solve_image_b64(image_b64: str) -> dict:
    img_bytes = base64.b64decode(image_b64)
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, 'frame.jpg')
        with open(img_path, 'wb') as f:
            f.write(img_bytes)
        cmd = [
            'solve-field',
            '--config', CFG,
            '--no-plots',
            '--no-verify',
            '--overwrite',
            '--dir', tmpdir,
            '--scale-units', 'degwidth',
            '--scale-low', '50',
            '--scale-high', '70',
            img_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        wcs_path = img_path.replace('.jpg', '.wcs')
        if not os.path.exists(wcs_path):
            return {'success': False, 'error': result.stderr[-500:]}
        from astropy.wcs import WCS
        from astropy.io import fits
        with fits.open(wcs_path) as hdul:
            h = hdul[0].header
            ra  = float(h.get('CRVAL1', 0))
            dec = float(h.get('CRVAL2', 0))
        lat = dec
        lon = (ra - 180.0) % 360 - 180.0
        return {
            'success': True,
            'ra_deg': ra,
            'dec_deg': dec,
            'predicted_lat': lat,
            'predicted_lon': lon,
            'source': 'stellar',
            'match_score': 0.99
        }


def solve_image_b64_geoloc(image_b64: str, tilt: float, azimuth: float,
                           utc_time: str) -> dict:
    """Real celestial geolocation.

    Runs drone_sky_prep.py (astrometry RA/Dec + observer tilt/azimuth + UTC
    time → ground latitude/longitude) and parses its position output. Unlike
    solve_image_b64() — which maps lat=Dec/lon=f(RA) as a rough placeholder —
    this returns a genuine ground fix.

    Args:
        image_b64: base64-encoded JPEG of the sky.
        tilt:      camera degrees above horizon (90 = straight up).
        azimuth:   compass heading the camera points at (0=N, 90=E, ...).
        utc_time:  "YYYY-MM-DD HH:MM:SS" of the exposure (UTC).
    """
    img_bytes = base64.b64decode(image_b64)
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, 'frame.jpg')
        with open(img_path, 'wb') as f:
            f.write(img_bytes)

        try:
            date_str, time_str = utc_time.split(' ')
        except ValueError:
            return {'success': False, 'error': f'bad utc_time: {utc_time!r}'}

        cmd = [sys.executable, DRONE_SKY_PREP, img_path, date_str, time_str,
               str(tilt), str(azimuth)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=300)
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'drone_sky_prep timeout (300s)'}

        out = result.stdout
        lat = lon = ra = dec = None
        for line in out.splitlines():
            if 'Latitude' in line:
                m = re.search(r'([-+]?\d+\.?\d*)\s*°?\s*([NS])?', line.split(':', 1)[-1])
                if m:
                    lat = float(m.group(1))
                    if m.group(2) == 'S':
                        lat = -lat
            elif 'Longitude' in line:
                m = re.search(r'([-+]?\d+\.?\d*)\s*°?\s*([EW])?', line.split(':', 1)[-1])
                if m:
                    lon = float(m.group(1))
                    if m.group(2) == 'W':
                        lon = -lon
            elif re.search(r'\bRA\b', line) and ':' in line:
                m = re.search(r'([-+]?\d+\.?\d*)', line.split(':', 1)[-1])
                if m:
                    ra = float(m.group(1))
            elif re.search(r'\bDec\b', line) and ':' in line:
                m = re.search(r'([-+]?\d+\.?\d*)', line.split(':', 1)[-1])
                if m:
                    dec = float(m.group(1))

        if lat is None or lon is None:
            return {
                'success': False,
                'error': 'drone_sky_prep could not solve',
                'stdout': out[-500:],
                'stderr': result.stderr[-300:],
            }

        return {
            'success': True,
            'ra_deg': ra,
            'dec_deg': dec,
            'predicted_lat': lat,
            'predicted_lon': lon,
            'source': 'stellar',
            'match_score': 0.95,
        }
