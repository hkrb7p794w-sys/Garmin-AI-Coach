"""Fit Coach - Einstieg: Anmeldeseite (Ingress), MQTT-Befehle, Zeitplan."""
import os
import html
import datetime
import threading

from flask import Flask, request, redirect

import store
import publish
import sync
import garmin_sync
import yazio
import gym as gym_mod

app = Flask(__name__)
sync.SYNC_HOURS = sync.parse_hours(os.environ.get("SYNC_HOURS", "6,12,20"))


# ------------------------------------------------------------ MQTT-Befehle
def on_command(key, payload):
    if key == "_connected":
        sync.refresh()
        return
    s = sync.settings()
    if key in ("zielgewicht", "ziel_laeufe", "ziel_gym", "rekord_kg", "rekord_wdh"):
        try:
            v = float(payload)
        except ValueError:
            return
        if key in ("ziel_laeufe", "ziel_gym", "rekord_wdh"):
            v = int(round(v))
        sync.save_setting(key, v)
        publish.state(key, v)
        if key in ("zielgewicht", "ziel_laeufe", "ziel_gym"):
            sync.refresh()
    elif key == "uebung":
        sync.save_setting("uebung", payload)
        publish.state("uebung", payload)
    elif key == "gewicht_eintragen":
        try:
            v = round(float(payload), 2)
        except ValueError:
            return
        if v <= 0:
            return
        if not (30 <= v <= 250):
            print(f"[eingabe] Gewicht {v} kg unplausibel - ignoriert")
            return
        today = datetime.date.today().isoformat()
        store.update("weights.json", sync.WEIGHTS_DEFAULT,
                     lambda w: {**w, "manual": {**(w.get("manual") or {}), today: v}})
        sync.save_setting("gewicht_eintragen", v)
        publish.state("gewicht_eintragen", v)
        print(f"[eingabe] Gewicht {v} kg für {today} gespeichert")
        sync.refresh()
    elif key == "gewicht_rueckgaengig":
        today = datetime.date.today().isoformat()
        store.update("weights.json", sync.WEIGHTS_DEFAULT,
                     lambda w: {**w, "manual": {k: v for k, v in (w.get("manual") or {}).items() if k != today}})
        sync.save_setting("gewicht_eintragen", 0)
        publish.state("gewicht_eintragen", 0)
        sync.refresh()
    elif key == "rekord_speichern":
        name = s.get("uebung") or "Kniebeuge"
        kg, reps = float(s.get("rekord_kg") or 0), int(s.get("rekord_wdh") or 0)
        if reps <= 0:
            return
        entry = gym_mod.manual_entry(name, kg, reps)
        store.update("manual_records.json", [], lambda l: (l or []) + [entry])
        print(f"[eingabe] Rekord gespeichert: {entry['name']} {kg:g} kg × {reps}")
        sync.refresh()
    elif key == "rekord_rueckgaengig":
        store.update("manual_records.json", [], lambda l: (l or [])[:-1])
        sync.refresh()
    elif key == "sync":
        sync.full_sync_async("knopf")


# ---------------------------------------------------------------- Web-UI
CSS = """
:root{--bg:#f6f6f3;--card:#fff;--text:#1b1b19;--muted:#6b6a64;--line:#e4e3dc;--accent:#1baf7a;--btn:#0f7a55;--warn:#a86b00;--bad:#c93b3b}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--card:#1d1d1b;--text:#ececea;--muted:#a3a29b;--line:#2f2f2c;--accent:#22c08a;--btn:#13865e;--warn:#f0b13a;--bad:#ef6a6a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:22px;margin:4px 0 2px}h2{font-size:17px;margin:0 0 6px}p{margin:6px 0}
.sub{color:var(--muted);margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:12px 0}
.row{display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:13px;font-weight:600;background:var(--line)}
.ok{color:var(--accent)}.warn{color:var(--warn)}.bad{color:var(--bad)}
label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
input{width:100%;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);font-size:16px}
button{appearance:none;border:0;border-radius:10px;padding:12px 16px;font:inherit;font-size:15px;font-weight:600;background:var(--btn);color:#fff;cursor:pointer;margin-top:12px}
button.sec{background:var(--line);color:var(--text)}
.small{font-size:13px;color:var(--muted)}
.msg{padding:10px 12px;border-radius:10px;background:var(--line);margin:10px 0}
.msg.err{color:var(--bad)}
ul{padding-left:18px;margin:6px 0}
"""


def page(body: str, msg: str = "", err: bool = False) -> str:
    m = f'<div class="msg {"err" if err else ""}">{html.escape(msg)}</div>' if msg else ""
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Fit Coach</title><style>{CSS}</style></head><body><main>'
            f'<h1>Fit Coach</h1><div class="sub">Garmin + Yazio fürs eigene Dashboard</div>{m}{body}</main></body></html>')


