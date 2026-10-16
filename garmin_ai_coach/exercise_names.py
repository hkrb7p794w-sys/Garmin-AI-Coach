"""Vereinheitlicht Übungsnamen aus Garmin Connect (seit v0.21.0).

Problem: Wer Kraft-Einheiten nachträglich in der Garmin-App bearbeitet, wählt
für dieselbe Übung nicht immer denselben Katalogeintrag. Aus „Lateral Raise“,
„Lateral Raise (ONE_ARM_CABLE_LATERAL_RAISE)“ oder „Lateral Raise
(CABLE_FRONT_RAISE)“ wird in der Auswertung dann scheinbar jedes Mal eine
andere Übung - Fortschritt und Gewichtshinweise zerfallen in Einzelteile.

Lösung: Jeder Garmin-Name (Kategorie + Enum, z. B. "Row (SEATED_CABLE_ROW)")
wird über eine geordnete Regelliste auf eine KANONISCHE Übung abgebildet
(id, deutscher Anzeigename, Muskelgruppe, Wiederholungsbereich für die
Progression). Die Zuordnung erfolgt erst bei der Auswertung, der Cache hält
weiter die Rohnamen - Regeländerungen wirken deshalb rückwirkend.

Grundsätze:
- Zusammengelegt wird nur, was nach Bewegungsmuster dieselbe Übung ist und
  sich bei der Namenswahl in Garmin nachweislich vermischt (Latziehen-Varianten,
  Seitheben, Hammer-Curls, Bizeps-Curls an Stange/Kabel, Beinstrecker, ...).
- Langhantel- und Kurzhantel-Varianten derselben Bewegung bleiben getrennt,
  weil die Gewichte nicht vergleichbar sind (Bankdrücken 50 kg vs. 2 × 20 kg).
- Spezifischer Teil-Name schlägt die Garmin-Kategorie: „Squat (LEG_PRESS)“ ist
  eine Beinpresse, „Crunch (WEIGHTED_LEG_EXTENSIONS)“ ein Beinstrecker,
  „Lateral Raise (CABLE_FRONT_RAISE)“ ein Frontheben.
- Mehrdeutige Rohnamen ohne Enum („Row“, „Flye“, „Curl“, „Pull Up“ mit
  Zusatzgewicht) werden mit einer begründeten Annahme zugeordnet und als
  `assumed` markiert - das Dashboard listet diese Annahmen zur Kontrolle.
- Eigene Korrekturen ohne Add-on-Update: Datei
  /share/garmin_ai_coach/exercise_aliases.json, z. B.
  {"aliases": {"CABLE_HAMMER_CURL": "hammer_curl", "FLYE": "reverse_fly"},
   "ignore": ["PLANK"]}
  Schlüssel = Textteil des Garmin-Namens (Groß-/Kleinschreibung egal),
  Wert = id aus RULES oder ein freier Anzeigename.
"""
import os
import re
import json

USER_ALIAS_FILE = os.environ.get("EXERCISE_ALIAS_FILE", "/share/garmin_ai_coach/exercise_aliases.json")

# id, Anzeigename, Gruppe, Muster (gegen den normalisierten Schlüssel),
# Wiederholungsbereich (unten, oben), Verbundübung, Mindest-Hantelstufe (kg),
# Lastzuwachs in % für den nächsten Schritt, Bedingung "weighted"
# (True = nur mit Zusatzgewicht, False = nur ohne, None = egal), angenommen?
#
# Wiederholungsbereiche: Verbundübungen 6-10, Isolation 8-12, Rumpf/Waden
# 10-15 (übliche Doppel-Progressions-Bereiche; ACSM 2009 empfiehlt für
# Muskelaufbau den 6-12-RM-Bereich). Der Bereich ist ein Planungswert, keine
# Messgröße - im Dashboard als „Ziel“ gekennzeichnet.
_R = []


