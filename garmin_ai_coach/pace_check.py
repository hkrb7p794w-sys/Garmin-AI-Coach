"""Hinweis, wenn Schwellen- oder Intervallpace angepasst werden sollte (seit 0.26.0).

Auftrag Alex 21.10.2026: Aus den Laufdaten soll ein Hinweis kommen, wenn die
Schwellenpace (und damit die Intervallpace, die im Plan daraus abgeleitet
ist: Schwelle −23 bis −18 s/km) schneller oder langsamer eingestellt werden
sollte.

Methode (bewusst konservativ, Feldtest bleibt der Goldstandard):
1. Grundlage sind harte Läufe der letzten LOOKBACK_DAYS Tage aus dem
   Tagesform-Cache (tagesform.py, Art "schwelle" bzw. "vo2"). Die Runden
   (get_activity_splits) werden je Aktivität einmal geladen und gecacht.
2. Arbeitsrunden: Bei strukturierten Workouts zählt Garmins intensityType
   (ACTIVE/INTERVAL). Sonst gelten Runden ≥ 150 s als Arbeit, die schneller
   sind als Schwelle + 30 s/km.
3. Schwellenläufe: Aus Tempo und Ø-HF der Arbeitsrunden wird das Tempo
   geschätzt, das du bei deiner Schwellen-HF (LTHR) laufen würdest.
   Linear über die Herzfrequenzreserve, nur wenn die Ø-HF bei 90–103 % der
   LTHR lag (kleine Extrapolation). Grundlage: Beziehung von Tempo und HF im
   submaximalen Bereich, LTHR als Anker der Schwelle (Friel; vgl.
   hr_zones.py).
4. 4×4-Läufe: Ziel sind 90–95 % HFmax (Helgerud et al. 2007). Erreicht die
   Spitzen-HF der Wiederholungen das nicht, obwohl die Pace im Zielband
   lag, ist das Band zu langsam. Lag die HF darüber und die Pace schon unter
   dem Band, ist es zu schnell. Das ergibt nur eine Richtung, keinen Wert.
5. Vorschlag erst ab MIN_SESSIONS Einheiten mit gleicher Richtung und einer
   Abweichung ≥ MIN_DELTA_S s/km. Höchstens MAX_STEP_S s/km pro Schritt, auf
   5 s gerundet. RPE ≥ 9 bremst eine Empfehlung „schneller“ aus.
Der Vorschlag landet im Vorschlags-Pool (Quelle "pace"). Annehmen trägt die
neue Schwellenpace direkt in input_text.lauf_schwellenpace ein (app.py).
"""
import os
import json
import statistics
import datetime

DATA_DIR = "/data"
CACHE_FILE = os.path.join(DATA_DIR, "pace_check_laps.json")
LOOKBACK_DAYS = 42
MIN_SESSIONS = 2
MIN_DELTA_S = 5
MAX_STEP_S = 10
FETCH_PER_SYNC = 4
WORK_TYPES = {"ACTIVE", "INTERVAL"}


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def mmss(sec) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def parse_mmss(text, default=None):
    try:
        m, s = str(text).strip().split(":")
        v = int(m) * 60 + int(s)
        return v if 150 <= v <= 600 else default
    except Exception:
        return default


def _load():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save(cache):
    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS + 30)).isoformat()
    cache = {k: v for k, v in cache.items() if (v.get("date") or "") >= cutoff}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1)
    return cache


def laps_compact(raw) -> list:
    laps = raw.get("lapDTOs") if isinstance(raw, dict) else raw
    out = []
    for lap in laps or []:
        if not isinstance(lap, dict):
            continue
        dur = _num(lap.get("movingDuration")) or _num(lap.get("duration"))
        dist = _num(lap.get("distance"))
        if not dur or not dist:
            continue
        out.append({"dur": round(dur), "dist": round(dist), "hr": _num(lap.get("averageHR")),
                    "hrmax": _num(lap.get("maxHR")), "type": lap.get("intensityType")})
    return out


def update_cache(client, sessions: list) -> dict:
    """Lädt die Runden für neue harte Läufe (höchstens FETCH_PER_SYNC pro Sync)."""
    cache = _load()
    budget = FETCH_PER_SYNC
    changed = False
    for s in sessions:
        key = str(s["id"])
        if key in cache or budget <= 0:
            continue
        budget -= 1
        try:
            cache[key] = {"date": s["date"], "laps": laps_compact(client.get_activity_splits(s["id"]))}
            changed = True
        except Exception as e:
            print(f"[pace_check] Runden für {key} nicht ladbar: {e}")
    return _save(cache) if changed else cache


def work_laps(laps: list, t_pace: int) -> list:
    typed = [l for l in laps if (l.get("type") or "").upper() in WORK_TYPES]
    if typed:
        return [l for l in typed if l["dur"] >= 120]
    limit = t_pace + 30
    return [l for l in laps if l["dur"] >= 150 and l["dist"] > 0 and l["dur"] / l["dist"] * 1000 <= limit]


