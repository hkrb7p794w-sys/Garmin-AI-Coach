#!/usr/bin/with-contenv bashio
# Fit Coach - Startskript

bashio::log.info "Fit Coach startet."
export PYTHONUNBUFFERED=1
export FIT_VERSION="$(bashio::addon.version 2>/dev/null || echo 0.1.0)"
export SYNC_HOURS="$(bashio::config 'sync_hours')"
export EXERCISE_ALIAS_FILE="/share/fit_coach/exercise_aliases.json"

# MQTT-Zugangsdaten kommen über die Supervisor-Services-API ("services: mqtt:need").
if bashio::services.available "mqtt"; then
    export MQTT_HOST="$(bashio::services mqtt 'host')"
    export MQTT_PORT="$(bashio::services mqtt 'port')"
    export MQTT_USERNAME="$(bashio::services mqtt 'username')"
    export MQTT_PASSWORD="$(bashio::services mqtt 'password')"
    bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"
else
    bashio::log.warning "Kein MQTT-Dienst gefunden - ist das Mosquitto-Broker-App installiert und gestartet?"
fi

cd /app
exec python3 /app/main.py
