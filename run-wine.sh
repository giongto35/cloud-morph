#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
docker rm -f gamevm
docker run -d --network=host --env "USE_XVFB=yes" --env "XVFB_SERVER=:99" --env "DISPLAY=:99" --env "XVFB_RESOLUTION=1280x800x16" --env "XVFB_SCREEN=0" --env "TZ=Asia/Singapore" --name "gamevm" --rm --mount type=bind,source="$(pwd)"/games,target=/games --hostname="$(hostname)" --shm-size=1g --volume=winehome:/home/wineuser --workdir=/home/wineuser syncwine $@