"""Extrahiert einzelne Kraft-Uebungen (Satz/Wiederholungen/Gewicht je Uebung)
aus der Original-FIT-Datei einer Aktivitaet.

Hintergrund: Die normale Garmin-Connect-API (garminconnect-Paket) liefert fuer
Krafttraining nur Aggregatwerte auf Aktivitaets-Ebene (total_sets/total_reps/
total_volume) - NICHT, welche Uebung wann mit wie vielen Wiederholungen/wie
viel Gewicht gemacht wurde. Diese Detailinfo steckt nur in der Original-FIT-
Datei, die das Geraet beim Training aufzeichnet:
  - Mesg 225 "set": ein Eintrag je Satz (repetitions, weight, set_type, ...)
  - Mesg 264 "exercise_title": Uebungs-Katalog des Workouts (exercise_name, ...)
Der Weg dahin: client.download_activity(activity_id, dl_fmt=ORIGINAL) liefert
die Originaldatei des Geraets als ZIP-Bytes (bei Watch-Aufzeichnungen: eine
.fit-Datei darin); die muss vor dem Parsen entzippt werden.

WICHTIG (Stand v0.10.0): Diese Extraktion ist Best-Effort und konnte NICHT
gegen eine echte Kraft-FIT-Datei getestet werden (keine oeffentlich verfuegbare
Testdatei gefunden, und in dieser Umgebung war weder PyPI noch das GitHub-Repo
des Athleten erreichbar). Bekannte Einschraenkungen laut Garmin-Dokumentation/
-Forum:
  - Uebungsdetails werden nur geschrieben, wenn die automatische Satz-/
    Wiederholungserkennung der Uhr waehrend des Trainings aktiv war.
  - Nachtraegliche Korrekturen in der Garmin-Connect-App (z.B. Uebung im
    Nachhinein umbenannt) spiegeln sich NICHT in der Original-FIT-Datei wider.
  - Garmin kodiert Uebungsnamen ueber category/category_subtype-Enums aus einer
    sehr grossen separaten Lookup-Tabelle, die NICHT Teil des Kern-FIT-Profils
    ist - falls fitparse diese Werte nicht in Klartext aufloesen kann, liefert
    dieses Modul einen Platzhalter ("Uebung (Code <n>)") statt eines Namens.

Jeder Fehler wird abgefangen -> [] statt den Sync abzubrechen (siehe
_safe_fetch-Philosophie in app.py). Nach dem ersten echten Sync bitte die
Attribute von sensor.garmin_ai_coach_strength_exercises in Home Assistant
(Entwicklerwerkzeuge -> Zustaende) pruefen und Rueckmeldung geben, ob echte
Uebungsnamen oder nur Codes ankommen - danach kann diese Zuordnung bei Bedarf
nachgeschaerft werden.
"""
import io
import zipfile

try:
    from fitparse import FitFile
    FITPARSE_AVAILABLE = True
except ImportError:
    FITPARSE_AVAILABLE = False


