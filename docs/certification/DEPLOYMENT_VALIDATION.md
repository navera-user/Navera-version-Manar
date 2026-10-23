# NAVERA — Deployment validation

Two levels: what was validated on 2026-10-21 **without root and without a deployed box**
(staged), and the **exact commands** to validate a production unit (root, real reboot). The
staged validation does not replace the reboot test (DEP-14 stays open until it is run).

## 1. Staged validation — result 2026-10-21: PASS

Run on the development Jetson (Orin Nano, JetPack 6.2.1), branch `work/cert-deploy-2026-10-21`,
with the running `navera-field` / `navera-academy` / `navera-netkeeper` system services left
untouched, no camera opened, no hardware probed:

```bash
# data paths for the day pipeline's replay camera (else the day pipeline is not staged)
export NAVERA_MBTILES=... DAY_DATASET_DIR=... TORCH_HOME=... NAVERA_DAY_CSV=... NAVERA_DAY_IMAGES_DIR=...
NAVERA_STAGE_DAY_CPU=1 deploy/stage_check.sh --stage <dir> \
    --kill navera-estimator --kill navera-gps --kill navera-pipeline-day
```

| Step | Tool | Result |
|---|---|---|
| 1. Staged install | `deploy/install.sh --root <dir>` (new; the real install is unchanged: its `--dry-run` output is byte-identical to the previous script for three option sets) | PASS — code synced, 12 packages built in 55 s, units enabled with `systemctl --root`, sudoers checked with `visudo -c -f` |
| 2. Unit checks | `deploy/verify_units.py --root <dir>` (new) | PASS — 160 checks, 0 WARN, 0 FAIL: `systemd-analyze verify` on all 11 units, every ExecStart executable, every `ros2 launch` file and `ros2 run` executable present in the build, every setting a wrapper reads documented in `navera.env.example`, `Restart=always` + `StartLimitIntervalSec=0`, day/night `Conflicts=`, sudoers syntax, mode 0440 and the units it may restart. A negative test (wrapper removed, `Restart=on-failure`, unknown key) gave 5 FAIL as expected |
| 3. Stack up | 8 staged user units `navera-stage-*` (estimator, gps, imu, rtc, vehicle-link, output, web, pipeline-day) + a simulated vehicle GPS, ROS domain 87, localhost only, web on :8281 | PASS — `check_boot.py --user --prefix navera-stage-`: 8 PASS / 0 FAIL, every unit active with its ROS node 35 s after start; IMU, clock and vehicle link idle by design (no device); `/navera/nav_status`: state FIX, source GPS, "GPS fix"; `/health` HTTP 200 |
| 4. Restart | the ROS node of a unit killed with SIGKILL by PID | PASS — estimator restarted by systemd 12 s after the kill, node back and check PASS at 32 s; GPS 12 s / 20 s; day pipeline 22 s / 42 s; NRestarts 0 → 1 each |
| 5. Clean-up | units stopped, runtime links and unit files removed | PASS — 0 staged units left |

Choices and limits of the staged run, stated plainly:

- The day pipeline ran **on the CPU** (`CUDA_VISIBLE_DEVICES` empty → matcher falls back to SIFT,
  DINOv2 on CPU): the shared GPU lock was held by other jobs. A first run with the GPU lock
  waited 420 s behind them and failed on that unit only. The GPU path of the unit is covered by
  the production procedure below.
- The GPS was a simulated vehicle fix through NAVERA's real ROS GPS source
  (`NAVERA_GPS_SOURCE=ros`, `deploy/stage/fake_vehicle_gps.py`); serial GPS, I²C IMU / RTC,
  cameras and the autopilot link were not exercised (their "device absent" idle path was).
- `navera-discover` was **not run** (it probes serial ports, I²C and cameras); its unit passed the
  static checks only.
- User units differ from the product units only by: no `User=` / `Group=` /
  `SupplementaryGroups=`, staged paths, `Nice=19`, `WantedBy=default.target` — so the user
  account, group permissions on `/dev`, boot ordering at power-on and the sudoers rule *in use*
  are **not** validated here.
- Not a reboot and not a power cut.

Re-run any time (≈ 3 min with `--reuse`; logs next to the stage directory):
`deploy/stage_check.sh --help`.

## 2. Production unit — install and reboot validation (needs root)

On the production Jetson, as the administrator, from a checkout of the release to install.
Never with the mission simulator, run_demo.sh or the fakes running on that box.

