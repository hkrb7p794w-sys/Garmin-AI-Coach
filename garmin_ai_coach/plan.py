"""Einzige Quelle der Wahrheit für den Trainingsplan (seit v0.18.0).

Vorher stand dasselbe Wissen (Soll-Werte, Phasen, Plantexte, Renndatum) an
vier bis fünf Stellen fest verdrahtet: in app.py (PHASES), ai_coach.py
(PHASE_FOCUS, TRAININGSPLAN_PHASE_DETAIL) und mehrfach als Freitext in den
Dashboard-Templates. Genau daraus entstanden die Widersprüche aus dem
Dashboard-Review vom 25.09.2026 (Soll Kraft 4-5x vs. "2x Kraft" in der
Periodisierung, "3x je Disziplin" vs. 1x Schwimmen, abgelehnte Vorschläge, die
im Dashboard weiter als offen standen).

Jetzt: alles hier. app.py publiziert den daraus berechneten Zustand als
Sensor ``sensor.garmin_ai_coach_garmin_plan`` (Attribute), das Dashboard
rendert NUR noch diese Attribute, und ai_coach.py baut seine Prompts aus
denselben Konstanten. Eine inhaltliche Planänderung passiert damit an genau
einer Stelle.
"""
import datetime

# ---------------------------------------------------------------------------
# Wochenrahmen (von Alex am 07.09.2026 vorgegeben, siehe status-und-plan.md)
# ---------------------------------------------------------------------------

# Soll je Kalenderwoche - bewusst Alex' reale Struktur, NICHT ein generischer
# Lehrbuchplan ("3x je Disziplin"), damit Fortschrittsbalken, Wochenreport und
# KI-Prompts dieselbe Messlatte benutzen.
WEEKLY_TARGETS = {
    "swim": {"min": 1, "max": 1, "label": "Schwimmen"},
    "run": {"min": 2, "max": 2, "label": "Laufen", "detail": "1x Zone 2, 1x Intervall/Schwelle"},
    "strength": {"min": 4, "max": 5, "label": "Kraft", "detail": "1x Beine + 3-4x Push/Pull"},
    # Rad hat im Rahmen keinen festen Platz (nur Wochenende, wenn Zeit bleibt) -
    # min 0, damit ein fehlender Radtag nicht als "Soll verfehlt" zählt.
    "bike": {"min": 0, "max": 1, "label": "Rad", "detail": "optional am Wochenende (Zwift)"},
}

# Feste Tagesbelegung. Läufe haben keinen festen Tag - sie tauchen deshalb im
# Tagesplan als "diese Woche noch offen" auf statt einem erfundenen Wochentag.
WEEK_TEMPLATE = {
    0: [{"type": "strength", "text": "Push/Pull (Home-Gym)"}],
    1: [{"type": "swim", "text": "Schwimmen vor der Arbeit"}],
    2: [{"type": "strength", "text": "Push/Pull (Home-Gym)"}],
    3: [{"type": "strength", "text": "Beine vor der Arbeit"}],
    4: [{"type": "strength", "text": "Push/Pull (Home-Gym)"}],
    5: [{"type": "optional", "text": "Wenn Zeit: Longrun ODER längere Zwift-Ausfahrt"}],
    6: [{"type": "optional", "text": "Wenn Zeit: Longrun ODER längere Zwift-Ausfahrt"}],
}
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

ATHLETE_PROFILE = """Wochenstruktur des Athleten (fester Rahmen, nicht verhandelbar):
- Dienstag + Donnerstag sind Bürotage: dort passen 1x Schwimmen und 1x Beintraining,
  jeweils vor der Arbeit.
- An den übrigen Werktagen Homeoffice mit eigenem Home-Gym: dort laufen die
  Push/Pull-Krafteinheiten (zusammen 3-4x pro Woche).
- Laufen: mindestens 1x lockerer Zone-2-Lauf (gemeinsam mit der Freundin) und
  1x Intervall- oder Schwellenlauf, Wochentag flexibel.
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
- Das Rad ist beim 70.3 der größte Zeitblock. Der Athlet kennt diesen Hinweis bereits
  und hat bewusst entschieden - erwähne ihn nur, wenn er im Wochenreport ausdrücklich
  gefragt ist, nicht in jeder Tagesnotiz."""

SOLL_TEXT = (
    "1x Schwimmen, 2x Laufen (1x Zone 2, 1x Intervall/Schwelle), "
    "4-5x Kraft (1x Beine + 3-4x Push/Pull), Rad optional am Wochenende"
)

# ---------------------------------------------------------------------------
# Periodisierung
# ---------------------------------------------------------------------------

DEFAULT_RACE_DATE = datetime.date(2027, 8, 29)
# Taper: 14 Tage. Belegt ist eine Volumenreduktion um 41-60 % bei gleicher
# Intensität/Frequenz über höchstens 21 Tage, am häufigsten 8-14 Tage (Bosquet
# et al. 2007; Wang et al. 2023, PLOS One, doi:10.1371/journal.pone.0282838).
# Vorher war der ganze August (~4 Wochen) als Taper eingetragen.
TAPER_DAYS = 14

