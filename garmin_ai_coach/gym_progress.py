"""Gewichts-Progression im Gym (seit v0.21.0).

Regelbasiert statt KI-geraten: je (vereinheitlichter, siehe exercise_names.py)
Übung wird aus dem Satzverlauf der letzten Einheiten abgeleitet, ob das
Gewicht beim nächsten Mal erhöht werden soll.

Methode: doppelte Progression innerhalb eines Wiederholungsbereichs
(z. B. 8-12): zuerst die Wiederholungen bis zur Obergrenze steigern, dann das
Gewicht erhöhen und wieder bei der Untergrenze beginnen. Zusätzlich die
„2-für-2“-Regel: Schafft man in zwei Einheiten in Folge in der letzten
Serie 1-2 Wiederholungen mehr als das Ziel, wird das Gewicht erhöht. Das
entspricht der Progressionsempfehlung des ACSM (2009): Laststeigerung um
2-10 %, sobald das Ziel um 1-2 Wiederholungen übertroffen wird.
  Quelle: ACSM Position Stand „Progression Models in Resistance Training for
  Healthy Adults“, Med Sci Sports Exerc 2009, doi:10.1249/MSS.0b013e3181915670

Grenzen (bewusst ehrlich im Dashboard genannt):
- Es gibt keine Garmin-Angabe, wie anstrengend ein Satz war (kein RPE/RIR).
  „Alle Sätze an der Obergrenze“ ist deshalb der einzige Auslöser; wer die
  Obergrenze schafft, hat per Definition noch Reserve.
- Wiederholungsbereiche sind Planungswerte (siehe exercise_names.RULES).
- Mehrere unterschiedliche Geräte hinter demselben Übungsnamen (z. B. zwei
  Latzugmaschinen) werden nicht getrennt.
- Die Erholungs-Schranke (Tagesampel) verschiebt nur den Zeitpunkt, sie ändert
  nie das Zielgewicht.
"""
import math
import datetime

import exercise_names

# Sätze unterhalb dieses Anteils des schwersten Satzes gelten als Aufwärmen.
WARMUP_FRACTION = 0.80
MIN_WORKING_SETS = 2          # für die Regel "alle Sätze an der Obergrenze"
RELEVANT_DAYS = 56            # Übungen, die länger nicht gemacht wurden, fallen raus
BREAK_DAYS = 21               # danach: Wiedereinstieg mit reduziertem Gewicht
RESTART_FACTOR = 0.90
MAX_INCREASE_PCT = 10.0       # ACSM-Obergrenze für einen Schritt
WEIGHT_TOLERANCE = 0.011      # kg-Rundung: 40.0 und 40.01 sind dasselbe Gewicht

STATUS_ORDER = {"erhöhen": 0, "wiedereinstieg": 1, "prüfen": 2, "aufbauen": 3, "basis": 4, "ohne_gewicht": 5}


def _valid_sets(sets):
    out = []
    for s in sets or []:
        reps = s.get("reps")
        w = s.get("weight_kg")
        if not isinstance(reps, (int, float)) or reps <= 0:
            continue
        w = float(w) if isinstance(w, (int, float)) and w > 0 else 0.0
        out.append({"reps": int(reps), "weight": w})
    return out


def working_sets(sets):
    """Arbeitssätze einer Übung in einer Einheit: Sätze mit mindestens 80 % des
    schwersten Gewichts (filtert Aufwärmsätze). Ohne Gewicht (Körpergewicht):
    alle Sätze."""
    valid = _valid_sets(sets)
    if not valid:
        return []
    top = max(s["weight"] for s in valid)
    if top <= 0:
        return valid
    return [s for s in valid if s["weight"] >= top * WARMUP_FRACTION]


def _session_summary(date, sets):
    ws = working_sets(sets)
    if not ws:
        return None
    top = max(s["weight"] for s in ws)
    at_top = [s for s in ws if abs(s["weight"] - top) <= WEIGHT_TOLERANCE] if top > 0 else ws
    reps = [s["reps"] for s in at_top]
    return {"date": date, "weight": top, "reps": reps, "min_reps": min(reps), "max_reps": max(reps),
            "last_reps": reps[-1], "n_sets": len(reps), "all_sets": len(ws)}


def history_by_exercise(sessions):
    """Kanonische Sessions -> {id: {meta, entries:[{date, weight, reps...}] (alt->neu)}}.
    Mehrere Einheiten am selben Tag werden zusammengelegt (Sätze addiert)."""
    per = {}
    for s in sessions or []:
        date = s.get("date")
        if not date:
            continue
        for ex in s.get("exercises") or []:
            if ex.get("id") == "unbekannt":
                continue
            meta = per.setdefault(ex["id"], {"id": ex["id"], "name": ex["exercise"], "group": ex.get("group"),
                                             "garmin_names": [], "assumed": False, "by_day": {}})
            for n in ex.get("garmin_names") or []:
                if n not in meta["garmin_names"]:
                    meta["garmin_names"].append(n)
            meta["assumed"] = meta["assumed"] or bool(ex.get("assumed"))
            meta["by_day"].setdefault(date, []).extend(ex.get("sets") or [])
    out = {}
    for ex_id, meta in per.items():
        entries = []
        for date in sorted(meta["by_day"]):
            summ = _session_summary(date, meta["by_day"][date])
            if summ:
                entries.append(summ)
        if entries:
            out[ex_id] = {"id": ex_id, "name": meta["name"], "group": meta["group"],
                          "garmin_names": meta["garmin_names"], "assumed": meta["assumed"],
                          "entries": entries}
    return out


