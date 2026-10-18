"""Wochenziele, Wochenserie und Abzeichen.

Spielregeln (bewusst einfach und fair für Einsteigerinnen):
- Woche = Montag bis Sonntag.
- Wochenziel = geplante Läufe UND geplante Gym-Einheiten geschafft
  (Ziele im Dashboard einstellbar, Standard 3 Läufe + 1× Gym).
- Bewegungsziel = 150 Minuten moderate Bewegung (Garmin-Intensitätsminuten,
  intensive Minuten zählen doppelt) - Untergrenze der WHO-Empfehlung
  150-300 min/Woche (Bull 2020, BJSM, doi:10.1136/bjsports-2020-102955).
- Eine Woche zählt für die Serie, wenn Wochenziel ODER Bewegungsziel erreicht
  ist. Wochen- statt Tagesserie, damit Ruhetage nicht bestraft werden.
- Schritte: mehr Schritte pro Tag gehen mit niedrigerer Sterblichkeit einher,
  bei unter 60-Jährigen bis etwa 8.000-10.000 (Paluch 2022, Lancet Public Health,
  doi:10.1016/S2468-2667(21)00302-9). Das Schrittziel kommt von Garmin.
"""
import datetime

WHO_MINUTES = 150


def _d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def monday(day):
    return day - datetime.timedelta(days=day.weekday())


def intensity_minutes(day_entry) -> int:
    if not day_entry:
        return 0
    return int((day_entry.get("mod_min") or 0) + 2 * (day_entry.get("vig_min") or 0))


def week_stats(start: datetime.date, acts: list, daily: dict, run_target: int, gym_target: int,
               today: datetime.date) -> dict:
    end = start + datetime.timedelta(days=7)
    in_week = [a for a in acts if start <= _d(a["date"]) < end]
    runs = sum(1 for a in in_week if a["kind"] == "run")
    gym = sum(1 for a in in_week if a["kind"] == "strength")
    days = [(start + datetime.timedelta(days=i)).isoformat() for i in range(7)]
    have_daily = [daily.get(d) for d in days if daily.get(d)]
    if have_daily:
        active = sum(intensity_minutes(x) for x in have_daily)
        active_src = "garmin"
    else:
        active = round(sum(a["sec"] for a in in_week if a["kind"] in ("run", "strength", "walk", "other") and a["sec"] >= 600) / 60)
        active_src = "aktivitaeten"
    steps = [x.get("steps") for x in have_daily if x.get("steps")]
    goal_steps = [x.get("step_goal") for x in have_daily if x.get("step_goal")]
    workouts_ok = runs >= run_target and (gym_target <= 0 or gym >= gym_target)
    move_ok = active >= WHO_MINUTES
    parts = [min(1.0, runs / run_target) if run_target > 0 else None,
             min(1.0, gym / gym_target) if gym_target > 0 else None,
             min(1.0, active / WHO_MINUTES)]
    parts = [p for p in parts if p is not None]
    return {
        "w": start.isoformat(), "runs": runs, "gym": gym, "run_target": run_target, "gym_target": gym_target,
        "active_min": active, "active_src": active_src, "active_goal": WHO_MINUTES,
        "steps_avg": round(sum(steps) / len(steps)) if steps else None,
        "step_goal": round(sum(goal_steps) / len(goal_steps)) if goal_steps else None,
        "workouts_ok": workouts_ok, "move_ok": move_ok, "ok": workouts_ok or move_ok,
        "pct": round(sum(parts) / len(parts) * 100) if parts else 0,
        "current": start == monday(today),
        "days_left": max(0, 6 - today.weekday()) if start == monday(today) else 0,
    }


def weekly(acts, daily, run_target, gym_target, today, n=12) -> dict:
    this = monday(today)
    weeks = [week_stats(this - datetime.timedelta(weeks=i), acts, daily, run_target, gym_target, today)
             for i in range(n - 1, -1, -1)]
    # Serie: abgeschlossene Wochen rückwärts; die laufende zählt mit, sobald sie erfüllt ist.
    streak = 0
    for w in reversed(weeks[:-1]):
        if w["ok"]:
            streak += 1
        else:
            break
    if weeks[-1]["ok"]:
        streak += 1
    best = run = 0
    for w in weeks:
        run = run + 1 if w["ok"] else 0
        best = max(best, run)
    return {"current": weeks[-1], "history": weeks, "streak": streak, "best_streak_12w": best}


