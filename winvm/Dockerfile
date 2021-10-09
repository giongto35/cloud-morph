#FROM golang:1.14
#FROM ubuntu:18.04
FROM ubuntu:20.04
#FROM debian:10-slim

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

# Download gecko and mono installers
COPY download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

RUN mkdir -p /winvm
WORKDIR /winvm
COPY ./ ./
COPY ./default.pa /etc/pulse/
# Compile syncinput.exe
RUN x86_64-w64-mingw32-g++ ./syncinput.cpp -o /winvm/syncinput.exe -lws2_32 -lpthread -static

COPY ./supervisord.conf /etc/supervisor/conf.d/
