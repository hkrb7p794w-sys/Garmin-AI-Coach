import os
import re
import json
import datetime
import requests
import time
from ha_publish import extract_metrics
import plan

# Google Gemini API - kostenloses Kontingent (Stand 09/2026: keine Kreditkarte nötig,
# siehe https://ai.google.dev/gemini-api/docs/pricing). Key kommt aus den Add-on-Optionen.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# gemini-2.5-flash liefert für neue Accounts nur noch HTTP 404 ("no longer available to
# new users"). Google nennt in dieser Fehlermeldung selbst das aktuelle Nachfolgemodell -
# wir starten daher mit dem empfohlenen Modell und ziehen bei einem 404 automatisch das
# in der Antwort genannte nach (siehe _model_from_404), damit ein künftiger Modellwechsel
# bei Google nicht wieder ein manuelles Update erzwingt.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", 120))
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Rennziel - per Add-on-Option änderbar.
RACE_GOAL = os.environ.get("RACE_GOAL", "Finish in 5:30-6:00 h")

# Seit v0.18.0: Wochenrahmen, Phasenfokus und Phasenpläne kommen aus plan.py
# (einzige Quelle der Wahrheit, dieselben Daten rendert das Dashboard).
ATHLETE_PROFILE = plan.ATHLETE_PROFILE
PHASE_FOCUS = plan.PHASE_FOCUS
TRAININGSPLAN_PHASE_DETAIL = {name: plan.phase_detail_text(name) for name in plan.PHASE_ORDER}

# Renndatum für Prompts (vorher an vier Stellen fest "29.08.2027").
RACE_DATE_TEXT = plan.parse_race_date(os.environ.get("RACE_DATE", "")).strftime("%d.%m.%Y")

# Datenschutz (Review-Punkt 23): Im kostenlosen Gemini-Kontingent darf Google
# Eingaben und Antworten zur Produktverbesserung nutzen, menschliche Prüfer
# dürfen sie lesen; Google rät dort ausdrücklich von sensiblen/persönlichen
# Daten ab (Gemini API Additional Terms, Abschnitt "Unpaid Services").
# "reduziert" (Standard) schickt deshalb keine Roh-Gesundheitswerte (Ruhepuls,
# HRV-ms, Schlafstunden, SpO2, Atemfrequenz, Stress), sondern nur abgeleitete
# Einordnungen. "voll" = bisheriges Verhalten, sinnvoll z. B. mit aktivierter
# Abrechnung (bezahlte Stufe: keine Nutzung zur Produktverbesserung).
AI_PRIVACY_MODE = (os.environ.get("AI_PRIVACY_MODE") or "reduziert").strip().lower()

# Bereits im Dashboard dokumentierte, gezielte Gym-Anpassungsvorschläge (siehe
# claude/status-und-plan.md) - Umsetzung liegt bei Alex, nicht automatisch
# vorgenommen. Phasenunabhängig, deshalb separat von TRAININGSPLAN_PHASE_DETAIL.
#
# Seit v0.14.0 als Liste einzelner, stabil identifizierbarer Vorschläge statt
# eines einzigen Textblocks (siehe Dashboard-Tab "Vorschläge", suggestions.py):
# jeder Punkt lässt sich dort einzeln annehmen ("weiter forcieren" - fliesst als
# Kontext in künftige Gemini-Prompts ein) oder ablehnen (wird vorerst nicht mehr
# vorgeschlagen, später reaktivierbar). Die "id" ist stabil und darf sich NICHT
# ändern, ohne den bereits gespeicherten Annehmen/Ablehnen-Zustand (Alex' frühere
# Entscheidungen!) für diesen Punkt zu verlieren.
TRAININGSPLAN_GYM_KRITIK = [
    {
        "id": "gym_bizeps_redundanz",
        "title": "Curl in Pull B durch Pallof Press ersetzen",
        "text": (
            "Pull A und Pull B haben je 2 Curl-Varianten (Bizeps wird dadurch 4x/Woche isoliert "
            "trainiert). In Pull B eine Curl-Variante durch Pallof Press am Kabel (Rumpf-Anti-"
            "Rotation, stützt Schwimmlage sowie Rad-/Lauf-Haltung) ersetzen, Pull A bleibt."
        ),
    },
    {
        "id": "gym_huefte_kreuzheben",
        "title": "Beinstrecken durch Rumänisches Kreuzheben ersetzen",
        "text": (
            "Lower hat mit Beinbeugen und Beinstrecken zwei reine Knie-Isolationsübungen, aber "
            "keine Hüftstreckung/posteriore Kette. Beinstrecken (geringster Ausdauer-Transfer) "
            "durch Rumänisches Kreuzheben ersetzen. Beinpressen und Fersenheben bleiben."
        ),
    },
    {
        "id": "gym_rumpf_plank",
        "title": "Plank/Side Plank ergänzen",
        "text": (
            "Crunches trainiert nur Bauchflexion. Optional Plank/Side Plank ergänzen (kein "
            "Ersatz für Crunches, sondern zusätzlich)."
        ),
    },
    {
        "id": "gym_periodisierung",
        "title": "Phasenweise auf 3x6-8 statt durchgehend 2x12 wechseln",
        "text": (
            "Durchgehend 2x12 ist reines Hypertrophie-Volumen, kein Kraft-/Ökonomie-Reiz. Bei "
            "den 5 grossen Grundübungen (Bankdrücken, Dips, Beinpressen, enges Rudern, "
            "Lat-Ziehen eng) phasenweise (z.B. 2 von 4 Wochen) auf 3x6-8 schwerer wechseln, "
            "Isolationsübungen bleiben bei 2x12-15."
        ),
    },
]


def _render_gym_kritik(status_by_id: dict = None) -> str:
    """Rendert TRAININGSPLAN_GYM_KRITIK als Text für den Trainingsplan-
    Kommentar-Prompt (generate_trainingsplan_kommentar unten).

    status_by_id (optional): {suggestion_id: "pending"|"accepted"|"rejected"}
    aus suggestions.by_source("gym_kritik") - vom Athleten ABGELEHNTE Punkte
    werden komplett ausgeblendet (Alex soll sie vorerst nicht erneut
    vorgeschlagen bekommen), ANGENOMMENE werden als bereits umgesetzt
    markiert, damit Gemini sie nicht wie einen offenen Vorschlag behandelt."""
    status_by_id = status_by_id or {}
    lines = []
    for item in TRAININGSPLAN_GYM_KRITIK:
        status = status_by_id.get(item["id"], "pending")
        if status == "rejected":
            continue
        suffix = " (vom Athleten bereits angenommen/umgesetzt)" if status == "accepted" else ""
        lines.append(f"- {item['title']}{suffix}: {item['text']}")
    if not lines:
        return "Keine offenen Gym-Anpassungsvorschläge (alle bereits entschieden)."
    return "\n".join(lines)


