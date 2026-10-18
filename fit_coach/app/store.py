"""Dauerhafte JSON-Ablage unter /data (übersteht Neustarts und Updates der App).

Jede Datei wird atomar geschrieben (temporäre Datei + rename), damit ein
Stromausfall oder ein Neustart mitten im Schreiben nie eine halbe Datei
hinterlässt. Ein Lock pro Datei verhindert, dass Sync-Thread und MQTT-Befehle
gleichzeitig dieselbe Datei verändern.
"""
import json
import os
import threading
import datetime

DATA_DIR = os.environ.get("FIT_DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)

_locks = {}
_locks_guard = threading.Lock()


def path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _lock(name: str) -> threading.RLock:
    with _locks_guard:
        if name not in _locks:
            _locks[name] = threading.RLock()
        return _locks[name]


def load(name: str, default=None):
    p = path(name)
    with _lock(name):
        if not os.path.exists(p):
            return _copy(default)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data if data is not None else _copy(default)
        except Exception as e:  # kaputte Datei: neu beginnen statt abstürzen
            print(f"[store] {name} nicht lesbar ({e}) - starte mit leerem Stand")
            return _copy(default)


def save(name: str, data, private: bool = False):
    p = path(name)
    tmp = f"{p}.tmp"
    with _lock(name):
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, default=str)
            os.replace(tmp, p)
        except Exception as e:
            print(f"[store] {name} konnte nicht geschrieben werden: {e}")
            try:
                os.remove(tmp)
            except OSError:
                pass


def update(name: str, default, fn):
    """Lesen, ändern, schreiben unter einem Lock. fn bekommt den Stand und gibt
    den neuen Stand zurück (oder verändert ihn in place und gibt None zurück)."""
    with _lock(name):
        data = load(name, default)
        new = fn(data)
        data = data if new is None else new
        save(name, data)
        return data


def delete(name: str):
    with _lock(name):
        try:
            os.remove(path(name))
        except FileNotFoundError:
            pass


def prune_dates(d: dict, keep_days: int, today: datetime.date = None) -> dict:
    """Behält nur Schlüssel im Format YYYY-MM-DD, die höchstens keep_days alt sind."""
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=keep_days)).isoformat()
    return {k: v for k, v in (d or {}).items() if str(k) >= cutoff}


def _copy(v):
    if isinstance(v, (dict, list)):
        return json.loads(json.dumps(v))
    return v
