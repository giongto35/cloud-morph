#!/bin/bash
# Start Wine application with proper environment and path handling

APP_FILE="${APP_FILE:-notepad}"
APP_ARGS="${APP_ARGS:-}"

echo "Starting application: $APP_FILE"
if [ -n "$APP_ARGS" ]; then
    echo "With arguments: $APP_ARGS"
fi

RUN_CMD="exec wine"

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
    # Extract the directory where the exe is located
    WORK_DIR=$(dirname "$APP_FILE")
    
    # If it's an absolute path with a directory
    if [ -d "$WORK_DIR" ]; then
        # Get just the game folder name for the C: drive path
        GAME_DIR_NAME=$(basename "$WORK_DIR")
        
        # Create symlink in Wine's C: drive
        FAKE_C_PATH="/root/.wine/drive_c/$GAME_DIR_NAME"
        
        if [ ! -d "$FAKE_C_PATH" ]; then
            echo "Symlinking $WORK_DIR to $FAKE_C_PATH"
            ln -s "$WORK_DIR" "$FAKE_C_PATH"
        fi
        
        # Change to the game directory
        cd "$FAKE_C_PATH"
        
        # Import any .reg files found in the directory
        for regfile in *.reg; do
            if [ -f "$regfile" ]; then
                echo "Importing registry file: $regfile"
                wine regedit /S "$regfile"
            fi
        done
        
        # Use just the executable name since we're in the right directory
        APP_FILE=$(basename "$APP_FILE")
    fi
    
    RUN_CMD="exec wine"
fi

# Execute the application
if [ -n "$APP_ARGS" ]; then
    # Split APP_ARGS on whitespace
    IFS=' ' read -ra ARGS <<< "$APP_ARGS"
    $RUN_CMD "$APP_FILE" "${ARGS[@]}"
else
    $RUN_CMD "$APP_FILE"
fi
