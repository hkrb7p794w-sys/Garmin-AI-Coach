"""Gemini-Aufruf mit Bild/Text und JSON-Antwort.

Gleiches Robustheitsprinzip wie im Garmin AI Coach (ai_coach.py):
- 404 "nicht mehr verfügbar": in der Meldung genanntes Nachfolgemodell nehmen.
- 429/5xx: kurz wiederholen, dann auf ein anderes Flash-Modell ausweichen
  (Modellliste der API, "lite" zuerst).
Für die Erfassung zählt Wartezeit, deshalb kürzere Pausen als beim Coach.

Datenschutz: Im kostenlosen Kontingent darf Google Eingaben (auch Fotos) zur
Produktverbesserung nutzen. Fotos werden vorher im Browser verkleinert und
neu kodiert (dabei fallen EXIF-/GPS-Daten weg).
"""
import json
import os
import re
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "").strip()
TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", 90))
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRYABLE = {429, 500, 502, 503, 504}
RETRY_DELAYS = [0, 3]
_state = {"fallback": None, "primary_down_until": 0.0, "schema_ok": True, "last_model": None, "dead": set()}


class GeminiError(RuntimeError):
    retryable = False


def configured() -> bool:
    return bool(API_KEY)


def _successor_from_404(text: str, tried: str):
    for name in re.findall(r"models/([A-Za-z0-9.\-]+)", text or ""):
        if name != tried:
            return name
    return None


def _list_flash_models():
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": API_KEY}, params={"pageSize": 200}, timeout=20)
        if r.status_code >= 400:
            return []
        out = []
        for m in r.json().get("models") or []:
            name = str(m.get("name", "")).replace("models/", "")
            if "generateContent" not in (m.get("supportedGenerationMethods") or []) or "flash" not in name:
                continue
            if any(x in name for x in ("image", "tts", "audio", "live", "embedding", "exp")):
                continue
            out.append(name)
        return out
    except Exception:
        return []


def _pick_fallback(current):
    if FALLBACK_MODEL and FALLBACK_MODEL != current:
        return FALLBACK_MODEL
    if _state["fallback"] and _state["fallback"] != current:
        return _state["fallback"]
    cands = [n for n in _list_flash_models() if n != current and n not in _state["dead"]]
    cands.sort(key=lambda n: (0 if "lite" in n else 1, "preview" in n, n))
    _state["fallback"] = cands[0] if cands else None
    return _state["fallback"]


def _body(parts, schema, max_tokens):
    gen = {"maxOutputTokens": max_tokens, "responseMimeType": "application/json", "temperature": 0.2}
    if schema is not None and _state["schema_ok"]:
        gen["responseJsonSchema"] = schema
    return {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}


def _extract_text(body: dict, model: str) -> str:
    cands = body.get("candidates") or []
    if not cands:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise GeminiError(f"Keine Antwort von Gemini (blockReason: {reason})")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise GeminiError(f"Leere Antwort von {model} (finishReason: {cands[0].get('finishReason')})")
    return text


def parse_json(text: str):
    """JSON aus der Antwort lösen (auch wenn in ```json ... ``` eingepackt)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


def _try(model, parts, schema, max_tokens):
    last = None
    for attempt, delay in enumerate(RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            r = requests.post(URL.format(model=model),
                              headers={"x-goog-api-key": API_KEY, "content-type": "application/json"},
                              json=_body(parts, schema, max_tokens), timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            last = GeminiError(f"Netzwerkfehler ({model}): {e}")
            last.retryable = True
            continue
        if r.status_code == 404:
            _state["dead"].add(model)
            if _state["fallback"] == model:
                _state["fallback"] = None
            succ = _successor_from_404(r.text, model)
            if succ:
                print(f"[gemini] Modell {model} nicht verfügbar, nehme {succ}")
                if model != MODEL:
                    _state["fallback"] = succ
                return _try(succ, parts, schema, max_tokens)
        if r.status_code == 400 and schema is not None and _state["schema_ok"] and \
                ("responseJsonSchema" in r.text or "response_json_schema" in r.text):
            # Ältere Modelle kennen das Schema-Feld nicht - dann nur JSON-Modus + Prompt
            print("[gemini] responseJsonSchema nicht unterstützt - nutze nur JSON-Modus")
            _state["schema_ok"] = False
            continue
        if r.status_code in RETRYABLE:
            last = GeminiError(f"Gemini HTTP {r.status_code} ({model})")
            last.retryable = True
            print(f"[gemini] Versuch {attempt + 1} mit {model}: HTTP {r.status_code}")
            if r.status_code == 429 or attempt >= 1:
                break  # Kontingent erschöpft bzw. überlastet: sofort ausweichen statt warten
            continue
        if r.status_code >= 400:
            raise GeminiError(f"Gemini HTTP {r.status_code} ({model}): {r.text[:300]}")
        _state["last_model"] = model
        return _extract_text(r.json(), model)
    raise last or GeminiError(f"Gemini ({model}) lieferte keine verwertbare Antwort")


def generate_json(prompt: str, image_b64: str = None, mime: str = "image/jpeg",
                  schema: dict = None, max_tokens: int = 6000):
    """Ein Aufruf mit Text (+ optional Bild). Gibt das geparste JSON zurück."""
    if not API_KEY:
        raise GeminiError("Kein Gemini API Key in der Add-on-Konfiguration")
    parts = []
    if image_b64:
        parts.append({"inline_data": {"mime_type": mime, "data": image_b64}})
    parts.append({"text": prompt})
    if time.time() < _state["primary_down_until"]:
        fb = _pick_fallback(MODEL)
        if fb:
            try:
                return parse_json(_try(fb, parts, schema, max_tokens))
            except GeminiError:
                pass
    try:
        text = _try(MODEL, parts, schema, max_tokens)
        _state["primary_down_until"] = 0.0
    except GeminiError as e:
        if not getattr(e, "retryable", False):
            raise
        fb = _pick_fallback(MODEL)
        if not fb:
            raise
        print(f"[gemini] {MODEL} überlastet, weiche aus auf {fb}")
        _state["primary_down_until"] = time.time() + 1800
        text = _try(fb, parts, schema, max_tokens)
    try:
        return parse_json(text)
    except ValueError as e:
        raise GeminiError(f"Antwort war kein gültiges JSON: {e}")


def last_model():
    return _state["last_model"]
