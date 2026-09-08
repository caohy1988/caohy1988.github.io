#!/bin/bash
cd /Users/haiyuancao/okf-bq-graph-spike/rfc/spikes/bq-graph
while pgrep -f "okf_bq_graph.run" >/dev/null; do sleep 15; done
sleep 20
if bq --project_id=test-project-0728-467323 --location=US ls --reservation 2>/dev/null | grep -q okf-graph-spike; then
  echo "$(date -u +%FT%TZ) SAFETY: reservation still present after run exit; closing" >> evidence/safety_teardown.log
  python3 -m okf_bq_graph.reservation close safety-$(date -u +%H%M) >> evidence/safety_teardown.log 2>&1
else
  echo "$(date -u +%FT%TZ) SAFETY: reservation already gone" >> evidence/safety_teardown.log
fi
