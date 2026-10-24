# Prepare THIS Jetson for sale — step by step

This Jetson (shadowteam-desktop) has been the development computer. Before a customer gets it,
it must be **erased and reinstalled** with only the NAVERA product. Deleting files one by one
always forgets something; a clean reinstall does not.

**Do this at the very end**, when development is finished or has moved to another computer:
after step 2, this Jetson no longer has the source code, the test data, Claude Code or the
remote access to the PC.

---

## What is on this Jetson today (must NOT reach a customer)
- The full NAVERA source with git history (`~/Navera`, ~30 worktrees), test data (`~/.navera_sim`,
  ~100 GB), releases, field tools.
- Other projects: NAVERA Academy (`~/navera-academy`), Nomad robot (`~/nomad_*`).
- Secrets: GitHub push scripts (`~/push_manar*.sh`, token typed in), the GitHub token and
  password shared in a chat, the Hikvision camera password (`~/thermal_inbox/.pw`), SSH keys
  (`~/.ssh`), Tailscale login, Claude Code (`~/.claude`).

---

## Step 1 — Back up everything (on this Jetson)
1. Code to GitHub:
   ```
   bash ~/push_manar.sh
   ```
   Must end with `exit code: 0`.
2. Test data and results to the ADATA disk (most already there; this adds the rest):
   ```
   rsync -a ~/.navera_sim/ "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/navera_sim_backup/"
   rsync -a ~/navera_releases/ "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/releases/"
   rsync -a ~/navera-academy/ "/media/shadow-team/ADATA SD620/NAVERA_WORKSPACE/navera-academy/"
   ```
3. Copy the release archive you will install, its `.sha256`, and this box's calibration files
   (camera lens file, `~/.navera_sim/insta360_*.json`) onto a USB stick.
4. **Unplug the ADATA disk** — it stays with IRIS.

## Step 2 — Erase and reinstall (from a Windows or Ubuntu PC)
1. Install **NVIDIA SDK Manager** on the PC (Ubuntu 20.04/22.04 host recommended).
2. Put the Jetson in recovery mode (jumper / button per the carrier board guide), connect USB-C.
3. Flash **JetPack 6.2** (same version as now) to the NVMe — choose "erase/format".
4. First boot: create the user account (a new, strong password — not the development one),
   connect to the network.

## Step 3 — Install only the product (on the fresh Jetson)
```
# from the USB stick
sha256sum -c navera-0.5.x.tar.gz.sha256
tar xzf navera-0.5.x.tar.gz && cd navera-0.5.x
sha256sum -c RELEASE_MANIFEST.sha256 --quiet
sudo deploy/install.sh                     # installs NAVERA as services
# add an SSH key for support access BEFORE the product mode (it turns passwords off):
ssh-copy-id <user>@<this box>              # from the support PC
sudo deploy/install.sh --product --dry-run # preview
sudo deploy/install.sh --product           # headless, SSH keys only, firewall, web token
sudo deploy/provision_box.sh --serial NAV-0001 --customer "<customer>" \
     --lens <lens file> --camera-delay <measured s> --map-bundle <dir> --env-extra extra.env
sudo reboot
```
`extra.env` holds e.g. `NAVERA_FORWARD_DEGRADED=true` and `NAVERA_DEGRADED_SIGMA_M=15`.
After the reboot: `deploy/check_boot.sh` → all services active.

## Step 4 — Calibrate and test this box
- Camera calibration and camera delay (manual §6.2–6.3) if not copied from step 1.
- Map package of the customer's area (`navera_tools/mission_bundle.py build` then `check`).
- Acceptance test (EVALUATION_PROGRAMME.md §3) — all 9 checks pass.
- 3 real power cuts (unplug during operation): the box restarts, `check_boot.sh` OK each time.
- 1-hour burn-in: temperature < 80 °C, memory flat.
- Keep the record `/var/lib/navera/provision/NAV-0001.json`.

## Step 5 — Revoke the development secrets (anywhere)
- **GitHub:** delete the token(s) used here (Settings → Developer settings → Personal access
  tokens) and **change the GitHub account password** (it was shared in a chat).
- **Hikvision camera** (if it ships with the box): set a new admin password.
- **Tailscale:** remove this machine in the Tailscale admin console.
- **PC access:** remove this Jetson's SSH key from the PC (`~/.ssh/authorized_keys` on the PC, the
  `id_ed25519.pub` of shadowteam-desktop).

## Step 6 — Pack
Box, camera + mount, cables, the printed acceptance results, USER_MANUAL and DATASHEET, the
support contact. Development continues on another computer (a second Jetson, or the PC).
