"""Hardware in the loop (navera_tools/isaac/hil_flight.sh): the real box fed by the Isaac Sim PC.

The pieces that can be checked without the PC: the network NMEA receiver the box's network GPS
source reads, the box's recorder (tegrastats parsing), the summariser's join of the box's frames
to the PC's camera stream (exposure times, latency stages, restarts) and the staged-stack options
hil_flight.sh relies on (deploy/stage_check.sh --env-extra / --nice / --kill none).
"""
import csv
import json
import os
import socket
import subprocess
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'navera_tools', 'sim'))
sys.path.insert(0, os.path.join(REPO, 'navera_tools', 'isaac'))

from nmea_gps import NmeaGps  # noqa: E402

TEGRA = ('10-22-2026 15:42:58 RAM 2529/7607MB (lfb 2x4MB) SWAP 1525/20188MB (cached 76MB) '
         'CPU [39%@1728,99%@1728,27%@1728,37%@1728,56%@729,29%@729] GR3D_FREQ 10% cpu@55.656C '
         'soc2@53.75C soc0@54.375C gpu@55.093C tj@55.656C soc1@54.593C VDD_IN 8029mW/8029mW')


def _read_lines(sock, n, timeout=3.0):
    sock.settimeout(timeout)
    buf = b''
    t0 = time.time()
    while buf.count(b'\n') < n and time.time() - t0 < timeout:
        buf += sock.recv(4096)
    return buf.decode().splitlines()


def test_nmea_over_tcp_reaches_every_client():
    gps = NmeaGps(seed=1)
    try:
        port = gps.serve_tcp(0, host='127.0.0.1')
        a = socket.create_connection(('127.0.0.1', port), 2)
        b = socket.create_connection(('127.0.0.1', port), 2)
        time.sleep(0.2)                                   # accepted
        gps.tick(35.8685, 10.5352, 289.0, 10.0, 90.0, 0.2)
        la, lb = _read_lines(a, 2), _read_lines(b, 2)
        assert [x[:6] for x in la] == ['$GPGGA', '$GPRMC'] == [x[:6] for x in lb]
        assert ',1,12,' in la[0]                         # a fix, 12 satellites
        gps.set_mode('jammed')                           # after the cut: talking, no fix
        gps.tick(35.8685, 10.5352, 289.0, 10.0, 90.0, 0.2)
        lj = _read_lines(a, 2)
        assert ',0,00,' in lj[0] and ',V,' in lj[1]
        b.close()                                        # a client leaving never stops the others
        for _ in range(3):
            gps.tick(35.8685, 10.5352, 289.0, 10.0, 90.0, 0.2)
        assert _read_lines(a, 2)
        a.close()
    finally:
        gps.close()


def test_tegrastats_line_parsed():
    try:                                                  # hil_record is a ROS node (built workspace)
        from hil_record import parse_tegrastats
    except ImportError as e:
        pytest.skip(f'navera_msgs not built: {e}')
    d = parse_tegrastats(TEGRA)
    assert d['ram_mb'] == 2529 and d['swap_mb'] == 1525
    assert d['cpu_max'] == 99 and d['cpu_avg'] == pytest.approx(47.8, abs=0.1)
    assert d['gpu'] == 10 and d['t_tj'] == pytest.approx(55.656) and d['t_gpu'] == pytest.approx(55.093)
    assert d['vdd_in_mw'] == 8029


