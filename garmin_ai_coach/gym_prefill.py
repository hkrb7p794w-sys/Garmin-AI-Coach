"""Kraft-Aktivitäten automatisch mit dem Tagesplan vorbefüllen (seit 0.28.0).

Auftrag Alex 21.10.2026: Die Garmin CIRQA (ohne Display) kann geplante Kraft-
Workouts nur mit Connect+ ausführen. Ziel ist aber nur: Nach dem Training steht
die Aktivität mit Übungen, Sätzen und Gewicht in Garmin Connect, Alex trägt nur
noch die Wiederholungen ein - ohne Abo und ohne an die Forerunner zu denken.

Ablauf bei jedem Sync:
1. Kraft-Aktivitäten der letzten LOOKBACK_DAYS Tage (frühestens ab START_DATE,
   damit nie alte Einheiten verändert werden), die noch nicht bearbeitet wurden.
2. Vorbefüllt wird nur, wenn die Aktivität noch keine benannte Übung enthält
   (leer oder nur "Unbekannt") - was Alex oder die Forerunner eingetragen haben,
   bleibt unangetastet.
3. Welche Einheit: nach Wochentag aus gym_plan.json (Mo Push A, Di/Do Lower,
   Mi Pull A, Fr Push & Pull B). Sa/So: keine feste Einheit -> nichts tun.
4. Gewicht je Übung: zuletzt gelogtes Gewicht dieser Übung, bei Status
   "erhöhen" das empfohlene neue Gewicht (gym_progress), sonst Planwert.
5. Wiederholungen bleiben leer (repetitionCount = None), damit eine nicht
   bearbeitete Einheit nicht als "12 geschafft" in die Progression eingeht.
   Lehnt Garmin leere Wiederholungen ab, wird mit dem Planwert geschrieben und
   die Einheit als "unbestätigt" gemerkt: Solange die Sätze exakt dem
   Vorbefüllten entsprechen, zählt sie nicht für die Progression.
6. Die Aktivität bekommt den Namen der Einheit (z. B. "Pull A").

Format (live geprüft an Alex' Aktivität vom 21.10.2026, in der Connect-App von
Hand angelegt): exerciseSets[] mit setType ACTIVE/REST, exercises[{category,
name, probability}], repetitionCount, weight in GRAMM, duration 0, startTime None.
Schreiben: PUT activity-service/activity/{id}/exerciseSets (Replace-All, siehe
python-garminconnect set_activity_exercise_sets).
"""
import os
import json
import datetime

import garmin_gym
import exercise_names

STATE_FILE = os.path.join("/data", "gym_prefill.json")
START_DATE = "2026-10-22"     # vorher erfasste Einheiten nie anfassen
LOOKBACK_DAYS = 3
URL = "/activity-service/activity/{}/exerciseSets"


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)


def workout_for(day: datetime.date, plan: dict = None):
    """Einheit für einen Tag (Schlüssel, Workout) oder (None, None)."""
    plan = plan if plan is not None else garmin_gym._load(garmin_gym.PLAN_FILE, {})
    wd = day.weekday()
    for key, days in (plan.get("flex") or {}).items():
        if wd in [int(d) for d in days]:
            return key, (plan.get("workouts") or {}).get(key)
    key = (plan.get("schedule") or {}).get(str(wd))
    return (key, (plan.get("workouts") or {}).get(key)) if key else (None, None)


def _named(sets_payload) -> bool:
    for s in (sets_payload or {}).get("exerciseSets") or []:
        if str(s.get("setType") or "").upper() != "ACTIVE":
            continue
        for e in s.get("exercises") or []:
            if e.get("category") and str(e.get("category")).upper() not in ("UNKNOWN", "NONE"):
                return True
    return False


