import os
import requests
from ha_publish import extract_metrics

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # kommt aus den Add-on-Optionen

PHASE_FOCUS = {
    "Grundlagenausdauer": "aerobe Basis (Zone 1-2), Schwimmtechnik, 3x/Woche je Disziplin, 2x Kraft",
    "Aufbau 1": "Schwellentraining, erste Bricks, Rad-Grundkraft",
    "Aufbau 2 (spezifisch)": "Wettkampftempo, lange Einheiten (Rad 90-100km, Lauf 18-20km)",
    "Peak": "höchstes Volumen, Formtest",
    "Taper/Rennwoche": "Volumen -40 bis -60%, Intensität halten, Rennwoche",
}


def _fmt(value, unit=""):
    if value is None:
        return "unbekannt"
    return f"{value}{unit}"


def generate_coaching_note(data: dict) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt")

    metrics = extract_metrics(data)
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")

    prompt = (
        "Du bist Personal-Trainer für einen Age-Group-Athleten in der Vorbereitung auf einen "
        "Ironman 70.3 (29.08.2027). Hier sind die heutigen Garmin-Daten:\n"
        f"- Ruhepuls: {_fmt(metrics.get('resting_hr'), ' bpm')}\n"
        f"- Schritte heute: {_fmt(metrics.get('steps_today'))}\n"
        f"- Training Readiness: {_fmt(metrics.get('training_readiness_score'))} "
        f"({_fmt(metrics.get('training_readiness_level'))})\n"
        f"- Trainingsstatus: {_fmt(metrics.get('training_status'))}\n"
        f"- HRV letzte Nacht: {_fmt(metrics.get('hrv_last_night_avg'), ' ms')} "
        f"(Status: {_fmt(metrics.get('hrv_status'))})\n"
        f"- Body Battery: {_fmt(metrics.get('body_battery'))}\n"
        f"- Schlaf-Score: {_fmt(metrics.get('sleep_score'))}\n"
        f"- VO2max: {_fmt(metrics.get('vo2max'))}\n"
        f"- Wochenvolumen bisher: Schwimmen {_fmt(metrics.get('weekly_swim_km'), 'km')}, "
        f"Rad {_fmt(metrics.get('weekly_bike_km'), 'km')}, Lauf {_fmt(metrics.get('weekly_run_km'), 'km')}\n"
        f"- Trainingsphase: {phase} (Fokus: {focus})\n"
        f"- Tage bis zum Rennen: {_fmt(metrics.get('days_to_race'))}\n\n"
        "Gib einen kurzen, ehrlichen Coaching-Tipp für heute auf Deutsch (max. 4 Sätze): "
        "1) kurze Einschätzung der Erholungslage, 2) konkrete Trainingsempfehlung für heute passend "
        "zur aktuellen Phase, 3) falls Readiness/HRV/Schlaf auf Übertraining oder Krankheit hindeuten, "
        "das explizit als Warnung benennen und zu einem Ruhetag raten. Keine Floskeln, keine Wiederholung "
        "der reinen Zahlen, direkt umsetzbar."
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=20,
    )
    resp.raise_for_status()
    content = resp.json()["content"]
    return "".join(b["text"] for b in content if b["type"] == "text").strip()