def _round_to(value, step):
    return round(round(value / step) * step, 2)


def next_weight(weight, step, pct):
    """Nächstes Gewicht: ca. `pct` % mehr, aber mindestens ein Gerätesprung
    `step` und höchstens 10 % (ACSM) - sofern der Sprung nicht kleiner geht.
    Gibt (neues_gewicht, tatsächliche_steigerung_in_prozent) zurück."""
    if weight <= 0:
        return None, None
    inc = max(weight * pct / 100.0, step)
    inc = _round_to(inc, step) or step
    cap = weight * MAX_INCREASE_PCT / 100.0
    if inc > cap and cap >= step:
        inc = math.floor(cap / step) * step
    new = round(weight + inc, 2)
    return new, round(inc / weight * 100.0, 1)


def _fmt_w(w):
    return f"{w:g}".replace(".", ",")


def _fmt_reps(reps):
    return "/".join(str(r) for r in reps)


def evaluate_exercise(rule_info, entries, today=None, recovered=None):
    """Bewertet eine Übung. rule_info: Ergebnis von exercise_names.classify (reps,
    step, pct, compound, bodyweight_reps). entries: alt->neu."""
    today = today or datetime.date.today()
    lo, hi = rule_info["reps"]
    last = entries[-1]
    prev = entries[-2] if len(entries) >= 2 else None
    try:
        days_since = (today - datetime.date.fromisoformat(last["date"])).days
    except ValueError:
        days_since = 0
    res = {
        "last_date": last["date"], "days_since": days_since, "weight": last["weight"],
        "reps": last["reps"], "target": f"{lo}-{hi}", "sessions": len(entries),
        "next_weight": None, "increase_pct": None, "status": "basis", "headline": "", "detail": "",
    }
    weight = last["weight"]

    # Haltübungen (Plank): keine Wiederholungsprogression
    if hi <= 1:
        res.update(status="ohne_gewicht", headline="Haltübung", detail="Keine Wiederholungsprogression - Zeit statt Gewicht steigern.")
        return res

    if weight <= 0:
        # Körpergewichtsübung
        if last["min_reps"] >= hi:
            res.update(status="erhöhen", headline="Zusatzgewicht beginnen",
                       detail=f"Alle Sätze mit {_fmt_reps(last['reps'])} Wdh. (Ziel {lo}-{hi}) - nächstes Mal mit kleinem Zusatzgewicht starten.")
        else:
            res.update(status="aufbauen", headline="Wiederholungen steigern",
                       detail=f"{_fmt_reps(last['reps'])} Wdh. - Ziel: alle Sätze auf {hi}.")
        return res

    # Wiedereinstieg nach längerer Pause
    if days_since > BREAK_DAYS:
        re_w =_round_to(weight * RESTART_FACTOR, rule_info["step"])
        res.update(status="wiedereinstieg", next_weight=re_w,
                   headline=f"Wiedereinstieg mit ca. {_fmt_w(re_w)} kg",
                   detail=f"Letzte Einheit vor {days_since} Tagen mit {_fmt_w(weight)} kg × {_fmt_reps(last['reps'])}. "
                          f"Nach Pause ~10 % weniger ansetzen und in 1-2 Einheiten wieder hocharbeiten (Erfahrungswert, nicht aus Daten abgeleitet).")
        return res

    nw, ipct = next_weight(weight, rule_info["step"], rule_info["pct"])
    same_weight_prev = prev is not None and abs(prev["weight"] - weight) <= WEIGHT_TOLERANCE

    # Regel A: alle Arbeitssätze an der Obergrenze
    rule_a = last["n_sets"] >= MIN_WORKING_SETS and last["min_reps"] >= hi
    # Regel B (2-für-2): letzte Serie in zwei Einheiten in Folge >= Ziel + 1
    rule_b = (same_weight_prev and last["last_reps"] >= hi + 1 and prev["last_reps"] >= hi + 1)
    # Warnsignal: Gewicht gleich/höher, Wiederholungen zweimal unter der Untergrenze
    # Mindestens 2 Wdh. unter der Untergrenze: die Bereiche sind Planungswerte,
    # eine Wiederholung Abstand soll noch keinen Alarm auslösen.
    drop = (prev is not None and last["min_reps"] <= lo - 2 and prev["min_reps"] <= lo - 2
            and last["weight"] >= prev["weight"] - WEIGHT_TOLERANCE)

    if rule_a or rule_b:
        why = (f"alle {last['n_sets']} Arbeitssätze bei {_fmt_reps(last['reps'])} Wdh. (Ziel {lo}-{hi})"
               if rule_a else
               f"letzte Serie in zwei Einheiten in Folge mit {prev['last_reps']} bzw. {last['last_reps']} Wdh. (Ziel {hi})")
        gate = ""
        if recovered is False:
            gate = " Erholung aktuell eingeschränkt: Steigerung erst bei guter Tagesform."
        res.update(status="erhöhen", next_weight=nw, increase_pct=ipct,
                   headline=f"Erhöhen auf {_fmt_w(nw)} kg (+{_fmt_w(ipct)} %)",
                   detail=f"{_fmt_w(weight)} kg: {why}. Danach wieder bei {lo} Wdh. beginnen.{gate}")
        if ipct and ipct > MAX_INCREASE_PCT:
            res["detail"] += (f" Kleinster Sprung ist größer als {MAX_INCREASE_PCT:g} %: erst Zwischenschritt "
                              f"(z. B. Mikroscheiben) oder nur den ersten Satz steigern.")
        return res

    if drop:
        res.update(status="prüfen", headline="Gewicht halten oder senken",
                   detail=f"Zwei Einheiten in Folge mindestens 2 Wdh. unter dem Ziel {lo}-{hi} ({_fmt_reps(prev['reps'])} → {_fmt_reps(last['reps'])}) "
                          f"bei {_fmt_w(weight)} kg. Gewicht nicht erhöhen; bei weiterer Stagnation 5-10 % reduzieren. "
                          f"Erholung und Reihenfolge im Training mitprüfen. Passt der Zielbereich nicht zu deinem Plan, kann er in der Alias-Datei überschrieben werden.")
        return res

    if len(entries) == 1:
        res.update(status="basis", headline=f"Ausgangswert {_fmt_w(weight)} kg",
                   detail=f"{_fmt_reps(last['reps'])} Wdh. - eine Einheit reicht noch nicht für eine Empfehlung. "
                          f"Ziel: alle Sätze auf {hi} Wdh.")
        return res

    left = max(0, hi - last["min_reps"])
    res.update(status="aufbauen", headline=f"Bei {_fmt_w(weight)} kg bleiben",
               detail=f"{_fmt_reps(last['reps'])} Wdh. - noch {left} Wdh. bis zur Obergrenze {hi} im schwächsten Satz. "
                      f"Dann auf {_fmt_w(nw)} kg gehen.")
    res["next_weight"] = nw
    res["increase_pct"] = ipct
    return res


