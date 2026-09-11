"""Verwaltung des Chatverlaufs fuer die freie Gemini-Chat-Funktion im
Dashboard-Tab "Chat" (siehe claude/status-und-plan.md im Projekt fuer den
Auftrag von Alex, 11.09.2026: "Chat integrieren, sodass ich gezielte Fragen
ueber die API an Gemini stellen kann").

Design-Entscheidung (per AskUserQuestion mit Alex abgestimmt): MQTT-basiert
(ein "text"-Entity zum Eingeben der Frage, Antwort kommt als Sensor-Attribut
zurueck), MIT dem aktuellen Trainingskontext (Readiness, VO2max, Phase,
Wochenvolumen etc. werden bei jeder Frage automatisch an Gemini mitgegeben,
siehe ai_coach.generate_chat_answer) und MIT gespeichertem Verlauf (mehrere
zurueckliegende Frage-Antwort-Paare bleiben sichtbar).

Bewusst ein eigenes, schlankes Modul statt Teil von app.py - analog zu
suggestions.py: reine Datei-Persistenz, kein Gemini-Aufruf hier drin (der
lebt in ai_coach.generate_chat_answer, aufgerufen von app.py)."""
import os
import json
import datetime

DATA_DIR = "/data"
CHAT_FILE = os.path.join(DATA_DIR, "chat_history.json")

# Wie viele Frage-Antwort-Paare dauerhaft gespeichert/im Dashboard angezeigt
# werden. Begrenzt, damit die Datei nicht unbegrenzt waechst und die
# Markdown-Card im Dashboard nicht endlos lang wird (analog zu HISTORY_DAYS/
# STRENGTH_CACHE_DAYS in app.py).
MAX_STORED = 30
# Wie viele der letzten Austausche als Kontext in den naechsten Gemini-Prompt
# wandern (siehe context_for_prompt) - klein gehalten, damit der Prompt nicht
# unnoetig gross wird; fuer echte Anschlussfragen reichen wenige reichen.
DEFAULT_CONTEXT_TURNS = 5


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load() -> list:
    if not os.path.exists(CHAT_FILE):
        return []
    try:
        with open(CHAT_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[chat] Verlauf nicht lesbar, starte neu: {e}")
        return []


def _save(entries: list):
    try:
        with open(CHAT_FILE, "w") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[chat] Verlauf konnte nicht geschrieben werden: {e}")


def add_exchange(question: str, answer: str) -> list:
    """Haengt eine neue Frage+Antwort an den Verlauf an, begrenzt auf
    MAX_STORED Eintraege (aelteste fallen zuerst raus). Gibt den kompletten
    (bereits begrenzten) Verlauf zurueck."""
    entries = _load()
    entries.append({
        "question": question,
        "answer": answer,
        "asked_at": _now(),
    })
    entries = entries[-MAX_STORED:]
    _save(entries)
    return entries


def all_exchanges() -> list:
    """Kompletter gespeicherter Verlauf, chronologisch (aelteste zuerst) -
    fuer die Anzeige im Dashboard (dort neueste zuerst sortiert per
    Jinja-`reverse`, siehe Dashboard-View "chat")."""
    return _load()


def recent(n: int = DEFAULT_CONTEXT_TURNS) -> list:
    """Die letzten n Austausche, chronologisch (aelteste zuerst) - fuer den
    Konversations-Kontext im naechsten Gemini-Prompt (siehe
    ai_coach.generate_chat_answer/context_for_prompt unten)."""
    entries = _load()
    return entries[-n:] if n else []


def context_for_prompt(n: int = DEFAULT_CONTEXT_TURNS) -> str:
    """Baut den Konversationsverlauf-Block fuer den naechsten Gemini-Prompt,
    damit Anschlussfragen ("und wie sieht das bei X aus?") funktionieren.
    Gibt "" zurueck, wenn es noch keinen Verlauf gibt (dann taucht im Prompt
    auch kein leerer/nutzloser Abschnitt auf)."""
    entries = recent(n)
    if not entries:
        return ""
    lines = ["Bisheriger Gespraechsverlauf in diesem Chat (fuer Anschlussfragen):"]
    for entry in entries:
        lines.append(f"Athlet: {entry.get('question', '')}")
        lines.append(f"Coach: {entry.get('answer', '')}")
    return "\n".join(lines)
