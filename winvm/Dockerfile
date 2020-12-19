#FROM golang:1.14
FROM ubuntu:18.04
#FROM debian:10-slim

RUN apt update
RUN apt-get update -y
RUN apt-get install --no-install-recommends --assume-yes wget software-properties-common gpg-agent supervisor xvfb wine64 mingw-w64 ffmpeg cabextract aptitude

RUN dpkg --add-architecture i386
RUN wget -O - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
RUN add-apt-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main'
RUN add-apt-repository ppa:cybermax-dexter/sdl2-backport

RUN aptitude install -y winehq-stable

RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks
RUN winetricks d3dx9_43

# Download gecko and mono installers
COPY download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./ ./
COPY ./supervisord.conf /etc/supervisor/conf.d/

# Compile synckey.exe
RUN x86_64-w64-mingw32-g++ ./syncinput.cpp -o /winevm/synckey.exe -lws2_32 -lpthread -static
## ENTRYPOINT ["/winevm/supervisord"]
