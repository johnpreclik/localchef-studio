# LocalChef Studio v Dockeru: desktopová aplikace (PyQt6 + Qt WebEngine) na virtuální obrazovce (Xvfb),
# ovládání z prohlížeče přes noVNC (port 6080), mobilní aplikace na portu 3665.
# Sestavení z kořene repozitáře:  docker build -t localchef-studio -f docker/Dockerfile .
#   --build-arg WITH_ARGOS=0  vynechá offline překladač (obraz je o ~2 GB menší)
FROM python:3.13-slim-bookworm

ARG WITH_ARGOS=1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DISPLAY=:99 \
    SCREEN_SIZE=1920x1080x24 \
    QT_QPA_PLATFORM=xcb \
    QTWEBENGINE_DISABLE_SANDBOX=1 \
    QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-dev-shm-usage"

# virtuální obrazovka, VNC, noVNC, písma (čeština + barevné emoji na tlačítkách) a knihovny pro Qt WebEngine
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc fluxbox novnc websockify procps \
        fontconfig fonts-dejavu fonts-noto-core fonts-noto-color-emoji \
        libnss3 libnspr4 libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
        libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 \
        libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxi6 libxss1 libxshmfence1 \
        libgbm1 libgl1 libegl1 libdrm2 libdbus-1-3 libasound2 libfontconfig1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && printf '<!DOCTYPE html><meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=1&resize=scale&reconnect=1">\n' \
        > /usr/share/novnc/index.html

WORKDIR /app
COPY requirements.txt .
# offline překladač potřebuje torch – stačí verze pro procesor (CPU), je mnohem menší
RUN grep -v -i argostranslate requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt \
    && if [ "$WITH_ARGOS" = "1" ]; then \
         pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
         && pip install --no-cache-dir argostranslate; \
       fi

# soubor aplikace má verzi v názvu (localchef_studio_v1.5.py)
COPY localchef_studio_v*.py DISCLAIMER.txt ./
COPY docker/start.sh /usr/local/bin/localchef-start
RUN chmod +x /usr/local/bin/localchef-start

# data aplikace (recepty, nastavení, klíče, přihlášení) – vždy jako svazek z hostitele
WORKDIR /data
VOLUME ["/data/localchef_data"]
EXPOSE 6080 3665
CMD ["localchef-start"]