# ---------------------------------------------------------------- Abzeichen
# (id, Gruppe, Titel, Beschreibung, Icon, Kennzahl, Schwelle)
BADGES = [
    ("lauf_1", "Laufen", "Erster Lauf", "Den ersten Lauf aufgezeichnet", "run", "runs_total", 1),
    ("lauf_10", "Laufen", "10 Läufe", "Dranbleiben zahlt sich aus", "run", "runs_total", 10),
    ("lauf_25", "Laufen", "25 Läufe", "Laufen wird zur Gewohnheit", "run-fast", "runs_total", 25),
    ("lauf_50", "Laufen", "50 Läufe", "Echte Läuferin", "run-fast", "runs_total", 50),
    ("lauf_3km", "Laufen", "3 km", "Ein Lauf über 3 km", "map-marker-distance", "longest_km", 3),
    ("lauf_5km", "Laufen", "5 km", "Ein Lauf über 5 km", "map-marker-distance", "longest_km", 5),
    ("lauf_10km", "Laufen", "10 km", "Ein Lauf über 10 km", "map-marker-distance", "longest_km", 10),
    ("lauf_30min", "Laufen", "30 Minuten", "30 Minuten Laufeinheit", "timer-outline", "longest_min", 30),
    ("km_50", "Laufen", "50 km gesamt", "Zusammengezählt 50 km", "road-variant", "km_total", 50),
    ("km_100", "Laufen", "100 km gesamt", "Dreistellig!", "road-variant", "km_total", 100),
    ("km_250", "Laufen", "250 km gesamt", "Eine ordentliche Strecke", "road-variant", "km_total", 250),
    ("woche_3laeufe", "Laufen", "3 Läufe in einer Woche", "Drei Läufe in einer Woche", "calendar-check", "max_runs_week", 3),
    ("fuenf_40", "Laufen", "5 km unter 40 min", "Bestzeit über 5 km < 40:00", "timer-sand", "five_k_under_40", 1),
    ("fuenf_35", "Laufen", "5 km unter 35 min", "Bestzeit über 5 km < 35:00", "timer-sand", "five_k_under_35", 1),
    ("fuenf_30", "Laufen", "5 km unter 30 min", "Bestzeit über 5 km < 30:00", "trophy-outline", "five_k_under_30", 1),
    ("gym_1", "Gym", "Erstes Training", "Erste Krafteinheit", "dumbbell", "gym_total", 1),
    ("gym_10", "Gym", "10 Trainings", "Zehn Krafteinheiten", "dumbbell", "gym_total", 10),
    ("gym_25", "Gym", "25 Trainings", "Kraft ist Routine", "weight-lifter", "gym_total", 25),
    ("rekord_1", "Gym", "Erster Rekord", "Eine Übung verbessert", "arm-flex", "pr_count", 1),
    ("rekord_10", "Gym", "10 Rekorde", "Zehnmal stärker geworden", "arm-flex", "pr_count", 10),
    ("kg_1", "Gewicht", "−1 kg", "Trend 1 kg unter Start", "scale-bathroom", "kg_lost", 1),
    ("kg_3", "Gewicht", "−3 kg", "Trend 3 kg unter Start", "scale-bathroom", "kg_lost", 3),
    ("kg_5", "Gewicht", "−5 kg", "Trend 5 kg unter Start", "scale-bathroom", "kg_lost", 5),
    ("kg_10", "Gewicht", "−10 kg", "Trend 10 kg unter Start", "scale-bathroom", "kg_lost", 10),
    ("halbzeit", "Gewicht", "Halbzeit", "Hälfte des Weges zum Zielgewicht", "flag-outline", "goal_pct", 50),
    ("ziel", "Gewicht", "Zielgewicht", "Zielgewicht erreicht", "flag-checkered", "goal_pct", 100),
    ("wiegen_7", "Gewohnheiten", "7 Tage gewogen", "Eine Woche lang jeden Tag gewogen", "calendar-week", "weighin_streak", 7),
    ("yazio_7", "Gewohnheiten", "7 Tage protokolliert", "Eine Woche lückenlos in Yazio", "food-apple-outline", "logged_streak", 7),
    ("yazio_30", "Gewohnheiten", "30 Tage protokolliert", "Ein Monat lückenlos in Yazio", "food-apple", "logged_streak", 30),
    ("serie_2", "Konstanz", "2 Wochen Serie", "Zwei Wochen in Folge geschafft", "fire", "best_streak", 2),
    ("serie_4", "Konstanz", "4 Wochen Serie", "Einen Monat drangeblieben", "fire", "best_streak", 4),
    ("serie_8", "Konstanz", "8 Wochen Serie", "Zwei Monate in Folge", "fire", "best_streak", 8),
    ("serie_12", "Konstanz", "12 Wochen Serie", "Ein Vierteljahr – stark", "fire", "best_streak", 12),
    ("who_1", "Konstanz", "150 Minuten", "Bewegungsempfehlung der WHO erreicht", "heart-pulse", "move_weeks", 1),
    ("who_4", "Konstanz", "4× 150 Minuten", "Vier Wochen mit 150+ Minuten", "heart-pulse", "move_weeks", 4),
    ("schritte_10k", "Konstanz", "10.000 Schritte", "An einem Tag 10.000 Schritte", "walk", "max_steps", 10000),
]


