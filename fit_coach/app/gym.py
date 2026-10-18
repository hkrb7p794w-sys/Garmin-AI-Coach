"""Gym: Rekorde je Übung aus Garmin-Krafteinheiten und eigenen Einträgen.

Rekord = höchstes geschätztes 1-Wiederholungs-Maximum (e1RM, Epley:
Gewicht × (1 + Wdh./30)). e1RM-Formeln werden mit steigender
Wiederholungszahl ungenauer; über 12 Wiederholungen wird deshalb kein e1RM
gebildet, der Satz zählt dann nur als „meiste Wiederholungen“ bei dem Gewicht.
Der Wert ist für den eigenen Verlauf gedacht, nicht als echtes Maximum - ein
echter 1-RM-Test ist für Einsteigerinnen nicht nötig.

Warum Krafttraining beim Abnehmen: Es hilft, Muskelmasse während einer
Kaloriendefizit-Phase zu erhalten und verbessert die Kraft (Cava 2017,
Adv Nutr, doi:10.3945/an.116.014506; Meta-Analyse bei älteren Erwachsenen:
Sardeli 2018, Nutrients, doi:10.3390/nu10040423).

Steigerungshinweise kommen aus gym_progress.py (gleiche Regeln wie im
Garmin AI Coach: doppelte Progression, ACSM 2009).
"""
import datetime
import uuid

import exercise_names
import gym_progress

E1RM_MAX_REPS = 12

# Einsteiger-Wiederholungsbereiche: ACSM 2009 empfiehlt Anfängern Lasten im
# Bereich 8-12 Wiederholungen (Isolation/Rumpf etwas höher, 10-15). Die Regeln in
# exercise_names.py stammen aus dem Garmin AI Coach (fortgeschritten, 6-10 bei
# Grundübungen) - für die Fit-Coach-Kopie hier einmalig umgestellt.
for _r in exercise_names.RULES:
    if _r["reps"][1] <= 1:
        continue
    _r["reps"] = (8, 12) if _r["compound"] else (10, 15)

# Auswahl für die eigene Rekord-Eingabe (Heim-Gym-typisch), ergänzt um alles,
# was in den Garmin-Daten vorkommt.
DEFAULT_EXERCISES = [
    "kniebeuge", "rumaenisches_kreuzheben", "kreuzheben", "hueftstoss", "ausfallschritt",
    "kurzhantel_bankdruecken", "bankdruecken", "liegestuetze", "kurzhantel_schulterdruecken",
    "schulterdruecken", "rudern_kurzhantel", "latziehen", "klimmzug", "seitheben",
    "kurzhantel_curl", "bizeps_curl", "trizepsstrecken", "wadenheben", "beinpresse",
]


def epley(weight, reps):
    if not weight or not reps or reps <= 0:
        return None
    if reps > E1RM_MAX_REPS:
        return None
    return round(weight * (1 + reps / 30.0), 1) if reps > 1 else round(float(weight), 1)


def exercise_options(seen_ids=()) -> list:
    ids = list(DEFAULT_EXERCISES)
    for i in seen_ids:
        if i and i not in ids and i != "unbekannt":
            ids.append(i)
    names = []
    for i in ids:
        rule = exercise_names.RULES_BY_ID.get(i)
        names.append(rule["name"] if rule else i)
    return sorted(set(names), key=lambda s: s.lower())


def id_for_name(name: str) -> str:
    for r in exercise_names.RULES:
        if r["name"] == name:
            return r["id"]
    return exercise_names._slug(name)


def _sets_from_sessions(sessions):
    """Kanonische Garmin-Sessions -> flache Satzliste."""
    for s in sessions or []:
        for ex in s.get("exercises") or []:
            if ex.get("id") == "unbekannt":
                continue
            for st in ex.get("sets") or []:
                reps = st.get("reps")
                w = st.get("weight_kg")
                if not isinstance(reps, (int, float)) or reps <= 0:
                    continue
                yield {"date": s.get("date"), "id": ex["id"], "name": ex["exercise"], "group": ex.get("group"),
                       "kg": float(w) if isinstance(w, (int, float)) and w > 0 else 0.0, "reps": int(reps),
                       "source": "garmin"}


def _manual_sets(manual):
    for m in manual or []:
        yield {"date": m["date"], "id": m["id"], "name": m["name"], "group": m.get("group"),
               "kg": float(m.get("kg") or 0), "reps": int(m.get("reps") or 0), "source": "manuell",
               "entry_id": m.get("entry_id")}


