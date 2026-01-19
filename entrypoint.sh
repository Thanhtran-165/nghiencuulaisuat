#!/bin/bash
set -e

# Create necessary directories
mkdir -p /app/data/duckdb /app/data/raw /app/logs

# Run database migrations (if any)
# python -m app.db.migrate

# Execute the main command
exec "$@"
