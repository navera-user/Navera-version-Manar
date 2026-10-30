# deploy/ — running NAVERA Lite as services on a box

Each node runs as a systemd service (a `.service` unit file in `systemd/`), as user `navera_lite`.
The site settings come from `/etc/navera_lite/navera_lite.env` (see `../navera_lite.env.example`).
A service that needs a device needs the device's group: see `ls -l /dev/<device>`.

    sudo cp systemd/*.service systemd/*.target /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now navera_lite.target
    journalctl -u navera_lite-gps -f          # follow the GPS reader's messages
