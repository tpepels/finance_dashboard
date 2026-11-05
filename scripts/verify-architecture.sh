#!/usr/bin/env bash
# Full local integration verification. No extra GitHub workflow and no
# publisher network calls from this script's tests/inspection commands.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! docker compose ps --status running --services | grep -qx finance-dashboard; then
  echo 'finance-dashboard container must be built and running first.' >&2
  exit 1
fi

log="${XDG_STATE_HOME:-$HOME/.local/state}/finance-dashboard/architecture"
mkdir -p "$log"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
test_log="$log/full-python-$stamp.log"
evidence_log="$log/evidence-audit-$stamp.json"
policy_log="$log/publisher-policy-$stamp.json"

echo '[1/3] Full Python unit/integration suite (offline)'
if ! docker compose exec -T finance-dashboard     python -m unittest discover -s tests -p 'test_*.py' -q >"$test_log" 2>&1; then
  echo "FAILED Python suite — full output: $test_log"
  tail -n 28 "$test_log"
  exit 1
fi
tail -n 3 "$test_log"

echo '[2/3] Verify ingestion-linked original archives (read-only)'
if ! docker compose exec -T finance-dashboard     python scripts/audit_ingestion_evidence.py --brief > "$evidence_log" 2>&1; then
  echo "FAILED original-evidence integrity audit: $evidence_log"
  tail -n 12 "$evidence_log"
  exit 1
fi
cat "$evidence_log"

echo '[3/3] Canonical publisher constraints (read-only)'
docker compose exec -T finance-dashboard   python scripts/source_policy_status.py --brief > "$policy_log"
cat "$policy_log"

echo "PASS Full logs: $test_log"
echo "PASS Original evidence: $evidence_log"
echo "PASS Publisher policies: $policy_log"