def _fmt(value, unit=""):
    """Formatiert einen Metrikwert für den Prompt; gibt 'keine Daten' zurück,
    wenn Garmin den Wert (noch) nicht geliefert hat, statt 'None' in den
    Prompt zu schreiben."""
    if value is None:
        return "keine Daten"
    return f"{value}{unit}"


def _model_from_404(message: str, tried_model: str):
    """Zieht aus einer 404-Antwort das von Google empfohlene Nachfolgemodell.

    Beispielmeldung: "This model models/gemini-2.5-flash is no longer available to
    new users. Please update your code to use models/gemini-3.6-flash ...".
    Wir nehmen das erste genannte Modell, das nicht das gerade versuchte ist."""
    for name in re.findall(r"models/([A-Za-z0-9.\-]+)", message or ""):
        if name != tried_model:
            return name
    return None


def _call_gemini(model: str, prompt: str, json_mode: bool = False):
    """Ein Gemini-Aufruf. Gibt (status_code, body_text_or_json) zurück."""
    resp = requests.post(
        GEMINI_URL_TEMPLATE.format(model=model),
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "content-type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            # Die Flash-Modelle sind "Thinking"-Modelle: interne Denk-Tokens zählen mit
            # gegen maxOutputTokens. Bei einem knappen Budget kann das Modell alles fürs
            # Denken verbrauchen und einen Kandidaten ganz ohne Text-Part zurückliefern
            # (finishReason MAX_TOKENS) - ohne HTTP-Fehler. Daher großzügige Obergrenze;
            # der sichtbare Text bleibt kurz, weil der Prompt 3-4 Sätze vorgibt.
            "generationConfig": (
                {"maxOutputTokens": 2000, "responseMimeType": "application/json"}
                if json_mode else {"maxOutputTokens": 2000}
            ),
        },
        # Thinking-Modelle brauchen für diesen Prompt teils deutlich mehr als 30s
        # (genau daran ist der erste Versuch mit gemini-3.6-flash gescheitert:
        # "Read timed out"). Der Aufruf blockiert nichts Kritisches mehr, seit die
        # Messwerte in app.py bereits VOR der KI-Anfrage publiziert werden.
        timeout=GEMINI_TIMEOUT,
    )
    return resp


# ---------------------------------------------------------------------------
# Robuster Gemini-Aufruf (seit v0.18.0, Review-Punkt 1)
# ---------------------------------------------------------------------------
# Live-Befund 25.09.2026: seit Tagen fast jeder Aufruf HTTP 503 "This model is
# currently experiencing high demand ... try again later", vereinzelt 429.
# Bisher gab es genau einen Versuch und keinen Fallback - der Coach war damit
# faktisch aus. Jetzt: Wiederholung mit Wartezeit bei vorübergehenden Fehlern,
# danach automatisch ein anderes verfügbares Flash-Modell (aus der Modellliste
# der API, gleiches Selbstheilungsprinzip wie beim 404-Nachfolger).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = [0, 15, 45]
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "").strip()
_fallback_cache = {"model": None, "primary_down_until": 0.0}
# Nach einem dauerhaften Ausfall des Hauptmodells 30 min direkt das
# Ausweichmodell nutzen, statt jedes Mal erst drei Fehlversuche abzuwarten.
PRIMARY_COOLDOWN_SECONDS = 1800


class GeminiError(RuntimeError):
    pass


def _list_flash_models() -> list:
    """Verfügbare Modelle mit generateContent, deren Name 'flash' enthält."""
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": GEMINI_API_KEY},
            params={"pageSize": 200},
            timeout=30,
        )
        if resp.status_code >= 400:
            return []
        names = []
        for m in resp.json().get("models") or []:
            name = str(m.get("name", "")).replace("models/", "")
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" not in methods or "flash" not in name:
                continue
            if any(x in name for x in ("image", "tts", "audio", "live", "embedding", "exp")):
                continue
            names.append(name)
        return names
    except Exception as e:
        print(f"[ai_coach] Modellliste nicht abrufbar: {e}")
        return []


def _pick_fallback(current: str):
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != current:
        return GEMINI_FALLBACK_MODEL
    if _fallback_cache["model"] and _fallback_cache["model"] != current:
        return _fallback_cache["model"]
    candidates = [n for n in _list_flash_models() if n != current]
    # "lite"-Varianten zuerst: laut Fehlerbild ist das Hauptmodell überlastet,
    # die kleinere Variante hat meist freie Kapazität.
    candidates.sort(key=lambda n: (0 if "lite" in n else 1, "preview" in n, n))
    choice = candidates[0] if candidates else None
    _fallback_cache["model"] = choice
    return choice


def _extract_text(body: dict, model: str) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise GeminiError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise GeminiError(
            f"Gemini ({model}) hat leeren Text geliefert "
            f"(finishReason: {candidate.get('finishReason')})"
        )
    return text


def _try_model(model: str, prompt: str, json_mode: bool):
    """Mehrere Versuche mit einem Modell. Gibt (text, model) oder wirft
    GeminiError; .retryable sagt, ob ein anderes Modell sinnvoll ist."""
    last_err = None
    for attempt, delay in enumerate(RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            resp = _call_gemini(model, prompt, json_mode=json_mode)
        except requests.exceptions.RequestException as e:
            last_err = GeminiError(f"Netzwerkfehler/Timeout ({model}): {e}")
            last_err.retryable = True
            continue
        if resp.status_code == 404:
            successor = _model_from_404(resp.text, model)
            if successor:
                print(f"[ai_coach] Modell '{model}' nicht verfügbar, wechsle auf '{successor}'")
                return _try_model(successor, prompt, json_mode)
        if resp.status_code in RETRYABLE_STATUS:
            last_err = GeminiError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:200]}")
            last_err.retryable = True
            print(f"[ai_coach] Versuch {attempt + 1}/{len(RETRY_DELAYS)} mit {model}: HTTP {resp.status_code}")
            continue
        if resp.status_code >= 400:
            err = GeminiError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:400]}")
            err.retryable = False
            raise err
        return _extract_text(resp.json(), model), model
    raise last_err


