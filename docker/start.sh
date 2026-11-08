#!/bin/sh
# Spustí virtuální obrazovku, VNC a noVNC a v ní LocalChef Studio. Když se aplikace zavře, za chvíli se spustí znovu,
# aby kontejner zůstal k dispozici (zastavení: docker stop localchef).
set -e
mkdir -p /data/localchef_data
APP=$(ls /app/localchef_studio_v*.py | sort -V | tail -n 1)
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

Xvfb :99 -screen 0 "${SCREEN_SIZE:-1920x1080x24}" -nolisten tcp &
for i in 1 2 3 4 5 6 7 8 9 10; do
    [ -e /tmp/.X11-unix/X99 ] && break
    sleep 0.5
done
fluxbox >/dev/null 2>&1 &

# VNC jen uvnitř kontejneru; ven jde přes noVNC (heslo volitelně proměnnou VNC_PASSWORD)
if [ -n "${VNC_PASSWORD:-}" ]; then
    x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null
    x11vnc -display :99 -forever -shared -localhost -rfbport 5900 -rfbauth /tmp/vncpass -quiet &
else
    x11vnc -display :99 -forever -shared -localhost -rfbport 5900 -nopw -quiet &
fi
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

cd /data
echo "LocalChef Studio: otevri http://localhost:6080/ v prohlizeci"
while true; do
    python "$APP" || true
    echo "LocalChef Studio se zavrela, spoustim znovu za 3 s"
    sleep 3
done
