#!/bin/bash
# Independent safety watcher: waits for the driver pid to exit, then closes the recorded reservation window
# using strict readback, even when an inventory command fails or the resource is already absent.
#   bin/safety_teardown.sh <driver_pid> <original_window_label> [python_executable]
set -euo pipefail
PID=${1:?driver pid}; LABEL=${2:?original window label}; PYTHON=${3:-python3}
cd "${OKF_SPIKE_DIR:-$(dirname "$0")/..}"
while kill -0 "$PID" 2>/dev/null; do sleep 15; done
echo "$(date -u +%FT%TZ) SAFETY: cancelling jobs and verifying original window $LABEL after driver $PID exit"
exec "$PYTHON" -m okf_bq_graph.safety "$LABEL"
