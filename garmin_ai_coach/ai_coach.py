import os
import requests
from ha_publish import extract_metrics

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # kommt aus den Add-on-Optionen

# Fokus je Trainingsphase (siehe claude/status-und-plan.md im Projekt).
PHASE_FOCUS = {
    "Grundlagenausdauer": "aerobe Basis (Zone 1-2), Schwimmtechnik, 3x/Woche je Disziplin, 2x Kraft",
    "Aufbau 1": "Schwellentraining, erste Bricks, Rad-Grundkraft",
    "Aufbau 2 (spezifisch)": "Wettkampftempo, lange Einheiten (Rad 90-100km, Lauf 18-20km)",
    "Peak": "hoechstes Volumen, Formtest",
    "Taper/Rennwoche": "Volumen -40 bis -60%, Intensitaet halten, Rennwoche",
}


def _fmt(value, unit=""):
    """Formatiert einen Metrikwert fuer den Prompt; gibt 'keine Daten' zurueck,
    wenn Garmin den Wert (noch) nicht geliefert hat, statt 'None' in den
    Prompt zu schreiben."""
    if value is None:
        return "keine Daten"
    return f"{value}{unit}"


def generate_coaching_note(data: dict) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt")

    metrics = extract_metrics(data)
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    wv = data.get("weekly_volumes") or {}

    prompt = (
        "Du bist ein Ausdauersport-Coach fuer einen Age-Group-Athleten in der Vorbereitung "
        "auf einen Ironman 70.3 am 29.08.2027.\n\n"
        f"Aktuelle Trainingsphase: {phase} (Fokus: {focus}). "
        f"Noch {_fmt(metrics['days_to_race'], ' Tage')} bis zum Rennen.\n\n"
        "Heutige Werte:\n"
        f"- Ruhepuls: {_fmt(metrics['resting_hr'], ' bpm')}\n"
        f"- Schritte bisher: {_fmt(metrics['steps_today'])}\n"
        f"- Training Readiness: {_fmt(metrics['training_readiness_score'], '%')} "
        f"({_fmt(metrics['training_readiness_level'])})\n"
        f"- Training Status: {_fmt(metrics['training_status_phrase'])}\n"
        f"- HRV letzte Nacht: {_fmt(metrics['hrv_avg'], ' ms')} ({_fmt(metrics['hrv_status'])})\n"
        f"- Body Battery: {_fmt(metrics['body_battery'], '%')}\n"
        f"- Stresslevel: {_fmt(metrics['stress_avg'])}\n"
        f"- Atemfrequenz: {_fmt(metrics['respiration_avg'], ' brpm')}\n"
        f"- SpO2: {_fmt(metrics['spo2_avg'], '%')}\n"
        f"- Schlaf: {_fmt(metrics['sleep_hours'], ' h')}, Score {_fmt(metrics['sleep_score'])}\n"
        f"- VO2max: {_fmt(metrics['vo2max'], ' ml/kg/min')}\n"
        f"- Wochenvolumen bisher: Schwimmen {_fmt(wv.get('swim_km'), 'km')}, "
        f"Rad {_fmt(wv.get('bike_km'), 'km')}, Lauf {_fmt(wv.get('run_km'), 'km')}\n\n"
        "Gib mir einen kurzen, ehrlichen Coaching-Tipp fuer heute (max. 3-4 Saetze, Deutsch): "
        "1) kurze Einschaetzung der Erholungslage, 2) eine konkrete Trainingsempfehlung fuer heute "
        "passend zur aktuellen Phase. Wenn Erholungswerte (Readiness, HRV, Body Battery, Schlaf) auf "
        "Uebertraining oder unzureichende Erholung hindeuten, empfiehl explizit leichteres Training "
        "oder einen Ruhetag statt eines harten Reizes. Nenne nicht jeden einzelnen Wert einzeln, "
        "sondern ziehe eine klare, direkt umsetzbare Schlussfolgerung."
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
