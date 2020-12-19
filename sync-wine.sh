#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
mkdir -p /tmp/syncwine
docker rm -f appvm | true
docker run -it --privileged --network=host --rm --name "appvm" --mount type=bind,source=/tmp/syncwine,target=/root/syncwine --volume "winecfg:/root/.wine" syncwine cp -r /root/.wine /root/syncwine
