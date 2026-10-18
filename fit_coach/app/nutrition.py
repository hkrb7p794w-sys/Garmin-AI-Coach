"""Ernährung aus Yazio: Tageswerte, Wochenschnitt, Eiweiß, geschätzter Verbrauch.

Grundsätze (Quellen im Dashboard unter „Wie das gerechnet wird“):
- Regelmäßiges Protokollieren hängt eng mit dem Abnehmerfolg zusammen; wer
  häufiger einträgt, nimmt mehr ab (Harvey 2019, Obesity, doi:10.1002/oby.22382).
  Deshalb zählt das Dashboard „protokollierte Tage“, nicht nur Kalorien.
- Eiweiß: Mehr Eiweiß hilft, Muskeln während der Abnahme zu erhalten
  (Cava 2017, Adv Nutr, doi:10.3945/an.116.014506); bei Krafttraining bringt mehr als
  ~1,6 g/kg/Tag keinen zusätzlichen Muskelzuwachs (Morton 2018, BJSM,
  doi:10.1136/bjsports-2017-097608). Richtwert hier 1,2-1,6 g pro kg Zielgewicht
  (bzw. aktuellem Gewicht, wenn kein Ziel gesetzt ist).
- Untergrenze: Leitlinien für Abnehmprogramme nennen für Frauen meist
  1.200-1.500 kcal/Tag (Jensen 2014, Circulation, doi:10.1161/01.cir.0000437739.71477.ee).
  Liegt der Schnitt vollständig erfasster Tage darunter, kommt ein Hinweis -
  zu wenig Energie bremst Training und Erholung (IOC-Konsens REDs, Mountjoy 2023,
  doi:10.1136/bjsports-2023-106994).
- Geschätzter Verbrauch: Uhren schätzen den Energieverbrauch ungenau (in einer
  Laborstudie lag kein Gerät unter 20 % Fehler; Shcherbina 2017, J Pers Med,
  doi:10.3390/jpm7020003). Genauer ist der Rückschluss aus dem, was gegessen
  wurde, und wie sich der Gewichtstrend dabei verändert hat:
  Verbrauch ≈ Ø Aufnahme − (Trendänderung kg × 7.700 kcal) / Tage.
  Das ist eine Schätzung (die Energiedichte der Gewichtsänderung ist nicht
  konstant) und funktioniert nur, wenn fast jeder Tag vollständig erfasst ist.
"""
import datetime

KCAL_PER_KG = 7700
LOW_INTAKE_KCAL = 1200
PROTEIN_G_PER_KG = (1.2, 1.6)
MIN_COMPLETE_DAYS_TDEE = 10


def _d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def parse_daily_summary(summary: dict) -> dict:
    """Yazio /user/widgets/daily-summary -> kompakter Tageseintrag."""
    meals = (summary or {}).get("meals") or {}
    kcal = protein = carbs = fat = 0.0
    logged_meals = 0
    for name in ("breakfast", "lunch", "dinner", "snack"):
        n = (meals.get(name) or {}).get("nutrients") or {}
        e = float(n.get("energy.energy") or 0)
        if e > 0:
            logged_meals += 1
        kcal += e
        protein += float(n.get("nutrient.protein") or 0)
        carbs += float(n.get("nutrient.carb") or 0)
        fat += float(n.get("nutrient.fat") or 0)
    goals = (summary or {}).get("goals") or {}
    user = (summary or {}).get("user") or {}
    activity = float((summary or {}).get("activity_energy") or 0)
    adds_activity = bool((summary or {}).get("consume_activity_energy"))
    goal = float(goals.get("energy.energy") or 0) or None
    return {
        "kcal": round(kcal),
        "protein": round(protein, 1),
        "carbs": round(carbs, 1),
        "fat": round(fat, 1),
        "meals": logged_meals,
        "goal_kcal": round(goal) if goal else None,
        "goal_protein": round(float(goals.get("nutrient.protein") or 0)) or None,
        "goal_carbs": round(float(goals.get("nutrient.carb") or 0)) or None,
        "goal_fat": round(float(goals.get("nutrient.fat") or 0)) or None,
        "activity_kcal": round(activity),
        "adds_activity": adds_activity,
        "goal_effective": round((goal or 0) + (activity if adds_activity else 0)) or None,
        "water_ml": round(float((summary or {}).get("water_intake") or 0)),
        "water_goal": round(float(goals.get("water") or 0)) or None,
        "steps": int((summary or {}).get("steps") or 0),
        "weight_goal": float(goals.get("bodyvalue.weight") or 0) or None,
        "start_weight": float(user.get("start_weight") or 0) or None,
        "current_weight": float(user.get("current_weight") or 0) or None,
        "energy_unit": ((summary or {}).get("units") or {}).get("unit_energy"),
    }