def _rule(id_, name, group, pattern, reps=(8, 12), compound=False, step=2.5, pct=2.5,
          weighted=None, assumed=False, bodyweight_reps=None):
    _R.append({
        "id": id_, "name": name, "group": group, "pattern": re.compile(pattern),
        "reps": reps, "compound": compound, "step": step, "pct": pct,
        "weighted": weighted, "assumed": assumed, "bodyweight_reps": bodyweight_reps,
    })


# --- Beine (zuerst: Garmin-Kategorien sind hier oft falsch) ----------------
_rule("beinpresse", "Beinpresse", "Beine", r"LEG_PRESS", (6, 12), True, 5.0, 5.0)
_rule("beinstrecken", "Beinstrecken", "Beine", r"LEG_EXTENSION", (10, 15), False, 2.5, 5.0)
_rule("beinbeugen", "Beinbeugen", "Beine", r"LEG_CURL", (8, 12), False, 2.5, 5.0)
_rule("rumaenisches_kreuzheben", "Rumänisches Kreuzheben", "Beine",
      r"ROMANIAN|STIFF_LEG", (6, 10), True, 2.5, 5.0)
_rule("kreuzheben", "Kreuzheben", "Beine", r"DEADLIFT", (5, 8), True, 5.0, 5.0)
_rule("ausfallschritt", "Ausfallschritte", "Beine", r"LUNGE|SPLIT_SQUAT|STEP_UP", (8, 12), True, 2.5, 5.0)
_rule("kniebeuge", "Kniebeuge", "Beine", r"SQUAT", (6, 10), True, 2.5, 5.0)
_rule("wadenheben", "Wadenheben", "Beine", r"CALF", (10, 15), False, 2.5, 5.0)
_rule("hueftstoss", "Hüftstoß", "Beine", r"HIP_THRUST|GLUTE_BRIDGE|HIP_RAISE", (8, 12), True, 5.0, 5.0)

# --- Rumpf -----------------------------------------------------------------
_rule("plank", "Plank", "Rumpf", r"PLANK", (1, 1), False, 2.5, 0.0, bodyweight_reps=False)
_rule("pallof", "Pallof Press", "Rumpf", r"PALLOF", (10, 15), False, 2.5, 2.5)
_rule("rotation", "Rumpfrotation", "Rumpf", r"RUSSIAN_TWIST|WOOD_?CHOP|ROTATION", (10, 15), False, 2.5, 2.5)
_rule("beinheben", "Beinheben", "Rumpf", r"LEG_RAISE|KNEE_RAISE|HANGING", (10, 15), False, 2.5, 2.5)
_rule("crunch", "Crunch", "Rumpf", r"CRUNCH|SIT_UP", (10, 15), False, 2.5, 2.5)

# --- Schultern / Rücken-Spezialfälle (vor den allgemeinen Rücken-Regeln) ---
_rule("reverse_fly", "Reverse Fly", "Schultern", r"REVERSE_FL|REAR_DELT", (10, 15), False, 1.0, 2.5)
_rule("face_pull", "Face Pull", "Schultern", r"FACE_PULL", (10, 15), False, 2.5, 2.5)
_rule("frontheben", "Frontheben", "Schultern", r"FRONT_RAISE", (8, 12), False, 1.0, 2.5)
_rule("seitheben", "Seitheben", "Schultern", r"LATERAL_RAISE", (10, 15), False, 1.0, 2.5)
_rule("aufrechtes_rudern", "Aufrechtes Rudern", "Schultern", r"UPRIGHT_ROW", (8, 12), False, 2.5, 2.5)
_rule("kurzhantel_schulterdruecken", "Kurzhantel-Schulterdrücken", "Schultern",
      r"DUMBBELL.*(SHOULDER_PRESS|OVERHEAD_PRESS)|ARNOLD", (6, 10), True, 2.5, 2.5)
_rule("schulterdruecken", "Schulterdrücken", "Schultern",
      r"OVERHEAD_PRESS|SHOULDER_PRESS|MILITARY", (6, 10), True, 2.5, 2.5)
