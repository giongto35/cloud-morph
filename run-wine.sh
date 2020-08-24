#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
docker rm -f gamevm
docker run -d --privileged --network=host --rm --name "gamevm" --mount type=bind,source="$(pwd)"/games,target=/games --env "appfile=$2" --env "apppath=$1" --env "appname=$3" --env "DISPLAY=:99" --volume "winecfg:/root/.wine" syncwine supervisord