def _weight_kg(ex: dict, progression_by_id: dict):
    c = exercise_names.classify(f"{ex['category']} ({ex.get('exercise', '')})",
                                [{"reps": 1, "weight_kg": ex.get("weight_kg") or 0}])
    p = progression_by_id.get(c["id"]) or {}
    if ex.get("seconds") or not ex.get("weight_kg"):
        return None, c["id"], "Plan"
    if p.get("status") == "erhöhen" and p.get("next_weight"):
        return float(p["next_weight"]), c["id"], "Empfehlung"
    if p.get("weight"):
        return float(p["weight"]), c["id"], "zuletzt"
    return float(ex["weight_kg"]), c["id"], "Plan"


def build_sets(workout: dict, progression: list = None, reps_none: bool = True) -> tuple:
    """(payload-Sätze, Übersicht) für eine Einheit."""
    by_id = {p.get("id"): p for p in (progression or [])}
    sets, overview = [], []
    for ex in workout.get("exercises") or []:
        kg, ex_id, src = _weight_kg(ex, by_id)
        n = int(ex.get("sets") or 1)
        for i in range(n):
            sets.append({
                "setType": "ACTIVE", "duration": float(ex["seconds"]) if ex.get("seconds") else 0,
                "startTime": None, "wktStepIndex": None, "messageIndex": None,
                "exercises": [{"category": ex["category"], "name": ex.get("exercise") or None, "probability": 100}],
                "repetitionCount": None if (reps_none or ex.get("seconds")) else int(ex.get("reps") or 0),
                "weight": int(round(kg * 1000)) if kg else None,
            })
            if i < n - 1 or ex is not workout["exercises"][-1]:
                sets.append({"setType": "REST", "duration": 0, "startTime": None, "wktStepIndex": None,
                             "messageIndex": None, "exercises": [], "repetitionCount": None, "weight": None})
        overview.append({"name": ex.get("name"), "id": ex_id, "sets": n,
                         "weight_kg": kg, "weight_source": src})
    return sets, overview


def _put(client, activity_id, payload):
    fn = getattr(client, "set_activity_exercise_sets", None)
    if callable(fn):
        return fn(activity_id, payload)
    path = URL.format(activity_id)
    # Ältere garminconnect-Versionen: dieselbe Anfrage über den internen HTTP-Client
    for attr in ("client", "garth"):
        inner = getattr(client, attr, None)
        if inner is None:
            continue
        if callable(getattr(inner, "put", None)):
            return inner.put("connectapi", path, json=payload, api=True)
        if callable(getattr(inner, "request", None)):
            return inner.request("PUT", "connectapi", path, json=payload, api=True)
    try:
        import importlib.metadata as md
        ver = md.version("garminconnect")
    except Exception:
        ver = "?"
    raise RuntimeError(f"garminconnect {ver} kann keine Sätze schreiben (Attribute: "
                       f"{[a for a in dir(client) if not a.startswith('_')][:40]})")


def _rename(client, activity_id, name):
    fn = getattr(client, "set_activity_name", None)
    if callable(fn):
        try:
            fn(activity_id, name)
        except Exception as e:
            print(f"[gym_prefill] Umbenennen fehlgeschlagen ({e})")


def _signature(sets_payload) -> list:
    return [(s.get("setType"), ((s.get("exercises") or [{}])[0] or {}).get("name"),
             s.get("repetitionCount"), s.get("weight"))
            for s in (sets_payload or {}).get("exerciseSets") or [] if s.get("setType") == "ACTIVE"]


def unconfirmed_ids() -> set:
    """Aktivitäten, die mit Planwerten vorbefüllt wurden und noch nicht bearbeitet sind."""
    return {k for k, v in _load().items() if v.get("unconfirmed") and not v.get("edited")}


def pending(today: datetime.date = None, state: dict = None) -> list:
    """Heute vorbefüllte Einheiten, an denen noch nichts geändert wurde (Erinnerung um 20:30)."""
    today = (today or datetime.date.today()).isoformat()
    state = state if state is not None else _load()
    return [{"activity_id": k, "workout": v.get("workout")} for k, v in state.items()
            if v.get("date") == today and v.get("action") == "vorbefüllt" and not v.get("edited")]


