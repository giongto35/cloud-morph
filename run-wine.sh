#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
docker rm -f appvm
docker run -d --privileged --network=host --rm --name "appvm" --mount type=bind,source="$(pwd)"/apps,target=/apps --env "appfile=$2" --env "apppath=$1" --env "appname=$3" --env "hwkey=$4" --env "DISPLAY=:99" --volume "winecfg:/root/.wine" syncwine supervisord
