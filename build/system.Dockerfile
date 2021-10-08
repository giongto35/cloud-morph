FROM debian:bullseye-slim

# WineHQ
RUN apt-get -qq update && apt-get -qq -y install wget gnupg \
 && dpkg --add-architecture i386 \
 && wget -nc https://dl.winehq.org/wine-builds/winehq.key \
 && apt-key add winehq.key \
 && echo 'deb https://dl.winehq.org/wine-builds/debian/ bullseye main' >> /etc/apt/sources.list

# install required packages
RUN apt-get -qq update && apt-get -qq install --install-recommends -y \
    winehq-stable

# winetricks
RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
 && chmod +x /usr/bin/winetricks \
 && export WINEDEBUG=fixme-all \
 && apt-get -qq install -y cabextract \
 && winetricks d3dx9_43
# uncomment it for lutris game
# RUN winetricks --force -q dotnet48

# Download gecko and mono installers
COPY ./download_gecko_and_mono.sh /root/download_gecko_and_mono.sh
RUN chmod +x /root/download_gecko_and_mono.sh \
    && /root/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep "^Version:\s" | awk '{print $2}' | sed -E 's/~.*$//')"

RUN apt-get -qq update && apt-get -qq -y install \
    software-properties-common \
    gpg-agent \
    supervisor \
    xvfb \
    ffmpeg \
    vim \
    pulseaudio \
 && apt-get clean \
 && apt-get autoremove \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /winevm
WORKDIR /winevm
COPY ./default.pa /etc/pulse/
COPY ./supervisord.conf /etc/supervisor/conf.d/

# to add syncinput
