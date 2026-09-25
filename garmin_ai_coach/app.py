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
    publish_decoupling,
    publish_plan,
    publish_recommendation,
    publish_coach_status,
    publish_kraftwerte,
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
import plan
import recommendation
import progress
import suggestions
import chat
import decoupling

DATA_DIR = "/data"
TOKEN_DIR = os.path.join(DATA_DIR, "garmin_tokens")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
# Rollierende Tages-Historie für Wochentrends (Ruhepuls, HRV, Schlaf, Readiness).
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HISTORY_DAYS = 60
# Cache der per FIT-Datei extrahierten Kraft-Übungen je Aktivität (siehe
# fit_exercises.py) - dauerhaft, damit nicht bei jedem Sync erneut die
# Original-Datei jeder Kraft-Aktivität von Garmin geladen wird.
STRENGTH_FILE = os.path.join(DATA_DIR, "strength_exercises.json")
STRENGTH_CACHE_DAYS = 21
# Cache der HF-Pace-Kopplung (aerobe Entkopplung) je qualifizierender
# Lauf-Aktivität - siehe decoupling.py und claude/konzept-erweiterung-
# metriken-v0.16-plus.md, Abschnitt 1.3. Gleiches Muster wie STRENGTH_FILE.
DECOUPLING_FILE = os.path.join(DATA_DIR, "decoupling.json")
DECOUPLING_CACHE_DAYS = 60
# Zustand der Trainingsplan-Kommentierung (Tab "Trainingspläne", siehe
# check_trainingsplan_trigger unten) - welche Phase zuletzt bekannt war und
# wann welcher Trigger zuletzt ausgelöst hat, damit nicht jeder Sync erneut
# denselben Grund meldet, solange der Zustand anhält.
TRAININGSPLAN_STATE_FILE = os.path.join(DATA_DIR, "trainingsplan_state.json")
TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS = 21
TRAININGSPLAN_READINESS_LOW_THRESHOLD = 60
TRAININGSPLAN_VO2MAX_STAGNATION_TOLERANCE = 0.3
# Ab wieviel Prozent FTP-Anstieg (7-Tage-Schnitt jetzt vs. 7-Tage-Schnitt vor
# ca. 4-5 Wochen) der bisher shelvte "Benchmark-Sprung"-Trigger auslöst - siehe
# claude/status-und-plan.md und Konzept-Dokument Abschnitt 1.1.
TRAININGSPLAN_FTP_JUMP_THRESHOLD_PCT = 5
# Interferenzfenster Ausdauer-vor-Kraft (AMPK/mTOR) - 3h, nicht die ursprünglich
# kursierenden 6h (siehe Wojtaszewski et al. 2000 / GSSI SSE #136, im
# Konzept-Dokument Abschnitt 3 sowie wissenschaftliche-quellen-
# trainingsgrundlagen.md dokumentiert). Bewusst nur diese Richtung, siehe
# _check_endurance_before_strength_interference().
INTERFERENCE_WINDOW_HOURS = 3
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TOKEN_DIR, exist_ok=True)
os.environ["GARMINTOKENS"] = TOKEN_DIR

def _parse_sync_hours(raw: str) -> list:
    """Parst die kommagetrennte Add-on-Option "sync_hours" (z. B. "6,12,18,20") zu einer
    sortierten Liste eindeutiger Stunden (0-23, lokale Zeit des Containers). Einzelne
    ungültige/leere Einträge werden übersprungen statt den Start abzubrechen (gleiches
    Verteidigungsprinzip wie beim Rest des Add-ons); bleibt am Ende nichts Gültiges übrig,
    wird auf 6 Uhr zurückgefallen."""
    hours = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hour = int(part)
        except ValueError:
            print(f"[scheduler] Ungültiger Eintrag in sync_hours ignoriert: {part!r}")
            continue
        if 0 <= hour <= 23 and hour not in hours:
            hours.append(hour)
        else:
            print(f"[scheduler] Stunde ausserhalb 0-23 in sync_hours ignoriert: {part!r}")
    return sorted(hours) or [6]


# Stunden (0-23, lokale Zeit des Containers), zu denen automatisch synchronisiert wird -
# mehrere pro Tag möglich. Wird von run.sh aus der Add-on-Option "sync_hours" befüllt
# (kommagetrennt, z. B. "6,12,18,20"; Default hier deckt sich mit dem Default in config.yaml).
# Seit v0.18.0 Default "6,20" (Review-Punkt 27): Erholungswerte stehen morgens
# fest, neue Aktivitäten kommen abends dazu; weitere Syncs bringen kaum Neues,
# kosten aber Aufrufe an Garmins inoffiziellen Login und Gemini-Kontingent.
SYNC_HOURS = _parse_sync_hours(os.environ.get("SYNC_HOURS", "6,20"))
RACE_DATE = os.environ.get("RACE_DATE", "2027-08-29")
RACE_DATE_OBJ = plan.parse_race_date(RACE_DATE)

# Periodisierung: seit v0.18.0 in plan.py (einzige Quelle, Taper jetzt 14 Tage).

app = Flask(__name__)


def is_logged_in():
    return len(os.listdir(TOKEN_DIR)) > 0


def get_client():
    from garminconnect import Garmin
    client = Garmin()
    client.login(TOKEN_DIR)
    return client


def current_phase(today: datetime.date) -> str:
    return plan.current_phase(today, RACE_DATE_OBJ)


def days_to_race(today: datetime.date) -> int:
    return (RACE_DATE_OBJ - today).days


# Garmin sperrt Konten zeitweise nach zu vielen Login-Versuchen in kurzer Zeit
# (das war vermutlich die Ursache des vorherigen "Garmin-Sperre"-Ausfalls).
# do_sync() loggt sich bei jedem Aufruf neu ein, daher hier eine Mindestpause
# zwischen zwei Versuchen - auch für den manuellen "Jetzt synchronisieren"-Button.
MIN_SYNC_INTERVAL = datetime.timedelta(minutes=15)
_last_sync_attempt = None