def run(client, activities: list, progression: list = None, today: datetime.date = None) -> dict:
    today = today or datetime.date.today()
    state = _load()
    plan = garmin_gym._load(garmin_gym.PLAN_FILE, {})
    if plan.get("prefill") is False:
        return {"status": "aus", "activities": []}
    done = []
    for act in activities or []:
        tk = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
        if "strength" not in tk:
            continue
        start = str(act.get("startTimeLocal") or "")[:10]
        aid = act.get("activityId")
        if not aid or start < START_DATE:
            continue
        try:
            day = datetime.date.fromisoformat(start)
        except ValueError:
            continue
        if (today - day).days > LOOKBACK_DAYS:
            continue
        key = str(aid)
        entry = state.get(key)
        if entry and entry.get("action") == "vorbefüllt" and not entry.get("edited"):
            # Schon bearbeitet? Sobald Alex etwas ändert, zählt die Einheit normal (und die
            # Erinnerung am Abend entfällt).
            try:
                cur = client.get_activity_exercise_sets(aid)
                if entry.get("sig") is not None and _signature(cur) != entry.get("sig"):
                    entry["edited"] = True
                    entry["unconfirmed"] = False
                    print(f"[gym_prefill] {start} {entry.get('workout')}: bearbeitet")
            except Exception:
                pass
            continue
        if entry:
            continue
        try:
            current = client.get_activity_exercise_sets(aid)
        except Exception as e:
            print(f"[gym_prefill] Sätze von {aid} nicht lesbar ({e})")
            continue
        if _named(current):
            state[key] = {"date": start, "action": "schon benannt - unverändert"}
            continue
        wkey, workout = workout_for(day, plan)
        if not workout:
            state[key] = {"date": start, "action": f"kein Plan für {day:%A}"}
            continue
        sets, overview = build_sets(workout, progression, reps_none=True)
        # Hat das Gerät Sätze erkannt (Anzahl passt zum Plan), deren Wiederholungen übernehmen.
        detected = [x for x in (current or {}).get("exerciseSets") or [] if x.get("setType") == "ACTIVE"]
        planned = [x for x in sets if x["setType"] == "ACTIVE"]
        if detected and len(detected) == len(planned):
            for d, p_ in zip(detected, planned):
                for f in ("repetitionCount", "startTime", "duration"):
                    if d.get(f) is not None:
                        p_[f] = d[f]
        unconfirmed = False
        try:
            _put(client, aid, {"activityId": aid, "exerciseSets": sets})
        except Exception as e:
            print(f"[gym_prefill] leere Wiederholungen abgelehnt ({str(e)[:120]}) - schreibe Planwerte")
            sets, overview = build_sets(workout, progression, reps_none=False)
            try:
                _put(client, aid, {"activityId": aid, "exerciseSets": sets})
                unconfirmed = True
            except Exception as e2:
                print(f"[gym_prefill] Schreiben fehlgeschlagen ({e2})")
                state[key] = {"date": start, "action": f"Fehler: {str(e2)[:150]}"}
                continue
        _rename(client, aid, workout.get("name"))
        sig = None
        try:
            sig = _signature(client.get_activity_exercise_sets(aid))
        except Exception:
            pass
        state[key] = {"date": start, "workout": workout.get("name"), "action": "vorbefüllt",
                      "reps_empty": not unconfirmed, "unconfirmed": unconfirmed, "sig": sig,
                      "exercises": overview}
        done.append({"date": start, "activity_id": aid, "workout": workout.get("name"),
                     "reps_empty": not unconfirmed, "exercises": overview})
        print(f"[gym_prefill] {start} {workout.get('name')}: Aktivität {aid} vorbefüllt "
              f"({len(overview)} Übungen, Wdh. {'leer' if not unconfirmed else 'Planwert'})")
    cutoff = (today - datetime.timedelta(days=60)).isoformat()
    state = {k: v for k, v in state.items() if (v.get("date") or "") >= cutoff}
    _save(state)
    recent = sorted(({"activity_id": k, **v} for k, v in state.items()), key=lambda x: x.get("date") or "")[-5:]
    return {"status": "ok", "activities": done, "recent": recent, "pending_today": pending(today, state),
            "updated": datetime.datetime.now().isoformat(timespec="minutes")}
