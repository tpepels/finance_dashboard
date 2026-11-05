#!/usr/bin/env bash
# Start the complete offline STAN verification soak in the existing Docker
# container, detached from this terminal. No OECD requests, no archive writes.
set -euo pipefail

cd "$(dirname "\${BASH_SOURCE[0]}")/.."

if ! docker compose ps --status running --services | grep -qx 'finance-dashboard'; then
  echo 'finance-dashboard is not running; build and start it first.' >&2
  exit 1
fi

state_dir="\${XDG_STATE_HOME:-$HOME/.local/state}/finance-dashboard/stan"
mkdir -p "$state_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log="$state_dir/overnight-$timestamp.log"
pid_file="$state_dir/overnight-$timestamp.pid"

# Explicit --all-archived includes newly acquired verified countries.
# Every report is kept in a unique subdirectory under the persistent /data
# volume, outside /data/source-evidence.
nohup docker compose exec -T finance-dashboard \
  python scripts/phase2_stan_overnight.py \
  --evidence-dir /data/source-evidence \
  --report-dir /data/stan-overnight-reports \
  --all-archived \
  --hours "\${STAN_HOURS:-8}" \
  --interval-minutes "\${STAN_INTERVAL_MINUTES:-30}" \
  --stress-groups "\${STAN_STRESS_GROUPS:-2500}" \
  > "$log" 2>&1 < /dev/null &

pid="$!"
printf '%s\n' "$pid" > "$pid_file"
printf 'Started STAN overnight verification (PID %s)\nLog: %s\nPID file: %s\n' \
  "$pid" "$log" "$pid_file"
printf 'Follow: tail -f %q\n' "$log"