def _generate(prompt: str, label: str, json_mode: bool = False):
    """Zentraler Aufruf für alle Texte. Gibt (text, verwendetes_modell) zurück."""
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY ist nicht gesetzt")
    if time.time() < _fallback_cache["primary_down_until"]:
        fallback = _pick_fallback(GEMINI_MODEL)
        if fallback:
            try:
                return _try_model(fallback, prompt, json_mode)
            except GeminiError as e:
                print(f"[ai_coach] {label}: Ausweichmodell {fallback} fehlgeschlagen ({e}), versuche Hauptmodell")
    try:
        result = _try_model(GEMINI_MODEL, prompt, json_mode)
        _fallback_cache["primary_down_until"] = 0.0
        return result
    except GeminiError as e:
        if not getattr(e, "retryable", False):
            raise
        fallback = _pick_fallback(GEMINI_MODEL)
        if not fallback:
            raise
        print(f"[ai_coach] {label}: {GEMINI_MODEL} dauerhaft überlastet, versuche {fallback}")
        _fallback_cache["primary_down_until"] = time.time() + PRIMARY_COOLDOWN_SECONDS
        return _try_model(fallback, prompt, json_mode)


# ---------------------------------------------------------------------------
# Erholungswerte für Prompts - je nach Datenschutzmodus roh oder eingeordnet
# ---------------------------------------------------------------------------

def _band(value, bands):
    if not isinstance(value, (int, float)):
        return "keine Daten"
    for limit, text in bands:
        if value < limit:
            return text
    return bands[-1][1]


def vitals_block(metrics: dict, rec: dict = None) -> str:
    """Erholungsblock für Prompts. Im Modus 'reduziert' ohne Rohwerte."""
    if AI_PRIVACY_MODE == "voll":
        return (
            f"- Ruhepuls: {_fmt(metrics.get('resting_hr'), ' bpm')}\n"
            f"- Training Readiness: {_fmt(metrics.get('training_readiness_score'), '%')} "
            f"({_fmt(metrics.get('training_readiness_level'))})\n"
            f"- HRV letzte Nacht: {_fmt(metrics.get('hrv_avg'), ' ms')}, 7-Tage-Schnitt "
            f"{_fmt(metrics.get('hrv_weekly_avg'), ' ms')} (Status {_fmt(metrics.get('hrv_status'))})\n"
            f"- Body Battery: {_fmt(metrics.get('body_battery'), '%')}\n"
            f"- Schlaf: {_fmt(metrics.get('sleep_hours'), ' h')}, Score {_fmt(metrics.get('sleep_score'))}\n"
            f"- Training Status: {_fmt(metrics.get('training_status_de') or metrics.get('training_status_phrase'))}\n"
        )
    return (
        f"- Readiness-Stufe (Garmin): {_fmt(metrics.get('training_readiness_level'))}\n"
        f"- HRV-Status (7-Tage-Schnitt vs. Baseline): {_fmt(metrics.get('hrv_status'))}\n"
        f"- Schlaf: {_band(metrics.get('sleep_hours'), [(6, 'kurz'), (7.5, 'normal'), (99, 'gut')])}\n"
        f"- Body Battery: {_band(metrics.get('body_battery'), [(30, 'niedrig'), (60, 'mittel'), (101, 'hoch')])}\n"
        f"- Training Status (Garmin): {_fmt(metrics.get('training_status_de') or metrics.get('training_status_phrase'))}\n"
        + (f"- Regelbasierte Tagesampel: {rec['label']} ({'; '.join(rec['reasons'])})\n" if rec else "")
    )


def generate_coaching_note(data: dict, rec: dict = None, plan_state: dict = None):
    """Tages-Coaching-Notiz (seit v0.18.0 strukturiert, Review-Punkt 15).

    Die Entscheidung normal/locker/Pause kommt aus recommendation.evaluate()
    (rec) - Gemini darf sie NICHT ändern, sondern formuliert nur die Umsetzung
    für den heutigen Tag. Antwort als JSON {"punkte": [...]} (responseMimeType
    application/json), damit das Format nicht mehr vom Modell abhängt.
    Gibt (markdown_text, modell) zurück."""
    metrics = extract_metrics(data)
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    wv = data.get("weekly_volumes") or {}
    ps = plan_state or {}
    today_items = ", ".join(i["text"] for i in ps.get("today_fixed") or []) or "nichts Festes"
    open_items = ", ".join(ps.get("week_open") or []) or "nichts"
    rec_text = (
        f"{rec['label']} - {rec['advice']} Gründe: {'; '.join(rec['reasons'])}."
        if rec else "keine"
    )

    prompt = (
        "Du bist ein Ausdauersport-Coach für einen Age-Group-Athleten in der Vorbereitung "
        f"auf einen Ironman 70.3 am {RACE_DATE_TEXT}. Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Heute ist {ps.get('weekday') or ''}. Trainingsphase: {phase} (Fokus: {focus}). "
        f"Noch {_fmt(metrics['days_to_race'], ' Tage')} bis zum Rennen.\n"
        f"Laut Wochenrahmen heute: {today_items}. Diese Woche noch offen: {open_items} "
        f"(noch {ps.get('days_left_in_week', '?')} Tage in der Woche).\n"
        f"Wochenvolumen bisher: Schwimmen {_fmt(wv.get('swim_km'), ' km')}, "
        f"Rad {_fmt(wv.get('bike_km'), ' km')}, Lauf {_fmt(wv.get('run_km'), ' km')}.\n\n"
        "Erholung:\n"
        f"{vitals_block(metrics, rec)}\n"
        f"VERBINDLICHE Tagesentscheidung (regelbasiert, nicht ändern): {rec_text}\n\n"
        "Aufgabe: Formuliere daraus eine kurze, konkrete Umsetzung für heute. Antworte "
        'AUSSCHLIESSLICH mit JSON der Form {"punkte": ["...", "..."]} mit 2-3 Punkten, je '
        "ein Satz, ohne Aufzählungszeichen im Text:\n"
        "1. Was heute konkret trainiert wird (passend zu Wochentag, offener Woche und der "
        "Tagesentscheidung - bei 'locker' eine entschärfte Variante, bei 'Ruhetag' nichts Hartes).\n"
        "2. Ein Satz zur Einordnung der Erholung (keine Rohzahlen aufzählen).\n"
        "3. Optional: ein Hinweis, wie die offene Woche im bestehenden Rahmen noch sinnvoll "
        "aufgeht - keine zusätzlichen Einheiten fordern.\n"
        "Schreibe durchgängig in korrektem Deutsch mit echten Umlauten (ä, ö, ü, ß)."
    )
    text, model = _generate(prompt, "coaching", json_mode=True)
    return parse_points(text), model


