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
# connect_async + loop_start (statt eines blockierenden connect()) laesst den
# Broker-Verbindungsaufbau im Hintergrund-Thread laufen und automatisch neu
# versuchen, falls core-mosquitto beim Add-on-Start noch nicht bereit ist.
client.reconnect_delay_set(min_delay=1, max_delay=60)
client.connect_async(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

SENSORS = {
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

    # Erholung / Belastung
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

    # Fitness-Fortschritt fuer die Ironman-70.3-Vorbereitung
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

    # Rennvorbereitung / Periodisierung (Ironman 70.3, 29.08.2027)
    "weekly_swim_km": {
        "name": "Garmin Wochenvolumen Schwimmen",
        "unit": "km",
        "icon": "mdi:swim",
        "state_class": "measurement",
    },
    "weekly_bike_km": {
        "name": "Garmin Wochenvolumen Rad",
        "unit": "km",
        "icon": "mdi:bike",
        "state_class": "measurement",
    },
    "weekly_run_km": {
        "name": "Garmin Wochenvolumen Lauf",
        "unit": "km",
        "icon": "mdi:run",
        "state_class": "measurement",
    },
    "days_to_race": {
        "name": "Garmin Tage bis Ironman 70.3",
        "unit": "d",
        "icon": "mdi:trophy-outline",
        "state_class": "measurement",
    },
    "training_phase": {
        "name": "Garmin Trainingsphase",
        "unit": None,
        "icon": "mdi:calendar-clock",
    },
    "weekly_report": {
        "name": "Garmin Wochenreport",
        "unit": None,
        "icon": "mdi:calendar-check",
    },
    "strength_exercises": {
        "name": "Garmin Krafttraining Uebungen",
        "unit": None,
        "icon": "mdi:dumbbell",
    },
}

# Sensoren, die zusaetzlich zum reinen state noch strukturierte Attribute
# (json_attributes_topic) mitliefern.
ATTRIBUTE_SENSORS = {
    "coaching_note", "training_readiness", "training_status", "weekly_report",
    "strength_exercises",
}


def publish_discovery():
    for key, cfg in SENSORS.items():
        topic = f"homeassistant/sensor/garmin_ai_coach_{key}/config"
        payload = {
            "name": cfg["name"],
            "unique_id": f"garmin_ai_coach_{key}",
            "state_topic": f"garmin_ai_coach/{key}/state",
            "icon": cfg["icon"],
            "device": DEVICE,
        }
        if cfg.get("unit"):
            payload["unit_of_measurement"] = cfg["unit"]
        if cfg.get("device_class"):
            payload["device_class"] = cfg["device_class"]
        if cfg.get("state_class"):
            payload["state_class"] = cfg["state_class"]
        if key in ATTRIBUTE_SENSORS:
            payload["json_attributes_topic"] = f"garmin_ai_coach/{key}/attributes"
        client.publish(topic, json.dumps(payload), retain=True)


def extract_metrics(data: dict) -> dict:
    resting_hr = None
    try:
        entries = data["resting_hr"]["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
        if entries:
            resting_hr = entries[-1]["value"]
    except (KeyError, IndexError, TypeError):
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

    # VO2max: Liste von Tageseintraegen mit "generic": {"vo2MaxPreciseValue": ...}.
    # Garmin berechnet VO2max nur nach qualifizierenden Einheiten, viele Tage sind
    # daher leer - deshalb den JUENGSTEN Eintrag mit Wert nehmen statt einfach [0]
    # (das war der Grund, warum der Sensor dauerhaft "unbekannt" blieb).
    vo2max = None
    try:
        newest_date = None
        for entry in data.get("max_metrics") or []:
            if not isinstance(entry, dict):
                continue
            generic = entry.get("generic") or {}
            value = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
            if value is None:
                continue
            day = str(entry.get("calendarDate") or generic.get("calendarDate") or "")
            if newest_date is None or day >= newest_date:
                newest_date, vo2max = day, value
    except (AttributeError, IndexError, TypeError):
        pass

    # Endurance Score: die Einzeltag-Abfrage liefert "overallScore", die Zeitraum-
    # Variante stattdessen avg/max/groupMap. Frueher wurde der Zeitraum abgefragt,
    # aber nach "overallScore" gesucht - der Sensor konnte also nie einen Wert
    # bekommen. Jetzt werden beide Antwortformen unterstuetzt.
    endurance_score = None
    try:
        es = data.get("endurance_score") or {}
        endurance_score = es.get("overallScore")
        if endurance_score is None:
            endurance_score = (es.get("enduranceScoreDTO") or {}).get("overallScore")
        if endurance_score is None:
            endurance_score = es.get("avg") or es.get("max")
    except AttributeError:
        pass

    # Wochenvolumen je Disziplin (bereits in app.py vorberechnet) + Rennvorbereitung
    wv = data.get("weekly_volumes") or {}

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
        "weekly_swim_km": wv.get("swim_km"),
        "weekly_bike_km": wv.get("bike_km"),
        "weekly_run_km": wv.get("run_km"),
        "days_to_race": data.get("days_to_race"),
        "training_phase": data.get("phase"),
    }


def publish_state(data: dict, coaching_note: str = None):
    metrics = extract_metrics(data)

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

    if metrics["weekly_swim_km"] is not None:
        client.publish("garmin_ai_coach/weekly_swim_km/state", metrics["weekly_swim_km"], retain=True)
    if metrics["weekly_bike_km"] is not None:
        client.publish("garmin_ai_coach/weekly_bike_km/state", metrics["weekly_bike_km"], retain=True)
    if metrics["weekly_run_km"] is not None:
        client.publish("garmin_ai_coach/weekly_run_km/state", metrics["weekly_run_km"], retain=True)

    if metrics["days_to_race"] is not None:
        client.publish("garmin_ai_coach/days_to_race/state", metrics["days_to_race"], retain=True)
    if metrics["training_phase"] is not None:
        client.publish("garmin_ai_coach/training_phase/state", metrics["training_phase"], retain=True)

    if coaching_note:
        publish_coaching_note(coaching_note)

    client.publish(
        "garmin_ai_coach/last_sync/state",
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        retain=True,
    )


def publish_coaching_note(note: str):
    """Publiziert nur die Coaching-Notiz.

    Bewusst getrennt von publish_state(): die Garmin-Messwerte gehen sofort nach
    dem Abruf raus und haengen nicht mehr an der (teils >30s dauernden oder ganz
    fehlschlagenden) KI-Anfrage."""
    if not note:
        return
    short = note[:250] + ("…" if len(note) > 250 else "")
    client.publish("garmin_ai_coach/coaching_note/state", short, retain=True)
    client.publish("garmin_ai_coach/coaching_note/attributes",
                   json.dumps({"full_text": note}), retain=True)


def publish_weekly_report(text: str, summary: dict = None):
    """Publiziert den Wochenreport plus die zugehoerigen Kennzahlen als Attribute.

    Die Kennzahlen wandern bewusst in die Attribute statt in je einen eigenen Sensor:
    sie werden nur woechentlich aktualisiert und gehoeren inhaltlich zusammen, das
    haelt die Entity-Liste in Home Assistant uebersichtlich."""
    if not text:
        return
    short = text[:250] + ("…" if len(text) > 250 else "")
    client.publish("garmin_ai_coach/weekly_report/state", short, retain=True)
    attributes = {"full_text": text}
    for key, value in (summary or {}).items():
        if isinstance(value, (int, float, str)) or value is None:
            attributes[key] = value
    client.publish("garmin_ai_coach/weekly_report/attributes",
                   json.dumps(attributes, ensure_ascii=False), retain=True)


def publish_strength_exercises(sessions: list):
    """Publiziert die je Kraft-Einheit dieser Woche per FIT-Datei erkannten
    Uebungen/Saetze (siehe fit_exercises.py) als Attribute - strukturierte
    Liste, deshalb Attribute statt eigener Sensor je Uebung. Best-Effort:
    ohne verwertbare Uebungsdetails (z.B. Auto-Satzerkennung der Uhr war aus)
    bleibt der state ehrlich statt eine leere Liste zu verschweigen."""
    sessions = sessions or []
    total_exercises = sum(len(s.get("exercises") or []) for s in sessions)
    if not sessions:
        state = "keine Kraft-Einheiten diese Woche"
    elif total_exercises == 0:
        state = f"{len(sessions)} Einheit(en), keine Uebungsdetails erkannt"
    else:
        state = f"{len(sessions)} Einheit(en), {total_exercises} Uebungen erkannt"
    client.publish("garmin_ai_coach/strength_exercises/state", state[:250], retain=True)
    client.publish(
        "garmin_ai_coach/strength_exercises/attributes",
        json.dumps({"sessions": sessions}, ensure_ascii=False, default=str),
        retain=True,
    )


def publish_sync_status(ok: bool, detail: str = ""):
    """Eigener Status-Sensor, damit ein fehlgeschlagener Sync in Home Assistant
    sichtbar wird, statt nur still im Add-on-Log zu verschwinden (genau das
    Problem, das den bisherigen Stillstand verschleiert hat)."""
    client.publish("garmin_ai_coach/sync_status/state", "ok" if ok else "error", retain=True)
    if detail:
        print(f"[sync_status] {'ok' if ok else 'error'}: {detail}")
