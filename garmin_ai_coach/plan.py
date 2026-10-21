"""Einzige Quelle der Wahrheit für den Trainingsplan (seit v0.18.0, Saisonplan mit Marathon seit v0.19.0).

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
# Testwerte (Stand 14.10.2026) - nach jedem Test HIER und im gleichnamigen
# Dashboard-Feld aktualisieren. Alle Watt-/Pace-Angaben in PHASE_PLAN und in
# den KI-Prompts rechnen sich daraus.
# ---------------------------------------------------------------------------
FTP_ZWIFT_W = 178        # Zwift FTP Ramp Test Lite, 09.10.2026 (Garmin-Schätzung gilt nicht)
CSS_S_PER_100M = 130     # CSS 2:10 /100 m
LT_PACE_S_PER_KM = 295   # Lauf-Schwellenpace 4:55 /km (echte 3×2-km-Einheiten; Garmin-Schätzung 4:31 zu optimistisch) - 30-min-Test KW 42 + Dez.
MARATHON_PACE_S_PER_KM = 325  # vorläufige Marathon-Zielpace 5:25 /km (~3:49 h), prüfen nach HM-Test 14.03.2027


def _w(pct: float) -> int:
    """Watt bei pct % der Zwift-FTP."""
    return round(FTP_ZWIFT_W * pct / 100)


def _mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _swim(offset_s: int = 0) -> str:
    return _mmss(CSS_S_PER_100M + offset_s)


def _run(offset_s: int = 0) -> str:
    return _mmss(LT_PACE_S_PER_KM + offset_s)


TEST_VALUES_TEXT = (
    f"Testwerte: FTP {FTP_ZWIFT_W} W (Zwift), CSS {_swim()} /100 m, Lauf-Schwellenpace {_run()} /km, "
    f"lockere Läufe {_run(65)}–{_run(100)} /km bzw. HF Zone 2, Marathon-Zielpace {_mmss(MARATHON_PACE_S_PER_KM)} /km, "
    f"Renn-Zielwatt Almere {_w(75)}–{_w(78)} W"
)

# ---------------------------------------------------------------------------
# Wochenrahmen (von Alex am 14.10.2026 aktualisiert, siehe status-und-plan.md)
# ---------------------------------------------------------------------------

# Soll je Kalenderwoche und Phase - bewusst Alex' reale Struktur, damit
# Fortschrittsbalken, Wochenreport und KI-Prompts dieselbe Messlatte benutzen.
_STRENGTH = {"min": 4, "max": 4, "label": "Kraft", "detail": "1x Beine + 3x Home-Gym (Push, Pull, Push+Pull)"}
_SWIM = {"min": 1, "max": 1, "label": "Schwimmen"}
WEEKLY_TARGETS_BY_PHASE = {
    "Grundlage": {
        "swim": _SWIM,
        "run": {"min": 2, "max": 2, "label": "Laufen", "detail": "1x Zone 2, 1x Schwelle/Intervall im Wechsel"},
        "strength": _STRENGTH,
        "bike": {"min": 1, "max": 2, "label": "Rad", "detail": "1x Zwift-Intervall, optional 1x locker"},
    },
    "Marathon-Aufbau": {
        "swim": _SWIM,
        "run": {"min": 3, "max": 3, "label": "Laufen", "detail": "Qualität, locker, Longrun"},
        "strength": _STRENGTH,
        "bike": {"min": 1, "max": 1, "label": "Rad", "detail": "1x Zwift"},
    },
    "Marathon-Taper": {
        "swim": _SWIM,
        "run": {"min": 3, "max": 3, "label": "Laufen", "detail": "kürzer, Tempo halten"},
        "strength": {"min": 2, "max": 4, "label": "Kraft", "detail": "Beine nur bis 10 Tage vor dem Rennen"},
        "bike": {"min": 0, "max": 1, "label": "Rad", "detail": "kurz und locker"},
    },
    "Regeneration": {
        "swim": {"min": 0, "max": 1, "label": "Schwimmen"},
        "run": {"min": 0, "max": 2, "label": "Laufen", "detail": "nur sehr locker"},
        "strength": {"min": 0, "max": 3, "label": "Kraft", "detail": "leicht"},
        "bike": {"min": 0, "max": 2, "label": "Rad", "detail": "locker"},
    },
    "Almere-Aufbau": {
        "swim": _SWIM,
        "run": {"min": 2, "max": 2, "label": "Laufen", "detail": "1x Qualität, 1x Zone 2 (+ Koppellauf)"},
        "strength": _STRENGTH,
        "bike": {"min": 2, "max": 2, "label": "Rad", "detail": "Zwift-Intervall + lange Ausfahrt"},
    },
    "Almere-Peak": {
        "swim": _SWIM,
        "run": {"min": 2, "max": 2, "label": "Laufen", "detail": "1x Qualität, 1x Zone 2 (+ Koppellauf)"},
        "strength": {"min": 2, "max": 4, "label": "Kraft", "detail": "Erhalt, 1-2 Sätze pro Übung"},
        "bike": {"min": 2, "max": 2, "label": "Rad", "detail": "Renntempo + Rennsimulation"},
    },
    "Almere-Taper": {
        "swim": _SWIM,
        "run": {"min": 2, "max": 2, "label": "Laufen", "detail": "kurz mit Renntempo"},
        "strength": {"min": 0, "max": 2, "label": "Kraft", "detail": "letzte Einheit ca. 5 Tage vor dem Rennen"},
        "bike": {"min": 1, "max": 2, "label": "Rad", "detail": "kurz mit Renntempo"},
    },
}
WEEKLY_TARGETS = WEEKLY_TARGETS_BY_PHASE["Grundlage"]

# Feste Tagesbelegung je Phase (Musterwoche, von Alex am 14.10.2026 präzisiert):
# Mo Push · Di/Do Schwimmen und Beine (Reihenfolge flexibel) · Mi Pull · Fr Push+Pull ·
# Wochenende Zwift · Z2-Lauf und Qualitätslauf frei unter der Woche (ohne festen Tag,
# erscheinen deshalb über week_open statt hier).
_GYM = {
    0: [{"type": "strength", "text": "Push (Home-Gym)"}],
    1: [{"type": "swim_or_legs", "text": "Schwimmen oder Beine vor der Arbeit (das andere am Donnerstag)"}],
    2: [{"type": "strength", "text": "Pull (Home-Gym)"}],
    3: [{"type": "swim_or_legs", "text": "Schwimmen oder Beine vor der Arbeit (was am Dienstag nicht dran war)"}],
    4: [{"type": "strength", "text": "Push + Pull kombiniert (Home-Gym)"}],
}
WEEK_TEMPLATE_BY_PHASE = {
    "Grundlage": {**_GYM,
        5: [{"type": "bike", "text": "Zwift-Einheit (Sa oder So)"}],
        6: [{"type": "bike", "text": "Zwift-Einheit, falls Samstag nicht geklappt hat"}]},
    "Marathon-Aufbau": {**_GYM,
        5: [{"type": "bike", "text": "Zwift oder Longrun (auf Sa/So verteilen)"}],
        6: [{"type": "run", "text": "Longrun oder Zwift (was Samstag nicht dran war)"}]},
    "Almere-Aufbau": {**_GYM,
        5: [{"type": "bike", "text": "Lange Radeinheit + Koppellauf (Sa oder So)"}],
        6: [{"type": "bike", "text": "Lange Radeinheit, falls Samstag nicht geklappt hat"}]},
}
WEEK_TEMPLATE_BY_PHASE["Marathon-Taper"] = WEEK_TEMPLATE_BY_PHASE["Marathon-Aufbau"]
WEEK_TEMPLATE_BY_PHASE["Almere-Peak"] = WEEK_TEMPLATE_BY_PHASE["Almere-Aufbau"]
WEEK_TEMPLATE_BY_PHASE["Almere-Taper"] = WEEK_TEMPLATE_BY_PHASE["Almere-Aufbau"]
WEEK_TEMPLATE_BY_PHASE["Regeneration"] = {d: [{"type": "optional", "text": "Regeneration: nur locker, nach Gefühl"}] for d in range(7)}
WEEK_TEMPLATE = WEEK_TEMPLATE_BY_PHASE["Grundlage"]
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

ATHLETE_PROFILE = f"""Ziele: erster Marathon am 02.05.2027 (Zwischenziel), Hauptziel Challenge Almere-Amsterdam, Mitteldistanz (1,9 km Schwimmen, 90 km Rad, 21,1 km Laufen) am Sa 11.09.2027.

