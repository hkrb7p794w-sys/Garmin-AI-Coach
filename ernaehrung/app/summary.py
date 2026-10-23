"""Tages- und Wochenauswertung (auch Grundlage für Home Assistant / Phase 2)."""
import datetime

import db
import garmin_bridge
import nutrients as N
import recommend
import targets as T


def settings_bundle() -> dict:
    keys = ("profile", "pal_base", "goal", "goal_adjust_pct", "protein_g_per_kg", "carbs_g_per_kg",
            "body_fat_pct", "weight_entity",
            "target_overrides", "day_type_override")
    return {k: db.get_setting(k) for k in keys}


def targets_for(date: str) -> dict:
    today = datetime.date.today().isoformat()
    sb = settings_bundle()
    if date == today:
        res = T.compute(sb, garmin_bridge.training_today(weight_entity=sb.get("weight_entity")), date)
        db.save_day_targets(date, res)
        return res
    stored = db.get_day_targets(date)
    if stored:
        # Ziele für Nährstoffe, die es beim Speichern noch nicht gab (Jod, Omega-3), ergänzen
        missing = [k for k in N.KEYS if k not in stored["targets"]]
        if missing:
            fresh = T.compute(sb, None, date)["targets"]
            for k in missing:
                if k in fresh:
                    stored["targets"][k] = fresh[k]
        return stored
    res = T.compute(settings_bundle(), None, date)
    res["estimated"] = True  # Tag ohne gespeicherte Trainingsdaten
    return res


def meal_totals(meal: dict) -> dict:
    tot = {k: None for k in N.KEYS}
    missing = set()
    for it in meal["items"]:
        part = N.scale(it["per100"], it["amount_g"])
        N.add(tot, part)
        for k in N.MICRO_KEYS:
            if it["per100"].get(k) is None and it["amount_g"] > 0:
                missing.add(k)
    return tot, missing


