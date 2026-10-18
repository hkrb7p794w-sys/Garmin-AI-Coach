"""MQTT: Entitäten per Discovery anlegen, Zustände senden, Befehle empfangen.

Alle Entitäten gehören zum Gerät „Fit Coach“ und haben feste IDs über
`default_entity_id` (sensor.fit_coach_*, number.fit_coach_*, ...), damit das
Dashboard sie sicher findet. Einstellungen (Ziele, Gewichtseingabe,
Rekord-Eingabe) sind MQTT-Entitäten dieser App selbst - es müssen keine Helfer
in Home Assistant angelegt werden. Ihre Werte liegen in /data/settings.json.
"""
import os
import json
import paho.mqtt.client as mqtt

VERSION = os.environ.get("FIT_VERSION", "0.1.0")
HOST = os.environ.get("MQTT_HOST", "core-mosquitto")
PORT = int(os.environ.get("MQTT_PORT") or 1883)
USER = os.environ.get("MQTT_USERNAME")
PASS = os.environ.get("MQTT_PASSWORD")
BASE = "fit_coach"
AVAIL = f"{BASE}/availability"

DEVICE = {"identifiers": ["fit_coach"], "name": "Fit Coach", "manufacturer": "Eigene App",
          "model": "Garmin + Yazio", "sw_version": VERSION}

# key: (Name, Einheit, Icon, device_class, state_class, mit Attributen?)
SENSORS = {
    "status": ("Status", None, "mdi:account-check-outline", None, None, True),
    "letzter_sync": ("Letzter Sync", None, "mdi:sync", "timestamp", None, False),
    "heute": ("Heute", None, "mdi:calendar-today", None, None, True),
    "schritte": ("Schritte", "Schritte", "mdi:walk", None, "measurement", False),
    "aktiv_kcal": ("Aktivkalorien", "kcal", "mdi:fire", None, "measurement", False),
    "kalorien": ("Kalorien gegessen", "kcal", "mdi:food-apple-outline", None, "measurement", False),
    "kalorien_ziel": ("Kalorienziel", "kcal", "mdi:target", None, None, False),
    "protein": ("Eiweiß", "g", "mdi:egg-outline", None, "measurement", False),
    "gewicht": ("Gewicht", "kg", "mdi:scale-bathroom", "weight", "measurement", False),
    "gewicht_trend": ("Gewicht Trend", "kg", "mdi:chart-bell-curve-cumulative", "weight", "measurement", False),
    "abnahme": ("Abnahme", None, "mdi:trending-down", None, None, True),
    "ernaehrung": ("Ernährung", None, "mdi:silverware-fork-knife", None, None, True),
    "laufen": ("Laufen", None, "mdi:run", None, None, True),
    "lauf_km_woche": ("Laufkilometer Woche", "km", "mdi:map-marker-distance", "distance", "measurement", False),
    "pace_locker": ("Pace locker", "s/km", "mdi:speedometer-slow", None, "measurement", False),
    "prognose_5k": ("Prognose 5 km", "s", "mdi:timer-outline", "duration", "measurement", False),
    "vo2max": ("VO2max", "ml/kg/min", "mdi:lungs", None, "measurement", False),
    "gym": ("Gym", None, "mdi:dumbbell", None, None, True),
    "woche": ("Woche", "%", "mdi:calendar-week", None, "measurement", True),
    "serie": ("Wochenserie", "Wochen", "mdi:fire", None, "measurement", False),
    "erfolge": ("Erfolge", None, "mdi:trophy-outline", None, None, True),
    "tipp": ("Tipp", None, "mdi:lightbulb-on-outline", None, None, True),
    "plan": ("Nächstes Workout", None, "mdi:calendar-clock", None, None, True),
}

# key: (Name, min, max, step, Einheit, Icon)
NUMBERS = {
    "zielgewicht": ("Zielgewicht", 0, 200, 0.1, "kg", "mdi:flag-checkered"),
    "gewicht_eintragen": ("Gewicht eintragen", 0, 250, 0.05, "kg", "mdi:scale-bathroom"),
    "ziel_laeufe": ("Läufe pro Woche", 0, 7, 1, None, "mdi:run"),
    "ziel_gym": ("Gym pro Woche", 0, 7, 1, None, "mdi:dumbbell"),
    "rekord_kg": ("Rekord Gewicht", 0, 300, 0.5, "kg", "mdi:weight-kilogram"),
    "rekord_wdh": ("Rekord Wiederholungen", 1, 50, 1, None, "mdi:counter"),
}
BUTTONS = {
    "sync": ("Jetzt synchronisieren", "mdi:sync"),
    "rekord_speichern": ("Rekord speichern", "mdi:content-save-outline"),
    "rekord_rueckgaengig": ("Letzten Rekord löschen", "mdi:undo"),
    "gewicht_rueckgaengig": ("Gewicht von heute löschen", "mdi:undo"),
}
SELECTS = {"uebung": ("Übung", "mdi:format-list-bulleted")}

_client = None
_handler = None
_select_options = {"uebung": ["Kniebeuge"]}


def _avail():
    return {"availability_topic": AVAIL, "payload_available": "online", "payload_not_available": "offline"}