_rule("shrugs", "Shrugs", "Schultern", r"SHRUG", (8, 12), False, 2.5, 2.5)

# --- Trizeps (vor Brust: „Triceps Extension (SUSPENDED_DIP)“ ist ein Dip) ---
_rule("dips", "Dips", "Trizeps", r"(^|_)DIPS?($|_)", (6, 12), True, 2.5, 2.5)
_rule("trizeps_pushdown", "Trizeps-Pushdown", "Trizeps", r"PUSHDOWN|PRESSDOWN|PRESS_DOWN", (8, 12), False, 2.5, 2.5)
_rule("trizepsstrecken", "Trizepsstrecken", "Trizeps",
      r"TRICEPS|SKULL|KICKBACK", (8, 12), False, 2.5, 2.5)

# --- Bizeps -----------------------------------------------------------------
_rule("handgelenk_curl", "Handgelenk-Curl", "Unterarme", r"WRIST_CURL", (10, 15), False, 1.0, 2.5)
_rule("hammer_curl", "Hammer Curl", "Bizeps", r"HAMMER_CURL", (8, 12), False, 2.5, 2.5)
_rule("kurzhantel_curl", "Kurzhantel-Curl", "Bizeps", r"DUMBBELL.*CURL|CURL.*DUMBBELL", (8, 12), False, 1.0, 2.5)
_rule("bizeps_curl", "Bizeps-Curl", "Bizeps", r"CURL", (8, 12), False, 2.5, 2.5)

# --- Brust --------------------------------------------------------------------
_rule("kurzhantel_schraegbankdruecken", "Kurzhantel-Schrägbankdrücken", "Brust",
      r"INCLINE.*DUMBBELL|DUMBBELL.*INCLINE", (6, 10), True, 2.5, 2.5)
_rule("schraegbankdruecken", "Schrägbankdrücken", "Brust", r"INCLINE.*(BENCH|PRESS)", (6, 10), True, 2.5, 2.5)
_rule("kurzhantel_bankdruecken", "Kurzhantel-Bankdrücken", "Brust",
      r"DUMBBELL_(BENCH|CHEST|PRESS)|DUMBBELL.*BENCH_PRESS", (6, 10), True, 2.5, 2.5)
_rule("brustpresse", "Brustpresse", "Brust", r"CHEST_PRESS|MACHINE_PRESS", (8, 12), True, 5.0, 2.5)
_rule("bankdruecken", "Bankdrücken", "Brust", r"BENCH_PRESS|BENCH$", (6, 10), True, 2.5, 2.5)
_rule("liegestuetze", "Liegestütze", "Brust", r"PUSH_UP|PUSHUP", (8, 20), False, 2.5, 2.5, bodyweight_reps=True)
_rule("fliegende", "Fliegende (Brust)", "Brust", r"(^|_)FLY(E|ES)?($|_)|PEC_DECK|CROSSOVER", (10, 15), False, 1.25, 2.5,
      assumed=False)

# --- Rücken -------------------------------------------------------------------
_rule("kabel_pullover", "Kabel-Pullover", "Rücken", r"PULLOVER", (10, 15), False, 2.5, 2.5)
_rule("latziehen", "Latziehen", "Rücken", r"PULLDOWN|PULL_DOWN", (6, 10), True, 2.5, 2.5)
# „Pull Up“ ohne Enum: mit Zusatzgewicht am Gerät = Latziehen (Annahme), sonst Klimmzug
_rule("latziehen", "Latziehen", "Rücken", r"^(PULL_UP|CHIN_UP)$", (6, 10), True, 2.5, 2.5,
      weighted=True, assumed=True)
