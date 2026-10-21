"""Gym-Einheiten als strukturierte Kraft-Workouts im Garmin-Kalender (seit 0.25.0).

Auftrag Alex 21.10.2026: wie beim Schwimmen sollen auch die Gym-Einheiten als
Kalendereintrag in Garmin Connect landen. Vorteil: Die Uhr kennt die Übung
schon vor dem Satz (Name, Wiederholungen, Gewicht) - die Übungen müssen danach
nicht mehr von Hand in der Aktivität korrigiert werden, und die Sätze kommen
sauber benannt im Add-on an (fit_exercises.py / gym_progress.py).

Quelle der Einheiten: gym_plan.json (von Alex' Trainingsplänen abgeleitet).
Solange dort keine Einheit steht, macht das Modul nichts.

Format gym_plan.json:
    {"workouts": {"push": {"name": "Push", "exercises": [
        {"name": "Bankdrücken", "category": "BENCH_PRESS", "exercise": "BARBELL_BENCH_PRESS",
         "sets": 3, "reps": 8, "weight_kg": 80, "rest_s": 120, "note": "2 Wdh. Reserve"},
        {"name": "Plank", "category": "PLANK", "exercise": "PLANK", "sets": 3, "seconds": 45, "rest_s": 60}]}},
     "schedule": {"0": "push", "2": "pull", "4": "pp", "3": "legs"}}
    schedule: Wochentag (0 = Montag) -> Einheit. Beine liegen am Donnerstag, weil das
    Schwimm-Workout auf Dienstag gelegt wird; in Garmin per Drag & Drop tauschbar.

Garmin-JSON (Kraft): sportTypeId 5 "strength_training"; je Übung ein
RepeatGroupDTO (Sätze) aus Übungsschritt (stepType interval, endCondition
reps = conditionTypeId 10 bzw. time = 2, category + exerciseName,
weightValue in GRAMM mit weightUnit kilogram/factor 1000) und Pause
(stepType rest, endCondition time). Aufbau wie create_strength_set() in
python-garminconnect 0.3.19 (garminconnect/workout.py, MIT); dort ist auch der
Übungskatalog her (gym_exercises.json: 1527 Übungen, category/exercise).
Selbst gebaut statt über die Bibliothek, weil das Add-on-Image (Alpine 3.19,
Python 3.11) eine ältere garminconnect-Version ohne StrengthWorkout installiert.
"""
import os, json, datetime, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = os.path.join(HERE, "gym_plan.json")
CATALOG_FILE = os.path.join(HERE, "gym_exercises.json")
STATE_FILE = os.path.join("/data", "garmin_gym_export.json")

SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
STEP_INTERVAL = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
STEP_REST = {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5}
STEP_REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}
COND_REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": True}
COND_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
COND_ITER = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def catalog() -> set:
    return {(c, e) for c, e, _ in _load(CATALOG_FILE, [])}


def validate(plan: dict = None) -> list:
    """Übungen, deren category/exercise Garmin nicht kennt (sonst zeigt die Uhr nur
    "Übung" oder verwirft den Schritt)."""
    plan = plan if plan is not None else _load(PLAN_FILE, {})
    cat = catalog()
    bad = []
    for key, w in (plan.get("workouts") or {}).items():
        for ex in w.get("exercises") or []:
            if (ex.get("category"), ex.get("exercise", "")) not in cat:
                bad.append(f"{key}: {ex.get('name')} ({ex.get('category')}/{ex.get('exercise')})")
    return bad


def build_workout(w: dict) -> dict:
    steps, order = [], 0
    secs = 0
    for gi, ex in enumerate(w.get("exercises") or [], start=1):
        order += 1
        group_order = order
        timed = bool(ex.get("seconds"))
        step = {
            "type": "ExecutableStepDTO", "stepOrder": order + 1, "childStepId": gi,
            "stepType": STEP_INTERVAL,
            "endCondition": COND_TIME if timed else COND_REPS,
            "endConditionValue": float(ex["seconds"] if timed else ex["reps"]),
            "targetType": NO_TARGET,
            "category": ex["category"], "exerciseName": ex.get("exercise", ""),
            "description": (ex.get("note") or ex.get("name") or "")[:250],
        }
        if ex.get("weight_kg"):
            step["weightValue"] = float(ex["weight_kg"]) * 1000.0
            step["weightUnit"] = KG
        rest = {
            "type": "ExecutableStepDTO", "stepOrder": order + 2, "childStepId": gi,
            "stepType": STEP_REST, "endCondition": COND_TIME,
            "endConditionValue": float(ex.get("rest_s") or 90), "targetType": NO_TARGET,
        }
        n = int(ex.get("sets") or 1)
        steps.append({
            "type": "RepeatGroupDTO", "stepOrder": group_order, "stepType": STEP_REPEAT,
            "childStepId": gi, "numberOfIterations": n, "smartRepeat": False,
            "endCondition": COND_ITER, "endConditionValue": float(n), "skipLastRestStep": True,
            "workoutSteps": [step, rest],
        })
        order += 2
        secs += n * ((ex.get("seconds") or (ex.get("reps") or 8) * 4) + (ex.get("rest_s") or 90))
    return {
        "workoutName": (w.get("name") or "Kraft")[:80],
        "description": (w.get("description") or "Garmin AI Coach")[:1000],
        "sportType": SPORT,
        "estimatedDurationInSecs": int(secs),
        "workoutSegments": [{"segmentOrder": 1, "sportType": SPORT, "workoutSteps": steps}],
    }


