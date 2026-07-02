# NAVERA — Démarrage automatique au boot

Ce dossier contient les fichiers de déploiement permettant de lancer **automatiquement au
démarrage de la Jetson** le pipeline de localisation NAVERA « day » (ROS2 + dashboard web),
sans intervention manuelle et sans session interactive.

Testé, rebooté et validé sur la Jetson Orin Nano (JetPack 6.2.1, Ubuntu 22.04) le 2026-07-02.

## Contenu

| Fichier | Rôle |
|---------|------|
| `systemd/navera_boot_day.sh` | Wrapper de lancement. Recrée l'environnement que systemd ne charge pas (CUDA dans le `PATH`, `source` de ROS Humble puis de l'overlay `install/`), puis `exec ros2 launch simulation_web day_sim.launch.py`. |
| `systemd/navera-day.service` | Unité systemd qui appelle le wrapper au boot (utilisateur `navera`, `Restart=on-failure`, cible `multi-user.target`). |

## Ce que fait le démarrage auto

Au boot, une fois le réseau prêt (`network-online.target`), systemd exécute le wrapper en
tant qu'utilisateur `navera`. Le wrapper :

1. se place dans le workspace `/home/navera/isaac_ros_common` ;
2. remet CUDA 12.6 dans `PATH` / `LD_LIBRARY_PATH` (normalement fait par `~/.bashrc`, jamais
   sourcé sous systemd) ;
3. source `/opt/ros/humble/setup.bash` puis `install/setup.bash` ;
4. lance le pipeline day via `ros2 launch simulation_web day_sim.launch.py`.

Le `ros2 launch` remplace le shell (`exec`) → il devient le processus principal vu par
systemd, ce qui garantit un `stop`/`restart` propre. En cas d'échec, systemd relance après
10 s (`Restart=on-failure`, `RestartSec=10`).

Résultat : après un simple `reboot`, le dashboard est disponible sans action manuelle.

## Installation sur une nouvelle Jetson

À exécuter sur la Jetson cible (le workspace doit déjà être présent dans
`/home/navera/isaac_ros_common` et compilé — `install/` généré par `colcon build`).

```bash
cd /home/navera/isaac_ros_common

# 1) Installer le wrapper dans le HOME (le .service pointe vers ~/navera_boot_day.sh)
cp deploy/systemd/navera_boot_day.sh /home/navera/navera_boot_day.sh
chmod +x /home/navera/navera_boot_day.sh

# 2) Installer l'unité systemd (nécessite sudo)
sudo cp deploy/systemd/navera-day.service /etc/systemd/system/navera-day.service
sudo systemctl daemon-reload

# 3) Activer le service au boot
sudo systemctl enable navera-day.service

# 4) S'assurer que la Jetson boote en mode multi-utilisateur (pas d'interface graphique requise)
sudo systemctl set-default multi-user.target

# 5) (optionnel) Démarrer tout de suite sans rebooter
sudo systemctl start navera-day.service
```

> Le wrapper est volontairement installé dans `~` et non lancé depuis le repo, pour coller à
> la configuration validée (`ExecStart=/home/navera/navera_boot_day.sh`). Si tu préfères le
> lancer directement depuis le repo, adapte le chemin `ExecStart` dans le `.service`.

## Vérifier que ça tourne

```bash
# État du service
sudo systemctl status navera-day.service        # doit être "active (running)"

# Confirmer qu'il est activé au boot
systemctl is-enabled navera-day.service          # doit afficher "enabled"

# Suivre les logs en direct
journalctl -u navera-day.service -f

# Test complet : redémarrer et revérifier
sudo reboot
```

Accès au dashboard une fois le service actif :

- **En local / réseau :** `http://<ip-jetson>:8181/`
- **Via Tailscale :** `http://100.126.3.71:8181/`

## Désinstaller / désactiver

```bash
sudo systemctl disable --now navera-day.service
sudo rm /etc/systemd/system/navera-day.service
sudo systemctl daemon-reload
```