def parse_points(text: str) -> str:
    """{"punkte": [...]} -> Markdown-Stichpunkte. Fallback: Rohtext."""
    raw = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    candidate = m.group(1) if m else raw
    try:
        parsed = json.loads(candidate)
        points = parsed.get("punkte") if isinstance(parsed, dict) else None
        points = [str(p).strip().lstrip("-• ").strip() for p in (points or []) if str(p).strip()]
        if points:
            return "\n".join(f"- {p}" for p in points[:3])
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return raw


def _trend(current, previous, unit="", better="hoch"):
    """Formatiert 'Wert (Vorwoche: X)' für den Wochenreport."""
    if current is None:
        return "keine Daten"
    if previous is None:
        return f"{current}{unit} (keine Vorwochendaten)"
    delta = round(current - previous, 1)
    sign = "+" if delta > 0 else ""
    return f"{current}{unit} (Vorwoche {previous}{unit}, {sign}{delta})"


def _format_strength_sessions(sessions: list) -> str:
    """Formatiert die per FIT-Datei erkannten Übungen/Sätze (siehe
    fit_exercises.py) für den Wochenreport-Prompt. Best-Effort: liefert '',
    wenn keine Session verwertbare Übungsdetails hat - der Prompt behauptet
    dann einfach nichts zu einzelnen Übungen, statt Lücken zu erfinden."""
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    lines = []
    for session in sessions or []:
        exercises = session.get("exercises") or []
        if not exercises:
            continue
        try:
            day_name = weekdays[datetime.date.fromisoformat(str(session.get("date"))).weekday()]
        except (ValueError, TypeError):
            day_name = session.get("date") or "?"
        parts = []
        for ex in exercises:
            sets = ex.get("sets") or []
            reps = [str(s.get("reps")) for s in sets if s.get("reps")]
            detail = f"{len(sets)} Sätze"
            if reps:
                detail += f", {'/'.join(reps)} Wdh."
            parts.append(f"{ex.get('exercise', '?')} ({detail})")
        if parts:
            lines.append(f"{day_name}: " + ", ".join(parts))
    return "\n".join(lines)


def _format_strength_sessions_detailed(sessions: list) -> str:
    """Formatiert die per exerciseSets-API erkannten Übungen/Sätze (siehe
    fit_exercises.py) INKLUSIVE Gewichten für den Gym-Coaching-Prompt - im
    Unterschied zu _format_strength_sessions (nur Wiederholungen, für den
    Wochenreport) werden hier auch die Gewichte gebraucht, um Belastung und
    Fortschritt je Übung einschätzen zu können."""
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    lines = []
    for session in sessions or []:
        exercises = session.get("exercises") or []
        if not exercises:
            continue
        try:
            day_name = weekdays[datetime.date.fromisoformat(str(session.get("date"))).weekday()]
        except (ValueError, TypeError):
            day_name = session.get("date") or "?"
        parts = []
        for ex in exercises:
            sets = ex.get("sets") or []
            set_strs = []
            for s in sets:
                reps = s.get("reps")
                weight = s.get("weight_kg")
                if reps is None and weight is None:
                    continue
                reps_str = str(reps) if reps is not None else "?"
                weight_str = f"{weight}kg" if weight is not None else "Körpergewicht/ohne Angabe"
                set_strs.append(f"{reps_str}x{weight_str}")
            if set_strs:
                parts.append(f"{ex.get('exercise', '?')} ({', '.join(set_strs)})")
        if parts:
            lines.append(f"{day_name} ({session.get('date')}): " + "; ".join(parts))
    return "\n".join(lines)


