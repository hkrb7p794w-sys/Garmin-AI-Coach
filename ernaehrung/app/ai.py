"""KI-Anbieter für Foto- und Textanalyse.

- "gemini" (Standard): Google Gemini API. Fotos verlassen dafür das Heimnetz; im
  kostenlosen Kontingent darf Google Eingaben zur Produktverbesserung nutzen.
- "lokal": ein eigener KI-Server mit OpenAI-kompatibler Schnittstelle im Heimnetz
  (z. B. Ollama mit einem Bildmodell wie qwen2.5vl, LM Studio, llama.cpp-Server).
  Dann bleiben Fotos und Texte vollständig im eigenen Netz. Ein Raspberry Pi 4 ist dafür
  zu schwach; ein PC/Mac mit Grafikkarte oder Apple Silicon im selben Netz reicht.

In beiden Fällen gilt: Fotos werden nur im Arbeitsspeicher für die Analyse gehalten und
nie gespeichert (weder auf dem Pi noch im Browser).
"""
import json
import os

import requests

import gemini

def _env(name, default=""):
    v = (os.environ.get(name) or "").strip()
    return default if v in ("", "null", "None") else v   # bashio liefert "null" für leere Optionen


PROVIDER = _env("KI_ANBIETER", "gemini").lower()
LOCAL_URL = _env("LOKAL_URL").rstrip("/")
LOCAL_MODEL = _env("LOKAL_MODELL")
LOCAL_KEY = _env("LOKAL_API_KEY")
LOCAL_TIMEOUT = int(os.environ.get("LOKAL_TIMEOUT", 300))

AIError = gemini.GeminiError
_state = {"last": None}


def provider() -> str:
    return "lokal" if PROVIDER == "lokal" else "gemini"


def configured() -> bool:
    if provider() == "lokal":
        return bool(LOCAL_URL and LOCAL_MODEL)
    return gemini.configured()


def describe() -> str:
    if provider() == "lokal":
        return f"Lokaler KI-Server ({LOCAL_MODEL or 'kein Modell'} @ {LOCAL_URL or 'keine Adresse'})"
    return f"Google Gemini ({gemini.last_model() or gemini.MODEL})"


def last_model():
    return _state["last"] or (LOCAL_MODEL if provider() == "lokal" else gemini.last_model())


def _chat_url():
    base = LOCAL_URL
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/chat/completions"


def _local(prompt, image_b64=None, mime="image/jpeg", schema=None, max_tokens=6000):
    content = [{"type": "text", "text": prompt}]
    if image_b64:
        content.insert(0, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}})
    body = {"model": LOCAL_MODEL, "messages": [{"role": "user", "content": content}],
            "temperature": 0.2, "max_tokens": max_tokens}
    headers = {"content-type": "application/json"}
    if LOCAL_KEY:
        headers["authorization"] = f"Bearer {LOCAL_KEY}"
    formats = []
    if schema is not None:
        formats.append({"type": "json_schema", "json_schema": {"name": "antwort", "schema": schema}})
    formats.append({"type": "json_object"})
    last = None
    for fmt in formats:
        try:
            r = requests.post(_chat_url(), headers=headers, json={**body, "response_format": fmt},
                              timeout=LOCAL_TIMEOUT)
        except requests.RequestException as e:
            raise AIError(f"Lokaler KI-Server nicht erreichbar ({LOCAL_URL}): {e}")
        if r.status_code == 400 and fmt["type"] == "json_schema":
            last = r.text[:200]
            continue  # Server kennt json_schema nicht - einfacher JSON-Modus
        if r.status_code >= 400:
            raise AIError(f"Lokaler KI-Server HTTP {r.status_code}: {r.text[:300]}")
        try:
            msg = r.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError):
            raise AIError("Lokaler KI-Server: unerwartete Antwort")
        _state["last"] = LOCAL_MODEL
        try:
            return gemini.parse_json(msg if isinstance(msg, str) else json.dumps(msg))
        except ValueError as e:
            raise AIError(f"Antwort war kein gültiges JSON: {e}")
    raise AIError(f"Lokaler KI-Server lehnt JSON-Antworten ab: {last}")


def generate_json(prompt, image_b64=None, mime="image/jpeg", schema=None, max_tokens=6000):
    if provider() == "lokal":
        if not configured():
            raise AIError("Lokaler KI-Server nicht eingerichtet (lokal_url und lokal_modell in der Konfiguration)")
        return _local(prompt, image_b64, mime, schema, max_tokens)
    res = gemini.generate_json(prompt, image_b64=image_b64, mime=mime, schema=schema, max_tokens=max_tokens)
    _state["last"] = gemini.last_model()
    return res
