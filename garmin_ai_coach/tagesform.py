"""Leistung im Verhältnis zur Tagesform (seit v0.24.0).

Konzept, Begründung und Quellen: claude/konzept-tagesform-leistung.md.

Drei getrennte Achsen statt eines Gesamtscores (gleiche Lehre wie bei ACWR,
siehe wissenschaftliche-quellen-trainingsgrundlagen.md, Abschnitt 6):

1. Tagesform am Trainingstag, gegen die persönliche Baseline:
   - HRV: 7-Tage-Mittel von ln(HRV) gegen den 60-Tage-Korridor ±0,5 SD
     ("smallest worthwhile change", Plews et al. 2012/2013; Buchheit 2014).
   - Ruhepuls und Schlaf-Score des Tages: Abweichung > 1 SD von der Baseline.
     Für Einzeltage ist das bewusst strenger als bei der HRV, weil
     Einzelwerte stärker schwanken als 7-Tage-Mittel.
   - Garmin Training Readiness geht NICHT ein, weil sie die Trainingslast
     selbst enthält (siehe recommendation.py).
2. Leistung relativ zur Erwartung: Vergleich nur mit den eigenen letzten
   Einheiten derselben Art (Sport + hart/locker). Laufen: Tempo, Rad:
   (Normalized) Power, Schwimmen: Tempo, Gym: e1RM der Top-Sätze je Übung.
   Zusätzlich der Efficiency Factor (Leistung bzw. Tempo pro Herzschlag) als
   Fitness-Signal (Lacome et al. 2018; Nuuttila et al. 2024).
3. Anstrengung: RPE und "Gefühl" aus der Garmin-Selbstbewertung.
   Liegen nur in get_activity(id).summaryDTO, nicht in der
   Aktivitätenliste: directWorkoutRpe (RPE x 10) und directWorkoutFeel
   (0/25/50/75/100). Belegt durch zwei unabhängige Open-Source-Clients
   (xichen-de/garmin-owl PR #4, pabloruizve/garmin-coach-mcp PR #3), nicht
   durch eine echte Antwort aus diesem Konto. Deshalb defensiv: fehlt das
   Feld, heißt es "keine RPE" statt einer erfundenen Zahl.

Bewertet wird "ausgereizt oder nicht" nur bei harten Einheiten. Bei lockeren
Einheiten ist Zurückhaltung gewollt (polarisiertes Training); dort wird nur
geprüft, ob die Einheit wirklich locker blieb.
"""

import datetime
import json
import math
import os
import statistics

import decoupling
import progress

DATA_DIR = "/data"
CACHE_FILE = os.path.join(DATA_DIR, "session_eval.json")
CACHE_SCHEMA = 1
CACHE_KEEP_DAYS = 180

BASELINE_DAYS = 60
MIN_BASELINE_DAYS = 14        # darunter keine Tagesform-Einordnung
HRV_SWC_SD = 0.5              # Plews/Buchheit: SWC = 0,5 x SD
DAY_MARKER_SD = 1.0           # Ruhepuls/Schlaf (Einzeltag)

COMPARE_N = 8                 # Vergleich mit den letzten n Einheiten gleicher Art
MIN_COMPARE = 4               # darunter: "zu wenig Vergleichsdaten"
PERF_BAND_SD = 0.5            # Leistung "wie erwartet" innerhalb ±0,5 SD ...
PERF_BAND_MIN_PCT = 1.5       # ... mindestens aber ±1,5 %

EVAL_DAYS = 28                # so weit zurück im Dashboard
RPE_FETCH_DAYS = 14           # so weit zurück RPE nachladen
RPE_REFRESH_DAYS = 2          # jüngere Einheiten ohne RPE erneut abfragen
RPE_MAX_FETCH = 8             # Garmin-Abrufe je Sync (Rate-Limit-Schutz)
LOW_RPE = 6                   # RPE <= 6 bei harter Einheit = Reserve vorhanden
MIN_DURATION_MIN = 15

HARD_HIGH_ZONE_SHARE = 0.15   # >= 15 % Zeit in Zone 4-5 zählt als harte Einheit
HARD_NAME_KEYWORDS = ("intervall", "interval", "schwelle", "threshold", "tempo",
                      "vo2", "sprint", "test", "css", "ftp", "rennen", "race")
EASY_MAX_HIGH_ZONE_SHARE = decoupling.MAX_HIGH_ZONE_SHARE  # 10 %

