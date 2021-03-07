#!/usr/bin/env bash
cd winvm
docker build -t syncwine .
docker rm -f appvm
if [ $(uname -s) == "Darwin" ]
then
    echo "Spawn container on Mac"
    docker run -d --privileged --rm --name "appvm" \
    --mount type=bind,source="$(pwd)"/apps,target=/apps \
    --mount type=bind,source="$(pwd)"/supervisord.conf,target=/etc/supervisor/conf.d/supervisord.conf  \
    --env "apppath=$1" \
    --env "appfile=$2" \
    --env "appname=$3" \
    --env "hwkey=$4" \
    --env "screenwidth=$5" \
    --env "screenheight=$6" \
    --env "wineoptions=$7" \
    --env "dockerhost=host.docker.internal" \
    --env "DISPLAY=:99" \
    --volume "winecfg:/root/.wine" syncwine supervisord
else 
    echo "Spawn container on Linux"
    docker run -t -d --privileged --rm --name "appvm" \
    --mount type=bind,source="$(pwd)"/apps,target=/apps \
    --mount type=bind,source="$(pwd)"/supervisord.conf,target=/etc/supervisor/conf.d/supervisord.conf  \
    --network=host \
    --env "apppath=$1" \
    --env "appfile=$2" \
    --env "appname=$3" \
    --env "hwkey=$4" \
    --env "screenwidth=$5" \
    --env "screenheight=$6" \
    --env "wineoptions=$7" \
    --env "dockerhost=127.0.0.1" \
    --env "DISPLAY=:99" \
    --volume "winecfg:/root/.wine" syncwine supervisord
fi
