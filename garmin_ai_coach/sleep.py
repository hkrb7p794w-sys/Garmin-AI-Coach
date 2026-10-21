"""Schlaf: Nächte sammeln und auswerten (seit 0.25.0).

Bisher kam vom Schlaf nur Dauer und Score des letzten Tages ins Add-on. Für eine
Schlafanalyse (Auftrag Alex 21.10.2026) braucht es den Verlauf: Dauer,
Schlafphasen, Einschlaf-/Aufwachzeit (Regelmäßigkeit), Wachphasen, SpO2,
Atmung, nächtliche HRV.

- record(): jede Nacht aus dem ohnehin geladenen get_sleep_data(heute) merken
  (kein zusätzlicher Garmin-Abruf).
- backfill(): fehlende Nächte einmalig nachladen - ein Abruf pro Nacht mit
  Pause dazwischen (Rate-Limit-Schutz), im Hintergrund über /sleep_export.
- summary(): Kennzahlen für den Sensor sensor.garmin_ai_coach_garmin_schlaf.

Garmin-Felder (get_sleep_data -> dailySleepDTO): sleepTimeSeconds,
deep/light/rem/awakeSleepSeconds, sleepStart/EndTimestampLocal (ms),
averageSpO2Value/lowestSpO2Value (nur mit Pulsoximeter im Schlaf),
averageRespirationValue, awakeCount, avgSleepStress, sleepScores.overall.value;
oberste Ebene: restlessMomentsCount, avgOvernightHrv, bodyBatteryChange,
restingHeartRate. Fehlende Felder bleiben None.
"""
import os, json, time, datetime, statistics, threading

DATA_DIR = "/data"
CACHE_FILE = os.path.join(DATA_DIR, "sleep_nights.json")
KEEP_DAYS = 400
_lock = threading.Lock()
_job = {"running": False, "done": 0, "todo": 0, "error": None}


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _clock(ms):
    """Garmin-Lokalzeit (ms seit Epoche, aber als lokale Uhrzeit kodiert) -> 'HH:MM'."""
    if not ms:
        return None
    return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M")


def extract(raw: dict):
    """Eine Nacht aus get_sleep_data(); None, wenn (noch) keine Daten da sind."""
    dto = (raw or {}).get("dailySleepDTO") or {}
    secs = _num(dto.get("sleepTimeSeconds"))
    if not secs:
        return None
    scores = dto.get("sleepScores") or {}
    need = dto.get("sleepNeed") or {}
    out = {
        "date": dto.get("calendarDate"),
        "sleep_min": round(secs / 60),
        "deep_min": round((_num(dto.get("deepSleepSeconds")) or 0) / 60),
        "light_min": round((_num(dto.get("lightSleepSeconds")) or 0) / 60),
        "rem_min": round((_num(dto.get("remSleepSeconds")) or 0) / 60),
        "awake_min": round((_num(dto.get("awakeSleepSeconds")) or 0) / 60),
        "start": _clock(dto.get("sleepStartTimestampLocal")),
        "end": _clock(dto.get("sleepEndTimestampLocal")),
        "score": ((scores.get("overall") or {}).get("value")),
        "awake_count": dto.get("awakeCount"),
        "stress": _num(dto.get("avgSleepStress")),
        "spo2_avg": _num(dto.get("averageSpO2Value")),
        "spo2_low": _num(dto.get("lowestSpO2Value")),
        "resp_avg": _num(dto.get("averageRespirationValue")),
        "restless": (raw or {}).get("restlessMomentsCount"),
        "hrv": _num((raw or {}).get("avgOvernightHrv")),
        "rhr": _num((raw or {}).get("restingHeartRate")),
        "bb_change": (raw or {}).get("bodyBatteryChange"),
        "need_min": need.get("actual"),
        "hr_avg": _num(dto.get("avgHeartRate")),
        "resp_low": _num(dto.get("lowestRespirationValue")),
        "skin_temp_dev": _num((raw or {}).get("avgSkinTempDeviationC")),
        "align": ((dto.get("sleepAlignment") or {}).get("status")),
        "breathing_data": bool((raw or {}).get("breathingDisruptionData")),
    }
    return out


