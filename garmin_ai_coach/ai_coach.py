import os
import re
import datetime
import requests
from ha_publish import extract_metrics

# Google Gemini API - kostenloses Kontingent (Stand 09/2026: keine Kreditkarte noetig,
# siehe https://ai.google.dev/gemini-api/docs/pricing). Key kommt aus den Add-on-Optionen.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# gemini-2.5-flash liefert fuer neue Accounts nur noch HTTP 404 ("no longer available to
# new users"). Google nennt in dieser Fehlermeldung selbst das aktuelle Nachfolgemodell -
# wir starten daher mit dem empfohlenen Modell und ziehen bei einem 404 automatisch das
# in der Antwort genannte nach (siehe _model_from_404), damit ein kuenftiger Modellwechsel
# bei Google nicht wieder ein manuelles Update erzwingt.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", 120))
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Rennziel - per Add-on-Option aenderbar.
RACE_GOAL = os.environ.get("RACE_GOAL", "Finish in 5:30-6:00 h")

# Realer Wochenrahmen des Athleten (von ihm selbst vorgegeben). Der Coach soll
# INNERHALB dieses Rahmens optimieren und niemals einfach "mehr Zeit" fordern.
ATHLETE_PROFILE = """Wochenstruktur des Athleten (fester Rahmen, nicht verhandelbar):
- Dienstag + Donnerstag sind Buerotage: dort passen 1x Schwimmen und 1x Beintraining,
  jeweils vor der Arbeit.
- An den uebrigen Werktagen Homeoffice mit eigenem Home-Gym: dort laufen die
  Push/Pull-Krafteinheiten (zusammen 3-4x pro Woche).
- Laufen: mindestens 1x lockerer Zone-2-Lauf (gemeinsam mit der Freundin) und
  1x Intervall- oder Schwellenlauf.
- Wochenende: NUR wenn Zeit bleibt, entweder ein Longrun ODER eine laengere
  Zwift-Ausfahrt auf dem Rad.
- Der Athlet will bewusst nicht mehr Zeit investieren. Diese Struktur ist der Idealfall
  und laesst sich in der Realitaet oft nicht vollstaendig umsetzen - fehlende Einheiten
  sind normal und kein Anlass fuer Vorwuerfe.

Coaching-Regeln daraus:
- Niemals mehr Gesamtzeit oder zusaetzliche Einheiten fordern. Wenn etwas fehlt, sage
  was innerhalb des bestehenden Rahmens umgeschichtet werden sollte (Prioritaeten setzen).
- Beruecksichtige den Wochentag: Schwimmen und Beine sind an Buerotagen (Di/Do) machbar,
  Push/Pull an Homeoffice-Tagen, laengere Rad-/Laufeinheiten am Wochenende.
- Das Rad ist beim 70.3 der groesste Zeitblock des Rennens. Wenn das Radvolumen dauerhaft
  sehr niedrig ist, benenne das klar als groesstes Risiko fuers Zeitziel - und schlage die
  Umschichtung aus einer Krafteinheit vor, statt zusaetzliche Zeit zu verlangen."""

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


def _model_from_404(message: str, tried_model: str):
    """Zieht aus einer 404-Antwort das von Google empfohlene Nachfolgemodell.

    Beispielmeldung: "This model models/gemini-2.5-flash is no longer available to
    new users. Please update your code to use models/gemini-3.6-flash ...".
    Wir nehmen das erste genannte Modell, das nicht das gerade versuchte ist."""
    for name in re.findall(r"models/([A-Za-z0-9.\-]+)", message or ""):
        if name != tried_model:
            return name
    return None


def _call_gemini(model: str, prompt: str):
    """Ein Gemini-Aufruf. Gibt (status_code, body_text_or_json) zurueck."""
    resp = requests.post(
        GEMINI_URL_TEMPLATE.format(model=model),
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "content-type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            # Die Flash-Modelle sind "Thinking"-Modelle: interne Denk-Tokens zaehlen mit
            # gegen maxOutputTokens. Bei einem knappen Budget kann das Modell alles fuers
            # Denken verbrauchen und einen Kandidaten ganz ohne Text-Part zurueckliefern
            # (finishReason MAX_TOKENS) - ohne HTTP-Fehler. Daher grosszuegige Obergrenze;
            # der sichtbare Text bleibt kurz, weil der Prompt 3-4 Saetze vorgibt.
            "generationConfig": {"maxOutputTokens": 2000},
        },
        # Thinking-Modelle brauchen fuer diesen Prompt teils deutlich mehr als 30s
        # (genau daran ist der erste Versuch mit gemini-3.6-flash gescheitert:
        # "Read timed out"). Der Aufruf blockiert nichts Kritisches mehr, seit die
        # Messwerte in app.py bereits VOR der KI-Anfrage publiziert werden.
        timeout=GEMINI_TIMEOUT,
    )
    return resp


