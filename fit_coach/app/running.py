"""Laufen: Aktivitäten normalisieren, Pace-Verlauf, Rekorde, Prognosen, Hinweise.

Für Laufanfänger zählt vor allem Regelmäßigkeit und überwiegend lockeres Laufen:
- In einer randomisierten Studie mit Freizeitläufern verbesserte ein Training
  mit ~77 % locker mindestens so gut wie eines mit viel mittlerer Intensität
  (Muñoz 2014, IJSPP, doi:10.1123/ijspp.2012-0350). Deshalb zeigt das Dashboard den
  lockeren Anteil (Garmin-HF-Zonen 1-2) mit Ziel ≈ 80 %.
- Anfänger, die ihre Wochenkilometer über 2 Wochen um mehr als 30 % steigerten,
  hatten häufiger Überlastungsbeschwerden als bei < 10 % (Nielsen 2014, JOSPT,
  doi:10.2519/jospt.2014.5164; explorativ). Die starre 10-%-Regel selbst hat in
  einer RCT keine Verletzungen verhindert (Buist 2008, AJSM,
  doi:10.1177/0363546507307505) - Hinweis also erst ab +30 %, nicht ab +10 %.
- Fortschritt bei der Pace: „lockere Pace“ (Läufe mit ≥ 70 % Zeit in Zone 1-2)
  und „Meter pro Herzschlag“ (Tempo geteilt durch Puls, steigt mit der Fitness)
  sind aussagekräftiger als die Durchschnittspace aller Läufe, weil Lauf-Geh-
  Intervalle und Steigungen die Durchschnittspace stark schwanken lassen.
"""
import datetime

RUN_KEYS = ("run",)            # running, treadmill_running, trail_running, track_running ...
WALK_KEYS = ("walk", "hik")
STRENGTH_KEYS = ("strength", "weight", "gym", "hiit", "pilates")
EASY_SHARE_MIN = 0.70          # ab hier gilt ein Lauf als „locker“
PR_TYPES = {1: ("1 km", "time"), 2: ("1 Meile", "time"), 3: ("5 km", "time"), 4: ("10 km", "time"),
            5: ("Halbmarathon", "time"), 6: ("Marathon", "time"), 7: ("Längster Lauf", "distance")}


def _d(s):
    return datetime.date.fromisoformat(str(s)[:10])


