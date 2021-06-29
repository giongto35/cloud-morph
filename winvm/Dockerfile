#FROM golang:1.14
#FROM ubuntu:18.04
FROM nvidia/cudagl:11.3.1-base-ubuntu20.04
ENV DEBIAN_FRONTEND=noninteractive 
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES compute,graphics,utility,video

RUN apt update
RUN apt-get update -y
RUN apt-get clean
RUN apt-get autoremove
RUN apt-get update -y
RUN apt-get install --no-install-recommends --assume-yes wget software-properties-common gpg-agent supervisor xvfb mingw-w64 ffmpeg cabextract aptitude vim pulseaudio

RUN dpkg --add-architecture i386
RUN wget -O - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
RUN add-apt-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main' 
RUN add-apt-repository ppa:cybermax-dexter/sdl2-backport

RUN aptitude install -y winehq-stable

RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks

# Silence all the "fixme: blah blah blah" messages from wine
ENV WINEDEBUG fixme-all
RUN winetricks d3dx9_43
# uncomment it for lutris game
#RUN winetricks --force -q dotnet48

ENV VIRTUALGL_VERSION 2.5.2
# Download gecko and mono installers
COPY download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglu1-mesa-dev mesa-utils curl ca-certificates xterm && \
    curl -sSL https://downloads.sourceforge.net/project/virtualgl/"${VIRTUALGL_VERSION}"/virtualgl_"${VIRTUALGL_VERSION}"_amd64.deb -o virtualgl_"${VIRTUALGL_VERSION}"_amd64.deb && \
    dpkg -i virtualgl_*_amd64.deb && \
    /opt/VirtualGL/bin/vglserver_config -config +s +f -t && \
    rm virtualgl_*_amd64.deb && \
    apt-get clean && \
    apt-get remove -y curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
LABEL com.nvidia.volumes.needed="nvidia_driver"
ENV PATH /usr/local/nvidia/bin:/opt/VirtualGL/bin:${PATH}
ENV LD_LIBRARY_PATH /usr/local/nvidia/lib:/usr/local/nvidia/lib64:${LD_LIBRARY_PATH}/lists/*

RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./ ./
COPY ./default.pa /etc/pulse/
# Compile syncinput.exe
RUN x86_64-w64-mingw32-g++ ./syncinput.cpp -o /winevm/syncinput.exe -lws2_32 -lpthread -static

COPY ./supervisord.conf /etc/supervisor/conf.d/
