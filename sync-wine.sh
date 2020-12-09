#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
docker rm -f appvm
#docker run -it --privileged --network=host --rm --name "appvm" --mount type=bind,source="$(pwd)"/apps,target=/apps --env=DISPLAY --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume="/tmp/.X11-unix:/tmp/.X11-unix:ro" -v "$(pwd)/.wine:/root/.wine" syncwine $1
docker run -it --privileged --network=host --rm --name "appvm" --mount type=bind,source="$(pwd)"/apps,target=/apps --env=DISPLAY --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume="/tmp/.X11-unix:/tmp/.X11-unix:ro" --volume "winecfg:/root/.wine" syncwine $1
