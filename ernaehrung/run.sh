#!/usr/bin/with-contenv bashio
# Ernährung - Startskript

bashio::log.info "Ernährung startet."
export PYTHONUNBUFFERED=1
export APP_VERSION="$(bashio::addon.version 2>/dev/null || echo 0.1.0)"
export GEMINI_API_KEY="$(bashio::config 'gemini_api_key')"
export GEMINI_MODEL="$(bashio::config 'gemini_model')"
export NUTRITION_DB="/data/ernaehrung.db"
export BLS_DB="/data/bls.db"
export PHOTO_DIR="/data/photos"
export NUTRITION_SHARE="/share/ernaehrung"
mkdir -p /share/ernaehrung

if bashio::services.available "mqtt"; then
    export MQTT_HOST="$(bashio::services mqtt 'host')"
    export MQTT_PORT="$(bashio::services mqtt 'port')"
    export MQTT_USERNAME="$(bashio::services mqtt 'username')"
    export MQTT_PASSWORD="$(bashio::services mqtt 'password')"
    bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT}"
else
    bashio::log.warning "Kein MQTT-Dienst gefunden – Sensoren für Home Assistant werden nicht veröffentlicht."
fi

cd /app
exec python3 /app/main.py