def _round(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if v is None:
            out[k] = None
        else:
            out[k] = round(v, 1) if abs(v) < 100 else round(v)
    return out


def progress(totals: dict, tgt: dict) -> dict:
    out = {}
    for k in N.KEYS:
        t, v = tgt.get(k), totals.get(k)
        out[k] = None if not t else round(100 * (v or 0) / t)
    return out


def day(date: str) -> dict:
    meals = db.meals_between(date, date)
    totals = {k: None for k in N.KEYS}
    missing_items = {}
    by_cat = {c: {"meals": [], "kcal": 0} for c in db.CATEGORIES}
    for m in meals:
        mt, miss = meal_totals(m)
        m["totals"] = _round(mt)
        N.add(totals, mt)
        for k in miss:
            missing_items[k] = missing_items.get(k, 0) + 1
        by_cat[m["category"]]["meals"].append(m)
        by_cat[m["category"]]["kcal"] += mt.get("kcal") or 0
    tg = targets_for(date)
    totals = {k: (v if v is not None else 0) for k, v in totals.items()}
    return {
        "date": date,
        "meals_count": len(meals),
        "totals": _round(totals),
        "targets": tg["targets"],
        "target_kind": tg.get("kind", {}),
        "progress": progress(totals, tg["targets"]),
        "day_type": tg["day_type"],
        "day_label": tg["day_label"],
        "day_source": tg.get("day_source"),
        "training": tg.get("training"),
        "activities": tg.get("activities"),
        "energy": tg.get("energy"),
        "profile": tg.get("profile"),
        "profile_source": tg.get("profile_source"),
        "plan_text": tg.get("plan_text"),
        "estimated_targets": bool(tg.get("estimated")),
        "incomplete": missing_items,      # Nährstoff -> Anzahl Positionen ohne Wert
        # Proteinverteilung: Mahlzeiten mit >= 0,25 g/kg (ISSN 2017: 0,25-0,4 g/kg bzw. 20-40 g
        # alle 3-4 h; ISSN 2026: mind. 3 proteinreiche Mahlzeiten)
        "protein_meals": sum(1 for m in meals
                             if (m["totals"].get("protein_g") or 0) >= 0.25 * tg["profile"]["weight_kg"]),
        "protein_meal_min_g": round(0.25 * tg["profile"]["weight_kg"]),
        "protein_g_per_kg": tg.get("protein_g_per_kg"),
        "planned_day_type": tg.get("planned_day_type"),
        "categories": {c: {"label": db.CATEGORY_LABELS[c], "kcal": round(v["kcal"]), "meals": v["meals"]}
                       for c, v in by_cat.items()},
    }


def day_with_recommendations(date: str) -> dict:
    d = day(date)
    try:
        d["recommendations"] = recommend.day_recommendations(d, db.get_setting("diet") or "pescetarisch")
    except Exception as e:  # Empfehlungen dürfen die Tagesansicht nie verhindern
        print(f"[recommend] Tag: {e!r}")
        d["recommendations"] = []
    return d


def status_of(key: str, pct, kind: str = None) -> str:
    if pct is None:
        return "?"
    if kind == "max":
        return "ok" if pct <= 100 else "zu_hoch"
    if key == "kcal":
        return "ok" if 90 <= pct <= 110 else ("zu_niedrig" if pct < 90 else "zu_hoch")
    return "ok" if pct >= 90 else ("knapp" if pct >= 70 else "zu_niedrig")


def week(end_date: str = None, days: int = 7) -> dict:
    end = datetime.date.fromisoformat(end_date) if end_date else datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    rows = []
    meals_by_day = {}
    for i in range(days):
        d = (start + datetime.timedelta(days=i)).isoformat()
        ds = day(d)
        meals_by_day[d] = [m for c in ds["categories"].values() for m in c.get("meals", [])]
        for c in ds["categories"].values():   # Wochenansicht ohne Mahlzeiten-Details
            c.pop("meals", None)
        rows.append(ds)
    logged = [r for r in rows if r["meals_count"] > 0]
    # Heute zählt erst, wenn >= 70 % der Ziel-kcal erfasst sind (sonst verzerrt der halbe Tag)
    today = datetime.date.today().isoformat()
    complete = [r for r in logged if r["date"] != today or (r["progress"].get("kcal") or 0) >= 70]
    avg, hit_rate, gaps = {}, {}, []
    if complete:
        for k in N.KEYS:
            vals = [r["totals"].get(k) or 0 for r in complete]
            avg[k] = round(sum(vals) / len(vals), 1)
            kind = (complete[0]["target_kind"] or {}).get(k)
            states = [status_of(k, r["progress"].get(k), kind) for r in complete]
            ok = sum(1 for s in states if s == "ok")
            hit_rate[k] = round(100 * ok / len(states))
            low = sum(1 for s in states if s in ("zu_niedrig",))
            high = sum(1 for s in states if s == "zu_hoch")
            if len(states) >= 3 and low / len(states) >= 0.5:
                gaps.append({"key": k, "label": N.NUTRIENTS[k][0], "issue": "zu_niedrig",
                             "days": low, "of": len(states)})
            if len(states) >= 3 and high / len(states) >= 0.5:
                gaps.append({"key": k, "label": N.NUTRIENTS[k][0], "issue": "zu_hoch",
                             "days": high, "of": len(states)})
    # Kohlenhydrate an harten Tagen / Protein an Trainingstagen
    hard = [r for r in complete if r["day_type"] in ("hart", "sehr_hart")]
    training_days = [r for r in complete if r["day_type"] != "ruhetag"]
    fueling = {
        "hard_days": len(hard),
        "carbs_pct_hard_days": round(sum(r["progress"]["carbs_g"] or 0 for r in hard) / len(hard)) if hard else None,
        "protein_pct_training_days": round(sum(r["progress"]["protein_g"] or 0 for r in training_days)
                                           / len(training_days)) if training_days else None,
    }
    complete_dates = {r["date"] for r in complete}
    fg = recommend.week_food_groups({d: m for d, m in meals_by_day.items() if d in complete_dates})
    result = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": [{k: r[k] for k in ("date", "meals_count", "totals", "targets", "progress", "day_type",
                                    "day_label", "estimated_targets")} for r in rows],
        "logged_days": len(logged),
        "complete_days": len(complete),
        "average": avg,
        "hit_rate": hit_rate,
        "gaps": gaps,
        "fueling": fueling,
        "food_groups": fg,
        "energy_balance": energy_balance(end),
    }
    try:
        result["recommendations"] = recommend.week_recommendations(result, fg, db.get_setting("diet") or
                                                                   "pescetarisch", end)
    except Exception as e:
        print(f"[recommend] Woche: {e!r}")
        result["recommendations"] = []
    return result


