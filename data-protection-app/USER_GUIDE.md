# Data Protection App — User Guide

This guide explains how to run the demo stack, reproduce the buggy processor behavior, validate the fixed processor, and operate the dashboard. For deep technical analysis of the bugs and fixes, see [README.md](README.md).

---

## Who this is for

| Audience | Typical goal |
|----------|----------------|
| Engineers learning RabbitMQ ack semantics | See how `auto_ack` and logging levels hide failures |
| Reviewers / trainers | Walk through a scripted pass/fail reproduction |
| Local developers | Run dashboard + processors against Docker infra |
| CI maintainers | Run a single shell script as a smoke/regression check |

---

## Prerequisites

- **Docker** and **Docker Compose** (`docker compose`)
- **Python 3** (3.11+ recommended; use a virtual environment — the scripts use `.venv`)
- Enough disk space for `rabbitmq` and `postgres` images
- Ports available on the host, or willingness to remap ports (see [Configuration](#configuration))

---

## Architecture (conceptual)

```text
producer.py  --->  RabbitMQ (queue: data_protection_events)  --->  processor.py | processor_fixed.py  --->  PostgreSQL (events)
                                                                                              ^
                                                                                              |
                                                                         dashboard.py (reads DB, HTTP :8080)
```

Infra is defined in `docker-compose.yml`. Application processes run **on the host** and connect to **published** Postgres and RabbitMQ ports.

---

## First-time setup

1. Clone or open the repo and go to the app directory:

   ```bash
   cd data-protection-app
   ```

2. Start dependencies and create the Python environment (either path below works).

   **Option A — automated (recommended)**  
   Bring up Docker, venv, and DB; then either run the full test or stop after setup:

   ```bash
   ./run_reproduction.sh --setup-only
   ```

   **Option B — manual**

   ```bash
   docker compose up -d rabbitmq postgres
   # wait until healthy, then:
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   docker compose exec -T postgres psql -U dataprotection -d dataprotection -f /docker-entrypoint-initdb.d/init_db.sql \
     || docker compose exec -T postgres psql -U dataprotection -d dataprotection < init_db.sql
   ```

---

## Configuration

### Port remapping (common on macOS / shared laptops)

Default Compose maps **Postgres → host 5432** and **AMQP → 5672**. If another Postgres or broker already uses those ports, set **host** ports and **matching** Python env vars before `docker compose up` and before any `python *.py`:

| Purpose | Compose variable (host side) | Python / clients |
|--------|--------------------------------|------------------|
| Postgres | `POSTGRES_HOST_PORT` (e.g. `5433`) | Same value is read as DB port when `POSTGRES_HOST_PORT` is set |
| RabbitMQ AMQP | `RABBITMQ_HOST_PORT` (e.g. `5673`) | `RABBITMQ_PORT` must match |
| RabbitMQ UI | `RABBITMQ_MANAGEMENT_HOST_PORT` (e.g. `15673`) | Browser only |

Example:

```bash
export POSTGRES_HOST_PORT=5433
export RABBITMQ_HOST_PORT=5673
export RABBITMQ_MANAGEMENT_HOST_PORT=15673
export RABBITMQ_PORT=5673

docker compose up -d rabbitmq postgres
```

Management UI: `http://localhost:15673` (with the example above) — user/password: `dataprotection` / `dataprotection`.

### Optional `.env.reproduction`

If you create `.env.reproduction` in `data-protection-app/`, `run_reproduction.sh` will `source` it (same directory as the script). Use it to persist exports like the block above.

### Producer batch size

`producer.py` exits after **N** messages when set:

```bash
export PRODUCER_MAX_EVENTS=200
.venv/bin/python producer.py
```

### Reproduction script tuning

| Variable | Default | Meaning |
|----------|---------|---------|
| `BUG_PHASE_EVENTS` | 100 | Messages published in Phase 1 (buggy processor) |
| `FIX_PHASE_EVENTS` | 80 | Messages published in Phase 2 (fixed processor) |
| `BAD_DB_PORT` | 65432 | Intentionally wrong Postgres port for Phase 1 |
| `WAIT_QUEUE_DRAIN_SEC` | 120 | Max seconds to wait for queue depth 0 |

---

## Use cases

### UC1 — Automated regression: buggy path vs fixed path (PASS/FAIL)

**Goal:** Prove that the buggy consumer drops persistence under simulated DB failure, then prove the fixed consumer persists rows.

**Steps:**

```bash
cd data-protection-app
# export ports if needed (see Configuration)
./run_reproduction.sh
```

**Expect:**

- Script exits **0** and prints `RESULT: PASS`.
- Phase 1: `events` row count stays **0** (buggy processor + unreachable DB port in the script).
- Phase 2: row count reaches at least ~**90%** of `FIX_PHASE_EVENTS`, queue depth **0**.

**When to use:** Quick validation after changes, demos, CI-style checks.

---

### UC2 — Interactive workshop: watch the buggy processor

**Goal:** Manually run `processor.py`, publish events, inspect queue vs database and logs (see [README.md](README.md) for bug details).

**Steps:**

```bash
./run_reproduction.sh --setup-only   # or ensure compose + venv + DB already up
```

Follow the printed instructions: one terminal for `.venv/bin/python processor.py`, one for `.venv/bin/python producer.py`, optional `rabbitmqctl` / `psql` / dashboard.

**When to use:** Training, live debugging, comparing log levels (set logging to DEBUG to surface hidden errors).

---

### UC3 — Verify only the fixed processor

**Goal:** Confirm `processor_fixed.py` writes to Postgres and drains the queue.

**Steps:**

```bash
docker compose up -d rabbitmq postgres
# set POSTGRES_HOST_PORT / RABBITMQ_PORT if required
.venv/bin/python processor_fixed.py
# another terminal:
PRODUCER_MAX_EVENTS=50 .venv/bin/python producer.py
docker compose exec -T postgres psql -U dataprotection -d dataprotection -c "SELECT COUNT(*) FROM events;"
```

**When to use:** After editing `processor_fixed.py` or infrastructure.

---

### UC4 — Dashboard only (operators / stakeholders)

**Goal:** View totals and recent events in a browser.

**Steps:**

```bash
# Postgres must be reachable with the same DB port as Compose
export POSTGRES_HOST_PORT=5433   # if you use remapped Postgres
.venv/bin/python dashboard.py
```

Open **http://localhost:8080**.

**When to use:** Showing event volume without using the CLI; requires existing data in `events`.

---

### UC5 — Clean shutdown and reset

**Goal:** Stop containers; optionally wipe broker/DB volumes for a fresh demo.

```bash
./stop.sh
# Remove data volumes (destructive):
docker compose down -v
```

**When to use:** Before a clean room demo or after schema experiments.

---

### UC6 — CI / headless runner

**Goal:** Single command, non-interactive, exit code reflects success.

```bash
cd data-protection-app
export POSTGRES_HOST_PORT=5433 RABBITMQ_PORT=5673   # if needed
./run_reproduction.sh
echo $?
```

**When to use:** Pipelines where Docker is available and you need a deterministic check.

---

## Handy commands

| Task | Command |
|------|---------|
| Service status | `docker compose ps` |
| Queue depth | `docker compose exec rabbitmq rabbitmqctl list_queues name messages` |
| Event count | `docker compose exec -T postgres psql -U dataprotection -d dataprotection -c "SELECT COUNT(*) FROM events;"` |
| RabbitMQ UI | Browser to mapped port **15672** (or **15673** if remapped) |

---

## Troubleshooting

| Symptom | Likely cause | What to do |
|---------|----------------|------------|
| `FATAL: role "dataprotection" does not exist` on **127.0.0.1:5432** | Dashboard/processor hitting **host** Postgres, not the container | Set `POSTGRES_HOST_PORT` to the **published** host port and restart the app |
| `ModuleNotFoundError: psycopg2` | Dependencies not installed in the interpreter you ran | `.venv/bin/pip install -r requirements.txt` and use `.venv/bin/python` |
| Broken emoji / `ðŸ"` in dashboard title | Missing UTF-8 charset on HTML response | Already addressed in `dashboard.py`; restart dashboard |
| RabbitMQ fails to bind **5672** | Another broker (or Java AMQP) on host | Use `RABBITMQ_HOST_PORT` + `RABBITMQ_PORT` overrides |
| `./run_reproduction.sh` exits **1** | Infra not ready, wrong ports, or processor mismatch | Run `docker compose ps`, verify exports, read script output |

---

## File map (quick reference)

| File | Role |
|------|------|
| `docker-compose.yml` | RabbitMQ + Postgres |
| `producer.py` | Publishes JSON events; optional `PRODUCER_MAX_EVENTS` |
| `processor.py` | Intentionally buggy consumer |
| `processor_fixed.py` | Corrected consumer (ack after commit, pooling, nack on failure) |
| `dashboard.py` | HTTP UI on port 8080 |
| `run_reproduction.sh` | Full automation or `--setup-only` |
| `stop.sh` | `docker compose down` |
| `init_db.sql` | `events` table and grants |

---

## See also

- [README.md](README.md) — root cause narrative, bug list, and expected behavior tables
