"""Tages- und Wochenauswertung (auch Grundlage für Home Assistant / Phase 2)."""
import datetime

import db
import garmin_bridge
import nutrients as N
import targets as T


def settings_bundle() -> dict:
    keys = ("profile", "pal_base", "goal", "goal_adjust_pct", "protein_g_per_kg", "carbs_g_per_kg",
            "target_overrides", "day_type_override")
    return {k: db.get_setting(k) for k in keys}


def targets_for(date: str) -> dict:
    today = datetime.date.today().isoformat()
    if date == today:
        res = T.compute(settings_bundle(), garmin_bridge.training_today(), date)
        db.save_day_targets(date, res)
        return res
    stored = db.get_day_targets(date)
    if stored:
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
        "categories": {c: {"label": db.CATEGORY_LABELS[c], "kcal": round(v["kcal"]), "meals": v["meals"]}
                       for c, v in by_cat.items()},
    }


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
    for i in range(days):
        d = (start + datetime.timedelta(days=i)).isoformat()
        ds = day(d)
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
    return {
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
    }
