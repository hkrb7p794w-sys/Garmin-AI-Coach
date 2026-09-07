import os, json, datetime, threading, time
from flask import Flask, request, redirect
from ha_publish import publish_discovery, publish_state, publish_sync_meta
from ai_coach import generate_coaching_note

DATA_DIR = "/data"
TOKEN_DIR = os.path.join(DATA_DIR, "garmin_tokens")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
STATE_FILE = os.path.join(DATA_DIR, "sync_state.json")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TOKEN_DIR, exist_ok=True)
os.environ["GARMINTOKENS"] = TOKEN_DIR

MIN_SYNC_INTERVAL_SECONDS = 15 * 60  # Schutz vor erneuter Garmin-Kontosperre (jeder Sync loggt sich neu ein)
RACE_DATE = os.environ.get("RACE_DATE", "2027-08-29")
try:
    SYNC_HOUR = int(os.environ.get("SYNC_HOUR", "6"))
except ValueError:
    SYNC_HOUR = 6

# Periodisierung Ironman 70.3 (siehe claude/status-und-plan.md im Projekt) – grobe Monats-Phasen.
PHASES = [
    (datetime.date(2026, 9, 1), datetime.date(2026, 12, 31), "Grundlagenausdauer"),
    (datetime.date(2027, 1, 1), datetime.date(2027, 3, 31), "Aufbau 1"),
    (datetime.date(2027, 4, 1), datetime.date(2027, 6, 30), "Aufbau 2 (spezifisch)"),
    (datetime.date(2027, 7, 1), datetime.date(2027, 7, 31), "Peak"),
    (datetime.date(2027, 8, 1), datetime.date(2027, 12, 31), "Taper/Rennwoche"),
]

app = Flask(__name__)
_sync_lock = threading.Lock()


def is_logged_in():
    return len(os.listdir(TOKEN_DIR)) > 0


def get_client():
    from garminconnect import Garmin
    client = Garmin()
    client.login(TOKEN_DIR)
    return client


def current_phase(today: datetime.date) -> str:
    for start, end, name in PHASES:
        if start <= today <= end:
            return name
    return "Grundlagenausdauer"


def days_to_race(today: datetime.date) -> int:
    try:
        race = datetime.date.fromisoformat(RACE_DATE)
    except ValueError:
        race = datetime.date(2027, 8, 29)
    return (race - today).days


def _safe(fn, *a, **kw):
    """Ruft eine Garmin-API-Methode auf; loggt Fehler und gibt None zurück, statt den ganzen
    Sync abzubrechen (z.B. wenn HRV/Body-Battery von der aktuellen Uhr nicht unterstützt wird)."""
    name = getattr(fn, "__name__", str(fn))
    try:
        return fn(*a, **kw)
    except Exception as e:
        print(f"[garmin-ai-coach] Warnung: {name} fehlgeschlagen: {e}")
        return None


def _weekly_volumes(activities):
    """Fasst Aktivitäten der letzten 7 Tage zu Wochenvolumen je Disziplin zusammen (km/Minuten)."""
    totals = {"swim_km": 0.0, "bike_km": 0.0, "run_km": 0.0,
              "swim_min": 0.0, "bike_min": 0.0, "run_min": 0.0}
    if not activities:
        return totals
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    for act in activities:
        try:
            start_str = act.get("startTimeLocal")
            if start_str:
                start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                if start_dt < cutoff:
                    continue
            type_key = (act.get("activityType") or {}).get("typeKey", "") or ""
            distance_km = (act.get("distance") or 0) / 1000.0
            duration_min = (act.get("duration") or 0) / 60.0
            if "swim" in type_key:
                totals["swim_km"] += distance_km
                totals["swim_min"] += duration_min
            elif "bik" in type_key or "cycl" in type_key or "ride" in type_key:
                totals["bike_km"] += distance_km
                totals["bike_min"] += duration_min
            elif "run" in type_key:
                totals["run_km"] += distance_km
                totals["run_min"] += duration_min
        except Exception as e:
            print(f"[garmin-ai-coach] Warnung: Aktivität konnte nicht ausgewertet werden: {e}")
    return {k: round(v, 1) for k, v in totals.items()}


def do_sync():
    client = get_client()
    today = datetime.date.today()
    today_iso = today.isoformat()

    recent_activities = _safe(client.get_activities, 0, 50) or []

    wellness = {
        "date": today_iso,
        "resting_hr": _safe(client.get_rhr_day, today_iso),
        "steps": _safe(client.get_steps_data, today_iso),
        "training_readiness": _safe(client.get_training_readiness, today_iso),
        "training_status": _safe(client.get_training_status, today_iso),
        "hrv": _safe(client.get_hrv_data, today_iso),
        "body_battery": _safe(client.get_body_battery, today_iso, today_iso),
        "sleep": _safe(client.get_sleep_data, today_iso),
        "max_metrics": _safe(client.get_max_metrics, today_iso),
        "weekly_volumes": _weekly_volumes(recent_activities),
        "days_to_race": days_to_race(today),
        "phase": current_phase(today),
    }

    with open(DATA_FILE, "w") as f:
        json.dump(wellness, f, indent=2, ensure_ascii=False, default=str)

    publish_discovery()

    try:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("Kein Anthropic API Key in der Add-on-Konfiguration hinterlegt")
        note = generate_coaching_note(wellness)
    except Exception as e:
        print(f"[garmin-ai-coach] Coaching-Notiz fehlgeschlagen: {e}")
        note = "Coaching-Tipp aktuell nicht verfügbar (Details im Add-on-Log)."

    publish_state(wellness, coaching_note=note)
    return wellness


