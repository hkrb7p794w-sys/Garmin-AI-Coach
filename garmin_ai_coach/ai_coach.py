import os
import re
import json
import datetime
import requests
from ha_publish import extract_metrics

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

# Realer Wochenrahmen des Athleten (von ihm selbst vorgegeben). Der Coach soll
# INNERHALB dieses Rahmens optimieren und niemals einfach "mehr Zeit" fordern.
ATHLETE_PROFILE = """Wochenstruktur des Athleten (fester Rahmen, nicht verhandelbar):
- Dienstag + Donnerstag sind Bürotage: dort passen 1x Schwimmen und 1x Beintraining,
  jeweils vor der Arbeit.
- An den übrigen Werktagen Homeoffice mit eigenem Home-Gym: dort laufen die
  Push/Pull-Krafteinheiten (zusammen 3-4x pro Woche).
- Laufen: mindestens 1x lockerer Zone-2-Lauf (gemeinsam mit der Freundin) und
  1x Intervall- oder Schwellenlauf.
- Wochenende: NUR wenn Zeit bleibt, entweder ein Longrun ODER eine längere
  Zwift-Ausfahrt auf dem Rad.
- Der Athlet will bewusst nicht mehr Zeit investieren. Diese Struktur ist der Idealfall
  und lässt sich in der Realität oft nicht vollständig umsetzen - fehlende Einheiten
  sind normal und kein Anlass für Vorwürfe.

Coaching-Regeln daraus:
- Niemals mehr Gesamtzeit oder zusätzliche Einheiten fordern. Wenn etwas fehlt, sage
  was innerhalb des bestehenden Rahmens umgeschichtet werden sollte (Prioritäten setzen).
- Berücksichtige den Wochentag: Schwimmen und Beine sind an Bürotagen (Di/Do) machbar,
  Push/Pull an Homeoffice-Tagen, längere Rad-/Laufeinheiten am Wochenende.
- Das Rad ist beim 70.3 der größte Zeitblock des Rennens. Wenn das Radvolumen dauerhaft
  sehr niedrig ist, benenne das klar als größtes Risiko fürs Zeitziel - und schlage die
  Umschichtung aus einer Krafteinheit vor, statt zusätzliche Zeit zu verlangen."""

# Fokus je Trainingsphase (siehe claude/status-und-plan.md im Projekt).
PHASE_FOCUS = {
    "Grundlagenausdauer": "aerobe Basis (Zone 1-2), Schwimmtechnik, 3x/Woche je Disziplin, 2x Kraft",
    "Aufbau 1": "Schwellentraining, erste Bricks, Rad-Grundkraft",
    "Aufbau 2 (spezifisch)": "Wettkampftempo, lange Einheiten (Rad 90-100km, Lauf 18-20km)",
    "Peak": "höchstes Volumen, Formtest",
    "Taper/Rennwoche": "Volumen -40 bis -60%, Intensität halten, Rennwoche",
}

