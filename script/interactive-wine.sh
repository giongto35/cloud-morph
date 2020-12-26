#!/usr/bin/env bash
# Script to pre-setup environment in local wine before deploying to server

# docker build -t syncwine .
echo $1
echo $2

apppath="$(pwd)"/../winvm/apps
if [ "$2" != "" ]; then
    apppath=$2
fi

docker rm -f appvm | true
docker run -it --privileged --network=host --rm --name "appvm" --mount type=bind,source="$apppath",target=/apps --env=DISPLAY --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume="/tmp/.X11-unix:/tmp/.X11-unix:ro" --volume "winecfg:/root/.wine" syncwine $1
 #docker run -it --privileged --network=host --rm --name "appvm" -v "$(pwd)/synccfg:/root/synccfg" --mount type=bind,source="$(pwd)"/apps,target=/apps --env=DISPLAY --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume="/tmp/.X11-unix:/tmp/.X11-unix:ro" --volume "winecfg:/root/.wine" syncwine $1
#docker run --volume "winecfg:/root/.wine" --mount type=bind,source="$(pwd)"/apps,target=/apps ubuntu /bin/bash
