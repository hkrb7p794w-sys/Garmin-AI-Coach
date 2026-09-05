import os
import requests
from ha_publish import extract_metrics

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # kommt aus den Add-on-Optionen

def generate_coaching_note(data: dict) -> str:
    metrics = extract_metrics(data)
    prompt = (
        f"Ruhepuls heute: {metrics['resting_hr']} bpm. "
        f"Schritte heute bisher: {metrics['steps_today']}. "
        "Gib mir einen kurzen, motivierenden Coaching-Tipp für heute (max. 2 Sätze, Deutsch)."
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