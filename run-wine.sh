#!/usr/bin/env bash
cd winvm
# pkill ffmpeg
# ffmpeg -f pulse -i default -t 30 -c:a libopus -f mulaw -f rtp rtp://127.0.0.1:4004 &
#-p 5004:5004 -p 4004:4000 -p 9090:9090 \
#--network=host \
#--expose 5004/udp --expose 4004/udp --expose 9090/udp \
#--publish-all \
#-p 4004:4004/udp -p 5004:5004/udp -p 9090:9090/udp --publish-all \
docker build -t syncwine .
docker rm -f appvm
if [ $(uname -s) == "darwin" ]
then
    echo "Spawn container on Mac"
    docker run -t -d --privileged --rm --name "appvm" \
    --mount type=bind,source="$(pwd)"/apps,target=/apps \
    --expose 9090 \
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
#docker run -d syncwine bash
echo "DONE"
exit 0
