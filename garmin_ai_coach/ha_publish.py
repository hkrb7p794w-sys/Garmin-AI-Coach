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
# Diagnose: zeigt beim Start, ob Supervisor die MQTT-Zugangsdaten ueberhaupt
# als Umgebungsvariablen injiziert hat (Passwort wird NICHT geloggt, nur ob
# gesetzt) - hilft bei "not authorised"-Fehlern in core_mosquitto zu klaeren,
# ob es an fehlenden Credentials oder an falschen Credentials liegt.
print(f"[mqtt debug] host={MQTT_HOST} port={MQTT_PORT} "
      f"user_set={'yes (' + MQTT_USER + ')' if MQTT_USER else 'NO - env var MQTT_USERNAME is empty/unset'} "
      f"pass_set={'yes' if MQTT_PASS else 'NO - env var MQTT_PASSWORD is empty/unset'}")
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)
<<<<<<< HEAD
=======
# connect_async + loop_start (statt eines blockierenden connect()) laesst den
# Broker-Verbindungsaufbau im Hintergrund-Thread laufen und automatisch neu
# versuchen, falls core-mosquitto beim Add-on-Start noch nicht bereit ist.
client.reconnect_delay_set(min_delay=1, max_delay=60)
client.connect_async(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e


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
<<<<<<< HEAD
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

=======
    # bereits vorhanden (v0.3.0)
    "resting_hr": {"name": "Garmin Resting HR", "unit": "bpm", "icon": "mdi:heart-pulse"},
    "steps_today": {"name": "Garmin Steps Today", "unit": "steps", "icon": "mdi:walk"},
    "coaching_note": {"name": "Garmin AI Coaching Note", "unit": None, "icon": "mdi:robot"},
    "training_readiness": {
        "name": "Garmin Training Readiness",
        "unit": "%",
        "icon": "mdi:lightning-bolt",
        "state_class": "measurement",
    },
    "last_sync": {
        "name": "Garmin Last Sync",
        "unit": None,
        "icon": "mdi:sync",
        "device_class": "timestamp",
    },
    "sync_status": {
        "name": "Garmin Sync Status",
        "unit": None,
        "icon": "mdi:check-network-outline",
    },

    # neu: Erholung / Belastung
    "hrv": {
        "name": "Garmin HRV (letzte Nacht)",
        "unit": "ms",
        "icon": "mdi:heart-flash",
        "state_class": "measurement",
    },
    "body_battery": {
        "name": "Garmin Body Battery",
        "unit": "%",
        "icon": "mdi:battery-heart-variant",
        "state_class": "measurement",
    },
    "stress": {
        "name": "Garmin Stress Level",
        "unit": None,
        "icon": "mdi:head-flash",
        "state_class": "measurement",
    },
    "respiration": {
        "name": "Garmin Atemfrequenz",
        "unit": "brpm",
        "icon": "mdi:lungs",
        "state_class": "measurement",
    },
    "spo2": {
        "name": "Garmin SpO2",
        "unit": "%",
        "icon": "mdi:water-percent",
        "state_class": "measurement",
    },
    "sleep_score": {
        "name": "Garmin Sleep Score",
        "unit": None,
        "icon": "mdi:sleep",
        "state_class": "measurement",
    },
    "sleep_hours": {
        "name": "Garmin Schlafdauer",
        "unit": "h",
        "icon": "mdi:bed-clock",
        "state_class": "measurement",
    },
    "training_status": {
        "name": "Garmin Training Status",
        "unit": None,
        "icon": "mdi:trending-up",
    },

    # neu: Fitness-Fortschritt fuer die Ironman-70.3-Vorbereitung
    "vo2max": {
        "name": "Garmin VO2max",
        "unit": "ml/kg/min",
        "icon": "mdi:lungs",
        "state_class": "measurement",
    },
    "endurance_score": {
        "name": "Garmin Endurance Score",
        "unit": None,
        "icon": "mdi:medal",
        "state_class": "measurement",
    },
}

# Sensoren, die zusaetzlich zum reinen state noch strukturierte Attribute
# (json_attributes_topic) mitliefern.
ATTRIBUTE_SENSORS = {"coaching_note", "training_readiness", "training_status"}

>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e

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
<<<<<<< HEAD
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if state_class:
            payload["state_class"] = state_class
        if key == "coaching_note":
