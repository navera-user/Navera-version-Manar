import base64
import math
import os
import re
import signal
import subprocess
import sys
import tempfile

CFG = os.path.join(os.path.dirname(__file__), 'astrometry.cfg')
# Real geolocation solver (RA/Dec + tilt/azimuth + UTC → ground lat/lon).
DRONE_SKY_PREP = os.path.join(os.path.dirname(__file__), 'drone_sky_prep.py')


def _run_group(cmd, timeout_s):
    """Run cmd in its own process group; on timeout kill the WHOLE group.

    solve-field and siril start helper processes (astrometry-engine, ...);
    killing only the direct child used to leave them running on the CPU.
    Returns (returncode, stdout, stderr, timed_out).
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return proc.returncode, out, err, True


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
            # astrometry.net's line removal runs a numpy.bool script that fails on
            # NumPy >= 1.24 (found on a real sky photo); the geoloc path skips it too
            '--no-remove-lines', '--uniformize', '0',
            img_path
        ]
        _, _, err, timed_out = _run_group(cmd, 300)
        if timed_out:
            return {'success': False, 'error': 'solve-field timeout (300s)'}
        wcs_path = img_path.replace('.jpg', '.wcs')
        if not os.path.exists(wcs_path):
            return {'success': False, 'error': err[-500:]}
        from astropy.io import fits
        with fits.open(wcs_path) as hdul:
            h = hdul[0].header
            ra = float(h.get('CRVAL1', 0))
            dec = float(h.get('CRVAL2', 0))
        # RA/Dec is where the camera points in the SKY, not a ground position:
        # never report it as a fix.
        return {
            'success': False,
            'ra_deg': ra,
            'dec_deg': dec,
            'error': 'wcs mode gives sky coordinates only (use geoloc for a position)',
            'source': 'stellar',
        }


def solve_image_b64_geoloc(image_b64: str, tilt: float, azimuth: float,
                           utc_time: str, prior_lat: float = float('nan'),
                           prior_lon: float = float('nan'),
                           fov_deg: float = float('nan'), up_cam=None) -> dict:
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
        prior_lat: approximate latitude used to pick between the two positions
                   one sky direction is consistent with (NaN = none).
        prior_lon: approximate longitude, same use as prior_lat (NaN = none).
        fov_deg:   horizontal field of view of the star camera (NaN = unknown,
                   slower wide search).
        up_cam:    'up' (3 values) in the camera's optical frame (x right, y down,
                   z along the axis) from the IMU's roll/pitch and the camera's full
                   mounting: the fix then uses the plate solve's whole rotation, no
                   compass, no prior (B11); tilt/azimuth are only reported.
    """
    img_bytes = base64.b64decode(image_b64)
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, 'frame.jpg')
        with open(img_path, 'wb') as f:
            f.write(img_bytes)

        try:
            # "YYYY-MM-DD HH:MM:SS", also ISO 8601 as the live camera writes it
            # ("YYYY-MM-DDTHH:MM:SS[.fff][Z]"); whole seconds (0.5 s of sky turn = 230 m)
            date_str, time_str = str(utc_time).strip().rstrip('Z').replace('T', ' ').split(' ')
            time_str = time_str.split('.')[0]
        except ValueError:
            return {'success': False, 'error': f'bad utc_time: {utc_time!r}'}

        cmd = [sys.executable, DRONE_SKY_PREP, img_path, date_str, time_str,
               str(tilt), str(azimuth)]
        if math.isfinite(fov_deg):
            cmd.append(str(fov_deg))
        if prior_lat == prior_lat:          # not NaN
            cmd += ['--prior-lat', str(prior_lat)]
        if prior_lon == prior_lon:
            cmd += ['--prior-lon', str(prior_lon)]
        if up_cam is not None:
            cmd += ['--up-cam', ','.join(f'{float(v):.9f}' for v in up_cam)]
        _, out, err, timed_out = _run_group(cmd, 300)
        if timed_out:
            return {'success': False, 'error': 'drone_sky_prep timeout (300s)'}
        log_odds = None
        lat = lon = ra = dec = None
        method, R_icrs_cam = None, None
        for line in out.splitlines():
            if 'Method' in line and ':' in line:
                method = line.split(':', 1)[-1].strip().split(' ')[0]
                continue
            if 'R_icrs_cam' in line:
                try:
                    R_icrs_cam = [float(v) for v in line.split(':', 1)[-1].split(',')]
                except ValueError:
                    R_icrs_cam = None
                continue
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
            elif 'Log-odds' in line:
                m = re.search(r'([-+]?\d+\.?\d*)', line.split(':', 1)[-1])
                if m:
                    log_odds = float(m.group(1))
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
                'stderr': err[-300:],
            }

        return {
            'success': True,
            'ra_deg': ra,
            'dec_deg': dec,
            'predicted_lat': lat,
            'predicted_lon': lon,
            'source': 'stellar',
            # astrometry.net's own confidence in the star match (log-odds);
            # it says nothing about the attitude or time used afterwards.
            'log_odds': log_odds,
            # "zenith" (camera rotation + IMU up, no compass) or "boresight" (tilt + compass azimuth)
            'method': method,
            'R_icrs_cam': R_icrs_cam,
        }
