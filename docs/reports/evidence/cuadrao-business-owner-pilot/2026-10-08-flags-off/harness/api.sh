#!/bin/bash
# api.sh start <STATE> | stop
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=/Users/garces/Documents/projects/repos/argus-worktrees/private-alpha-next/.venv/bin/python
case "$1" in
  start)
    cd "$HERE"
    env -i PATH=/usr/bin:/bin HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" FLAG_STATE="$2" PYTHONDONTWRITEBYTECODE=1 \
      nohup "$PY" "$HERE/launcher.py" >>"$HERE/api.log" 2>&1 &
    echo $! >"$HERE/api.pid"
    for i in $(seq 1 120); do
      curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8641/health 2>/dev/null | grep -q 200 && { echo "api up state $2 pid $(cat "$HERE/api.pid")"; exit 0; }
      sleep 1
    done
    echo "api did not come up"; tail -20 "$HERE/api.log"; exit 1;;
  stop)
    pid=$(cat "$HERE/api.pid" 2>/dev/null) || exit 0
    kill "$pid" 2>/dev/null; for i in $(seq 1 15); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null; echo "stopped $pid";;
esac
