#!/bin/sh
# Lock screen camera: leak tests against the camera (run on the Mac). It copies the helpers to the
# camera, runs the scenarios there (tools/lockcam-scenarios.sh), and brings the screenshots back to
# /tmp/lockcam/ to look at. The camera needs: the test phosh installed, grim, python3, and a
# Locked action on the default camera's desktop file (see the plan).
# usage: tools/lockcam-test.sh [scenario ...]
set -eu
DEV=${DEVICE:-root@192.168.1.191}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=/tmp/lockcam

scp -q "$HERE/lockcam-touch.py" "$HERE/lockcam-env.sh" "$HERE/lockcam-scenarios.sh" "$DEV":/tmp/
ssh "$DEV" 'rm -rf /tmp/lockcam' || true
ssh "$DEV" "sh /tmp/lockcam-scenarios.sh $*"
rm -rf "$OUT" && mkdir -p "$OUT"
scp -q "$DEV":/tmp/lockcam/*.png "$OUT"/ 2>/dev/null || echo "(no screenshots came back)"
ls -la "$OUT" | cut -c30-90
