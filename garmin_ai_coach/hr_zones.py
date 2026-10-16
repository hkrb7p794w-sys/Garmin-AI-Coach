"""Herzfrequenzzonen (seit v0.21.0).

Zwei Sichten nebeneinander, bewusst nicht vermischt:

1. „Uhr“ - die Zonen, die auf der Forerunner eingestellt sind, direkt aus
   Garmin Connect (/biometric-service/heartRateZones). Nur lesen, nichts
   ändern. Das sind die Zonen, nach denen die Uhr „Zeit in Zone“ zählt.

2. „Coach“ - schwellenbasierte Zonen, aus deinen eigenen Daten berechnet und
   bei jedem Sync nachgezogen:
   - Anker ist die Laktatschwellen-HF (LTHR), nicht die Maximal-HF. Die
     Schwelle trennt die Intensitätsbereiche physiologisch sinnvoller als ein
     Prozentsatz der HFmax (Seiler/Esteve-Lanao: Zonen nach Ventilations-/
     Laktatschwellen; Esteve-Lanao 2007, doi:10.1519/R-19725.1).
   - Zonenbreiten nach Friel (Triathlete's Training Bible) in % der LTHR,
     getrennt für Laufen und Rad. Das ist eine verbreitete Praxisvorgabe,
     keine Laborwahrheit - im Dashboard so gekennzeichnet.
   - LTHR-Quelle in dieser Reihenfolge: eigener Wert (HA-Helfer
     input_number.coach_lthr_lauf / _rad) > von Garmin ermittelte
     Laktatschwelle > Schätzung 90 % der HFmax (deutlich als Schätzung
     markiert).
   - HFmax: eigener Wert (input_number.coach_hfmax) > höchster bestätigter
     Messwert der letzten 12 Monate > Garmin-Einstellung. „Bestätigt“ heißt:
     eine zweite Einheit liegt höchstens 3 Schläge darunter. Das filtert die
     typischen Ausreißer des optischen Pulsmessers (Kadenz-Lock, Kälte) aus.
     Altersformeln weichen im Einzelfall um ±11 Schläge ab (Nes 2013,
     doi:10.1111/j.1600-0838.2012.01445.x) und werden deshalb nicht benutzt.

3. Verteilung: Zeit in den Garmin-Zonen der letzten 4 Wochen, getrennt nach
   Laufen/Rad, mit Anteil „locker“ (Z1-2) / „mittel“ (Z3) / „hart“ (Z4-5).
   Richtwert aus der Trainingsforschung: ca. 80 % locker (Seiler; Muñoz 2014,
   doi:10.1123/ijspp.2012-0350). Der optische Sensor unterschätzt bei
   intensiven Einheiten die Zeit in hohen Zonen (Neudorfer 2024,
   doi:10.1111/sms.14756) - der „hart“-Anteil ist daher eher eine Untergrenze.

Alle Garmin-Feldnamen werden defensiv gelesen (siehe _find*). Die rohe
Antwort steht gekürzt als Attribut `garmin_raw`, damit Feldnamen nach dem
ersten echten Sync verifiziert werden können.
"""
import os
import re
import json
import math
import datetime

import requests

DATA_DIR = "/data"
STATE_FILE = os.path.join(DATA_DIR, "hr_zones_state.json")
SUPERVISOR_STATES = "http://supervisor/core/api/states/"
OVERRIDE_ENTITIES = {
    "hrmax": "input_number.coach_hfmax",
    "lthr_run": "input_number.coach_lthr_lauf",
    "lthr_bike": "input_number.coach_lthr_rad",
}
OBS_KEEP_DAYS = 365
HISTORY_KEEP = 60
CONFIRM_TOLERANCE = 3        # bpm
HRMAX_MIN, HRMAX_MAX = 140, 230
LTHR_FACTOR_ESTIMATE = 0.90  # nur Notbehelf
LTHR_RATIO_BAND = (0.80, 0.97)

