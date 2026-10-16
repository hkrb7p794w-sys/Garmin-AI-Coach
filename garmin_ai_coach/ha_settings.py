"""Einstellungen aus dem Dashboard (seit v0.22.0).

Sync-Zeiten, KI-Datenschutz und der Garmin-Export der Schwimmeinheiten lassen sich
im Dashboard (Seite "Einstellungen") ändern statt in der Add-on-Konfiguration.
Das Add-on liest dafür drei Home-Assistant-Helfer über die Core-API
(homeassistant_api: true in config.yaml, wie schon für die CSS in garmin_swim.py):

    input_text.coach_sync_zeiten          z. B. "6,12,20"
    input_select.coach_ki_datenschutz     "reduziert" | "voll"
    input_boolean.coach_garmin_schwimmexport

Fehlt ein Helfer, ist er leer/ungültig oder die API nicht erreichbar, gilt die
Add-on-Option als Rückfall. Nichts bricht, wenn es die Helfer nicht gibt.
Werte werden 60 s zwischengespeichert, damit der Scheduler (alle 5 min) und die
KI-Prompts die API nicht fluten.
"""
import os
import re
import time

import requests

STATES_URL = "http://supervisor/core/api/states/"
SYNC_ENTITY = "input_text.coach_sync_zeiten"
PRIVACY_ENTITY = "input_select.coach_ki_datenschutz"
SWIM_ENTITY = "input_boolean.coach_garmin_schwimmexport"
CACHE_SECONDS = 60
PRIVACY_MODES = ("reduziert", "voll")

_cache = {}
_last_problem = {}


def _log_once(entity: str, text: str):
    """Fehler je Helfer nur loggen, wenn sie sich ändern - sonst alle 60 s dieselbe Zeile."""
    if _last_problem.get(entity) != text:
        _last_problem[entity] = text
        if text:
            print(f"[settings] {entity}: {text}")


def _state(entity: str):
    """Zustand eines HA-Helfers als String, None wenn nicht vorhanden/lesbar."""
    now = time.monotonic()
    hit = _cache.get(entity)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = None
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            r = requests.get(STATES_URL + entity, headers={"Authorization": f"Bearer {token}"}, timeout=8)
            if r.status_code == 200:
                s = r.json().get("state")
                if s not in (None, "", "unknown", "unavailable"):
                    value = str(s).strip()
                _log_once(entity, "")
            elif r.status_code == 404:
                _log_once(entity, "Helfer fehlt - Add-on-Option gilt")
            else:
                _log_once(entity, f"HTTP {r.status_code} - Add-on-Option gilt")
        except Exception as e:  # Netzwerk/JSON - nie den Sync stören
            _log_once(entity, f"nicht lesbar ({e}) - Add-on-Option gilt")
    _cache[entity] = (now, value)
    return value


def parse_hours(raw: str) -> list:
    """"6, 12,20" -> [6, 12, 20]. Ungültige Einträge fallen weg, leere Liste = nichts Gültiges."""
    hours = []
    for part in re.findall(r"\d+", raw or ""):  # trennt an Komma, Leerzeichen, "Uhr" usw.
        hour = int(part)
        if 0 <= hour <= 23 and hour not in hours:
            hours.append(hour)
    return sorted(hours)


def sync_hours(default: list):
    """(Stunden, Quelle) - Quelle "dashboard" oder "option"."""
    raw = _state(SYNC_ENTITY)
    if raw:
        hours = parse_hours(raw)
        if hours:
            return hours, "dashboard"
        _log_once(SYNC_ENTITY + "#parse", f"'{raw}' enthält keine gültige Stunde - Add-on-Option gilt")
    return list(default), "option"


def privacy_mode(default: str) -> str:
    raw = (_state(PRIVACY_ENTITY) or "").lower()
    if raw in PRIVACY_MODES:
        return raw
    return (default or "reduziert").strip().lower()


def swim_export(default: bool) -> bool:
    raw = _state(SWIM_ENTITY)
    if raw in ("on", "off"):
        return raw == "on"
    return bool(default)


def effective(default_hours: list, default_privacy: str, default_swim: bool) -> dict:
    """Aktuell wirksame Einstellungen - wird im Coach-Status-Sensor veröffentlicht,
    damit das Dashboard anzeigen kann, was tatsächlich gilt."""
    hours, source = sync_hours(default_hours)
    return {
        "sync_hours": hours,
        "sync_source": source,
        "privacy_mode": privacy_mode(default_privacy),
        "swim_export": swim_export(default_swim),
    }
