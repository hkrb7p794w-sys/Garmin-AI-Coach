#!/usr/bin/with-contenv bashio

bashio::log.info "Garmin AI Coach add-on gestartet."

export ANTHROPIC_API_KEY=$(bashio::config 'anthropic_api_key')
export GARMIN_EMAIL=$(bashio::config 'garmin_email')

exec python3 /app.py