def is_complete(day: dict) -> bool:
    """Gilt der Tag als vollständig erfasst? Mindestens 3 Mahlzeiten oder
    mindestens die Hälfte des Tagesziels. Halbe Tage verfälschen sonst Schnitt
    und Verbrauchsschätzung nach unten."""
    if not day or not day.get("kcal"):
        return False
    goal = day.get("goal_effective") or day.get("goal_kcal") or 0
    return day.get("meals", 0) >= 3 or (goal and day["kcal"] >= 0.5 * goal)


def _window(days: dict, today: datetime.date, n: int, include_today=False):
    end = today if include_today else today - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=n - 1)
    out = []
    d = start
    while d <= end:
        out.append((d.isoformat(), days.get(d.isoformat())))
        d += datetime.timedelta(days=1)
    return out


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals)) if vals else None


def protein_target(goal_kg, trend_kg):
    ref = goal_kg or trend_kg
    if not ref:
        return None
    return {"low": round(ref * PROTEIN_G_PER_KG[0]), "high": round(ref * PROTEIN_G_PER_KG[1]),
            "ref_kg": round(ref, 1), "ref": "Zielgewicht" if goal_kg else "aktuelles Gewicht"}


def expenditure_estimate(days: dict, weight_series: list, today: datetime.date, window: int = 28):
    """Geschätzter Tagesverbrauch aus Aufnahme + Gewichtstrend (siehe Modultext)."""
    win = _window(days, today, window)
    complete = [(d, v) for d, v in win if is_complete(v)]
    if len(complete) < MIN_COMPLETE_DAYS_TDEE or not weight_series:
        return {"ok": False, "complete_days": len(complete), "need": MIN_COMPLETE_DAYS_TDEE}
    first_day = _d(complete[0][0])
    last_day = _d(win[-1][0])
    trend = {p["d"]: p["t"] for p in weight_series}
    dates = sorted(trend)

    def at(day):
        val = None
        for k in dates:
            if k <= day.isoformat():
                val = trend[k]
            else:
                break
        return val

    t0 = at(first_day - datetime.timedelta(days=1)) or at(first_day)
    t1 = at(last_day)
    span = (last_day - first_day).days + 1
    if t0 is None or t1 is None or span < 14:
        return {"ok": False, "complete_days": len(complete), "need": MIN_COMPLETE_DAYS_TDEE}
    intake = sum(v["kcal"] for _, v in complete) / len(complete)
    tdee = intake - (t1 - t0) * KCAL_PER_KG / span
    share = len(complete) / span
    return {"ok": True, "kcal": int(round(tdee / 50.0) * 50), "intake_avg": round(intake),
            "trend_change": round(t1 - t0, 2), "days": span, "complete_days": len(complete),
            "confidence": "gut" if share >= 0.85 else "mittel" if share >= 0.65 else "gering"}