FEEL_DE = {0: "sehr schwach", 25: "schwach", 50: "normal", 75: "stark", 100: "sehr stark"}
FORM_DE = {"unter": "unter Baseline", "normal": "normal", "ueber": "über Baseline"}
PERF_DE = {"unter": "unter Erwartung", "erwartet": "wie erwartet", "ueber": "über Erwartung"}
SPORT_DE = {"run": "Lauf", "ride": "Rad", "swim": "Schwimmen", "strength": "Gym"}


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _parse_dt(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _mean_sd(values):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None, None
    return statistics.mean(vals), statistics.stdev(vals)


def _load_cache() -> dict:
    try:
        with open(CACHE_FILE) as f:
            raw = json.load(f) or {}
        if raw.get("_schema") == CACHE_SCHEMA:
            return raw.get("data") or {}
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[tagesform] Cache nicht lesbar, starte neu: {e}")
    return {}


def _save_cache(cache: dict) -> dict:
    cutoff = (datetime.date.today() - datetime.timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    cache = {k: v for k, v in cache.items() if (v.get("date") or "") >= cutoff}
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"_schema": CACHE_SCHEMA, "data": cache}, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[tagesform] Cache konnte nicht geschrieben werden: {e}")
    return cache


# ---------------------------------------------------------------------------
# Achse 1: Tagesform
# ---------------------------------------------------------------------------

def day_form(day: str, history: list) -> dict:
    """Tagesform am Tag `day` (ISO) aus history.json-Einträgen.

    Gibt {"level": "unter"|"normal"|"ueber"|None, "reasons": [...],
    "markers": {...}} zurück; level None heißt: zu wenig Baseline."""
    by_date = {h.get("date"): h for h in history or [] if h.get("date")}
    try:
        d = datetime.date.fromisoformat(day)
    except (TypeError, ValueError):
        return {"level": None, "reasons": ["kein Datum"], "markers": {}}
    start = (d - datetime.timedelta(days=BASELINE_DAYS)).isoformat()
    base = [h for k, h in by_date.items() if start <= k < day]
    today = by_date.get(day) or {}

    def ln(v):
        v = _num(v)
        return math.log(v) if v and v > 0 else None

    markers, reasons = {}, []
    base_hrv = [ln(h.get("hrv_avg")) for h in base]
    base_hrv = [v for v in base_hrv if v is not None]
    if len(base_hrv) >= MIN_BASELINE_DAYS:
        week = [ln((by_date.get((d - datetime.timedelta(days=i)).isoformat()) or {}).get("hrv_avg"))
                for i in range(7)]
        week = [v for v in week if v is not None]
        mean, sd = _mean_sd(base_hrv)
        if len(week) >= 3 and sd:
            z = (statistics.mean(week) - mean) / sd
            markers["hrv_7d_z"] = round(z, 2)
            if z < -HRV_SWC_SD:
                markers["hrv"] = -1
                reasons.append("HRV-7-Tage-Schnitt unter deinem Normalbereich")
            elif z > HRV_SWC_SD:
                markers["hrv"] = 1
                reasons.append("HRV-7-Tage-Schnitt über deinem Normalbereich")
            else:
                markers["hrv"] = 0

    for key, label, invert in (("resting_hr", "Ruhepuls", True), ("sleep_score", "Schlaf-Score", False)):
        vals = [_num(h.get(key)) for h in base]
        vals = [v for v in vals if v is not None]
        cur = _num(today.get(key))
        if len(vals) < MIN_BASELINE_DAYS or cur is None:
            continue
        mean, sd = _mean_sd(vals)
        if not sd:
            continue
        z = (cur - mean) / sd
        markers[f"{key}_z"] = round(z, 2)
        good = -z if invert else z
        if good < -DAY_MARKER_SD:
            markers[key] = -1
            reasons.append(f"{label} {'erhöht' if invert else 'niedrig'} ({round(cur)} vs. Ø {round(mean)})")
        elif good > DAY_MARKER_SD:
            markers[key] = 1
            reasons.append(f"{label} {'niedrig' if invert else 'hoch'} ({round(cur)} vs. Ø {round(mean)})")
        else:
            markers[key] = 0

    scores = [v for k, v in markers.items() if k in ("hrv", "resting_hr", "sleep_score")]
    if not scores:
        return {"level": None, "reasons": ["noch zu wenig Baseline (mind. 14 Tage)"], "markers": markers}
    total = sum(scores)
    if total <= -1:
        level = "unter"
    elif total >= 1 and -1 not in scores:
        level = "ueber"
    else:
        level = "normal"
    if not reasons:
        reasons.append("alle Werte im Normalbereich")
    return {"level": level, "reasons": reasons, "markers": markers}


# ---------------------------------------------------------------------------
# Einheiten erfassen (Aktivitätenliste + RPE aus get_activity)
# ---------------------------------------------------------------------------

def _sport(act: dict):
    t = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
    if "swim" in t:
        return "swim"
    if "run" in t:
        return "run"
    if "bik" in t or "cycl" in t or "ride" in t:
        return "ride"
    if "strength" in t or "weight" in t or "gym" in t:
        return "strength"
    return None


def _is_hard(act: dict, sport: str) -> bool:
    if sport == "strength":
        return True
    name = (act.get("activityName") or "").lower()
    if any(kw in name for kw in HARD_NAME_KEYWORDS):
        return True
    if sport == "swim":
        return False  # Handgelenk-HF im Wasser ist zu unzuverlässig für Zonen
    share = decoupling.high_zone_share(act)
    return share is not None and share >= HARD_HIGH_ZONE_SHARE


def _extract(act: dict, sport: str) -> dict:
    hr = _num(act.get("averageHR"))
    speed = _num(act.get("averageSpeed"))
    out = {"output": None, "output_unit": None, "ef": None}
    if sport in ("run", "swim") and speed and speed > 0:
        out["output"] = round(speed, 4)
        out["output_unit"] = "m/s"
        if sport == "run" and hr:
            out["ef"] = round(speed * 60 / hr, 4)  # m/min pro Schlag
    elif sport == "ride":
        power = _num(act.get("normPower")) or _num(act.get("avgPower")) or _num(act.get("averagePower"))
        if power:
            out["output"] = round(power, 1)
            out["output_unit"] = "W"
            if hr:
                out["ef"] = round(power / hr, 4)
    return out


def _companion_ride(act: dict, activities: list):
    """Zwift-Fahrt: Alex zeichnet parallel auf der Uhr auf (0 km, siehe
    app._volumes_in_window). HF und Selbstbewertung stehen dann oft nur
    dort. Partner = 0-km-Radaktivität, deren Start < 30 min abweicht."""
    start = _parse_dt(act.get("startTimeLocal"))
    if not start:
        return None
    for other in activities or []:
        if other is act or _sport(other) != "ride" or (other.get("distance") or 0) > 0:
            continue
        o_start = _parse_dt(other.get("startTimeLocal"))
        if o_start and abs((o_start - start).total_seconds()) <= 1800:
            return other
    return None


def _read_self_eval(raw) -> tuple:
    """(rpe 1-10 | None, feel 0-100 | None) aus get_activity()."""
    s = (raw or {}).get("summaryDTO") or {}
    rpe = _num(s.get("directWorkoutRpe"))
    feel = _num(s.get("directWorkoutFeel"))
    rpe = round(rpe / 10, 1) if rpe and rpe > 0 else None
    feel = int(feel) if feel is not None and 0 <= feel <= 100 else None
    return rpe, feel


def update_sessions(client, activities: list) -> dict:
    """Ergänzt den Cache um neue Einheiten aus der Aktivitätenliste und lädt
    RPE/Gefühl für jüngere Einheiten nach (höchstens RPE_MAX_FETCH Abrufe)."""
    cache = _load_cache()
    changed = False
    now = datetime.datetime.now()
    budget = RPE_MAX_FETCH

    for act in activities or []:
        try:
            aid = act.get("activityId")
            start = _parse_dt(act.get("startTimeLocal"))
            sport = _sport(act)
            if aid is None or not start or not sport:
                continue
            if sport == "ride" and (act.get("distance") or 0) <= 0:
                continue  # HF-Zweitaufzeichnung, siehe _companion_ride
            if (act.get("duration") or 0) / 60.0 < MIN_DURATION_MIN:
                continue
            key = str(aid)
            entry = cache.get(key)
            if entry is None:
                companion = _companion_ride(act, activities) if sport == "ride" else None
                metrics = _extract(act, sport)
                if sport == "ride" and metrics["output"] and not metrics["ef"] and companion:
                    hr = _num(companion.get("averageHR"))
                    if hr:
                        metrics["ef"] = round(metrics["output"] / hr, 4)
                entry = {
                    "date": start.date().isoformat(),
                    "start": act.get("startTimeLocal"),
                    "name": act.get("activityName"),
                    "sport": sport,
                    "hard": _is_hard(act, sport),
                    "duration_min": round((act.get("duration") or 0) / 60.0),
                    "high_zone_share": (round(decoupling.high_zone_share(act) * 100, 1)
                                        if decoupling.high_zone_share(act) is not None else None),
                    "companion_id": companion.get("activityId") if companion else None,
                    **metrics,
                    "rpe": None, "feel": None, "rpe_checked": None,
                }
                cache[key] = entry
                changed = True

            age = (now - start).days
            if age > RPE_FETCH_DAYS or entry.get("rpe") is not None:
                continue
            checked = entry.get("rpe_checked")
            if checked and age > RPE_REFRESH_DAYS:
                continue
            if checked and checked == now.date().isoformat():
                continue  # höchstens einmal pro Tag erneut fragen
            if budget <= 0:
                continue
            budget -= 1
            rpe, feel = _read_self_eval(client.get_activity(aid))
            if rpe is None and entry.get("companion_id"):
                budget -= 1
                c_rpe, c_feel = _read_self_eval(client.get_activity(entry["companion_id"]))
                rpe, feel = rpe or c_rpe, feel if feel is not None else c_feel
            entry.update({"rpe": rpe, "feel": feel, "rpe_checked": now.date().isoformat()})
            changed = True
        except Exception as e:
            print(f"[tagesform] Einheit konnte nicht erfasst werden: {e}")

    if changed:
        cache = _save_cache(cache)
    return cache


# ---------------------------------------------------------------------------
# Achse 2: Leistung relativ zur Erwartung
# ---------------------------------------------------------------------------

def _relative(value, previous: list):
    """(Abweichung in %, Band in %) gegenüber dem Median der Vorgänger."""
    prev = [v for v in previous if v]
    if value is None or len(prev) < MIN_COMPARE:
        return None, None
    med = statistics.median(prev)
    if not med:
        return None, None
    pct = [(v - med) / med * 100 for v in prev]
    band = max(PERF_BAND_SD * statistics.stdev(pct), PERF_BAND_MIN_PCT) if len(pct) > 1 else PERF_BAND_MIN_PCT
    return round((value - med) / med * 100, 1), round(band, 1)


def _gym_relative(day: str, strength_sessions: list):
    """Gym: je Übung bestes e1RM des Tages gegen den Median der letzten
    Einheiten mit dieser Übung; Session-Wert = Median über die Übungen."""
    per_ex = {}
    for s in strength_sessions or []:
        d = s.get("date")
        for ex in s.get("exercises") or []:
            name = ex.get("exercise")
            if not d or not name or name == "Unknown":
                continue
            best = max([v for v in (progress.epley(st.get("weight_kg"), st.get("reps"))
                                    for st in ex.get("sets") or []) if v] or [0])
            if best > 0:
                per = per_ex.setdefault(name, {})
                per[d] = max(per.get(d, 0), best)
    devs, bands = [], []
    for name, days in per_ex.items():
        if day not in days:
            continue
        prev = [days[k] for k in sorted(days) if k < day][-COMPARE_N:]
        pct, band = _relative(days[day], prev)
        if pct is not None:
            devs.append(pct)
            bands.append(band)
    if len(devs) < 2:
        return None, None, 0
    return round(statistics.median(devs), 1), round(statistics.median(bands), 1), len(devs)


def _classify_perf(pct, band):
    if pct is None:
        return None
    if pct < -band:
        return "unter"
    if pct > band:
        return "ueber"
    return "erwartet"


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

def _verdict_hard(form, perf, rpe):
    if form is None:
        return "Tagesform noch ohne Baseline – nur Leistung bewertet"
    if perf is None:
        return "zu wenig Vergleichseinheiten"
    if form == "unter":
        return {"unter": "stimmig: müde und entsprechend gedrosselt",
                "erwartet": "gut verkraftet trotz schwächerer Tagesform",
                "ueber": "stark trotz Müdigkeit – Erholung danach im Blick behalten"}[perf]
    if form == "normal":
        if perf == "unter":
            if rpe is None:
                return "unter Erwartung – ohne RPE unklar, ob Ermüdung oder nicht ausgereizt"
            return ("unter Erwartung bei hoher Anstrengung – Hinweis auf Ermüdung"
                    if rpe > LOW_RPE else "unter Erwartung bei niedriger Anstrengung – nicht ausgereizt")
        return {"erwartet": "Normalfall", "ueber": "guter Tag"}[perf]
    # form == "ueber"
    if perf == "unter":
        if rpe is not None and rpe <= LOW_RPE:
            return "Potenzial liegen gelassen: gute Form, wenig Anstrengung"
        if rpe is None:
            return "gute Form, Leistung unter Erwartung – RPE fehlt für die Einordnung"
        return "gute Form, aber zäh: hohe Anstrengung bei schwächerer Leistung"
    return {"erwartet": "solide – bei der Form wäre Luft nach oben gewesen",
            "ueber": "Form genutzt"}[perf]


def evaluate(cache: dict, history: list, strength_sessions: list, today: datetime.date = None) -> dict:
    """Bewertet alle Einheiten der letzten EVAL_DAYS Tage."""
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=EVAL_DAYS)).isoformat()
    entries = sorted(cache.values(), key=lambda e: e.get("start") or e.get("date") or "")
    sessions = []
    for i, e in enumerate(entries):
        if (e.get("date") or "") < cutoff:
            continue
        sport, hard = e.get("sport"), bool(e.get("hard"))
        form = day_form(e["date"], history)
        same = [p for p in entries[:i] if p.get("sport") == sport and bool(p.get("hard")) == hard][-COMPARE_N:]
        if sport == "strength":
            perf_pct, band, n_cmp = _gym_relative(e["date"], strength_sessions)
            ef_pct = None
        else:
            perf_pct, band = _relative(e.get("output"), [p.get("output") for p in same])
            ef_pct, _ = _relative(e.get("ef"), [p.get("ef") for p in same])
            n_cmp = len([p for p in same if p.get("output")])
        perf = _classify_perf(perf_pct, band)
        rpe = e.get("rpe")
        if hard:
            verdict = _verdict_hard(form["level"], perf, rpe)
        else:
            share = e.get("high_zone_share")
            if share is not None and share > EASY_MAX_HIGH_ZONE_SHARE * 100:
                verdict = f"als locker gedacht, aber {share:.0f} % in Zone 4–5"
            else:
                verdict = "locker gehalten – Zurückhaltung ist hier richtig"
        sessions.append({
            "date": e["date"], "name": e.get("name"), "sport": SPORT_DE.get(sport, sport),
            "intent": "hart" if hard else "locker", "duration_min": e.get("duration_min"),
            "form": FORM_DE.get(form["level"]) if form["level"] else "ohne Baseline",
            "form_level": form["level"], "form_reasons": form["reasons"],
            "perf_pct": perf_pct, "perf_band_pct": band, "perf": PERF_DE.get(perf) if perf else None,
            "ef_pct": ef_pct, "n_compare": n_cmp,
            "rpe": rpe, "feel": FEEL_DE.get(e.get("feel")) if e.get("feel") is not None else None,
            "verdict": verdict,
        })

    hard = [s for s in sessions if s["intent"] == "hart"]
    last14 = (today - datetime.timedelta(days=14)).isoformat()
    tired_strong = [s for s in hard if s["date"] >= last14 and s["form_level"] == "unter"
                    and s["perf"] in (PERF_DE["erwartet"], PERF_DE["ueber"])]
    good_form = [s for s in hard if s["form_level"] == "ueber" and s["perf"]]
    used = [s for s in good_form if s["perf"] == PERF_DE["ueber"]]
    with_rpe = [s for s in sessions if s.get("rpe") is not None]
    summary = {
        "sessions_rated": len(sessions),
        "hard_sessions": len(hard),
        "rpe_coverage_pct": round(len(with_rpe) / len(sessions) * 100) if sessions else None,
        "good_form_hard": len(good_form),
        "good_form_used": len(used),
        "tired_but_strong_14d": len(tired_strong),
        "overreaching_hint": len(tired_strong) >= 3,
    }
    return {"sessions": sessions[::-1], "summary": summary}


