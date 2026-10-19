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

BASES = ("https://yzapi.yazio.com/v20", "https://yzapi.yazio.com/v15")  # für Abfragen mit gespeichertem Token
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


# Varianten der Token-Anfrage, wichtigste zuerst. Variante 1 entspricht exakt dem
# gepflegten Projekt juriadams/yazio (JSON-Text ohne eigenen Content-Type und ohne
# eigenen User-Agent), die anderen fangen ältere API-Stände ab.
ATTEMPTS = (
    ("v20", "json-text"),
    ("v20", "json"),
    ("v20", "form"),
    ("v15", "form"),
)


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


def _post_token(payload: dict) -> dict:
    """Probiert die Varianten nacheinander und protokolliert jede Antwort (ohne
    Passwort). Falsche Zugangsdaten (invalid_grant / 401) brechen sofort ab – kein
    mehrfaches Probieren mit demselben falschen Passwort."""
    import json as _json
    seen = []
    grant = payload.get("grant_type")
    for ver, mode in ATTEMPTS:
        url = f"https://yzapi.yazio.com/{ver}/oauth/token"
        try:
            if mode == "json-text":
                r = requests.post(url, data=_json.dumps(payload).encode(), timeout=TIMEOUT,
                                  headers={"Content-Type": "text/plain;charset=UTF-8", "Accept": "*/*"})
            elif mode == "json":
                r = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
            else:
                r = requests.post(url, data=payload, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as e:
            print(f"[yazio] {grant} {ver}/{mode}: nicht erreichbar ({e})", flush=True)
            seen.append(f"{ver}/{mode}: nicht erreichbar")
            continue
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                data = {}
            if data.get("access_token"):
                print(f"[yazio] {grant} {ver}/{mode}: ok", flush=True)
                data["base"] = f"https://yzapi.yazio.com/{ver}"
                data["expires_at"] = time.time() + float(data.get("expires_in") or 3600) - 300
                return data
            print(f"[yazio] {grant} {ver}/{mode}: 200 ohne Token: {_redact(r.text)}", flush=True)
            seen.append(f"{ver}/{mode}: Antwort ohne Token")
            continue
        why = _describe(r)
        print(f"[yazio] {grant} {ver}/{mode}: HTTP {r.status_code}: {why}", flush=True)
        low = why.lower()
        if r.status_code == 401 or "invalid_grant" in low or "credentials" in low or "password" in low:
            raise YazioAuthError("Yazio meldet: E-Mail oder Passwort falsch (oder Konto ohne Yazio-Passwort, "
                                 f"z. B. Apple-/Google-Anmeldung). Antwort: {why[:160]}")
        seen.append(f"{ver}/{mode}: HTTP {r.status_code} {why[:120]}")
    raise YazioError("Yazio-Login fehlgeschlagen – " + " | ".join(seen[:2]))


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
