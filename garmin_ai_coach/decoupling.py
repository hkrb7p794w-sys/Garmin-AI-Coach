"""Berechnet aerobe HF-Pace-Kopplung ("aerobic decoupling") fuer laengere,
gleichmaessige Laufeinheiten.

Siehe claude/konzept-erweiterung-metriken-v0.16-plus.md, Abschnitt 1.3.

Methode (Joe Friel / TrainingPeaks "Pa:HR decoupling", siehe
https://www.trainingpeaks.com/blog/aerobic-endurance-and-decoupling/):
Die Einheit wird nach zurueckgelegter Distanz (nicht nach Rundenzahl - eine
kuerzere Schlussrunde soll das Ergebnis nicht verzerren) in zwei Haelften
geteilt. Je Haelfte wird ein Effizienzfaktor aus Geschwindigkeit und
Herzfrequenz gebildet:

    EF1 = Durchschnittsgeschwindigkeit erste Haelfte / Durchschnitts-HF erste Haelfte
    EF2 = Durchschnittsgeschwindigkeit zweite Haelfte / Durchschnitts-HF zweite Haelfte
    Entkopplung % = (EF1 - EF2) / EF1 * 100

Positive Werte: die HF steigt im Verlauf der Einheit relativ zur Pace
(Ermuedung bzw. fuer diese Dauer noch unzureichende aerobe Basis). Werte nahe
0 oder negativ: stabile Kopplung. Als grobe Faustregel gilt < 5% als gute
aerobe Basis fuer die jeweilige Dauer - eine Orientierung, keine exakte,
wissenschaftlich scharf abgegrenzte Kennzahl.

WICHTIG (Datenunsicherheit, analog zur exerciseSets-Vorsicht in v0.10.1):
Garmin.get_activity_splits() liefert laut python-garminconnect-Quellcode ein
dict; das genaue Feld fuer die Rundenliste ("lapDTOs") sowie die Feldnamen je
Runde sind nicht durch eine echte Beispielantwort belegt. Die Extraktion
unten ist deshalb bewusst defensiv (mehrere plausible Feldnamen) und liefert
{} statt eines erfundenen Werts, wenn sich keine verwertbaren Runden finden
lassen. Nach dem ersten echten Sync mit qualifizierender Lauf-Einheit bitte
die Attribute von sensor.garmin_ai_coach_garmin_hf_pace_kopplung
(Entwicklerwerkzeuge -> Zustaende) pruefen.
"""

# Nur laengere, gleichmaessige Laeufe eignen sich fuer diese Kennzahl -
# Intervall-/Schwellen-/VO2max-Einheiten haben absichtlich wechselnde
# Intensitaet, dort wuerde die Kennzahl nur Rauschen statt Ermuedung zeigen.
# Filterung ueber den Aktivitaetsnamen (best effort) plus eine Mindestdauer,
# unter der ein Entkopplungssignal ohnehin nicht belastbar waere. Diese
# Heuristik muss nach den ersten echten Syncs gegen reale Aktivitaetsnamen/
# -dauern geprueft werden (gleiche Vorsicht wie beim v0.10.0-FIT-Parsing).
EXCLUDED_NAME_KEYWORDS = ("intervall", "schwelle", "vo2max", "tempo")
MIN_DURATION_MIN = 35


def is_eligible_run(activity: dict) -> bool:
    """Grobfilter, ob eine Aktivitaet fuer die Entkopplungs-Berechnung infrage
    kommt - siehe Moduldocstring."""
    type_key = ((activity.get("activityType") or {}).get("typeKey", "") or "").lower()
    if "run" not in type_key:
        return False
    name = (activity.get("activityName") or "").lower()
    if any(kw in name for kw in EXCLUDED_NAME_KEYWORDS):
        return False
    duration_min = (activity.get("duration") or 0) / 60.0
    return duration_min >= MIN_DURATION_MIN


def _laps_from_splits(raw) -> list:
    """Extrahiert die Rundenliste aus Garmin.get_activity_splits() - siehe
    Moduldocstring zur Feldnamen-Unsicherheit."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [lap for lap in raw if isinstance(lap, dict)]
    if isinstance(raw, dict):
        laps = raw.get("lapDTOs")
        if isinstance(laps, list):
            return [lap for lap in laps if isinstance(lap, dict)]
    return []


def _lap_metrics(lap: dict):
    """(distanz_m, dauer_s, avg_hf) aus einem einzelnen Rundeneintrag -
    defensiv gegen mehrere plausible Feldnamen. None, wenn eine der drei
    Groessen fehlt oder nicht plausibel ist."""
    distance = lap.get("distance")
    duration = lap.get("duration") or lap.get("movingDuration") or lap.get("elapsedDuration")
    hr = lap.get("averageHR") or lap.get("avgHr") or lap.get("averageHeartRate")
    if not isinstance(distance, (int, float)) or distance <= 0:
        return None
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None
    if not isinstance(hr, (int, float)) or hr <= 0:
        return None
    return distance, duration, hr


def compute_decoupling(raw_splits) -> dict:
    """Berechnet die aerobe HF-Pace-Kopplung (siehe Moduldocstring) aus der
    Antwort von Garmin.get_activity_splits(). Gibt {} zurueck, wenn nicht
    genug verwertbare Runden vorliegen (z.B. keine HF je Runde) - die
    Aktivitaet wird dann einfach uebersprungen statt eine unbelastbare Zahl
    zu erfinden."""
    laps = []
    for lap in _laps_from_splits(raw_splits):
        metrics = _lap_metrics(lap)
        if metrics:
            laps.append(metrics)
    if len(laps) < 2:
        return {}

    total_distance = sum(d for d, _, _ in laps)
    if total_distance <= 0:
        return {}
    half_distance = total_distance / 2

    first_half, second_half = [], []
    cumulative = 0.0
    for lap in laps:
        cumulative += lap[0]
        (first_half if cumulative <= half_distance else second_half).append(lap)
    # Randfall: die Haelften-Grenze faellt (bei wenigen, ungleichen Runden)
    # so, dass eine Seite leer bleibt - dann stattdessen nach Rundenzahl
    # aufteilen, damit beide Haelften mindestens eine Runde haben.
    if not first_half or not second_half:
        mid = len(laps) // 2 or 1
        first_half, second_half = laps[:mid], laps[mid:]
        if not first_half or not second_half:
            return {}

    def _half_stats(half):
        dist = sum(d for d, _, _ in half)
        dur = sum(t for _, t, _ in half)
        if dur <= 0 or dist <= 0:
            return None
        hr_weighted = sum(hr * t for _, t, hr in half)
        avg_hr = hr_weighted / dur
        if avg_hr <= 0:
            return None
        return dist / dur, avg_hr  # (m/s, bpm)

    stats1 = _half_stats(first_half)
    stats2 = _half_stats(second_half)
    if not stats1 or not stats2:
        return {}

    speed1, hr1 = stats1
    speed2, hr2 = stats2
    ef1 = speed1 / hr1
    ef2 = speed2 / hr2
    if ef1 <= 0:
        return {}
    decoupling_pct = round((ef1 - ef2) / ef1 * 100, 1)

    def _pace_min_km(speed_m_s):
        if not speed_m_s or speed_m_s <= 0:
            return None
        return round((1000 / speed_m_s) / 60, 2)

    return {
        "decoupling_pct": decoupling_pct,
        "avg_hr_first_half": round(hr1, 1),
        "avg_hr_second_half": round(hr2, 1),
        "avg_pace_first_half_min_km": _pace_min_km(speed1),
        "avg_pace_second_half_min_km": _pace_min_km(speed2),
    }
