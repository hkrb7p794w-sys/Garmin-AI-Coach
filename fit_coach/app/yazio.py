"""Inoffizieller Yazio-Client (Yazio hat keine öffentliche API).

Grundlage: die Open-Source-Projekte juriadams/yazio bzw. der Fork dimensi/yazio
(Stand 10/2026: Login über API v22, Abfragen über v20). Login per
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
import os
import time
import datetime
import requests

import store

DATA_BASE = "https://yzapi.yazio.com/v20"  # Abfragen (Tagesübersicht, Gewicht, Ziele)
TOKEN_FILE = "yazio_token.json"
TIMEOUT = 20

# Seit 10/2026 nimmt Yazio die Anmeldung nur noch über /v22/oauth/token mit dem
# OAuth-Client der aktuellen App an, und unbekannte User-Agents werden abgewiesen
# („version_blocked“, oft nur als leeres HTTP 400). Werte wie im gepflegten Fork
# dimensi/yazio (PR #1 „update mobile authentication“). Der alte Client bleibt als
# Rückfall für ältere API-Stände.
USER_AGENT = os.environ.get(
    "YAZIO_USER_AGENT", "YAZIO/26.30.1 (com.yazio.ios.YAZIO; build:2607271240; iOS 27.0.0) Ktor")
HEADERS = {"Accept": "application/json", "User-Agent": USER_AGENT}

CLIENTS = {
    "app2026": ("https://yzapi.yazio.com/v22/oauth/token",
                "3_5rbw4kehpugw8ogsc8ck8oo4ogswgckcskc04gcg8kk8k48ssw",
                "25gdtt1hvdi8gwowoww4oo88sgsw0oo04o0og0kkgwwks8k0k"),
    "legacy": ("https://yzapi.yazio.com/v20/oauth/token",
               "1_4hiybetvfksgw40o0sog4s884kwc840wwso8go4k8c04goo4c",
               "6rok2m65xuskgkgogw40wkkk8sw0osg84s8cggsc4woos4s8o"),
}
ORDER = ("app2026", "legacy")


class YazioError(Exception):
    pass


class YazioAuthError(YazioError):
    pass


def is_connected() -> bool:
    tok = store.load(TOKEN_FILE, {})
    return bool(tok.get("refresh_token") or tok.get("access_token"))


def _redact(text: str) -> str:
    return (text or "").replace("\n", " ")[:400]


def _describe(r) -> str:
    """Yazios Fehlermeldung lesbar machen (error / error_description / message)."""
    try:
        j = r.json()
    except ValueError:
        return _redact(r.text)
    if isinstance(j, dict):
        parts = [str(j.get(k)) for k in ("error", "error_description", "message", "title", "detail") if j.get(k)]
        if parts:
            return " – ".join(parts)
    return _redact(r.text)


def _post_token(fields: dict, clients=ORDER) -> dict:
    """Token holen; probiert die Clients nacheinander und protokolliert jede Antwort
    (ohne Passwort). Falsche Zugangsdaten (invalid_grant / 401) brechen sofort ab –
    kein mehrfaches Probieren mit demselben falschen Passwort."""
    seen = []
    grant = fields.get("grant_type")
    for name in clients:
        url, cid, secret = CLIENTS[name]
        payload = {"client_id": cid, "client_secret": secret, **fields}
        try:
            r = requests.post(url, json=payload, timeout=TIMEOUT,
                              headers=dict(HEADERS, **{"Content-Type": "application/json"}))
        except requests.RequestException as e:
            print(f"[yazio] {grant} {name}: nicht erreichbar ({e})", flush=True)
            seen.append(f"{name}: nicht erreichbar")
            continue
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                data = {}
            if data.get("access_token"):
                print(f"[yazio] {grant} {name}: ok", flush=True)
                data["client"] = name
                data["expires_at"] = time.time() + float(data.get("expires_in") or 3600) - 300
                return data
            print(f"[yazio] {grant} {name}: 200 ohne Token: {_redact(r.text)}", flush=True)
            seen.append(f"{name}: Antwort ohne Token")
            continue
        why = _describe(r)
        print(f"[yazio] {grant} {name}: HTTP {r.status_code}: {why or '(leere Antwort)'}", flush=True)
        low = why.lower()
        if r.status_code == 401 or "invalid_grant" in low or "credentials" in low or "password" in low:
            raise YazioAuthError("Yazio meldet: E-Mail oder Passwort falsch (oder Konto ohne Yazio-Passwort, "
                                 f"z. B. Apple-/Google-Anmeldung). Antwort: {why[:160]}")
        if "version_blocked" in low:
            why = "App-Version abgelehnt (version_blocked) – Fit Coach braucht ein Update"
        seen.append(f"{name}: HTTP {r.status_code} {why[:120]}".strip())
    raise YazioError("Yazio-Login fehlgeschlagen – " + " | ".join(seen[:2]))


def login(email: str, password: str) -> dict:
    data = _post_token({"username": email.strip(), "password": password, "grant_type": "password"})
    store.save(TOKEN_FILE, {k: data.get(k) for k in ("access_token", "refresh_token", "expires_at", "client")}, private=True)
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
        client = tok.get("client") if tok.get("client") in CLIENTS else "legacy"
        data = _post_token({"refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, clients=(client,))
    except YazioError:
        # auch ein Token des alten Clients, den Yazio nicht mehr annimmt
        raise YazioAuthError("Yazio-Anmeldung abgelaufen - bitte neu anmelden")
    tok = {"access_token": data["access_token"], "refresh_token": data.get("refresh_token") or tok["refresh_token"],
           "expires_at": data["expires_at"], "client": data.get("client")}
    store.save(TOKEN_FILE, tok, private=True)
    return tok


def _get(path: str, params=None):
    tok = _token()
    base = DATA_BASE
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
