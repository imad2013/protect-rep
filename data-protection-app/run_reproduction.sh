#!/bin/bash

echo "=============================================="
echo "Data Protection Dashboard - Issue Reproduction"
echo "=============================================="
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose is not installed"
    exit 1
fi

cd "$(dirname "$0")"

echo "[1/6] Starting RabbitMQ and PostgreSQL..."
docker compose up -d rabbitmq postgres

echo "[2/6] Waiting for services to be ready..."
sleep 15

echo "[3/6] Checking service health..."
docker compose ps

echo ""
echo "[4/6] Installing Python dependencies..."
pip install -q -r requirements.txt

echo ""
echo "[5/6] Initializing database..."
# Wait a bit more for Postgres to be fully ready
sleep 5
docker compose exec -T postgres psql -U dataprotection -d dataprotection -f /docker-entrypoint-initdb.d/init_db.sql 2>/dev/null || \
docker compose exec -T postgres psql -U dataprotection -d dataprotection < init_db.sql

echo ""
echo "=============================================="
echo "Setup complete! Now run the following commands:"
echo "=============================================="
echo ""
echo "Terminal 1 - Start the buggy processor:"
echo "  python processor.py"
echo ""
echo "Terminal 2 - Start producing events:"
echo "  python producer.py"
echo ""
echo "Terminal 3 - Monitor queue length:"
echo "  watch 'docker compose exec rabbitmq rabbitmqctl list_queues name messages'"
echo ""
echo "Terminal 4 - Check database (will show zero or few records):"
echo "  docker compose exec -T postgres psql -U dataprotection -d dataprotection -c 'SELECT COUNT(*) FROM events;'"
echo ""
echo "Terminal 5 - View dashboard:"
echo "  python dashboard.py"
echo "  Then open http://localhost:8080 in your browser"
echo ""
echo "=============================================="
echo "Expected behavior:"
echo "- RabbitMQ queue length will GROW continuously"
echo "- PostgreSQL events table will show ZERO or very few records"
echo "- Dashboard will show zero events"
echo "- Processor logs will show no errors (INFO level only)"
echo "- Processor process will appear healthy/running"
echo "=============================================="
