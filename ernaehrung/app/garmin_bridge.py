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


def all_states():
    if not TOKEN:
        return []
    try:
        r = requests.get(f"{API}/states", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
        return r.json() if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        return []


def weight_sensors():
    """Sensoren mit Einheit kg, die nach Körpergewicht aussehen (Waage, Garmin, Fit Coach)."""
    out = []
    for st in all_states():
        eid = st.get("entity_id", "")
        a = st.get("attributes") or {}
        if not eid.startswith("sensor.") or a.get("unit_of_measurement") != "kg":
            continue
        name = f"{eid} {a.get('friendly_name', '')}".lower()
        if any(k in name for k in ("gewicht", "weight", "waage", "scale")):
            try:
                val = float(st.get("state"))
            except (TypeError, ValueError):
                val = None
            out.append({"entity_id": eid, "name": a.get("friendly_name") or eid, "value": val,
                        "updated": st.get("last_updated")})
    return out


def weight_from(entity_id: str):
    st = get_state(entity_id) if entity_id else None
    try:
        v = float((st or {}).get("state"))
    except (TypeError, ValueError):
        return None
    return v if 30 <= v <= 250 else None


def training_today(max_age_s: int = 120, weight_entity: str = None):
    """Energie-/Trainingsdaten von heute oder None."""
    now = datetime.datetime.now()
    if _cache["at"] and _cache.get("we") == weight_entity and (now - _cache["at"]).total_seconds() < max_age_s:
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
        pattrs = plan.get("attributes") or {}
        if pattrs.get("date") == datetime.date.today().isoformat():
            data["plan_items"] = pattrs.get("today_fixed") or []
    w = weight_from(weight_entity)
    if w is not None:
        data = data or {}
        data["weight_kg"], data["weight_kg_source"] = round(w, 1), "Waage"
    _cache.update(at=now, data=data, we=weight_entity)
    return data
