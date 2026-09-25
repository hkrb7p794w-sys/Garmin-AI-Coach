"""Zustandsdateien, die über Syncs hinweg bestehen bleiben müssen (seit v0.18.0):

1. Coach-Status (Review-Punkt 1 + 21): ob die KI-Schicht funktioniert, wann
   zuletzt erfolgreich, wie viele Fehlschläge in Folge, und die letzte
   erfolgreiche KI-Notiz. Vorher meldete sync_status "ok", während der
   KI-Coach seit Tagen ausgefallen war - das war genau der stille Fehlschlag
   aus den Lessons Learned.

2. Kraftwerte (Review-Punkt 20): geschätztes 1-Wiederholungs-Maximum (e1RM)
   je Übung über Wochen statt einer Satzliste der letzten 7 Tage. Formel nach
   Epley: e1RM = Gewicht × (1 + Wiederholungen / 30). Bei mehr als ~10-12
   Wiederholungen wird jede e1RM-Formel ungenauer - der Wert ist deshalb als
   "geschätzt" gekennzeichnet und nur für den eigenen Trend gedacht, nicht als
   absoluter Maximalkraftwert.
"""
import os
import json
import datetime

DATA_DIR = "/data"
COACH_STATUS_FILE = os.path.join(DATA_DIR, "coach_status.json")
E1RM_FILE = os.path.join(DATA_DIR, "e1rm_history.json")
E1RM_KEEP_DAYS = 180
E1RM_MAX_REPS = 15  # darüber wird kein e1RM geschätzt


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f) or default
    except Exception as e:
        print(f"[progress] {path} nicht lesbar, starte neu: {e}")
        return default


def _save(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[progress] {path} konnte nicht geschrieben werden: {e}")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Coach-Status
# ---------------------------------------------------------------------------

def record_ai_result(kind: str, ok: bool, text: str = None, error: str = None, model: str = None) -> dict:
    """kind: 'coaching' | 'gym' | 'weekly' | 'chat' | 'plan'. Speichert pro Art
    Erfolg/Fehler; für 'coaching' zusätzlich die letzte erfolgreiche Notiz."""
    state = _load(COACH_STATUS_FILE, {})
    entry = state.get(kind) or {}
    if ok:
        entry["last_success"] = _now_iso()
        entry["consecutive_failures"] = 0
        entry["last_model"] = model
        if text and kind == "coaching":
            entry["last_text"] = text
    else:
        entry["consecutive_failures"] = int(entry.get("consecutive_failures") or 0) + 1
        entry["last_failure"] = _now_iso()
        # Nur die erste Zeile/400 Zeichen - kein API-Key, keine Prompt-Inhalte.
        entry["last_error"] = (error or "").splitlines()[0][:400] if error else None
    state[kind] = entry
    _save(COACH_STATUS_FILE, state)
    return state


def coach_status() -> dict:
    return _load(COACH_STATUS_FILE, {})


def overall_status(state: dict) -> str:
    """'ok' | 'eingeschränkt' | 'ausgefallen' - bezogen auf die Tagesnotiz,
    weil die der Kern des Coaches ist."""
    c = (state or {}).get("coaching") or {}
    fails = int(c.get("consecutive_failures") or 0)
    if fails == 0:
        return "ok"
    if fails < 2:
        return "eingeschränkt"
    return "ausgefallen"


# ---------------------------------------------------------------------------
# Kraftwerte (e1RM)
# ---------------------------------------------------------------------------

def epley(weight_kg, reps):
    if not isinstance(weight_kg, (int, float)) or not isinstance(reps, (int, float)):
        return None
    if weight_kg <= 0 or reps <= 0 or reps > E1RM_MAX_REPS:
        return None
    return round(weight_kg * (1 + reps / 30.0), 1)


def update_e1rm(strength_sessions: list) -> dict:
    """Übernimmt je Übung und Tag den besten e1RM-Wert in die Historie.
    Format: {exercise: {date: e1rm}}."""
    hist = _load(E1RM_FILE, {})
    for s in strength_sessions or []:
        day = s.get("date")
        if not day:
            continue
        for ex in s.get("exercises") or []:
            name = ex.get("exercise")
            if not name:
                continue
            best = None
            for st in ex.get("sets") or []:
                v = epley(st.get("weight_kg"), st.get("reps"))
                if v is not None and (best is None or v > best):
                    best = v
            if best is None:
                continue
            per_ex = hist.setdefault(name, {})
            if best > (per_ex.get(day) or 0):
                per_ex[day] = best
    cutoff = (datetime.date.today() - datetime.timedelta(days=E1RM_KEEP_DAYS)).isoformat()
    hist = {k: {d: v for d, v in days.items() if d >= cutoff} for k, days in hist.items()}
    hist = {k: v for k, v in hist.items() if v}
    _save(E1RM_FILE, hist)
    return hist


def e1rm_summary(hist: dict, today: datetime.date = None) -> list:
    """Je Übung: aktueller Wert (bester der letzten 14 Tage) vs. Vergleichswert
    (bester im Fenster 28-56 Tage zurück). Sortiert nach letztem Trainingsdatum."""
    today = today or datetime.date.today()
    out = []
    for name, days in (hist or {}).items():
        def best_in(lo, hi):
            vals = []
            for d, v in days.items():
                try:
                    age = (today - datetime.date.fromisoformat(d)).days
                except ValueError:
                    continue
                if lo <= age <= hi:
                    vals.append(v)
            return max(vals) if vals else None
        current = best_in(0, 13)
        before = best_in(28, 56)
        last = max(days.keys()) if days else None
        change = round((current - before) / before * 100, 1) if current and before else None
        out.append({"exercise": name, "current": current, "before": before,
                    "change_pct": change, "last_date": last, "sessions": len(days)})
    out.sort(key=lambda x: x.get("last_date") or "", reverse=True)
    return out