# (Name, Verwendung, Untergrenze %LTHR, Obergrenze %LTHR)  - Friel
FRIEL = {
    "run": [
        ("Z1", "Erholung", None, 85),
        ("Z2", "Grundlagenausdauer", 85, 89),
        ("Z3", "Tempo", 90, 94),
        ("Z4", "Unterschwelle", 95, 99),
        ("Z5a", "Schwelle", 100, 102),
        ("Z5b", "VO₂max", 103, 106),
        ("Z5c", "Anaerob", 106, None),
    ],
    "bike": [
        ("Z1", "Erholung", None, 81),
        ("Z2", "Grundlagenausdauer", 81, 89),
        ("Z3", "Tempo", 90, 93),
        ("Z4", "Unterschwelle", 94, 99),
        ("Z5a", "Schwelle", 100, 102),
        ("Z5b", "VO₂max", 103, 106),
        ("Z5c", "Anaerob", 106, None),
    ],
}

RUN_TYPES = ("running", "trail_running", "treadmill_running", "track_running")
BIKE_TYPES = ("cycling", "road_biking", "indoor_cycling", "virtual_ride", "mountain_biking",
              "gravel_cycling", "e_bike", "bmx", "cyclocross")


# ---------------------------------------------------------------------------
# kleine Helfer
# ---------------------------------------------------------------------------

