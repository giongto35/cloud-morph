docker rm -f apptest

#nvidia-docker run -it --privileged --rm --name "appvm" \
#--runtime=nvidia \
#-e XAUTHORITY -e NVIDIA_DRIVER_CAPABILITIES=all \
#--env "DISPLAY=$DISPLAY" \
#--network=host \
#--volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
#--volume="/usr/lib/x86_64-linux-gnu/libXv.so.1:/usr/lib/x86_64-linux-gnu/libXv.so.1" \
#--volume "winecfg:/root/.wine" syncwine bash

#[/ C:/7554/7554.exe 7554 game 800 600 -w vglrun ]    
nvidia-docker run -it --privileged --rm --name "apptest" \
--runtime=nvidia \
-e XAUTHORITY -e NVIDIA_DRIVER_CAPABILITIES=all \
--network=host \
--env "apppath=/" \
--env "appfile=C:/7554/7554.exe" \
--env "appname=7554" \
--env "hwkey=game" \
--env "screenwidth=800" \
--env "screenheight=600" \
--env "wineoptions=-w" \
--env "vglrun=vglrun" \
--env "dockerhost=127.0.0.1" \
--env "DISPLAY=:99" \
--volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
--volume="/usr/lib/x86_64-linux-gnu/libXv.so.1:/usr/lib/x86_64-linux-gnu/libXv.so.1" \
--volume "winecfg:/root/.wine" vglrun syncwine glxinfo | grep vendor
#xhost -local:root # resetting permissions
#--mount type=bind,source="$(pwd)"/apps,target=/apps \
#--mount type=bind,source="$(pwd)"/supervisord.conf,target=/etc/supervisor/conf.d/supervisord.conf  \
