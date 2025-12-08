# Wine Environment Docker Image
# Minimal setup for running Windows apps via HTTP API

FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Install base dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    software-properties-common \
    gpg-agent \
    supervisor \
    xvfb \
    mingw-w64 \
    ffmpeg \
    cabextract \
    aptitude \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Wine
RUN dpkg --add-architecture i386 && \
    wget -O - https://dl.winehq.org/wine-builds/winehq.key | apt-key add - && \
    add-apt-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ bionic main' && \
    add-apt-repository ppa:cybermax-dexter/sdl2-backport && \
    aptitude install -y winehq-stable && \
    rm -rf /var/lib/apt/lists/*

# Install winetricks
RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks

# Silence Wine debug messages
ENV WINEDEBUG=fixme-all

# Install common Wine dependencies
RUN winetricks d3dx9_43 || true

# Download gecko and mono installers
COPY scripts/download_gecko_and_mono.sh /tmp/
RUN chmod +x /tmp/download_gecko_and_mono.sh && \
    /tmp/download_gecko_and_mono.sh "$(dpkg -s wine-stable | grep '^Version:' | awk '{print $2}' | sed -E 's/~.*$//')" || true

# Setup directories
RUN mkdir -p /app /apps /app/logs
WORKDIR /app

# Compile syncinput.exe
COPY src/syncinput.cpp /app/
RUN x86_64-w64-mingw32-g++ /app/syncinput.cpp -o /app/syncinput.exe -lws2_32 -lpthread -static

# Install Python dependencies
RUN pip3 install --no-cache-dir fastapi uvicorn numpy opencv-python pillow

# Copy application code
COPY src/server/ /app/server/
COPY src/models.py /app/
RUN touch /app/__init__.py /app/server/__init__.py

# Copy supervisor config
COPY config/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
EXPOSE 8000 9090

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

