import os, json
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
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

SENSORS = {
    "resting_hr": {"name": "Garmin Resting HR", "unit": "bpm", "icon": "mdi:heart-pulse"},
    "steps_today": {"name": "Garmin Steps Today", "unit": "steps", "icon": "mdi:walk"},
    "coaching_note": {"name": "Garmin AI Coaching Note", "unit": None, "icon": "mdi:robot"},
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
        if cfg["unit"]:
            payload["unit_of_measurement"] = cfg["unit"]
        if key == "coaching_note":
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
    return {"resting_hr": resting_hr, "steps_today": steps_today}

def publish_state(data: dict, coaching_note: str = None):
    metrics = extract_metrics(data)
    if metrics["resting_hr"] is not None:
        client.publish("garmin_ai_coach/resting_hr/state", metrics["resting_hr"], retain=True)
    client.publish("garmin_ai_coach/steps_today/state", metrics["steps_today"], retain=True)
    if coaching_note:
        short = coaching_note[:250] + ("…" if len(coaching_note) > 250 else "")
        client.publish("garmin_ai_coach/coaching_note/state", short, retain=True)
        client.publish("garmin_ai_coach/coaching_note/attributes",
                        json.dumps({"full_text": coaching_note}), retain=True)