def _fmt_ts(ts):
    if not ts:
        return "noch nie"
    try:
        d = datetime.datetime.fromisoformat(ts)
        return d.strftime("%d.%m. %H:%M")
    except ValueError:
        return ts


def home_body() -> str:
    st = sync.state()
    g, y = st.get("garmin") or {}, st.get("yazio") or {}
    parts = []
    # Garmin
    if garmin_sync.mfa_pending():
        parts.append("""<div class="card"><h2>Garmin – Bestätigungscode</h2>
        <p>Garmin hat einen Code per E-Mail oder an die Authenticator-App geschickt.</p>
        <form method="post" action="garmin/mfa"><label>Code</label>
        <input name="code" inputmode="numeric" autocomplete="one-time-code" required autofocus>
        <button type="submit">Bestätigen</button></form>
        <form method="post" action="garmin/cancel"><button class="sec" type="submit">Abbrechen</button></form></div>""")
    elif garmin_sync.is_connected():
        status = '<span class="pill ok">verbunden</span>'
        if g.get("needs_login"):
            status = '<span class="pill bad">bitte neu anmelden</span>'
        err = f'<p class="small bad">Letzter Fehler: {html.escape(g["last_error"])}</p>' if g.get("last_error") and (g.get("last_error_at") or "") >= (g.get("last_sync") or "") else ""
        parts.append(f"""<div class="card"><div class="row"><h2>Garmin</h2>{status}</div>
        <p class="small">Letzter Abruf: {_fmt_ts(g.get('last_sync'))}</p>{err}
        <form method="post" action="garmin/logout" onsubmit="return confirm('Garmin-Verbindung wirklich trennen?')">
        <button class="sec" type="submit">Garmin trennen</button></form></div>""")
    else:
        parts.append("""<div class="card"><h2>Garmin verbinden</h2>
        <p class="small">Dieselben Zugangsdaten wie in der Garmin-Connect-App. Das Passwort wird nicht gespeichert – nur ein Anmelde-Token, das sich selbst erneuert.</p>
        <form method="post" action="garmin/login"><label>E-Mail</label><input type="email" name="email" autocomplete="username" required>
        <label>Passwort</label><input type="password" name="password" autocomplete="current-password" required>
        <button type="submit">Bei Garmin anmelden</button></form>
        <p class="small">Mit Zwei-Faktor-Schutz kommt als Nächstes die Abfrage des Codes.</p></div>""")
    # Yazio
    if yazio.is_connected():
        status = '<span class="pill ok">verbunden</span>' if not y.get("needs_login") else '<span class="pill bad">bitte neu anmelden</span>'
        err = f'<p class="small warn">Hinweis: {html.escape(y["last_error"])}</p>' if y.get("last_error") else ""
        parts.append(f"""<div class="card"><div class="row"><h2>Yazio</h2>{status}</div>
        <p class="small">Letzter Abruf: {_fmt_ts(y.get('last_sync'))}</p>{err}
        <form method="post" action="yazio/logout" onsubmit="return confirm('Yazio-Verbindung wirklich trennen?')">
        <button class="sec" type="submit">Yazio trennen</button></form></div>""")
    else:
        parts.append("""<div class="card"><h2>Yazio verbinden <span class="small">(optional)</span></h2>
        <p class="small">Für Kalorien, Eiweiß und Wasser. Yazio hat keine offizielle Schnittstelle – die Verbindung nutzt die der Yazio-App und kann sich ändern.
        Geht nur mit E-Mail und Yazio-Passwort (nicht mit „Mit Apple/Google anmelden“).</p>
        <form method="post" action="yazio/login"><label>E-Mail</label><input type="email" name="email" autocomplete="username" required>
        <label>Yazio-Passwort</label><input type="password" name="password" autocomplete="current-password" required>
        <button type="submit">Bei Yazio anmelden</button></form></div>""")
    # Sync
    if garmin_sync.is_connected() or yazio.is_connected():
        running = st.get("sync_running")
        parts.append(f"""<div class="card"><div class="row"><h2>Daten</h2>
        <span class="pill">{'läuft …' if running else 'Abruf ' + ', '.join(f'{h} Uhr' for h in sync.SYNC_HOURS)}</span></div>
        <p class="small">Letzter Abruf: {_fmt_ts(st.get('last_sync'))}. Der erste Abruf holt auch die letzten Wochen nach und dauert 1–2 Minuten.</p>
        <form method="post" action="sync"><button type="submit">Jetzt synchronisieren</button></form>
        <p class="small">Fertig? Das Dashboard „Fit“ in der Seitenleiste zeigt alles an.</p></div>""")
    parts.append("""<div class="card small"><b>Datenschutz:</b> Alle Daten bleiben auf diesem Home Assistant. Gespeichert werden nur Anmelde-Tokens (Datei nur für die App lesbar) und die abgerufenen Werte.
    Garmin und Yazio werden nur zu den Abrufzeiten kontaktiert; keine KI, keine Weitergabe.</div>""")
    return "".join(parts)


