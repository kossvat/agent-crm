#!/bin/bash

echo "Running database migrations..."
alembic upgrade head || echo "WARNING: Alembic migration failed (non-fatal), continuing..."

echo "Starting Agent CRM..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8100
