#!/usr/bin/with-contenv bashio

bashio::log.info "Garmin AI Coach add-on gestartet."

export ANTHROPIC_API_KEY=$(bashio::config 'anthropic_api_key')
export GARMIN_EMAIL=$(bashio::config 'garmin_email')
export SYNC_HOUR=$(bashio::config 'sync_hour')
<<<<<<< HEAD
export RACE_DATE=$(bashio::config 'race_date')
=======
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e

exec python3 /app.py
