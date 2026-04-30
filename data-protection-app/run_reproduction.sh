#!/usr/bin/env bash
#
# Data Protection Dashboard — reproduce processor.py bugs vs processor_fixed.py
#
# Bug narrative (processor.py):
#   • auto_ack=True — broker acks before your callback finishes; failures still look "consumed"
#   • Exceptions logged only at DEBUG while logging is INFO → "silent" failures
#   • No real transaction discipline / connection churn / process_event returns True on errors
#
# Phase 1 simulates unreachable Postgres (wrong DB_PORT) so inserts always fail: logs stay
# quiet at INFO while messages are still acked — classic data loss symptom.
# Phase 2 runs processor_fixed against the real DB: manual ack after commit, pooling, ERROR logs, nack+requeue.
#
# Optional env (same as docker-compose / Python apps):
#   POSTGRES_HOST_PORT=5433 RABBITMQ_HOST_PORT=5673 RABBITMQ_MANAGEMENT_HOST_PORT=15673 RABBITMQ_PORT=5673
#
# Optional file: source .env.reproduction before running if you keep secrets/overrides there:
#   set -a && source .env.reproduction && set +a && ./run_reproduction.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env.reproduction ]]; then
  # shellcheck disable=SC1091
  set -a && source .env.reproduction && set +a
fi

SETUP_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --setup-only) SETUP_ONLY=true ;;
    -h|--help)
      echo "Usage: $0 [--setup-only]"
      echo "  (default)  Start infra, run Phase 1 (buggy + bad DB), Phase 2 (fixed + real DB), assert counts"
      echo "  --setup-only  Only Docker + venv + DB init; print manual steps"
      exit 0
      ;;
  esac
done

PYTHON="${SCRIPT_DIR}/.venv/bin/python"
PIP="${SCRIPT_DIR}/.venv/bin/pip"
QUEUE_NAME="data_protection_events"

# Tunables
BUG_PHASE_EVENTS="${BUG_PHASE_EVENTS:-100}"
FIX_PHASE_EVENTS="${FIX_PHASE_EVENTS:-80}"
BAD_DB_PORT="${BAD_DB_PORT:-65432}"
WAIT_QUEUE_DRAIN_SEC="${WAIT_QUEUE_DRAIN_SEC:-120}"

compose() {
  docker compose "$@"
}

wait_for_postgres() {
  local n=0
  until compose exec -T postgres pg_isready -U dataprotection -d dataprotection &>/dev/null; do
    n=$((n + 1))
    if [[ "$n" -gt 90 ]]; then
      echo "ERROR: PostgreSQL did not become ready in time."
      exit 1
    fi
    sleep 2
  done
}

wait_for_rabbitmq() {
  local n=0
  until compose exec -T rabbitmq rabbitmq-diagnostics -q ping &>/dev/null; do
    n=$((n + 1))
    if [[ "$n" -gt 90 ]]; then
      echo "ERROR: RabbitMQ did not become ready in time."
      exit 1
    fi
    sleep 2
  done
}

queue_messages() {
  compose exec -T rabbitmq rabbitmqctl list_queues name messages 2>/dev/null \
    | awk -v q="$QUEUE_NAME" '$1==q {print $2; exit}'
}

db_event_count() {
  compose exec -T postgres psql -U dataprotection -d dataprotection -tAc 'SELECT COUNT(*) FROM events;' \
    | tr -d '[:space:]'
}

wait_for_queue_depth() {
  local want="$1" deadline=$((SECONDS + WAIT_QUEUE_DRAIN_SEC))
  local depth
  while [[ $SECONDS -lt $deadline ]]; do
    depth="$(queue_messages)"
    depth="${depth:-0}"
    if [[ "$depth" == "$want" ]]; then
      return 0
    fi
    sleep 1
  done
  depth="$(queue_messages)"
  depth="${depth:-0}"
  echo "WARN: Queue depth still ${depth} after ${WAIT_QUEUE_DRAIN_SEC}s (wanted ${want})."
  return 1
}