def build_progression(sessions, today=None, recovered=None):
    """sessions: kanonische Sessions (exercise_names.canonical_sessions) über
    mehrere Wochen. Gibt Liste je Übung zurück, 'erhöhen' zuerst."""
    today = today or datetime.date.today()
    hist = history_by_exercise(sessions)
    try:
        import garmin_gym
        plan_ranges = garmin_gym.plan_rep_ranges()
    except Exception as e:
        print(f"[gym_progress] Plan-Zielbereiche nicht lesbar ({e})")
        plan_ranges = {}
    out = []
    for ex_id, h in hist.items():
        entries = h["entries"]
        try:
            age = (today - datetime.date.fromisoformat(entries[-1]["date"])).days
        except ValueError:
            continue
        if age > RELEVANT_DAYS:
            continue
        info = exercise_names.RULES_BY_ID.get(ex_id)
        if info is None:
            info = exercise_names.classify(h["name"])
        info = dict(info)
        if ex_id in plan_ranges:
            info["reps"] = plan_ranges[ex_id]
        custom = exercise_names.user_rep_range(ex_id)
        if custom:
            info["reps"] = custom
        ev = evaluate_exercise(info, entries, today=today, recovered=recovered)
        ev.update({"id": ex_id, "name": h["name"], "group": h["group"],
                   "garmin_names": h["garmin_names"], "assumed": h["assumed"]})
        out.append(ev)
    out.sort(key=lambda e: (STATUS_ORDER.get(e["status"], 9), -(datetime.date.fromisoformat(e["last_date"]).toordinal())))
    return out


def summary_state(prog):
    n_up = sum(1 for e in prog if e["status"] == "erhöhen")
    n_chk = sum(1 for e in prog if e["status"] == "prüfen")
    if not prog:
        return "noch keine Daten"
    parts = [f"{n_up} zum Erhöhen"]
    if n_chk:
        parts.append(f"{n_chk} prüfen")
    return ", ".join(parts)


def prompt_block(prog, limit=8):
    """Kompakter Textblock für den KI-Gym-Tipp: die Regeln haben schon
    entschieden, die KI formuliert nur."""
    lines = []
    for e in prog[:limit]:
        lines.append(f"- {e['name']}: {e['headline']} ({e['detail']})")
    return "\n".join(lines)
