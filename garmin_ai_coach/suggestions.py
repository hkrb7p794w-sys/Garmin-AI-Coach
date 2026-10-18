"""Gemeinsamer Vorschlags-Pool des KI-Coaches (Dashboard: Reiter "Chat",
Abschnitt "Coach"; Auftrag Alex 11.09.2026, erweitert 18.10.2026).

Quellen
- "gym_kritik": feste, von Hand gepflegte Gym-Punkte (TRAININGSPLAN_GYM_KRITIK
  in ai_coach.py). Statisch - Titel/Text kommen nur aus dem Code.
- "trainingsplan_kommentar": Gemini-Vorschläge beim ereignisgesteuerten
  Plan-Kommentar (Phasenwechsel, Readiness, VO2max, FTP).
- "wochenreport": Gemini-Vorschläge aus dem Wochenreport (montags bzw. beim
  "Jetzt synchronisieren") - deckt alle Disziplinen ab.

Jeder Vorschlag hat eine Disziplin (schwimmen/rad/laufen/gym/erholung/
allgemein), damit das Dashboard ihn einsortieren kann.

Keine Dopplungen, keine Widersprüche (seit v0.23.0)
1. Gemini bekommt vor jeder Generierung den KOMPLETTEN Pool (offen,
   angenommen, abgelehnt, feste Gym-Punkte) mit ids zu sehen und muss eine
   bestehende id wiederverwenden, statt denselben Inhalt neu anzulegen.
2. Zusätzlich deterministischer Abgleich (similar()): ein neuer Vorschlag mit
   im Kern gleichem Titel in derselben Disziplin wird auf den bestehenden
   Eintrag abgebildet - ein fester Gym-Punkt oder eine frühere Entscheidung
   (angenommen/abgelehnt) hat Vorrang.
3. Die dynamische Liste einer Generierung ERSETZT die bisher offenen
   KI-Vorschläge: was Gemini nicht erneut aufführt, gilt als überholt
   ("superseded", wird nicht mehr angezeigt). So bleibt immer nur die neueste,
   in sich stimmige Einschätzung offen - ein älterer Rat ("diese Woche
   Intensität raus") kann einem neueren nicht widersprechen.
4. Offene KI-Vorschläge verfallen nach MAX_PENDING_AGE_DAYS ohne erneute
   Bestätigung (sie beziehen sich meist auf eine konkrete Woche).

"Annehmen" = als entschieden merken und künftigen Prompts als umgesetzt
mitgeben (keine automatische Planänderung). "Ablehnen" = nicht mehr anzeigen
und nicht erneut vorschlagen; per erneutem "Annehmen" reaktivierbar.
"""
import os
import re
import json
import datetime

DATA_DIR = "/data"
SUGGESTIONS_FILE = os.path.join(DATA_DIR, "suggestions_state.json")

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"   # überholt/zusammengeführt - unsichtbar
VISIBLE_STATUSES = (STATUS_PENDING, STATUS_ACCEPTED, STATUS_REJECTED)

STATIC_SOURCES = {"gym_kritik"}
MAX_PENDING_AGE_DAYS = 10

DISCIPLINES = {
    "schwimmen": "🏊",
    "rad": "🚴",
    "laufen": "🏃",
    "gym": "🏋️",
    "erholung": "😴",
    "allgemein": "🎯",
}
DISCIPLINE_ALIASES = {
    "swim": "schwimmen", "schwimm": "schwimmen",
    "bike": "rad", "radfahren": "rad", "zwift": "rad",
    "run": "laufen", "lauf": "laufen",
    "kraft": "gym", "krafttraining": "gym", "strength": "gym",
    "regeneration": "erholung", "schlaf": "erholung", "recovery": "erholung",
}
# Reihenfolge = Priorität bei der Stichwort-Zuordnung (Gym zuerst: "Kreuzheben
# für die Laufbelastung" ist eine Gym-Massnahme, keine Laufmassnahme).
_KEYWORDS = [
    ("gym", ("gym", "kraft", "kreuzheben", "plank", "kniebeug", "beinpress", "beinstreck",
             "beinbeug", "bankdr", "rudern", "latzieh", "curl", "crunch", "dips", "ausfallschritt",
             "satz", "sätze", "wiederholung", "pallof", "fersenheb", "übung")),
    ("schwimmen", ("schwimm", "css", "kraul", "pool", "becken", "freiwasser", "neopren")),
    ("rad", ("rad", "zwift", "ftp", "watt", "bike", "sweet spot", "trittfrequenz")),
    ("laufen", ("lauf", "läuf", "longrun", "fahrtspiel", "intervall", "pace", "marathon",
                "schwellenlauf", "koppel")),
    ("erholung", ("schlaf", "erholung", "ruhetag", "regeneration", "hrv", "readiness",
                  "deload", "entlastung")),
]

