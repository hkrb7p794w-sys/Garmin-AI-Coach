import os, json, datetime, threading, time
from flask import Flask, request, redirect
from ha_publish import (
    publish_discovery,
    publish_state,
    publish_sync_status,
    publish_coaching_note,
    publish_weekly_report,
    publish_strength_exercises,
    publish_gym_coaching_note,
    publish_trainingsplan_kommentar,
    publish_vorschlaege,
    publish_chat_history,
    set_sync_button_callback,
    set_vorschlag_callbacks,
    set_chat_callback,
    extract_metrics,
)
from ai_coach import (
    generate_coaching_note,
    generate_weekly_report,
    generate_gym_coaching_note,
    generate_trainingsplan_kommentar,
    generate_chat_answer,
    TRAININGSPLAN_GYM_KRITIK,
)
import fit_exercises
import suggestions
import chat

DATA_DIR = "/data"
TOKEN_DIR = os.path.join(DATA_DIR, "garmin_tokens")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
# Rollierende Tages-Historie fuer Wochentrends (Ruhepuls, HRV, Schlaf, Readiness).
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HISTORY_DAYS = 60
# Cache der per FIT-Datei extrahierten Kraft-Uebungen je Aktivitaet (siehe
# fit_exercises.py) - dauerhaft, damit nicht bei jedem Sync erneut die
# Original-Datei jeder Kraft-Aktivitaet von Garmin geladen wird.
STRENGTH_FILE = os.path.join(DATA_DIR, "strength_exercises.json")
STRENGTH_CACHE_DAYS = 21
# Zustand der Trainingsplan-Kommentierung (Tab "Trainingsplaene", siehe
# check_trainingsplan_trigger unten) - welche Phase zuletzt bekannt war und
# wann welcher Trigger zuletzt ausgeloest hat, damit nicht jeder Sync erneut
# denselben Grund meldet, solange der Zustand anhaelt.
TRAININGSPLAN_STATE_FILE = os.path.join(DATA_DIR, "trainingsplan_state.json")
TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS = 21
TRAININGSPLAN_READINESS_LOW_THRESHOLD = 60
TRAININGSPLAN_VO2MAX_STAGNATION_TOLERANCE = 0.3
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TOKEN_DIR, exist_ok=True)
os.environ["GARMINTOKENS"] = TOKEN_DIR

# Stunde (0-23, lokale Zeit des Containers), zu der automatisch synchronisiert wird.
# Wird von run.sh aus der Add-on-Option "sync_hour" befuellt.
SYNC_HOUR = int(os.environ.get("SYNC_HOUR", 6))
RACE_DATE = os.environ.get("RACE_DATE", "2027-08-29")

# Periodisierung Ironman 70.3 (siehe claude/status-und-plan.md im Projekt) - grobe Monats-Phasen.
PHASES = [
    (datetime.date(2026, 9, 1), datetime.date(2026, 12, 31), "Grundlagenausdauer"),
    (datetime.date(2027, 1, 1), datetime.date(2027, 3, 31), "Aufbau 1"),
    (datetime.date(2027, 4, 1), datetime.date(2027, 6, 30), "Aufbau 2 (spezifisch)"),
    (datetime.date(2027, 7, 1), datetime.date(2027, 7, 31), "Peak"),
    (datetime.date(2027, 8, 1), datetime.date(2027, 12, 31), "Taper/Rennwoche"),
]

app = Flask(__name__)


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

def _volumes_in_window(activities, window_start, window_end):
    """Summiert Aktivitaeten in einem Zeitfenster je Disziplin (km/Minuten).

    window_start/window_end sind konkrete datetime-Grenzen (start inklusiv,
    end exklusiv) - so lassen sich echte Kalenderwochen (Mo-So) abbilden statt
    nur rollierender 7-Tage-Fenster ab "jetzt"."""
    totals = {"swim_km": 0.0, "bike_km": 0.0, "run_km": 0.0,
              "swim_min": 0.0, "bike_min": 0.0, "run_min": 0.0, "strength_min": 0.0,
              "swim_sessions": 0, "bike_sessions": 0, "run_sessions": 0,
              "strength_sessions": 0}
    if not activities:
        return totals
    for act in activities:
        try:
            start_str = act.get("startTimeLocal")
            if not start_str:
                continue
            start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            if not (window_start <= start_dt < window_end):
                continue
            type_key = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
            distance_km = (act.get("distance") or 0) / 1000.0
            duration_min = (act.get("duration") or 0) / 60.0
            if "swim" in type_key:
                totals["swim_km"] += distance_km
                totals["swim_min"] += duration_min
                totals["swim_sessions"] += 1
            elif "bik" in type_key or "cycl" in type_key or "ride" in type_key:
                # Alex faehrt auf Zwift (das laedt die Einheit inkl. echter Distanz
                # nach Garmin hoch) und laesst parallel zur Herzfrequenzmessung eine
                # zweite Aktivitaet auf der Uhr mitlaufen, die er selbst als "Indoor
                # Radfahren" ohne km einordnet - dieselbe Fahrt wuerde sonst doppelt
                # als zwei Rad-Einheiten gezaehlt (Sessions UND Minuten). Nur
                # Aktivitaeten mit echter Distanz > 0 zaehlen als Rad-Einheit; die
                # reine Herzfrequenz-Zweitaufzeichnung (0 km) wird ignoriert.
                if distance_km <= 0:
                    continue
                totals["bike_km"] += distance_km
                totals["bike_min"] += duration_min
                totals["bike_sessions"] += 1
            elif "run" in type_key:
                totals["run_km"] += distance_km
                totals["run_min"] += duration_min
                totals["run_sessions"] += 1
            elif "strength" in type_key or "weight" in type_key or "gym" in type_key:
                totals["strength_min"] += duration_min
                totals["strength_sessions"] += 1
        except Exception as e:
            print(f"[sync] Aktivitaet konnte nicht ausgewertet werden: {e}")
    return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}