def _write(path, header, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(header.split(','))
        w.writerows(rows)


def test_summary_joins_frames_to_the_pc_stream(tmp_path):
    """Two frames: exposure from the PC's stream.csv, latency stages, delivery to the autopilot."""
    import hil_summarise as hs
    r = str(tmp_path)
    t0, off = 1000.0, 0.5                               # PC t0; PC clock = box clock + 0.5 s
    json.dump(dict(t0_pc=t0, pc_offset_s=off), open(os.path.join(r, 'hil_t0.json'), 'w'))
    open(os.path.join(r, 'gps_cut'), 'w').write('10.0')
    # the truth: flying north at 10 m/s from (35.8685, 10.5352)
    _write(os.path.join(r, 'truth.csv'), 't,lat,lon,alt,rel',
           [[t, 35.8685 + 10.0 * t / 111320.0, 10.5352, 289, 250] for t in range(0, 60)])
    # exposures at t=20 and 21 s, sent 1.3 s later (PC clock)
    _write(os.path.join(r, 'stream.csv'), 'wall,t_exposure,n', [[t0 + 21.3, 20.0, 0], [t0 + 22.3, 21.0, 1]])
    # the box grabbed them 50 ms after sending (box clock = PC - 0.5), frame_meta 30 ms later
    _write(os.path.join(r, 'hil_meta.csv'), 'frame,grab_box,meta_rx_box,usable,reason',
           [[7, t0 + 21.35 - off, t0 + 21.38 - off, 1, ''], [8, t0 + 22.35 - off, t0 + 22.38 - off, 1, '']])
    _write(os.path.join(r, 'proc.csv'), 't,frame,proc_ms', [[21.9, 7, 500], [22.9, 8, 520]])
    lat7 = 35.8685 + 200.0 / 111320.0                    # frame 7: exactly the truth at its exposure
    lat8 = 35.8685 + 230.0 / 111320.0                    # frame 8: 20 m north of it
    _write(os.path.join(r, 'day.csv'), 't,frame,lat,lon,mode,valid,sigma_m,err_m,err_frame_m,t_exposure,proc_ms,reason',
           [[21.35, 7, f'{lat7:.7f}', '10.5352000', 'measured', 1, 15, 13, 'nan', 'nan', 500, ''],
            [22.35, 8, f'{lat8:.7f}', '10.5352000', 'measured', 1, 15, 33, 'nan', 'nan', 520, '']])
    _write(os.path.join(r, 'hil_day.csv'), 'rx_box,sensor_box,frame,valid,mode',
           [[t0 + 21.9 - off, t0 + 21.35 - off, 7, 1, 'measured'], [t0 + 22.9 - off, t0 + 22.35 - off, 8, 1, 'measured']])
    _write(os.path.join(r, 'hil_pos.csv'), 'rx_box,header_box,sensor_box,source,mode,valid,frame',
           [[t0 + 21.91 - off, 0, 0, 'day', 'measured', 1, 7], [t0 + 22.92 - off, 0, 0, 'day', 'measured', 1, 8]])
    _write(os.path.join(r, 'position.csv'), 't,lat,lon,source,mode,valid,sigma_m,truth_lat,truth_lon,err_m,gps',
           [[21.35, f'{lat7:.7f}', '10.5352000', 'day', 'measured', 1, 15, 0, 0, 13, 'cut'],
            [22.35, f'{lat8:.7f}', '10.5352000', 'day', 'measured', 1, 15, 0, 0, 33, 'cut']])
    # the autopilot's GPS showed frame 7's position 40 ms after the box published it
    _write(os.path.join(r, 'sitl_gps.csv'), 'wall,t,lat,lon,fix_type,sats,eph',
           [[t0 + 21.95, 21.95, f'{lat7:.7f}', '10.5352000', 3, 0, 1500]])
    truth = hs.Truth(os.path.join(r, 'truth.csv'))
    frames = hs.join_exposure(r, off, t0, truth)
    assert sorted(frames) == [7, 8] and frames[7]['t_exp'] == 20.0
    day = {int(x['frame']): x for x in csv.DictReader(open(os.path.join(r, 'day.csv')))}
    assert float(day[7]['err_frame_m']) < 0.5 and abs(float(day[8]['err_frame_m']) - 20.0) < 0.5
    assert os.path.exists(os.path.join(r, 'day_box.csv'))          # the box's raw record is kept
    lat = hs.latency(r, frames, off, t0, 10.0)
    assert lat['transport_ms']['median'] == pytest.approx(50, abs=1)
    assert lat['camera_ms']['median'] == pytest.approx(30, abs=1)
    assert lat['estimator_ms']['n'] == 2
    assert lat['exposure_to_position_s']['median'] == pytest.approx(1.92, abs=0.05)
    assert lat['position_to_autopilot_ms']['n'] == 1
    assert lat['position_to_autopilot_ms']['median'] == pytest.approx(40, abs=2)


def test_restart_recovery_measured(tmp_path):
    import hil_summarise as hs
    r = str(tmp_path)
    json.dump(dict(t0_pc=0.0, pc_offset_s=0.0), open(os.path.join(r, 'hil_t0.json'), 'w'))
    with open(os.path.join(r, 'hil_kills.jsonl'), 'w') as f:
        f.write(json.dumps(dict(unit='navera-estimator', box=100.0, pid=1, restarted=True)) + '\n')
    _write(os.path.join(r, 'hil_pos.csv'), 'rx_box,header_box,sensor_box,source,mode,valid,frame',
           [[99.0, 0, 0, 'day', 'measured', 1, 1], [99.6, 0, 0, 'day', 'measured', 1, 2],
            [114.2, 0, 0, 'day', 'measured', 1, 3]])
    _write(os.path.join(r, 'sitl_gps.csv'), 'wall,t,lat,lon,fix_type,sats,eph',
           [[101.0, 0, 0, 0, 3, 0, 0], [103.5, 0, 0, 0, 1, 0, 0], [115.0, 0, 0, 0, 3, 0, 0]])
    k = hs.restarts(r, 0.0)[0]
    assert k['position_back_after_s'] == pytest.approx(14.2)
    assert k['position_gap_s'] == pytest.approx(14.6)
    assert k['autopilot_gps'] == dict(lost_after_s=3.5, back_after_s=15.0)
    assert k['output_max_gap_s'] is None                    # no /navera/fix record (older runs)


def test_restart_gap_given_to_the_autopilot_measured(tmp_path):
    """B23: hil_out.csv (/navera/fix, the output's decision) gives the longest time the autopilot
    went without a position around each kill, and when it was first told "no fix"."""
    import hil_summarise as hs
    r = str(tmp_path)
    json.dump(dict(t0_pc=0.0, pc_offset_s=0.0), open(os.path.join(r, 'hil_t0.json'), 'w'))
    with open(os.path.join(r, 'hil_kills.jsonl'), 'w') as f:
        f.write(json.dumps(dict(unit='navera-pipeline-day:day_subscriber', box=100.0, pid=1, node='day_subscriber.py',
                                restarted=True, how='respawn', active_after_s=1.2)) + '\n')
    _write(os.path.join(r, 'hil_pos.csv'), 'rx_box,header_box,sensor_box,source,mode,valid,frame',
           [[99.6, 0, 0, 'day', 'measured', 1, 2], [108.4, 0, 0, 'day', 'measured', 1, 3]])
    _write(os.path.join(r, 'sitl_gps.csv'), 'wall,t,lat,lon,fix_type,sats,eph', [[101.0, 0, 0, 0, 3, 0, 0]])
    _write(os.path.join(r, 'hil_out.csv'), 'rx_box,fix,sigma_m',
           [[99.6, 1, 12.0], [102.2, 1, 20.0], [103.2, 1, 25.0], [104.2, 1, 31.0], [108.5, 1, 12.0],
            [150.0, 0, 'nan']])
    k = hs.restarts(r, 0.0)[0]
    assert k['output_max_gap_s'] == pytest.approx(4.3)      # 104.2 -> 108.5: bridged up to there
    assert k['output_no_fix_after_s'] == pytest.approx(50.0)
    assert k['back_how'] == 'respawn' and k['node'] == 'day_subscriber.py' and k['autopilot_gps'] is None


STAGE_CHECK = os.path.join(REPO, 'deploy', 'stage_check.sh')


def test_stage_check_hil_options_documented_and_checked(tmp_path):
    h = subprocess.run(['bash', STAGE_CHECK, '--help'], capture_output=True, text=True, timeout=30).stdout
    for opt in ('--env-extra FILE', '--nice N', '"none": no restart test'):
        assert opt in h
    bad = subprocess.run(['bash', STAGE_CHECK, '--nice', 'x'], capture_output=True, text=True, timeout=30)
    assert bad.returncode == 2 and 'not a number' in bad.stderr
    missing = subprocess.run(['bash', STAGE_CHECK, '--env-extra', str(tmp_path / 'nope.env')],
                             capture_output=True, text=True, timeout=30)
    assert missing.returncode == 2 and 'not readable' in missing.stderr