def _safe_fetch(label, fn):
    """Ruft eine einzelne Garmin-Metrik ab; loggt Fehler statt den ganzen Sync
    abzubrechen. Jede zusätzliche Metrik ist ein eigener HTTPS-Call an Garmin,
    daher soll ein einzelner fehlschlagender Endpoint (z.B. weil ein Gerät
    einen Sensor nicht unterstützt) nicht den kompletten Sync killen."""
    try:
        return fn()
    except Exception as e:
        print(f"[sync] Metrik '{label}' fehlgeschlagen: {e}")
        return None

def _volumes_in_window(activities, window_start, window_end):
    """Summiert Aktivitäten in einem Zeitfenster je Disziplin (km/Minuten).

    window_start/window_end sind konkrete datetime-Grenzen (start inklusiv,
    end exklusiv) - so lassen sich echte Kalenderwochen (Mo-So) abbilden statt
    nur rollierender 7-Tage-Fenster ab "jetzt"."""
    totals = {"swim_km": 0.0, "bike_km": 0.0, "run_km": 0.0,
              "swim_min": 0.0, "bike_min": 0.0, "run_min": 0.0, "strength_min": 0.0,
              "swim_sessions": 0, "bike_sessions": 0, "run_sessions": 0,
              "strength_sessions": 0,
              # Seit v0.18.0 (Review-Punkt 18): Minuten je HF-Zonenbereich über alle
              # Ausdauereinheiten - statt nur Einheiten zu zählen.
              "zone_low_min": 0.0, "zone_mid_min": 0.0, "zone_high_min": 0.0,
              "zone_sessions": 0}
    if not activities:
        return _finish_totals(totals)
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
            is_endurance = ("swim" in type_key or "run" in type_key or
                            (("bik" in type_key or "cycl" in type_key or "ride" in type_key) and distance_km > 0))
            if is_endurance:
                zones = decoupling.zone_seconds(act)
                if zones:
                    totals["zone_low_min"] += (zones[0] + zones[1]) / 60.0
                    totals["zone_mid_min"] += zones[2] / 60.0
                    totals["zone_high_min"] += (zones[3] + zones[4]) / 60.0
                    totals["zone_sessions"] += 1
            if "swim" in type_key:
                totals["swim_km"] += distance_km
                totals["swim_min"] += duration_min
                totals["swim_sessions"] += 1
            elif "bik" in type_key or "cycl" in type_key or "ride" in type_key:
                # Alex fährt auf Zwift (das lädt die Einheit inkl. echter Distanz
                # nach Garmin hoch) und lässt parallel zur Herzfrequenzmessung eine
                # zweite Aktivität auf der Uhr mitlaufen, die er selbst als "Indoor
                # Radfahren" ohne km einordnet - dieselbe Fahrt würde sonst doppelt
                # als zwei Rad-Einheiten gezählt (Sessions UND Minuten). Nur
                # Aktivitäten mit echter Distanz > 0 zählen als Rad-Einheit; die
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
            print(f"[sync] Aktivität konnte nicht ausgewertet werden: {e}")
    return _finish_totals(totals)


def _finish_totals(totals: dict) -> dict:
    total_zone = totals["zone_low_min"] + totals["zone_mid_min"] + totals["zone_high_min"]
    totals["zone_total_min"] = total_zone
    for key in ("low", "mid", "high"):
        totals[f"zone_{key}_pct"] = round(totals[f"zone_{key}_min"] / total_zone * 100) if total_zone else None
    return {k: (round(v, 1) if isinstance(v, float) else v) for k, v in totals.items()}