def _read_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _write_state(ts, status):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_sync_ts": ts, "status": status}, f)


def _run_sync_and_record():
    """Führt do_sync() aus und schreibt in jedem Fall last_sync/sync_status (auch bei Fehlern),
    damit im Dashboard sichtbar ist, wenn ein Sync fehlgeschlagen ist, statt nur zu 'verschwinden'."""
    ts = time.time()
    try:
        do_sync()
        _write_state(ts, "ok")
        publish_sync_meta(ts, "ok")
    except Exception as e:
        status = f"error: {type(e).__name__}"
        print(f"[garmin-ai-coach] Sync fehlgeschlagen: {e}")
        _write_state(ts, status)
        try:
            publish_sync_meta(ts, status)
        except Exception as mqtt_err:
            print(f"[garmin-ai-coach] Konnte sync_status nicht publizieren: {mqtt_err}")


LOGIN_FORM = """
<html><body style="font-family:sans-serif;padding:2rem;">
<h1>Garmin AI Coach – Login</h1>
<p>Deine Zugangsdaten werden nur einmalig verwendet, um ein Login-Token zu erzeugen.
Passwort wird nirgends gespeichert.</p>
<form method="post" action="login">
  E-Mail: <input type="email" name="email" required><br><br>
  Passwort: <input type="password" name="password" required><br><br>
  <button type="submit">Einloggen</button>
</form>
</body></html>
"""


@app.route("/")
def home():
    if not is_logged_in():
        return LOGIN_FORM
    latest = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            latest = json.load(f)
    state = _read_state()
    last_ts = state.get("last_sync_ts")
    last_str = (datetime.datetime.fromtimestamp(last_ts).strftime("%d.%m.%Y %H:%M")
                if last_ts else "noch nie")
    return f"""
    <html><body style="font-family:sans-serif;padding:2rem;">
    <h1>Garmin AI Coach</h1>
    <p>Verbunden mit Garmin ✅ &nbsp;|&nbsp; Letzter Sync: {last_str} ({state.get('status', '-')})</p>
    <p><a href="sync">Jetzt synchronisieren</a> &nbsp;|&nbsp; <a href="sync?force=1">Sync erzwingen</a></p>
    <pre>{json.dumps(latest, indent=2, ensure_ascii=False)}</pre>
    </body></html>
    """


@app.route("/login", methods=["POST"])
def login():
    from garminconnect import Garmin
    email = request.form["email"]
    password = request.form["password"]
    try:
        client = Garmin(email, password)
        client.login()
        return redirect(".")
    except Exception as e:
        return f"<p>Login fehlgeschlagen: {e}</p><a href='.'>Zurück</a>"


@app.route("/sync")
def sync():
    if not is_logged_in():
        return redirect(".")
    force = request.args.get("force") == "1"
    state = _read_state()
    last_ts = state.get("last_sync_ts")
    now_ts = time.time()
    if not force and last_ts and (now_ts - last_ts) < MIN_SYNC_INTERVAL_SECONDS:
        wait_min = int((MIN_SYNC_INTERVAL_SECONDS - (now_ts - last_ts)) // 60) + 1
        return (f"<p>Letzter Sync ist erst {int((now_ts - last_ts) // 60)} Min. her. "
                f"Bitte {wait_min} Min. warten oder <a href='sync?force=1'>Sync erzwingen</a>.</p>"
                f"<a href='.'>Zurück</a>")
    with _sync_lock:
        _run_sync_and_record()
    return redirect(".")


def _scheduler_loop():
    last_auto_date = None
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == SYNC_HOUR and last_auto_date != now.date() and is_logged_in():
                print("[garmin-ai-coach] Automatischer Tages-Sync gestartet.")
                with _sync_lock:
                    _run_sync_and_record()
                last_auto_date = now.date()
        except Exception as e:
            print(f"[garmin-ai-coach] Scheduler-Fehler: {e}")
        time.sleep(60)


if __name__ == "__main__":
    # Discovery immer beim Start publizieren, damit alle Sensoren (inkl. last_sync/sync_status)
    # in HA existieren, auch bevor der erste Sync erfolgreich durchgelaufen ist.
    try:
        publish_discovery()
    except Exception as e:
        print(f"[garmin-ai-coach] MQTT-Discovery beim Start fehlgeschlagen: {e}")
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8099)
