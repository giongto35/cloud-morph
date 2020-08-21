#!/usr/bin/env bash
#docker build . -t syncwine;
docker run -it --privileged --network=host --rm --env "appfile=notepad" --env "apppath=/" --env "appname=Notepad" --env "DISPLAY=:0" --volume "/tmp/.X11-unix:/tmp/.X11-unix:ro" --volume="${XAUTHORITY:-${HOME}/.Xauthority}:/root/.Xauthority:ro" --volume "winecfg:/root/.wine" syncwine bash