def discovery():
    c = _client
    if c is None:
        return
    for key, (name, unit, icon, dc, sc, attrs) in SENSORS.items():
        p = {"name": name, "unique_id": f"fit_coach_{key}", "default_entity_id": f"sensor.fit_coach_{key}",
             "state_topic": f"{BASE}/{key}/state", "icon": icon, "device": DEVICE, **_avail()}
        if unit:
            p["unit_of_measurement"] = unit
        if dc:
            p["device_class"] = dc
        if sc:
            p["state_class"] = sc
        if attrs:
            p["json_attributes_topic"] = f"{BASE}/{key}/attributes"
        c.publish(f"homeassistant/sensor/fit_coach_{key}/config", json.dumps(p), retain=True)
    for key, (name, mn, mx, step, unit, icon) in NUMBERS.items():
        p = {"name": name, "unique_id": f"fit_coach_{key}", "default_entity_id": f"number.fit_coach_{key}",
             "command_topic": f"{BASE}/{key}/set", "state_topic": f"{BASE}/{key}/state",
             "min": mn, "max": mx, "step": step, "mode": "box", "icon": icon, "device": DEVICE,
             "entity_category": "config", **_avail()}
        if unit:
            p["unit_of_measurement"] = unit
        c.publish(f"homeassistant/number/fit_coach_{key}/config", json.dumps(p), retain=True)
    for key, (name, icon) in BUTTONS.items():
        p = {"name": name, "unique_id": f"fit_coach_{key}", "default_entity_id": f"button.fit_coach_{key}",
             "command_topic": f"{BASE}/{key}/press", "payload_press": "PRESS", "icon": icon,
             "device": DEVICE, **_avail()}
        c.publish(f"homeassistant/button/fit_coach_{key}/config", json.dumps(p), retain=True)
    for key, (name, icon) in SELECTS.items():
        publish_select(key, _select_options.get(key) or ["–"])


def publish_select(key, options, current=None):
    _select_options[key] = list(options)
    c = _client
    if c is None:
        return
    name, icon = SELECTS[key]
    p = {"name": name, "unique_id": f"fit_coach_{key}", "default_entity_id": f"select.fit_coach_{key}",
         "command_topic": f"{BASE}/{key}/set", "state_topic": f"{BASE}/{key}/state",
         "options": list(options), "icon": icon, "device": DEVICE, "entity_category": "config", **_avail()}
    c.publish(f"homeassistant/select/fit_coach_{key}/config", json.dumps(p), retain=True)
    if current:
        c.publish(f"{BASE}/{key}/state", current, retain=True)


def state(key, value, attributes=None):
    c = _client
    if c is None:
        return
    # "None" setzt einen MQTT-Sensor in HA auf „unbekannt“; ein leerer Text würde
    # ignoriert und der alte Wert bliebe stehen.
    v = "None" if value is None or value == "" else value
    if isinstance(v, float):
        v = round(v, 2)
    c.publish(f"{BASE}/{key}/state", str(v) if not isinstance(v, str) else v, retain=True)
    if attributes is not None:
        payload = json.dumps(attributes, ensure_ascii=False, default=str)
        if len(payload) > 15000:
            print(f"[mqtt] Attribute von {key} sind {len(payload)} Bytes groß (Recorder-Grenze 16 KB)")
        c.publish(f"{BASE}/{key}/attributes", payload, retain=True)


def _on_connect(client, userdata, flags, rc, properties=None):
    failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
    if not failed:
        print("[mqtt] verbunden")
        client.publish(AVAIL, "online", retain=True)
        for key in list(NUMBERS) + list(SELECTS):
            client.subscribe(f"{BASE}/{key}/set")
        for key in BUTTONS:
            client.subscribe(f"{BASE}/{key}/press")
        client.subscribe("homeassistant/status")
        discovery()
        if _handler:
            _handler("_connected", None)
    else:
        print(f"[mqtt] Verbindung fehlgeschlagen rc={rc} (Benutzer gesetzt: {'ja' if USER else 'NEIN'})")


def _on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode("utf-8", errors="replace").strip()
    if topic == "homeassistant/status":
        if payload == "online":  # HA neu gestartet -> Discovery + Zustände erneut senden
            discovery()
            if _handler:
                _handler("_connected", None)
        return
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != BASE:
        return
    key, kind = parts[1], parts[2]
    if _handler:
        try:
            _handler(key, payload if kind == "set" else "PRESS")
        except Exception as e:
            print(f"[mqtt] Befehl {key} fehlgeschlagen: {e}")


def start(handler):
    """handler(key, payload) bekommt Befehle (Zahl/Auswahl/Knopf) und '_connected'."""
    global _client, _handler
    _handler = handler
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fit_coach")
    except AttributeError:  # paho-mqtt < 2
        c = mqtt.Client(client_id="fit_coach")
    if USER:
        c.username_pw_set(USER, PASS)
    c.will_set(AVAIL, "offline", retain=True)
    c.on_connect = _on_connect
    c.on_message = _on_message
    c.reconnect_delay_set(min_delay=1, max_delay=60)
    _client = c
    c.connect_async(HOST, PORT, 60)
    c.loop_start()
    print(f"[mqtt] verbinde mit {HOST}:{PORT} (Benutzer gesetzt: {'ja' if USER else 'NEIN'})")


def stop():
    if _client:
        _client.publish(AVAIL, "offline", retain=True)
        _client.loop_stop()
