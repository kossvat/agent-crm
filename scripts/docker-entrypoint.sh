#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Agent CRM..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8100
