import os, json, datetime
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USERNAME")
MQTT_PASS = os.environ.get("MQTT_PASSWORD")

DEVICE = {
    "identifiers": ["garmin_ai_coach"],
    "name": "Garmin AI Coach",
    "manufacturer": "Custom Add-on",
    "model": "Garmin Sync",
}

client = mqtt.Client(client_id="garmin_ai_coach")
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)


def _on_connect(c, userdata, flags, rc):
    if rc == 0:
        print("[garmin-ai-coach] MQTT verbunden.")
    else:
        print(f"[garmin-ai-coach] MQTT-Verbindung fehlgeschlagen, rc={rc}")


def _on_disconnect(c, userdata, rc):
    print(f"[garmin-ai-coach] MQTT getrennt (rc={rc}), automatischer Reconnect aktiv.")


client.on_connect = _on_connect
client.on_disconnect = _on_disconnect
client.reconnect_delay_set(min_delay=1, max_delay=30)

try:
    # connect_async + loop_start: blockiert den Start nicht, falls core-mosquitto beim
    # Add-on-Start noch nicht bereit ist – paho versucht im Hintergrund weiter zu verbinden.
    client.connect_async(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    print(f"[garmin-ai-coach] MQTT connect_async fehlgeschlagen: {e}")

# key -> (Anzeigename, Einheit, Icon, device_class, state_class)
SENSORS = {
    "resting_hr": ("Garmin Resting HR", "bpm", "mdi:heart-pulse", None, "measurement"),
    "steps_today": ("Garmin Steps Today", "steps", "mdi:walk", None, "measurement"),
    "coaching_note": ("Garmin AI Coaching Note", None, "mdi:robot", None, None),
    "training_readiness_score": ("Garmin Training Readiness", None, "mdi:battery-heart", None, "measurement"),
    "training_readiness_level": ("Garmin Training Readiness Level", None, "mdi:battery-heart-variant", None, None),
    "training_status": ("Garmin Training Status", None, "mdi:chart-timeline-variant", None, None),
    "hrv_status": ("Garmin HRV Status", None, "mdi:pulse", None, None),
    "hrv_last_night_avg": ("Garmin HRV (letzte Nacht)", "ms", "mdi:pulse", None, "measurement"),
    "body_battery": ("Garmin Body Battery", None, "mdi:battery-charging-70", None, "measurement"),
    "sleep_score": ("Garmin Sleep Score", None, "mdi:sleep", None, "measurement"),
    "vo2max": ("Garmin VO2max", None, "mdi:lungs", None, "measurement"),
    "weekly_swim_km": ("Garmin Wochenvolumen Schwimmen", "km", "mdi:swim", None, "measurement"),
    "weekly_bike_km": ("Garmin Wochenvolumen Rad", "km", "mdi:bike", None, "measurement"),
    "weekly_run_km": ("Garmin Wochenvolumen Lauf", "km", "mdi:run", None, "measurement"),
    "days_to_race": ("Garmin Tage bis Ironman 70.3", "d", "mdi:trophy-outline", None, "measurement"),
    "training_phase": ("Garmin Trainingsphase", None, "mdi:calendar-clock", None, None),
    "last_sync": ("Garmin AI Coach Last Sync", None, "mdi:sync", "timestamp", None),
    "sync_status": ("Garmin AI Coach Sync Status", None, "mdi:sync-alert", None, None),
}


def publish_discovery():
    for key, (name, unit, icon, device_class, state_class) in SENSORS.items():
        topic = f"homeassistant/sensor/garmin_ai_coach_{key}/config"
        payload = {
            "name": name,
            "unique_id": f"garmin_ai_coach_{key}",
            "state_topic": f"garmin_ai_coach/{key}/state",
            "icon": icon,
            "device": DEVICE,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if state_class:
            payload["state_class"] = state_class
        if key == "coaching_note":
            payload["json_attributes_topic"] = f"garmin_ai_coach/{key}/attributes"
        client.publish(topic, json.dumps(payload), retain=True)


def _find_key(obj, *keys, _depth=6):
    """Sucht rekursiv (begrenzte Tiefe) den ersten Wert zu einem der angegebenen Keys in einer
    verschachtelten dict/list-Struktur. Garmins inoffizielle API ist nicht dokumentiert und ändert
    sich gelegentlich – dieser Helper macht die Auswertung robuster gegen leicht abweichende Formen,
    statt bei einem falschen Pfad die ganze Auswertung mit einer Exception abzubrechen."""
    if _depth < 0 or obj is None:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            found = _find_key(v, *keys, _depth=_depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key(item, *keys, _depth=_depth - 1)
            if found is not None:
                return found
    return None


def extract_metrics(data: dict) -> dict:
    m = {}

    # Ruhepuls
    try:
        entries = data["resting_hr"]["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
        m["resting_hr"] = entries[-1]["value"] if entries else None
    except (KeyError, IndexError, TypeError):
        m["resting_hr"] = None

    # Schritte
    try:
        m["steps_today"] = sum(s.get("steps", 0) for s in data.get("steps") or [])
    except (AttributeError, TypeError):
        m["steps_today"] = None

    # Training Readiness (Score + Level werden von Garmin bereits geliefert)
    tr = data.get("training_readiness")
    m["training_readiness_score"] = _find_key(tr, "score")
    m["training_readiness_level"] = _find_key(tr, "level")

    # Training Status (Textform, z.B. PRODUCTIVE/MAINTAINING/OVERREACHING)
    m["training_status"] = _find_key(
        data.get("training_status"), "trainingStatusFeedbackPhrase", "trainingStatus"
    )

    # HRV
    hrv = data.get("hrv")
    m["hrv_status"] = _find_key(hrv, "status", "hrvStatus")
    m["hrv_last_night_avg"] = _find_key(hrv, "lastNightAvg", "weeklyAvg")

    # Body Battery: aktuellster Wert aus der Zeitreihe des Tages (nicht die reine "charged"-Menge),
    # da das den tatsächlichen Body-Battery-Stand jetzt widerspiegelt statt nur des Nacht-Zuwachses.
    bb_series = _find_key(data.get("body_battery"), "bodyBatteryValuesArray")
    if isinstance(bb_series, list) and bb_series:
        last = bb_series[-1]
        m["body_battery"] = last[1] if isinstance(last, (list, tuple)) and len(last) > 1 else None
    else:
        m["body_battery"] = _find_key(data.get("body_battery"), "charged", "level")

    # Schlaf-Score
    try:
        m["sleep_score"] = data["sleep"]["dailySleepDTO"]["sleepScores"]["overall"]["value"]
    except (KeyError, TypeError):
        m["sleep_score"] = _find_key(data.get("sleep"), "overall")

    # VO2max (bestverfügbarer Wert, ohne Unterscheidung Rad/Lauf)
    m["vo2max"] = _find_key(data.get("max_metrics"), "vo2MaxPreciseValue", "vo2MaxValue")

    # Wochenvolumen je Disziplin (bereits in app.py vorberechnet)
    wv = data.get("weekly_volumes") or {}
    m["weekly_swim_km"] = wv.get("swim_km")
    m["weekly_bike_km"] = wv.get("bike_km")
    m["weekly_run_km"] = wv.get("run_km")

    # Rennvorbereitung
    m["days_to_race"] = data.get("days_to_race")
    m["training_phase"] = data.get("phase")

    return m


def publish_state(data: dict, coaching_note: str = None):
    metrics = extract_metrics(data)
    for key, value in metrics.items():
        if value is None:
            continue
        client.publish(f"garmin_ai_coach/{key}/state", value, retain=True)

    if coaching_note:
        short = coaching_note[:250] + ("…" if len(coaching_note) > 250 else "")
        client.publish("garmin_ai_coach/coaching_note/state", short, retain=True)
        client.publish(
            "garmin_ai_coach/coaching_note/attributes",
            json.dumps({"full_text": coaching_note}),
            retain=True,
        )


def publish_sync_meta(ts: float, status: str):
    """Publiziert last_sync/sync_status unabhängig vom Rest des Syncs, damit ein Fehlschlag im
    Dashboard sichtbar ist (statt dass die Sensoren einfach einfrieren)."""
    iso_ts = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
    client.publish("garmin_ai_coach/last_sync/state", iso_ts, retain=True)
    client.publish("garmin_ai_coach/sync_status/state", status, retain=True)