```bash
# a CLEAN clone of the release: install.sh copies the source tree without .git, .claude/ (worktrees),
# build/, install/, log/, caches and test recordings (B18 fixed; verify_units.py checks it)
git clone --branch <release> <repo-url> ~/navera-release && cd ~/navera-release
git status --short                             # clean; ls -a shows no .claude/
deploy/install.sh --dry-run                    # review what will be done
python3 deploy/verify_units.py                 # units vs this checkout: must end "unit check: PASS"

# install / update (add --units "..." to choose; see deploy/README.md §1)
sudo deploy/install.sh --headless
sudoedit /etc/navera/navera.env                # NAVERA_MAX_SPEED_KMH, sources, data paths, NAVERA_WEB_TOKEN
sudo visudo -c                                 # whole sudoers configuration
python3 /home/navera/isaac_ros_common/deploy/verify_units.py --root /   # installed units: PASS

# data disk and swap (H-11 / F5: a day pipeline without swap was OOM-killed after 4.6 min)
findmnt /data && sudo -u navera -H test -r "$(sudo grep -oP '^NAVERA_MBTILES=\K.*' /etc/navera/navera.env)" && echo map readable
# install.sh made /swapfile (8 GB) if less than 4 GB of disk swap was active (deploy/setup_swap.sh;
# NAVERA_SWAP_MB / NAVERA_SWAP_FILE in navera.env to change it; zram does not count)
/home/navera/isaac_ros_common/deploy/setup_swap.sh --check   # "swap: ... OK"; else: sudo .../setup_swap.sh
swapon --show; grep swap /etc/fstab            # the file, active, and in fstab (sw,nofail)
# memory protection of the units (F5 / H-11): the output chain last for the OOM killer, web / discovery first
for u in navera-estimator navera-output navera-pipeline-day navera-web; do
  printf '%-22s %s\n' $u "$(systemctl show -p OOMScoreAdjust -p MemoryHigh -p MemoryMax $u | tr '\n' ' ')"; done
for p in $(systemctl show -p MainPID --value navera-estimator navera-web); do cat /proc/$p/oom_score_adj; done  # -900, 500
cat /sys/fs/cgroup/system.slice/navera-web.service/memory.max   # 2147483648
ls /etc/systemd/journald.conf.d/navera.conf && journalctl --disk-usage   # journal capped at 1 GB

# clock (F27): the box needs a battery-backed RTC
sudo i2cdetect -y 1 | grep '^60:'               # "68" (or "UU" if a kernel driver holds it) = DS3231 present;
                                               # "--" at 0x68: fit the clock before flying

# start now, then check before rebooting
sudo systemctl restart navera-discover navera-hotplug navera-estimator navera-gps navera-imu navera-rtc \
    navera-vehicle-link navera-pipeline-day navera-output navera-web
python3 /home/navera/isaac_ros_common/navera_tools/check_boot.py --wait 8
python3 /home/navera/isaac_ros_common/navera_tools/check_box.py   # in the NAVERA shell (deploy/README.md §11)

# 1) soft reboot
sudo reboot
# ... after the reboot, log in, wait 2 minutes, then:
python3 /home/navera/isaac_ros_common/navera_tools/check_boot.py --wait 8 | tee ~/reboot_check_$(date +%F_%H%M).txt
/home/navera/isaac_ros_common/deploy/check_boot.sh | tee -a ~/reboot_check_$(date +%F_%H%M).txt
systemd-analyze blame | grep navera            # start time of each unit
journalctl -b -u 'navera-*' --no-pager > ~/reboot_journal_$(date +%F_%H%M).txt

# 2) restart of a killed node (by PID, one unit at a time; repeat for navera-gps, navera-pipeline-day)
u=navera-estimator
main=$(systemctl show -p MainPID --value $u); pid=$main
while c=$(ps -o pid= --ppid $pid | head -1 | tr -d ' '); [ -n "$c" ]; do pid=$c; done
ps -o pid,args -p $pid                          # check it is the node
n0=$(systemctl show -p NRestarts --value $u); sudo kill -KILL $pid
sleep 30; echo "NRestarts $n0 -> $(systemctl show -p NRestarts --value $u)"
python3 /home/navera/isaac_ros_common/navera_tools/check_boot.py --wait 8   # PASS again

# 3) the web service's only root right (sudoers), as the service user
sudo -u navera sudo -n /usr/bin/systemctl restart navera-pipeline-day.service && echo "sudoers restart OK"

# 4) power cut: switch the vehicle supply off for 30 s (not a reboot), on again, then step 1)'s checks
#    record: time from power-on to "reboot check: PASS", and the RTC line of deploy/check_boot.sh
```

Acceptance (closes DEP-14 and the HW level of NAV-DEP-01): after the soft reboot **and** the
power cut, `check_boot.py` reports `reboot check: PASS` (every enabled unit active, stable, its
node in the graph), the clock line shows `valid: true` and `lost_power: false`, each killed node
is back with `NRestarts` + 1, and the sudoers restart works. Attach the saved reports to the
release record and add the result to docs/VALIDATION_STATUS.md.

## 3. Root steps left by the 2026-10-22 hardening (swap, OOM order, journal cap)

Everything below was tested without root (staged install, dry-run, unit checks, user units);
these commands are what only an administrator can run on the box. From the release checkout:

