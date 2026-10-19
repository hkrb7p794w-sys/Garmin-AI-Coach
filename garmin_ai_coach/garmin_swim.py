"""Schwimmeinheiten aus dem Saisonplan als strukturierte Garmin-Workouts.

Bei jedem Sync legt das Add-on die Schwimmeinheiten der laufenden und der
nächsten Woche in den Garmin-Connect-Kalender (Dienstag; ist der in der
laufenden Woche schon vorbei: Donnerstag). Von dort landen sie
beim nächsten Uhren-Sync auf der Uhr - mit Einzelstrecken, Pausen und Ziel-Pace
(echtes Schritt-Ziel: Pace aus der Dashboard-CSS + CSS-Offset, nicht als Notiz).

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
import os, re, json, math, datetime, hashlib

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
CSS_OFFSET_TARGET = {"workoutTargetTypeId": 17, "workoutTargetTypeKey": "swim.css.offset", "displayOrder": 17}
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
    """Notiz je Schritt. Die Pace selbst steht als echtes Ziel im Schritt
    (siehe _pace_target) und nur noch im Rückfall zusätzlich in der Notiz."""
    return step.get("note", "")


def garmin_css(client, today: datetime.date = None):
    """CSS, die Garmin für die Uhr hinterlegt hat (s/100 m) - Bezugswert des
    CSS-Offset-Ziels. GraphQL criticalSwimSpeedScalar liefert mm/s
    (Alex 19.10.2026: 741 -> 2:15). None, wenn nicht lesbar."""
    today = today or datetime.date.today()
    q = (f'query{{criticalSwimSpeedScalar(startDate:"{today - datetime.timedelta(days=365)}", '
         f'endDate:"{today}")}}')
    try:
        data = client.query_garmin_graphql({"query": q})
        lst = (data.get("data") or {}).get("criticalSwimSpeedScalar") or {}
        lst = lst.get("criticalSwimSpeedDTOList") or []
        last = max(lst, key=lambda d: d.get("measurementTimestampGMT") or "")
        css = round(100 / (float(last["criticalSwimSpeed"]) / 1000))
        return css if 60 <= css <= 300 else None
    except Exception as e:
        print(f"[garmin_swim] Garmin-CSS nicht lesbar ({e}) - CSS-Offset bezieht sich auf die Dashboard-CSS")
        return None


def _pace_target(css: int, lo: int, hi: int, gcss: int = None) -> dict:
    """Ziel-Pace als echte Schritt-Ziele auf der Uhr (keine Notiz).

    Garmin-Connect-Editor bei Schwimm-Schritten (gegengeprüft am
    gespeicherten Workout-JSON, 19.10.2026):
      * "Primäres Ziel" = targetType "pace.zone" (Werte in m/s, langsam =
        Wert 1) - absolute Pace aus der getesteten Dashboard-CSS.
      * "Intensitätsziel" = secondaryTargetType "swim.css.offset" (id 17,
        Wert 1 = Sekunden-Offset zur CSS, Wert 2 leer) - genau so legt der
        Editor "CSS-basierte Zielpace" an (eigenes Workout "CSS 100er").
    Der CSS-Offset bezieht sich auf die CSS, die Garmin hinterlegt hat
    (gcss, bei Alex 2:15 statt getestet 2:10). Darum wird er wie im Garmin-
    Editor auf die absolute Ziel-Pace umgerechnet (2:12 bei Garmin-CSS 2:15
    -> "CSS -3 s"), sonst zeigte die Uhr zwei verschiedene Paces. Ohne
    Garmin-CSS: Offset zur Dashboard-CSS. Eine einzelne Ziel-Pace bekommt im primären Ziel
    ±2 s Spielraum, damit die Uhr nicht bei jeder Bahn piept."""
    fast_s, slow_s = css + lo, css + hi
    offset = math.floor((fast_s + slow_s) / 2 - gcss + 0.5) if gcss else (lo + hi) // 2
    if fast_s == slow_s:
        fast_s, slow_s = fast_s - 2, slow_s + 2
    return {"targetType": PACE_TARGET,
            "targetValueOne": round(100 / slow_s, 4),
            "targetValueTwo": round(100 / fast_s, 4),
            "secondaryTargetType": CSS_OFFSET_TARGET,
            "secondaryTargetValueOne": float(offset)}


def _pace_text(v_slow: float, v_fast: float) -> str:
    slow, fast = round(100 / v_slow), round(100 / v_fast)
    return f"{_mmss(fast)}-{_mmss(slow)} /100 m"


def _strip_targets(steps: list, keep_primary: bool) -> list:
    """Rückfall, falls Garmin den Upload ablehnt: erst nur ohne CSS-Offset,
    dann ganz ohne Pace-Ziel - dann steht die Pace wenigstens in der Notiz."""
    out = []
    for st in steps:
        st = dict(st)
        if st.get("workoutSteps"):
            st["workoutSteps"] = _strip_targets(st["workoutSteps"], keep_primary)
        if st.get("secondaryTargetType") == CSS_OFFSET_TARGET:
            st.pop("secondaryTargetType")
            st.pop("secondaryTargetValueOne", None)
        if not keep_primary and st.get("targetType") == PACE_TARGET:
            pace = _pace_text(st.pop("targetValueOne"), st.pop("targetValueTwo"))
            st["targetType"] = NO_TARGET
            st["description"] = (f"@ {pace} - " + st.get("description", "")).rstrip(" -")[:250]
        out.append(st)
    return out


def _key(t) -> str:
    return (t or {}).get("workoutTargetTypeKey") or ""


def _pace_steps(steps: list) -> list:
    """Alle Schritte (auch in Wiederholungen) mit Pace- oder CSS-Ziel."""
    out = []
    for st in steps or []:
        if st.get("workoutSteps"):
            out += _pace_steps(st["workoutSteps"])
        elif _key(st.get("targetType")) == "pace.zone" or _key(st.get("secondaryTargetType")) == "swim.css.offset":
            out.append(st)
    return out


def verify_targets(client, workout_id, payload: dict) -> str:
    """Liest das gespeicherte Workout zurück und prüft, ob Garmin die Ziele
    behalten hat (Garmin verwirft unbekannte Felder still)."""
    sent = _pace_steps(payload["workoutSegments"][0]["workoutSteps"])
    if not sent:
        return "ohne Pace-Ziel"
    try:
        stored = client.get_workout_by_id(workout_id)
        stored = _pace_steps((stored.get("workoutSegments") or [{}])[0].get("workoutSteps"))
    except Exception as e:
        return f"Prüfung nicht möglich ({e})"
    pace = [st for st in stored if _key(st.get("targetType")) == "pace.zone" and st.get("targetValueOne")]
    css = [st for st in stored if _key(st.get("secondaryTargetType")) == "swim.css.offset"]
    if not pace:
        return f"Pace-Ziel NICHT übernommen (0/{len(sent)} Schritte)"
    st = pace[0]
    msg = f"Pace-Ziel ok ({len(pace)}/{len(sent)}, {_pace_text(st['targetValueOne'], st['targetValueTwo'])}"
    if css:
        msg += f", CSS {css[0].get('secondaryTargetValueOne', 0):+.0f} s"
    return msg + ")"


def _upload(client, payload: dict) -> dict:
    try:
        return client.upload_workout(payload)
    except Exception as e:
        print(f"[garmin_swim] Upload mit CSS-Ziel abgelehnt ({e}) - versuche es nur mit Pace-Ziel")
    seg = dict(payload["workoutSegments"][0])
    try:
        return client.upload_workout(dict(payload, workoutSegments=[
            dict(seg, workoutSteps=_strip_targets(seg["workoutSteps"], keep_primary=True))]))
    except Exception as e:
        print(f"[garmin_swim] Upload mit Pace-Ziel abgelehnt ({e}) - Pace nur als Notiz")
    return client.upload_workout(dict(payload, workoutSegments=[
        dict(seg, workoutSteps=_strip_targets(seg["workoutSteps"], keep_primary=False))]))


def _steps(steps: list, css: int, order: list, groups: list, child=None, gcss: int = None) -> list:
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
                "workoutSteps": _steps(st["steps"], css, order, groups, gid, gcss),
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
                step.update(_pace_target(css, st["lo"], st["hi"], gcss))
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


def build_workout(week: dict, css: int, day: datetime.date, gcss: int = None) -> dict:
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
            "workoutSteps": _steps(week["steps"], css, [0], [0], gcss=gcss),
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
    gcss = garmin_css(client, today)
    if gcss and gcss != css:
        print(f"[garmin_swim] Garmin-CSS {_mmss(gcss)} weicht von der Dashboard-CSS {_mmss(css)} ab - "
              "CSS-Offsets werden auf die Dashboard-Paces umgerechnet")
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
        payload = build_workout(week, css, day, gcss)
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
                    entry["target_check"] = verify_targets(client, entry["workout_id"], payload)
                    print(f"[garmin_swim] {day.isoformat()} {week['name']}: {entry['target_check']}")
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
            check = verify_targets(client, wid, payload)
            print(f"[garmin_swim] {day.isoformat()} {week['name']}: {check}")
            entry = {"workout_id": wid, "target_check": check,
                     "schedule_id": _id(sched, "workoutScheduleId", "scheduleId", "id"),
                     "date": day.isoformat()}
            action = "aktualisiert" if week["w"] in state else "neu im Kalender"
        entry.update({"sig": sig, "css": css, "name": week["name"], "m": week["m"]})
        state[week["w"]] = entry
        result.append({"date": entry.get("date", day.isoformat()), "name": week["name"],
                       "distance_m": week["m"], "action": action,
                       "workout_id": entry["workout_id"],
                       "target_check": entry.get("target_check", "")})
        print(f"[garmin_swim] {day.isoformat()} {week['name']}: {action}")

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    return {"css": _mmss(css), "garmin_css": _mmss(gcss) if gcss else None, "pool_m": POOL_LENGTH_M, "workouts": result,
            "updated": datetime.datetime.now().isoformat(timespec="minutes")}
