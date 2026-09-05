import os, json, datetime
from flask import Flask, request, redirect
from ha_publish import publish_discovery, publish_state
from ai_coach import generate_coaching_note

DATA_DIR = "/data"
TOKEN_DIR = os.path.join(DATA_DIR, "garmin_tokens")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TOKEN_DIR, exist_ok=True)
os.environ["GARMINTOKENS"] = TOKEN_DIR

app = Flask(__name__)

def is_logged_in():
    return len(os.listdir(TOKEN_DIR)) > 0

def get_client():
    from garminconnect import Garmin
    client = Garmin()
    client.login(TOKEN_DIR)
    return client

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
    return redirect(".")

    publish_discovery()
    try:
        note = generate_coaching_note(wellness)
    except Exception as e:
        note = f"Coaching-Tipp nicht verfügbar: {e}"
    publish_state(wellness, coaching_note=note)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)