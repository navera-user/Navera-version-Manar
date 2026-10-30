# NAVERA Academy 1.0 on the NAVERA box — delivery

The Academy runs on the NAVERA box itself, fully offline, beside NAVERA. Flight safety first:
GPU/AI training and Sim Lite are refused while NAVERA flies, and whenever NAVERA cannot say.

| | |
|---|---|
| Code | `/opt/navera-academy` (read only, root) — Python packages in `/opt/navera-academy/pyuser` |
| Data | `/var/lib/navera-academy/{state,students,logs,data}` (user `academy`) |
| Settings | `/etc/navera-academy/academy.env` |
| Service | `navera-academy.service`, user `academy`, at boot; MemoryMax 1.5 GB, CPUWeight/IOWeight 10, Nice 10; student sandboxes together ≤ 3 GB (`user-<uid>.slice`), killed before NAVERA |
| Address | `http://navera-42ef.local:8300/` — on the setup Wi-Fi `http://10.42.0.1:8300/` (no public access, no Funnel) |
| Accounts | local only (no Google/GitHub/Facebook). `teacher` = the box's teacher; students are created on `/teacher` as lines `login, Full name, password` |
| Firewall | 8300 added to `NAVERA_FW_ALLOW_TCP` in `/etc/navera/navera.env` (if `NAVERA_FW_ALLOW_FROM` is set, only those networks reach it) |

## Install (after NAVERA is installed and in product mode; BEFORE the dev account is deleted)

```bash
cd /home/shadow-team/navera_releases
sha256sum -c navera-academy-1.0.tar.gz.sha256
sudo bash install_academy.sh --tarball navera-academy-1.0.tar.gz \
     --data-from /home/shadow-team/academy-data --pyuser-from /home/shadow-team/.local
```
It copies the map (osm_sousse.mbtiles, ~1 GB) and models into `/var/lib/navera-academy/data` and the Python
packages (~2.5 GB) into `/opt/navera-academy/pyuser`: nothing is downloaded. At step 7 it prints the
teacher password ONCE: write it on the delivery sheet (only its hash is stored).

Check:
```bash
systemctl status navera-academy --no-pager | head -5
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8300/        # 200
journalctl -u navera-academy -n 20 --no-pager | grep "flight gate"      # REFUSING… or allowed
sudo /usr/local/sbin/navera_firewall.sh --print | grep 8300
```

## Flight gate
The Academy asks `http://127.0.0.1:8181/api/mission/state` every 2 s. Refused while the answer says the
vehicle is armed / moving / navigating without GPS, or the bridge does not answer, or it does not report
a flight state. The student sees: *"Refused for flight safety: <reason>. Sim Lite and AI training are
available again once the vehicle has landed and is disarmed."* Running GPU jobs of the students are stopped.

## Later
- New teacher password (forgotten): `sudo bash /opt/navera-academy/deploy/teacher_password.sh`
- Update: `sudo bash install_academy.sh --tarball navera-academy-<V>.tar.gz` (keeps data, users, packages, settings).
- Stop / disable: `sudo systemctl disable --now navera-academy`.
- Remove: `sudo systemctl disable --now navera-academy; sudo rm -rf /opt/navera-academy* /var/lib/navera-academy /etc/navera-academy /etc/systemd/system/navera-academy.service; sudo userdel academy`
  then remove `8300` from `NAVERA_FW_ALLOW_TCP`.