def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[hr_zones] Zustand nicht speicherbar: {e}")


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _norm_key(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _find_key(d, *needles, exclude=()):
    """Erster Wert, dessen normalisierter Schlüssel alle `needles` enthält."""
    for k, v in (d or {}).items():
        nk = _norm_key(k)
        if all(n in nk for n in needles) and not any(x in nk for x in exclude):
            n = _num(v)
            if n is not None:
                return n
    return None


def read_overrides():
    """Eigene Werte aus HA-Helfern (0 / unbekannt = nicht gesetzt)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    out = {}
    if not token:
        return out
    for key, entity in OVERRIDE_ENTITIES.items():
        try:
            r = requests.get(SUPERVISOR_STATES + entity, headers={"Authorization": f"Bearer {token}"}, timeout=8)
            if r.status_code != 200:
                continue
            v = _num(r.json().get("state"))
            if v and v >= 40:
                out[key] = int(round(v))
        except Exception as e:
            print(f"[hr_zones] Override {entity} nicht lesbar: {e}")
    return out


# ---------------------------------------------------------------------------
# Garmin-Daten
# ---------------------------------------------------------------------------

def fetch_garmin(client):
    """(zones_raw, lactate_raw) - beides optional, Fehler werden geschluckt."""
    zones_raw = lt_raw = None
    try:
        fn = getattr(client, "get_heart_rate_zones", None)
        if callable(fn):
            zones_raw = fn()
        else:
            zones_raw = client.connectapi("/biometric-service/heartRateZones")
    except Exception as e:
        print(f"[hr_zones] heartRateZones nicht abrufbar: {e}")
    try:
        lt_raw = client.get_lactate_threshold(latest=True)
    except Exception as e:
        print(f"[hr_zones] Laktatschwelle nicht abrufbar: {e}")
    return zones_raw, lt_raw


def parse_garmin_zones(raw):
    """-> [{sport, method, max_hr, rest_hr, lthr, zones:[{n, low, high}]}]"""
    entries = raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        floors = {}
        for k, v in e.items():
            m = re.fullmatch(r"zone(\d)floor", _norm_key(k))
            if m and _num(v) is not None:
                floors[int(m.group(1))] = int(_num(v))
        if len(floors) < 5:
            continue
        max_hr = _find_key(e, "max", "hr") or _find_key(e, "maxheartrate")
        rest_hr = _find_key(e, "rest", "h")
        lthr = _find_key(e, "lactate", "h")
        zones = []
        for n in range(1, 6):
            low = floors[n]
            high = floors[n + 1] - 1 if n < 5 else (int(max_hr) if max_hr else None)
            zones.append({"n": n, "low": low, "high": high})
        out.append({
            "sport": str(e.get("sport") or "DEFAULT"),
            "method": str(e.get("trainingMethod") or e.get("method") or ""),
            "max_hr": int(max_hr) if max_hr else None,
            "rest_hr": int(rest_hr) if rest_hr else None,
            "lthr": int(lthr) if lthr else None,
            "zones": zones,
        })
    return out


def parse_lactate(raw):
    """-> {"run": bpm|None, "bike": bpm|None}"""
    res = {"run": None, "bike": None}
    d = (raw or {}).get("speed_and_heart_rate") if isinstance(raw, dict) else None
    if not isinstance(d, dict):
        d = raw if isinstance(raw, dict) else {}
    for key, target in (("heartRate", "run"), ("hearRate", "run"), ("heartRateCycling", "bike")):
        v = _num(d.get(key))
        if v and 80 <= v <= 220 and res[target] is None:
            res[target] = int(round(v))
    return res


# ---------------------------------------------------------------------------
# HFmax aus eigenen Messwerten
# ---------------------------------------------------------------------------

def _sport_group(act):
    t = ((act.get("activityType") or {}).get("typeKey", "") or "").lower()
    if t in RUN_TYPES or "running" in t:
        return "run"
    if t in BIKE_TYPES or "cycling" in t or "biking" in t or "ride" in t:
        return "bike"
    return None


def update_observed_max(state, activities, today):
    """Pflegt die laufende Liste der Höchstwerte (Läufe/Rad; Schwimmen und Kraft
    haben unzuverlässigen optischen Puls) und gibt den bestätigten Höchstwert zurück."""
    obs = {str(o["id"]): o for o in state.get("hrmax_obs", []) if isinstance(o, dict) and "id" in o}
    for a in activities or []:
        if _sport_group(a) is None:
            continue
        v = _num(a.get("maxHR"))
        aid = a.get("activityId")
        start = (a.get("startTimeLocal") or "")[:10]
        if v is None or aid is None or not start or not (HRMAX_MIN <= v <= HRMAX_MAX):
            continue
        obs[str(aid)] = {"id": aid, "date": start, "value": int(v)}
    cutoff = (today - datetime.timedelta(days=OBS_KEEP_DAYS)).isoformat()
    lst = sorted((o for o in obs.values() if o["date"] >= cutoff), key=lambda o: o["value"], reverse=True)
    state["hrmax_obs"] = lst
    confirmed = None
    for i, o in enumerate(lst):
        if any(o["value"] - p["value"] <= CONFIRM_TOLERANCE for p in lst[i + 1:i + 2]):
            confirmed = o
            break
    peak = lst[0] if lst else None
    return {
        "confirmed": confirmed["value"] if confirmed else None,
        "confirmed_date": confirmed["date"] if confirmed else None,
        "peak": peak["value"] if peak else None,
        "peak_date": peak["date"] if peak else None,
        "n": len(lst),
    }


# ---------------------------------------------------------------------------
# Zonen berechnen
# ---------------------------------------------------------------------------

def friel_zones(lthr, sport, hrmax=None):
    rows = []
    for name, use, lo_pct, hi_pct in FRIEL[sport]:
        lo = None if lo_pct is None else int(math.ceil(lthr * lo_pct / 100.0 - 1e-9))
        hi = None if hi_pct is None else int(math.floor(lthr * hi_pct / 100.0 + 1e-9))
        # Zonen schließen lückenlos an: Obergrenze = nächste Untergrenze - 1
        if lo_pct is None:
            pct = f"<{hi_pct} %"
        elif hi_pct is None:
            pct = f">{lo_pct} %"
        else:
            pct = f"{lo_pct}-{hi_pct} %"
        rows.append({"zone": name, "use": use, "low": lo, "high": hi, "pct": pct})
    for i in range(len(rows) - 1):
        if rows[i + 1]["low"] is not None:
            rows[i]["high"] = rows[i + 1]["low"] - 1
    if hrmax:
        rows[-1]["high"] = int(hrmax)
    return rows


def choose_hrmax(overrides, observed, garmin_entries):
    garmin_max = next((g["max_hr"] for g in garmin_entries if g.get("max_hr")), None)
    if overrides.get("hrmax"):
        return overrides["hrmax"], "eigener Wert"
    cands = [(v, s) for v, s in ((observed.get("confirmed"), "bestätigter Messwert (12 Monate)"),
                                 (garmin_max, "Garmin-Einstellung")) if v]
    if cands:
        return max(cands, key=lambda c: c[0])
    if observed.get("peak"):
        return observed["peak"], "unbestätigter Höchstwert"
    return None, "unbekannt"


def choose_lthr(sport, overrides, garmin_lt, hrmax):
    key = "lthr_run" if sport == "run" else "lthr_bike"
    if overrides.get(key):
        return overrides[key], "eigener Wert", False
    if garmin_lt.get(sport):
        return garmin_lt[sport], "Garmin (Laktatschwelle)", False
    if sport == "bike" and overrides.get("lthr_run") is None and garmin_lt.get("run"):
        return garmin_lt["run"], "Garmin Laufwert als Näherung", True
    if sport == "bike" and overrides.get("lthr_run"):
        return overrides["lthr_run"], "eigener Laufwert als Näherung", True
    if hrmax:
        return int(round(hrmax * LTHR_FACTOR_ESTIMATE)), f"Schätzung ({int(LTHR_FACTOR_ESTIMATE * 100)} % HFmax)", True
    return None, "unbekannt", True


# ---------------------------------------------------------------------------
# Verteilung
# ---------------------------------------------------------------------------

def zone_seconds(act):
    vals = []
    for i in range(1, 6):
        v = _num(act.get(f"hrTimeInZone_{i}"))
        if v is None:
            return None
        vals.append(v)
    return vals if sum(vals) > 0 else None


def distribution(activities, today, weeks=4):
    start = today - datetime.timedelta(days=weeks * 7)
    acc = {"run": [0.0] * 5, "bike": [0.0] * 5}
    per_week = {}
    counted = {"run": 0, "bike": 0}
    missing = 0
    for a in activities or []:
        g = _sport_group(a)
        if g is None:
            continue
        try:
            day = datetime.date.fromisoformat((a.get("startTimeLocal") or "")[:10])
        except ValueError:
            continue
        if day < start:
            continue
        z = zone_seconds(a)
        if z is None:
            missing += 1
            continue
        counted[g] += 1
        for i in range(5):
            acc[g][i] += z[i]
        wk = (day - datetime.timedelta(days=day.weekday())).isoformat()
        w = per_week.setdefault(wk, {"run": [0.0] * 5, "bike": [0.0] * 5})
        for i in range(5):
            w[g][i] += z[i]

    def shares(sec):
        tot = sum(sec)
        if tot <= 0:
            return None
        return {
            "minutes": round(tot / 60),
            "zones_pct": [round(s / tot * 100) for s in sec],
            "easy_pct": round((sec[0] + sec[1]) / tot * 100),
            "mid_pct": round(sec[2] / tot * 100),
            "hard_pct": round((sec[3] + sec[4]) / tot * 100),
        }

    out = {"weeks": weeks, "activities": counted, "without_zone_data": missing,
           "run": shares(acc["run"]), "bike": shares(acc["bike"]), "per_week": []}
    for wk in sorted(per_week, reverse=True):
        out["per_week"].append({"week_start": wk, "run": shares(per_week[wk]["run"]),
                                "bike": shares(per_week[wk]["bike"])})
    return out


def avg_hr_distribution(activities, today, coach, weeks=4, min_minutes=15):
    """Näherung: jede Einheit nach ihrer DURCHSCHNITTS-HF einer Coach-Zone
    zuordnen und nach Dauer gewichten. Grob (Intervalle verschwinden im
    Schnitt), aber die Zonen sind schwellenbasiert - anders als die
    %-HFmax-Zonen der Uhr, bei denen lockere Läufe schnell in Z3 landen."""
    start = today - datetime.timedelta(days=weeks * 7)
    out = {}
    for sport in ("run", "bike"):
        zones = (coach.get(sport) or {}).get("zones") or []
        if len(zones) < 3 or zones[1].get("high") is None or zones[2].get("high") is None:
            continue
        z2_hi, z3_hi = zones[1]["high"], zones[2]["high"]
        acc = {"easy": 0.0, "mid": 0.0, "hard": 0.0}
        n = 0
        for a in activities or []:
            if _sport_group(a) != sport:
                continue
            try:
                day = datetime.date.fromisoformat((a.get("startTimeLocal") or "")[:10])
            except ValueError:
                continue
            avg = _num(a.get("averageHR"))
            dur = _num(a.get("duration"))
            if day < start or avg is None or dur is None or dur < min_minutes * 60:
                continue
            key = "easy" if avg <= z2_hi else ("mid" if avg <= z3_hi else "hard")
            acc[key] += dur
            n += 1
        tot = sum(acc.values())
        if tot > 0:
            out[sport] = {"minutes": round(tot / 60), "n": n,
                          "easy_pct": round(acc["easy"] / tot * 100),
                          "mid_pct": round(acc["mid"] / tot * 100),
                          "hard_pct": round(acc["hard"] / tot * 100)}
    return out


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def _method_hint(method):
    m = (method or "").upper()
    if "MAX" in m:
        return "Die Uhr rechnet Zonen in % der HFmax. Das ist nicht dasselbe wie Zonen um die Schwelle: Z2 der Uhr liegt tiefer als Z2 nach Schwelle."
    if "RESERVE" in m:
        return "Die Uhr rechnet Zonen nach HF-Reserve (Karvonen)."
    if "LACTATE" in m or "THRESHOLD" in m:
        return "Die Uhr rechnet Zonen bereits in % der Laktatschwelle."
    return None


def build(client, activities, today=None):
    """Berechnet alles für den Sensor `herzfrequenzzonen`. Wirft nie nach außen,
    sondern liefert im Fehlerfall ein Ergebnis mit `error`."""
    today = today or datetime.date.today()
    state = _load_state()
    overrides = read_overrides()
    zones_raw, lt_raw = fetch_garmin(client)
    garmin = parse_garmin_zones(zones_raw)
    garmin_lt = parse_lactate(lt_raw)
    observed = update_observed_max(state, activities, today)
    hrmax, hrmax_src = choose_hrmax(overrides, observed, garmin)

    coach = {}
    hints = []
    for sport in ("run", "bike"):
        lthr, src, approx = choose_lthr(sport, overrides, garmin_lt, hrmax)
        entry = {"lthr": lthr, "source": src, "approx": approx, "zones": []}
        if lthr:
            entry["zones"] = friel_zones(lthr, sport, hrmax)
            if hrmax:
                ratio = lthr / hrmax
                entry["lthr_pct_hrmax"] = round(ratio * 100)
                if not (LTHR_RATIO_BAND[0] <= ratio <= LTHR_RATIO_BAND[1]):
                    hints.append(f"{'Lauf' if sport == 'run' else 'Rad'}-LTHR {lthr} liegt bei {round(ratio * 100)} % der HFmax {hrmax} - "
                                 f"außerhalb des üblichen Bereichs von {int(LTHR_RATIO_BAND[0] * 100)}-{int(LTHR_RATIO_BAND[1] * 100)} %. HFmax oder LTHR prüfen.")
        coach[sport] = entry

    if coach["run"]["approx"] and coach["run"]["lthr"]:
        hints.append("Die Lauf-Schwelle ist nur geschätzt. Genauer: 30-Minuten-Lauf am Anschlag, Durchschnitts-HF der letzten 20 Minuten = LTHR (Friel-Feldtest), "
                     "dann den Wert im Helfer „Coach LTHR Laufen“ eintragen.")
    if coach["bike"]["approx"] and coach["bike"]["lthr"]:
        hints.append("Für das Rad liegt kein eigener Schwellenwert vor - die Rad-Zonen sind eine Näherung. Rad-HF ist sportartspezifisch; ein eigener 30-Minuten-Test auf dem Rad ist sinnvoll.")

    garmin_max = next((g["max_hr"] for g in garmin if g.get("max_hr")), None)
    if observed.get("confirmed") and garmin_max and observed["confirmed"] - garmin_max > 3:
        hints.append(f"Bestätigter Höchstpuls {observed['confirmed']} liegt über der Uhr-Einstellung {garmin_max}. "
                     f"Die Zonen der Uhr sind dadurch zu tief angesetzt.")
    if (observed.get("confirmed") and garmin_max and garmin_max - observed["confirmed"] > 5
            and observed.get("n", 0) >= 5 and not overrides.get("hrmax")):
        hints.append(f"Die HFmax der Uhr ({garmin_max}) wurde bisher in keiner aufgezeichneten Einheit erreicht "
                     f"(höchster bestätigter Wert {observed['confirmed']}, {observed['n']} Einheiten seit Beginn der Aufzeichnung). "
                     f"Das kann stimmen (Maximum zeigt sich nur bei Maximaltests) oder die Einstellung ist zu hoch. "
                     f"Die Coach-Zonen hängen an der Schwelle und sind davon kaum betroffen; die Uhr-Zonen schon.")
    if observed.get("peak") and (observed.get("confirmed") is None or observed["peak"] - observed["confirmed"] > CONFIRM_TOLERANCE):
        hints.append(f"Höchstwert {observed['peak']} ({observed.get('peak_date')}) wurde in keiner zweiten Einheit annähernd erreicht "
                     f"und gilt als möglicher Sensor-Ausreißer - er fließt nicht in die Zonen ein.")
    for g in garmin:
        h = _method_hint(g.get("method"))
        if h and g["sport"].upper() in ("DEFAULT", "RUNNING"):
            hints.append(h)
            break
    if lt_raw is not None and not any(garmin_lt.values()):
        hints.append("Garmin hat (noch) keine Laktatschwelle ermittelt - sie braucht in der Regel einen kompatiblen Brustgurt.")

    dist = distribution(activities, today)
    dist_avg = avg_hr_distribution(activities, today, coach)
    for g, label in (("run", "Laufen"), ("bike", "Rad")):
        d = dist.get(g)
        a = dist_avg.get(g)
        if a and a["minutes"] >= 120 and a["easy_pct"] < 70:
            extra = (f" Nach den Zonen der Uhr sind es {d['easy_pct']} % in Z1-2." if d else "")
            hints.append(f"{label}: {a['easy_pct']} % der Zeit liegen bei einer Durchschnitts-HF in Coach-Z1-2 "
                         f"(Mittelbereich Z3: {a['mid_pct']} %, Z4+: {a['hard_pct']} %; letzte 4 Wochen, Näherung über die Durchschnitts-HF je Einheit).{extra} "
                         f"Richtwert ~80 % locker. Zu viel Mittelbereich macht lockere Einheiten weniger erholsam.")
        elif d and d["minutes"] >= 120 and d["easy_pct"] < 70 and not a:
            hints.append(f"{label}: nur {d['easy_pct']} % der Zeit in Z1-2 der Uhr (letzte 4 Wochen); Richtwert ~80 %.")
    hints.append("Optisches Handgelenk-Messen unterschätzt bei intensiven Intervallen die Zeit in hohen Zonen (Neudorfer 2024). Der Hart-Anteil ist deshalb eher eine Untergrenze.")

    # Verlauf für "stetig anpassen": nur bei Änderung oder einmal pro Woche
    hist = state.get("history", [])
    snap = {"date": today.isoformat(), "hrmax": hrmax, "lthr_run": coach["run"]["lthr"], "lthr_bike": coach["bike"]["lthr"]}
    prev = hist[-1] if hist else None
    changed = (not prev) or any(prev.get(k) != snap[k] for k in ("hrmax", "lthr_run", "lthr_bike"))
    stale = prev is not None and (today - datetime.date.fromisoformat(prev["date"])).days >= 7
    if changed or stale:
        hist.append(snap)
    state["history"] = hist[-HISTORY_KEEP:]
    _save_state(state)

    raw_txt = json.dumps({"zones": zones_raw, "lactate": lt_raw}, ensure_ascii=False, default=str)
    return {
        "updated": today.isoformat(),
        "hrmax": {"used": hrmax, "source": hrmax_src, "garmin": garmin_max,
                  "observed_confirmed": observed.get("confirmed"), "observed_confirmed_date": observed.get("confirmed_date"),
                  "observed_peak": observed.get("peak"), "observations": observed.get("n"),
                  "override": overrides.get("hrmax")},
        "garmin": garmin,
        "garmin_lthr": garmin_lt,
        "coach": coach,
        "distribution": dist,
        "distribution_avg": dist_avg,
        "hints": hints,
        "history": state["history"][-12:],
        "garmin_raw": raw_txt[:1800],
        "method": "Coach-Zonen: %LTHR nach Friel; Anker Schwelle statt HFmax",
    }


def state_text(result):
    if not result or result.get("error"):
        return "Fehler"
    run = (result.get("coach") or {}).get("run") or {}
    hm = (result.get("hrmax") or {}).get("used")
    parts = []
    if run.get("lthr"):
        parts.append(f"LTHR {run['lthr']}")
    if hm:
        parts.append(f"HFmax {hm}")
    return " · ".join(parts) if parts else "keine Daten"
