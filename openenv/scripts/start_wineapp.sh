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
    # Switch to the executable's directory
    WORK_DIR=$(dirname "$APP_FILE")
    
    # Symlink to C: drive to make games happy (map Z:\apps\...\Game to C:\Game)
    if [ -d "$WORK_DIR" ]; then
        GAME_DIR_NAME=$(basename "$WORK_DIR")
        FAKE_C_PATH="/root/.wine/drive_c/$GAME_DIR_NAME"
        
        # Only symlink if not already there
        if [ ! -d "$FAKE_C_PATH" ]; then
            echo "Symlinking $WORK_DIR to $FAKE_C_PATH"
            ln -s "$WORK_DIR" "$FAKE_C_PATH"
        fi
        
        # Use the C: path
        WORK_DIR="$FAKE_C_PATH"
        echo "Changing working directory to: $WORK_DIR"
        cd "$WORK_DIR"

        # Import any .reg files found in the directory
        for regfile in *.reg; do
            # Check if file exists (loop expands to literal *.reg if no match)
            if [ -f "$regfile" ]; then
                echo "Importing registry file: $regfile"
                wine regedit /S "$regfile"
            fi
        done

        APP_FILE=$(basename "$APP_FILE")
    fi
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
