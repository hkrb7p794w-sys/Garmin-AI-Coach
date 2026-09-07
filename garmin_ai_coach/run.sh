#!/usr/bin/with-contenv bashio

bashio::log.info "Garmin AI Coach add-on gestartet."

# Ohne das puffert Python seine print()-Ausgaben blockweise, weil stdout kein TTY ist:
# Diagnose-Zeilen wie "[sync] ..." oder "[ai_coach] ..." tauchen dann erst viel spaeter
# (oder gar nicht) im Add-on-Log auf, waehrend die Flask-Zugriffslogs sofort erscheinen -
# was die Fehlersuche massiv erschwert hat.
export PYTHONUNBUFFERED=1

export GEMINI_API_KEY=$(bashio::config 'gemini_api_key')
export GARMIN_EMAIL=$(bashio::config 'garmin_email')
export SYNC_HOUR=$(bashio::config 'sync_hour')
export RACE_DATE=$(bashio::config 'race_date')
export RACE_GOAL=$(bashio::config 'race_goal')

# MQTT-Zugangsdaten werden NICHT automatisch als Umgebungsvariablen injiziert,
# nur weil "services: - mqtt:want" in config.yaml steht - das deklariert nur
# die Abhaengigkeit. Die eigentlichen Werte muessen explizit ueber die
# Supervisor Services API abgefragt werden (siehe Home Assistant Developer
# Docs, "App communication"). Ohne diese Zeilen bleiben MQTT_USERNAME/
# MQTT_PASSWORD leer, der Client verbindet sich anonym und core-mosquitto
# lehnt das mit "not authorised" ab - der eigentliche Grund, warum bisher
# trotz erfolgreichem Sync keine Sensor-Werte in Home Assistant ankamen.
if bashio::services.available "mqtt"; then
    export MQTT_HOST=$(bashio::services mqtt "host")
    export MQTT_PORT=$(bashio::services mqtt "port")
    export MQTT_USERNAME=$(bashio::services mqtt "username")
    export MQTT_PASSWORD=$(bashio::services mqtt "password")
    bashio::log.info "MQTT-Service gefunden: ${MQTT_HOST}:${MQTT_PORT}"
else
    bashio::log.warning "Kein MQTT-Service verfuegbar - Mosquitto-Add-on installiert und gestartet?"
fi

exec python3 /app.py