PHASE_ORDER = ["Grundlagenausdauer", "Aufbau 1", "Aufbau 2 (spezifisch)", "Peak", "Taper/Rennwoche"]

PHASE_FOCUS = {
    "Grundlagenausdauer": "aerobe Basis (überwiegend Zone 1-2), Schwimmtechnik, Kraft im bestehenden Split",
    "Aufbau 1": "Schwellentraining, erste Koppeleinheiten, Rad-Grundkraft",
    "Aufbau 2 (spezifisch)": "Wettkampftempo, lange Einheiten (Rad 90-100 km, Lauf 18-20 km), Rennverpflegung üben",
    "Peak": "höchstes Volumen, Formtest (z. B. Olympische Distanz)",
    "Taper/Rennwoche": "Volumen -40 bis -60 %, Intensität und Häufigkeit halten, Rennwoche",
}

# Kurzpläne je Phase und Disziplin - ersetzen die langen Markdown-Tabellen,
# die bisher fest im Dashboard standen (Review-Punkt 25).
PHASE_PLAN = {
    "Grundlagenausdauer": {
        "lauf": "Zone 2 mit der Freundin 45-60 min · 4×8 min Schwelle (2 min Trabpause) oder Fahrtspiel 30-40 min · optional Longrun 60-75 min ruhig",
        "schwimmen": "Technik zuerst: 10 min Drills, Hauptsatz 12-16×50 m an CSS-Pace, 15 s Pause · CSS-Test alle 6-8 Wochen",
        "rad": "Wenn Zeit: 45-60 min Zone 2 auf Zwift, oder Wochenendausfahrt 60-90 min locker",
        "kraft": "bestehender Split (Push A/B, Pull A/B, Beine)",
    },
    "Aufbau 1": {
        "lauf": "Zone 2 wie bisher · 3-4×10 min an Schwellenpace · Longrun bis 90 min, alle 3-4 Wochen mit 15-20 min Tempo",
        "schwimmen": "6-8×100 m an CSS-Pace, 20 s Pause · Sighting üben",
        "rad": "60 min mit 2×15 min Sweet Spot (88-94 % FTP) · FTP-Test zu Phasenbeginn",
        "kraft": "bestehender Split",
    },
    "Aufbau 2 (spezifisch)": {
        "lauf": "Zone 2 wie bisher · 6×3 min knapp über Schwelle im Wechsel mit Schwelle · Longrun 100-110 min inkl. 20 min Renntempo, ideal als Koppellauf",
        "schwimmen": "4×400 m renntemponah · wenn möglich Freiwasser/Neopren",
        "rad": "Rennsimulation 60-90 min bei 70-75 % FTP, danach 20-30 min Koppellauf",
        "kraft": "bestehender Split, Volumen leicht reduzieren",
    },
    "Peak": {
        "lauf": "Formtest 10 km oder Halbmarathon als Tempolauf · höchstes Laufvolumen",
        "schwimmen": "kurz halten: 8×50 m zügig, viel Pause",
        "rad": "längste Ausfahrt 2:30-3:00 h bei Zielwatt",
        "kraft": "Volumen reduzieren, keine neuen Reize",
    },
    "Taper/Rennwoche": {
        "lauf": "kürzer (30-40 min), 2-3×5 min Renntempo, kein Longrun",
        "schwimmen": "8×50 m zügig, viel Pause",
        "rad": "30-40 min mit kurzen Intensitätsspitzen",
        "kraft": "Volumen -40 bis -60 %, letzte Einheit ca. 5 Tage vor dem Rennen",
    },
}

# ---------------------------------------------------------------------------
# Meilensteine bis zum Rennen (Review-Punkt 22) - die Häkchen selbst liegen als
# input_boolean-Helper in Home Assistant (input_boolean.meilenstein_<id>), hier
# steht nur, welche es gibt und bis wann sie sinnvoll erledigt sein sollten.
# ---------------------------------------------------------------------------
MILESTONES = [
    {"id": "css_test", "title": "Erster CSS-Test Schwimmen", "due_phase": "Grundlagenausdauer"},
    {"id": "ftp_test", "title": "FTP-Test auf Zwift", "due_phase": "Aufbau 1"},
    {"id": "erster_koppellauf", "title": "Erster Koppellauf (Rad → Lauf)", "due_phase": "Aufbau 1"},
    {"id": "rad_90km", "title": "Erste 90 km am Stück", "due_phase": "Aufbau 2 (spezifisch)"},
    {"id": "freiwasser_neo", "title": "Freiwasser mit Neopren", "due_phase": "Aufbau 2 (spezifisch)"},
    {"id": "verpflegung_renntempo", "title": "Rennverpflegung im Renntempo getestet", "due_phase": "Aufbau 2 (spezifisch)"},
    {"id": "formtest", "title": "Formtest (z. B. Olympische Distanz)", "due_phase": "Peak"},
]