def _id(resp, *keys):
    if isinstance(resp, dict):
        for k in keys:
            if resp.get(k):
                return resp[k]
    return None


def _strength_steps(steps: list) -> list:
    out = []
    for st in steps or []:
        if st.get("workoutSteps"):
            out += _strength_steps(st["workoutSteps"])
        elif st.get("category"):
            out.append(st)
    return out


def verify(client, workout_id, payload: dict) -> str:
    """Liest das gespeicherte Workout zurück: Übung (category/exerciseName) und
    Gewicht übernommen? Garmin verwirft unbekannte Felder still."""
    sent = _strength_steps(payload["workoutSegments"][0]["workoutSteps"])
    try:
        stored = client.get_workout_by_id(workout_id)
        got = _strength_steps((stored.get("workoutSegments") or [{}])[0].get("workoutSteps"))
    except Exception as e:
        return f"Prüfung nicht möglich ({e})"
    ok_ex = sum(1 for a, b in zip(sent, got)
                if a["category"] == b.get("category") and a["exerciseName"] == (b.get("exerciseName") or ""))
    ok_w = sum(1 for a, b in zip(sent, got) if "weightValue" not in a or b.get("weightValue") == a["weightValue"])
    return f"Übungen {ok_ex}/{len(sent)}, Gewichte {ok_w}/{len(sent)}"


def selftest(client) -> dict:
    """Lädt ein Mini-Workout hoch (nicht eingeplant), prüft es und löscht es wieder -
    beweist, dass Garmin Übung, Wiederholungen und Gewicht übernimmt."""
    w = {"name": "GAC Selbsttest Kraft", "exercises": [
        {"name": "Bankdrücken", "category": "BENCH_PRESS", "exercise": "BARBELL_BENCH_PRESS",
         "sets": 2, "reps": 8, "weight_kg": 60, "rest_s": 90},
        {"name": "Plank", "category": "PLANK", "exercise": "PLANK", "sets": 1, "seconds": 45, "rest_s": 30}]}
    payload = build_workout(w)
    resp = client.upload_workout(payload)
    wid = _id(resp, "workoutId")
    out = {"uploaded": bool(wid), "workout_id": wid}
    if wid:
        out["check"] = verify(client, wid, payload)
        try:
            stored = client.get_workout_by_id(wid)
            out["stored_first_step"] = _strength_steps(stored["workoutSegments"][0]["workoutSteps"])[0]
        except Exception as e:
            out["stored_first_step"] = str(e)
        client.delete_workout(wid)
        out["deleted"] = True
    return out


def export_upcoming(client, today: datetime.date = None, done_dates: set = None) -> dict:
    """Plant die Gym-Einheiten der restlichen Woche und der nächsten Woche ein
    (wie garmin_swim: rollierendes Fenster, bei Planänderung ersetzt).
    done_dates: Tage mit erledigter Krafteinheit - dort nichts mehr anlegen."""
    plan = _load(PLAN_FILE, {})
    workouts = plan.get("workouts") or {}
    schedule = plan.get("schedule") or {}
    if not workouts or not schedule:
        return {"status": "kein Plan hinterlegt", "workouts": []}
    bad = validate(plan)
    if bad:
        print(f"[garmin_gym] Unbekannte Übungen, bitte gym_plan.json prüfen: {bad}")
    today = today or datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    state = _load(STATE_FILE, {})
    result = []
    for wk in (monday, monday + datetime.timedelta(days=7)):
        for wd, key in sorted(schedule.items()):
            day = wk + datetime.timedelta(days=int(wd))
            w = workouts.get(key)
            if not w or day < today or day.isoformat() in (done_dates or set()):
                continue
            payload = build_workout(w)
            sig = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
            entry = state.get(day.isoformat()) or {}
            action = "unverändert"
            if entry.get("workout_id") and entry.get("sig") != sig:
                try:
                    client.delete_workout(entry["workout_id"])
                except Exception as e:
                    print(f"[garmin_gym] Löschen von {entry['workout_id']} fehlgeschlagen ({e})")
                entry = {}
            if not entry.get("workout_id"):
                wid = _id(client.upload_workout(payload), "workoutId")
                if not wid:
                    raise RuntimeError("Garmin hat keine workoutId geliefert")
                client.schedule_workout(wid, day.isoformat())
                entry = {"workout_id": wid, "check": verify(client, wid, payload)}
                action = "neu im Kalender"
            entry.update({"sig": sig, "key": key, "name": w.get("name")})
            state[day.isoformat()] = entry
            result.append({"date": day.isoformat(), "name": w.get("name"), "action": action,
                           "workout_id": entry["workout_id"], "check": entry.get("check", "")})
            print(f"[garmin_gym] {day.isoformat()} {w.get('name')}: {action}")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    return {"status": "ok", "unknown_exercises": bad, "workouts": result,
            "updated": datetime.datetime.now().isoformat(timespec="minutes")}
