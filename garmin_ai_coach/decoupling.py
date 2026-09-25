"""Berechnet aerobe HF-Pace-Kopplung ("aerobic decoupling") für längere,
gleichmäßige Laufeinheiten.

Siehe claude/konzept-erweiterung-metriken-v0.16-plus.md, Abschnitt 1.3.

Methode (Joe Friel / TrainingPeaks "Pa:HR decoupling", siehe
https://www.trainingpeaks.com/blog/aerobic-endurance-and-decoupling/):
Die Einheit wird nach zurückgelegter Distanz (nicht nach Rundenzahl - eine
kürzere Schlussrunde soll das Ergebnis nicht verzerren) in zwei Hälften
geteilt. Je Hälfte wird ein Effizienzfaktor aus Geschwindigkeit und
Herzfrequenz gebildet:

    EF1 = Durchschnittsgeschwindigkeit erste Hälfte / Durchschnitts-HF erste Hälfte
    EF2 = Durchschnittsgeschwindigkeit zweite Hälfte / Durchschnitts-HF zweite Hälfte
    Entkopplung % = (EF1 - EF2) / EF1 * 100

Positive Werte: die HF steigt im Verlauf der Einheit relativ zur Pace
(Ermüdung bzw. für diese Dauer noch unzureichende aerobe Basis). Werte nahe
0 oder negativ: stabile Kopplung. Als grobe Faustregel gilt < 5% als gute
aerobe Basis für die jeweilige Dauer - eine Orientierung, keine exakte,
wissenschaftlich scharf abgegrenzte Kennzahl.

WICHTIG (Datenunsicherheit, analog zur exerciseSets-Vorsicht in v0.10.1):
Garmin.get_activity_splits() liefert laut python-garminconnect-Quellcode ein
dict; das genaue Feld für die Rundenliste ("lapDTOs") sowie die Feldnamen je
Runde sind nicht durch eine echte Beispielantwort belegt. Die Extraktion
unten ist deshalb bewusst defensiv (mehrere plausible Feldnamen) und liefert
{} statt eines erfundenen Werts, wenn sich keine verwertbaren Runden finden
lassen. Nach dem ersten echten Sync mit qualifizierender Lauf-Einheit bitte
die Attribute von sensor.garmin_ai_coach_garmin_hf_pace_kopplung
(Entwicklerwerkzeuge -> Zustände) prüfen.
"""

# Nur längere, gleichmäßige Läufe eignen sich für diese Kennzahl -
# Intervall-/Schwellen-/VO2max-Einheiten haben absichtlich wechselnde
# Intensität, dort würde die Kennzahl nur Rauschen statt Ermüdung zeigen.
# Filterung über den Aktivitätsnamen (best effort) plus eine Mindestdauer,
# unter der ein Entkopplungssignal ohnehin nicht belastbar wäre. Diese
# Heuristik muss nach den ersten echten Syncs gegen reale Aktivitätsnamen/
# -dauern geprüft werden (gleiche Vorsicht wie beim v0.10.0-FIT-Parsing).
EXCLUDED_NAME_KEYWORDS = ("intervall", "schwelle", "vo2max", "tempo")
MIN_DURATION_MIN = 35


def is_eligible_run(activity: dict) -> bool:
    """Grobfilter, ob eine Aktivität für die Entkopplungs-Berechnung infrage
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
    Größen fehlt oder nicht plausibel ist."""
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
    Antwort von Garmin.get_activity_splits(). Gibt {} zurück, wenn nicht
    genug verwertbare Runden vorliegen (z.B. keine HF je Runde) - die
    Aktivität wird dann einfach übersprungen statt eine unbelastbare Zahl
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
    # Randfall: die Hälften-Grenze fällt (bei wenigen, ungleichen Runden)
    # so, dass eine Seite leer bleibt - dann stattdessen nach Rundenzahl
    # aufteilen, damit beide Hälften mindestens eine Runde haben.
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