Wochenstruktur des Athleten (fester Rahmen, nicht verhandelbar, Stand 14.10.2026):
- Montag Push, Mittwoch Pull, Freitag Push und Pull kombiniert (Home-Gym, Homeoffice-Tage).
- Dienstag und Donnerstag (Bürotage, jeweils vor der Arbeit): 1x Schwimmen und 1x Beine,
  welche Einheit an welchem der beiden Tage liegt, wechselt von Woche zu Woche.
- Wochenende: Zwift-Einheit (Sa oder So).
- Unter der Woche zusätzlich ohne festen Tag: 1x lockerer Zone-2-Lauf (gemeinsam mit der
  Partnerin) und 1x Qualitätslauf, wöchentlich im Wechsel: Schwellenlauf oder 4x4-min-Intervall
  (4x4 min bei 90-95 % HFmax, 3 min Trab). Andere Intervallformen (z. B. 1000er) macht der
  Athlet bewusst nicht - nie vorschlagen. Wettkampfspezifische Läufe (Marathontempo,
  Renntempo Almere, Taper-Tempo) sind im Plan mit 🏁 markiert; der Athlet nimmt sie einzeln an
  oder lehnt sie ab (dann gilt Schwelle/4x4 bzw. locker) - abgelehnte nicht wieder vorschlagen.
