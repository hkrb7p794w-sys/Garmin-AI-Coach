"""Inoffizieller Yazio-Client (Yazio hat keine öffentliche API).

Grundlage: das gepflegte Open-Source-Projekt juriadams/yazio (Stand 10/2026,
API v20) und die Dokumentation saganos/yazio_public_api (API v15). Login per
OAuth2 „password“-Grant mit dem Client der Yazio-App; danach wird nur das
Token-Paar gespeichert (Datei mit Rechten 0600 in /data), nie das Passwort.
Läuft das Access-Token ab (ca. 48 h), wird es mit dem Refresh-Token erneuert.

Hinweise:
- Konten, die bei Yazio nur über „Mit Apple/Google anmelden“ laufen, haben kein
  Yazio-Passwort - dann ist diese Verbindung nicht möglich.
- Weil die Schnittstelle inoffiziell ist, kann Yazio sie jederzeit ändern. Jede
  Abfrage ist deshalb einzeln abgesichert; ein Fehler legt nur den Yazio-Teil
  lahm, nie den Garmin-Sync.
"""
import time
import datetime
import requests

import store

BASES = ("https://yzapi.yazio.com/v20", "https://yzapi.yazio.com/v15")
CLIENT_ID = "1_4hiybetvfksgw40o0sog4s884kwc840wwso8go4k8c04goo4c"
CLIENT_SECRET = "6rok2m65xuskgkgogw40wkkk8sw0osg84s8cggsc4woos4s8o"
TOKEN_FILE = "yazio_token.json"
TIMEOUT = 20
HEADERS = {"Accept": "application/json", "User-Agent": "YAZIO/12 (Fit Coach Home Assistant)"}


class YazioError(Exception):
    pass


class YazioAuthError(YazioError):
    pass


def is_connected() -> bool:
    tok = store.load(TOKEN_FILE, {})
    return bool(tok.get("refresh_token") or tok.get("access_token"))


def _post_token(payload: dict) -> dict:
    """Probiert JSON (v20) und Formular-Kodierung (v15). Falsche Zugangsdaten
    (invalid_grant/401) brechen sofort ab - kein mehrfaches Probieren mit
    demselben falschen Passwort."""
    last = None
    for base in BASES:
        for mode in ("json", "form"):
            try:
                if mode == "json":
                    r = requests.post(f"{base}/oauth/token", json=payload, headers=HEADERS, timeout=TIMEOUT)
                else:
                    r = requests.post(f"{base}/oauth/token", data=payload, headers=HEADERS, timeout=TIMEOUT)
            except requests.RequestException as e:
                last = YazioError(f"Yazio nicht erreichbar: {e}")
                continue
            if r.status_code == 200:
                data = r.json()
                if data.get("access_token"):
                    data["base"] = base
                    data["expires_at"] = time.time() + float(data.get("expires_in") or 3600) - 300
                    return data
                last = YazioError("Yazio-Antwort ohne Token")
                continue
            body = (r.text or "")[:300].lower()
            if r.status_code in (400, 401) and ("invalid_grant" in body or "credentials" in body or r.status_code == 401):
                raise YazioAuthError("E-Mail oder Passwort falsch (oder Konto ohne Yazio-Passwort, z. B. Apple-/Google-Anmeldung).")
            last = YazioError(f"Yazio-Login fehlgeschlagen (HTTP {r.status_code})")
    raise last or YazioError("Yazio-Login fehlgeschlagen")


def login(email: str, password: str) -> dict:
    data = _post_token({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                        "username": email.strip(), "password": password, "grant_type": "password"})
    store.save(TOKEN_FILE, {k: data.get(k) for k in ("access_token", "refresh_token", "expires_at", "base")}, private=True)
    return data


def logout():
    store.delete(TOKEN_FILE)


def _token() -> dict:
    tok = store.load(TOKEN_FILE, {})
    if not tok:
        raise YazioAuthError("Nicht mit Yazio verbunden")
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time():
        return tok
    if not tok.get("refresh_token"):
        raise YazioAuthError("Yazio-Anmeldung abgelaufen - bitte neu anmelden")
    try:
        data = _post_token({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    except YazioAuthError:
        raise YazioAuthError("Yazio-Anmeldung abgelaufen - bitte neu anmelden")
    tok = {"access_token": data["access_token"], "refresh_token": data.get("refresh_token") or tok["refresh_token"],
           "expires_at": data["expires_at"], "base": data.get("base") or tok.get("base")}
    store.save(TOKEN_FILE, tok, private=True)
    return tok


def _get(path: str, params=None):
    tok = _token()
    base = tok.get("base") or BASES[0]
    h = dict(HEADERS, Authorization=f"Bearer {tok['access_token']}")
    r = requests.get(f"{base}{path}", params=params, headers=h, timeout=TIMEOUT)
    if r.status_code == 401:
        # Token serverseitig verworfen: einmal erneuern und wiederholen
        store.update(TOKEN_FILE, {}, lambda t: {**t, "expires_at": 0})
        tok = _token()
        h["Authorization"] = f"Bearer {tok['access_token']}"
        r = requests.get(f"{base}{path}", params=params, headers=h, timeout=TIMEOUT)
    if r.status_code == 204:
        return None
    if r.status_code != 200:
        raise YazioError(f"Yazio {path}: HTTP {r.status_code}")
    return r.json()


def daily_summary(day: datetime.date):
    return _get("/user/widgets/daily-summary", {"date": day.isoformat()})


def last_weight(day: datetime.date):
    """Letzter Gewichtseintrag am oder vor `day` -> (Datum, kg) oder None."""
    data = _get("/user/bodyvalues/weight/last", {"date": day.isoformat()})
    if not data or data.get("value") in (None, 0):
        return None
    return str(data.get("date") or day.isoformat())[:10], float(data["value"])


def goals(day: datetime.date):
    return _get("/user/goals/unmodified", {"date": day.isoformat()})