def generate_coaching_note(data: dict) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")

    metrics = extract_metrics(data)
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    wv = data.get("weekly_volumes") or {}

    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    today_name = weekdays[datetime.date.today().weekday()]

    prompt = (
        "Du bist ein Ausdauersport-Coach fuer einen Age-Group-Athleten in der Vorbereitung "
        f"auf einen Ironman 70.3 am 29.08.2027. Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Heute ist {today_name}.\n"
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
        "Gib mir einen kurzen, ehrlichen Coaching-Tipp fuer heute auf Deutsch - als Stichpunkte im "
        "Markdown-Format, JEDER Punkt eine eigene Zeile beginnend mit '- ', KEIN Fliesstext und "
        "KEIN einleitender Satz davor. Genau 2-3 Punkte:\n"
        "- Ein Punkt: kurze Einschaetzung der Erholungslage (1 Satz).\n"
        "- Ein Punkt: eine konkrete Trainingsempfehlung fuer heute, die zur aktuellen Phase UND zum "
        "heutigen Wochentag passt (siehe Wochenstruktur oben) (1 Satz).\n"
        "- NUR falls Erholungswerte (Readiness, HRV, Body Battery, Schlaf) auf Uebertraining oder "
        "unzureichende Erholung hindeuten: ein dritter Punkt mit explizit leichterem Training oder "
        "einem Ruhetag statt eines harten Reizes (sonst diesen Punkt weglassen).\n"
        "Nenne nicht jeden einzelnen Rohwert einzeln, sondern ziehe pro Punkt eine klare, direkt "
        "umsetzbare Schlussfolgerung."
    )

    model = GEMINI_MODEL
    resp = _call_gemini(model, prompt)

    if resp.status_code == 404:
        # Google zieht Modelle fuer neue Accounts zurueck und nennt in der 404-Antwort
        # das Nachfolgemodell. Einmal automatisch nachziehen, statt den Coaching-Tipp
        # ausfallen zu lassen, bis jemand die Version haendisch anpasst.
        successor = _model_from_404(resp.text, model)
        if successor:
            print(f"[ai_coach] Modell '{model}' nicht verfuegbar, wechsle auf '{successor}'")
            model = successor
            resp = _call_gemini(model, prompt)

    if resp.status_code >= 400:
        # Antwortkoerper mitloggen: Gemini erklaert darin praezise, was fehlt
        # (ungueltiger Key, unbekanntes Modell, Quota erschoepft, ...).
        raise RuntimeError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:400]}")
    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        # Gemini liefert bei Safety-Blocks o.ae. leere candidates statt eines Fehlers -
        # dann lieber eine klare Meldung als ein KeyError.
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise RuntimeError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        # Nicht still "" zurueckgeben: publish_state() published leere Notizen gar nicht,
        # dann bleibt im Dashboard kommentarlos die alte Notiz stehen und der Fehler
        # bleibt unsichtbar - genau die Klasse von Bug, die dieses Projekt schon zweimal
        # ausgebremst hat.
        raise RuntimeError(
            f"Gemini ({model}) hat leeren Text geliefert "
            f"(finishReason: {candidate.get('finishReason')}, "
            f"usageMetadata: {body.get('usageMetadata')})"
        )
    return text


def _trend(current, previous, unit="", better="hoch"):
    """Formatiert 'Wert (Vorwoche: X)' fuer den Wochenreport."""
    if current is None:
        return "keine Daten"
    if previous is None:
        return f"{current}{unit} (keine Vorwochendaten)"
    delta = round(current - previous, 1)
    sign = "+" if delta > 0 else ""
    return f"{current}{unit} (Vorwoche {previous}{unit}, {sign}{delta})"


def _format_strength_sessions(sessions: list) -> str:
    """Formatiert die per FIT-Datei erkannten Uebungen/Saetze (siehe
    fit_exercises.py) fuer den Wochenreport-Prompt. Best-Effort: liefert '',
    wenn keine Session verwertbare Uebungsdetails hat - der Prompt behauptet
    dann einfach nichts zu einzelnen Uebungen, statt Luecken zu erfinden."""
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
            detail = f"{len(sets)} Saetze"
            if reps:
                detail += f", {'/'.join(reps)} Wdh."
            parts.append(f"{ex.get('exercise', '?')} ({detail})")
        if parts:
            lines.append(f"{day_name}: " + ", ".join(parts))
    return "\n".join(lines)


