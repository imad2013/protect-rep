#!/bin/bash

echo "=============================================="
echo "Stopping all services..."
echo "=============================================="

cd "$(dirname "$0")"

# Stop Docker Compose services
docker compose down

echo ""
echo "All services stopped."
echo "To clean up volumes, run: docker compose down -v"
