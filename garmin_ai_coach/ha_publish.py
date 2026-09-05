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
# connect_async + loop_start (statt eines blockierenden connect()) laesst den
# Broker-Verbindungsaufbau im Hintergrund-Thread laufen und automatisch neu
# versuchen, falls core-mosquitto beim Add-on-Start noch nicht bereit ist.
client.reconnect_delay_set(min_delay=1, max_delay=60)
client.connect_async(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

SENSORS = {
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
}

# Sensoren, die zusaetzlich zum reinen state noch strukturierte Attribute
# (json_attributes_topic) mitliefern.
ATTRIBUTE_SENSORS = {"coaching_note", "training_readiness"}

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

    return {
        "resting_hr": resting_hr,
        "steps_today": steps_today,
        "training_readiness_score": readiness_score,
        "training_readiness_level": readiness_level,
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

    if coaching_note:
        short = coaching_note[:250] + ("…" if len(coaching_note) > 250 else "")
        client.publish("garmin_ai_coach/coaching_note/state", short, retain=True)
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
