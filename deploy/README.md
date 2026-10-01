# NAVERA — Démarrage automatique au boot

Ce dossier contient les fichiers de déploiement permettant de lancer **automatiquement au
démarrage de la Jetson** l'ensemble NAVERA (capteurs + pipeline de localisation « day » +
dashboard web), sans intervention manuelle et sans session interactive.

L'architecture de boot est **découpée en services systemd indépendants** — 3 capteurs, 1
pipeline de vision (jour, nuit **ou** céleste : un seul à la fois), 1 arbitre de position
(`navera-estimator`), 1 bridge web. Chaque brique démarre, tombe et redémarre seule
(`Restart=always`, voir « Redémarrage automatique »), sans dépendre de l'ordre de démarrage des autres.

Découpage validé par reboot sur la Jetson Orin Nano (JetPack 6.2.1, Ubuntu 22.04) le
2026-07-15 : après un simple `reboot`, les 5 services remontent seuls, le bridge binde le
port `:8181` (HTTP 200), les 6 nodes tournent, et le marqueur bouge sur le dashboard — donc
le bridge et le pipeline se parlent bien en DDS malgré la séparation en deux services.

> **À revalider :** cette validation date d'avant l'ajout de `navera-estimator`, de
> `Restart=always` / `on_exit=Shutdown` et de `/etc/navera/navera.env`. Refaire le test de
> reboot, puis tuer un node (`pkill -f gps_node`) et vérifier qu'il revient en ~10 s.

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
| `systemd/navera-estimator.service` + `navera_boot_estimator.sh` | Arbitre de position : choisit la meilleure source (GPS > jour > nuit > céleste) → `/navera/position`, `/navera/nav_status`. |
| `systemd/navera-pipeline-night.service` + `navera_boot_pipeline_night.sh` | Pipeline de nuit : caméra thermique + STHN (GPU). Non activé par défaut. |
| `systemd/navera-pipeline-cn.service` + `navera_boot_pipeline_cn.sh` | Pipeline céleste : caméra stellaire + astrometry.net. Non activé par défaut. |
| `systemd/navera_boot_lib.sh` | Étapes communes des wrappers (environnement ROS, purge des logs, vérification des données). |
| `navera.env.example` | Réglages du site (chemins des données, `ROS_DOMAIN_ID`, isolation réseau) → à copier dans `/etc/navera/navera.env`. |

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
qui garantit un `stop`/`restart` propre.

### Démarrage sans réseau, données absentes

- Aucun service n'attend le réseau (`network-online.target`) : sur le terrain il n'y en a
  souvent pas, et tous les nodes dialoguent en DDS local.
- Avant de lancer un pipeline, son wrapper vérifie que ses données existent (carte MBTiles,
  jeu de tuiles, poids STHN). Si le disque de données n'est pas encore monté, le wrapper sort
  en erreur et systemd réessaie toutes les 10 s : le pipeline ne tourne jamais « à moitié ».
- Les dossiers de logs ROS (`~/.ros/log`) de plus de 7 jours sont purgés à chaque démarrage.

### Redémarrage automatique

`ros2 launch` sort avec le code 0 même quand un de ses nodes a planté : `Restart=on-failure`
ne relançait donc jamais rien. Désormais :

- chaque node des launch files de boot a `on_exit=Shutdown` : si **un** node meurt, tout le
  launch s'arrête (la caméra ne reste pas seule à attendre un localiseur mort) ;
- chaque unité a `Restart=always` + `RestartSec=10` + `StartLimitIntervalSec=0` : systemd
  relance le service 10 s après n'importe quel arrêt, indéfiniment (un `systemctl stop`
  volontaire n'est pas relancé) ;
- `gps_node` sort avec le code 1 si le port série est absent ou se déconnecte : le cycle
  ci-dessus le relance toutes les 10 s jusqu'au retour du GPS.

Résultat : après un simple `reboot`, capteurs, pipeline et dashboard sont disponibles sans
aucune action manuelle.

## Installation sur une nouvelle Jetson

À exécuter sur la Jetson cible (le workspace doit déjà être présent dans
`/home/navera/isaac_ros_common` et compilé — `install/` généré par `colcon build`).