kill_bg_safely() {
  local pid="$1"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

echo "============================================================"
echo " Data Protection — reproduction & fix verification"
echo "============================================================"
echo ""

if ! command -v docker &>/dev/null; then
  echo "ERROR: docker not found."
  exit 1
fi
if ! docker compose version &>/dev/null; then
  echo "ERROR: docker compose not available."
  exit 1
fi
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found."
  exit 1
fi

echo "[1] Starting RabbitMQ + PostgreSQL..."
compose up -d rabbitmq postgres

echo "[2] Waiting for healthy dependencies..."
wait_for_postgres
wait_for_rabbitmq

echo "[3] Python virtualenv + dependencies..."
python3 -m venv .venv
"$PIP" install -q -r requirements.txt

echo "[4] Database schema (idempotent)..."
compose exec -T postgres psql -U dataprotection -d dataprotection \
  -f /docker-entrypoint-initdb.d/init_db.sql 2>/dev/null \
  || compose exec -T postgres psql -U dataprotection -d dataprotection < init_db.sql

compose ps
echo ""

if [[ "$SETUP_ONLY" == true ]]; then
  echo "------------------------------------------------------------"
  echo " Setup complete (--setup-only). Manual reproduction:"
  echo "------------------------------------------------------------"
  echo ""
  echo "Bug traits in processor.py:"
  echo "  • auto_ack=True → premature acknowledgment"
  echo "  • failures → logger.debug only (hidden at INFO)"
  echo "  • weak transactions / new connection per message / returns True on errors"
  echo ""
  echo "Terminal A — buggy processor:"
  echo "  cd \"$SCRIPT_DIR\" && .venv/bin/python processor.py"
  echo ""
  echo "Terminal B — producer:"
  echo "  cd \"$SCRIPT_DIR\" && .venv/bin/python producer.py"
  echo ""
  echo "Terminal C — observe queue vs DB:"
  echo "  docker compose exec rabbitmq rabbitmqctl list_queues name messages"
  echo "  docker compose exec -T postgres psql -U dataprotection -d dataprotection -c \"SELECT COUNT(*) FROM events;\""
  echo ""
  echo "Terminal D — dashboard:"
  echo "  cd \"$SCRIPT_DIR\" && .venv/bin/python dashboard.py   # http://localhost:8080"
  echo ""
  echo "Then stop buggy processor and run:"
  echo "  .venv/bin/python processor_fixed.py"
  echo ""
  exit 0
fi

echo "[5] Reset queue + events table for a clean run..."
PRODUCER_MAX_EVENTS=1 "$PYTHON" producer.py >/dev/null
compose exec -T rabbitmq rabbitmqctl purge_queue "$QUEUE_NAME" &>/dev/null || true
compose exec -T postgres psql -U dataprotection -d dataprotection -c \
  'TRUNCATE events RESTART IDENTITY;' >/dev/null

echo ""
echo "==================== PHASE 1: Buggy processor ===================="
echo "Starting processor.py with DB_PORT=${BAD_DB_PORT} (Postgres unreachable)."
echo "Expect: INFO logs show consumer running; failures only at DEBUG;"
echo "        messages leave the queue (auto_ack) but rows stay at 0."
echo ""

(
  unset POSTGRES_HOST_PORT || true
  export DB_PORT="$BAD_DB_PORT"
  exec "$PYTHON" processor.py
) &
BUG_PID=$!
sleep 4

PRODUCER_MAX_EVENTS="$BUG_PHASE_EVENTS" "$PYTHON" producer.py

wait_for_queue_depth 0 || true

Q1="$(queue_messages)"
Q1="${Q1:-0}"
C1="$(db_event_count)"

kill_bg_safely "$BUG_PID"

echo ""
echo "Phase 1 snapshot: queue_messages=${Q1} events_rows=${C1}"
echo ""

echo "==================== PHASE 2: Fixed processor ===================="
echo "Starting processor_fixed.py with your real DB settings."
echo "Expect: ERROR-level logs on real failures; ack after commit; pooling;"
echo "        queue drains and events_rows ~= messages published."
echo ""

"$PYTHON" processor_fixed.py &
FIX_PID=$!
sleep 5

PRODUCER_MAX_EVENTS="$FIX_PHASE_EVENTS" "$PYTHON" producer.py

wait_for_queue_depth 0 || true

C2="$(db_event_count)"

kill_bg_safely "$FIX_PID"

Q2="$(queue_messages)"
Q2="${Q2:-0}"

echo ""
echo "Phase 2 snapshot: queue_messages=${Q2} events_rows=${C2}"
echo ""

PASS=true
if [[ "${C1:-999}" != "0" ]]; then
  echo "FAIL: Phase 1 expected 0 rows in events after simulated DB outage; got ${C1}."
  PASS=false
fi
if [[ "${Q1:-1}" != "0" ]]; then
  echo "WARN: Phase 1 queue not empty (${Q1}); producer may still be catching up or consumer stuck."
fi

MIN_ACCEPT=$((FIX_PHASE_EVENTS * 90 / 100))
if [[ "${C2:-0}" -lt "$MIN_ACCEPT" ]]; then
  echo "FAIL: Phase 2 expected at least ~${MIN_ACCEPT} rows after publishing ${FIX_PHASE_EVENTS}; got ${C2}."
  PASS=false
fi

if [[ "${Q2:-1}" != "0" ]]; then
  echo "WARN: Phase 2 queue not empty (${Q2}); check processor_fixed logs."
fi

echo "------------------------------------------------------------"
if [[ "$PASS" == true ]]; then
  echo "RESULT: PASS — buggy path dropped writes (${C1} rows); fixed path persisted (${C2} rows)."
else
  echo "RESULT: FAIL — review logs above, POSTGRES_HOST_PORT/RABBITMQ_PORT, and docker compose ps."
  exit 1
fi
echo "------------------------------------------------------------"
