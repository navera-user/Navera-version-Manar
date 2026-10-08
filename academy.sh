#!/bin/bash
# NAVERA Academy — start / stop / status of the course dashboard.
#   ./academy.sh start | stop | status | restart | logs
# Dashboard: http://<jetson-ip>:8300   (teacher password: state/teacher_password.txt)
cd "$(dirname "$(readlink -f "$0")")" || exit 1
ROOT=$(pwd)
PIDF="$ROOT/state/server.pid"
pid() { [ -f $PIDF ] && kill -0 "$(cat $PIDF)" 2>/dev/null && cat $PIDF; }
case "${1:-status}" in
  start)
    if pid >/dev/null; then echo "already running (pid $(pid))"; exit 0; fi
    mkdir -p state logs
    ( cd server || exit 1; setsid nohup python3 app.py >> ../logs/server.log 2>&1 & echo $! > "$PIDF" )
    sleep 3
    if pid >/dev/null; then echo "NAVERA Academy running: http://$(hostname -I | awk '{print $1}'):8300  (pid $(pid))"
    else echo "failed to start — see logs/server.log"; tail -20 logs/server.log; exit 1; fi ;;
  stop)
    p=$(pid) && { kill "$p"; sleep 1; echo "stopped"; } || echo "not running"
    # terminals of the students stop with their scopes
    systemctl --user list-units --plain --no-legend 'academy-*' 2>/dev/null | awk '{print $1}' | xargs -r systemctl --user stop ;;
  restart) "$0" stop; "$0" start ;;
  public-start)   # HTTPS front door for academy.iris-systems.tn (router: 80→8080, 443→8443)
    XDG_DATA_HOME="$ROOT/state/caddy" XDG_CONFIG_HOME="$ROOT/state/caddy" setsid nohup "$ROOT/tools/bin/caddy" run \
      --config "$ROOT/deploy/Caddyfile" --adapter caddyfile >> "$ROOT/logs/caddy.log" 2>&1 &
    echo $! > "$ROOT/state/caddy.pid"; sleep 2; tail -3 "$ROOT/logs/caddy.log" ;;
  public-stop) [ -f "$ROOT/state/caddy.pid" ] && kill "$(cat "$ROOT/state/caddy.pid")" 2>/dev/null; echo "public access stopped" ;;
  status) p=$(pid) && echo "running (pid $p) on http://$(hostname -I | awk '{print $1}'):8300" || echo "not running" ;;
  logs) tail -f logs/server.log ;;
  *) echo "usage: $0 start|stop|restart|status|logs|public-start|public-stop"; exit 1 ;;
esac