# Für den Titelvergleich bedeutungsarme Wörter (Füllwörter und generische
# Handlungsverben - "ergänzen" vs. "integrieren" vs. "aufnehmen" ist derselbe
# Vorschlag). Richtungsverben wie reduzieren/steigern bleiben bewusst drin.
_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer",
    "und", "oder", "im", "in", "ins", "am", "an", "auf", "aus", "bei", "mit", "zu", "zum",
    "zur", "fuer", "von", "vom", "durch", "statt", "als", "pro", "je", "deinem", "deinen",
    "dein", "deine", "deiner", "dich", "dir", "noch", "mehr", "weiter", "bestehend",
    "bestehenden", "programm", "training", "trainingsplan", "plan", "woche", "wochen",
    "einheit", "einheiten", "gym", "krafttraining", "kraft", "home",
    "ersetzen", "ersetzt", "ergaenzen", "ergaenzt", "aufnehmen", "integrieren", "einbauen",
    "hinzufuegen", "nutzen", "einplanen", "beibehalten", "halten", "machen", "trainieren",
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _parse_ts(value):
    try:
        ts = datetime.datetime.fromisoformat(str(value))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return ts
    except Exception:
        return None


def _translit(s: str) -> str:
    return (s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            .replace("ß", "ss"))


def normalize_id(raw: str) -> str:
    """kebab-case-id; Umlaute transliteriert statt verschluckt
    (vorher wurde aus "plank-ergänzen" "plank-erg-nzen")."""
    return re.sub(r"[^a-z0-9-]+", "-", _translit(str(raw or ""))).strip("-")


def normalize_discipline(raw, title: str = "", text: str = "") -> str:
    d = _translit(str(raw or "")).strip()
    d = DISCIPLINE_ALIASES.get(d, d)
    if d in DISCIPLINES:
        return d
    return classify(title, text)


def classify(title: str, text: str = "") -> str:
    """Stichwort-Zuordnung, wenn Gemini keine (gültige) Disziplin liefert -
    zuerst nur der Titel, dann Titel + Text."""
    for blob in (title or "", f"{title or ''} {text or ''}"):
        low = blob.lower()
        for disc, words in _KEYWORDS:
            if any(w in low for w in words):
                return disc
    return "allgemein"


def _tokens(title: str) -> set:
    out = set()
    for w in re.split(r"[^a-z0-9]+", _translit(title or "")):
        if len(w) < 3 or w in _STOPWORDS:
            continue
        for suf in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
            if len(w) > 5 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.add(w[:8])
    return out


def similar(a: dict, b: dict) -> bool:
    """Gleicher Vorschlag? Gleiche Disziplin und mindestens zwei gemeinsame
    Kernbegriffe im Titel, die mindestens 60 % des kürzeren Titels ausmachen.
    Beispiele aus dem echten Bestand: "Plank/Side Plank ergänzen" ==
    "Plank und Side Plank ins Gym integrieren"; "Schwellenlauf durch lockeres
    Fahrtspiel ersetzen" != "Zwift-Einheit strikt regenerativ halten"."""
    da, db = a.get("discipline"), b.get("discipline")
    if da and db and da != db:
        return False
    ta, tb = _tokens(a.get("title")), _tokens(b.get("title"))
    if not ta or not tb:
        return False
    shared = len(ta & tb)
    return shared >= 2 and shared / min(len(ta), len(tb)) >= 0.6


def _load() -> dict:
    if not os.path.exists(SUGGESTIONS_FILE):
        return {}
    try:
        with open(SUGGESTIONS_FILE) as f:
            state = json.load(f) or {}
    except Exception as e:
        print(f"[suggestions] Zustand nicht lesbar, starte neu: {e}")
        return {}
    for rec in state.values():   # Altbestand (vor v0.23.0) ohne Disziplin
        if not rec.get("discipline"):
            rec["discipline"] = classify(rec.get("title"), rec.get("text"))
    return state


