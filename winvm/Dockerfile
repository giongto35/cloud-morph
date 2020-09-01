#FROM golang:1.14
FROM ubuntu:18.04
#FROM debian:10-slim

RUN apt-get update -y
RUN apt-get install --no-install-recommends --assume-yes wget software-properties-common gpg-agent supervisor xvfb
RUN apt-get install --no-install-recommends --assume-yes wine64 mingw-w64 ffmpeg cabextract vim

RUN dpkg --add-architecture i386
RUN wget -O - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
RUN add-apt-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main'
RUN add-apt-repository ppa:cybermax-dexter/sdl2-backport

RUN apt-get update -y

RUN apt install -y aptitude
RUN aptitude install -y winehq-stable
RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./ ./
COPY ./supervisord.conf /etc/supervisor/conf.d/

RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks

RUN winetricks d3dx9_43

# Download gecko and mono installers
COPY download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

# Compile synckey.exe
RUN x86_64-w64-mingw32-g++ ./sendkey.cpp -o /winevm/synckey.exe -lws2_32 -static-libgcc -static-libstdc++
## ENTRYPOINT ["/winevm/supervisord"]
