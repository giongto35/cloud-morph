#FROM golang:1.14
FROM ubuntu:18.04
#FROM debian:10-slim

RUN apt-get update -y
RUN apt-get install --no-install-recommends --assume-yes wget software-properties-common gpg-agent supervisor xvfb
RUN apt-get install --no-install-recommends --assume-yes wine64 mingw-w64

RUN dpkg --add-architecture i386
RUN wget -O - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
RUN add-apt-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main'
RUN add-apt-repository ppa:cybermax-dexter/sdl2-backport

#RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv F987672F
RUN apt-get update -y
#RUN wget -nv https://download.opensuse.org/repositories/Emulators:/Wine:/Debian/xUbuntu_18.04/Release.key -O /tmp/Release.key
#RUN apt-key add - < /tmp/Release.key
#RUN apt-add-repository 'deb https://download.opensuse.org/repositories/Emulators:/Wine:/Debian/xUbuntu_18.04/ ./'

#ARG WINE_BRANCH="stable"
#RUN wget -nv -O- https://dl.winehq.org/wine-builds/winehq.key | APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1 apt-key add - \
    #&& apt-add-repository "deb https://dl.winehq.org/wine-builds/ubuntu/ $(grep VERSION_CODENAME= /etc/os-release | cut -d= -f2) main" \
    #&& dpkg --add-architecture i386 \
    #&& apt-get update \
    #&& DEBIAN_FRONTEND="noninteractive" apt-get install -y --install-recommends winehq-${WINE_BRANCH} \
    #&& rm -rf /var/lib/apt/lists/*
    ##&& apt-add-repository "deb https://dl.winehq.org/wine-builds/ubuntu/ $(grep VERSION_CODENAME= /etc/os-release | cut -d= -f2) main" \

#RUN apt install --install-recommends -y winehq-stable
RUN apt install -y aptitude
RUN aptitude install -y winehq-stable
RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./ ./
COPY ./supervisord.conf /etc/supervisor/conf.d/

RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks


# Download gecko and mono installers
COPY download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

RUN x86_64-w64-mingw32-g++ ./sendkey.cpp -o /winevm/synckey.exe -lws2_32 -static-libgcc -static-libstdc++
## ENTRYPOINT ["/winevm/supervisord"]
