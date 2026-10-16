"""Schwimmeinheiten aus dem Saisonplan als strukturierte Garmin-Workouts.

Bei jedem Sync legt das Add-on die Schwimmeinheiten der laufenden und der
nächsten Woche in den Garmin-Connect-Kalender (Dienstag; ist der in der
laufenden Woche schon vorbei: Donnerstag). Von dort landen sie
beim nächsten Uhren-Sync auf der Uhr - mit Einzelstrecken, Pausen und Ziel-Pace
(manuelle Pace aus der Dashboard-CSS, zusätzlich als Notiz je Abschnitt).

Bewusst nur ein rollierendes 2-Wochen-Fenster statt der ganzen Saison: die
Ziel-Paces hängen an der CSS. Nach einem neuen CSS-Test werden die schon
hochgeladenen Workouts beim nächsten Sync ersetzt (altes Workout löschen,
neues am selben Tag einplanen), statt 46 veraltete Einheiten im Kalender
stehen zu lassen.

Quelle der Einheiten: swim_plan.json (aus demselben Generator wie
custom_templates/coach_plan.jinja in Home Assistant, Stand 14.10.2026).
CSS-Quelle: input_text.zielzeit_schwimm_pace_100m über die Home-Assistant-API
(homeassistant_api: true in config.yaml), Rückfall plan.CSS_S_PER_100M.

Garmin-JSON-Felder (Schwimmen): sportTypeId 4, poolLength + poolLengthUnit,
Strecken-Ende conditionTypeId 3 "distance" mit preferredEndConditionUnit
meter, Pause stepType 5 "rest" mit conditionTypeId 8 "fixed.rest",
Kraulen strokeTypeId 6 "free", Pull-Buoy equipmentTypeId 4.
"""
import os, re, json, datetime, hashlib

import requests

import plan

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = os.path.join(HERE, "swim_plan.json")
STATE_FILE = os.path.join("/data", "garmin_swim_export.json")

POOL_LENGTH_M = 25
WEEKDAY = 1            # Dienstag (Schwimmen wechselt Di/Do - in Garmin per Drag & Drop verschiebbar)
NAME_PREFIX = "GAC Schwimmen"
CSS_ENTITY = "input_text.zielzeit_schwimm_pace_100m"