# Benchmark-Werte der Zielzeit-Schätzung gelten nach dieser Zeit als veraltet
# (Review-Punkt 19). 8 Wochen = übliches Retest-Intervall für CSS/FTP.
BENCHMARK_MAX_AGE_DAYS = 56


def parse_race_date(raw: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat((raw or "").strip())
    except ValueError:
        return DEFAULT_RACE_DATE


def phase_bounds(race_date: datetime.date) -> list:
    """Liefert [(start, end, name)] - die ersten Phasen an Monatsgrenzen wie
    bisher, Peak bis 15 Tage vor dem Rennen, danach 14 Tage Taper."""
    taper_start = race_date - datetime.timedelta(days=TAPER_DAYS - 1)
    return [
        (datetime.date(2026, 9, 1), datetime.date(2026, 12, 31), "Grundlagenausdauer"),
        (datetime.date(2027, 1, 1), datetime.date(2027, 3, 31), "Aufbau 1"),
        (datetime.date(2027, 4, 1), datetime.date(2027, 6, 30), "Aufbau 2 (spezifisch)"),
        (datetime.date(2027, 7, 1), taper_start - datetime.timedelta(days=1), "Peak"),
        (taper_start, race_date, "Taper/Rennwoche"),
    ]


def current_phase(today: datetime.date, race_date: datetime.date) -> str:
    for start, end, name in phase_bounds(race_date):
        if start <= today <= end:
            return name
    if today > race_date:
        return "Taper/Rennwoche"
    return "Grundlagenausdauer"


def _done_counts(weekly_volumes: dict) -> dict:
    wv = weekly_volumes or {}
    return {
        "swim": wv.get("swim_sessions") or 0,
        "run": wv.get("run_sessions") or 0,
        "strength": wv.get("strength_sessions") or 0,
        "bike": wv.get("bike_sessions") or 0,
    }


def build_plan_state(today: datetime.date, race_date: datetime.date, weekly_volumes: dict) -> dict:
    """Berechnet den Planzustand für heute: Phase, heutige Fixpunkte, was diese
    Woche noch offen ist, Soll/Ist. Reine Funktion (kein I/O) - direkt testbar."""
    phase = current_phase(today, race_date)
    bounds = phase_bounds(race_date)
    phase_end = next((e for s, e, n in bounds if n == phase), race_date)
    idx = PHASE_ORDER.index(phase) if phase in PHASE_ORDER else 0
    next_phase = PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None

    done = _done_counts(weekly_volumes)
    targets = []
    open_items = []
    for key in ("swim", "run", "strength", "bike"):
        t = WEEKLY_TARGETS[key]
        d = done[key]
        targets.append({
            "key": key, "label": t["label"], "done": d, "min": t["min"], "max": t["max"],
            "detail": t.get("detail", ""),
            "pct": 100 if t["min"] == 0 else min(100, round(d / t["min"] * 100)),
        })
        if d < t["min"]:
            missing = t["min"] - d
            open_items.append(f"{missing}× {t['label']}" + (f" ({t['detail']})" if t.get("detail") and key == "run" else ""))

    weekday = today.weekday()
    today_fixed = [dict(item) for item in WEEK_TEMPLATE.get(weekday, [])]
    days_left_in_week = 6 - weekday

    return {
        "date": today.isoformat(),
        "weekday": WEEKDAY_NAMES[weekday],
        "phase": phase,
        "phase_focus": PHASE_FOCUS.get(phase, ""),
        "phase_end": phase_end.isoformat(),
        "next_phase": next_phase,
        "race_date": race_date.isoformat(),
        "days_to_race": (race_date - today).days,
        "today_fixed": today_fixed,
        "week_open": open_items,
        "days_left_in_week": days_left_in_week,
        "targets": targets,
        "soll_text": SOLL_TEXT,
        "phase_plan": PHASE_PLAN.get(phase, {}),
        "phases": [
            {"name": n, "start": s.isoformat(), "end": e.isoformat(), "focus": PHASE_FOCUS.get(n, ""),
             "current": n == phase}
            for s, e, n in bounds
        ],
        "milestones": MILESTONES,
        "benchmark_max_age_days": BENCHMARK_MAX_AGE_DAYS,
    }


def phase_detail_text(phase: str) -> str:
    """Kompakter Plantext für KI-Prompts - aus denselben Daten wie das Dashboard."""
    p = PHASE_PLAN.get(phase) or {}
    if not p:
        return ""
    return (
        f"Lauf: {p['lauf']}. Schwimmen: {p['schwimmen']}. "
        f"Rad (Zwift): {p['rad']}. Kraft: {p['kraft']}."
    )