KCAL_PER_KG = 7700  # gängige Näherung für Körpergewebe (Fett + etwas Magermasse)


def energy_balance(end: datetime.date, window: int = 28):
    """Tatsächlichen Energieverbrauch aus Gewichtsverlauf und erfasster Zufuhr schätzen
    (Prinzip wie MacroFactor: Zufuhr - Gewichtsänderung x Energiedichte). Braucht mindestens
    14 vollständig erfasste Tage und Gewichtswerte über mindestens 14 Tage."""
    start = end - datetime.timedelta(days=window - 1)
    weights, intakes, targets = [], [], []
    for i in range(window):
        d = (start + datetime.timedelta(days=i)).isoformat()
        tg = db.get_day_targets(d)
        if tg and (tg.get("profile_source") or {}).get("weight_kg") in ("Waage", "garmin", "einstellung"):
            weights.append((i, tg["profile"]["weight_kg"]))
        meals = db.meals_between(d, d)
        if meals and tg:
            kcal = sum((it["per100"].get("kcal") or 0) * it["amount_g"] / 100 for m in meals for it in m["items"])
            if kcal >= 0.7 * tg["targets"]["kcal"]:
                intakes.append(kcal)
                targets.append(tg["targets"]["kcal"])
    distinct = {w for _i, w in weights}
    if len(intakes) < 14 or len(weights) < 4 or len(distinct) < 2 or weights[-1][0] - weights[0][0] < 14:
        return {"ready": False, "days_logged": len(intakes), "weights": len(weights),
                "text": "Braucht mind. 14 vollständig erfasste Tage und regelmäßige Gewichtswerte "
                        "(Waage in den Einstellungen wählen)."}
    n = len(weights)
    mx = sum(i for i, _ in weights) / n
    my = sum(w for _, w in weights) / n
    sxx = sum((i - mx) ** 2 for i, _ in weights)
    slope = sum((i - mx) * (w - my) for i, w in weights) / sxx if sxx else 0  # kg/Tag
    avg_in = sum(intakes) / len(intakes)
    tdee = avg_in - slope * KCAL_PER_KG
    avg_target = sum(targets) / len(targets)
    diff = tdee - avg_target
    res = {"ready": True, "days_logged": len(intakes), "weight_change_kg_per_week": round(slope * 7, 2),
           "avg_intake": round(avg_in), "estimated_expenditure": round(tdee), "avg_target": round(avg_target),
           "difference": round(diff)}
    if abs(diff) > 0.08 * avg_target:
        res["suggest_pal"] = True
        res["text"] = (f"Gewichtsverlauf ({res['weight_change_kg_per_week']:+.2f} kg/Woche) und Zufuhr "
                       f"(Ø {res['avg_intake']} kcal) ergeben einen Verbrauch von etwa {res['estimated_expenditure']} kcal "
                       f"– {abs(res['difference'])} kcal {'mehr' if diff > 0 else 'weniger'} als berechnet. "
                       f"Alltagsaktivität in den Einstellungen {'erhöhen' if diff > 0 else 'senken'} oder das Ziel "
                       "anpassen. Schätzung, schwankt mit Wassereinlagerungen.")
    return res
