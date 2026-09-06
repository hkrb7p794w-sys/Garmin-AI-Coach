import os
import requests
from ha_publish import extract_metrics

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # kommt aus den Add-on-Optionen

# Freitext-Kontext fuer die KI - haelt den Prompt lesbar und macht das
# Race-Datum / die Phase an einer Stelle aenderbar, statt es im f-String
# zu verstecken.
RACE_CONTEXT = "Ziel: Ironman 70.3 (Platzhalter-Rennmonat August 2027)."


def _fmt(value, unit=""):
    """Formatiert einen Metrikwert fuer den Prompt; gibt 'keine Daten' zurueck,
    wenn Garmin den Wert (noch) nicht geliefert hat, statt 'None' in den
    Prompt zu schreiben."""
    if value is None:
        return "keine Daten"
    return f"{value}{unit}"


def generate_coaching_note(data: dict) -> str:
    metrics = extract_metrics(data)

    prompt = (
        f"Du bist ein Ausdauersport-Coach. {RACE_CONTEXT}\n\n"
        "Heutige Werte:\n"
        f"- Ruhepuls: {_fmt(metrics['resting_hr'], ' bpm')}\n"
        f"- Schritte bisher: {_fmt(metrics['steps_today'])}\n"
        f"- Training Readiness: {_fmt(metrics['training_readiness_score'], '%')} "
        f"({_fmt(metrics['training_readiness_level'])})\n"
        f"- Training Status: {_fmt(metrics['training_status_phrase'])}\n"
        f"- HRV letzte Nacht: {_fmt(metrics['hrv_avg'], ' ms')} "
        f"({_fmt(metrics['hrv_status'])})\n"
        f"- Body Battery: {_fmt(metrics['body_battery'], '%')}\n"
        f"- Stresslevel: {_fmt(metrics['stress_avg'])}\n"
        f"- Atemfrequenz: {_fmt(metrics['respiration_avg'], ' brpm')}\n"
        f"- SpO2: {_fmt(metrics['spo2_avg'], '%')}\n"
        f"- Schlaf: {_fmt(metrics['sleep_hours'], ' h')}, Score {_fmt(metrics['sleep_score'])}\n"
        f"- VO2max: {_fmt(metrics['vo2max'], ' ml/kg/min')}\n"
        f"- Endurance Score (letzte 7 Tage): {_fmt(metrics['endurance_score'])}\n\n"
        "Gib mir einen kurzen, motivierenden Coaching-Tipp für heute (max. 2-3 Sätze, "
        "Deutsch). Wenn Erholungswerte (Readiness, HRV, Body Battery, Schlaf) auf "
        "Übertraining oder unzureichende Erholung hindeuten, empfiehl explizit "
        "leichteres Training oder Ruhe statt eines harten Reizes. Nenne nicht "
        "jeden einzelnen Wert, sondern ziehe eine kurze, klare Schlussfolgerung."
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
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=20,
    )
    resp.raise_for_status()
    content = resp.json()["content"]
    return "".join(b["text"] for b in content if b["type"] == "text").strip()