def _fetch_max_metrics(client, today_date):
    """Holt VO2max ueber ein 14-Tage-Fenster statt nur fuer heute.

    Garmin berechnet VO2max nur nach qualifizierenden Einheiten, der Tageseintrag
    fuer 'heute' ist deshalb meistens leer - genau daran lag es, dass der VO2max-
    Sensor dauerhaft 'unbekannt' blieb. Die Bibliothek fragt fest cdate/cdate ab,
    der Endpunkt kann aber einen Zeitraum: ein Request statt 14 einzelner (schont
    das Garmin-Rate-Limit)."""
    start = (today_date - datetime.timedelta(days=13)).isoformat()
    end = today_date.isoformat()
    try:
        return client.connectapi(f"/metrics-service/metrics/maxmet/daily/{start}/{end}")
    except Exception as e:
        print(f"[sync] VO2max-Zeitraumabfrage fehlgeschlagen ({e}), nutze Einzeltag")
        return _safe_fetch("max_metrics", lambda: client.get_max_metrics(end))


def _update_history(wellness):
    """Fuehrt eine rollierende Tages-Historie in /data/history.json.

    Damit kann der Wochenreport Trends (Ruhepuls, HRV, Schlaf, Readiness) ueber
    mehrere Tage bilden, ohne fuer jeden Tag erneut bei Garmin anzufragen."""
    metrics = extract_metrics(wellness)
    entry = {
        "date": wellness.get("date"),
        "resting_hr": metrics["resting_hr"],
        "hrv_avg": metrics["hrv_avg"],
        "body_battery": metrics["body_battery"],
        "sleep_hours": metrics["sleep_hours"],
        "sleep_score": metrics["sleep_score"],
        "readiness": metrics["training_readiness_score"],
        "stress_avg": metrics["stress_avg"],
        "steps": metrics["steps_today"],
        # Seit v0.12.0: fuer den VO2max-Stagnations-Trigger der
        # Trainingsplan-Kommentierung (siehe check_trainingsplan_trigger).
        # Aeltere Historieneintraege haben dieses Feld noch nicht - das ist
        # unproblematisch, _history_avg() ueberspringt fehlende Werte einfach.
        "vo2max": metrics["vo2max"],
    }
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f) or []
        except Exception as e:
            print(f"[history] nicht lesbar, starte neu: {e}")
            history = []
    history = [h for h in history if h.get("date") != entry["date"]]
    history.append(entry)
    history = sorted(history, key=lambda h: str(h.get("date") or ""))[-HISTORY_DAYS:]
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[history] konnte nicht geschrieben werden: {e}")
    return history


def _history_avg(history, key, offset_from: int, offset_to: int, today=None):
    """Mittelwert eines Feldes ueber Tage mit Abstand offset_from..offset_to zu heute."""
    today = today or datetime.date.today()
    values = []
    for entry in history or []:
        try:
            day = datetime.date.fromisoformat(str(entry.get("date")))
        except (TypeError, ValueError):
            continue
        if offset_from <= (today - day).days <= offset_to:
            value = entry.get(key)
            if isinstance(value, (int, float)):
                values.append(value)
    return round(sum(values) / len(values), 1) if values else None


def _pct_change(current, previous):
    """Prozentuale Veraenderung; None wenn die Vorwoche keine Basis hergibt."""
    if not previous or current is None:
        return None
    return round((current - previous) / previous * 100)


def _fmt_dm(d: datetime.date) -> str:
    return d.strftime("%d.%m.")


def _load_strength_cache() -> dict:
    if not os.path.exists(STRENGTH_FILE):
        return {}
    try:
        with open(STRENGTH_FILE) as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[strength] Cache nicht lesbar, starte neu: {e}")
        return {}