def metrics(acts, recs_prs, gym_info, weight_info, weekly_info, daily, weighin_streak, logged_streak, run_prs) -> dict:
    runs = sorted([a for a in acts if a["kind"] == "run"], key=lambda a: a["start"])
    weeks = {}
    for r in runs:
        k = monday(_d(r["date"])).isoformat()
        weeks[k] = weeks.get(k, 0) + 1
    five = next((p["value"] for p in run_prs or [] if p["type"] == 3 and not p.get("estimated")), None)
    kg_lost = None
    goal_pct = None
    if weight_info and weight_info.get("has_data"):
        kg_lost = round(weight_info["start_kg"] - weight_info["trend"], 1)
        goal_pct = weight_info.get("progress_pct")
    hist = (weekly_info or {}).get("history") or []
    return {
        "runs_total": len(runs),
        "km_total": round(sum(r["km"] for r in runs), 1),
        "longest_km": max((r["km"] for r in runs), default=0),
        "longest_min": max((r["sec"] / 60 for r in runs), default=0),
        "max_runs_week": max(weeks.values(), default=0),
        "five_k_under_40": 1 if five and five < 2400 else 0,
        "five_k_under_35": 1 if five and five < 2100 else 0,
        "five_k_under_30": 1 if five and five < 1800 else 0,
        "gym_total": (gym_info or {}).get("sessions_total", 0),
        "pr_count": (gym_info or {}).get("pr_count", 0),
        "kg_lost": kg_lost or 0,
        "goal_pct": goal_pct or 0,
        "weighin_streak": weighin_streak or 0,
        "logged_streak": logged_streak or 0,
        "best_streak": (weekly_info or {}).get("best_streak_12w", 0),
        "move_weeks": sum(1 for w in hist if w.get("move_ok")),
        "max_steps": max((v.get("steps") or 0 for v in (daily or {}).values()), default=0),
    }


def achieved_dates(acts) -> dict:
    """Tatsächliches Datum für Abzeichen, die sich aus Aktivitäten ergeben
    (z. B. „10 Läufe“ = Datum des 10. Laufs) - damit auch beim ersten Sync die
    Zeitleiste stimmt. Alles andere bekommt das Datum, an dem es erkannt wurde."""
    runs = sorted([a for a in acts if a["kind"] == "run"], key=lambda a: a["start"])
    gyms = sorted([a for a in acts if a["kind"] == "strength"], key=lambda a: a["start"])
    out = {}
    for bid, _g, _t, _d2, _i, key, need in BADGES:
        hit = None
        if key == "runs_total" and len(runs) >= need:
            hit = runs[need - 1]["date"]
        elif key == "gym_total" and len(gyms) >= need:
            hit = gyms[need - 1]["date"]
        elif key == "km_total":
            tot = 0.0
            for r in runs:
                tot += r["km"]
                if tot >= need:
                    hit = r["date"]
                    break
        elif key == "longest_km":
            hit = next((r["date"] for r in runs if r["km"] >= need), None)
        elif key == "longest_min":
            hit = next((r["date"] for r in runs if r["sec"] / 60 >= need), None)
        elif key == "max_runs_week":
            per = {}
            for r in runs:
                k = monday(_d(r["date"]))
                per[k] = per.get(k, 0) + 1
                if per[k] >= need:
                    hit = r["date"]
                    break
        if hit:
            out[bid] = hit
    return out


def badges(m: dict, earned: dict, today: datetime.date, dates: dict = None):
    """Gibt (Liste für das Dashboard, aktualisiertes earned-Dict, neu verdiente IDs) zurück.
    Einmal verdient bleibt verdient (earned wird gespeichert)."""
    earned = dict(earned or {})
    dates = dates or {}
    new = []
    out = []
    for bid, group, title, desc, icon, key, need in BADGES:
        have = m.get(key) or 0
        if bid not in earned and have >= need:
            earned[bid] = dates.get(bid) or today.isoformat()
            new.append(bid)
        out.append({"id": bid, "group": group, "title": title, "desc": desc, "icon": icon,
                    "earned": earned.get(bid), "have": round(have, 1) if isinstance(have, float) else have,
                    "need": need, "progress": 1.0 if bid in earned else round(min(1.0, have / need), 2) if need else 0})
    return out, earned, new
