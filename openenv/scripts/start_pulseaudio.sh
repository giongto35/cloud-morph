#!/bin/bash
# Start a PulseAudio server with a virtual sink so Wine has an audio device.

set -e

# Pulse runtime dir for supervisor-managed processes
export PULSE_RUNTIME_PATH="/tmp/pulse"
mkdir -p "$PULSE_RUNTIME_PATH"
chmod 700 "$PULSE_RUNTIME_PATH"

# Run PulseAudio in system mode with a null sink to avoid hardware deps.
exec pulseaudio \
  --daemonize=no \
  --disallow-exit \
  --exit-idle-time=-1 \
  --log-target=stderr \
  -n \
  -L "module-native-protocol-unix auth-anonymous=1 socket=$PULSE_RUNTIME_PATH/native" \
  -L "module-null-sink sink_name=vsink sink_properties=device.description=VirtualSink" \
  -L "module-null-source source_name=vsource"