def _extract_fit_bytes(raw: bytes) -> bytes:
    """download_activity(..., dl_fmt=ORIGINAL) liefert bei Geraete-Aufzeichnungen
    ein ZIP mit der .fit-Datei darin. Manche Aktivitaeten (z.B. manuell in der
    App angelegte, oder von Drittanbieter-Apps importierte) haben keine
    Original-FIT-Datei bzw. ein anderes Format - dann roh zurueckgeben und das
    Parsen weiter unten kontrolliert fehlschlagen lassen."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            fit_names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if not fit_names:
                raise ValueError(
                    f"Kein .fit im ZIP enthalten (Inhalt: {zf.namelist()}) - "
                    "vermutlich kein Original-Geraete-Export fuer diese Aktivitaet"
                )
            return zf.read(fit_names[0])
    return raw


def _exercise_label(msg) -> str | None:
    """Best-effort lesbarer Uebungsname aus einer 'set'- oder
    'exercise_title'-FIT-Message. Siehe Modul-Docstring zur Enum-Problematik."""
    for field_name in ("exercise_name", "wkt_step_name"):
        val = msg.get_value(field_name)
        if isinstance(val, str) and val.strip():
            return val.strip().replace("_", " ").title()
    subtype = msg.get_value("category_subtype")
    category = msg.get_value("category")
    if isinstance(subtype, str) and subtype.strip():
        return subtype.replace("_", " ").title()
    if isinstance(category, str) and category.strip():
        return category.replace("_", " ").title()
    if subtype is not None:
        return f"Uebung (Code {subtype})"
    if category is not None:
        return f"Uebung (Code {category})"
    return None


def parse_strength_sets(raw_download: bytes) -> list:
    """Liefert pro erkannter Uebung eine Liste von Saetzen:
    [{"exercise": str, "sets": [{"reps": int|None, "weight_kg": float|None}, ...]}, ...]

    Reine Pausen-Eintraege (set_type == 'rest') werden ausgefiltert. Gibt []
    zurueck, wenn fitparse fehlt, das Format nicht passt, oder die FIT-Datei
    keine 'set'-Messages enthaelt (z.B. weil die Auto-Erkennung aus war)."""
    if not FITPARSE_AVAILABLE:
        print("[fit_exercises] fitparse nicht installiert, ueberspringe Uebungs-Details")
        return []
    try:
        fit_bytes = _extract_fit_bytes(raw_download)
        fitfile = FitFile(io.BytesIO(fit_bytes))
        # Einmal vollstaendig einlesen (statt get_messages() mehrfach mit
        # unterschiedlichem Filter aufzurufen) - robuster gegenueber Details der
        # fitparse-internen Lazy-Parsing-Reihenfolge.
        all_messages = list(fitfile.get_messages())

        # exercise_title-Messages nach message_index indizieren (Uebungs-Katalog
        # des Workouts, falls das Geraet ihn mitschreibt).
        titles_by_index = {}
        for msg in all_messages:
            if msg.name != "exercise_title":
                continue
            idx = msg.get_value("message_index")
            label = _exercise_label(msg)
            if idx is not None and label:
                titles_by_index[idx] = label

        exercises = []  # Liste statt Dict: erhaelt die Reihenfolge, falls
                         # dieselbe Uebung mehrfach im Workout vorkommt (z.B.
                         # als zweiter Satzblock nach einer anderen Uebung).
        current = None
        for msg in all_messages:
            if msg.name != "set":
                continue
            set_type = msg.get_value("set_type")
            if isinstance(set_type, str) and set_type.lower() == "rest":
                continue
            step_idx = msg.get_value("wkt_step_index")
            label = titles_by_index.get(step_idx) or _exercise_label(msg) or "Unbekannte Uebung"
            set_entry = {
                "reps": msg.get_value("repetitions"),
                "weight_kg": msg.get_value("weight"),
            }
            if current and current["exercise"] == label:
                current["sets"].append(set_entry)
            else:
                current = {"exercise": label, "sets": [set_entry]}
                exercises.append(current)
        return exercises
    except Exception as e:
        print(f"[fit_exercises] Konnte Uebungsdetails nicht extrahieren: {e}")
        return []


def get_strength_exercises(client, activity_id) -> list:
    """Laedt die Original-Datei einer Aktivitaet von Garmin und extrahiert die
    einzelnen Uebungen/Saetze daraus. Ein zusaetzlicher HTTPS-Call an Garmin -
    wird deshalb in app.py nur fuer NEUE Kraft-Aktivitaeten der laufenden Woche
    aufgerufen und dauerhaft gecacht, nicht bei jedem Sync neu."""
    try:
        raw = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
    except Exception as e:
        print(f"[fit_exercises] Download der Original-Datei fehlgeschlagen (activity {activity_id}): {e}")
        return []
    return parse_strength_sets(raw)