def generate_weekly_report(data: dict, summary: dict) -> str:
    """Woechentlicher Rueckblick: Soll/Ist der Wochenstruktur, Trends, Fokus fuer die
    kommende Woche. Nutzt dieselbe Gemini-Anbindung wie die Tagesnotiz."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")

    s = summary or {}
    phase = data.get("phase") or "unbekannt"
    focus = PHASE_FOCUS.get(phase, "")
    days_left = data.get("days_to_race")

    # Belastbarkeit der Trenddaten ehrlich benennen: die Historie fuellt sich erst
    # ueber die ersten Tage, vorher waeren "Trends" reine Behauptung.
    history_days = s.get("history_days") or 0
    trend_note = (
        "Die Trenddaten sind belastbar."
        if history_days >= 10 else
        f"ACHTUNG: Es liegen erst {history_days} Tage Historie vor - Trendaussagen zu "
        "Ruhepuls/HRV/Schlaf sind noch NICHT belastbar, sag das offen statt sie zu deuten."
    )

    # Einzelne erkannte Kraft-Uebungen (Best-Effort aus der Original-FIT-Datei, siehe
    # fit_exercises.py) - nur einbauen, wenn tatsaechlich etwas Verwertbares vorliegt.
    strength_detail = _format_strength_sessions(data.get("strength_exercises"))
    strength_block = (
        "- Davon erkannte Kraft-Uebungen (Best-Effort aus der Original-Geraetedatei, "
        f"nicht garantiert vollstaendig):\n{strength_detail}"
        if strength_detail else ""
    )

    prompt = (
        "Du bist ein Ausdauersport-Coach und schreibst den woechentlichen Rueckblick fuer "
        f"einen Age-Group-Athleten in der Vorbereitung auf einen Ironman 70.3 am 29.08.2027. "
        f"Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Trainingsphase: {phase} (Fokus: {focus}). Noch {_fmt(days_left, ' Tage')} bis zum Rennen.\n\n"
        "SOLL laut Wochenstruktur: 1x Schwimmen, 2x Laufen (1x Zone 2, 1x Intervall/Schwelle), "
        "4-5x Kraft (1x Beine + 3-4x Push/Pull), Rad optional am Wochenende.\n\n"
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
        f"Veraenderung {_fmt(s.get('volume_change_pct'), '%')})\n"
        f"{strength_block}\n"
        "Erholung im Wochenmittel:\n"
        f"- Ruhepuls: {_trend(s.get('resting_hr_avg'), s.get('resting_hr_avg_prev'), ' bpm')}\n"
        f"- HRV: {_trend(s.get('hrv_avg'), s.get('hrv_avg_prev'), ' ms')}\n"
        f"- Schlaf: {_trend(s.get('sleep_hours_avg'), s.get('sleep_hours_avg_prev'), ' h')}\n"
        f"- Training Readiness: {_trend(s.get('readiness_avg'), s.get('readiness_avg_prev'))}\n"
        f"{trend_note}\n\n"
        "Schreibe den woechentlichen Rueckblick auf Deutsch als Stichpunkte im Markdown-Format, "
        "JEDER Punkt eine eigene Zeile beginnend mit '- ', KEIN Fliesstext und KEIN einleitender "
        "Satz davor. Genau diese Punkte, je maximal 1-2 Saetze, keine Wiederholung der reinen "
        "Zahlen (die stehen bereits in der Tabelle im Dashboard):\n"
        "- Wie war der Zeitraum im Vergleich zur Wochenstruktur und zum Vorzeitraum?\n"
        "- Was sagen Belastung und Erholung zusammen - passt die Progression (Faustregel: "
        "Steigerung der Gesamtbelastung um mehr als ~10% pro Woche ist riskant)?\n"
        "- EIN konkreter Fokus fuer die kommende Woche, umsetzbar im bestehenden Zeitrahmen.\n"
        "- NUR falls das Zeitziel durch zu wenig Radtraining gefaehrdet ist: ein eigener Punkt "
        "dazu (sonst weglassen).\n"
        "Sei realistisch und ohne Vorwuerfe: verpasste Einheiten sind eingeplant."
    )

    resp = _call_gemini(GEMINI_MODEL, prompt)
    if resp.status_code == 404:
        successor = _model_from_404(resp.text, GEMINI_MODEL)
        if successor:
            print(f"[weekly] Modell nicht verfuegbar, wechsle auf '{successor}'")
            resp = _call_gemini(successor, prompt)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:400]}")

    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise RuntimeError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(
            f"Gemini hat leeren Text geliefert "
            f"(finishReason: {candidates[0].get('finishReason')})"
        )
    return text
