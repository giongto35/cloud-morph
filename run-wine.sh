#!/usr/bin/env bash
cd winvm
# docker build -t syncwine .
docker rm -f appvm
echo "$1"
echo "$2"
echo "$3"
echo "$4"
echo "$5"
echo "$6"
echo "$7"
docker run -d --privileged --network=host --rm --name "appvm" --mount type=bind,source="$(pwd)"/apps,target=/apps \
--env "apppath=$1" \
--env "appfile=$2" \
--env "appname=$3" \
--env "hwkey=$4" \
--env "screenwidth=$5" \
--env "screenheight=$6" \
--env "wineoptions=$7" \
--env "DISPLAY=:99" \
--volume "winecfg:/root/.wine" syncwine supervisord
