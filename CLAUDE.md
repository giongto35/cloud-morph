# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CloudMorph is a decentralized, self-hosted cloud gaming/application platform that streams Windows applications to web browsers via WebRTC. It virtualizes Windows apps using Wine in Docker containers and streams video/audio with ultra-low latency.

## Common Commands

```bash
# Setup (installs Docker, Go, builds Wine container)
./setup.sh

# Run the server (starts Go server + Docker container)
go run server.go

# Access at http://localhost:8080
# Profiling at http://localhost:3535/debug/pprof

# Run without Docker (debug mode) — requires modifying server.go to use run-wine-nodocker.sh
```

There are no automated tests in this project.

## Architecture

**Data flow:**
```
Browser ←WebRTC(video/audio)→ Go Server ←TCP:9090/UDP:5004,4004→ Docker Container (Wine+FFmpeg+syncinput)
Browser ←WebSocket(input/ctrl)→ Go Server
```

**Video/Audio output:** Wine app → Xvfb virtual display → FFmpeg (x11grab + PulseAudio) → RTP → Go server → WebRTC → browser

**Input path:** Browser → WebSocket → Go server → TCP:9090 → syncinput.exe (C++ WinAPI input injector running in Wine) → Wine application

### Key Packages

- `server.go` — Main entry point; HTTP server, WebSocket handler, WebRTC setup
- `pkg/core/go/cloudapp/` — Core cloud app virtualization logic, manages Docker container lifecycle
- `pkg/core/go/cloudapp/webrtc/` — WebRTC peer connection management (Pion v3)
- `pkg/common/config/` — Configuration parsing from `config.yaml`
- `pkg/common/cws/` — Custom WebSocket wrapper used for input/control events
- `pkg/addon/textchat/` — Text chat service (collaborative mode)
- `pkg/mesh/` — Discovery service client for decentralized app registration
- `discovery/` — Standalone etcd-backed discovery service
- `web/` — Frontend HTML/CSS/JS (native WebRTC + WebSocket)
- `winvm/` — Wine Docker environment, Dockerfile, and supervisord config
- `winvm/syncinput.cpp` — C++ utility that receives input events over TCP and injects them via WinAPI

### Docker Container Internals

Managed by supervisord (`winvm/supervisord.conf`), runs 6 processes:
- Xvfb (virtual display :99)
- Wine + target Windows app
- PulseAudio (virtual audio)
- syncinput.exe (input injection)
- FFmpeg video encoder (x11grab → H264/VPX → RTP to port 5004)
- FFmpeg audio encoder (PulseAudio → Opus → RTP to port 4004)

### Configuration

`config.yaml` controls app path, window title, screen size, video codec (h264/vpx), collaborative mode, and discovery settings.

### OpenEnv (RL Agent Integration)

Located in `openenv/`, provides an HTTP API compatible with Meta's OpenEnv standard for training RL agents on Windows applications. Endpoints: `/reset`, `/step`, `/state`, `/health`. Run with `./openenv/run.sh`. Game-specific scripts: `run_starcraft.sh`, `run_bomberman.sh`, `run_aoe2.sh`, `run_cs16.sh`.

## Tech Stack

Go 1.14+, C++ (WinAPI), JavaScript, Python (FastAPI for OpenEnv), Docker, Wine, Xvfb, FFmpeg, PulseAudio, Pion WebRTC, Gorilla (Mux + WebSocket), etcd
