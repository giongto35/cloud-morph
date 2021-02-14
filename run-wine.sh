#!/usr/bin/env bash
cd winvm
# pkill ffmpeg
# ffmpeg -f pulse -i default -t 30 -c:a libopus -f mulaw -f rtp rtp://127.0.0.1:4004 &
docker build -t syncwine .
docker rm -f appvm
docker run -d --privileged --network=host --rm --name "appvm" \
--mount type=bind,source="$(pwd)"/apps,target=/apps \
--mount type=bind,source="$(pwd)"/supervisord.conf,target=/etc/supervisor/conf.d/supervisord.conf \
--env "apppath=$1" \
--env "appfile=$2" \
--env "appname=$3" \
--env "hwkey=$4" \
--env "screenwidth=$5" \
--env "screenheight=$6" \
--env "wineoptions=$7" \
--env "DISPLAY=:99" \
-v /run/dbus-1/:/run/dbus-1/ -v /dev/shm:/dev/shm \
-v /var/run/dbus/:/var/run/dbus/ \
-v /etc/dbus-1/:/etc/dbus-1/ \
--volume "winecfg:/root/.wine" syncwine supervisord