def state_text(result: dict) -> str:
    hard = [s for s in result.get("sessions") or [] if s["intent"] == "hart"]
    if not hard:
        return "noch keine harte Einheit bewertet"
    s = hard[0]
    return f"{s['date'][8:10]}.{s['date'][5:7]}. {s['sport']}: {s['verdict']}"


def prompt_block(result: dict, max_items: int = 4) -> str:
    """Kurzer Block für den Coaching-Prompt (nur harte Einheiten)."""
    hard = [s for s in result.get("sessions") or [] if s["intent"] == "hart"][:max_items]
    if not hard:
        return ""
    lines = []
    for s in hard:
        perf = f"{s['perf_pct']:+.1f} %" if s["perf_pct"] is not None else "k. A."
        rpe = f"RPE {s['rpe']:g}" if s["rpe"] is not None else "ohne RPE"
        lines.append(f"- {s['date']} {s['sport']} ({s['name']}): Tagesform {s['form']}, "
                     f"Leistung {perf} ggü. eigenen Vergleichseinheiten, {rpe} → {s['verdict']}")
    summ = result.get("summary") or {}
    if summ.get("overreaching_hint"):
        lines.append(f"- Achtung: {summ['tired_but_strong_14d']} harte Einheiten in 14 Tagen trotz "
                     "Tagesform unter Baseline voll durchgezogen – Hinweis auf funktionelles Overreaching.")
    return "\n".join(lines)