def analyze(days: dict, today: datetime.date = None, goal_kg=None, trend_kg=None,
            weight_series=None, garmin_total_kcal=None) -> dict:
    today = today or datetime.date.today()
    t = days.get(today.isoformat()) or {}
    w7 = _window(days, today, 7)
    w14 = _window(days, today, 14)
    complete7 = [v for _, v in w7 if is_complete(v)]
    logged7 = sum(1 for _, v in w7 if v and v.get("kcal"))
    logged14 = sum(1 for _, v in w14 if v and v.get("kcal"))
    avg_kcal = _avg([v["kcal"] for v in complete7])
    avg_goal = _avg([v.get("goal_effective") or v.get("goal_kcal") for v in complete7])
    avg_protein = _avg([v["protein"] for v in complete7])
    ptarget = protein_target(goal_kg, trend_kg)
    hints = []
    if len(complete7) >= 4 and avg_kcal is not None and avg_kcal < LOW_INTAKE_KCAL:
        hints.append({"kind": "warn", "id": "low_intake",
                      "text": f"Im Schnitt {avg_kcal} kcal an vollständig erfassten Tagen – unter 1.200 kcal wird es für Training und Erholung knapp. Lieber etwas mehr essen und langsamer abnehmen."})
    if ptarget and avg_protein is not None and len(complete7) >= 3 and avg_protein < ptarget["low"]:
        hints.append({"kind": "info", "id": "protein_low",
                      "text": f"Eiweiß im Schnitt {avg_protein} g – Richtwert {ptarget['low']}–{ptarget['high']} g. Einfache Extras: Skyr/Quark, Eier, Linsen, Hüttenkäse."})
    if logged7 <= 3:
        hints.append({"kind": "info", "id": "log_more",
                      "text": f"{logged7} von 7 Tagen in Yazio erfasst. Wer häufiger einträgt, nimmt im Schnitt mehr ab – auch grobe Einträge zählen."})
    series = []
    for d, v in _window(days, today, 28, include_today=True):
        series.append({"d": d, "k": (v or {}).get("kcal") or 0, "g": (v or {}).get("goal_effective") or (v or {}).get("goal_kcal"),
                       "p": (v or {}).get("protein") or 0, "c": 1 if is_complete(v) else 0})
    goal_today = t.get("goal_effective") or t.get("goal_kcal")
    res = {
        "has_data": any(v for v in days.values()),
        "today": {
            "kcal": t.get("kcal"), "goal": goal_today, "base_goal": t.get("goal_kcal"),
            "adds_activity": t.get("adds_activity"), "activity_kcal": t.get("activity_kcal"),
            "remaining": (goal_today - t.get("kcal", 0)) if goal_today else None,
            "protein": t.get("protein"), "protein_goal": t.get("goal_protein"),
            "carbs": t.get("carbs"), "carbs_goal": t.get("goal_carbs"),
            "fat": t.get("fat"), "fat_goal": t.get("goal_fat"),
            "water_ml": t.get("water_ml"), "water_goal": t.get("water_goal"),
            "meals": t.get("meals"),
        },
        "avg7_kcal": avg_kcal, "avg7_goal": avg_goal, "avg7_protein": avg_protein,
        "avg7_diff": (avg_kcal - avg_goal) if avg_kcal is not None and avg_goal else None,
        "complete7": len(complete7), "logged7": logged7, "logged14": logged14,
        "protein_target": ptarget,
        "hints": hints,
        "series": series,
        "garmin_total_kcal": garmin_total_kcal,
    }
    if weight_series:
        res["expenditure"] = expenditure_estimate(days, weight_series, today)
    return res


def logged_streak(days: dict, today: datetime.date = None) -> int:
    today = today or datetime.date.today()
    d = today if (days.get(today.isoformat()) or {}).get("kcal") else today - datetime.timedelta(days=1)
    n = 0
    while (days.get(d.isoformat()) or {}).get("kcal"):
        n += 1
        d -= datetime.timedelta(days=1)
    return n
