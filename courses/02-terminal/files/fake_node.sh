#!/bin/bash
# fake_node.sh — pretends to be a ROS node that runs until it is stopped.
# Start it in the background:   ./fake_node.sh &
# It writes its process ID (PID) in fake_node.pid and a line in fake_node.log
# when it starts and when it receives a signal it can catch (SIGINT, SIGTERM).
# SIGKILL (kill -9) cannot be caught: the node then dies without writing anything.

cd "$(dirname "$0")" || exit 1
echo "$$" > fake_node.pid
echo "$(date +%s) fake_node pid=$$ started" >> fake_node.log
trap 'echo "$(date +%s) fake_node pid=$$ received SIGTERM, shutting down cleanly" >> fake_node.log; exit 0' TERM
trap 'echo "$(date +%s) fake_node pid=$$ received SIGINT (Ctrl+C), shutting down cleanly" >> fake_node.log; exit 0' INT
while true; do
    sleep 1
done