=======
        if cfg.get("unit"):
            payload["unit_of_measurement"] = cfg["unit"]
        if cfg.get("device_class"):
            payload["device_class"] = cfg["device_class"]
        if cfg.get("state_class"):
            payload["state_class"] = cfg["state_class"]
        if key in ATTRIBUTE_SENSORS:
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e
            payload["json_attributes_topic"] = f"garmin_ai_coach/{key}/attributes"
        client.publish(topic, json.dumps(payload), retain=True)


<<<<<<< HEAD
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


=======
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e
def extract_metrics(data: dict) -> dict:
    m = {}

    # Ruhepuls
    try:
        entries = data["resting_hr"]["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
        m["resting_hr"] = entries[-1]["value"] if entries else None
    except (KeyError, IndexError, TypeError):
<<<<<<< HEAD
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
=======
        pass

    steps_today = sum(s.get("steps", 0) for s in data.get("steps", []))

    # get_training_readiness() liefert typischerweise eine Liste mit einem
    # Eintrag fuer den Tag; defensiv behandeln, falls Garmin das Format aendert
    # oder fuer den Tag (noch) nichts liefert.
    readiness_score = None
    readiness_level = None
    try:
        readiness = data.get("training_readiness") or []
        if readiness:
            readiness_score = readiness[0].get("score")
            readiness_level = readiness[0].get("level")
    except (AttributeError, IndexError, TypeError):
        pass

    # HRV: get_hrv_data() -> {"hrvSummary": {"lastNightAvg": ..., "status": ...}}
    hrv_avg = None
    hrv_status = None
    try:
        summary = (data.get("hrv") or {}).get("hrvSummary") or {}
        hrv_avg = summary.get("lastNightAvg")
        hrv_status = summary.get("status")
    except AttributeError:
        pass

    # Body Battery: get_body_battery(start, end) -> Liste pro Tag, jeweils mit
    # "bodyBatteryValuesArray": [[timestamp, value, ...], ...]. Wir nehmen den
    # letzten Wert des letzten Tages als aktuellen Stand.
    body_battery = None
    try:
        bb_days = data.get("body_battery") or []
        if bb_days:
            values = bb_days[-1].get("bodyBatteryValuesArray") or []
            if values:
                body_battery = values[-1][1]
    except (IndexError, TypeError, AttributeError):
        pass

    # Stress: get_all_day_stress() -> {"avgStressLevel": ...}
    stress_avg = None
    try:
        stress_avg = (data.get("stress") or {}).get("avgStressLevel")
        if stress_avg is not None and stress_avg < 0:
            # Garmin nutzt -1/-2 fuer "kein Wert"/"nicht genug Daten"
            stress_avg = None
    except AttributeError:
        pass

    # Atemfrequenz: get_respiration_data() -> {"avgWakingRespirationValue": ...}
    respiration_avg = None
    try:
        respiration_avg = (data.get("respiration") or {}).get("avgWakingRespirationValue")
    except AttributeError:
        pass

    # SpO2: get_spo2_data() -> {"averageSpO2": ...}
    spo2_avg = None
    try:
        spo2_avg = (data.get("spo2") or {}).get("averageSpO2")
    except AttributeError:
        pass

    # Schlaf: get_sleep_data() -> {"dailySleepDTO": {"sleepTimeSeconds": ...,
    #   "sleepScores": {"overall": {"value": ...}}}}
    sleep_score = None
    sleep_hours = None
    try:
        dto = (data.get("sleep") or {}).get("dailySleepDTO") or {}
        sleep_score = ((dto.get("sleepScores") or {}).get("overall") or {}).get("value")
        seconds = dto.get("sleepTimeSeconds")
        if seconds:
            sleep_hours = round(seconds / 3600, 1)
    except AttributeError:
        pass

    # Training Status: get_training_status() -> verschachtelt unter einem
    # dynamischen Geraete-Key, den wir nicht im Voraus kennen -> ersten Eintrag
    # nehmen, egal welche Geraete-ID Garmin verwendet.
    training_status_phrase = None
    try:
        latest = (
            (data.get("training_status") or {})
            .get("mostRecentTrainingStatus", {})
            .get("latestTrainingStatusData", {})
        )
        if latest:
            first_device = next(iter(latest.values()))
            training_status_phrase = first_device.get("trainingStatusFeedbackPhrase")
    except (AttributeError, StopIteration):
        pass

    # VO2max: get_max_metrics() -> Liste, i.d.R. ein Eintrag mit
    # "generic": {"vo2MaxPreciseValue": ...} (Fallback: "vo2MaxValue")
    vo2max = None
    try:
        metrics_list = data.get("max_metrics") or []
        if metrics_list:
            generic = metrics_list[0].get("generic") or {}
            vo2max = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
    except (AttributeError, IndexError):
        pass

    # Endurance Score: get_endurance_score() -> {"overallScore": ...}
    # (wird in app.py nur montags abgerufen, daher an den meisten Tagen None)
    endurance_score = None
    try:
        endurance_score = (data.get("endurance_score") or {}).get("overallScore")
    except AttributeError:
        pass

    return {
        "resting_hr": resting_hr,
        "steps_today": steps_today,
        "training_readiness_score": readiness_score,
        "training_readiness_level": readiness_level,
        "hrv_avg": hrv_avg,
        "hrv_status": hrv_status,
        "body_battery": body_battery,
        "stress_avg": stress_avg,
        "respiration_avg": respiration_avg,
        "spo2_avg": spo2_avg,
        "sleep_score": sleep_score,
        "sleep_hours": sleep_hours,
        "training_status_phrase": training_status_phrase,
        "vo2max": vo2max,
        "endurance_score": endurance_score,
    }
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e


def publish_state(data: dict, coaching_note: str = None):
    metrics = extract_metrics(data)
<<<<<<< HEAD
    for key, value in metrics.items():
        if value is None:
            continue
        client.publish(f"garmin_ai_coach/{key}/state", value, retain=True)
=======

    if metrics["resting_hr"] is not None:
        client.publish("garmin_ai_coach/resting_hr/state", metrics["resting_hr"], retain=True)
    client.publish("garmin_ai_coach/steps_today/state", metrics["steps_today"], retain=True)

    if metrics["training_readiness_score"] is not None:
        client.publish("garmin_ai_coach/training_readiness/state",
                        metrics["training_readiness_score"], retain=True)
        client.publish("garmin_ai_coach/training_readiness/attributes",
                        json.dumps({"level": metrics["training_readiness_level"]}),
                        retain=True)

    if metrics["hrv_avg"] is not None:
        client.publish("garmin_ai_coach/hrv/state", metrics["hrv_avg"], retain=True)

    if metrics["body_battery"] is not None:
        client.publish("garmin_ai_coach/body_battery/state", metrics["body_battery"], retain=True)

    if metrics["stress_avg"] is not None:
        client.publish("garmin_ai_coach/stress/state", metrics["stress_avg"], retain=True)

    if metrics["respiration_avg"] is not None:
        client.publish("garmin_ai_coach/respiration/state", metrics["respiration_avg"], retain=True)

    if metrics["spo2_avg"] is not None:
        client.publish("garmin_ai_coach/spo2/state", metrics["spo2_avg"], retain=True)

    if metrics["sleep_score"] is not None:
        client.publish("garmin_ai_coach/sleep_score/state", metrics["sleep_score"], retain=True)

    if metrics["sleep_hours"] is not None:
        client.publish("garmin_ai_coach/sleep_hours/state", metrics["sleep_hours"], retain=True)

    if metrics["training_status_phrase"] is not None:
        client.publish("garmin_ai_coach/training_status/state",
                        metrics["training_status_phrase"], retain=True)
        client.publish("garmin_ai_coach/training_status/attributes",
                        json.dumps({"raw": metrics["training_status_phrase"]}), retain=True)

    if metrics["vo2max"] is not None:
        client.publish("garmin_ai_coach/vo2max/state", metrics["vo2max"], retain=True)

    if metrics["endurance_score"] is not None:
        client.publish("garmin_ai_coach/endurance_score/state", metrics["endurance_score"], retain=True)
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e

    if coaching_note:
        short = coaching_note[:250] + ("…" if len(coaching_note) > 250 else "")
        client.publish("garmin_ai_coach/coaching_note/state", short, retain=True)
<<<<<<< HEAD
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
=======
        client.publish("garmin_ai_coach/coaching_note/attributes",
                        json.dumps({"full_text": coaching_note}), retain=True)

    client.publish(
        "garmin_ai_coach/last_sync/state",
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        retain=True,
    )


def publish_sync_status(ok: bool, detail: str = ""):
    """Eigener Status-Sensor, damit ein fehlgeschlagener Sync in Home Assistant
    sichtbar wird, statt nur still im Add-on-Log zu verschwinden (genau das
    Problem, das den bisherigen Stillstand verschleiert hat)."""
    client.publish("garmin_ai_coach/sync_status/state", "ok" if ok else "error", retain=True)
    if detail:
        print(f"[sync_status] {'ok' if ok else 'error'}: {detail}")
>>>>>>> e6144c40b4d98bf6dd43f9d6ab4e0d30872d235e
