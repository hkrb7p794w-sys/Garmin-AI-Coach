"""Wettkampfspezifische Laufeinheiten zum Annehmen oder Ablehnen (seit 0.26.0).

Auftrag Alex 21.10.2026: Laufeinheiten zur Vorbereitung auf einen Wettkampf
(Marathontempo, Renntempo für Almere, Tempo in Taper- und Rennwoche,
Longrun-Abschnitte im Marathontempo) sollen als solche gekennzeichnet sein, und
er entscheidet einzeln, ob er sie läuft. Sonst gilt das Grundmuster: Z2-Lauf
plus im Wechsel Schwelle oder 4x4 min.

Quelle: run_plan.json (erzeugt von scripts/gen_run_plan.py aus demselben
Saisonplan wie custom_templates/coach_plan.jinja). Felder qw/qa/qca
(Qualitätslauf) und lw/la (Longrun).

Ablauf:
- Jede Einheit der nächsten WINDOW_DAYS Tage wird ein Eintrag im
  Vorschlags-Pool (suggestions.py, Quelle "wettkampf", id
  wk-lauf-<Montag>-q bzw. -l) und erscheint im Dashboard-Reiter Chat.
- Annehmen: Die Einheit bleibt (im Plan mit 🏁 markiert).
- Ablehnen: Das Dashboard zeigt die Alternative. coach_plan.jinja liest die
  Entscheidungen aus dem Attribut `wettkampf` des Vorschlags-Sensors.
- Ohne Entscheidung bleibt die Einheit stehen, markiert als „offen“.
"""
import os
import re
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = os.path.join(HERE, "run_plan.json")
WINDOW_DAYS = 21          # so weit im Voraus wird gefragt
SOURCE = "wettkampf"

TOKENS = {"§MP§": "Marathontempo", "§T§": "Schwellenpace", "§R§": "Renn-Laufpace (Almere)",
          "§E§": "lockeres Tempo", "§I§": "Intervallpace"}


def _clean(text: str) -> str:
    text = text or ""
    for k, v in TOKENS.items():
        text = text.replace(k, v)
    return re.sub(r"§[^§]*§", "", text)


def _load() -> list:
    try:
        with open(PLAN_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def goal(phase: str) -> str:
    return "Marathon 02.05." if phase.startswith("Marathon") else "Challenge Almere 11.09."


def items(today: datetime.date = None) -> list:
    """Vorschlags-Einträge für alle wettkampfspezifischen Laufeinheiten, deren Woche
    in den nächsten WINDOW_DAYS Tagen liegt (inkl. der laufenden Woche)."""
    today = today or datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    until = today + datetime.timedelta(days=WINDOW_DAYS)
    out = []
    for w in _load():
        start = datetime.date.fromisoformat(w["w"])
        if start < monday or start > until:
            continue
        kw = start.isocalendar()[1]
        span = f"KW {kw}, {start:%d.%m.}–{start + datetime.timedelta(days=6):%d.%m.}"
        if w.get("qw"):
            out.append({
                "id": f"wk-lauf-{w['w']}-q",
                "discipline": "laufen",
                "title": f"🏁 {w['qc']} ({span})",
                "text": (f"Wettkampfspezifisch für {goal(w['ph'])}: {_clean(w['q'])}. "
                         f"Annehmen = so laufen. Ablehnen = stattdessen {_clean(w['qa'])}."),
            })
        if w.get("lw"):
            out.append({
                "id": f"wk-lauf-{w['w']}-l",
                "discipline": "laufen",
                "title": f"🏁 Longrun mit Wettkampftempo ({span})",
                "text": (f"Wettkampfspezifisch für {goal(w['ph'])}: {_clean(w['l'])}. "
                         f"Annehmen = so laufen. Ablehnen = {_clean(w['la'])}."),
            })
    return out
