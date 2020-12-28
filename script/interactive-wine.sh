#!/usr/bin/env bash
# Script to pre-setup environment in local wine before deploying to server

# docker build -t syncwine .
echo $1
echo $2

#apppath="$(pwd)"/../winvm/apps
apppath=$(pwd)
if [ "$2" != "" ]; then
    apppath=$2
fi

docker rm -f appvm | true |> /dev/null
docker run -it --privileged --network=host --rm --name "appvm" --mount type=bind,source="$apppath",target=/apps --env=DISPLAY --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume="/tmp/.X11-unix:/tmp/.X11-unix:ro" --volume "winecfg:/root/.wine" syncwine bash -c "$1"
