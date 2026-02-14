# Wine Environment Docker Image
# Minimal setup for running Windows apps via HTTP API

FROM ubuntu:22.04

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
    python3-tk \
    python3-dev \
    netcat-openbsd \
    pulseaudio \
    libpulse0 \
    alsa-utils \
    # Window management and automation tools
    fluxbox \
    x11-utils \
    xdotool \
    && rm -rf /var/lib/apt/lists/*

# Install Wine from Ubuntu repositories
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    wine \
    wine32 \
    wine64 \
    libwine \
    libpulse0:i386 && \
    rm -rf /var/lib/apt/lists/*

# Install winetricks
RUN wget -nv -O /usr/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks \
    && chmod +x /usr/bin/winetricks

# Silence Wine debug messages
ENV WINEDEBUG=fixme-all

# Install common Wine dependencies
RUN winetricks d3dx9_43 || true
RUN winetricks -q sound=pulse || true

# Copy helper scripts
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

# Download gecko and mono installers
RUN /app/scripts/download_gecko_and_mono.sh "$(dpkg -s wine | grep '^Version:' | awk '{print $2}' | sed -E 's/~.*$//')" || true

# Setup directories
RUN mkdir -p /app /apps /app/logs
WORKDIR /app

# Install native minesweeper
RUN apt-get update && apt-get install -y gnome-mines



# Compile syncinput.exe
COPY src/syncinput.cpp /app/
RUN x86_64-w64-mingw32-g++ /app/syncinput.cpp -o /app/syncinput.exe -lws2_32 -lpthread -static

# Install Python dependencies
RUN pip3 install --no-cache-dir fastapi uvicorn numpy opencv-python pillow mss

# Copy application code
COPY src/server/ /app/server/
COPY src/models.py /app/
RUN touch /app/__init__.py /app/server/__init__.py
COPY examples/ /app/examples/

# Copy supervisor config
COPY config/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY config/asound.conf /etc/asound.conf

# Expose ports
EXPOSE 8000 9090



CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