def generate_gym_coaching_note(sessions: list, interference_note: str = "") -> str:
    """Eigener, auf Krafttraining fokussierter KI-Tipp - getrennt vom
    allgemeinen Tages-Coaching-Tipp (generate_coaching_note), weil der sich
    auf Erholung/Tagesplanung über alle Disziplinen bezieht, während dieser
    Tipp gezielt die einzelnen Übungen/Sätze/Gewichte der letzten 7 Tage
    auswertet (Muskelgruppen-Balance, auffällige Sätze, konkrete Empfehlung
    für die nächste Einheit). Nutzt dieselbe Gemini-Anbindung wie die
    anderen beiden Coaching-Texte.

    interference_note (optional): Kontext-Satz aus app.py,
    _check_endurance_before_strength_interference() - siehe dort und
    claude/konzept-erweiterung-metriken-v0.16-plus.md, Abschnitt 1.5. Leerer
    String, wenn kein Interferenz-Fall vorliegt (Normalfall)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")

    detail = _format_strength_sessions_detailed(sessions)
    if not detail:
        raise RuntimeError("keine verwertbaren Kraft-Übungsdaten der letzten 7 Tage")

    interference_block = f"\n\n{interference_note}" if interference_note else ""

    prompt = (
        "Du bist ein Kraft-/Fitnesscoach für einen Age-Group-Athleten in der "
        f"Ironman-70.3-Vorbereitung (Zielzeit {RACE_GOAL}). Krafttraining ist bei ihm "
        "Nebensache zum Ausdauertraining, nicht das Hauptziel - Kraftaufbau soll die "
        "Ausdauerdisziplinen unterstützen (Verletzungsvorbeugung, Rumpfstabilität, "
        "muskuläre Balance), nicht mit ihnen konkurrieren.\n\n"
        "Erkannte Kraft-Übungen der letzten 7 Tage (Übung: Wiederholungen x Gewicht "
        "je Satz - 'Körpergewicht/ohne Angabe' heisst: keine Zusatzgewichts-Angabe am "
        "Gerät erfasst, nicht zwangsläufig ein Datenfehler):\n"
        f"{detail}"
        f"{interference_block}\n\n"
        "Gib mir einen kurzen, konkreten Gym-Coaching-Tipp auf Deutsch - als Stichpunkte "
        "im Markdown-Format, JEDER Punkt eine eigene Zeile beginnend mit '- ', KEIN "
        "Fliesstext und KEIN einleitender Satz davor. Genau 2-4 Punkte:\n"
        "- Ein Punkt: Einschätzung der Muskelgruppen-Balance dieser Woche (Push/Pull/"
        "Beine/Rumpf) - fehlt etwas Wichtiges fürs Ausdauertraining (v.a. Beine/Rumpf)?\n"
        "- Ein Punkt: eine konkrete, umsetzbare Empfehlung für die nächste Kraft-Einheit "
        "(z.B. eine Übung ergänzen, Gewicht/Wiederholungen einer auffälligen Übung "
        "anpassen).\n"
        "- NUR falls Kraftvolumen/-intensität auffällig hoch wirkt und die Erholung "
        "fürs Ausdauertraining gefährden könnte: ein dritter Punkt dazu (sonst "
        "weglassen).\n"
        "- NUR falls oben ein Hinweis zur Trainingsreihenfolge steht: ein eigener Punkt "
        "dazu, kurz eingeordnet (sonst weglassen).\n"
        "Nenne nicht jeden Satz einzeln, sondern ziehe eine klare Schlussfolgerung. "
        "Gewichtsangaben können unvollständig sein (siehe Hinweis oben) - baue darauf "
        "keine überzogen sichere Aussage. Schreibe durchgängig in korrektem Deutsch mit echten "
        "Umlauten (ä, ö, ü, ß) - niemals die Ersatzschreibweisen ae/oe/ue/ss."
    )

    text, model = _generate(prompt, "gym")
    return text


def generate_weekly_report(data: dict, summary: dict) -> str:
    """Wöchentlicher Rückblick: Soll/Ist der Wochenstruktur, Trends, Fokus für die
    kommende Woche. Nutzt dieselbe Gemini-Anbindung wie die Tagesnotiz."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")

    s = summary or {}
    metrics = extract_metrics(data or {})
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    days_left = data.get("days_to_race")

    # Belastbarkeit der Trenddaten ehrlich benennen: die Historie füllt sich erst
    # über die ersten Tage, vorher wären "Trends" reine Behauptung.
    history_days = s.get("history_days") or 0
    trend_note = (
        "Die Trenddaten sind belastbar."
        if history_days >= 10 else
        f"ACHTUNG: Es liegen erst {history_days} Tage Historie vor - Trendaussagen zu "
        "Ruhepuls/HRV/Schlaf sind noch NICHT belastbar, sag das offen statt sie zu deuten."
    )

    # Einzelne erkannte Kraft-Übungen (Best-Effort aus der Original-FIT-Datei, siehe
    # fit_exercises.py) - nur einbauen, wenn tatsächlich etwas Verwertbares vorliegt.
    strength_detail = _format_strength_sessions(data.get("strength_exercises"))
    strength_block = (
        "- Davon erkannte Kraft-Übungen (Best-Effort aus der Original-Gerätedatei, "
        f"nicht garantiert vollständig):\n{strength_detail}"
        if strength_detail else ""
    )

    if AI_PRIVACY_MODE == "voll":
        weekly_recovery = (
            "Erholung im Wochenmittel:\n"
            f"- Ruhepuls: {_trend(s.get('resting_hr_avg'), s.get('resting_hr_avg_prev'), ' bpm')}\n"
            f"- HRV: {_trend(s.get('hrv_avg'), s.get('hrv_avg_prev'), ' ms')}\n"
            f"- Schlaf: {_trend(s.get('sleep_hours_avg'), s.get('sleep_hours_avg_prev'), ' h')}\n"
            f"- Training Readiness: {_trend(s.get('readiness_avg'), s.get('readiness_avg_prev'))}\n"
            f"- Training Status (aktuell): {_fmt(metrics.get('training_status_de') or metrics.get('training_status_phrase'))}\n"
        )
    else:
        def _dir(cur, prev, better_high=True):
            if not isinstance(cur, (int, float)) or not isinstance(prev, (int, float)) or not prev:
                return "keine Vergleichsdaten"
            d = (cur - prev) / prev * 100
            if abs(d) < 3:
                return "stabil"
            up = d > 0
            return "besser als Vorwoche" if up == better_high else "schlechter als Vorwoche"
        weekly_recovery = (
            "Erholung im Wochenvergleich (ohne Rohwerte, Datenschutzmodus):\n"
            f"- Ruhepuls: {_dir(s.get('resting_hr_avg'), s.get('resting_hr_avg_prev'), better_high=False)}\n"
            f"- HRV: {_dir(s.get('hrv_avg'), s.get('hrv_avg_prev'))}\n"
            f"- Schlaf: {_dir(s.get('sleep_hours_avg'), s.get('sleep_hours_avg_prev'))}\n"
            f"- Training Status (aktuell): {_fmt(metrics.get('training_status_de') or metrics.get('training_status_phrase'))}\n"
        )
    zones = data.get("weekly_volumes") or {}
    if zones.get("zone_total_min"):
        weekly_recovery += (
            f"- Intensitätsverteilung Ausdauer (HF-Zonen): {zones.get('zone_low_pct')} % locker (Z1-2), "
            f"{zones.get('zone_mid_pct')} % mittel (Z3), {zones.get('zone_high_pct')} % hart (Z4-5)\n"
        )

    prompt = (
        "Du bist ein Ausdauersport-Coach und schreibst den wöchentlichen Rückblick für "
        f"einen Age-Group-Athleten in der Vorbereitung auf einen Ironman 70.3 am {RACE_DATE_TEXT}. "
        f"Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Trainingsphase: {phase} (Fokus: {focus}). Noch {_fmt(days_left, ' Tage')} bis zum Rennen.\n\n"
        f"SOLL laut Wochenstruktur: {plan.SOLL_TEXT}.\n\n"
        f"IST im Zeitraum {_fmt(s.get('period_label'))} (Vorzeitraum "
        f"{_fmt(s.get('period_prev_label'))} in Klammern) - schreibe im Report konkret 'in der "
        "Woche vom ... bis ...' mit diesen Daten, nicht 'diese Woche', damit klar ist, welcher "
        "Zeitraum gemeint ist:\n"
        f"- Schwimmen: {_fmt(s.get('swim_sessions'))} Einheiten "
        f"({_fmt(s.get('swim_sessions_prev'))}), {_fmt(s.get('swim_km'), ' km')} "
        f"(Vorwoche {_fmt(s.get('swim_km_prev'), ' km')})\n"
        f"- Rad: {_fmt(s.get('bike_sessions'))} Einheiten ({_fmt(s.get('bike_sessions_prev'))}), "
        f"{_fmt(s.get('bike_km'), ' km')} (Vorwoche {_fmt(s.get('bike_km_prev'), ' km')})\n"
        f"- Laufen: {_fmt(s.get('run_sessions'))} Einheiten ({_fmt(s.get('run_sessions_prev'))}), "
        f"{_fmt(s.get('run_km'), ' km')} (Vorwoche {_fmt(s.get('run_km_prev'), ' km')})\n"
        f"- Kraft: {_fmt(s.get('strength_sessions'))} Einheiten "
        f"({_fmt(s.get('strength_sessions_prev'))})\n"
        f"- Gesamtbelastung: {_fmt(s.get('total_min'), ' min')} "
        f"(Vorwoche {_fmt(s.get('total_min_prev'), ' min')}, "
        f"Veränderung {_fmt(s.get('volume_change_pct'), '%')})\n"
        f"{strength_block}\n"
        f"{weekly_recovery}"
        f"{trend_note}\n\n"
        "Schreibe den wöchentlichen Rückblick auf Deutsch als Stichpunkte im Markdown-Format, "
        "JEDER Punkt eine eigene Zeile beginnend mit '- ', KEIN Fliesstext und KEIN einleitender "
        "Satz davor. Genau diese Punkte, je maximal 1-2 Sätze, keine Wiederholung der reinen "
        "Zahlen (die stehen bereits in der Tabelle im Dashboard):\n"
        "- Wie war der Zeitraum im Vergleich zur Wochenstruktur und zum Vorzeitraum?\n"
        "- Was sagen Belastung und Erholung zusammen - passt die Progression (Faustregel: "
        "Steigerung der Gesamtbelastung um mehr als ~10% pro Woche ist riskant)?\n"
        "- EIN konkreter Fokus für die kommende Woche, umsetzbar im bestehenden Zeitrahmen.\n"
        "- NUR falls das Zeitziel durch zu wenig Radtraining gefährdet ist: ein eigener Punkt "
        "dazu (sonst weglassen).\n"
        "Sei realistisch und ohne Vorwürfe: verpasste Einheiten sind eingeplant. Schreibe "
        "durchgängig in korrektem Deutsch mit echten Umlauten (ä, ö, ü, ß) - niemals die "
        "Ersatzschreibweisen ae/oe/ue/ss."
    )

    text, model = _generate(prompt, "weekly")
    return text