def _load() -> dict:
    try:
        with open(CACHE_FILE) as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save(nights: dict):
    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    nights = {k: v for k, v in nights.items() if k >= cutoff}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(nights, f, indent=1, ensure_ascii=False)
    return nights


def record(raw: dict) -> dict:
    night = extract(raw)
    with _lock:
        nights = _load()
        if night and night.get("date"):
            nights[night["date"]] = night
            nights = _save(nights)
    return nights


def _backfill(client, days: int, pause: float):
    try:
        today = datetime.date.today()
        with _lock:
            have = set(_load())
        todo = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days)]
        todo = [d for d in todo if d not in have]
        _job.update(todo=len(todo), done=0, error=None)
        empty = 0
        for d in todo:
            try:
                night = extract(client.get_sleep_data(d))
            except Exception as e:
                _job["error"] = f"{d}: {e}"
                print(f"[sleep] {d} nicht ladbar: {e}")
                if "429" in str(e) or "Too Many" in str(e):
                    break
                night = None
            if night:
                with _lock:
                    nights = _load()
                    nights[night["date"]] = night
                    _save(nights)
            else:
                empty += 1
            _job["done"] += 1
            time.sleep(pause)
        print(f"[sleep] Nachladen fertig: {_job['done']} Tage abgefragt, {empty} ohne Schlafdaten")
    finally:
        _job["running"] = False


def start_backfill(client, days: int = 90, pause: float = 1.5) -> dict:
    if not _job["running"]:
        _job["running"] = True
        threading.Thread(target=_backfill, args=(client, days, pause), daemon=True).start()
    return dict(_job)


def job_status() -> dict:
    return dict(_job)


def _mins(hhmm):
    """'23:40' -> Minuten relativ zu Mitternacht, Abendzeiten negativ (-20)."""
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    v = h * 60 + m
    return v - 1440 if v >= 18 * 60 else v


def _fmt(mins):
    if mins is None:
        return None
    v = round(mins) % 1440
    return f"{v // 60:02d}:{v % 60:02d}"


def summary(nights: dict = None, days: int = 28) -> dict:
    nights = nights if nights is not None else _load()
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    sel = [v for k, v in sorted(nights.items()) if k >= cutoff]
    if not sel:
        return {"nights": 0}

    def avg(key):
        vals = [v[key] for v in sel if isinstance(v.get(key), (int, float))]
        return round(statistics.mean(vals), 1) if vals else None

    def sd(vals):
        return round(statistics.stdev(vals)) if len(vals) > 2 else None

    starts = [_mins(v.get("start")) for v in sel if v.get("start")]
    ends = [_mins(v.get("end")) for v in sel if v.get("end")]
    mids = [(_mins(v["start"]) + _mins(v["end"])) / 2 for v in sel if v.get("start") and v.get("end")]
    tot = avg("sleep_min") or 0
    stage = {k: (round(avg(f"{k}_min") / tot * 100) if tot and avg(f"{k}_min") is not None else None)
             for k in ("deep", "light", "rem")}
    short = sum(1 for v in sel if (v.get("sleep_min") or 0) < 7 * 60)
    return {
        "nights": len(sel), "days": days,
        "sleep_h": round(tot / 60, 2) if tot else None,
        "nights_under_7h": short,
        "deep_pct": stage["deep"], "light_pct": stage["light"], "rem_pct": stage["rem"],
        "awake_min": avg("awake_min"), "awake_count": avg("awake_count"),
        "score": avg("score"), "hrv": avg("hrv"), "rhr": avg("rhr"), "resp": avg("resp_avg"),
        "spo2_avg": avg("spo2_avg"), "spo2_low": avg("spo2_low"),
        "spo2_nights": sum(1 for v in sel if v.get("spo2_avg")),
        "bedtime": _fmt(statistics.mean(starts)) if starts else None, "bedtime_sd_min": sd(starts),
        "wake": _fmt(statistics.mean(ends)) if ends else None, "wake_sd_min": sd(ends),
        "midpoint_sd_min": sd(mids),
        "need_min": avg("need_min"),
        "hr_avg": avg("hr_avg"),
    }