# Kompakte, phasenabhängige Zusammenfassung der Trainingspläne aus dem
# Dashboard-Tab "Trainingspläne" (View "pläne" im Dashboard "garmin-coach",
# siehe claude/status-und-plan.md) - bewusst nur die Kernpunkte je Disziplin,
# nicht die volle Markdown-Tabelle, damit der Prompt für
# generate_trainingsplan_kommentar() nicht unnötig gross wird. WICHTIG: Bei
# einer inhaltlichen Änderung der Pläne im Dashboard muss dieser Text
# manuell nachgezogen werden, sonst kommentiert Gemini einen veralteten Stand.
TRAININGSPLAN_PHASE_DETAIL = {
    "Grundlagenausdauer": (
        "Lauf: Zone-2 fix (mit der Freundin) + 4x8min Schwelle (2min Trabpause) oder Fahrtspiel "
        "30-40min, Wochenende optional Longrun 60-75min. Schwimmen: Technik-Fokus, 12-16x50m an "
        "CSS-Pace, 15s Pause, CSS-Test alle 4-6 Wochen. Rad (Zwift): 45-60min Zone 2 (Endurance) fest, "
        "Wochenende optional 60-90min locker. Kraft: bestehender Split (Push A/B, Pull A/B, Lower), "
        "2x12 Standard-Wiederholungsbereich."
    ),
    "Aufbau 1": (
        "Lauf: Zone-2 fix + 3-4x10min Schwellenpace, Longrun bis 90min (alle 3-4 Wochen mit 15-20min "
        "Tempo). Schwimmen: längere Intervalle, 6-8x100m an CSS-Pace, 20s Pause. Rad (Zwift): 60min "
        "Sweet-Spot (2x15min @88-94% FTP) fest, optional Longride bis 90min, FTP-Test zu Phasenbeginn. "
        "Kraft: bei den 5 Grundübungen (Bankdrücken, Dips, Beinpressen, enges Rudern, Lat-Ziehen eng) "
        "phasenweise (2 von 4 Wochen) auf 3x6-8 schwerer wechseln statt durchgehend 2x12."
    ),
    "Aufbau 2 (spezifisch)": (
        "Lauf: Zone-2 fix + 6x3min knapp über Schwelle (VO2max-Reiz, wechselt mit Schwelleneinheit), "
        "Longrun 100-110min inkl. 20min Renntempo (ideal als Brick direkt nach einer Radeinheit). "
        "Schwimmen: wettkampfnah, 4x400m renntemponah, wenn möglich Freiwasser-/Neopren-Gewöhnung. "
        "Rad (Zwift): Race-Simulation 60-90min bei 70-75% FTP konstant fest, danach Brick-Lauf "
        "20-30min locker. Kraft: weiter phasenweise schwerer bei den Grundübungen."
    ),
    "Peak": (
        "Lauf: Zone-2 fix + Formtest (10km oder Halbmarathon als Tempolauf), höchstes Wochenvolumen "
        "der gesamten Vorbereitung. Schwimmen: kurz halten, Frische bewahren, 8x50m zügig mit viel "
        "Pause. Rad (Zwift): längste Ausfahrt der Vorbereitung, 2:30-3:00h bei Zielwatt. Kraft: "
        "Volumen reduzieren, Fokus auf Erholung statt neuen Reizen."
    ),
    "Taper/Rennwoche": (
        "Lauf: Zone-2 fix, aber kürzer (30-40min) + 2-3x5min Renntempo, Rest locker, kein Longrun "
        "mehr. Schwimmen: kurz halten, viel Pause. Rad (Zwift): 30-40min mit kurzen "
        "Intensitätsspitzen. Kraft und Gesamtvolumen: -40 bis -60%, Intensität halten, Rennwoche."
    ),
}

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