@app.route("/")
def home():
    return page(home_body(), request.args.get("m", ""), request.args.get("e") == "1")


def _back(msg, err=False):
    """Zurück zur Startseite. Unter Ingress liegt die App unter
    /api/hassio_ingress/<token>/ - der Präfix kommt im Header X-Ingress-Path."""
    from urllib.parse import quote
    base = (request.headers.get("X-Ingress-Path") or "").rstrip("/")
    return redirect(f"{base}/?m={quote(msg)}&e={'1' if err else '0'}", code=303)


@app.route("/garmin/login", methods=["POST"])
def garmin_login():
    try:
        res = garmin_sync.start_login(request.form.get("email", ""), request.form.get("password", ""))
    except garmin_sync.GarminLoginError as e:
        return _back(str(e), True)
    if res == "mfa":
        return _back("Code angefordert – bitte unten eingeben.")
    _after_garmin_login()
    return _back("Mit Garmin verbunden. Der erste Abruf läuft im Hintergrund.")


@app.route("/garmin/mfa", methods=["POST"])
def garmin_mfa():
    try:
        garmin_sync.finish_mfa(request.form.get("code", ""))
    except garmin_sync.GarminLoginError as e:
        return _back(str(e), True)
    _after_garmin_login()
    return _back("Mit Garmin verbunden. Der erste Abruf läuft im Hintergrund.")


@app.route("/garmin/cancel", methods=["POST"])
def garmin_cancel():
    garmin_sync.cancel_mfa()
    return _back("Anmeldung abgebrochen.")


def _after_garmin_login():
    st = sync.state()
    g = st.get("garmin") or {}
    g.update(needs_login=False, last_error=None)
    st["garmin"] = g
    store.save("state.json", st)
    sync.publish_status(st)
    sync.full_sync_async("anmeldung", force=True)


@app.route("/garmin/logout", methods=["POST"])
def garmin_logout():
    garmin_sync.logout()
    st = sync.state()
    st["garmin"] = {}
    store.save("state.json", st)
    sync.refresh()
    return _back("Garmin getrennt. Die bisher abgerufenen Daten bleiben erhalten.")


@app.route("/yazio/login", methods=["POST"])
def yazio_login():
    try:
        yazio.login(request.form.get("email", ""), request.form.get("password", ""))
    except yazio.YazioError as e:
        return _back(str(e), True)
    except Exception as e:
        return _back(f"Yazio-Anmeldung fehlgeschlagen: {str(e)[:160]}", True)
    st = sync.state()
    st["yazio"] = {"needs_login": False}
    store.save("state.json", st)
    sync.full_sync_async("yazio-anmeldung", force=True)
    return _back("Mit Yazio verbunden. Die letzten 4 Wochen werden im Hintergrund geladen.")


@app.route("/yazio/logout", methods=["POST"])
def yazio_logout():
    yazio.logout()
    st = sync.state()
    st["yazio"] = {}
    store.save("state.json", st)
    sync.refresh()
    return _back("Yazio getrennt.")


@app.route("/sync", methods=["POST"])
def sync_now():
    sync.full_sync_async("webseite")
    return _back("Abruf gestartet – dauert meist unter einer Minute.")


@app.route("/health")
def health():
    return {"ok": True, "garmin": garmin_sync.is_connected(), "yazio": yazio.is_connected()}


def main():
    print(f"[start] Fit Coach {publish.VERSION}, Abruf um {sync.SYNC_HOURS} Uhr")
    publish.start(on_command)
    st = sync.state()
    if st.get("sync_running"):
        st["sync_running"] = False
        store.save("state.json", st)
    threading.Thread(target=sync.scheduler_loop, daemon=True).start()
    # Kurz nach dem Start einmal abrufen, wenn der letzte Abruf länger her ist
    def _startup():
        last = st.get("last_sync")
        stale = True
        if last:
            try:
                stale = (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(last)).total_seconds() > 3 * 3600
            except ValueError:
                pass
        if stale and (garmin_sync.is_connected() or yazio.is_connected()):
            sync.full_sync("start", force=True)
        else:
            sync.refresh()
    threading.Timer(15, _startup).start()
    app.run(host="0.0.0.0", port=8099, threaded=True)


if __name__ == "__main__":
    main()
