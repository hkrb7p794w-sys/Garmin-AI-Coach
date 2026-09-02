#!/usr/bin/with-contenv bashio
bashio::log.info "Garmin AI Coach – Platzhalter-Webserver läuft auf Port 8099"
mkdir -p /www
cat > /www/index.html << 'HTML'
<!DOCTYPE html>
<html>
<head><title>Garmin AI Coach</title></head>
<body style="font-family: sans-serif; padding: 2rem;">
  <h1>Garmin AI Coach</h1>
  <p>Grundgerüst läuft. Sync-Script folgt im nächsten Schritt.</p>
</body>
</html>
HTML
cd /www
python3 -m http.server 8099