_rule("klimmzug", "Klimmzug", "Rücken", r"PULL_UP|CHIN_UP", (5, 10), True, 2.5, 2.5, bodyweight_reps=True)
_rule("rudern_kurzhantel", "Kurzhantelrudern", "Rücken", r"DUMBBELL_ROW|ONE_ARM_ROW|SINGLE_ARM_ROW", (8, 12), True, 2.5, 2.5)
_rule("rudern_langhantel", "Langhantelrudern", "Rücken", r"BARBELL_ROW|BENT_OVER|T_BAR|PENDLAY", (6, 10), True, 2.5, 2.5)
_rule("rudern_kabel", "Rudern am Kabel", "Rücken", r"SEATED_CABLE_ROW|CABLE_ROW|SEATED_ROW|MACHINE_ROW", (6, 10), True, 2.5, 2.5)
# „Row“ ohne Enum: Annahme Kabelrudern (die Rudervariante im Pull-Tag)
_rule("rudern_kabel", "Rudern am Kabel", "Rücken", r"(^|_)ROW($|_)", (6, 10), True, 2.5, 2.5, assumed=True)

RULES = _R
RULES_BY_ID = {}
for _r in _R:
    RULES_BY_ID.setdefault(_r["id"], _r)

IGNORED_IDS = {"unbekannt"}
_UNKNOWN = {"id": "unbekannt", "name": "Unknown", "group": "Sonstige", "reps": (8, 12),
            "compound": False, "step": 2.5, "pct": 2.5, "weighted": None, "assumed": False,
            "bodyweight_reps": None}


def key_of(label) -> str:
    """„Row (SEATED_CABLE_ROW)“ -> „ROW_SEATED_CABLE_ROW“."""
    s = str(label or "").upper()
    s = re.sub(r"[()\-/,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().replace(" ", "_")
    return s


def _slug(text) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower().replace("ä", "ae").replace("ö", "oe")
               .replace("ü", "ue").replace("ß", "ss")).strip("_")
    return s or "uebung"


_user_cache = {"mtime": None, "data": {"aliases": {}, "ignore": []}}


def _user_aliases() -> dict:
    try:
        mtime = os.path.getmtime(USER_ALIAS_FILE)
    except OSError:
        return {"aliases": {}, "ignore": []}
    if _user_cache["mtime"] == mtime:
        return _user_cache["data"]
    try:
        with open(USER_ALIAS_FILE, encoding="utf-8") as f:
            raw = json.load(f) or {}
        data = {
            "aliases": {key_of(k): v for k, v in (raw.get("aliases") or {}).items() if v},
            "ignore": [key_of(k) for k in (raw.get("ignore") or [])],
        }
    except Exception as e:
        print(f"[exercise_names] {USER_ALIAS_FILE} nicht lesbar ({e}) - ignoriere Eigenkorrekturen")
        data = {"aliases": {}, "ignore": []}
    _user_cache["mtime"] = mtime
    _user_cache["data"] = data
    return data


def _has_weight(sets) -> bool:
    return any(isinstance(s.get("weight_kg"), (int, float)) and s.get("weight_kg") > 0 for s in (sets or []))