def _save(state: dict):
    try:
        with open(SUGGESTIONS_FILE, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[suggestions] Zustand konnte nicht geschrieben werden: {e}")


def _supersede(rec: dict, now: str, by: str = None, reason: str = ""):
    rec["status"] = STATUS_SUPERSEDED
    rec["superseded_at"] = now
    if by:
        rec["superseded_by"] = by
    if reason:
        rec["superseded_reason"] = reason


def _match_priority(rec: dict) -> int:
    """Wohin wird ein doppelter Vorschlag abgebildet? Fester Gym-Punkt vor
    Entscheidung vor offenem vor überholtem Eintrag."""
    if rec.get("source") in STATIC_SOURCES:
        return 0
    return {STATUS_ACCEPTED: 1, STATUS_REJECTED: 1, STATUS_PENDING: 2}.get(rec.get("status"), 3)


def _find_similar(state: dict, item: dict, exclude=()):
    hits = [(sid, rec) for sid, rec in state.items() if sid not in exclude and similar(item, rec)]
    if not hits:
        return None
    hits.sort(key=lambda kv: (_match_priority(kv[1]), kv[1].get("created_at") or ""))
    return hits[0][0]


def sync_static(source: str, items: list) -> dict:
    """Feste Punkte (gym_kritik): anlegen bzw. Titel/Text aktualisieren,
    Status bleibt. Ein früher als überholt markierter fester Punkt wird
    wieder offen."""
    state = _load()
    now = _now()
    for item in items or []:
        sid = item.get("id")
        if not sid:
            continue
        existing = state.get(sid) or {}
        status = existing.get("status") or STATUS_PENDING
        if status == STATUS_SUPERSEDED:
            status = STATUS_PENDING
        state[sid] = {
            **existing,
            "status": status,
            "title": item.get("title") or sid,
            "text": item.get("text") or "",
            "source": source,
            "discipline": normalize_discipline(item.get("discipline"), item.get("title"), item.get("text")),
            "created_at": existing.get("created_at") or now,
            "updated_at": existing.get("updated_at") or now,
            "last_seen": now,
        }
        for k in ("superseded_at", "superseded_by", "superseded_reason"):
            state[sid].pop(k, None)
    _save(state)
    return state


def sync_dynamic(source: str, items) -> dict:
    """Übernimmt die Vorschlagsliste einer Gemini-Generierung.

    items=None heisst "Antwort nicht auswertbar" - dann bleibt alles, wie es
    ist (nichts wird fälschlich als überholt markiert). Eine leere Liste heisst
    dagegen "aktuell nichts zu ändern" und schliesst offene KI-Vorschläge."""
    state = _load()
    if items is None:
        return state
    now = _now()
    kept = set()
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        text = (item.get("text") or "").strip()
        cand = {
            "title": title,
            "text": text,
            "discipline": normalize_discipline(item.get("discipline"), title, text),
        }
        sid = normalize_id(item.get("id"))
        target = sid if sid in state else None
        if target and state[target].get("status") == STATUS_SUPERSEDED:
            # Früher zusammengeführte id: auf den Zieleintrag umleiten statt die Dublette
            # wiederzubeleben (z. B. "rumaenisches-kreuzheben" -> fester Gym-Punkt).
            active = {k: v for k, v in state.items() if v.get("status") != STATUS_SUPERSEDED}
            alt = state[target].get("superseded_by")
            target = alt if alt in active else (_find_similar(active, cand) or target)
        if not target:
            target = _find_similar(state, cand)
        if target in kept:
            continue   # Dublette innerhalb derselben Antwort
        if target and target != sid and sid:
            print(f"[suggestions] '{sid}' ist inhaltlich '{target}' - zusammengeführt")
        if target:
            rec = state[target]
            rec["last_seen"] = now
            if rec.get("source") not in STATIC_SOURCES:
                if rec.get("status") == STATUS_SUPERSEDED:
                    rec["status"] = STATUS_PENDING
                    for k in ("superseded_at", "superseded_by", "superseded_reason"):
                        rec.pop(k, None)
                if rec.get("status") == STATUS_PENDING:
                    rec.update(cand)
                    rec["source"] = source
                    rec["updated_at"] = now
            kept.add(target)
            continue
        if not sid:
            continue
        state[sid] = {
            "status": STATUS_PENDING, **cand, "source": source,
            "created_at": now, "updated_at": now, "last_seen": now,
        }
        kept.add(sid)
    for sid, rec in state.items():
        if (rec.get("status") == STATUS_PENDING and rec.get("source") not in STATIC_SOURCES
                and sid not in kept):
            _supersede(rec, now, reason=f"nicht mehr in der neuesten Einschätzung ({source})")
    _save(state)
    return state


def sync_suggestions(source: str, items) -> dict:
    """Kompatibler Einstieg: statische Quelle -> sync_static, sonst sync_dynamic."""
    if source in STATIC_SOURCES:
        return sync_static(source, items)
    return sync_dynamic(source, items)


def cleanup(now_dt: datetime.datetime = None) -> dict:
    """Bestandspflege bei jedem Sync: (a) offene KI-Vorschläge ohne Bestätigung
    seit MAX_PENDING_AGE_DAYS verfallen, (b) offene Dubletten werden auf den
    vorrangigen Eintrag (fester Gym-Punkt, Entscheidung, ältester offener)
    zusammengeführt. Räumt auch den Altbestand vor v0.23.0 auf."""
    state = _load()
    now_dt = now_dt or datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.isoformat()
    changed = False
    for sid, rec in state.items():
        if rec.get("status") != STATUS_PENDING or rec.get("source") in STATIC_SOURCES:
            continue
        seen = _parse_ts(rec.get("last_seen") or rec.get("updated_at") or rec.get("created_at"))
        if seen and (now_dt - seen).days >= MAX_PENDING_AGE_DAYS:
            _supersede(rec, now, reason=f"älter als {MAX_PENDING_AGE_DAYS} Tage")
            changed = True
    ordered = sorted(state.items(), key=lambda kv: (_match_priority(kv[1]), kv[1].get("created_at") or ""))
    for sid, rec in ordered:
        if rec.get("status") != STATUS_PENDING or rec.get("source") in STATIC_SOURCES:
            continue
        others = {k: v for k, v in state.items() if v.get("status") != STATUS_SUPERSEDED}
        target = _find_similar(others, rec, exclude={sid})
        if target and _match_priority(state[target]) <= _match_priority(rec):
            _supersede(rec, now, by=target, reason="Dublette")
            changed = True
    if changed:
        _save(state)
    return state


def set_status(suggestion_id: str, status: str) -> bool:
    """Annehmen/Ablehnen über die Dashboard-Buttons (app.py)."""
    if status not in (STATUS_PENDING, STATUS_ACCEPTED, STATUS_REJECTED):
        raise ValueError(f"Unbekannter Status: {status}")
    state = _load()
    if suggestion_id not in state:
        return False
    state[suggestion_id]["status"] = status
    state[suggestion_id]["updated_at"] = _now()
    for k in ("superseded_at", "superseded_by", "superseded_reason"):
        state[suggestion_id].pop(k, None)
    _save(state)
    return True


def all_suggestions() -> dict:
    """Gesamter Zustand inkl. überholter Einträge (die Anzeige filtert)."""
    return _load()


def visible_suggestions() -> dict:
    return {k: v for k, v in _load().items() if v.get("status") in VISIBLE_STATUSES}


def by_source(source: str) -> dict:
    return {k: v for k, v in _load().items() if v.get("source") == source}


def context_for_prompt(source: str = None, max_items: int = 30) -> str:
    """Kontextblock für JEDEN Gemini-Prompt, der Vorschläge erzeugt oder
    Empfehlungen gibt (Plan-Kommentar, Wochenreport, Gym-Tipp). Enthält den
    ganzen Pool quellenübergreifend - Dopplungen entstanden vorher genau
    daran, dass Gemini die offenen Punkte anderer Quellen nicht mit id sah.
    `source` wird aus Kompatibilitätsgründen angenommen und ignoriert."""
    state = visible_suggestions()
    if not state:
        return ""

    def line(sid, v, with_text=True):
        txt = f": {v.get('text')}" if with_text and v.get("text") else ""
        return f"- [{sid}] ({v.get('discipline')}) {v.get('title')}{txt}"

    groups = [
        ("Feste Gym-Anpassungen (vom Athleten selbst zu entscheiden; NICHT als neuen "
         "Vorschlag wiederholen, höchstens im Text darauf verweisen)",
         [(k, v) for k, v in state.items()
          if v.get("source") in STATIC_SOURCES and v["status"] == STATUS_PENDING], True),
        ("Offene KI-Vorschläge (noch unentschieden)",
         [(k, v) for k, v in state.items()
          if v.get("source") not in STATIC_SOURCES and v["status"] == STATUS_PENDING], True),
        ("ANGENOMMEN (gilt als umgesetzt - darauf aufbauen, nicht erneut vorschlagen, "
         "nicht widersprechen)",
         [(k, v) for k, v in state.items() if v["status"] == STATUS_ACCEPTED], False),
        ("ABGELEHNT (nicht erneut vorschlagen, auch nicht umformuliert)",
         [(k, v) for k, v in state.items() if v["status"] == STATUS_REJECTED], False),
    ]
    lines = ["Bisherige Coach-Vorschläge (id in eckigen Klammern, Disziplin in runden):"]
    n = 0
    for head, items, with_text in groups:
        if not items:
            continue
        items.sort(key=lambda kv: kv[1].get("updated_at") or "", reverse=True)
        lines.append(f"{head}:")
        for sid, v in items:
            if n >= max_items:
                break
            lines.append(line(sid, v, with_text))
            n += 1
    return "\n".join(lines)