SPORT = {"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3}
METER = {"unitId": 1, "unitKey": "meter", "factor": 100.0}
STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cool": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "int": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "rec": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "rep": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}
COND_LAP = {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True}
COND_DIST = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
COND_ITER = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
COND_REST = {"conditionTypeId": 8, "conditionTypeKey": "fixed.rest", "displayOrder": 8, "displayable": True}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
PACE_TARGET = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
FREE = {"strokeTypeId": 6, "strokeTypeKey": "free", "displayOrder": 6}
NO_EQUIP = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
EQUIP = {"pull_buoy": {"equipmentTypeId": 4, "equipmentTypeKey": "pull_buoy", "displayOrder": 4}}


def _mmss(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def current_css() -> int:
    """CSS in s/100 m aus dem Dashboard-Feld; Rückfall auf plan.CSS_S_PER_100M."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            r = requests.get(f"http://supervisor/core/api/states/{CSS_ENTITY}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=10)
            r.raise_for_status()
            m, s = r.json()["state"].strip().split(":")
            css = int(m) * 60 + int(s)
            if 60 <= css <= 300:
                return css
        except Exception as e:
            print(f"[garmin_swim] CSS aus Home Assistant nicht lesbar ({e}) - nehme {plan.CSS_S_PER_100M} s")
    return plan.CSS_S_PER_100M


def _pace_note(step: dict, css: int) -> str:
    lo, hi = step.get("lo"), step.get("hi")
    if lo is None:
        return step.get("note", "")
    pace = _mmss(css + lo) if lo == hi else f"{_mmss(css + lo)}-{_mmss(css + hi)}"
    note = step.get("note", "")
    return f"@ {pace} /100 m" + (f" - {note}" if note else "")


def _pace_target(fast_s: int, slow_s: int) -> dict:
    """Manuelle Ziel-Pace (Garmin "pace.zone", Werte in m/s, langsam = Wert 1).

    Bewusst NICHT Garmins "CSS-basierte Zielpace": die rechnet mit der von
    Garmin geschätzten CSS (bei Alex 2:15), nicht mit der getesteten aus dem
    Dashboard (2:10). Eine einzelne Ziel-Pace bekommt ±2 s Spielraum, damit die
    Uhr nicht bei jeder Bahn piept."""
    if fast_s == slow_s:
        fast_s, slow_s = fast_s - 2, slow_s + 2
    return {"targetType": PACE_TARGET,
            "targetValueOne": round(100 / slow_s, 4),
            "targetValueTwo": round(100 / fast_s, 4)}


def _strip_targets(steps: list) -> list:
    """Rückfall: dieselben Schritte ohne Pace-Ziel (nur Notiz)."""
    out = []
    for st in steps:
        st = dict(st)
        if st.get("workoutSteps"):
            st["workoutSteps"] = _strip_targets(st["workoutSteps"])
        if st.get("targetType") == PACE_TARGET:
            st["targetType"] = NO_TARGET
            st.pop("targetValueOne", None)
            st.pop("targetValueTwo", None)
        out.append(st)
    return out


def _upload(client, payload: dict) -> dict:
    try:
        return client.upload_workout(payload)
    except Exception as e:
        print(f"[garmin_swim] Upload mit Pace-Ziel abgelehnt ({e}) - versuche es ohne Pace-Ziel")
        seg = dict(payload["workoutSegments"][0])
        seg["workoutSteps"] = _strip_targets(seg["workoutSteps"])
        return client.upload_workout(dict(payload, workoutSegments=[seg]))


def _steps(steps: list, css: int, order: list, groups: list, child=None) -> list:
    """order/groups sind Zähler (Listen, damit rekursiv veränderbar). Wie im
    Garmin-Editor bekommt jede Wiederholungsgruppe eine eigene childStepId,
    die auch ihre Unterschritte tragen."""
    out = []
    for st in steps:
        order[0] += 1
        n = order[0]
        if st["t"] == "rep":
            groups[0] += 1
            gid = groups[0]
            out.append({
                "type": "RepeatGroupDTO", "stepOrder": n, "stepType": STEP_TYPES["rep"],
                "childStepId": gid,
                "numberOfIterations": st["n"], "endCondition": COND_ITER,
                "endConditionValue": float(st["n"]), "smartRepeat": False,
                "skipLastRestStep": True,
                "workoutSteps": _steps(st["steps"], css, order, groups, gid),
            })
        elif st["t"] == "rest":
            out.append({
                "type": "ExecutableStepDTO", "stepOrder": n, "childStepId": child, "stepType": STEP_TYPES["rest"],
                "endCondition": COND_REST, "endConditionValue": float(st["s"]),
                "targetType": NO_TARGET,
            })
        elif st["t"] == "rec":
            out.append({
                "type": "ExecutableStepDTO", "stepOrder": n, "childStepId": child, "stepType": STEP_TYPES["rec"],
                "endCondition": COND_LAP, "targetType": NO_TARGET,
                "strokeType": FREE, "equipmentType": NO_EQUIP,
                "description": st.get("note", "")[:250],
            })
        else:
            step = {
                "type": "ExecutableStepDTO", "stepOrder": n, "childStepId": child, "stepType": STEP_TYPES[st["t"]],
                "endCondition": COND_DIST, "endConditionValue": float(st["m"]),
                "preferredEndConditionUnit": METER, "targetType": NO_TARGET,
                "strokeType": FREE, "equipmentType": EQUIP.get(st.get("eq"), NO_EQUIP),
                "description": _pace_note(st, css)[:250],
            }
            if st.get("lo") is not None:
                step.update(_pace_target(css + st["lo"], css + st["hi"]))
            out.append(step)
    return out


def _duration(steps: list, css: int) -> int:
    """Grobe Dauer in Sekunden (Strecken mit CSS+5 s, Pausen exakt, Lap-Erholung 7 min)."""
    s = 0
    for st in steps:
        if st["t"] == "rep":
            s += st["n"] * _duration(st["steps"], css)
        elif st["t"] == "rest":
            s += st["s"]
        elif st["t"] == "rec":
            s += 420
        else:
            s += st["m"] / 100 * (css + 5)
    return int(s)


def _fill(text: str, css: int) -> str:
    """Ersetzt die §S±n§-Platzhalter aus dem Plantext durch echte Paces."""
    return re.sub(r"§S([+-]?\d+)§", lambda m: _mmss(css + int(m.group(1))), text)


def build_workout(week: dict, css: int, day: datetime.date) -> dict:
    return {
        "workoutName": f"{NAME_PREFIX} {day.strftime('%d.%m.')} {week['name']}",
        "description": (f"{_fill(week['text'], css)} | CSS {_mmss(css)} /100 m | {week['m']} m | "
                        "Garmin AI Coach")[:1000],
        "sportType": SPORT,
        "poolLength": float(POOL_LENGTH_M),
        "poolLengthUnit": METER,
        "estimatedDurationInSecs": _duration(week["steps"], css),
        "estimatedDistanceInMeters": float(week["m"]),
        "workoutSegments": [{
            "segmentOrder": 1, "sportType": SPORT,
            "poolLength": float(POOL_LENGTH_M), "poolLengthUnit": METER,
            "workoutSteps": _steps(week["steps"], css, [0], [0]),
        }],
    }


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _id(resp, *keys):
    if isinstance(resp, dict):
        for k in keys:
            if resp.get(k):
                return resp[k]
    return None


def export_upcoming(client, today: datetime.date = None, swim_done_this_week: bool = False) -> dict:
    """Legt die Schwimmeinheit der laufenden Woche (nur bis Donnerstag und nur,
    wenn diese Woche noch nicht geschwommen wurde) und der nächsten Woche in
    den Garmin-Kalender bzw. aktualisiert sie. Gibt eine Zusammenfassung für
    den Dashboard-Sensor zurück."""
    today = today or datetime.date.today()
    weeks = {w["w"]: w for w in _load(PLAN_FILE, [])}
    state = _load(STATE_FILE, {})
    css = current_css()
    monday = today - datetime.timedelta(days=today.weekday())
    targets = [monday + datetime.timedelta(days=7)]
    if today.weekday() <= 3 and not swim_done_this_week:
        targets.insert(0, monday)

    result = []
    for mon in targets:
        week = weeks.get(mon.isoformat())
        if not week:
            continue
        entry = state.get(week["w"]) or {}
        if entry.get("date"):
            day = datetime.date.fromisoformat(entry["date"])
        else:
            # Dienstag; ist der in der laufenden Woche schon vorbei: Donnerstag
            day = mon + datetime.timedelta(days=WEEKDAY)
            if day < today:
                day = mon + datetime.timedelta(days=3)
        payload = build_workout(week, css, day)
        sig = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        action = "unverändert"
        if entry.get("workout_id") and entry.get("sig") == sig:
            pass
        elif entry.get("workout_id"):
            # Neue CSS oder geänderter Plan. update_workout() gibt es erst in
            # neueren garminconnect-Versionen (Python >= 3.12); im Add-on-Image
            # (Python 3.11) daher: altes Workout löschen - das entfernt auch
            # den Kalendereintrag - und unten neu anlegen.
            try:
                if hasattr(client, "update_workout"):
                    client.update_workout(entry["workout_id"], payload)
                    action = "aktualisiert"
                else:
                    client.delete_workout(entry["workout_id"])
                    entry = {}
            except Exception as e:
                print(f"[garmin_swim] Aktualisieren von {entry.get('workout_id')} fehlgeschlagen ({e}) - lege neu an")
                entry = {}
        if not entry.get("workout_id"):
            resp = _upload(client, payload)
            wid = _id(resp, "workoutId")
            if not wid:
                raise RuntimeError(f"Garmin hat keine workoutId geliefert: {str(resp)[:200]}")
            sched = client.schedule_workout(wid, day.isoformat())
            entry = {"workout_id": wid,
                     "schedule_id": _id(sched, "workoutScheduleId", "scheduleId", "id"),
                     "date": day.isoformat()}
            action = "aktualisiert" if week["w"] in state else "neu im Kalender"
        entry.update({"sig": sig, "css": css, "name": week["name"], "m": week["m"]})
        state[week["w"]] = entry
        result.append({"date": entry.get("date", day.isoformat()), "name": week["name"],
                       "distance_m": week["m"], "action": action,
                       "workout_id": entry["workout_id"]})
        print(f"[garmin_swim] {day.isoformat()} {week['name']}: {action}")

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    return {"css": _mmss(css), "pool_m": POOL_LENGTH_M, "workouts": result,
            "updated": datetime.datetime.now().isoformat(timespec="minutes")}
