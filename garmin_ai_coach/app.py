import os, json, datetime, threading, time
from flask import Flask, request, redirect
from ha_publish import publish_discovery, publish_state, publish_sync_status
from ai_coach import generate_coaching_note

DATA_DIR = "/data"
TOKEN_DIR = os.path.join(DATA_DIR, "garmin_tokens")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TOKEN_DIR, exist_ok=True)
os.environ["GARMINTOKENS"] = TOKEN_DIR

# Stunde (0-23, lokale Zeit des Containers), zu der automatisch synchronisiert wird.
# Wird von run.sh aus der Add-on-Option "sync_hour" befuellt.
SYNC_HOUR = int(os.environ.get("SYNC_HOUR", 6))

app = Flask(__name__)

def is_logged_in():
    return len(os.listdir(TOKEN_DIR)) > 0

def get_client():
    from garminconnect import Garmin
    client = Garmin()
    client.login(TOKEN_DIR)
    return client

# Garmin sperrt Konten zeitweise nach zu vielen Login-Versuchen in kurzer Zeit
# (das war vermutlich die Ursache des vorherigen "Garmin-Sperre"-Ausfalls).
# do_sync() loggt sich bei jedem Aufruf neu ein, daher hier eine Mindestpause
# zwischen zwei Versuchen - auch fuer den manuellen "Jetzt synchronisieren"-Button.
MIN_SYNC_INTERVAL = datetime.timedelta(minutes=15)
_last_sync_attempt = None


def _safe_fetch(label, fn):
    """Ruft eine einzelne Garmin-Metrik ab; loggt Fehler statt den ganzen Sync
    abzubrechen. Jede zusaetzliche Metrik ist ein eigener HTTPS-Call an Garmin,
    daher soll ein einzelner fehlschlagender Endpoint (z.B. weil ein Geraet
    einen Sensor nicht unterstuetzt) nicht den kompletten Sync killen."""
    try:
        return fn()
    except Exception as e:
        print(f"[sync] Metrik '{label}' fehlgeschlagen: {e}")
        return None


def do_sync(force: bool = False):
    """Holt aktuelle Garmin-Daten, speichert sie lokal und published sie
    (inkl. KI-Coaching-Notiz) nach MQTT/Home Assistant.

    Wird sowohl vom manuellen /sync-Aufruf als auch vom taeglichen
    Hintergrund-Scheduler genutzt, damit beide Wege garantiert
    tatsaechlich bei Home Assistant ankommen. `force=True` umgeht die
    Mindestpause (z.B. fuer gezieltes Testen ueber /sync?force=1).
    """
    global _last_sync_attempt
    if not is_logged_in():
        return None

    now = datetime.datetime.now()
    if not force and _last_sync_attempt and now - _last_sync_attempt < MIN_SYNC_INTERVAL:
        print("[sync] uebersprungen: letzter Versuch liegt weniger als "
              f"{MIN_SYNC_INTERVAL} zurueck (Schutz vor Garmin-Kontosperre).")
        return None
    _last_sync_attempt = now

    try:
        client = get_client()
        today = datetime.date.today().isoformat()

        wellness = {
            "date": today,
            # bereits vorhanden (v0.3.0)
            "resting_hr": client.get_rhr_day(today),
            "steps": client.get_steps_data(today),
            "training_readiness": client.get_training_readiness(today),

            # neu: Erholung / Belastung - fuer Uebertrainings-Fruehwarnung
            "training_status": _safe_fetch("training_status", lambda: client.get_training_status(today)),
            "hrv": _safe_fetch("hrv", lambda: client.get_hrv_data(today)),
            "body_battery": _safe_fetch("body_battery", lambda: client.get_body_battery(today, today)),
            "stress": _safe_fetch("stress", lambda: client.get_all_day_stress(today)),
            "respiration": _safe_fetch("respiration", lambda: client.get_respiration_data(today)),
            "spo2": _safe_fetch("spo2", lambda: client.get_spo2_data(today)),
            "sleep": _safe_fetch("sleep", lambda: client.get_sleep_data(today)),

            # neu: Fitness-Fortschritt - fuer die Ironman-70.3-Vorbereitung
            "max_metrics": _safe_fetch("max_metrics", lambda: client.get_max_metrics(today)),  # VO2max, Fitness-Age
        }

        # Diese beiden aendern sich nur langsam (Tage/Wochen) -> nur einmal
        # woechentlich (montags) abrufen, um zusaetzliche Garmin-Calls und
        # damit das Rate-Limit-Risiko nicht unnoetig zu erhoehen.
        if datetime.date.today().weekday() == 0:  # Montag
            week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            wellness["endurance_score"] = _safe_fetch(
                "endurance_score", lambda: client.get_endurance_score(week_ago, today)
            )
            wellness["race_predictions"] = _safe_fetch("race_predictions", client.get_race_predictions)

        with open(DATA_FILE, "w") as f:
            json.dump(wellness, f, indent=2, ensure_ascii=False, default=str)

        publish_discovery()
        try:
            note = generate_coaching_note(wellness)
        except Exception as e:
            # Technischen Fehler nur ins Log schreiben, nicht in die Notiz, die
            # im Dashboard landet - dort sollen keine Exception-Details/Keys auftauchen.
            print(f"[ai_coach] Coaching-Notiz fehlgeschlagen: {e}")
            note = "Coaching-Tipp aktuell nicht verfuegbar - Werte wurden trotzdem synchronisiert."
        publish_state(wellness, coaching_note=note)
        publish_sync_status(ok=True)
        return wellness
    except Exception as e:
        print(f"[sync] Sync fehlgeschlagen: {e}")
        publish_sync_status(ok=False, detail=str(e))
        return None

@app.route("/")
def home():
    if not is_logged_in():
        return LOGIN_FORM
    latest = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            latest = json.load(f)
    return f"""
    <html><body style="font-family:sans-serif;padding:2rem;">
    <h1>Garmin AI Coach</h1>
    <p>Verbunden mit Garmin ✅</p>
    <p><a href="sync">Jetzt synchronisieren</a></p>
    <pre>{json.dumps(latest, indent=2, ensure_ascii=False)}</pre>
    </body></html>
    """

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
    do_sync(force=request.args.get("force") == "1")
    return redirect(".")

def _seconds_until_next_run(hour: int) -> float:
    now = datetime.datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()

def _scheduler_loop():
    """Laeuft im Hintergrund und ruft do_sync() einmal taeglich um SYNC_HOUR auf,
    damit "automatischer Sync" auch wirklich automatisch passiert."""
    while True:
        time.sleep(_seconds_until_next_run(SYNC_HOUR))
        try:
            do_sync()
        except Exception as e:
            print(f"[scheduler] Automatischer Sync fehlgeschlagen: {e}")

if __name__ == "__main__":
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8099)