- Hauptrennen Challenge Almere: Strecke flach und windanfällig (Aeroposition, gleichmäßige Watt),
  Schwimmen im See mit Neoprenanzug.
- Marathonblock (04.01.-11.04.2027): am Wochenende zusätzlich ein Longrun (bis 32 km),
  Zwift und Longrun auf Sa/So verteilt.
- Almere-Block (ab 17.05.2027): am Wochenende lange Radeinheit mit Koppellauf, Zwift-Intervall
  zusätzlich unter der Woche.
- Der Athlet will bewusst nicht mehr Zeit investieren. Diese Struktur ist der Idealfall
  und lässt sich in der Realität oft nicht vollständig umsetzen - fehlende Einheiten
  sind normal und kein Anlass für Vorwürfe.
- {TEST_VALUES_TEXT}.

Coaching-Regeln daraus:
- Niemals mehr Gesamtzeit oder zusätzliche Einheiten fordern. Wenn etwas fehlt, sage
  was innerhalb des bestehenden Rahmens umgeschichtet werden sollte (Prioritäten setzen):
  im Marathonblock Longrun vor Qualitätslauf vor Zwift, im Almere-Block lange Radeinheit vor
  Zwift-Intervall vor Qualitätslauf; Home-Gym hat in beiden Blöcken die niedrigste Priorität.
- Berücksichtige den Wochentag: Schwimmen und Beine an den Bürotagen (Di/Do, Reihenfolge
  flexibel), Push/Pull an Homeoffice-Tagen, Zwift und lange Einheiten am Wochenende.
