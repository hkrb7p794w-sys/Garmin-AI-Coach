"""Verwaltung des Annehmen/Ablehnen-Zustands fuer KI-Trainingsplan-Vorschlaege
(Dashboard-Tab "Vorschlaege", siehe claude/status-und-plan.md im Projekt fuer
den Auftrag von Alex, 11.09.2026).

Design-Entscheidung (mit Alex abgestimmt): NUR Trainingsplan-Vorschlaege
bekommen diese Annehmen/Ablehnen-Funktion - die statische Gym-Kritik
(TRAININGSPLAN_GYM_KRITIK in ai_coach.py) und die dynamischen, per Gemini
generierten Einzelvorschlaege aus generate_trainingsplan_kommentar(). Die
anderen KI-Texte (Tages-Coaching-Tipp, Wochenreport, Gym-Coaching-Tipp) sind
eher Status-Kommentare als einzeln bewertbare Handlungsempfehlungen und
bleiben unveraendert.

"Annehmen" bedeutet (Alex' ausdruecklicher Wunsch): der Vorschlag wird als
entschieden gemerkt und kuenftigen Gemini-Prompts als Kontext mitgegeben
("bereits angenommen/umgesetzt, nicht erneut vorschlagen, darauf aufbauen") -
KEINE automatische Aenderung der Plantexte im Dashboard, die pflegt Alex
weiterhin selbst. "Ablehnen" bedeutet: der Vorschlag wird dem Athleten
vorerst nicht mehr angezeigt/vorgeschlagen, bleibt aber im Dashboard-Tab
"Vorschlaege" unter "Abgelehnt" sichtbar und laesst sich dort jederzeit
wieder auswaehlen und per erneutem "Annehmen" reaktivieren.
"""
import os
import json
import datetime

DATA_DIR = "/data"
SUGGESTIONS_FILE = os.path.join(DATA_DIR, "suggestions_state.json")

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load() -> dict:
    if not os.path.exists(SUGGESTIONS_FILE):
        return {}
    try:
        with open(SUGGESTIONS_FILE) as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[suggestions] Zustand nicht lesbar, starte neu: {e}")
        return {}


def _save(state: dict):
    try:
        with open(SUGGESTIONS_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[suggestions] Zustand konnte nicht geschrieben werden: {e}")


def sync_suggestions(source: str, items: list) -> dict:
    """Gleicht eine aktuelle Liste von Vorschlaegen ({"id","title","text"})
    einer Quelle ("gym_kritik" oder "trainingsplan_kommentar") mit dem
    gespeicherten Zustand ab.

    NEUE ids werden als "pending" angelegt. Bereits ENTSCHIEDENE ids
    (accepted/rejected) behalten ihren Status - eine erneut vorgeschlagene
    (oder weiterhin bestehende, z.B. bei der statischen Gym-Kritik) id wird
    NICHT auf "pending" zurueckgesetzt, das waere genau das Gegenteil von
    "abgelehnte Vorschlaege werden vorerst nicht erneut angezeigt". Titel/
    Text werden trotzdem aktualisiert (Gemini formuliert leicht anders, oder
    Alex passt TRAININGSPLAN_GYM_KRITIK an), damit die Anzeige nicht
    veraltet. Gibt den aktualisierten Gesamtzustand (alle Quellen) zurueck."""
    state = _load()
    now = _now()
    for item in items or []:
        sid = item.get("id")
        if not sid:
            continue
        existing = state.get(sid)
        status = existing["status"] if existing else STATUS_PENDING
        state[sid] = {
            "status": status,
            "title": item.get("title") or sid,
            "text": item.get("text") or "",
            "source": source,
            "created_at": (existing or {}).get("created_at") or now,
            "updated_at": now,
        }
    _save(state)
    return state


def set_status(suggestion_id: str, status: str) -> bool:
    """Setzt den Status eines einzelnen Vorschlags (ueber die Dashboard-
    Buttons "Annehmen"/"Ablehnen" ausgeloest, siehe app.py). Gibt False
    zurueck, wenn die id nicht (mehr) bekannt ist - z.B. eine veraltete
    Dashboard-Auswahl, nachdem ein Sync die Vorschlagsliste veraendert hat."""
    if status not in (STATUS_PENDING, STATUS_ACCEPTED, STATUS_REJECTED):
        raise ValueError(f"Unbekannter Status: {status}")
    state = _load()
    if suggestion_id not in state:
        return False
    state[suggestion_id]["status"] = status
    state[suggestion_id]["updated_at"] = _now()
    _save(state)
    return True


def all_suggestions() -> dict:
    """Gesamter Zustand (alle Quellen, alle Status) - fuer die Anzeige."""
    return _load()


def by_source(source: str) -> dict:
    """Nur die Vorschlaege einer Quelle - z.B. um vor einem
    generate_trainingsplan_kommentar()-Aufruf den aktuellen Gym-Kritik-Status
    zu kennen (angenommene/abgelehnte Punkte werden dort ausgeblendet bzw.
    markiert, siehe ai_coach._render_gym_kritik)."""
    return {k: v for k, v in _load().items() if v.get("source") == source}


def context_for_prompt(source: str) -> str:
    """Baut den Kontext-Block ueber bereits entschiedene fruehere Vorschlaege
    dieser Quelle fuer den naechsten Gemini-Prompt (siehe ai_coach.
    generate_trainingsplan_kommentar): Angenommene sollen NICHT erneut
    vorgeschlagen, sondern als bereits umgesetzt/akzeptiert behandelt werden;
    abgelehnte sollen NICHT erneut vorgeschlagen werden, ausser ein neuer,
    im Ausloeser genannter Grund rechtfertigt es ausdruecklich. Gibt "" zurueck,
    wenn es noch keine Entscheidungen gibt (dann taucht im Prompt auch kein
    leerer/nutzloser Abschnitt auf)."""
    items = by_source(source)
    accepted = [(sid, v) for sid, v in items.items() if v.get("status") == STATUS_ACCEPTED]
    rejected = [(sid, v) for sid, v in items.items() if v.get("status") == STATUS_REJECTED]
    if not accepted and not rejected:
        return ""
    lines = [
        "Bereits vom Athleten entschiedene fruehere Einzelvorschlaege aus diesem "
        "Kommentar-Kanal (nicht wortgleich wiederholen):"
    ]
    for sid, v in accepted:
        lines.append(
            f"- ANGENOMMEN (id '{sid}'): {v.get('title')} - gilt als umgesetzt/akzeptiert, "
            "baue darauf auf, schlage es NICHT erneut vor."
        )
    for sid, v in rejected:
        lines.append(
            f"- ABGELEHNT (id '{sid}'): {v.get('title')} - NICHT erneut vorschlagen, ausser ein "
            "neuer, im Ausloeser genannter Grund rechtfertigt es ausdruecklich."
        )
    lines.append(
        "Falls einer deiner neuen Vorschlaege inhaltlich identisch mit einem der oben genannten "
        "ist, wiederverwende dessen id exakt (gleiche Schreibweise), damit er als derselbe "
        "Vorschlag erkannt wird - sonst erstelle eine neue, inhaltlich passende kebab-case id."
    )
    return "\n".join(lines)
