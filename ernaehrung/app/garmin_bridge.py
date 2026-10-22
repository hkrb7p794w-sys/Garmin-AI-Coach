"""Trainings- und Körperdaten aus Home Assistant lesen (Garmin AI Coach).

Der Garmin AI Coach veröffentlicht ab 0.29.0 den Sensor
`sensor.garmin_ai_coach_garmin_energie_heute` (Zustand: aktive kcal heute) mit
Attributen: date, weight_kg, height_cm, age, sex, bmr_kcal, active_kcal,
total_kcal, activities [{type, name, start, duration_min, kcal, training_load}],
training_minutes, endurance_minutes, training_load.

Gelesen wird über die Home-Assistant-API des Supervisors (homeassistant_api: true).
Ohne den Sensor (oder außerhalb von HA) liefert das Modul None und die App
nutzt die Profilwerte aus den Einstellungen.
"""
import datetime
import os

import requests

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = os.environ.get("HA_API", "http://supervisor/core/api")
ENERGY_ENTITY = os.environ.get("GARMIN_ENERGY_ENTITY", "sensor.garmin_ai_coach_garmin_energie_heute")
PLAN_ENTITY = os.environ.get("GARMIN_PLAN_ENTITY", "sensor.garmin_ai_coach_garmin_plan")

_cache = {"at": None, "data": None}


def get_state(entity_id: str):
    if not TOKEN:
        return None
    try:
        r = requests.get(f"{API}/states/{entity_id}",
                         headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except requests.RequestException:
        return None


def training_today(max_age_s: int = 120):
    """Energie-/Trainingsdaten von heute oder None."""
    now = datetime.datetime.now()
    if _cache["at"] and (now - _cache["at"]).total_seconds() < max_age_s:
        return _cache["data"]
    data = None
    st = get_state(ENERGY_ENTITY)
    if st and st.get("state") not in (None, "unknown", "unavailable"):
        attrs = dict(st.get("attributes") or {})
        attrs["synced_at"] = st.get("last_updated")
        if attrs.get("date") == datetime.date.today().isoformat():
            data = attrs
        else:
            # Nur Körperdaten übernehmen, Training gilt nicht für heute
            data = {k: attrs.get(k) for k in ("weight_kg", "height_cm", "age", "sex")}
            data["stale_date"] = attrs.get("date")
    plan = get_state(PLAN_ENTITY)
    if plan and plan.get("state") not in (None, "unknown", "unavailable"):
        data = data or {}
        data["plan_text"] = plan.get("state")
    _cache.update(at=now, data=data)
    return data
