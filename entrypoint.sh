#!/bin/sh
set -e

# Run database migrations if DATABASE_URL is configured
if [ -n "$DATABASE_URL" ]; then
    echo "Applying database migrations..."
    alembic upgrade head || echo "Warning: Database migrations skipped or failed, proceeding with service startup..."
    echo "Migrations step completed."
fi

# Respect Render dynamic PORT variable, defaulting to 8000
PORT="${PORT:-8000}"

if [ "$1" = "uvicorn" ]; then
    echo "Starting Uvicorn web server on 0.0.0.0:$PORT..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi

echo "Executing command: $@"
exec "$@"