def generate_chat_answer(question: str, data: dict, history: list, chat_context: str = "") -> str:
    """Beantwortet eine freie, gezielte Frage des Athleten im Dashboard-Tab
    "Chat" (siehe claude/status-und-plan.md, Auftrag von Alex 11.09.2026:
    "Chat integrieren, sodass ich gezielte Fragen über die API an Gemini
    stellen kann"). Anders als die anderen generate_*-Funktionen hier KEIN
    fest vorgegebenes Antwortformat (keine erzwungenen Stichpunkte) - eine
    echte Chat-Antwort soll sich an der gestellten Frage orientieren, nicht an
    einer Coaching-Notiz-Schablone.

    data: die zuletzt gespeicherten Sync-Daten (wie bei generate_coaching_note)
    - MIT Trainingskontext, das war Alex' ausdrücklicher Wunsch bei der
    Abstimmung dieser Funktion: Readiness/VO2max/Phase/Wochenvolumen etc.
    werden bei jeder Frage automatisch mitgegeben, damit z.B. "Wie war meine
    Woche?" ohne weitere Erklärung funktioniert.
    history: die Tages-Historie (für evtl. Trend-Rückfragen, gleiche Quelle
    wie beim Wochenreport).
    chat_context: vorformatierter Block über den bisherigen Gesprächsverlauf
    (siehe chat.context_for_prompt) - hier bewusst als fertiger String statt
    chat.py direkt zu importieren, analog zu generate_trainingsplan_kommentar/
    decided_context (suggestions.py)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")
    question = (question or "").strip()
    if not question:
        raise RuntimeError("Leere Frage")

    metrics = extract_metrics(data or {})
    phase = (data or {}).get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    plan_detail = TRAININGSPLAN_PHASE_DETAIL.get(phase, "")
    wv = (data or {}).get("weekly_volumes") or {}
    readiness_14d = None
    vo2max_7d = None
    try:
        today = datetime.date.today()
        readiness_14d = _history_avg_for_chat(history, "readiness", 0, 13, today)
        vo2max_7d = _history_avg_for_chat(history, "vo2max", 0, 6, today)
    except Exception:
        pass
    context_block = f"\n\n{chat_context}\n" if chat_context else ""

    prompt = (
        "Du bist ein Ausdauersport-Coach und persönlicher Trainingsassistent für einen "
        f"Age-Group-Athleten in der Vorbereitung auf einen Ironman 70.3 am {RACE_DATE_TEXT}. "
        f"Zielzeit: {RACE_GOAL}. Du beantwortest hier eine gezielte Frage in einem Chat - "
        "KEINE Coaching-Notiz und KEINE erzwungenen Stichpunkte, sondern eine direkte, "
        "natürliche Antwort auf genau diese Frage, so kurz wie möglich, aber vollständig.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Aktuelle Trainingsphase: {phase} (Fokus: {focus}). "
        f"Noch {_fmt(metrics['days_to_race'], ' Tage')} bis zum Rennen.\n"
        f"Für die aktuelle Phase geplant:\n{plan_detail}\n\n"
        "Aktueller Datenstand (letzter Sync):\n"
        f"{vitals_block(metrics)}"
        f"- Readiness 14-Tage-Schnitt: {_fmt(readiness_14d if AI_PRIVACY_MODE == 'voll' else None, '%')}\n"
        f"- VO2max: {_fmt(metrics['vo2max'], ' ml/kg/min')}, 7-Tage-Schnitt: {_fmt(vo2max_7d, ' ml/kg/min')}\n"
        f"- FTP (Rad, letzter bekannter Wert laut Garmin): {_fmt(metrics.get('ftp'), ' W')}\n"
        f"- HF-Pace-Kopplung Lauf (Ø letzte qualifizierende Einheiten): "
        f"{_fmt(metrics.get('decoupling_avg_pct'), '%')}\n"
        f"- Wochenvolumen bisher: Schwimmen {_fmt(wv.get('swim_km'), 'km')}, "
        f"Rad {_fmt(wv.get('bike_km'), 'km')}, Lauf {_fmt(wv.get('run_km'), 'km')}\n\n"
        "WICHTIGE EINSCHRÄNKUNG (damit du nichts erfindest): Dir liegen keine Pace-Daten "
        "(Lauf/Schwimmen) und kein Körpergewicht vor; einzige Watt-Größe ist die FTP oben. Die "
        "manuell gepflegten Benchmark-Felder der Zielzeit-Schätzung kennst du nicht. Fehlen "
        "Werte für eine Antwort, sag das ehrlich statt eine Zahl zu erfinden.\n"
        f"{context_block}\n"
        f"Neue Frage des Athleten: {question}\n\n"
        "Antworte auf Deutsch, direkt und konkret auf die Frage bezogen, nutze die obigen Daten "
        "wo relevant. Halte die Antwort kurz (max. ca. 120 Wörter), als Fliesstext (kein "
        "Stichpunkt-Zwang) - nur wenn eine Aufzählung die Frage klarer beantwortet, darfst du "
        "kurze Stichpunkte verwenden. Wenn eine Frage nichts mit Training/Erholung/Coaching zu "
        "tun hat, beantworte sie trotzdem höflich, aber lenke bei Gelegenheit kurz zurück auf "
        "die Rolle als Trainingscoach. Schreibe durchgängig in korrektem Deutsch mit echten "
        "Umlauten (ä, ö, ü, ß) - niemals die Ersatzschreibweisen ae/oe/ue/ss."
    )

    text, model = _generate(prompt, "chat")
    return text


def _history_avg_for_chat(history: list, key: str, offset_from: int, offset_to: int, today):
    """Kleine, lokale Kopie von app._history_avg (Mittelwert eines Feldes über
    Tage mit Abstand offset_from..offset_to zu heute) - bewusst dupliziert statt
    aus app.py importiert, um keinen zirkulären Import (app.py importiert
    bereits aus ai_coach.py) einzuführen. Nur für die zwei Zusatzwerte
    (Readiness-14-Tage-/VO2max-7-Tage-Schnitt) im Chat-Prompt oben genutzt."""
    values = []
    for entry in history or []:
        try:
            day = datetime.date.fromisoformat(str(entry.get("date")))
        except (TypeError, ValueError):
            continue
        if offset_from <= (today - day).days <= offset_to:
            value = entry.get(key)
            if isinstance(value, (int, float)):
                values.append(value)
    return round(sum(values) / len(values), 1) if values else None


def generate_trainingsplan_kommentar(
    trigger_key: str,
    trigger_detail: str,
    data: dict,
    history: list,
    gym_status: dict = None,
    decided_context: str = "",
    interference_note: str = "",
) -> tuple:
    """Phasenspezifischer Gemini-Kommentar zu den Trainingsplänen im
    Dashboard-Tab 'Trainingspläne' (View 'pläne'). Anders als die anderen
    Coaching-Texte wird diese Funktion NICHT bei jedem Sync aufgerufen,
    sondern nur wenn app.check_trainingsplan_trigger() einen konkreten
    Auslöser erkennt (Phasenwechsel oder Datentrigger - Readiness/VO2max,
    siehe claude/status-und-plan.md, Abschnitt 'Trigger-Kriterien für
    automatische Gemini-Kommentierung'). Der Kommentar ERSETZT NICHT die
    Plantabellen selbst (die bleiben als stabile Referenz im Dashboard
    stehen), sondern erklärt, warum JETZT eine Anpassung sinnvoll sein
    könnte - genau das war Alex' ausdrücklicher Design-Wunsch.

    gym_status (optional): {suggestion_id: status} aus
    suggestions.by_source("gym_kritik") - siehe _render_gym_kritik.
    decided_context (optional): Text aus suggestions.context_for_prompt(
    "trainingsplan_kommentar") über bereits angenommene/abgelehnte frühere
    Einzelvorschläge aus DIESEM Kommentar-Kanal.
    interference_note (optional): Kontext-Satz aus app.py,
    _check_endurance_before_strength_interference() - siehe dort und
    Konzept-Dokument Abschnitt 1.5. Leerer String im Normalfall.

    Gibt seit v0.14.0 ein Tupel (kommentar_text, vorschläge) zurück statt
    nur eines Strings (Dashboard-Tab 'Vorschläge', siehe suggestions.py):
    kommentar_text ist der bisherige Freitext-Kommentar (Markdown-
    Stichpunkte), vorschläge eine Liste von {"id","title","text"}-Dicts mit
    den darin enthaltenen konkreten, einzeln annehm-/ablehnbaren
    Handlungsempfehlungen. Gemini antwortet dafür mit einem JSON-Objekt
    statt reinem Markdown-Text - siehe _parse_trainingsplan_response für
    das defensive Parsing (Fallback auf Rohtext ohne Einzelvorschläge, falls
    Gemini sich nicht ans Format hält)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")

    metrics = extract_metrics(data)
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    plan_detail = TRAININGSPLAN_PHASE_DETAIL.get(phase, "")
    wv = data.get("weekly_volumes") or {}
    gym_kritik_text = _render_gym_kritik(gym_status)
    decided_block = f"\n\n{decided_context}" if decided_context else ""
    interference_block = f"\n\n{interference_note}" if interference_note else ""

    prompt = (
        "Du bist ein Ausdauersport-Coach für einen Age-Group-Athleten in der Vorbereitung "
        f"auf einen Ironman 70.3 am {RACE_DATE_TEXT}. Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Aktuelle Trainingsphase: {phase} (Fokus: {focus}).\n\n"
        "Der Athlet hat bereits konkrete, phasenabhängige Trainingspläne für Laufen, Schwimmen "
        f"und Rad im Dashboard hinterlegt. Für die aktuelle Phase gilt:\n{plan_detail}\n\n"
        f"Offene Gym-Plan-Anpassungen (bereits vorgeschlagen, Umsetzung liegt beim Athleten):\n"
        f"{gym_kritik_text}"
        f"{decided_block}\n\n"
        f"AUSLOESER für diesen Kommentar JETZT: {trigger_detail}\n\n"
        "Aktuelle Werte: "
        f"Training Readiness {_fmt(metrics['training_readiness_score'] if AI_PRIVACY_MODE == 'voll' else metrics.get('training_readiness_level'), '%' if AI_PRIVACY_MODE == 'voll' else '')}, "
        f"Training Status {_fmt(metrics.get('training_status_de') or metrics.get('training_status_phrase'))}, "
        f"VO2max {_fmt(metrics['vo2max'], ' ml/kg/min')}, "
        f"FTP (Rad) {_fmt(metrics.get('ftp'), ' W')}, "
        f"HF-Pace-Kopplung Lauf (Ø letzte Einheiten) {_fmt(metrics.get('decoupling_avg_pct'), '%')}, "
        f"Wochenvolumen Rad {_fmt(wv.get('bike_km'), ' km')}, "
        f"Wochenvolumen Lauf {_fmt(wv.get('run_km'), ' km')}."
        f"{interference_block}\n\n"
        "Schreibe einen kurzen Kommentar zu den BESTEHENDEN Trainingsplänen auf Deutsch. WICHTIG: "
        "Du ersetzt NICHT den Plan, sondern kommentierst ihn - erfinde KEINE komplett neuen "
        "Wocheneinheiten, sondern beziehe dich konkret auf die oben genannten bestehenden Pläne.\n\n"
        "Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt (kein Markdown-Codeblock, kein "
        "Text davor oder danach) mit genau diesen zwei Feldern:\n"
        '{"kommentar": "...", "vorschläge": [...]}\n\n'
        '"kommentar": Stichpunkte als Markdown-Text, JEDER Punkt eine eigene Zeile beginnend mit '
        "'- ', KEIN Fliesstext und KEIN einleitender Satz davor. Genau 2-3 Punkte:\n"
        "- Ein Punkt: was der genannte Auslöser konkret bedeutet (1-2 Sätze, direkt auf die Werte "
        "oben bezogen).\n"
        "- Ein Punkt: eine kurze Einordnung, ob/welche Anpassung sinnvoll ist (Details dazu gehören "
        'in "vorschläge", hier nur die Einordnung) - oder die begründete Einschätzung, dass der '
        "Plan aktuell so bleiben kann.\n"
        "- NUR falls der Auslöser ein Phasenwechsel ist: ein dritter Punkt, was sich in der NEUEN "
        "Phase laut der Beschreibung oben inhaltlich am stärksten ändert (sonst diesen Punkt "
        "weglassen).\n"
        "- NUR falls oben ein Hinweis zur Trainingsreihenfolge steht: kurz einordnen, ob das für "
        "diesen Kommentar relevant ist (sonst nicht erwähnen).\n\n"
        '"vorschläge": Liste von 0 bis maximal 3 konkreten, einzeln umsetzbaren '
        "Handlungsempfehlungen an einem der vier Pläne (Lauf/Schwimm/Rad/Gym) - NICHT die reine "
        'Einschätzung/Begründung (die gehört in "kommentar"). Leere Liste, wenn der Plan '
        "unverändert bleiben sollte. Jeder Eintrag:\n"
        '{"id": "kurze-kebab-case-id", "title": "Kurztitel, max. 8 Wörter", '
        '"text": "1-2 Sätze, konkrete Massnahme"}\n'
        "Falls einer deiner Vorschläge inhaltlich identisch mit einem bereits oben unter "
        '"entschiedene frühere Einzelvorschläge" genannten ist, wiederverwende dessen id exakt '
        "(gleiche Schreibweise) - sonst eine neue, inhaltlich passende id.\n\n"
        "Sei konkret und begründet, keine allgemeinen Trainingsplatitüden. Schreibe die Texte in "
        '"kommentar" und "vorschläge" durchgängig in korrektem Deutsch mit echten Umlauten '
        "(ä, ö, ü, ß) - niemals die Ersatzschreibweisen ae/oe/ue/ss."
    )

    text, model = _generate(prompt, "plan", json_mode=True)
    return _parse_trainingsplan_response(text)


def _parse_trainingsplan_response(text: str) -> tuple:
    """Parst die JSON-Antwort von generate_trainingsplan_kommentar() (siehe
    dort) - eigene, direkt testbare Funktion, weil Gemini sich trotz
    Anweisung nicht IMMER an reines JSON hält (z.B. ein umschliessender
    ```json-Codeblock). Wird defensiv behandelt statt den ganzen Sync zu
    gefährden (siehe do_sync()-try/except um den Aufruf in app.py). Gibt
    IMMER (kommentar_text, vorschlaege_liste) zurück - im schlimmsten Fall
    (kompletter Parse-Fehlschlag) den rohen Text als Kommentar mit leerer
    Vorschlagsliste."""
    raw = text.strip()
    # Häufigstes Abweichungsmuster: Gemini umschliesst die JSON-Antwort trotz
    # gegenteiliger Anweisung mit einem Markdown-Codeblock (```json ... ``` oder ``` ... ```).
    fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else raw
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_coach] Trainingsplan-Kommentar: JSON-Parsing fehlgeschlagen ({e}), "
              "nutze Rohtext als Kommentar ohne Einzelvorschläge")
        return raw, []

    if not isinstance(parsed, dict):
        print("[ai_coach] Trainingsplan-Kommentar: JSON-Antwort ist kein Objekt, "
              "nutze Rohtext als Kommentar ohne Einzelvorschläge")
        return raw, []

    kommentar = parsed.get("kommentar")
    if not isinstance(kommentar, str) or not kommentar.strip():
        kommentar = raw
    kommentar = kommentar.strip()

    vorschläge = []
    for item in parsed.get("vorschläge") or []:
        if not isinstance(item, dict):
            continue
        sid_raw = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        vtext = str(item.get("text") or "").strip()
        if not sid_raw or not title:
            continue
        # id robust normalisieren (Gemini hält sich nicht IMMER exakt an kebab-case) -
        # sonst würde eine leicht andere Schreibweise (Grossbuchstaben, Leerzeichen, ...)
        # fälschlich als neuer Vorschlag statt als Wiederverwendung eines bereits
        # entschiedenen erkannt (siehe suggestions.sync_suggestions).
        sid = re.sub(r"[^a-z0-9-]+", "-", sid_raw.lower()).strip("-")
        if not sid:
            continue
        vorschläge.append({"id": sid, "title": title, "text": vtext})
    return kommentar, vorschläge