```bash
# all at once: the normal update (code, units, swap file if missing, journal cap)
sudo deploy/install.sh --no-apt --no-pip

# or one by one
sudo deploy/setup_swap.sh                      # /swapfile 8 GB + fstab line if < 4 GB disk swap active
sudo install -D -m 0644 deploy/journald/navera.conf /etc/systemd/journald.conf.d/navera.conf
sudo systemctl restart systemd-journald
sudo install -m 0644 deploy/systemd/navera-*.service /etc/systemd/system/
sudo install -o navera -g navera -m 0755 deploy/systemd/navera_boot_*.sh /home/navera/
sudo systemctl daemon-reload
sudo systemctl restart navera-estimator navera-gps navera-imu navera-rtc navera-vehicle-link \
    navera-pipeline-day navera-output navera-web

# check (no root)
deploy/setup_swap.sh --check                   # swap: ... OK
python3 deploy/verify_units.py --root /        # memory classes PASS
for u in navera-estimator navera-output navera-pipeline-day navera-web; do
  p=$(systemctl show -p MainPID --value $u); echo "$u oom_score_adj=$(cat /proc/$p/oom_score_adj)"; done
                                               # -900 -900 -300 500
cat /sys/fs/cgroup/system.slice/navera-web.service/memory.max          # 2147483648
journalctl -u navera-pipeline-day -b | grep -i swap                    # no "WARNING: only ... swap"
sudo reboot                                    # then deploy/check_boot.sh: the swap line says OK
```

## 4. Crash in flight without GPS — box in the loop, 2026-10-22/23 (B23)

The real Jetson as deployed (staged product units, `navera_tools/isaac/hil_flight.sh`), flying
an ArduPilot SITL copter in Isaac Sim (PC) at 250 m, 10 m/s, GPS jammed from the cut on. A node
is killed with SIGKILL in GPS-denied flight; "autopilot gap" = the longest time the autopilot
was given no position (`/navera/fix` = its GPS_INPUT, `hil_out.csv`). SIMULATION feeding the
real box: the box's timing and restarts are real, the world and the vehicle are not.

| killed (GPS denied) | before (hil_base1 / hil_endur30, RestartSec=10) | after (hil_resil4 / hil_resil5) |
|---|---|---|
| `navera-estimator` | `/navera/position` back after 15.4 s; output "no fix" at once, autopilot GPS lost after 2.3 s → **EKF failsafe LAND** | systemd back in 1.7 s, positions after 5.2 s / 4.8 s; output bridged: autopilot gap **2.6 s / 2.5 s**, GPS never lost, mission went on |
| `navera-output` | — | systemd back in 1.4 s; autopilot gap **4.7 s** (GPS lost 4.1 → 4.8 s), resumed bridging from `output_held`; no failsafe |
| day live camera | whole pipeline restarted: position back after 25.5 s → **LAND** | respawned alone in 2.3 s; day node dead-reckoned through it: autopilot gap **2.6 s**, positions never stopped |
| whole `navera-pipeline-day` unit (its launch) | — | systemd back in 3.0 s, day positions after **12.5 s**; bridged 10 s then "no fix" 2.5 s (autopilot GPS lost 10.3 → 12.5 s); **no failsafe**, mission went on |
| `day_subscriber` alone | — | respawned in 1.7 s, ready (`localizer_ready`) **7.2 s** after the kill (was ~25 s: imports 7.5 → 3.9 s, no camera reopen, the camera re-sends at once); but it **did not match again**: its restart search circle was 600 m (80 m before the kill), frames took 10 s each and failed (6–10 inliers, "scale 0.81"), the bridge ended at 10 s → **EKF failsafe LAND** (hil_resil4) |

Fixed 2026-10-23 (`day_pkg/carry_state.py`, `day_pkg/nodes/day_entry.py`): the day node persists its
track (measured points, carried velocity, headings, last output; state `day_track`, at most once a
second); a restarted process first publishes that carry from a light node, before its heavy imports
and its matcher, then the node restores the track at its original times (sigma grown by the time
elapsed, never a fresh fix) and searches k sigma around it. Isaac Sim endurance with `day_subscriber`
killed (SIGKILL) 45 min into GPS-denied flight, respawned by the flight script 1 s later (PC under
Isaac Sim load, not the Jetson): before the early bridge (fin_endur_2h try 1, ad88f5d) the restored node
published 21 s after the kill, the output's bridge ended at 10 s → EKF failsafe LAND; with it
(fin_endur_2h, 3b95ab5) the carried position was published again 7.0 s after the kill (the output
bridged the gap, never "no fix"), the node was ready 17.6 s after it (±123 m restored), no failsafe.
Also seen, not caused by the kills: in hil_resil4/5 the day fix error after the cut grew to
20–45 m (5–7 m in hil_base1 / hil_endur30) — already before the first kill; the exposure join
of `hil_summarise` is wrong after a camera restart (frame numbers restart). Results:
`~/.navera_sim/isaac/hil/hil_resil4`, `hil_resil5`.
