#!/bin/sh
set -e

# Fix ownership of data and logs directories for the mounted volume
chown -R app:app /app/data /app/logs

# Execute the main command
exec "$@"
