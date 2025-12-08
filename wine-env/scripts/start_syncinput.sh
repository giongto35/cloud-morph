#!/bin/bash
# Wait for http_server to be listening on port 9090 before starting syncinput

echo "Waiting for HTTP server input listener on port 9090..."
for i in {1..30}; do
    if nc -z 127.0.0.1 9090 2>/dev/null; then
        echo "Port 9090 is ready"
        break
    fi
    sleep 1
done

echo "Starting syncinput.exe..."
exec wine /app/syncinput.exe "$@"

