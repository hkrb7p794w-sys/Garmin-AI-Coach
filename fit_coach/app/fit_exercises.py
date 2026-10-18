"""Liest einzelne Kraft-Übungen (Satz/Wiederholungen/Gewicht je Übung) einer
Aktivität über Garmins offizielle exerciseSets-API.

Hintergrund (siehe auch claude/status-und-plan.md): Die einfache
Aktivitätsliste (`get_activities`) liefert für Krafttraining nur
Aggregatwerte (total_sets/total_reps/total_volume). Die erste Implementierung
dieses Moduls (v0.10.0) hat deshalb versucht, die Original-FIT-Datei der
Aktivität herunterzuladen (`download_activity(..., dl_fmt=ORIGINAL)`) und
selbst zu parsen (`fitparse`) - ungetestet gegen eine echte Kraft-FIT-Datei,
weil weder eine öffentliche Testdatei noch der echte Quellcode von
cyberjunky/python-garminconnect erreichbar war. Am ersten echten Sync zeigte
sich, dass dieser Ansatz tatsächlich unbrauchbare Ergebnisse lieferte: von 4
Kraft-Einheiten zeigten 2 gar keine Übungen, die anderen 2 nur
"Übung (Code (None, None, None))" ohne jede Gewichtsangabe - fitparse konnte
die Übungs-Enums nicht auflösen.

Nachdem das Repo als Projekt-Quelle synchronisiert wurde (project instructions:
"Validiere deine Ergebnisse solange gegen öffentliche Quellen"), zeigt der
echte Quellcode einen direkteren, robusteren Weg: `Garmin.get_activity_
exercise_sets(activity_id)` ruft GET .../activity-service/activity/{id}/
exerciseSets auf und bekommt die von Garmin bereits aufgelösten Übungsdaten
als JSON zurück - dieselbe Antwortstruktur, die `set_activity_exercise_sets()`
laut eigenem Docstring als Payload zum Zurückschreiben erwartet (Replace-All-
Semantik). Kein FIT-Download, kein ZIP-Handling, kein fitparse mehr nötig.
Der Dateiname `fit_exercises.py` blieb aus Kompatibilitätsgründen (Import in
app.py) bestehen, macht inhaltlich aber keinen FIT-Umweg mehr.

Übungsnamen kommen von Garmin als `category`/`name`-Enum-Paar (z.B.
category="PULL_UP", name="LAT_PULLDOWN") - laut Docstring von
`set_activity_exercise_sets()` validiert Garmin `exercises[].category` und
`exercises[].name` gegen sein FIT-Enum, `name` darf leer sein. Aufgelöst
werden sie in Klartext über den mitgelieferten Übungskatalog
`garminconnect.exercises` (1527 Übungen, 47 Kategorien, Teil desselben
Pakets) - fehlt der Katalog (z.B. sehr alte garminconnect-Version), wird
ersatzweise die Kategorie selbst als Name verwendet.

WICHTIG: Die genauen JSON-Feldnamen INNERHALB eines einzelnen Satzes für
Wiederholungen/Gewicht (z.B. `repetitionCount` vs. `reps`, `weight` in Gramm
vs. Kilogramm) sind NICHT durch eine echte Beispielantwort oder einen Unit-
Test mit Feldnamen aus dem Repo bestätigt - dazu gab es keinen Treffer bei
der Recherche, nur der Hinweis auf die grobe Struktur aus dem PUT-Docstring.
Deshalb werden mehrere plausible Feldnamen probiert (siehe `_first_present`)
und die Gewichts-Einheit heuristisch erkannt (siehe `_normalize_weight`).
Bitte nach dem nächsten Sync die Attribute von
`sensor.garmin_ai_coach_garmin_krafttraining_uebungen` prüfen - falls
Wiederholungen/Gewicht leer oder offensichtlich falsch skaliert sind, bitte
kurz Rückmeldung mit den rohen Werten geben, dann lässt sich das gezielt
nachschärfen.
"""

try:
    from garminconnect import exercises as _exercise_catalog
except Exception:
    _exercise_catalog = None

_CATALOG = {}
for _e in getattr(_exercise_catalog, "EXERCISES", []) or []:
    try:
        _CATALOG[(_e.get("category"), _e.get("exercise") or "")] = _e.get("name")
    except AttributeError:
        continue


def _first_present(d: dict, *keys):
    """Erster vorhandener, nicht-None-Wert unter mehreren möglichen
    Feldnamen - Absicherung gegen unbekannte Feldbenennung (siehe Modul-
    Docstring)."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _normalize_weight(raw):
    """Garmin speichert Zielgewichte in Workout-DEFINITIONEN nachweislich als
    Gramm (siehe workout.py: weightValue = kg * 1000, weightUnit=kilogram).
    Ob dieselbe Konvention für AUFGEZEICHNETE exerciseSets gilt, ist nicht
    bestätigt. Heuristik: Werte > 500 werden als Gramm interpretiert (ein
    Trainingsgewicht von > 500 kg ist praktisch ausgeschlossen)."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return round(value / 1000.0, 1) if value > 500 else round(value, 1)


def _exercise_label(category, name) -> str:
    if not category and not name:
        return "Unbekannte Übung"
    label = _CATALOG.get((category, name or ""))
    if label:
        return label
    if category:
        base = str(category).replace("_", " ").title()
        return f"{base} ({name})" if name else base
    return f"Übung ({name})"


def parse_exercise_sets(data) -> list:
    """Wandelt die Antwort von `Garmin.get_activity_exercise_sets()` in
    `[{"exercise": str, "sets": [{"reps": int|None, "weight_kg": float|None}, ...]}, ...]`
    um. Pausen-Einträge (setType/type == 'REST') werden gefiltert. Robust
    gegenüber unbekannten/fehlenden Feldern - liefert im Zweifel [] statt
    eine Exception zu werfen (siehe _safe_fetch-Philosophie in app.py)."""
    try:
        raw_sets = (data or {}).get("exerciseSets") or []
        exercises_out = []
        current = None
        for s in raw_sets:
            if not isinstance(s, dict):
                continue
            set_type = str(s.get("setType") or s.get("type") or "").upper()
            if set_type == "REST":
                continue
            ex_list = s.get("exercises") or []
            first = ex_list[0] if ex_list and isinstance(ex_list[0], dict) else {}
            category = first.get("category") or s.get("category")
            name = first.get("name") or s.get("exerciseName")
            label = _exercise_label(category, name)
            reps = _first_present(s, "repetitionCount", "reps", "repCount")
            weight = _normalize_weight(_first_present(s, "weight", "weightValue", "volume"))
            entry = {"reps": reps, "weight_kg": weight}
            if current and current["exercise"] == label:
                current["sets"].append(entry)
            else:
                current = {"exercise": label, "sets": [entry]}
                exercises_out.append(current)
        return exercises_out
    except Exception as e:
        print(f"[fit_exercises] Konnte exerciseSets-Antwort nicht auswerten: {e}")
        return []


def get_strength_exercises(client, activity_id) -> list:
    """Ruft Garmins exerciseSets-Endpunkt für eine Aktivität ab und wandelt
    die Antwort in eine übungsweise gruppierte Satzliste um. Ein zusätzlicher
    Garmin-Call pro NEUER Kraft-Aktivität - wird in app.py deshalb dauerhaft
    gecacht, nicht bei jedem Sync erneut abgefragt."""
    try:
        data = client.get_activity_exercise_sets(activity_id)
    except Exception as e:
        print(f"[fit_exercises] exerciseSets-Abruf fehlgeschlagen (activity {activity_id}): {e}")
        return []
    return parse_exercise_sets(data)