def evaluate(sessions: list, cache: dict, t_pace: int, lthr: float, hrmax: float, rhr: float) -> dict:
    """sessions: [{id, date, name, kind, rpe}] harte Läufe. Liefert das Ergebnis für Sensor und Vorschlag."""
    rows = []
    est_t = []
    direction = []
    i_lo, i_hi = t_pace - 23, t_pace - 18
    for s in sessions:
        laps = (cache.get(str(s["id"])) or {}).get("laps") or []
        wl = work_laps(laps, t_pace)
        if not wl:
            rows.append({**s, "verdict": "keine Arbeitsrunden erkannt"})
            continue
        dur = sum(l["dur"] for l in wl)
        pace = dur / sum(l["dist"] for l in wl) * 1000
        hrs = [(l["hr"], l["dur"]) for l in wl if l.get("hr")]
        hr = sum(h * d for h, d in hrs) / sum(d for _, d in hrs) if hrs else None
        row = {**s, "work_min": round(dur / 60), "work_pace": mmss(pace), "work_hr": round(hr) if hr else None}
        if s["kind"] == "schwelle" and hr and lthr and rhr and 0.90 <= hr / lthr <= 1.03:
            speed = 1000 / pace
            speed_lt = speed * (lthr - rhr) / (hr - rhr)
            t_est = 1000 / speed_lt
            row.update({"hr_pct_lthr": round(hr / lthr * 100), "est_threshold": mmss(t_est)})
            if s.get("rpe") and s["rpe"] >= 9 and t_est < t_pace:
                row["verdict"] = "RPE ≥ 9 – keine Empfehlung „schneller“ aus dieser Einheit"
            else:
                est_t.append(t_est)
                row["verdict"] = ("Schwelle eher schneller" if t_est < t_pace - MIN_DELTA_S else
                                  "Schwelle eher langsamer" if t_est > t_pace + MIN_DELTA_S else "passt")
        elif s["kind"] == "schwelle":
            row["verdict"] = "HF außerhalb 90–103 % LTHR – nicht auswertbar" if hr else "ohne HF"
        elif s["kind"] == "vo2" and hrmax:
            peaks = [l["hrmax"] for l in wl if l.get("hrmax")]
            peak = statistics.mean(peaks) if peaks else None
            row["rep_peak_hr_pct"] = round(peak / hrmax * 100) if peak else None
            if peak and peak < 0.90 * hrmax and pace <= i_hi:
                direction.append(-1)
                row["verdict"] = "Ziel-HF nicht erreicht trotz Pace im Band – Band zu langsam"
            elif peak and peak > 0.96 * hrmax and pace > i_hi + 5:
                direction.append(1)
                row["verdict"] = "HF über Ziel, Pace langsamer als Band – Band zu schnell"
            else:
                row["verdict"] = "passt"
        rows.append(row)

    status, suggested, reason = "passt", None, ""
    if len(est_t) >= MIN_SESSIONS:
        target = statistics.median(est_t)
        delta = target - t_pace
        votes = sum(1 for t in est_t if (t - t_pace) * delta > 0 and abs(t - t_pace) >= MIN_DELTA_S)
        vo2_agree = sum(1 for d in direction if d * delta > 0)
        if abs(delta) >= MIN_DELTA_S and votes + vo2_agree >= MIN_SESSIONS:
            step = max(-MAX_STEP_S, min(MAX_STEP_S, delta))
            suggested = int(5 * round((t_pace + step) / 5))
            if suggested != t_pace:
                status = "schneller" if suggested < t_pace else "langsamer"
                reason = (f"{votes} Schwellenläufe der letzten {LOOKBACK_DAYS // 7} Wochen ergeben bei deiner Schwellen-HF "
                          f"{int(lthr)} bpm im Median {mmss(target)} /km"
                          + (f", {vo2_agree} 4×4-Lauf/-Läufe zeigen in dieselbe Richtung" if vo2_agree else "") + ".")
    elif len(est_t) + len(direction) < MIN_SESSIONS:
        status = "zu wenig Daten"
    elif direction and all(d == direction[0] for d in direction) and len(direction) >= MIN_SESSIONS:
        suggested = t_pace + 5 * direction[0]
        status = "schneller" if direction[0] < 0 else "langsamer"
        reason = f"{len(direction)} 4×4-Läufe zeigen dieselbe Richtung (Ziel-HF 90–95 % HFmax)."
    res = {"status": status, "current": mmss(t_pace), "interval_band": f"{mmss(i_lo)}–{mmss(i_hi)}",
           "lthr": lthr, "hrmax": hrmax, "sessions": rows[-10:],
           "updated": datetime.datetime.now().isoformat(timespec="minutes")}
    if suggested:
        res.update({"suggested": mmss(suggested), "suggested_s": suggested,
                    "suggested_interval_band": f"{mmss(suggested - 23)}–{mmss(suggested - 18)}", "reason": reason})
    return res


def suggestion(res: dict) -> list:
    """Eintrag für den Vorschlags-Pool (leer, wenn nichts anzupassen ist)."""
    if not res.get("suggested"):
        return []
    word = "schneller" if res["status"] == "schneller" else "langsamer"
    return [{
        "id": f"pace-schwelle-{res['suggested'].replace(':', '')}",
        "discipline": "laufen",
        "title": f"Schwellenpace auf {res['suggested']} /km ({word}, bisher {res['current']})",
        "text": (f"{res['reason']} Annehmen trägt {res['suggested']} /km als Schwellenpace ein; "
                 f"die Intervallpace für 4×4 wird damit {res['suggested_interval_band']} /km "
                 f"(bisher {res['interval_band']}). Den nächsten 30-min-Test als Bestätigung nutzen."),
    }]
