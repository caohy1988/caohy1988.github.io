#!/bin/bash
# Independent safety watcher: waits for the driver pid to exit, then closes the recorded reservation window
# if the reservation still exists. Spawned detached by okf_bq_graph.run; can also be started by hand:
#   bin/safety_teardown.sh <driver_pid> <window_label>
PID=${1:?driver pid}; LABEL=${2:-safety}
cd "$(dirname "$0")/.."
while kill -0 "$PID" 2>/dev/null; do sleep 15; done
sleep 20
if bq --project_id=test-project-0728-467323 --location=US ls --reservation 2>/dev/null | grep -q okf-graph-spike; then
  echo "$(date -u +%FT%TZ) SAFETY: reservation still present after driver $PID exit; closing window $LABEL"
  python3 -m okf_bq_graph.reservation close "safety-$LABEL-$(date -u +%H%M)"
else
  echo "$(date -u +%FT%TZ) SAFETY: reservation already gone after driver $PID exit"
fi