# ===========================================================================
# v0.18.0 - Überarbeitung nach dem Dashboard-Review (Punkte 5 und 17)
# ===========================================================================
#
# Problem der bisherigen Version: Der Namensfilter griff nie, weil Garmin alle
# Läufe schlicht "<Ort> Laufen" nennt. Dadurch landete z. B. ein Lauf vom
# 13.09.2026 mit 4:46 min/km (schneller als die eigene Schwelle) und HF 159 ->
# 179 als "Grundlagenlauf" mit 16,8 % Entkopplung in der Anzeige. Die Kennzahl
# ist aber nur für komplett aerobe, gleichmäßige Einheiten aussagekräftig
# (TrainingPeaks/Friel: "the workout ... must have been fully aerobic ... and
# steady"; > 10 % deutet eher auf eine Einheit über der aeroben Schwelle hin).
#
# Neu:
# 1. Filter über die Herzfrequenzzonen der Aktivität (hrTimeInZone_1..5 aus der
#    Aktivitätsliste) statt über den Namen: höchstens 10 % der Zeit in Zone 4-5.
#    Fehlen die Zonenfelder, wird die Aktivität NICHT gewertet (lieber keine
#    Zahl als eine falsche) - die Feldnamen sind nach dem ersten Sync zu prüfen.
# 2. Die ersten 10 Minuten (Aufwärmen, HF läuft erst hoch) werden abgeschnitten.
# 3. Zusätzlich Zwift-Einheiten mit Leistungsmessung (Pw:HR statt Pa:HR) -
#    konstante Watt ohne Wind/Steigung sind der ideale Fall für diese Kennzahl.
# 4. Berechnung bevorzugt aus der Zeitreihe (get_activity_details), weil
#    Zwift-Fahrten oft nur eine einzige Runde haben; Rundenmethode nur als
#    Fallback für Läufe.
# 5. Cache-Einträge der alten Methode werden verworfen und neu berechnet
#    (Lessons Learned 6: ein Fix muss das Alte aktiv erkennen und verwerfen).

METHOD_VERSION = 3
WARMUP_SECONDS = 600
MAX_HIGH_ZONE_SHARE = 0.10
MIN_RIDE_DURATION_MIN = 45


def zone_seconds(activity: dict):
    """[z1..z5] in Sekunden aus der Aktivitätszusammenfassung oder None."""
    vals = []
    for i in range(1, 6):
        v = activity.get(f"hrTimeInZone_{i}")
        if not isinstance(v, (int, float)):
            return None
        vals.append(float(v))
    return vals if sum(vals) > 0 else None


def high_zone_share(activity: dict):
    z = zone_seconds(activity)
    if not z:
        return None
    return (z[3] + z[4]) / sum(z)


def classify(activity: dict):
    """'run' | 'ride' | None - ob und als was die Aktivität für die
    Entkopplung infrage kommt."""
    type_key = ((activity.get("activityType") or {}).get("typeKey", "") or "").lower()
    duration_min = (activity.get("duration") or 0) / 60.0
    if "run" in type_key:
        sport = "run"
        if duration_min < MIN_DURATION_MIN:
            return None
    elif "bik" in type_key or "cycl" in type_key or "ride" in type_key:
        sport = "ride"
        if duration_min < MIN_RIDE_DURATION_MIN:
            return None
        # Nur die Zwift-Aufzeichnung mit Distanz und Leistung, nicht die
        # parallele HF-Zweitaufzeichnung der Uhr (siehe app._volumes_in_window).
        if (activity.get("distance") or 0) <= 0:
            return None
        if not isinstance(activity.get("avgPower") or activity.get("averagePower"), (int, float)):
            return None
    else:
        return None
    share = high_zone_share(activity)
    if share is None or share > MAX_HIGH_ZONE_SHARE:
        return None
    return sport


def _series_from_details(details: dict) -> dict:
    """Zerlegt get_activity_details() in {key: [werte]} anhand der
    metricDescriptors. Feldnamen laut Garmin-Connect-Antwortformat
    (directHeartRate, directSpeed, directPower, sumDuration) - defensiv."""
    if not isinstance(details, dict):
        return {}
    descriptors = details.get("metricDescriptors") or []
    rows = details.get("activityDetailMetrics") or []
    index = {}
    for d in descriptors:
        if isinstance(d, dict) and "metricsIndex" in d and d.get("key"):
            index[d["key"]] = d["metricsIndex"]
    series = {k: [] for k in index}
    for row in rows:
        metrics = (row or {}).get("metrics") if isinstance(row, dict) else None
        if not isinstance(metrics, list):
            continue
        for key, i in index.items():
            series[key].append(metrics[i] if i < len(metrics) else None)
    return series