def _call_gemini(model: str, prompt: str):
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
            "generationConfig": {"maxOutputTokens": 2000},
        },
        # Thinking-Modelle brauchen für diesen Prompt teils deutlich mehr als 30s
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
        "Du bist ein Ausdauersport-Coach für einen Age-Group-Athleten in der Vorbereitung "
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
        "Gib mir einen kurzen, ehrlichen Coaching-Tipp für heute auf Deutsch - als Stichpunkte im "
        "Markdown-Format, JEDER Punkt eine eigene Zeile beginnend mit '- ', KEIN Fliesstext und "
        "KEIN einleitender Satz davor. Genau 2-3 Punkte:\n"
        "- Ein Punkt: kurze Einschätzung der Erholungslage (1 Satz).\n"
        "- Ein Punkt: eine konkrete Trainingsempfehlung für heute, die zur aktuellen Phase UND zum "
        "heutigen Wochentag passt (siehe Wochenstruktur oben) (1 Satz).\n"
        "- NUR falls Erholungswerte (Readiness, HRV, Body Battery, Schlaf) auf Übertraining oder "
        "unzureichende Erholung hindeuten: ein dritter Punkt mit explizit leichterem Training oder "
        "einem Ruhetag statt eines harten Reizes (sonst diesen Punkt weglassen).\n"
        "Nenne nicht jeden einzelnen Rohwert einzeln, sondern ziehe pro Punkt eine klare, direkt "
        "umsetzbare Schlussfolgerung. Schreibe durchgängig in korrektem Deutsch mit echten "
        "Umlauten (ä, ö, ü, ß) - niemals die Ersatzschreibweisen ae/oe/ue/ss."
    )

    model = GEMINI_MODEL
    resp = _call_gemini(model, prompt)

    if resp.status_code == 404:
        # Google zieht Modelle für neue Accounts zurück und nennt in der 404-Antwort
        # das Nachfolgemodell. Einmal automatisch nachziehen, statt den Coaching-Tipp
        # ausfallen zu lassen, bis jemand die Version händisch anpasst.
        successor = _model_from_404(resp.text, model)
        if successor:
            print(f"[ai_coach] Modell '{model}' nicht verfügbar, wechsle auf '{successor}'")
            model = successor
            resp = _call_gemini(model, prompt)

    if resp.status_code >= 400:
        # Antwortkörper mitloggen: Gemini erklärt darin präzise, was fehlt
        # (ungültiger Key, unbekanntes Modell, Quota erschöpft, ...).
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
        # Nicht still "" zurückgeben: publish_state() published leere Notizen gar nicht,
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

    model = GEMINI_MODEL
    resp = _call_gemini(model, prompt)
    if resp.status_code == 404:
        successor = _model_from_404(resp.text, model)
        if successor:
            print(f"[ai_coach] Modell '{model}' nicht verfügbar, wechsle auf '{successor}'")
            model = successor
            resp = _call_gemini(model, prompt)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:400]}")
    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise RuntimeError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(
            f"Gemini ({model}) hat leeren Text geliefert "
            f"(finishReason: {candidate.get('finishReason')})"
        )
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

    prompt = (
        "Du bist ein Ausdauersport-Coach und schreibst den wöchentlichen Rückblick für "
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
        f"Veränderung {_fmt(s.get('volume_change_pct'), '%')})\n"
        f"{strength_block}\n"
        "Erholung im Wochenmittel:\n"
        f"- Ruhepuls: {_trend(s.get('resting_hr_avg'), s.get('resting_hr_avg_prev'), ' bpm')}\n"
        f"- HRV: {_trend(s.get('hrv_avg'), s.get('hrv_avg_prev'), ' ms')}\n"
        f"- Schlaf: {_trend(s.get('sleep_hours_avg'), s.get('sleep_hours_avg_prev'), ' h')}\n"
        f"- Training Readiness: {_trend(s.get('readiness_avg'), s.get('readiness_avg_prev'))}\n"
        f"- Training Status (aktuell): {_fmt(metrics.get('training_status_phrase'))}\n"
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

    resp = _call_gemini(GEMINI_MODEL, prompt)
    if resp.status_code == 404:
        successor = _model_from_404(resp.text, GEMINI_MODEL)
        if successor:
            print(f"[weekly] Modell nicht verfügbar, wechsle auf '{successor}'")
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
        f"Age-Group-Athleten in der Vorbereitung auf einen Ironman 70.3 am 29.08.2027. "
        f"Zielzeit: {RACE_GOAL}. Du beantwortest hier eine gezielte Frage in einem Chat - "
        "KEINE Coaching-Notiz und KEINE erzwungenen Stichpunkte, sondern eine direkte, "
        "natürliche Antwort auf genau diese Frage, so kurz wie möglich, aber vollständig.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Aktuelle Trainingsphase: {phase} (Fokus: {focus}). "
        f"Noch {_fmt(metrics['days_to_race'], ' Tage')} bis zum Rennen.\n"
        f"Für die aktuelle Phase geplant:\n{plan_detail}\n\n"
        "Aktueller Datenstand (letzter Sync):\n"
        f"- Ruhepuls: {_fmt(metrics['resting_hr'], ' bpm')}\n"
        f"- Training Readiness: {_fmt(metrics['training_readiness_score'], '%')} "
        f"({_fmt(metrics['training_readiness_level'])}), 14-Tage-Schnitt: {_fmt(readiness_14d, '%')}\n"
        f"- HRV letzte Nacht: {_fmt(metrics['hrv_avg'], ' ms')} ({_fmt(metrics['hrv_status'])})\n"
        f"- Body Battery: {_fmt(metrics['body_battery'], '%')}\n"
        f"- Schlaf: {_fmt(metrics['sleep_hours'], ' h')}, Score {_fmt(metrics['sleep_score'])}\n"
        f"- VO2max: {_fmt(metrics['vo2max'], ' ml/kg/min')}, 7-Tage-Schnitt: {_fmt(vo2max_7d, ' ml/kg/min')}\n"
        f"- Training Status: {_fmt(metrics['training_status_phrase'])}\n"
        f"- FTP (Rad, letzter bekannter Wert laut Garmin): {_fmt(metrics.get('ftp'), ' W')}\n"
        f"- HF-Pace-Kopplung Lauf (Ø letzte qualifizierende Einheiten): "
        f"{_fmt(metrics.get('decoupling_avg_pct'), '%')}\n"
        f"- Wochenvolumen bisher: Schwimmen {_fmt(wv.get('swim_km'), 'km')}, "
        f"Rad {_fmt(wv.get('bike_km'), 'km')}, Lauf {_fmt(wv.get('run_km'), 'km')}\n\n"
        "WICHTIGE EINSCHRAENKUNG (damit du nichts erfindest): Dir liegen KEINE Sensordaten zu "
        "Pace (Lauf/Schwimm) oder Körpergewicht vor (FTP siehe oben, das ist die einzige "
        "vorliegende Watt-Größe), und du hast KEINEN Lesezugriff auf die manuell im "
        "Dashboard gepflegten Zielzeit-Benchmark-Felder (Schwimm-Pace/Rad-Schnitt/Lauf-Pace) "
        "- diese sind bewusst manuell, siehe Konzept-Dokument. Falls die Frage andere Werte "
        "braucht, sag das ehrlich statt eine Zahl zu erfinden, und beziehe dich stattdessen "
        "auf die oben genannten tatsächlich vorliegenden Daten.\n"
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

    model = GEMINI_MODEL
    resp = _call_gemini(model, prompt)
    if resp.status_code == 404:
        successor = _model_from_404(resp.text, model)
        if successor:
            print(f"[ai_coach] Modell '{model}' nicht verfügbar, wechsle auf '{successor}'")
            model = successor
            resp = _call_gemini(model, prompt)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:400]}")
    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise RuntimeError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(
            f"Gemini ({model}) hat leeren Text geliefert "
            f"(finishReason: {candidate.get('finishReason')})"
        )
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
        f"auf einen Ironman 70.3 am 29.08.2027. Zielzeit: {RACE_GOAL}.\n\n"
        f"{ATHLETE_PROFILE}\n\n"
        f"Aktuelle Trainingsphase: {phase} (Fokus: {focus}).\n\n"
        "Der Athlet hat bereits konkrete, phasenabhängige Trainingspläne für Laufen, Schwimmen "
        f"und Rad im Dashboard hinterlegt. Für die aktuelle Phase gilt:\n{plan_detail}\n\n"
        f"Offene Gym-Plan-Anpassungen (bereits vorgeschlagen, Umsetzung liegt beim Athleten):\n"
        f"{gym_kritik_text}"
        f"{decided_block}\n\n"
        f"AUSLOESER für diesen Kommentar JETZT: {trigger_detail}\n\n"
        "Aktuelle Werte: "
        f"Training Readiness {_fmt(metrics['training_readiness_score'], '%')}, "
        f"Training Status {_fmt(metrics.get('training_status_phrase'))}, "
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

    model = GEMINI_MODEL
    resp = _call_gemini(model, prompt)
    if resp.status_code == 404:
        successor = _model_from_404(resp.text, model)
        if successor:
            print(f"[ai_coach] Modell '{model}' nicht verfügbar, wechsle auf '{successor}'")
            model = successor
            resp = _call_gemini(model, prompt)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {resp.status_code} (Modell {model}): {resp.text[:400]}")
    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        reason = (body.get("promptFeedback") or {}).get("blockReason", "unbekannt")
        raise RuntimeError(f"Gemini hat keinen Kandidaten geliefert (blockReason: {reason})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(
            f"Gemini ({model}) hat leeren Text geliefert "
            f"(finishReason: {candidate.get('finishReason')})"
        )
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