- Qualitätslauf möglichst nicht am Tag nach dem Beintraining legen.
- Beine im Marathonblock schwer und kurz, mindestens 48 h Abstand zu Longrun und Qualitätslauf."""

SOLL_TEXT_BY_PHASE = {
    "Grundlage": "1x Schwimmen, 2x Laufen (1x Zone 2, 1x Schwelle/Intervall im Wechsel), 4x Kraft (1x Beine + 3x Home-Gym), 1-2x Zwift",
    "Marathon-Aufbau": "1x Schwimmen, 3x Laufen (Qualität, locker, Longrun), 4x Kraft (1x Beine + 3x Home-Gym), 1x Zwift",
    "Marathon-Taper": "1x Schwimmen, 3x Laufen kürzer bei gleichem Tempo, Kraft reduziert, Zwift kurz",
    "Regeneration": "nur lockere Bewegung, kein Lauftempo",
    "Almere-Aufbau": "1x Schwimmen, 2x Laufen (+ Koppellauf), 4x Kraft (1x Beine + 3x Home-Gym), 2x Rad (Zwift-Intervall + lange Ausfahrt)",
    "Almere-Peak": "1x Schwimmen (Freiwasser), 2x Laufen (+ Koppellauf), Kraft auf Erhalt, 2x Rad inkl. Rennsimulation",
    "Almere-Taper": "Umfang -40 bis -60 %, Intensität kurz halten",
}
SOLL_TEXT = SOLL_TEXT_BY_PHASE["Grundlage"]


def soll_text(phase: str) -> str:
    return SOLL_TEXT_BY_PHASE.get(phase, SOLL_TEXT)


# ---------------------------------------------------------------------------
# Periodisierung (Saisonplan 2026/27, siehe Dashboard custom_templates/coach_plan.jinja)
# ---------------------------------------------------------------------------

DEFAULT_RACE_DATE = datetime.date(2027, 9, 11)
# Hauptrennen (Alex 21.10.2026: nicht Ironman 70.3 Duisburg, sondern Challenge Almere-Amsterdam,
# Mitteldistanz, Sa 11.09.2027 - flach, windanfällig, Schwimmen im See mit Neo)
RACE_NAME = "Challenge Almere"
RACE_NAME_LONG = "Challenge Almere-Amsterdam, Mitteldistanz (1,9 km / 90 km / 21,1 km)"
MARATHON_DATE = datetime.date(2027, 5, 2)
GRUNDLAGE_START = datetime.date(2026, 9, 1)
MARATHON_BLOCK_START = datetime.date(2027, 1, 4)
# Taper Almere: 14 Tage. Belegt ist eine Volumenreduktion um 41-60 % bei gleicher
# Intensität/Frequenz über höchstens 21 Tage, am häufigsten 8-14 Tage (Bosquet
# et al. 2007; Wang et al. 2023, PLOS One, doi:10.1371/journal.pone.0282838).
TAPER_DAYS = 14
MARATHON_TAPER_DAYS = 21   # 3 Wochen, übliche Marathon-Praxis
REGENERATION_DAYS = 14     # 2 Wochen ohne Lauftempo nach dem Marathon
PEAK_DAYS = 21

PHASE_ORDER = ["Grundlage", "Marathon-Aufbau", "Marathon-Taper", "Regeneration", "Almere-Aufbau", "Almere-Peak", "Almere-Taper"]

PHASE_FOCUS = {
    "Grundlage": "aerobe Basis, Sweet-Spot-Progression auf Zwift, CSS-Schwimmen, Z2-Lauf bis 90 min verlängern",
    "Marathon-Aufbau": "Longrun von 16 auf 32 km, Schwelle und Marathontempo im Wechsel, Rad und Schwimmen halten",
    "Marathon-Taper": "Umfang -25/-40/-60 %, Tempo halten, Rennverpflegung festlegen",
    "Regeneration": "2 Wochen ohne Lauftempo, lockere Bewegung, Erholung vom Marathon",
    "Almere-Aufbau": "Rad wird Priorität (Almere: flach und windig - Aeroposition, gleichmäßige Watt): lange Ausfahrten mit Renntempo und Koppellauf, Freiwasser",
    "Almere-Peak": "Rennsimulation 90 km, Formtest, höchste spezifische Belastung",
    "Almere-Taper": "Volumen -40 bis -60 %, Intensität und Häufigkeit halten, Rennwoche",
}

# Kurzpläne je Phase und Disziplin (die Woche-für-Woche-Details stehen im Dashboard).
PHASE_PLAN = {
    "Grundlage": {
        "lauf": f"Z2-Lauf mit Partnerin 50 → 90 min (HF Zone 2) · Qualitätslauf im Wechsel: Schwelle (z. B. 3×2 km @ {_run()} /km) und 4×4-min-Intervall (90–95 % HFmax, Richtwert {_run(-23)}–{_run(-18)} /km, 3 min Trab) · 30-min-Lauftest Mitte Dezember",
        "schwimmen": f"CSS-Serien im 4-Wochen-Wechsel: 100er @ {_swim()}, 200er–400er @ {_swim(1)}–{_swim(4)}, Technik + Ausdauer, Tempo-50er @ {_swim(-4)}–{_swim(-2)} /100 m · CSS-Test 30.11.",
        "rad": f"1x Zwift: Sweet Spot 3×10 → 2×20 min @ {_w(88)}–{_w(94)} W, dann Schwelle {_w(98)} W und Over-Under · FTP-Test 07.12. · optional 1x Z2 {_w(65)}–{_w(70)} W",
        "kraft": "Mo Push · Mi Pull · Fr Push+Pull · Beine Di oder Do",
    },
    "Marathon-Aufbau": {
        "lauf": f"So Longrun 16 → 32 km ({_run(65)}–{_run(100)} /km, Spitze 11.04.) · unter der Woche Schwelle @ {_run()} oder Marathontempo @ {_mmss(MARATHON_PACE_S_PER_KM)} /km im Wechsel + locker mit Partnerin · Halbmarathon-Test 14.03.",
        "schwimmen": f"1x CSS-Serie wie bisher (@ {_swim()} /100 m), Wiederholungen steigern, Pausen kürzen",
        "rad": f"1x Zwift am Wochenende zum Erhalt: Sweet Spot @ {_w(90)}–{_w(94)} W, in Entlastungswochen Z2 · FTP-Tests 01.02. und 29.03.",
        "kraft": "Home-Gym wie gewohnt · Beine schwer und kurz (2-3 Sätze à 4-6 Wdh.), 48 h Abstand zu Longrun/Qualität",
    },
    "Marathon-Taper": {
        "lauf": f"Longrun 24 → 16 km, Marathontempo kurz @ {_mmss(MARATHON_PACE_S_PER_KM)} /km · Rennen So 02.05., 60-90 g KH/h",
        "schwimmen": "kurz und locker, ein paar zügige 50er",
        "rad": f"Zwift kurz mit Aktivierung (3×3 min @ {_w(80)} W)",
        "kraft": "Volumen reduzieren, letzte schwere Beine-Einheit ca. 10 Tage vor dem Rennen",
    },
    "Regeneration": {
        "lauf": "ab Tag 5 sehr locker 20-30 min, Woche 2: 2× 30-40 min locker",
        "schwimmen": "locker, Technik",
        "rad": f"Zwift locker Z2 ({_w(65)}–{_w(70)} W)",
        "kraft": "Oberkörper leicht, Beine erst in Woche 2 leicht",
    },
    "Almere-Aufbau": {
        "lauf": f"Qualitätslauf im Wechsel Schwelle @ {_run()} /km und Renn-Laufpace · So Z2 mit Partnerin · Koppellauf nach jeder langen Radeinheit",
        "schwimmen": f"CSS-Serien und Renn-Simulation 1200 → 1900 m @ {_swim(1)}–{_swim(3)} /100 m (1,9 km ≈ CSS bis +3 s), Sighting, ab Juni Freiwasser mit Neo",
        "rad": f"Zwift-Intervall unter der Woche (Sweet Spot, Renntempo 2×30 / 3×20 min @ {_w(77)}–{_w(78)} W) · Wochenende lange Ausfahrt 2:00 → 3:00 h mit Renntempo-Blöcken + Koppellauf",
        "kraft": "Home-Gym wie gewohnt, Beine 1x",
    },
    "Almere-Peak": {
        "lauf": "Renn-Laufpace 2×5 km / 3×3 km, Koppelläufe 20-30 min",
        "schwimmen": "Freiwasser 1500-2000 m am Stück mit Neo",
        "rad": f"Rennsimulation 90 km @ {_w(75)}–{_w(78)} W + 30 min Koppellauf · Formtest (z. B. Olympische Distanz)",
        "kraft": "Erhalt: 1-2 Sätze pro Übung, keine neuen Reize",
    },
    "Almere-Taper": {
        "lauf": "kürzer (30-40 min) mit kurzen Renntempo-Abschnitten, kein Longrun",
        "schwimmen": "8×50 m zügig, viel Pause",
        "rad": f"Aktivierung 35 min (3×3 min @ {_w(80)} W) · Rennen: {_w(75)}–{_w(78)} W",
        "kraft": "Volumen -40 bis -60 %, letzte Einheit ca. 5 Tage vor dem Rennen",
    },
}

# ---------------------------------------------------------------------------
# Meilensteine (Review-Punkt 22) - die Häkchen selbst liegen als input_boolean-
# Helper in Home Assistant (input_boolean.meilenstein_<id>).
# ---------------------------------------------------------------------------
MILESTONES = [
    {"id": "css_test", "title": "Erster CSS-Test Schwimmen", "due_phase": "Grundlage"},
    {"id": "ftp_test", "title": "FTP-Test auf Zwift", "due_phase": "Grundlage"},
    {"id": "lauftest_30_min", "title": "30-min-Lauftest (Schwellenpace)", "due_phase": "Grundlage"},
    {"id": "longrun_25_km", "title": "Erster Longrun 25 km", "due_phase": "Marathon-Aufbau"},
    {"id": "halbmarathon_test", "title": "Halbmarathon-Test", "due_phase": "Marathon-Aufbau"},
    {"id": "longrun_30_km", "title": "Erster Longrun 30 km", "due_phase": "Marathon-Aufbau"},
    {"id": "marathon_verpflegung_getestet", "title": "Marathon-Verpflegung im Longrun getestet", "due_phase": "Marathon-Aufbau"},
    {"id": "marathon_finish", "title": "Marathon gefinisht", "due_phase": "Marathon-Taper"},
    {"id": "erster_koppellauf", "title": "Erster Koppellauf (Rad → Lauf)", "due_phase": "Almere-Aufbau"},
    {"id": "rad_90km", "title": "Erste 90 km am Stück", "due_phase": "Almere-Aufbau"},
    {"id": "freiwasser_neo", "title": "Freiwasser mit Neopren", "due_phase": "Almere-Aufbau"},
    {"id": "verpflegung_renntempo", "title": "Rennverpflegung im Renntempo getestet", "due_phase": "Almere-Aufbau"},
    {"id": "formtest", "title": "Formtest (z. B. Olympische Distanz)", "due_phase": "Almere-Peak"},
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
    """Liefert [(start, end, name)] für die Saison 2026/27 mit Marathon als
    Zwischenziel. Marathon-Taper 3 Wochen, danach 2 Wochen Regeneration;
    Almere-Peak 3 Wochen, Almere-Taper 14 Tage."""
    d = datetime.timedelta
    m_taper = MARATHON_DATE - d(days=MARATHON_TAPER_DAYS - 1)
    regen_end = MARATHON_DATE + d(days=REGENERATION_DAYS)
    # Taper beginnt am Montag der vorletzten Rennwoche (Wochenplan im Dashboard ist
    # montagsbasiert; Rennen Sa 11.09. -> Taper ab Mo 30.08., 13 Tage).
    race_monday = race_date - d(days=race_date.weekday())
    taper_start = race_monday - d(days=TAPER_DAYS - 7)
    peak_start = taper_start - d(days=PEAK_DAYS)
    return [
        (GRUNDLAGE_START, MARATHON_BLOCK_START - d(days=1), "Grundlage"),
        (MARATHON_BLOCK_START, m_taper - d(days=1), "Marathon-Aufbau"),
        (m_taper, MARATHON_DATE, "Marathon-Taper"),
        (MARATHON_DATE + d(days=1), regen_end, "Regeneration"),
        (regen_end + d(days=1), peak_start - d(days=1), "Almere-Aufbau"),
        (peak_start, taper_start - d(days=1), "Almere-Peak"),
        (taper_start, race_date, "Almere-Taper"),
    ]


def current_phase(today: datetime.date, race_date: datetime.date) -> str:
    for start, end, name in phase_bounds(race_date):
        if start <= today <= end:
            return name
    if today > race_date:
        return "Almere-Taper"
    return "Grundlage"


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

    targets_cfg = WEEKLY_TARGETS_BY_PHASE.get(phase, WEEKLY_TARGETS)
    done = _done_counts(weekly_volumes)
    targets = []
    open_items = []
    for key in ("swim", "run", "strength", "bike"):
        t = targets_cfg[key]
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
    today_fixed = [dict(item) for item in WEEK_TEMPLATE_BY_PHASE.get(phase, WEEK_TEMPLATE).get(weekday, [])]
    days_left_in_week = 6 - weekday
    # Rad am Wochenende: Ist das Wochen-Soll schon erreicht (z. B. Zwift am Samstag), ist die Einheit von heute
    # ("falls Samstag nicht geklappt hat") hinfällig. Ohne diesen Zusatz verordnete die KI-Notiz sie am
    # Sonntag noch einmal (18.10.2026).
    bike_min = max(targets_cfg["bike"]["min"], 1)
    for item in today_fixed:
        if item.get("type") == "bike" and weekday >= 5 and done["bike"] >= bike_min:
            item["done"] = True
            item["text"] += " - diese Woche schon erledigt"

    return {
        "date": today.isoformat(),
        "weekday": WEEKDAY_NAMES[weekday],
        "phase": phase,
        "phase_focus": PHASE_FOCUS.get(phase, ""),
        "phase_end": phase_end.isoformat(),
        "next_phase": next_phase,
        "race_date": race_date.isoformat(),
        "race_name": RACE_NAME,
        "days_to_race": (race_date - today).days,
        "marathon_date": MARATHON_DATE.isoformat(),
        "days_to_marathon": (MARATHON_DATE - today).days,
        "today_fixed": today_fixed,
        "week_open": open_items,
        "days_left_in_week": days_left_in_week,
        "targets": targets,
        "soll_text": soll_text(phase),
        "phase_plan": PHASE_PLAN.get(phase, {}),
        "phases": [
            {"name": n, "start": s.isoformat(), "end": e.isoformat(), "focus": PHASE_FOCUS.get(n, ""),
             "current": n == phase}
            for s, e, n in bounds
        ],
        "milestones": MILESTONES,
        "benchmark_max_age_days": BENCHMARK_MAX_AGE_DAYS,
        "test_values": TEST_VALUES_TEXT,
    }


def phase_detail_text(phase: str) -> str:
    """Kompakter Plantext für KI-Prompts - aus denselben Daten wie das Dashboard."""
    p = PHASE_PLAN.get(phase) or {}
    if not p:
        return ""
    return (
        f"Lauf: {p['lauf'].rstrip('.')}. Schwimmen: {p['schwimmen'].rstrip('.')}. "
        f"Rad (Zwift): {p['rad'].rstrip('.')}. Kraft: {p['kraft'].rstrip('.')}."
    )
