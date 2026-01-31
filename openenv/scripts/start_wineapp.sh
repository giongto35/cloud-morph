#!/bin/bash
# Start application (Wine or Native) with proper path handling

APP_FILE="${APP_FILE:-notepad}"
APP_ARGS="${APP_ARGS:-}"

echo "Starting application: $APP_FILE"
if [ -n "$APP_ARGS" ]; then
    echo "With arguments: $APP_ARGS"
fi

RUN_CMD="exec"

# Start persistent focus loop in background to ensure input registration
(
    TARGET_NAME="${WINDOW_TITLE:-Minesweeper}"
    echo "Starting focus loop for '$TARGET_NAME'..."
    while true; do
        if xdotool search --name "$TARGET_NAME" >/dev/null 2>&1; then
             xdotool search --name "$TARGET_NAME" windowactivate
        fi
        sleep 2
    done
) &

# Check if it is a Windows executable
if [[ "$APP_FILE" == *.exe ]]; then
    RUN_CMD="exec wine"
fi

# Run with the app file (properly quoted)
if [ -n "$APP_ARGS" ]; then
    # Split APP_ARGS by spaces and pass as separate arguments
    IFS=' ' read -ra ARGS <<< "$APP_ARGS"
    $RUN_CMD "$APP_FILE" "${ARGS[@]}"
else
    $RUN_CMD "$APP_FILE"
fi
