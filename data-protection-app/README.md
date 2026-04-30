# Data Protection Dashboard - Issue Reproduction

**How to run the stack, configure ports, and walk through scenarios:** see [USER_GUIDE.md](USER_GUIDE.md).

This application reproduces the issue where:
- Data protection dashboard shows zero events
- Python event-processor service is running
- No new records appear in PostgreSQL events table
- RabbitMQ queue length is growing
- No errors in the logs

## Root Cause

The issue is caused by a **silent message acknowledgment failure**. The consumer receives messages from RabbitMQ but fails to commit them properly due to incorrect acknowledgment timing, causing messages to be re-queued indefinitely while appearing "processed" with no errors logged.

## Architecture

```
[Event Producer] --> [RabbitMQ Queue] --> [Event Processor] --> [PostgreSQL]
                                              |
                                              v
                                       [Dashboard UI]
```

## Components

1. **producer.py** - Generates data protection events and publishes to RabbitMQ
2. **processor.py** - Consumes events from RabbitMQ and writes to PostgreSQL (BUGGY)
3. **processor_fixed.py** - Fixed version with proper acknowledgment handling
4. **dashboard.py** - Simple web UI showing event counts from PostgreSQL
5. **docker-compose.yml** - Orchestrates RabbitMQ, PostgreSQL, and services
6. **init_db.sql** - Database schema initialization

## Quick Start

```bash
# Run the reproduction setup script
./run_reproduction.sh
```

Or manually:

```bash
# Start infrastructure
docker compose up -d rabbitmq postgres

# Wait for services to be ready
sleep 10

# Initialize database
docker compose exec -T postgres psql -U dataprotection -d dataprotection < init_db.sql

# Start the buggy processor (reproduces the issue)
python processor.py &

# Start producing events
python producer.py

# In another terminal, check queue growth
watch 'docker compose exec rabbitmq rabbitmqctl list_queues name messages'

# Check PostgreSQL (will show zero or very few records)
docker compose exec -T postgres psql -U dataprotection -d dataprotection -c "SELECT COUNT(*) FROM events;"

# Access dashboard at http://localhost:8080
python dashboard.py
```

## Testing the Fix

To verify the fix works, stop the buggy processor and run the fixed version:

```bash
# Stop the buggy processor (Ctrl+C or kill the process)

# Run the fixed processor
python processor_fixed.py

# Continue producing events in another terminal
python producer.py

# Now check the database - events should appear!
docker compose exec -T postgres psql -U dataprotection -d dataprotection -c "SELECT COUNT(*) FROM events;"

# Dashboard should now show increasing event counts
```

## The Bug Details

The bug in `processor.py` has multiple issues:

1. **Auto-acknowledgment enabled** (`auto_ack=True`): Messages are acknowledged by RabbitMQ immediately upon delivery, BEFORE the callback function processes them. This means:
   - If processing fails, the message is already gone from the queue
   - No retry mechanism is possible
   - Messages appear "processed" even when they're not

2. **Silent failures**: Exceptions are caught but logged at DEBUG level, which is not visible with the default INFO logging configuration. This creates the illusion of "no errors in logs."

3. **No transaction management**: Database operations don't use explicit transactions, so partial failures can leave data in an inconsistent state.

4. **Connection per message**: Creating a new database connection for each message is inefficient and can exhaust connection limits.

5. **Always returns success**: The `process_event()` function always returns `True`, even when exceptions occur, preventing any failure handling.

## How the Fix Works

The `processor_fixed.py` addresses all these issues:

1. **Manual acknowledgment** (`auto_ack=False`): Messages are only acknowledged AFTER successful database commit
2. **Proper error logging**: Errors are logged at ERROR level with stack traces
3. **Transaction management**: Explicit commits and rollbacks ensure data consistency
4. **Connection pooling**: Reuses database connections efficiently
5. **Nack on failure**: Failed messages are nacked with `requeue=True` to retry processing
6. **Graceful shutdown**: Proper signal handling ensures clean termination

## Expected Behavior

### With Buggy Processor:
- ✅ RabbitMQ queue length GROWS continuously
- ✅ PostgreSQL events table shows ZERO or very few records
- ✅ Dashboard shows zero events
- ✅ Processor logs show no errors (INFO level only)
- ✅ Processor process appears healthy/running

### With Fixed Processor:
- ✅ RabbitMQ queue length remains stable (messages consumed as fast as produced)
- ✅ PostgreSQL events table grows with processed events
- ✅ Dashboard shows increasing event counts
- ✅ Processor logs show successful processing messages
- ✅ Errors are properly logged if they occur