def records(sessions, manual, today: datetime.date = None) -> list:
    """Bester Satz je Übung (nach e1RM, sonst nach Wiederholungen bei Körpergewicht)."""
    today = today or datetime.date.today()
    by_ex = {}
    for st in sorted(list(_sets_from_sessions(sessions)) + list(_manual_sets(manual)), key=lambda x: str(x["date"])):
        e = by_ex.setdefault(st["id"], {"id": st["id"], "name": st["name"], "group": st.get("group"),
                                        "best": None, "history": [], "sessions": set(), "first_date": st["date"]})
        e["sessions"].add(st["date"])
        score = epley(st["kg"], st["reps"]) if st["kg"] > 0 else None
        cand = {"date": st["date"], "kg": st["kg"], "reps": st["reps"], "e1rm": score, "source": st["source"]}
        b = e["best"]
        better = False
        if b is None:
            better = True
        elif score is not None and (b["e1rm"] is None or score > b["e1rm"] + 0.05):
            better = True
        elif score is None and b["e1rm"] is None and st["kg"] == 0 and st["reps"] > b["reps"]:
            better = True
        if better:
            if b is not None:
                e["history"].append(b)
            e["best"] = cand
    out = []
    for ex_id, e in by_ex.items():
        b = e["best"]
        prev = e["history"][-1] if e["history"] else None
        gain = None
        if prev and prev.get("e1rm") and b.get("e1rm"):
            gain = round((b["e1rm"] / prev["e1rm"] - 1) * 100)
        days = (today - datetime.date.fromisoformat(str(b["date"])[:10])).days if b.get("date") else None
        out.append({"id": ex_id, "name": e["name"], "group": e["group"], "kg": b["kg"], "reps": b["reps"],
                    "e1rm": b["e1rm"], "date": b["date"], "source": b["source"], "days_ago": days,
                    "new": days is not None and days <= 7 and bool(e["history"]),
                    "improvements": len(e["history"]), "gain_pct": gain,
                    "sessions": len(e["sessions"]), "first_date": e["first_date"]})
    out.sort(key=lambda r: (r["days_ago"] if r["days_ago"] is not None else 9999, r["name"]))
    return out


def count_prs(recs) -> int:
    """Wie viele Verbesserungen insgesamt (für Abzeichen)."""
    return sum(r["improvements"] for r in recs)


def manual_entry(name: str, kg: float, reps: int, day: datetime.date = None) -> dict:
    ex_id = id_for_name(name)
    rule = exercise_names.RULES_BY_ID.get(ex_id) or {}
    return {"entry_id": uuid.uuid4().hex[:8], "date": (day or datetime.date.today()).isoformat(),
            "id": ex_id, "name": rule.get("name", name), "group": rule.get("group", "Sonstige"),
            "kg": round(float(kg), 2), "reps": int(reps)}


def analyze(sessions, manual, strength_acts, today: datetime.date, target_per_week: int) -> dict:
    canon = exercise_names.canonical_sessions(sessions)
    recs = records(canon, manual, today)
    prog = gym_progress.build_progression(canon, today)
    monday = today - datetime.timedelta(days=today.weekday())
    month = today.replace(day=1)
    acts = sorted(strength_acts or [], key=lambda a: a.get("start") or "")
    week_n = sum(1 for a in acts if a["date"] >= monday.isoformat())
    month_n = sum(1 for a in acts if a["date"] >= month.isoformat())
    last = acts[-1] if acts else None
    return {
        "has_data": bool(recs or acts),
        "records": recs[:40],
        "progression": [{k: e[k] for k in ("id", "name", "status", "headline", "detail", "weight", "reps", "next_weight", "last_date")}
                        for e in prog if e["status"] in ("erhöhen", "wiedereinstieg", "prüfen", "aufbauen", "basis")][:12],
        "sessions_week": week_n,
        "sessions_month": month_n,
        "sessions_total": len(acts),
        "target_per_week": target_per_week,
        "last_session": {"date": last["date"], "name": last.get("name"), "min": round(last["sec"] / 60)} if last else None,
        "pr_count": count_prs(recs),
        "manual_count": len(manual or []),
        "missing_sets_hint": bool(acts) and not canon,
        "seen_ids": sorted({r["id"] for r in recs}),
    }