def compute_from_details(details: dict, sport: str) -> dict:
    """Entkopplung aus der Zeitreihe: Aufwärmen abschneiden, Rest nach Zeit
    halbieren, Effizienzfaktor (Tempo bzw. Leistung / HF) je Hälfte."""
    s = _series_from_details(details)
    hr = s.get("directHeartRate")
    out_key = "directPower" if sport == "ride" else "directSpeed"
    out = s.get(out_key)
    t = s.get("sumDuration") or s.get("sumElapsedDuration")
    if not hr or not out or not t or len(hr) != len(out) or len(t) != len(hr):
        return {}
    points = [
        (tt, o, h) for tt, o, h in zip(t, out, hr)
        if isinstance(tt, (int, float)) and isinstance(o, (int, float)) and isinstance(h, (int, float))
        and h > 0 and tt >= WARMUP_SECONDS
    ]
    if len(points) < 20:
        return {}
    t0, t1 = points[0][0], points[-1][0]
    if t1 - t0 < 20 * 60:
        return {}
    mid = t0 + (t1 - t0) / 2
    first = [(o, h) for tt, o, h in points if tt < mid]
    second = [(o, h) for tt, o, h in points if tt >= mid]
    if not first or not second:
        return {}
    o1 = sum(o for o, _ in first) / len(first)
    h1 = sum(h for _, h in first) / len(first)
    o2 = sum(o for o, _ in second) / len(second)
    h2 = sum(h for _, h in second) / len(second)
    if o1 <= 0 or h1 <= 0 or h2 <= 0:
        return {}
    ef1, ef2 = o1 / h1, o2 / h2
    res = {
        "decoupling_pct": round((ef1 - ef2) / ef1 * 100, 1),
        "avg_hr_first_half": round(h1, 1),
        "avg_hr_second_half": round(h2, 1),
        "source": "zeitreihe",
    }
    if sport == "ride":
        res["avg_power_first_half_w"] = round(o1)
        res["avg_power_second_half_w"] = round(o2)
    else:
        res["avg_pace_first_half"] = pace_mmss(o1)
        res["avg_pace_second_half"] = pace_mmss(o2)
    return res


def compute_from_laps_trimmed(raw_splits) -> dict:
    """Fallback für Läufe: Rundenmethode wie bisher, aber ohne die Runden der
    ersten 10 Minuten."""
    laps = _laps_from_splits(raw_splits)
    kept, elapsed = [], 0.0
    for lap in laps:
        dur = lap.get("duration") or lap.get("movingDuration") or lap.get("elapsedDuration") or 0
        if elapsed >= WARMUP_SECONDS:
            kept.append(lap)
        elapsed += dur if isinstance(dur, (int, float)) else 0
    res = compute_decoupling({"lapDTOs": kept})
    if not res:
        return {}
    res["avg_pace_first_half"] = pace_mmss_from_minkm(res.pop("avg_pace_first_half_min_km", None))
    res["avg_pace_second_half"] = pace_mmss_from_minkm(res.pop("avg_pace_second_half_min_km", None))
    res["source"] = "runden"
    return res


def pace_mmss(speed_m_s):
    if not isinstance(speed_m_s, (int, float)) or speed_m_s <= 0:
        return None
    sec = round(1000 / speed_m_s)
    return f"{sec // 60}:{sec % 60:02d}"


def pace_mmss_from_minkm(minkm):
    if not isinstance(minkm, (int, float)) or minkm <= 0:
        return None
    sec = round(minkm * 60)
    return f"{sec // 60}:{sec % 60:02d}"


def skip_reason(activity: dict):
    """Klartext, warum classify() die Aktivität verworfen hat; None, wenn es
    gar keine Lauf-/Radaktivität ist."""
    type_key = ((activity.get("activityType") or {}).get("typeKey", "") or "").lower()
    duration_min = (activity.get("duration") or 0) / 60.0
    is_run = "run" in type_key
    is_ride = "bik" in type_key or "cycl" in type_key or "ride" in type_key
    if not (is_run or is_ride):
        return None
    if is_ride and (activity.get("distance") or 0) <= 0:
        return None  # HF-Zweitaufzeichnung der Uhr, kein eigener Eintrag
    if is_run and duration_min < MIN_DURATION_MIN:
        return f"kürzer als {MIN_DURATION_MIN} min"
    if is_ride and duration_min < MIN_RIDE_DURATION_MIN:
        return f"kürzer als {MIN_RIDE_DURATION_MIN} min"
    if is_ride and not isinstance(activity.get("avgPower") or activity.get("averagePower"), (int, float)):
        return "keine Leistungsdaten"
    share = high_zone_share(activity)
    if share is None:
        return "keine HF-Zonendaten von Garmin"
    if share > MAX_HIGH_ZONE_SHARE:
        return f"zu intensiv ({round(share * 100)} % der Zeit in Zone 4-5)"
    return "nicht geeignet"