```bash
# 0) Utilisateur de service et accès matériel (port série GPS, bus I²C)
sudo useradd -m -s /bin/bash navera 2>/dev/null || true
sudo usermod -aG dialout,i2c,gpio navera

# 0a) Pipeline céleste : résolveur astrometry.net + index Tycho-2 (champs 1°–33°+)
sudo apt install astrometry.net astrometry-data-tycho2-10-19

# 0a') Cap vrai (nord géographique) : modèle magnétique mondial WMM 2025 pour l'IMU
sudo -u navera pip install --user pygeomag==1.1.0

# 0b) Réglages du site : chemins des données, isolation réseau ROS 2
sudo mkdir -p /etc/navera
sudo cp /home/navera/isaac_ros_common/deploy/navera.env.example /etc/navera/navera.env
sudoedit /etc/navera/navera.env
#     À régler pour CHAQUE véhicule : NAVERA_MAX_SPEED_KMH (vitesse maximale, km/h —
#     ex. multirotor 108, bateau 72, robot 36, voilure fixe 250). NAVERA refuse toute
#     position que le véhicule n'aurait pas pu atteindre à cette vitesse.

cd /home/navera/isaac_ros_common

# 1) Installer les wrappers dans le HOME (les .service pointent vers ~/navera_boot_*.sh)
cp deploy/systemd/navera_boot_*.sh /home/navera/
chmod +x /home/navera/navera_boot_*.sh

# 2) Installer les unités systemd (nécessite sudo)
sudo cp deploy/systemd/navera-*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3) Activer les services au boot (pipeline de jour par défaut)
sudo systemctl enable navera-web navera-pipeline-day navera-gps navera-imu navera-rtc navera-estimator

# 3b) Modèles hors ligne : le véhicule peut démarrer sans internet. Pré-remplir UNE fois
#     (avec internet) le cache DINOv2 pointé par TORCH_HOME dans navera.env :
sudo -u navera bash -c 'set -a; . /etc/navera/navera.env; set +a; \
  python3 -c "import torch; torch.hub.load(\"facebookresearch/dinov2\", \"dinov2_vits14\")"'

# 4) S'assurer que la Jetson boote en mode multi-utilisateur (pas d'interface graphique requise)
sudo systemctl set-default multi-user.target

# 5) (optionnel) Démarrer tout de suite sans rebooter
sudo systemctl start navera-web navera-pipeline-day navera-gps navera-imu navera-rtc navera-estimator
```

> Les wrappers sont volontairement installés dans `~` et non lancés depuis le repo, pour coller
> à la configuration validée (`ExecStart=/home/navera/navera_boot_*.sh`).

## Changer de pipeline (jour / nuit / céleste)

Un seul pipeline de vision GPU tient en mémoire : jour et nuit sont en `Conflicts=` (en démarrer
un arrête l'autre). Le pipeline céleste (caméra stellaire, astrometry.net, CPU) n'est en conflit
avec aucun : il peut tourner en même temps que le jour ou la nuit, comme repli quand la vision
ne donne plus de position (priorité de l'arbitre : GPS > jour > nuit > céleste).

```bash
# Exemple : passer en nuit
sudo sed -i 's/^NAVERA_PIPELINE=.*/NAVERA_PIPELINE=night/' /etc/navera/navera.env
sudo systemctl disable --now navera-pipeline-day
sudo systemctl enable --now navera-pipeline-night
sudo systemctl restart navera-web      # le bridge suit NAVERA_PIPELINE
```

## Vérifier que ça tourne

```bash
# État des 6 services (tous "active (running)")
systemctl status 'navera-*'

# Confirmer qu'ils sont activés au boot ("enabled")
systemctl is-enabled navera-web navera-pipeline-day navera-gps navera-imu navera-rtc navera-estimator

# Voir les topics depuis un shell : charger le même environnement que les services
set -a; . /etc/navera/navera.env; set +a
ros2 topic echo /navera/nav_status

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

## Désinstaller / désactiver

```bash
# Un service en particulier (ex. le pipeline day)
sudo systemctl disable --now navera-pipeline-day
sudo rm /etc/systemd/system/navera-pipeline-day.service

# Ou tout d'un coup
sudo systemctl disable --now navera-web navera-pipeline-day navera-pipeline-night navera-pipeline-cn navera-gps navera-imu navera-rtc navera-estimator
sudo rm /etc/systemd/system/navera-*.service
sudo systemctl daemon-reload
```
