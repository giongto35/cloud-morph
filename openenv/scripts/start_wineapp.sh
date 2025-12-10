#!/bin/bash
# Start Wine application with proper path handling

APP_FILE="${APP_FILE:-notepad}"
APP_ARGS="${APP_ARGS:-}"

echo "Starting Wine application: $APP_FILE"
if [ -n "$APP_ARGS" ]; then
    echo "With arguments: $APP_ARGS"
fi

# Run Wine with the app file (properly quoted)
# If APP_ARGS is set, split it and pass as separate arguments
if [ -n "$APP_ARGS" ]; then
    # Split APP_ARGS by spaces and pass as separate arguments
    IFS=' ' read -ra ARGS <<< "$APP_ARGS"
    exec wine "$APP_FILE" "${ARGS[@]}"
else
    exec wine "$APP_FILE"
fi





