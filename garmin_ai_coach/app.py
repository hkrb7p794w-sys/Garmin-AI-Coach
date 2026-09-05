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
            "resting_hr": client.get_rhr_day(today),
            "steps": client.get_steps_data(today),
            "training_readiness": client.get_training_readiness(today),
        }
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