def classify(label, sets=None) -> dict:
    """Ordnet einen Garmin-Namen einer kanonischen Übung zu. Gibt eine Kopie
    der Regel zurück (id, name, group, reps, ...), plus `matched_by`:
    'eigene Zuordnung' | 'Regel' | 'Rückfall'."""
    key = key_of(label)
    if not key or key in ("UNKNOWN", "UNBEKANNT") or key.startswith("UEBUNG_CODE"):
        return dict(_UNKNOWN, matched_by="Regel")
    user = _user_aliases()
    for ign in user["ignore"]:
        if ign and ign in key:
            return dict(_UNKNOWN, matched_by="eigene Zuordnung")
    for needle, target in user["aliases"].items():
        if needle and needle in key:
            rule = RULES_BY_ID.get(str(target)) or RULES_BY_ID.get(_slug(target))
            if rule:
                return {k: v for k, v in rule.items() if k != "pattern"} | {"matched_by": "eigene Zuordnung", "assumed": False}
            return {"id": _slug(target), "name": str(target), "group": "Sonstige", "reps": (8, 12),
                    "compound": False, "step": 2.5, "pct": 2.5, "weighted": None, "assumed": False,
                    "bodyweight_reps": None, "matched_by": "eigene Zuordnung"}
    for rule in RULES:
        if rule["weighted"] is not None and sets is not None:
            if _has_weight(sets) != rule["weighted"]:
                continue
        elif rule["weighted"] is True and sets is None:
            continue
        if rule["pattern"].search(key):
            return {k: v for k, v in rule.items() if k != "pattern"} | {"matched_by": "Regel"}
    name = re.sub(r"\s+", " ", str(label)).strip()
    return {"id": _slug(name), "name": name, "group": "Sonstige", "reps": (8, 12), "compound": False,
            "step": 2.5, "pct": 2.5, "weighted": None, "assumed": False, "bodyweight_reps": None,
            "matched_by": "Rückfall"}


def group_of(label) -> str:
    return classify(label)["group"]


def canonical_sessions(sessions) -> list:
    """Wendet die Zuordnung auf Kraft-Sessions an (Cache- oder Publish-Format:
    [{date, activity_name, exercises:[{exercise, sets:[{reps, weight_kg}]}]}]).
    Gleiche Übungen innerhalb einer Einheit werden zusammengeführt. Jeder
    Eintrag behält die Garmin-Rohnamen (`garmin_names`) zur Kontrolle."""
    out = []
    for s in sessions or []:
        merged = {}
        order = []
        for ex in s.get("exercises") or []:
            label = ex.get("exercise")
            sets = ex.get("sets") or []
            c = classify(label, sets)
            if c["id"] in IGNORED_IDS:
                key = ("unbekannt", label)
                entry = merged.get(key)
                if entry is None:
                    entry = {"exercise": "Unknown", "id": "unbekannt", "group": "Sonstige",
                             "garmin_names": [label], "assumed": False, "sets": []}
                    merged[key] = entry
                    order.append(key)
                entry["sets"] = entry["sets"] + list(sets)
                continue
            key = (c["id"],)
            entry = merged.get(key)
            if entry is None:
                entry = {"exercise": c["name"], "id": c["id"], "group": c["group"],
                         "garmin_names": [], "assumed": bool(c.get("assumed")), "sets": []}
                merged[key] = entry
                order.append(key)
            if label and label not in entry["garmin_names"]:
                entry["garmin_names"].append(label)
            entry["assumed"] = entry["assumed"] or bool(c.get("assumed"))
            entry["sets"] = entry["sets"] + list(sets)
        new = {k: v for k, v in s.items() if k != "exercises"}
        new["exercises"] = [merged[k] for k in order]
        out.append(new)
    return out


def mapping_overview(sessions) -> list:
    """Welche Garmin-Rohnamen wurden zu welcher Übung zusammengeführt?
    [{id, name, group, garmin_names:[...], assumed, fallback}] - nur Übungen mit
    mehr als einem Rohnamen, angenommener Zuordnung oder Rückfall (also alles,
    was Alex kontrollieren sollte)."""
    seen = {}
    for s in sessions or []:
        for ex in s.get("exercises") or []:
            label = ex.get("exercise")
            c = classify(label, ex.get("sets") or [])
            if c["id"] in IGNORED_IDS:
                continue
            e = seen.setdefault(c["id"], {"id": c["id"], "name": c["name"], "group": c["group"],
                                          "garmin_names": [], "assumed": False, "fallback": False})
            if label and label not in e["garmin_names"]:
                e["garmin_names"].append(label)
            e["assumed"] = e["assumed"] or bool(c.get("assumed"))
            e["fallback"] = e["fallback"] or c["matched_by"] == "Rückfall"
    return [e for e in seen.values() if len(e["garmin_names"]) > 1 or e["assumed"] or e["fallback"]]
