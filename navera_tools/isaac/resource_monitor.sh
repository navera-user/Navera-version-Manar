#!/bin/bash
# Resources of an Isaac Sim closed-loop run, every 30 s, into RES/resources.csv (SIMULATION tooling):
# GPU (memory, load, temperature, power), the NAVERA container (CPU, memory, each node's RSS),
# WSL memory, Isaac Sim's Windows process, the size of the record and of the logs, D: free.
# Long runs: a leak shows as a steady rise of a node's RSS or of the GPU memory over hours.
#
#   resource_monitor.sh RES_DIR ISAAC_RUN_DIR [PERIOD_S]     (run_closed_loop.sh starts it)
# The PC has no CPU temperature for a normal user (WSL has no thermal zones): GPU only.
res=$1; run=$2; period=${3:-30}
out=$res/resources.csv
smi=/mnt/c/Windows/System32/nvidia-smi.exe
ps1=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
[ -s "$out" ] || echo "wall,epoch,t_s,gpu_mem_mib,gpu_util_pct,gpu_temp_c,gpu_power_w,ctr_cpu_pct,ctr_mem_mib,\
rss_day_mib,rss_estimator_mib,rss_camera_mib,rss_link_mib,rss_gps_mib,rss_output_mib,wsl_used_mib,wsl_avail_mib,\
isaac_ws_mib,isaac_private_mib,results_mib,logs_mib,isaac_frames,d_free_gb" > "$out"
t0=$(date +%s)
mib() { awk -v p="$1" 'index($0, p) && $2 ~ /^[0-9]+$/ {s += $2} END {printf "%.0f", s / 1024}' <<< "$top"; }
while sleep "$period"; do
  docker ps -q -f name=navera_isaac | grep -q . || break
  g=$($smi --query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits \
      2>/dev/null | tr -d ' \r' | head -1)
  [ -n "$g" ] || g=",,,"
  st=$(docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' navera_isaac 2>/dev/null)
  cpu=$(awk '{gsub("%", "", $1); print $1}' <<< "$st")
  mem=$(awk '{v = $2; u = v; gsub(/[0-9.]/, "", u); gsub(/[A-Za-z]/, "", v);
              f = (u == "GiB") ? 1024 : (u == "KiB") ? 1 / 1024 : 1; printf "%.0f", v * f}' <<< "$st")
  top=$(docker top navera_isaac -eo pid,rss,args 2>/dev/null)
  # the node processes (not their "ros2 run" wrappers)
  rss="$(mib lib/day_pkg/day_subscriber),$(mib lib/navera_estimator/estimator_node),$(mib lib/camera_pkg/live_camera),\
$(mib isaac/isaac_link.py),$(mib lib/gps_pkg/gps_node),$(mib lib/navera_output/vehicle_output_node)"
  wsl=$(free -m | awk '/^Mem:/ {print $3 "," $7}')
  win=$($ps1 -NoProfile -Command "\$p = Get-Process python,kit -ErrorAction SilentlyContinue | Where-Object { \$_.Path -like '*isaacsim*' }; \
'{0},{1}' -f [int](((\$p | Measure-Object WorkingSet64 -Sum).Sum) / 1MB), [int](((\$p | Measure-Object PrivateMemorySize64 -Sum).Sum) / 1MB)" \
      2>/dev/null | tr -d '\r' | tail -1)
  [ -n "$win" ] || win=","
  rmib=$(du -sm "$res" 2>/dev/null | cut -f1); lmib=$(du -sm "$res/logs" 2>/dev/null | cut -f1)
  nfr=$( [ -f "$run/frames.jsonl" ] && wc -l < "$run/frames.jsonl")
  dfree=$(df -BG --output=avail /mnt/d 2>/dev/null | tail -1 | tr -dc 0-9)
  echo "$(date +%T),$(date +%s),$(( $(date +%s) - t0 )),$g,$cpu,$mem,$rss,$wsl,$win,$rmib,$lmib,$nfr,$dfree" >> "$out"
done
