# NAVERA — Démarrage automatique au boot

Ce dossier contient les fichiers de déploiement permettant de lancer **automatiquement au
démarrage de la Jetson** l'ensemble NAVERA (capteurs + pipeline de localisation « day » +
dashboard web), sans intervention manuelle et sans session interactive.

L'architecture de boot est **découpée en 5 services systemd indépendants** — 3 capteurs, 1
pipeline de vision, 1 bridge web. Chaque brique démarre, tombe et redémarre seule
(`Restart=on-failure`), sans dépendre de l'ordre de démarrage des autres.

Découpage validé par reboot sur la Jetson Orin Nano (JetPack 6.2.1, Ubuntu 22.04) le
2026-07-15 : après un simple `reboot`, les 5 services remontent seuls, le bridge binde le
port `:8181` (HTTP 200), les 6 nodes tournent, et le marqueur bouge sur le dashboard — donc
le bridge et le pipeline se parlent bien en DDS malgré la séparation en deux services.

## Architecture

```
capteurs (host, CPU)          pipeline vision (host, GPU/CUDA)      bridge web (host)
  navera-gps  → /navera/sensors/gps_fix                              navera-web
  navera-imu  → /navera/sensors/imu        navera-pipeline-day  ←DDS→  (HTTP :8181,
  navera-rtc  → /navera/sensors/rtc_time     camera + day_subscriber    dashboard)
                                             (DINOv2)
```

- **Bridge ↔ pipeline** communiquent en **DDS** (découverte, indépendant de l'ordre) via des
  topics de handshake latchés → aucun `After=`/`Before=` entre `navera-web` et
  `navera-pipeline-day` : l'un ou l'autre peut démarrer ou redémarrer en premier.
- **Tout tourne sur l'HÔTE**, pas dans le conteneur Isaac ROS.
- La pipeline vision exporte CUDA (GPU) ; les capteurs sont CPU-only (pas d'exports CUDA).

## Contenu

| Fichier | Rôle |
|---------|------|
| `systemd/navera-web.service` + `navera_boot_web.sh` | Bridge ROS→HTTP, dashboard `:8181`. Pilote le pipeline day par-dessus DDS. |
| `systemd/navera-pipeline-day.service` + `navera_boot_pipeline_day.sh` | Pipeline de localisation day : `camera_pkg` + `day_subscriber` (DINOv2, GPU), **sans** bridge. |
| `systemd/navera-gps.service` + `navera_boot_gps.sh` | Node capteur GPS (NMEA `/dev/ttyTHS1` → `/navera/sensors/gps_fix`). CPU-only. |
| `systemd/navera-imu.service` + `navera_boot_imu.sh` | Node capteur IMU (BNO085, I²C bus 1 @ `0x4A` → `/navera/sensors/imu`). |
| `systemd/navera-rtc.service` + `navera_boot_rtc.sh` | Node horloge RTC (DS3231, I²C bus 1 @ `0x68` → `/navera/sensors/rtc_time`). |

> **Note :** l'ancien service monolithique `navera-day` (un seul service lançant
> `day_sim.launch.py` = pipeline + bridge ensemble) a été **retiré** au profit de ce découpage.
> Le launch `day_sim.launch.py` reste disponible pour le workflow « une commande » en dev/test
> (`ros2 launch simulation_web day_sim.launch.py`), mais n'est plus utilisé au boot.

## Ce que fait chaque service au boot

Au boot, une fois le réseau prêt (`network-online.target`), systemd exécute chaque wrapper en
tant qu'utilisateur `navera`. Chaque wrapper :

1. se place dans le workspace `/home/navera/isaac_ros_common` ;
2. (pipeline vision uniquement) remet CUDA 12.6 dans `PATH` / `LD_LIBRARY_PATH` (normalement
   fait par `~/.bashrc`, jamais sourcé sous systemd) ;
3. source `/opt/ros/humble/setup.bash` puis `install/setup.bash` ;
4. `exec` la commande ROS du service (`ros2 launch` / `ros2 run`).

L'`exec` remplace le shell → le process ROS devient le process principal vu par systemd, ce
qui garantit un `stop`/`restart` propre. En cas d'échec, systemd relance après 10 s
(`Restart=on-failure`, `RestartSec=10`).

Résultat : après un simple `reboot`, capteurs, pipeline et dashboard sont disponibles sans
aucune action manuelle.

## Installation sur une nouvelle Jetson

À exécuter sur la Jetson cible (le workspace doit déjà être présent dans
`/home/navera/isaac_ros_common` et compilé — `install/` généré par `colcon build`).

```bash
cd /home/navera/isaac_ros_common

# 1) Installer les wrappers dans le HOME (les .service pointent vers ~/navera_boot_*.sh)
cp deploy/systemd/navera_boot_*.sh /home/navera/
chmod +x /home/navera/navera_boot_*.sh

# 2) Installer les unités systemd (nécessite sudo)
sudo cp deploy/systemd/navera-*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3) Activer les 5 services au boot
sudo systemctl enable navera-web navera-pipeline-day navera-gps navera-imu navera-rtc

# 4) S'assurer que la Jetson boote en mode multi-utilisateur (pas d'interface graphique requise)
sudo systemctl set-default multi-user.target

# 5) (optionnel) Démarrer tout de suite sans rebooter
sudo systemctl start navera-web navera-pipeline-day navera-gps navera-imu navera-rtc
```

> Les wrappers sont volontairement installés dans `~` et non lancés depuis le repo, pour coller
> à la configuration validée (`ExecStart=/home/navera/navera_boot_*.sh`).

## Vérifier que ça tourne

```bash
# État des 5 services (tous "active (running)")
systemctl status 'navera-*'

# Confirmer qu'ils sont activés au boot ("enabled")
systemctl is-enabled navera-web navera-pipeline-day navera-gps navera-imu navera-rtc

# Suivre les logs en direct (ex. le bridge ou le pipeline)
journalctl -u navera-web -f
journalctl -u navera-pipeline-day -f

# Confirmer que le bridge écoute
curl -sI http://localhost:8181/ | head -1     # doit renvoyer HTTP 200

# Test complet : redémarrer et revérifier
sudo reboot
```

Accès au dashboard une fois `navera-web` actif :

- **En local / réseau :** `http://<ip-jetson>:8181/`
- **Via Tailscale :** `http://100.126.3.71:8181/`

## Désinstaller / désactiver

```bash
# Un service en particulier (ex. le pipeline day)
sudo systemctl disable --now navera-pipeline-day
sudo rm /etc/systemd/system/navera-pipeline-day.service

# Ou tout d'un coup
sudo systemctl disable --now navera-web navera-pipeline-day navera-gps navera-imu navera-rtc
sudo rm /etc/systemd/system/navera-{web,pipeline-day,gps,imu,rtc}.service
sudo systemctl daemon-reload
```