def _save_strength_cache(cache: dict) -> dict:
    """Speichert den Uebungs-Cache, begrenzt auf STRENGTH_CACHE_DAYS Tage
    (analog zu HISTORY_DAYS bei der Wellness-Historie), damit die Datei nicht
    unbegrenzt waechst."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=STRENGTH_CACHE_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if (v.get("date") or "") >= cutoff}
    try:
        with open(STRENGTH_FILE, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[strength] Cache konnte nicht geschrieben werden: {e}")
    return cache


def _is_broken_strength_entry(entry: dict) -> bool:
    """Erkennt Cache-Eintraege aus der fehlgeschlagenen v0.10.0-FIT-Extraktion
    (leere Uebungsliste oder nur der Codename-Platzhalter „Uebung (Code ...)"),
    damit sie nach dem v0.10.1-Fix (exerciseSets-API statt eigenem FIT-Parsing)
    automatisch einmalig neu abgerufen werden, statt dauerhaft als kaputter
    Eintrag im Cache haengen zu bleiben (siehe claude/status-und-plan.md,
    Abschnitt v0.10.1 - live bestaetigt: 2 von 4 Kraft-Einheiten des ersten
    echten Syncs blieben unter v0.10.0 leer bzw. nur mit Codename-Platzhalter)."""
    exercises = entry.get("exercises") or []
    if not exercises:
        return True
    return any(
        str((ex or {}).get("exercise", "")).startswith("Uebung (Code")
        for ex in exercises
    )


def _update_strength_exercises(client, activities: list) -> list:
    """Laedt fuer Kraft-Aktivitaeten der laufenden Woche, die noch nicht im
    Cache stehen (oder deren Cache-Eintrag als fehlgeschlagen erkannt wurde,
    siehe _is_broken_strength_entry), die Uebungsdaten ueber Garmins
    exerciseSets-API (siehe fit_exercises.py) - die normale Aktivitaetenliste
    liefert dafuer nur Aggregatwerte (total_sets/total_reps/total_volume),
    keine Aufschluesselung je Uebung. Gibt die Sessions der laufenden Woche
    zurueck (fuer Wochenreport/Dashboard), aeltere bleiben nur im Cache."""
    cache = _load_strength_cache()
    broken_keys = [k for k, v in cache.items() if _is_broken_strength_entry(v)]
    for k in broken_keys:
        del cache[k]
    if broken_keys:
        print(f"[strength] {len(broken_keys)} kaputte Cache-Eintraege (v0.10.0) verworfen, werden neu abgerufen: {broken_keys}")
    now = datetime.datetime.now()
    window_start = now - datetime.timedelta(days=7)
    changed = bool(broken_keys)

    for act in activities or []:
        try:
            type_key = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
            if not ("strength" in type_key or "weight" in type_key or "gym" in type_key):
                continue
            start_str = act.get("startTimeLocal")
            if not start_str:
                continue
            start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            if start_dt < window_start:
                continue
            activity_id = act.get("activityId")
            if activity_id is None:
                continue
            key = str(activity_id)
            if key in cache:
                continue
            exercises = fit_exercises.get_strength_exercises(client, activity_id)
            cache[key] = {
                "date": start_dt.date().isoformat(),
                "activity_name": act.get("activityName"),
                "exercises": exercises,
            }
            changed = True
        except Exception as e:
            print(f"[strength] Aktivitaet konnte nicht verarbeitet werden: {e}")

    if changed:
        cache = _save_strength_cache(cache)

    window_date = window_start.date().isoformat()
    sessions = [v for v in cache.values() if (v.get("date") or "") >= window_date]
    return sorted(sessions, key=lambda s: s.get("date") or "")


def _load_trainingsplan_state() -> dict:
    if not os.path.exists(TRAININGSPLAN_STATE_FILE):
        return {"last_known_phase": None, "last_trigger_dates": {}}
    try:
        with open(TRAININGSPLAN_STATE_FILE) as f:
            return json.load(f) or {"last_known_phase": None, "last_trigger_dates": {}}
    except Exception as e:
        print(f"[trainingsplan] Status nicht lesbar, starte neu: {e}")
        return {"last_known_phase": None, "last_trigger_dates": {}}


def _save_trainingsplan_state(state: dict):
    try:
        with open(TRAININGSPLAN_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[trainingsplan] Status konnte nicht geschrieben werden: {e}")


def _days_since(date_str, today: datetime.date):
    if not date_str:
        return None
    try:
        return (today - datetime.date.fromisoformat(date_str)).days
    except ValueError:
        return None


def check_trainingsplan_trigger(today_date: datetime.date, phase: str, history: list):
    """Prueft, ob eine Gemini-Kommentierung der Trainingsplaene (Dashboard-Tab
    "Trainingsplaene") gerechtfertigt ist - bewusst NICHT bei jedem Sync,
    siehe claude/status-und-plan.md ("Trigger-Kriterien fuer automatische
    Gemini-Kommentierung", von Alex am 09.09.2026 so gewuenscht). Zwei
    Trigger-Arten:

    1. Phasenwechsel (kalenderbasiert, einmalig je Phasenuebergang) - die
       Basis-Kadenz, faellt mit den echten Mesozyklus-Grenzen der
       Periodisierung zusammen (PHASES oben, alle ~8-13 Wochen).
    2. Datenbasiert, mit Cooldown (TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS),
       damit ein anhaltender Zustand nicht bei jedem einzelnen Sync erneut
       ausloest:
       - Training Readiness im 14-Tage-Schnitt unter
         TRAININGSPLAN_READINESS_LOW_THRESHOLD (moegliches Uebertraining).
       - VO2max im 7-Tage-Schnitt stagniert/sinkt gegenueber dem 7-Tage-
         Schnitt vor ca. 4 Wochen (Reiz greift nicht mehr).

    Zwei in status-und-plan.md ebenfalls dokumentierte Trigger (deutlicher
    Benchmark-Sprung, konsistente Planabweichung ueber mehrere Wochen) sind
    hier bewusst NICHT implementiert: dafuer fehlen aktuell verlaessliche
    Daten (die Zielzeit-Benchmarks liegen nur als manuell gepflegte HA-
    input_number-Helper vor, auf die dieses Add-on keinen Lesezugriff hat;
    eine historische Wochenvolumen-Reihe wird bisher nicht persistiert) -
    lieber ehrlich zwei Trigger auslassen als sie auf duennem Datenboden zu
    erraten.

    Gibt (trigger_key, klartext_grund) oder (None, None) zurueck; speichert
    bei jedem erkannten Ausloeser sowie beim allerersten Aufruf ueberhaupt
    (Phase nur merken) den aktualisierten Zustand."""
    state = _load_trainingsplan_state()
    last_dates = state.get("last_trigger_dates") or {}

    if state.get("last_known_phase") and state.get("last_known_phase") != phase:
        old_phase = state["last_known_phase"]
        state["last_known_phase"] = phase
        last_dates["phase_change"] = today_date.isoformat()
        state["last_trigger_dates"] = last_dates
        _save_trainingsplan_state(state)
        return "phase_change", f"Phasenwechsel von '{old_phase}' zu '{phase}'"
    if not state.get("last_known_phase"):
        # Erster Sync ueberhaupt (oder erster nach diesem Feature-Update):
        # Phase nur merken, nicht sofort als "Wechsel" werten.
        state["last_known_phase"] = phase
        _save_trainingsplan_state(state)

    readiness_14d = _history_avg(history, "readiness", 0, 13, today=today_date)
    days_since_readiness = _days_since(last_dates.get("readiness_low"), today_date)
    if (readiness_14d is not None and readiness_14d < TRAININGSPLAN_READINESS_LOW_THRESHOLD
            and len(history) >= 14
            and (days_since_readiness is None
                 or days_since_readiness >= TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS)):
        last_dates["readiness_low"] = today_date.isoformat()
        state["last_trigger_dates"] = last_dates
        _save_trainingsplan_state(state)
        return "readiness_low", (
            f"Training Readiness im 14-Tage-Schnitt bei {readiness_14d}% "
            f"(unter der Schwelle von {TRAININGSPLAN_READINESS_LOW_THRESHOLD}%)"
        )

    vo2max_recent = _history_avg(history, "vo2max", 0, 6, today=today_date)
    vo2max_month_ago = _history_avg(history, "vo2max", 21, 27, today=today_date)
    days_since_vo2max = _days_since(last_dates.get("vo2max_stagnation"), today_date)
    if (vo2max_recent is not None and vo2max_month_ago is not None
            and vo2max_recent <= vo2max_month_ago + TRAININGSPLAN_VO2MAX_STAGNATION_TOLERANCE
            and (days_since_vo2max is None
                 or days_since_vo2max >= TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS)):
        last_dates["vo2max_stagnation"] = today_date.isoformat()
        state["last_trigger_dates"] = last_dates
        _save_trainingsplan_state(state)
        return "vo2max_stagnation", (
            f"VO2max stagniert/sinkt: {vo2max_recent} ml/kg/min (7-Tage-Schnitt aktuell) vs. "
            f"{vo2max_month_ago} ml/kg/min (7-Tage-Schnitt vor ca. 4 Wochen)"
        )

    return None, None


def build_weekly_summary(wellness: dict, history: list) -> dict:
    """Stellt die Kennzahlen des Wochenreports zusammen (laufende Woche vs. Vorwoche).

    Bewusst eine flache Struktur aus Zahlen: so laesst sie sich 1:1 als
    MQTT-Attribute mitschicken und im Dashboard direkt anzeigen."""
    cur = wellness.get("weekly_volumes") or {}
    prev = wellness.get("weekly_volumes_prev") or {}
    total_min = round(sum(cur.get(k, 0) or 0 for k in
                          ("swim_min", "bike_min", "run_min", "strength_min")))
    total_min_prev = round(sum(prev.get(k, 0) or 0 for k in
                               ("swim_min", "bike_min", "run_min", "strength_min")))

    # Datumsbereiche der beiden Fenster als Klartext - die Tabelle im Dashboard nannte
    # diese Fenster bisher "Diese Woche"/"Vorwoche", was auf den Kopf zeigt, wenn der
    # Report (wie vorgesehen) montags ueber die gerade abgeschlossene Woche laeuft:
    # dann ist "diese Woche" fuer den Betrachter eigentlich schon "letzte Woche". Ein
    # konkretes Datum statt einer relativen Woche-Bezeichnung raeumt die Verwirrung aus,
    # unabhaengig davon, an welchem Wochentag der Report erzeugt wird (auch /weekly
    # kann jederzeit manuell ausgeloest werden, nicht nur montags).
    
    try:
        today = datetime.date.fromisoformat(wellness.get("date")) if wellness.get("date") else datetime.date.today()
    except ValueError:
        today = datetime.date.today()
    # Kalenderwoche Mo-So statt rollierender 7-Tage-Fenster (dsm = Tage seit Montag).
    dsm = today.weekday()
    period_from = today - datetime.timedelta(days=dsm)
    period_to = period_from + datetime.timedelta(days=6)
    period_prev_from = period_from - datetime.timedelta(days=7)
    period_prev_to = period_from - datetime.timedelta(days=1)

    summary = {
        "period_label": f"{_fmt_dm(period_from)}–{_fmt_dm(period_to)}",
        "period_prev_label": f"{_fmt_dm(period_prev_from)}–{_fmt_dm(period_prev_to)}",
        "swim_km": cur.get("swim_km"), "bike_km": cur.get("bike_km"), "run_km": cur.get("run_km"),
        "swim_km_prev": prev.get("swim_km"), "bike_km_prev": prev.get("bike_km"),
        "run_km_prev": prev.get("run_km"),
        "swim_sessions": cur.get("swim_sessions"), "bike_sessions": cur.get("bike_sessions"),
        "run_sessions": cur.get("run_sessions"), "strength_sessions": cur.get("strength_sessions"),
        "swim_sessions_prev": prev.get("swim_sessions"),
        "bike_sessions_prev": prev.get("bike_sessions"),
        "run_sessions_prev": prev.get("run_sessions"),
        "strength_sessions_prev": prev.get("strength_sessions"),
        "total_min": total_min, "total_min_prev": total_min_prev,
        "volume_change_pct": _pct_change(total_min, total_min_prev),
        "resting_hr_avg": _history_avg(history, "resting_hr", 0, dsm),
        "resting_hr_avg_prev": _history_avg(history, "resting_hr", dsm + 1, dsm + 7),
        "hrv_avg": _history_avg(history, "hrv_avg", 0, dsm),
        "hrv_avg_prev": _history_avg(history, "hrv_avg", dsm + 1, dsm + 7),
        "sleep_hours_avg": _history_avg(history, "sleep_hours", 0, dsm),
        "sleep_hours_avg_prev": _history_avg(history, "sleep_hours", dsm + 1, dsm + 7),
        "readiness_avg": _history_avg(history, "readiness", 0, dsm),
        "readiness_avg_prev": _history_avg(history, "readiness", dsm + 1, dsm + 7),
        # Wie viele Tage die Historie ueberhaupt schon abdeckt - der Report soll
        # nicht so tun, als waeren Trends belastbar, wenn erst 2 Tage erfasst sind.
        "history_days": len(history or []),
    }
    return summary


def do_weekly_report(wellness: dict = None, history: list = None) -> str:
    """Erzeugt den KI-Wochenreport und published ihn nach Home Assistant."""
    if wellness is None:
        if not os.path.exists(DATA_FILE):
            print("[weekly] noch keine Sync-Daten vorhanden")
            return None
        with open(DATA_FILE) as f:
            wellness = json.load(f)
    if history is None:
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    history = json.load(f) or []
            except Exception as e:
                print(f"[weekly] Historie nicht lesbar: {e}")

    summary = build_weekly_summary(wellness, history)
    try:
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
        text = generate_weekly_report(wellness, summary)
    except Exception as e:
        print(f"[weekly] Wochenreport fehlgeschlagen: {e}")
        text = "Wochenreport aktuell nicht verfuegbar - Kennzahlen siehe Attribute."
    publish_weekly_report(text, summary)
    return text


def do_sync(force: bool = False, also_weekly: bool = False):
    """Holt aktuelle Garmin-Daten, speichert sie lokal und published sie
    (inkl. KI-Coaching-Notiz) nach MQTT/Home Assistant.

    Wird sowohl vom manuellen /sync-Aufruf als auch vom taeglichen
    Hintergrund-Scheduler genutzt, damit beide Wege garantiert
    tatsaechlich bei Home Assistant ankommen. `force=True` umgeht die
    Mindestpause (z.B. fuer gezieltes Testen ueber /sync?force=1).
    `also_weekly=True` erzeugt zusaetzlich unabhaengig vom Wochentag den
    Wochenreport (siehe "Jetzt synchronisieren"-Button/Handler unten) -
    normalerweise laeuft der Wochenreport nur montags automatisch mit.
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
        today_date = datetime.date.today()
        today = today_date.isoformat()

        wellness = {
            "date": today,
            # bereits vorhanden (v0.3.0)
            "resting_hr": client.get_rhr_day(today),
            "steps": client.get_steps_data(today),
            "training_readiness": client.get_training_readiness(today),

            # Erholung / Belastung - fuer Uebertrainings-Fruehwarnung
            "training_status": _safe_fetch("training_status", lambda: client.get_training_status(today)),
            "hrv": _safe_fetch("hrv", lambda: client.get_hrv_data(today)),
            "body_battery": _safe_fetch("body_battery", lambda: client.get_body_battery(today, today)),
            "stress": _safe_fetch("stress", lambda: client.get_all_day_stress(today)),
            "respiration": _safe_fetch("respiration", lambda: client.get_respiration_data(today)),
            "spo2": _safe_fetch("spo2", lambda: client.get_spo2_data(today)),
            "sleep": _safe_fetch("sleep", lambda: client.get_sleep_data(today)),

            # Fitness-Fortschritt - fuer die Ironman-70.3-Vorbereitung
            "max_metrics": _fetch_max_metrics(client, today_date),  # VO2max (14-Tage-Fenster)

            # Rennvorbereitung / Periodisierung (siehe claude/status-und-plan.md)
            "days_to_race": days_to_race(today_date),
            "phase": current_phase(today_date),
        }

        recent_activities = _safe_fetch("activities", lambda: client.get_activities(0, 50)) or []
        # Kalenderwoche Mo-So statt rollierender 7-Tage-Fenster: Montag 00:00 dieser
        # Woche bis (exklusiv) naechsten Montag; Vorwoche entsprechend 7 Tage davor.
        week_start = datetime.datetime.combine(
            today_date - datetime.timedelta(days=today_date.weekday()), datetime.time.min
        )
        week_end = week_start + datetime.timedelta(days=7)
        prev_week_start = week_start - datetime.timedelta(days=7)
        prev_week_end = week_start
        wellness["weekly_volumes"] = _volumes_in_window(recent_activities, week_start, week_end)
        # Vorwoche aus denselben Aktivitaetsdaten - Basis fuer den Soll/Ist-Vergleich
        # im Wochenreport, ohne einen einzigen zusaetzlichen Garmin-Request.
        wellness["weekly_volumes_prev"] = _volumes_in_window(recent_activities, prev_week_start, prev_week_end)
        # Einzelne Uebungen/Saetze je Kraft-Einheit dieser Woche (Best-Effort ueber
        # die Original-FIT-Datei, siehe fit_exercises.py) - ueber _safe_fetch, damit
        # ein Problem hier (z.B. neues Garmin-Dateiformat) nie den ganzen Sync killt.
        wellness["strength_exercises"] = _safe_fetch(
            "strength_exercises", lambda: _update_strength_exercises(client, recent_activities)
        ) or []

        # Diese beiden aendern sich nur langsam (Tage/Wochen) -> nur einmal
        # woechentlich (montags) abrufen, um zusaetzliche Garmin-Calls und
        # damit das Rate-Limit-Risiko nicht unnoetig zu erhoehen.
        if today_date.weekday() == 0:  # Montag
            # Einzeltag-Abfrage: liefert "overallScore" direkt. Die frueher genutzte
            # Zeitraum-Variante liefert stattdessen avg/max/groupMap - deren Feld
            # "overallScore" gibt es dort gar nicht, der Sensor konnte also nie
            # einen Wert bekommen.
            wellness["endurance_score"] = _safe_fetch(
                "endurance_score", lambda: client.get_endurance_score(today)
            )
            wellness["race_predictions"] = _safe_fetch("race_predictions", client.get_race_predictions)

        with open(DATA_FILE, "w") as f:
            json.dump(wellness, f, indent=2, ensure_ascii=False, default=str)

        publish_discovery()

        # Messwerte SOFORT publizieren - vor der KI-Anfrage. Die Gemini-Antwort kann
        # je nach Modell deutlich ueber eine Minute dauern oder ganz fehlschlagen; die
        # Garmin-Daten sollen davon nicht aufgehalten oder mitgerissen werden.
        publish_state(wellness)
        publish_sync_status(ok=True)
        publish_strength_exercises(wellness["strength_exercises"])

        # Annehmen/Ablehnen-Zustand der Gym-Kritik-Vorschlaege (Dashboard-Tab
        # "Vorschlaege", siehe suggestions.py) mit der aktuellen Punkteliste
        # abgleichen - VOR dem Trainingsplan-Kommentar-Block unten, damit
        # generate_trainingsplan_kommentar() dort bereits den aktuellen Status kennt
        # (angenommene/abgelehnte Punkte werden im Prompt ausgeblendet bzw. markiert,
        # siehe ai_coach._render_gym_kritik). Guenstig genug, um bei jedem Sync zu
        # laufen (reine Dict-/Datei-Operation, kein Gemini-Aufruf).
        suggestions.sync_suggestions("gym_kritik", TRAININGSPLAN_GYM_KRITIK)

        # Eigener, auf Krafttraining fokussierter Coaching-Tipp (siehe
        # ai_coach.generate_gym_coaching_note) - getrennt vom allgemeinen
        # Tages-Tipp unten, damit er im eigenen Gym-Dashboard-Tab landet und
        # nicht mit der Erholungs-/Tagesplanungs-Perspektive vermischt wird.
        try:
            if not os.environ.get("GEMINI_API_KEY"):
                raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
            if not any((s.get("exercises") or []) for s in wellness["strength_exercises"]):
                gym_note = "Noch keine verwertbaren Kraft-Uebungsdaten der letzten 7 Tage fuer einen Gym-Tipp."
            else:
                gym_note = generate_gym_coaching_note(wellness["strength_exercises"])
        except Exception as e:
            print(f"[ai_coach] Gym-Coaching-Tipp fehlgeschlagen: {e}")
            gym_note = "Gym-Coaching-Tipp aktuell nicht verfuegbar - Uebungsdaten wurden trotzdem synchronisiert."
        publish_gym_coaching_note(gym_note)

        try:
            if not os.environ.get("GEMINI_API_KEY"):
                raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
            note = generate_coaching_note(wellness)
        except Exception as e:
            # Technischen Fehler nur ins Log schreiben, nicht in die Notiz, die
            # im Dashboard landet - dort sollen keine Exception-Details/Keys auftauchen.
            print(f"[ai_coach] Coaching-Notiz fehlgeschlagen: {e}")
            note = "Coaching-Tipp aktuell nicht verfuegbar - Werte wurden trotzdem synchronisiert."
        publish_coaching_note(note)

        history = _update_history(wellness)

        # Trainingsplan-Kommentierung (Tab "Trainingsplaene") - anders als die
        # anderen Coaching-Texte NICHT bei jedem Sync, sondern nur wenn ein
        # konkreter Ausloeser vorliegt (siehe check_trainingsplan_trigger).
        # Kein Trigger -> Funktion wird gar nicht erst aufgerufen, der zuletzt
        # publizierte (retained) Kommentar bleibt im Dashboard einfach stehen.
        try:
            trigger_key, trigger_detail = check_trainingsplan_trigger(
                today_date, wellness["phase"], history
            )
            if trigger_key:
                if not os.environ.get("GEMINI_API_KEY"):
                    raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
                # Aktueller Annehmen/Ablehnen-Stand als Kontext fuer den Prompt (siehe
                # suggestions.py): Gym-Status blendet abgelehnte Punkte aus, decided_context
                # nennt bereits entschiedene fruehere Einzelvorschlaege aus DIESEM Kanal, damit
                # Gemini angenommene nicht erneut vorschlaegt und abgelehnte nicht wiederholt.
                gym_status = {
                    sid: rec["status"] for sid, rec in suggestions.by_source("gym_kritik").items()
                }
                decided_context = suggestions.context_for_prompt("trainingsplan_kommentar")
                plan_note, plan_vorschlaege = generate_trainingsplan_kommentar(
                    trigger_key, trigger_detail, wellness, history,
                    gym_status=gym_status, decided_context=decided_context,
                )
                suggestions.sync_suggestions("trainingsplan_kommentar", plan_vorschlaege)
                publish_trainingsplan_kommentar(plan_note, trigger_key, trigger_detail)
                print(f"[trainingsplan] Kommentar publiziert (Ausloeser: {trigger_key}, "
                      f"{len(plan_vorschlaege)} Einzelvorschlag/-vorschlaege)")
        except Exception as e:
            # Bewusst KEIN publish_trainingsplan_kommentar(...) mit Fehlertext:
            # anders als bei den anderen Coaching-Texten soll bei einem Fehler
            # hier der zuletzt erfolgreich generierte Kommentar (falls
            # vorhanden) im Dashboard stehen bleiben statt durch eine
            # Fehlermeldung ersetzt zu werden - der naechste ausgeloeste Sync
            # versucht es erneut.
            print(f"[trainingsplan] Kommentar fehlgeschlagen: {e}")

        # Aktuellen Annehmen/Ablehnen-Gesamtzustand publizieren (Dashboard-Tab
        # "Vorschlaege") - unabhaengig davon, ob oben ein Trainingsplan-Kommentar-
        # Trigger ausgeloest hat: die Gym-Kritik wurde weiter oben in jedem Fall
        # abgeglichen, und selbst ohne neuen Trigger soll das Dashboard den zuletzt
        # bekannten Stand (inkl. frueherer Annahme-/Ablehnungs-Entscheidungen) zeigen.
        publish_vorschlaege(suggestions.all_suggestions())

        # Wochenreport montags automatisch (Rueckblick auf die abgeschlossene Woche);
        # jederzeit manuell ueber /weekly ausloesbar, oder ueber also_weekly=True
        # gebuendelt mit diesem Sync (siehe "Jetzt synchronisieren"-Button).
        if today_date.weekday() == 0 or also_weekly:
            do_weekly_report(wellness, history)
        return wellness
    except Exception as e:
        print(f"[sync] Sync fehlgeschlagen: {e}")
        publish_sync_status(ok=False, detail=str(e))
        return None


def _handle_sync_button_press():
    """Wird ueber MQTT ausgeloest (Button-Entity "Garmin AI Coach Jetzt
    synchronisieren" aus ha_publish.publish_discovery(), Topic
    garmin_ai_coach/sync_now/set) statt wie bisher ueber einen Dashboard-Klick
    auf eine fest verdrahtete Ingress-URL. Diese URL scheiterte mit HTTP 401,
    sobald der Browser keine gueltige (kurzlebige) Ingress-Session mehr hatte -
    z.B. weil der Tap-Action-Typ "url" den Link in einem neuen Tab oeffnet, der
    nie eine Ingress-Session aufgebaut hat (siehe claude/status-und-plan.md,
    "Dashboard-Ingress-URL fragil"). Ein MQTT-Button ist eine normale
    HA-Entity, die ueber einen ganz normalen Service-Call (mqtt.publish)
    ausgeloest wird - unabhaengig von Ingress-Sessions.

    Laeuft in einem eigenen Thread, damit der MQTT-Netzwerk-Thread (der diesen
    Callback aufruft) nicht blockiert wird - ein Sync inkl. Gemini-Aufrufen
    kann mehrere zehn Sekunden dauern. Loest bewusst IMMER auch den
    Wochenreport aus (also_weekly=True, siehe do_sync) - Alex' ausdruecklicher
    Wunsch, damit ein Klick auf "Jetzt synchronisieren" beides gleichzeitig
    anstoesst, unabhaengig vom Wochentag."""
    def _run():
        print("[mqtt] Sync-Button gedrueckt - starte Sync + Wochenreport")
        try:
            do_sync(force=True, also_weekly=True)
        except Exception as e:
            print(f"[mqtt] Sync ueber Button fehlgeschlagen: {e}")
    threading.Thread(target=_run, daemon=True).start()


set_sync_button_callback(_handle_sync_button_press)


def _handle_vorschlag_accept(suggestion_id: str):
    """Wird ueber MQTT ausgeloest (Button "Garmin Vorschlag Annehmen", Topic
    garmin_ai_coach/vorschlag_annehmen/set), wirkt auf den zuletzt im Dropdown
    "Garmin Vorschlag Auswahl" ausgewaehlten Vorschlag (siehe ha_publish.
    _on_message). Setzt dessen Status auf "accepted" (suggestions.py) - wird
    kuenftigen Trainingsplan-Kommentar-Prompts als bereits angenommen/
    umgesetzt mitgegeben, siehe suggestions.context_for_prompt und
    ai_coach._render_gym_kritik. Publiziert danach sofort den neuen
    Gesamtzustand, damit das Dashboard nicht bis zum naechsten Sync auf die
    Aktualisierung warten muss. Schnelle reine Datei-/MQTT-Operation, deshalb
    (anders als der Sync-Button) ohne eigenen Thread."""
    try:
        if suggestions.set_status(suggestion_id, suggestions.STATUS_ACCEPTED):
            print(f"[vorschlaege] '{suggestion_id}' angenommen")
        else:
            print(f"[vorschlaege] Annehmen fehlgeschlagen: id '{suggestion_id}' unbekannt "
                  "(veraltete Dashboard-Auswahl nach einem zwischenzeitlichen Sync?)")
        publish_vorschlaege(suggestions.all_suggestions())
    except Exception as e:
        print(f"[vorschlaege] Annehmen fehlgeschlagen: {e}")


def _handle_vorschlag_reject(suggestion_id: str):
    """Analog zu _handle_vorschlag_accept, aber fuer den "Garmin Vorschlag
    Ablehnen"-Button - setzt den Status auf "rejected". Der Vorschlag bleibt
    im Dashboard-Tab "Vorschlaege" unter "Abgelehnt" sichtbar und laesst sich
    dort jederzeit wieder auswaehlen und per erneutem Annehmen reaktivieren."""
    try:
        if suggestions.set_status(suggestion_id, suggestions.STATUS_REJECTED):
            print(f"[vorschlaege] '{suggestion_id}' abgelehnt")
        else:
            print(f"[vorschlaege] Ablehnen fehlgeschlagen: id '{suggestion_id}' unbekannt "
                  "(veraltete Dashboard-Auswahl nach einem zwischenzeitlichen Sync?)")
        publish_vorschlaege(suggestions.all_suggestions())
    except Exception as e:
        print(f"[vorschlaege] Ablehnen fehlgeschlagen: {e}")


set_vorschlag_callbacks(on_accept=_handle_vorschlag_accept, on_reject=_handle_vorschlag_reject)


def _load_latest_wellness_and_history():
    """Laedt die zuletzt gespeicherten Sync-Daten + Tages-Historie von der
    Platte - gleiche Quelle/gleiches Muster wie do_weekly_report() ohne
    Parameter. Fuer den Chat (_handle_chat_question unten) gebraucht, damit
    eine Frage NICHT extra einen neuen Garmin-Sync ausloest (waere zu
    langsam/unnoetiges Rate-Limit-Risiko fuer eine reine Textfrage)."""
    wellness = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                wellness = json.load(f) or {}
        except Exception as e:
            print(f"[chat] Sync-Daten nicht lesbar: {e}")
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f) or []
        except Exception as e:
            print(f"[chat] Historie nicht lesbar: {e}")
    return wellness, history


def _handle_chat_question(question: str):
    """Wird ueber MQTT ausgeloest (text-Entity "Garmin Chat Frage", Topic
    garmin_ai_coach/chat_frage/set, siehe ha_publish.py). Ruft Gemini MIT dem
    aktuellen Trainingskontext auf (ai_coach.generate_chat_answer - Alex'
    ausdruecklicher Wunsch, damit z.B. "Wie war meine Woche?" ohne weitere
    Erklaerung funktioniert), haengt Frage+Antwort an den gespeicherten
    Verlauf an (chat.py) und published das Ergebnis sofort.

    Laeuft in einem eigenen Thread (wie _handle_sync_button_press) - der
    Gemini-Aufruf kann mehrere Sekunden bis über eine Minute dauern und darf
    den MQTT-Netzwerk-Thread nicht blockieren. Ein Fehler landet NICHT als
    Exception im Dashboard, sondern als ehrliche, kurze Fehlermeldung in der
    Antwort - der Verlauf bekommt trotzdem einen Eintrag, damit die gestellte
    Frage nicht spurlos verschwindet."""
    def _run():
        print(f"[mqtt] Chat-Frage wird beantwortet: {question[:80]!r}")
        try:
            wellness, history = _load_latest_wellness_and_history()
            chat_context = chat.context_for_prompt()
            if not os.environ.get("GEMINI_API_KEY"):
                raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
            answer = generate_chat_answer(question, wellness, history, chat_context)
        except Exception as e:
            print(f"[chat] Antwort fehlgeschlagen: {e}")
            answer = "Antwort aktuell nicht verfuegbar (Gemini-Fehler). Frag gern gleich nochmal."
        entries = chat.add_exchange(question, answer)
        publish_chat_history(entries)
    threading.Thread(target=_run, daemon=True).start()


set_chat_callback(_handle_chat_question)


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
    <p><a href="sync">Jetzt synchronisieren</a> &nbsp;|&nbsp; <a href="sync?force=1">Sync erzwingen</a> &nbsp;|&nbsp; <a href="sync?force=1&weekly=1">Sync + Wochenreport erzwingen</a> &nbsp;|&nbsp; <a href="weekly">Wochenreport erzeugen</a></p>
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
    do_sync(
        force=request.args.get("force") == "1",
        also_weekly=request.args.get("weekly") == "1",
    )
    return redirect(".")


@app.route("/weekly")
def weekly():
    """Wochenreport manuell ausloesen (laeuft sonst automatisch montags).
    Nutzt die zuletzt gesyncten Daten, loest also KEINE Garmin-Abfrage aus."""
    if not is_logged_in():
        return redirect(".")
    do_weekly_report()
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
