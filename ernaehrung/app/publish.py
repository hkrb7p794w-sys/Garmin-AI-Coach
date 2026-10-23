"""Home-Assistant-Sensoren per MQTT Discovery (Schnittstelle für Phase 2).

Sensoren (Gerät "Ernährung"):
- sensor.ernaehrung_<naehrstoff>   Tageswert je Nährstoff, Attribute: Ziel, Prozent
- sensor.ernaehrung_tag            Zustand: kcal-Fortschritt in %, Attribute: komplette
                                   Tagesauswertung (Summen, Ziele, Tagestyp, Mahlzeiten)
- sensor.ernaehrung_woche          Zustand: Anzahl wiederkehrender Lücken, Attribute:
                                   7-Tage-Auswertung (Schnitt, Trefferquote, Lücken,
                                   Kohlenhydrate an harten Tagen, Protein an Trainingstagen)
Veröffentlicht nach jeder Änderung und alle 10 Minuten (Datumswechsel, neue Garmin-Daten).
"""
import json
import os
import threading

import nutrients as N

try:
    import paho.mqtt.client as mqtt
except ImportError:  # Tests ohne paho
    mqtt = None

HOST = os.environ.get("MQTT_HOST", "core-mosquitto")
PORT = int(os.environ.get("MQTT_PORT", 1883))
USER = os.environ.get("MQTT_USERNAME")
PASS = os.environ.get("MQTT_PASSWORD")
PREFIX = "ernaehrung"
DEVICE = {"identifiers": ["ernaehrung_app"], "name": "Ernährung", "manufacturer": "Eigenes Add-on",
          "model": "Ernährungs-Tracking"}

SLUGS = {
    "kcal": "kalorien", "protein_g": "protein", "carbs_g": "kohlenhydrate", "sugar_g": "zucker",
    "fat_g": "fett", "satfat_g": "gesaettigte_fettsaeuren", "fiber_g": "ballaststoffe",
    "water_ml": "fluessigkeit", "sodium_mg": "natrium", "potassium_mg": "kalium",
    "magnesium_mg": "magnesium", "calcium_mg": "calcium", "iron_mg": "eisen", "zinc_mg": "zink",
    "vitd_ug": "vitamin_d", "b12_ug": "vitamin_b12", "vitc_mg": "vitamin_c",
    "iodine_ug": "jod", "omega3_mg": "omega_3",
}
SENSOR_NAMES = {"sugar_g": "Zucker", "satfat_g": "Gesättigte Fettsäuren"}
ICONS = {"kcal": "mdi:fire", "protein_g": "mdi:egg-outline", "carbs_g": "mdi:bread-slice",
         "fat_g": "mdi:water-opacity", "fiber_g": "mdi:leaf", "water_ml": "mdi:cup-water",
         "sugar_g": "mdi:cube-outline"}

_client = None
_lock = threading.Lock()
_connected = threading.Event()


def _connect():
    global _client
    if mqtt is None or not USER:
        return None
    if _client is not None:
        return _client
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ernaehrung_app")
    c.username_pw_set(USER, PASS)
    c.on_connect = lambda cl, ud, fl, rc, props=None: (_connected.set(), print(f"[mqtt] verbunden ({rc})"))
    c.on_disconnect = lambda *a, **k: _connected.clear()
    c.connect_async(HOST, PORT, keepalive=60)
    c.loop_start()
    _client = c
    _connected.wait(10)
    return c


def discovery():
    c = _connect()
    if not c:
        return False
    for key, slug in SLUGS.items():
        name, unit, _grp = N.NUTRIENTS[key]
        cfg = {
            "name": SENSOR_NAMES.get(key, name), "unique_id": f"{PREFIX}_{slug}",
            # HA >= 2025.10: default_entity_id (ersetzt object_id) -> sensor.ernaehrung_<slug>
            "default_entity_id": f"sensor.{PREFIX}_{slug}",
            "state_topic": f"{PREFIX}/{slug}/state", "json_attributes_topic": f"{PREFIX}/{slug}/attr",
            "unit_of_measurement": unit, "state_class": "measurement",
            "icon": ICONS.get(key, "mdi:nutrition"), "device": DEVICE,
        }
        c.publish(f"homeassistant/sensor/{PREFIX}_{slug}/config", json.dumps(cfg), retain=True)
    for slug, name, icon, unit in (("tag", "Heute", "mdi:food-apple", "%"),
                                   ("woche", "Woche", "mdi:calendar-week", None)):
        cfg = {"name": name, "unique_id": f"{PREFIX}_{slug}", "default_entity_id": f"sensor.{PREFIX}_{slug}",
               "state_topic": f"{PREFIX}/{slug}/state", "json_attributes_topic": f"{PREFIX}/{slug}/attr",
               "icon": icon, "device": DEVICE}
        if unit:
            cfg["unit_of_measurement"] = unit
        c.publish(f"homeassistant/sensor/{PREFIX}_{slug}/config", json.dumps(cfg), retain=True)
    return True


def _day_attrs(d: dict) -> dict:
    return {
        "date": d["date"], "day_type": d["day_type"], "day_label": d["day_label"],
        "day_source": d.get("day_source"), "meals_count": d["meals_count"],
        "totals": d["totals"], "targets": d["targets"], "progress": d["progress"],
        "target_kind": d.get("target_kind"), "training": d.get("training"), "energy": d.get("energy"),
        "incomplete_micros": d.get("incomplete"),
        "protein_meals": d.get("protein_meals"), "protein_meal_min_g": d.get("protein_meal_min_g"),
        "recommendations": [{k: r.get(k) for k in ("id", "type", "icon", "title", "text", "source")}
                            | {"foods": [f"{f['name']}, {f['portion']}" for f in r.get("foods") or []]}
                            for r in d.get("recommendations") or []],
        "meals": [{"category": c, "title": m.get("title"), "time": m.get("time"),
                   "kcal": (m.get("totals") or {}).get("kcal"),
                   "items": [f"{it['name']} {round(it['amount_g'])} g" for it in m["items"]]}
                  for c, cat in d["categories"].items() for m in cat.get("meals", [])],
    }


def publish(day: dict, week: dict) -> bool:
    with _lock:
        c = _connect()
        if not c:
            return False
        for key, slug in SLUGS.items():
            v = day["totals"].get(key) or 0
            c.publish(f"{PREFIX}/{slug}/state", str(round(v, 1)), retain=True)
            c.publish(f"{PREFIX}/{slug}/attr", json.dumps({
                "ziel": day["targets"].get(key), "prozent": day["progress"].get(key),
                "art": (day.get("target_kind") or {}).get(key, "min"), "datum": day["date"]}), retain=True)
        c.publish(f"{PREFIX}/tag/state", str(day["progress"].get("kcal") or 0), retain=True)
        c.publish(f"{PREFIX}/tag/attr", json.dumps(_day_attrs(day), ensure_ascii=False, default=str), retain=True)
        c.publish(f"{PREFIX}/woche/state", str(len(week.get("gaps") or [])), retain=True)
        wk = dict(week)
        wk["recommendations"] = [{k: r.get(k) for k in ("id", "type", "title", "text", "source")}
                                 | {"foods": [f"{f['name']}, {f['portion']}" for f in r.get("foods") or []]}
                                 for r in week.get("recommendations") or []]
        for dd in wk.get("days", []):   # Attribute klein halten (HA-Recorder)
            dd.pop("targets", None)
        c.publish(f"{PREFIX}/woche/attr", json.dumps(wk, ensure_ascii=False, default=str), retain=True)
        return True