def _de(x, digits=1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def monday(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def kind_of(type_key: str) -> str:
    t = (type_key or "").lower()
    if any(k in t for k in RUN_KEYS):
        return "run"
    if any(k in t for k in STRENGTH_KEYS):
        return "strength"
    if any(k in t for k in WALK_KEYS):
        return "walk"
    return "other"


def normalize_activity(act: dict) -> dict:
    """Garmin-Aktivität (Liste von get_activities) -> kompakter Eintrag."""
    type_key = ((act.get("activityType") or {}).get("typeKey") or "").lower()
    start = act.get("startTimeLocal") or ""
    dist_km = round((act.get("distance") or 0) / 1000.0, 2)
    dur = float(act.get("movingDuration") or act.get("duration") or 0)
    elapsed = float(act.get("duration") or dur)
    zones = [float(act.get(f"hrTimeInZone_{i}") or 0) for i in range(1, 6)]
    ztot = sum(zones)
    avg_hr = act.get("averageHR")
    speed = (dist_km * 1000 / dur) if dur > 0 else None  # m/s
    out = {
        "id": act.get("activityId"),
        "date": start[:10],
        "start": start[:16],
        "name": act.get("activityName") or "",
        "type": type_key,
        "kind": kind_of(type_key),
        "km": dist_km,
        "sec": round(dur),
        "elapsed": round(elapsed),
        "pace": round(dur / dist_km) if dist_km >= 0.2 and dur > 0 else None,  # s/km
        "hr": round(avg_hr) if isinstance(avg_hr, (int, float)) else None,
        "hr_max": act.get("maxHR"),
        "kcal": round(act.get("calories") or 0),
        "elev": round(act.get("elevationGain") or 0),
        "easy": round((zones[0] + zones[1]) / ztot, 2) if ztot > 0 else None,
        "zones_min": [round(z / 60, 1) for z in zones] if ztot > 0 else None,
        "m_per_beat": round(speed * 60 / avg_hr, 2) if speed and isinstance(avg_hr, (int, float)) and avg_hr > 60 else None,
    }
    return out


def _weeks_back(today: datetime.date, n: int):
    m = monday(today)
    return [m - datetime.timedelta(weeks=i) for i in range(n - 1, -1, -1)]


def weekly_km(runs: list, today: datetime.date, n: int = 12) -> list:
    weeks = _weeks_back(today, n)
    out = []
    for w in weeks:
        rs = [r for r in runs if w <= _d(r["date"]) < w + datetime.timedelta(days=7)]
        out.append({"w": w.isoformat(), "km": round(sum(r["km"] for r in rs), 1), "n": len(rs),
                    "min": round(sum(r["sec"] for r in rs) / 60)})
    return out


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2


def easy_pace_trend(runs: list, today: datetime.date) -> dict:
    """Median-Pace lockerer Läufe: letzte 4 Wochen vs. die 4 Wochen davor."""
    easy = [r for r in runs if r.get("pace") and r.get("easy") is not None and r["easy"] >= EASY_SHARE_MIN and r["km"] >= 1.0]
    now = [r["pace"] for r in easy if (today - _d(r["date"])).days < 28]
    before = [r["pace"] for r in easy if 28 <= (today - _d(r["date"])).days < 56]
    m_now, m_before = _median(now), _median(before)
    eff_now = _median([r["m_per_beat"] for r in runs if r.get("m_per_beat") and (today - _d(r["date"])).days < 28])
    eff_before = _median([r["m_per_beat"] for r in runs if r.get("m_per_beat") and 28 <= (today - _d(r["date"])).days < 56])
    return {
        "easy_pace": round(m_now) if m_now else None,
        "easy_pace_before": round(m_before) if m_before else None,
        "easy_pace_delta": round(m_now - m_before) if m_now and m_before else None,  # negativ = schneller
        "easy_runs_4w": len(now),
        "m_per_beat": round(eff_now, 2) if eff_now else None,
        "m_per_beat_before": round(eff_before, 2) if eff_before else None,
        "points": [{"d": r["date"], "p": r["pace"], "e": r.get("m_per_beat")} for r in easy[-20:]],
    }


def parse_prs(raw) -> list:
    """Garmin get_personal_record() -> Laufrekorde (typeId 1-7)."""
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        if (r.get("activityType") or "running") != "running":
            continue
        tid = r.get("typeId")
        if tid not in PR_TYPES:
            continue
        label, kind = PR_TYPES[tid]
        val = r.get("value")
        if not isinstance(val, (int, float)) or val <= 0:
            continue
        date = (r.get("prStartTimeLocalFormatted") or r.get("actStartDateTimeInGMTFormatted")
                or r.get("prStartTimeGmtFormatted") or "")
        if not date and r.get("prStartTimeGmt"):
            try:
                date = datetime.datetime.utcfromtimestamp(r["prStartTimeGmt"] / 1000).isoformat()
            except Exception:
                date = ""
        out.append({"type": tid, "label": label, "kind": kind,
                    "value": round(val, 1), "date": str(date)[:10], "activity_id": r.get("activityId")})
    out.sort(key=lambda x: x["type"])
    return out


def prs_from_activities(runs: list) -> list:
    """Rückfall, falls Garmins Rekord-Schnittstelle nichts liefert: längster Lauf
    und schnellster Durchschnitt bei Läufen ≥ 5 km (keine Bestzeit-Abschnitte)."""
    out = []
    if runs:
        longest = max(runs, key=lambda r: r["km"])
        out.append({"type": 7, "label": "Längster Lauf", "kind": "distance", "value": longest["km"] * 1000,
                    "date": longest["date"], "activity_id": longest["id"], "estimated": True})
        five = [r for r in runs if r["km"] >= 5 and r.get("pace")]
        if five:
            best = min(five, key=lambda r: r["pace"])
            out.append({"type": 3, "label": "5 km", "kind": "time", "value": best["pace"] * 5,
                        "date": best["date"], "activity_id": best["id"], "estimated": True})
    return sorted(out, key=lambda x: x["type"])


def parse_predictions(raw) -> dict:
    if isinstance(raw, list):
        raw = raw[-1] if raw else {}
    raw = raw or {}
    out = {}
    for k, label in (("time5K", "5k"), ("time10K", "10k"), ("timeHalfMarathon", "hm"), ("timeMarathon", "m")):
        v = raw.get(k)
        if isinstance(v, (int, float)) and v > 0:
            out[label] = round(v)
    if raw.get("calendarDate"):
        out["date"] = str(raw["calendarDate"])[:10]
    return out


def parse_prediction_history(raw) -> dict:
    """Tägliche Prognosen (get_race_predictions(start, end, 'daily')) -> {date: s(5 km)}."""
    hist = {}
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        d = str(r.get("calendarDate") or r.get("fromCalendarDate") or "")[:10]
        v = r.get("time5K")
        if d and isinstance(v, (int, float)) and v > 0:
            hist[d] = round(v)
    return hist


def parse_vo2max(raw):
    """maxmet latest/daily -> Wert oder None."""
    items = raw if isinstance(raw, list) else [raw]
    best = None
    for it in items or []:
        g = (it or {}).get("generic") or {}
        v = g.get("vo2MaxPreciseValue") or g.get("vo2MaxValue")
        if isinstance(v, (int, float)) and v > 0:
            best = round(float(v), 1)
    return best


def guardrails(runs: list, today: datetime.date) -> list:
    hints = []
    wk = weekly_km(runs, today, 3)
    this_km = wk[-1]["km"]
    base = (wk[0]["km"] + wk[1]["km"]) / 2
    if base >= 3 and this_km > base * 1.3 and this_km - base >= 2:
        hints.append({"kind": "warn", "id": "volume_jump",
                      "text": f"Diese Woche {_de(this_km)} km statt Ø {_de(base)} km (+{round((this_km / base - 1) * 100)} %). "
                              "Bei Laufanfängern hingen Sprünge über 30 % mit mehr Überlastungsbeschwerden zusammen – "
                              "den nächsten Lauf lieber kurz und locker halten."})
    recent = [r for r in runs if (today - _d(r["date"])).days < 14 and r.get("zones_min")]
    tot = sum(sum(r["zones_min"]) for r in recent)
    easy = sum(r["zones_min"][0] + r["zones_min"][1] for r in recent)
    share = round(easy / tot * 100) if tot >= 30 else None
    if share is not None and share < 60 and len(recent) >= 2:
        hints.append({"kind": "info", "id": "too_hard",
                      "text": f"Nur {share} % der Laufzeit in Zone 1–2. Langsamer laufen fühlt sich falsch an, macht aber schneller: "
                              "Sprechtempo, Gehpausen sind erlaubt."})
    last_two = sorted({r["date"] for r in runs if (today - _d(r["date"])).days <= 1})
    if len(last_two) == 2:
        hints.append({"kind": "info", "id": "back_to_back",
                      "text": "Gestern und heute gelaufen – als Einsteigerin zwischen Läufen besser einen Tag Pause oder Gehen/Radfahren einplanen."})
    return hints, share


def next_run(runs: list, today: datetime.date, target_per_week: int, planned=None) -> dict:
    """Vorschlag für den nächsten Lauf. Ein geplantes Garmin-Workout (z. B. aus
    Garmin Coach) hat immer Vorrang - die adaptiven Garmin-Pläne passen sich an."""
    if planned:
        return {"source": "garmin", **planned}
    week_runs = [r for r in runs if _d(r["date"]) >= monday(today)]
    ran_today = any(_d(r["date"]) == today for r in runs)
    ran_yesterday = any(_d(r["date"]) == today - datetime.timedelta(days=1) for r in runs)
    total = len(runs)
    if ran_today:
        return {"source": "regel", "title": "Heute schon gelaufen", "detail": "Erholung gehört zum Training. Gehen oder Dehnen ist ideal."}
    if len(week_runs) >= target_per_week:
        return {"source": "regel", "title": "Wochenziel erreicht", "detail": "Ein zusätzlicher Lauf ist optional – gern ganz locker oder ein Spaziergang."}
    if ran_yesterday:
        return {"source": "regel", "title": "Morgen wieder laufen", "detail": "Nach einem Lauftag ist heute ein guter Tag für Pause, Gehen oder Gym."}
    if total < 6:
        return {"source": "regel", "title": "Lauf-Geh-Einheit, 20–30 min",
                "detail": "Abwechselnd 1–2 min locker laufen und 1–2 min gehen. So locker, dass Reden geht."}
    recent = [r for r in runs if (today - _d(r["date"])).days < 21]
    longest = max((r["sec"] for r in recent), default=0) / 60
    typical = _median([r["sec"] / 60 for r in recent]) or 20
    weekend = today.weekday() >= 5
    if weekend and longest > 0:
        dur = min(round(longest * 1.1 / 5) * 5, round(typical * 1.5 / 5) * 5) or 25
        return {"source": "regel", "title": f"Etwas längerer Lauf, ~{int(dur)} min",
                "detail": "Ruhig im Sprechtempo, Gehpausen sind ok. Höchstens etwa 10 % länger als zuletzt."}
    dur = max(20, round(typical / 5) * 5)
    return {"source": "regel", "title": f"Lockerer Lauf, ~{int(dur)} min",
            "detail": "Sprechtempo (Zone 1–2). Lockeres Laufen macht auf Dauer schneller."}


def analyze(acts: list, today: datetime.date, target_per_week: int, prs=None, predictions=None,
            pred_hist=None, vo2max=None, vo2_hist=None, planned=None) -> dict:
    runs = sorted([a for a in acts if a.get("kind") == "run" and a.get("km", 0) > 0], key=lambda r: r["start"])
    weeks = weekly_km(runs, today, 12)
    pace = easy_pace_trend(runs, today)
    hints, easy_share = guardrails(runs, today)
    prs_list = prs if prs else prs_from_activities(runs)
    week_runs = [r for r in runs if _d(r["date"]) >= monday(today)]
    total_km = round(sum(r["km"] for r in runs), 1)
    return {
        "has_data": bool(runs),
        "week_runs": len(week_runs),
        "week_km": round(sum(r["km"] for r in week_runs), 1),
        "target_per_week": target_per_week,
        "total_runs": len(runs),
        "total_km": total_km,
        "weeks": weeks,
        "recent": [{k: r[k] for k in ("date", "name", "km", "sec", "pace", "hr", "easy", "id")} for r in reversed(runs[-15:])],
        "pace": pace,
        "easy_share_14d": easy_share,
        "prs": prs_list,
        "predictions": predictions or {},
        "prediction_history": [{"d": d, "s": s} for d, s in sorted((pred_hist or {}).items())][-90:],
        "vo2max": vo2max,
        "vo2_history": [{"d": d, "v": v} for d, v in sorted((vo2_hist or {}).items())][-90:],
        "hints": hints,
        "next": next_run(runs, today, target_per_week, planned),
        "last_run": runs[-1] if runs else None,
    }