def _fetch_max_metrics(client, today_date):
    """Holt VO2max über ein 14-Tage-Fenster statt nur für heute.

    Garmin berechnet VO2max nur nach qualifizierenden Einheiten, der Tageseintrag
    für 'heute' ist deshalb meistens leer - genau daran lag es, dass der VO2max-
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
    """Führt eine rollierende Tages-Historie in /data/history.json.

    Damit kann der Wochenreport Trends (Ruhepuls, HRV, Schlaf, Readiness) über
    mehrere Tage bilden, ohne für jeden Tag erneut bei Garmin anzufragen."""
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
        # Seit v0.12.0: für den VO2max-Stagnations-Trigger der
        # Trainingsplan-Kommentierung (siehe check_trainingsplan_trigger).
        # Ältere Historieneinträge haben dieses Feld noch nicht - das ist
        # unproblematisch, _history_avg() überspringt fehlende Werte einfach.
        "vo2max": metrics["vo2max"],
        # Seit v0.16.0: für den FTP-"Benchmark-Sprung"-Trigger (siehe
        # check_trainingsplan_trigger) sowie den Verlauf im Dashboard-Tab
        # "Verlauf". Ältere Einträge ohne dieses Feld werden wie bei vo2max
        # einfach übersprungen.
        "ftp": metrics.get("ftp"),
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


def _load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f) or []
    except Exception as e:
        print(f"[history] nicht lesbar: {e}")
        return []


def _publish_coach_status():
    """Coach-Status-Sensor (Review-Punkte 1 und 21) - eigener Sensor statt
    sync_status, damit ein KI-Ausfall nicht hinter "ok" verschwindet."""
    try:
        state = progress.coach_status()
        c = state.get("coaching") or {}
        publish_coach_status(progress.overall_status(state), {
            "last_success": c.get("last_success"),
            "last_failure": c.get("last_failure"),
            "consecutive_failures": c.get("consecutive_failures") or 0,
            "last_error": c.get("last_error"),
            "last_model": c.get("last_model"),
            "privacy_mode": os.environ.get("AI_PRIVACY_MODE") or "reduziert",
            "details": {k: {kk: vv for kk, vv in v.items() if kk != "last_text"}
                        for k, v in state.items() if isinstance(v, dict)},
        })
    except Exception as e:
        print(f"[coach_status] konnte nicht publiziert werden: {e}")


def _history_avg(history, key, offset_from: int, offset_to: int, today=None):
    """Mittelwert eines Feldes über Tage mit Abstand offset_from..offset_to zu heute."""
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
    """Prozentuale Veränderung; None wenn die Vorwoche keine Basis hergibt."""
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
    """Speichert den Übungs-Cache, begrenzt auf STRENGTH_CACHE_DAYS Tage
    (analog zu HISTORY_DAYS bei der Wellness-Historie), damit die Datei nicht
    unbegrenzt wächst."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=STRENGTH_CACHE_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if (v.get("date") or "") >= cutoff}
    try:
        with open(STRENGTH_FILE, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[strength] Cache konnte nicht geschrieben werden: {e}")
    return cache


def _is_broken_strength_entry(entry: dict) -> bool:
    """Erkennt Cache-Einträge aus der fehlgeschlagenen v0.10.0-FIT-Extraktion
    (leere Übungsliste oder nur der Codename-Platzhalter „Übung (Code ...)"),
    damit sie nach dem v0.10.1-Fix (exerciseSets-API statt eigenem FIT-Parsing)
    automatisch einmalig neu abgerufen werden, statt dauerhaft als kaputter
    Eintrag im Cache hängen zu bleiben (siehe claude/status-und-plan.md,
    Abschnitt v0.10.1 - live bestätigt: 2 von 4 Kraft-Einheiten des ersten
    echten Syncs blieben unter v0.10.0 leer bzw. nur mit Codename-Platzhalter)."""
    exercises = entry.get("exercises") or []
    if not exercises:
        return True
    return any(
        str((ex or {}).get("exercise", "")).startswith("Übung (Code")
        for ex in exercises
    )


def _update_strength_exercises(client, activities: list) -> list:
    """Lädt für Kraft-Aktivitäten der laufenden Woche, die noch nicht im
    Cache stehen (oder deren Cache-Eintrag als fehlgeschlagen erkannt wurde,
    siehe _is_broken_strength_entry), die Übungsdaten über Garmins
    exerciseSets-API (siehe fit_exercises.py) - die normale Aktivitätenliste
    liefert dafür nur Aggregatwerte (total_sets/total_reps/total_volume),
    keine Aufschlüsselung je Übung. Gibt die Sessions der laufenden Woche
    zurück (für Wochenreport/Dashboard), ältere bleiben nur im Cache."""
    cache = _load_strength_cache()
    broken_keys = [k for k, v in cache.items() if _is_broken_strength_entry(v)]
    for k in broken_keys:
        del cache[k]
    if broken_keys:
        print(f"[strength] {len(broken_keys)} kaputte Cache-Einträge (v0.10.0) verworfen, werden neu abgerufen: {broken_keys}")
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
            print(f"[strength] Aktivität konnte nicht verarbeitet werden: {e}")

    if changed:
        cache = _save_strength_cache(cache)

    window_date = window_start.date().isoformat()
    sessions = [v for v in cache.values() if (v.get("date") or "") >= window_date]
    return sorted(sessions, key=lambda s: s.get("date") or "")


def _load_decoupling_cache() -> dict:
    if not os.path.exists(DECOUPLING_FILE):
        return {}
    try:
        with open(DECOUPLING_FILE) as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[decoupling] Cache nicht lesbar, starte neu: {e}")
        return {}


def _save_decoupling_cache(cache: dict) -> dict:
    """Speichert den Entkopplungs-Cache, begrenzt auf DECOUPLING_CACHE_DAYS
    Tage (analog zu STRENGTH_CACHE_DAYS/HISTORY_DAYS)."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=DECOUPLING_CACHE_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if (v.get("date") or "") >= cutoff}
    try:
        with open(DECOUPLING_FILE, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[decoupling] Cache konnte nicht geschrieben werden: {e}")
    return cache


def _update_decoupling_cache(client, activities: list) -> list:
    """HF-Pace-/HF-Watt-Kopplung für qualifizierende Läufe und Zwift-Fahrten
    (seit v0.18.0: Filter über HF-Zonen, Aufwärmen abgeschnitten, Zeitreihe -
    siehe decoupling.py). Einträge der alten Methode werden verworfen."""
    cache = _load_decoupling_cache()
    old_keys = [k for k, v in cache.items() if v.get("method") != decoupling.METHOD_VERSION]
    for k in old_keys:
        del cache[k]
    changed = bool(old_keys)
    if old_keys:
        print(f"[decoupling] {len(old_keys)} Einträge der alten Methode verworfen, werden neu bewertet")

    for act in activities or []:
        try:
            activity_id = act.get("activityId")
            start_str = act.get("startTimeLocal")
            if activity_id is None or not start_str:
                continue
            key = str(activity_id)
            if key in cache:
                continue
            start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            if (datetime.datetime.now() - start_dt).days > DECOUPLING_CACHE_DAYS:
                continue
            sport = decoupling.classify(act)
            base = {"date": start_dt.date().isoformat(), "activity_name": act.get("activityName"),
                    "method": decoupling.METHOD_VERSION}
            if not sport:
                reason = decoupling.skip_reason(act)
                if reason is None:
                    continue  # keine Lauf-/Radaktivität - nicht merken, nicht anzeigen
                cache[key] = {**base, "empty": True, "reason": reason}
                changed = True
                continue
            result = {}
            try:
                details = client.get_activity_details(activity_id, maxchart=2000)
                result = decoupling.compute_from_details(details, sport)
            except Exception as e:
                print(f"[decoupling] Zeitreihe für {activity_id} nicht verfügbar: {e}")
            if not result and sport == "run":
                result = decoupling.compute_from_laps_trimmed(client.get_activity_splits(activity_id))
            if not result:
                cache[key] = {**base, "empty": True, "sport": sport,
                              "reason": "keine verwertbare Zeitreihe/Runden"}
            else:
                cache[key] = {**base, "sport": sport, **result,
                              "high_zone_share": round(decoupling.high_zone_share(act) * 100, 1)}
            changed = True
        except Exception as e:
            print(f"[decoupling] Aktivität konnte nicht verarbeitet werden: {e}")

    if changed:
        cache = _save_decoupling_cache(cache)

    sessions = [v for v in cache.values() if not v.get("empty")]
    return sorted(sessions, key=lambda s: s.get("date") or "")


def _decoupling_skipped() -> list:
    """Geprüfte, aber nicht gewertete Einheiten mit Grund (v0.18.1) - macht im
    Dashboard sichtbar, warum ein Lauf fehlt, und zeigt nebenbei, ob Garmin die
    HF-Zonenfelder überhaupt liefert."""
    cache = _load_decoupling_cache()
    skipped = [{"date": v.get("date"), "activity_name": v.get("activity_name"), "reason": v.get("reason")}
               for v in cache.values() if v.get("empty") and v.get("reason")]
    return sorted(skipped, key=lambda s: s.get("date") or "")[-10:]


def _check_endurance_before_strength_interference(activities: list, today_date: datetime.date) -> str:
    """Prüft, ob am Sync-Tag oder Vortag eine Ausdauer-Einheit (Schwimmen/Rad/
    Lauf) weniger als INTERFERENCE_WINDOW_HOURS vor einer Kraft-Einheit endete -
    siehe claude/konzept-erweiterung-metriken-v0.16-plus.md, Abschnitt 1.5.

    Bewusst NUR diese Richtung (Ausdauer -> Kraft), nicht umgekehrt: das
    AMPK/mTOR-Interferenzfenster (Wojtaszewski et al. 2000, GSSI SSE #136 -
    3h, nicht die ursprünglich kursierenden 6h) betrifft primär diese
    Reihenfolge; Kraft-vor-Ausdauer zeigt laut Murlasits et al. 2017 keinen
    vergleichbaren VO2max-Nachteil (bereits im Projekt dokumentierte
    Quellen, siehe wissenschaftliche-quellen-trainingsgrundlagen.md).

    Gibt einen fertigen Kontext-Satz zurück (oder '' wenn kein Fall
    vorliegt) - bewusst KEIN neuer Sensor/keine neue Kachel (Entscheidung vom
    11.09.2026, Konzept-Dokument Abschnitt 5): nur als Kontextsatz in
    bestehende Coaching-Prompts eingespeist, um keine neue ACWR-artige
    Überpräzisions-Kennzahl zu erzeugen. Betrachtet bewusst nur heute und
    gestern (der tägliche Sync läuft morgens, ein späterer Fund am
    Vortag ist zum nächsten Sync noch aktuell genug für den Gym-Tipp)."""
    by_day = {}
    for act in activities or []:
        start_str = act.get("startTimeLocal")
        if not start_str:
            continue
        try:
            start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        day = start_dt.date()
        if day > today_date or (today_date - day).days > 1:
            continue
        type_key = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
        duration_s = act.get("duration") or 0
        by_day.setdefault(day, []).append(
            (start_dt, duration_s, type_key, act.get("activityName") or "Einheit")
        )

    for day, day_activities in by_day.items():
        day_activities.sort(key=lambda a: a[0])
        for i in range(len(day_activities) - 1):
            start1, dur1, type1, name1 = day_activities[i]
            start2, _dur2, type2, name2 = day_activities[i + 1]
            is_endurance = any(k in type1 for k in ("swim", "bik", "cycl", "ride", "run"))
            is_strength = any(k in type2 for k in ("strength", "weight", "gym"))
            if not (is_endurance and is_strength):
                continue
            end1 = start1 + datetime.timedelta(seconds=dur1)
            gap_hours = (start2 - end1).total_seconds() / 3600
            if 0 <= gap_hours < INTERFERENCE_WINDOW_HOURS:
                return (
                    f"Hinweis Trainingsreihenfolge: Am {day.strftime('%d.%m.')} folgte "
                    f"'{name2}' nur {gap_hours:.1f}h nach '{name1}' (Ausdauer vor Kraft, "
                    f"unter {INTERFERENCE_WINDOW_HOURS}h). In diesem Fenster kann das "
                    "Interferenz-Signal (AMPK/mTOR) den Kraft-/Muskelaufbaureiz etwas "
                    "abschwächen - kein Problem als Einzelfall, aber bei wiederholtem "
                    "Muster ggf. größeren zeitlichen Abstand oder umgekehrte "
                    "Reihenfolge erwägen."
                )
    return ""


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
    """Prüft, ob eine Gemini-Kommentierung der Trainingspläne (Dashboard-Tab
    "Trainingspläne") gerechtfertigt ist - bewusst NICHT bei jedem Sync,
    siehe claude/status-und-plan.md ("Trigger-Kriterien für automatische
    Gemini-Kommentierung", von Alex am 09.09.2026 so gewünscht). Drei
    Trigger-Arten:

    1. Phasenwechsel (kalenderbasiert, einmalig je Phasenübergang) - die
       Basis-Kadenz, fällt mit den echten Mesozyklus-Grenzen der
       Periodisierung zusammen (PHASES oben, alle ~8-13 Wochen).
    2. Datenbasiert, mit Cooldown (TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS),
       damit ein anhaltender Zustand nicht bei jedem einzelnen Sync erneut
       auslöst:
       - Training Readiness im 14-Tage-Schnitt unter
         TRAININGSPLAN_READINESS_LOW_THRESHOLD (mögliches Übertraining).
       - VO2max im 7-Tage-Schnitt stagniert/sinkt gegenüber dem 7-Tage-
         Schnitt vor ca. 4 Wochen (Reiz greift nicht mehr).
       - Seit v0.16.0: FTP (Rad) im 7-Tage-Schnitt um mehr als
         TRAININGSPLAN_FTP_JUMP_THRESHOLD_PCT gegenüber vor ca. 4-5 Wochen
         gestiegen ("Benchmark-Sprung", siehe unten - vorher mangels
         Datenquelle nicht umsetzbar).

    Ein in status-und-plan.md ebenfalls dokumentierter Trigger (konsistente
    Planabweichung über mehrere Wochen) ist hier weiterhin bewusst NICHT
    implementiert: dafür fehlt weiterhin eine persistierte historische
    Wochenvolumen-Reihe - lieber ehrlich auslassen als auf dünnem
    Datenboden zu raten.

    Gibt (trigger_key, klartext_grund) oder (None, None) zurück; speichert
    bei jedem erkannten Auslöser sowie beim allerersten Aufruf überhaupt
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
        # Erster Sync überhaupt (oder erster nach diesem Feature-Update):
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

    # "Benchmark-Sprung" (FTP) - in status-und-plan.md und Konzept-Dokument
    # Abschnitt 1.1 lange als Trigger dokumentiert, aber bis v0.16.0 mangels
    # FTP-Datenquelle nicht umsetzbar (siehe check_trainingsplan_trigger()-
    # Docstring oben, der diese Lücke bisher explizit benannte). Seit dem
    # FTP-Sensor (Garmin.get_cycling_ftp(), siehe do_sync) jetzt verfügbar:
    # 7-Tage-Schnitt jetzt vs. 7-Tage-Schnitt vor ca. 4-5 Wochen, gleicher
    # Cooldown-Mechanismus wie bei den anderen Datentriggern.
    ftp_recent = _history_avg(history, "ftp", 0, 6, today=today_date)
    ftp_month_ago = _history_avg(history, "ftp", 21, 34, today=today_date)
    days_since_ftp = _days_since(last_dates.get("ftp_jump"), today_date)
    if (ftp_recent is not None and ftp_month_ago is not None and ftp_month_ago > 0
            and ftp_recent >= ftp_month_ago * (1 + TRAININGSPLAN_FTP_JUMP_THRESHOLD_PCT / 100)
            and (days_since_ftp is None
                 or days_since_ftp >= TRAININGSPLAN_TRIGGER_COOLDOWN_DAYS)):
        last_dates["ftp_jump"] = today_date.isoformat()
        state["last_trigger_dates"] = last_dates
        _save_trainingsplan_state(state)
        return "ftp_jump", (
            f"FTP (Rad) deutlich gestiegen: {ftp_recent} W (7-Tage-Schnitt aktuell) vs. "
            f"{ftp_month_ago} W (7-Tage-Schnitt vor ca. 4-5 Wochen), "
            f"Schwelle +{TRAININGSPLAN_FTP_JUMP_THRESHOLD_PCT}%"
        )

    return None, None


def build_weekly_summary(wellness: dict, history: list) -> dict:
    """Stellt die Kennzahlen des Wochenreports zusammen (laufende Woche vs. Vorwoche).

    Bewusst eine flache Struktur aus Zahlen: so lässt sie sich 1:1 als
    MQTT-Attribute mitschicken und im Dashboard direkt anzeigen."""
    cur = wellness.get("weekly_volumes") or {}
    prev = wellness.get("weekly_volumes_prev") or {}
    total_min = round(sum(cur.get(k, 0) or 0 for k in
                          ("swim_min", "bike_min", "run_min", "strength_min")))
    total_min_prev = round(sum(prev.get(k, 0) or 0 for k in
                               ("swim_min", "bike_min", "run_min", "strength_min")))

    # Datumsbereiche der beiden Fenster als Klartext - die Tabelle im Dashboard nannte
    # diese Fenster bisher "Diese Woche"/"Vorwoche", was auf den Kopf zeigt, wenn der
    # Report (wie vorgesehen) montags über die gerade abgeschlossene Woche läuft:
    # dann ist "diese Woche" für den Betrachter eigentlich schon "letzte Woche". Ein
    # konkretes Datum statt einer relativen Woche-Bezeichnung räumt die Verwirrung aus,
    # unabhängig davon, an welchem Wochentag der Report erzeugt wird (auch /weekly
    # kann jederzeit manuell ausgelöst werden, nicht nur montags).
    
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
        # Wie viele Tage die Historie überhaupt schon abdeckt - der Report soll
        # nicht so tun, als wären Trends belastbar, wenn erst 2 Tage erfasst sind.
        "history_days": len(history or []),
        "zone_low_pct": cur.get("zone_low_pct"),
        "zone_mid_pct": cur.get("zone_mid_pct"),
        "zone_high_pct": cur.get("zone_high_pct"),
        "zone_total_min": round(cur.get("zone_total_min") or 0),
        "zone_sessions": cur.get("zone_sessions"),
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
        progress.record_ai_result("weekly", True)
    except Exception as e:
        progress.record_ai_result("weekly", False, error=str(e))
        print(f"[weekly] Wochenreport fehlgeschlagen: {e}")
        text = "Wochenreport aktuell nicht verfügbar - Kennzahlen siehe Attribute."
    publish_weekly_report(text, summary)
    return text


def do_sync(force: bool = False, also_weekly: bool = False):
    """Holt aktuelle Garmin-Daten, speichert sie lokal und published sie
    (inkl. KI-Coaching-Notiz) nach MQTT/Home Assistant.

    Wird sowohl vom manuellen /sync-Aufruf als auch vom täglichen
    Hintergrund-Scheduler genutzt, damit beide Wege garantiert
    tatsächlich bei Home Assistant ankommen. `force=True` umgeht die
    Mindestpause (z.B. für gezieltes Testen über /sync?force=1).
    `also_weekly=True` erzeugt zusätzlich unabhängig vom Wochentag den
    Wochenreport (siehe "Jetzt synchronisieren"-Button/Handler unten) -
    normalerweise läuft der Wochenreport nur montags automatisch mit.
    """
    global _last_sync_attempt
    if not is_logged_in():
        return None

    now = datetime.datetime.now()
    if not force and _last_sync_attempt and now - _last_sync_attempt < MIN_SYNC_INTERVAL:
        print("[sync] übersprungen: letzter Versuch liegt weniger als "
              f"{MIN_SYNC_INTERVAL} zurück (Schutz vor Garmin-Kontosperre).")
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

            # Erholung / Belastung - für Übertrainings-Frühwarnung
            "training_status": _safe_fetch("training_status", lambda: client.get_training_status(today)),
            "hrv": _safe_fetch("hrv", lambda: client.get_hrv_data(today)),
            "body_battery": _safe_fetch("body_battery", lambda: client.get_body_battery(today, today)),
            "stress": _safe_fetch("stress", lambda: client.get_all_day_stress(today)),
            "respiration": _safe_fetch("respiration", lambda: client.get_respiration_data(today)),
            "spo2": _safe_fetch("spo2", lambda: client.get_spo2_data(today)),
            "sleep": _safe_fetch("sleep", lambda: client.get_sleep_data(today)),

            # Fitness-Fortschritt - für die Ironman-70.3-Vorbereitung
            "max_metrics": _fetch_max_metrics(client, today_date),  # VO2max (14-Tage-Fenster)
            # FTP (Rad) - Garmin.get_cycling_ftp() liefert ohne Parameter die
            # zuletzt von Garmin/Zwift ermittelte FTP, kein Datum nötig (siehe
            # claude/konzept-erweiterung-metriken-v0.16-plus.md, Abschnitt 1.1).
            "ftp_raw": _safe_fetch("ftp", lambda: client.get_cycling_ftp()),

            # Rennvorbereitung / Periodisierung (siehe claude/status-und-plan.md)
            "days_to_race": days_to_race(today_date),
            "phase": current_phase(today_date),
        }

        recent_activities = _safe_fetch("activities", lambda: client.get_activities(0, 50)) or []
        # Kalenderwoche Mo-So statt rollierender 7-Tage-Fenster: Montag 00:00 dieser
        # Woche bis (exklusiv) nächsten Montag; Vorwoche entsprechend 7 Tage davor.
        week_start = datetime.datetime.combine(
            today_date - datetime.timedelta(days=today_date.weekday()), datetime.time.min
        )
        week_end = week_start + datetime.timedelta(days=7)
        prev_week_start = week_start - datetime.timedelta(days=7)
        prev_week_end = week_start
        wellness["weekly_volumes"] = _volumes_in_window(recent_activities, week_start, week_end)
        # Vorwoche aus denselben Aktivitätsdaten - Basis für den Soll/Ist-Vergleich
        # im Wochenreport, ohne einen einzigen zusätzlichen Garmin-Request.
        wellness["weekly_volumes_prev"] = _volumes_in_window(recent_activities, prev_week_start, prev_week_end)
        # Einzelne Übungen/Sätze je Kraft-Einheit dieser Woche (Best-Effort über
        # die Original-FIT-Datei, siehe fit_exercises.py) - über _safe_fetch, damit
        # ein Problem hier (z.B. neues Garmin-Dateiformat) nie den ganzen Sync killt.
        wellness["strength_exercises"] = _safe_fetch(
            "strength_exercises", lambda: _update_strength_exercises(client, recent_activities)
        ) or []

        # HF-Pace-Kopplung (aerobe Entkopplung) je qualifizierender Lauf-
        # Aktivität - siehe decoupling.py. Über _safe_fetch, damit ein
        # Problem hier (z.B. unerwartetes Antwortformat von
        # get_activity_splits) nie den ganzen Sync killt.
        wellness["decoupling_sessions"] = _safe_fetch(
            "decoupling", lambda: _update_decoupling_cache(client, recent_activities)
        ) or []

        # Interferenz-Hinweis Ausdauer-vor-Kraft <3h (siehe
        # _check_endurance_before_strength_interference) - reine Berechnung
        # auf bereits geladenen Aktivitätsdaten, kein zusätzlicher
        # Garmin-Request, trotzdem defensiv behandelt.
        interference_note = ""
        try:
            interference_note = _check_endurance_before_strength_interference(
                recent_activities, today_date
            )
        except Exception as e:
            print(f"[sync] Interferenz-Prüfung fehlgeschlagen: {e}")

        # Diese beiden ändern sich nur langsam (Tage/Wochen) -> nur einmal
        # wöchentlich (montags) abrufen, um zusätzliche Garmin-Calls und
        # damit das Rate-Limit-Risiko nicht unnötig zu erhöhen.
        if today_date.weekday() == 0:  # Montag
            # Einzeltag-Abfrage: liefert "overallScore" direkt. Die früher genutzte
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
        # je nach Modell deutlich über eine Minute dauern oder ganz fehlschlagen; die
        # Garmin-Daten sollen davon nicht aufgehalten oder mitgerissen werden.
        publish_state(wellness)
        publish_sync_status(ok=True)
        publish_strength_exercises(wellness["strength_exercises"])
        publish_decoupling(wellness["decoupling_sessions"], skipped=_decoupling_skipped())

        # Annehmen/Ablehnen-Zustand der Gym-Kritik-Vorschläge (Dashboard-Tab
        # "Vorschläge", siehe suggestions.py) mit der aktuellen Punkteliste
        # abgleichen - VOR dem Trainingsplan-Kommentar-Block unten, damit
        # generate_trainingsplan_kommentar() dort bereits den aktuellen Status kennt
        # (angenommene/abgelehnte Punkte werden im Prompt ausgeblendet bzw. markiert,
        # siehe ai_coach._render_gym_kritik). Günstig genug, um bei jedem Sync zu
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
                gym_note = "Noch keine verwertbaren Kraft-Übungsdaten der letzten 7 Tage für einen Gym-Tipp."
            else:
                gym_note = generate_gym_coaching_note(
                    wellness["strength_exercises"], interference_note=interference_note
                )
                progress.record_ai_result("gym", True)
        except Exception as e:
            progress.record_ai_result("gym", False, error=str(e))
            print(f"[ai_coach] Gym-Coaching-Tipp fehlgeschlagen: {e}")
            gym_note = "Gym-Coaching-Tipp aktuell nicht verfügbar - Übungsdaten wurden trotzdem synchronisiert."
        publish_gym_coaching_note(gym_note)

        # Plan, Tagesampel, Kraftwerte (v0.18.0) - reine Berechnung, kein Netzwerk.
        metrics_now = extract_metrics(wellness)
        history_before = _load_history()
        plan_state = plan.build_plan_state(today_date, RACE_DATE_OBJ, wellness["weekly_volumes"])
        publish_plan(plan_state)
        rec = recommendation.evaluate(
            metrics_now,
            rhr_7d_avg=_history_avg(history_before, "resting_hr", 1, 7, today_date),
            hrv_baseline=metrics_now.get("hrv_baseline"),
            hrv_7d=metrics_now.get("hrv_weekly_avg"),
        )
        publish_recommendation(rec)
        try:
            publish_kraftwerte(progress.e1rm_summary(progress.update_e1rm(list(_load_strength_cache().values()))))
        except Exception as e:
            print(f"[kraftwerte] fehlgeschlagen: {e}")

        # Tagesnotiz: KI formuliert, Regeln entscheiden. Fällt Gemini aus, steht die
        # regelbasierte Notiz im Dashboard - plus die letzte erfolgreiche KI-Notiz.
        try:
            note, model_used = generate_coaching_note(wellness, rec=rec, plan_state=plan_state)
            state = progress.record_ai_result("coaching", True, text=note, model=model_used)
            publish_coaching_note(note, source="ki")
        except Exception as e:
            print(f"[ai_coach] Coaching-Notiz fehlgeschlagen: {e}")
            state = progress.record_ai_result("coaching", False, error=str(e))
            last = state.get("coaching") or {}
            publish_coaching_note(
                recommendation.fallback_note(rec, plan_state), source="regeln",
                last_ai_note=last.get("last_text"), last_ai_at=last.get("last_success"),
            )
        _publish_coach_status()

        history = _update_history(wellness)

        # Trainingsplan-Kommentierung (Tab "Trainingspläne") - anders als die
        # anderen Coaching-Texte NICHT bei jedem Sync, sondern nur wenn ein
        # konkreter Auslöser vorliegt (siehe check_trainingsplan_trigger).
        # Kein Trigger -> Funktion wird gar nicht erst aufgerufen, der zuletzt
        # publizierte (retained) Kommentar bleibt im Dashboard einfach stehen.
        try:
            trigger_key, trigger_detail = check_trainingsplan_trigger(
                today_date, wellness["phase"], history
            )
            if trigger_key:
                if not os.environ.get("GEMINI_API_KEY"):
                    raise RuntimeError("Kein Gemini API Key in der Add-on-Konfiguration hinterlegt")
                # Aktueller Annehmen/Ablehnen-Stand als Kontext für den Prompt (siehe
                # suggestions.py): Gym-Status blendet abgelehnte Punkte aus, decided_context
                # nennt bereits entschiedene frühere Einzelvorschläge aus DIESEM Kanal, damit
                # Gemini angenommene nicht erneut vorschlägt und abgelehnte nicht wiederholt.
                gym_status = {
                    sid: rec["status"] for sid, rec in suggestions.by_source("gym_kritik").items()
                }
                decided_context = suggestions.context_for_prompt("trainingsplan_kommentar")
                plan_note, plan_vorschlaege = generate_trainingsplan_kommentar(
                    trigger_key, trigger_detail, wellness, history,
                    gym_status=gym_status, decided_context=decided_context,
                    interference_note=interference_note,
                )
                progress.record_ai_result("plan", True)
                suggestions.sync_suggestions("trainingsplan_kommentar", plan_vorschlaege)
                publish_trainingsplan_kommentar(plan_note, trigger_key, trigger_detail)
                print(f"[trainingsplan] Kommentar publiziert (Auslöser: {trigger_key}, "
                      f"{len(plan_vorschlaege)} Einzelvorschlag/-vorschläge)")
        except Exception as e:
            # Bewusst KEIN publish_trainingsplan_kommentar(...) mit Fehlertext:
            # anders als bei den anderen Coaching-Texten soll bei einem Fehler
            # hier der zuletzt erfolgreich generierte Kommentar (falls
            # vorhanden) im Dashboard stehen bleiben statt durch eine
            # Fehlermeldung ersetzt zu werden - der nächste ausgelöste Sync
            # versucht es erneut.
            progress.record_ai_result("plan", False, error=str(e))
            print(f"[trainingsplan] Kommentar fehlgeschlagen: {e}")

        # Aktuellen Annehmen/Ablehnen-Gesamtzustand publizieren (Dashboard-Tab
        # "Vorschläge") - unabhängig davon, ob oben ein Trainingsplan-Kommentar-
        # Trigger ausgelöst hat: die Gym-Kritik wurde weiter oben in jedem Fall
        # abgeglichen, und selbst ohne neuen Trigger soll das Dashboard den zuletzt
        # bekannten Stand (inkl. früherer Annahme-/Ablehnungs-Entscheidungen) zeigen.
        publish_vorschlaege(suggestions.all_suggestions())

        # Wochenreport montags automatisch (Rückblick auf die abgeschlossene Woche);
        # jederzeit manuell über /weekly auslösbar, oder über also_weekly=True
        # gebündelt mit diesem Sync (siehe "Jetzt synchronisieren"-Button).
        if today_date.weekday() == 0 or also_weekly:
            do_weekly_report(wellness, history)
        return wellness
    except Exception as e:
        print(f"[sync] Sync fehlgeschlagen: {e}")
        publish_sync_status(ok=False, detail=str(e))
        return None


def _handle_sync_button_press():
    """Wird über MQTT ausgelöst (Button-Entity "Garmin AI Coach Jetzt
    synchronisieren" aus ha_publish.publish_discovery(), Topic
    garmin_ai_coach/sync_now/set) statt wie bisher über einen Dashboard-Klick
    auf eine fest verdrahtete Ingress-URL. Diese URL scheiterte mit HTTP 401,
    sobald der Browser keine gültige (kurzlebige) Ingress-Session mehr hatte -
    z.B. weil der Tap-Action-Typ "url" den Link in einem neuen Tab öffnet, der
    nie eine Ingress-Session aufgebaut hat (siehe claude/status-und-plan.md,
    "Dashboard-Ingress-URL fragil"). Ein MQTT-Button ist eine normale
    HA-Entity, die über einen ganz normalen Service-Call (mqtt.publish)
    ausgelöst wird - unabhängig von Ingress-Sessions.

    Läuft in einem eigenen Thread, damit der MQTT-Netzwerk-Thread (der diesen
    Callback aufruft) nicht blockiert wird - ein Sync inkl. Gemini-Aufrufen
    kann mehrere zehn Sekunden dauern. Löst bewusst IMMER auch den
    Wochenreport aus (also_weekly=True, siehe do_sync) - Alex' ausdrücklicher
    Wunsch, damit ein Klick auf "Jetzt synchronisieren" beides gleichzeitig
    anstößt, unabhängig vom Wochentag."""
    def _run():
        print("[mqtt] Sync-Button gedrückt - starte Sync + Wochenreport")
        try:
            do_sync(force=True, also_weekly=True)
        except Exception as e:
            print(f"[mqtt] Sync über Button fehlgeschlagen: {e}")
    threading.Thread(target=_run, daemon=True).start()


set_sync_button_callback(_handle_sync_button_press)


def _handle_vorschlag_accept(suggestion_id: str):
    """Wird über MQTT ausgelöst (Button "Garmin Vorschlag Annehmen", Topic
    garmin_ai_coach/vorschlag_annehmen/set), wirkt auf den zuletzt im Dropdown
    "Garmin Vorschlag Auswahl" ausgewählten Vorschlag (siehe ha_publish.
    _on_message). Setzt dessen Status auf "accepted" (suggestions.py) - wird
    künftigen Trainingsplan-Kommentar-Prompts als bereits angenommen/
    umgesetzt mitgegeben, siehe suggestions.context_for_prompt und
    ai_coach._render_gym_kritik. Publiziert danach sofort den neuen
    Gesamtzustand, damit das Dashboard nicht bis zum nächsten Sync auf die
    Aktualisierung warten muss. Schnelle reine Datei-/MQTT-Operation, deshalb
    (anders als der Sync-Button) ohne eigenen Thread."""
    try:
        if suggestions.set_status(suggestion_id, suggestions.STATUS_ACCEPTED):
            print(f"[vorschläge] '{suggestion_id}' angenommen")
        else:
            print(f"[vorschläge] Annehmen fehlgeschlagen: id '{suggestion_id}' unbekannt "
                  "(veraltete Dashboard-Auswahl nach einem zwischenzeitlichen Sync?)")
        publish_vorschlaege(suggestions.all_suggestions())
    except Exception as e:
        print(f"[vorschläge] Annehmen fehlgeschlagen: {e}")


def _handle_vorschlag_reject(suggestion_id: str):
    """Analog zu _handle_vorschlag_accept, aber für den "Garmin Vorschlag
    Ablehnen"-Button - setzt den Status auf "rejected". Der Vorschlag bleibt
    im Dashboard-Tab "Vorschläge" unter "Abgelehnt" sichtbar und lässt sich
    dort jederzeit wieder auswählen und per erneutem Annehmen reaktivieren."""
    try:
        if suggestions.set_status(suggestion_id, suggestions.STATUS_REJECTED):
            print(f"[vorschläge] '{suggestion_id}' abgelehnt")
        else:
            print(f"[vorschläge] Ablehnen fehlgeschlagen: id '{suggestion_id}' unbekannt "
                  "(veraltete Dashboard-Auswahl nach einem zwischenzeitlichen Sync?)")
        publish_vorschlaege(suggestions.all_suggestions())
    except Exception as e:
        print(f"[vorschläge] Ablehnen fehlgeschlagen: {e}")


set_vorschlag_callbacks(on_accept=_handle_vorschlag_accept, on_reject=_handle_vorschlag_reject)


def _load_latest_wellness_and_history():
    """Lädt die zuletzt gespeicherten Sync-Daten + Tages-Historie von der
    Platte - gleiche Quelle/gleiches Muster wie do_weekly_report() ohne
    Parameter. Für den Chat (_handle_chat_question unten) gebraucht, damit
    eine Frage NICHT extra einen neuen Garmin-Sync auslöst (wäre zu
    langsam/unnötiges Rate-Limit-Risiko für eine reine Textfrage)."""
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
    """Wird über MQTT ausgelöst (text-Entity "Garmin Chat Frage", Topic
    garmin_ai_coach/chat_frage/set, siehe ha_publish.py). Ruft Gemini MIT dem
    aktuellen Trainingskontext auf (ai_coach.generate_chat_answer - Alex'
    ausdrücklicher Wunsch, damit z.B. "Wie war meine Woche?" ohne weitere
    Erklärung funktioniert), hängt Frage+Antwort an den gespeicherten
    Verlauf an (chat.py) und published das Ergebnis sofort.

    Läuft in einem eigenen Thread (wie _handle_sync_button_press) - der
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
            progress.record_ai_result("chat", True)
        except Exception as e:
            progress.record_ai_result("chat", False, error=str(e))
            print(f"[chat] Antwort fehlgeschlagen: {e}")
            answer = "Antwort aktuell nicht verfügbar (Gemini-Fehler). Frag gern gleich nochmal."
        entries = chat.add_exchange(question, answer)
        publish_chat_history(entries)
        _publish_coach_status()
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
    """Wochenreport manuell auslösen (läuft sonst automatisch montags).
    Nutzt die zuletzt gesyncten Daten, löst also KEINE Garmin-Abfrage aus."""
    if not is_logged_in():
        return redirect(".")
    do_weekly_report()
    return redirect(".")


def _seconds_until_next_run(hours: list) -> float:
    """Sekunden bis zum nächsten Termin unter mehreren täglichen Stunden - also bis zur
    zeitlich nächstgelegenen noch ausstehenden Stunde aus `hours` (heute, sonst morgen)."""
    now = datetime.datetime.now()
    targets = []
    for hour in hours:
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        targets.append(target)
    return (min(targets) - now).total_seconds()


def _scheduler_loop():
    """Läuft im Hintergrund und ruft do_sync() zu jeder in SYNC_HOURS konfigurierten Stunde
    auf (Default 6/12/18/20 Uhr), damit "automatischer Sync" auch wirklich mehrfach täglich
    automatisch passiert, nicht nur einmal."""
    while True:
        time.sleep(_seconds_until_next_run(SYNC_HOURS))
        try:
            do_sync()
        except Exception as e:
            print(f"[scheduler] Automatischer Sync fehlgeschlagen: {e}")


if __name__ == "__main__":
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8099)
