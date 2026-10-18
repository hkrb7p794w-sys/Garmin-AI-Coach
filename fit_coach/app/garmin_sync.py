"""Garmin-Anbindung: Anmeldung (inkl. Zwei-Faktor-Code) und Datenabruf.

Anmeldung: python-garminconnect >= 0.3.19 mit `return_on_mfa=True`. Das
Passwort wird nur für den Login-Aufruf verwendet; gespeichert werden die
Garmin-Tokens in /data/garmin_tokens (Rechte 0600, setzt die Bibliothek).
Die Tokens erneuern sich selbst; ein neuer Login ist nur nötig, wenn Garmin
sie verwirft (z. B. Passwortänderung).

Abrufe: Jede Abfrage einzeln abgesichert (`_safe`): fällt ein Endpunkt aus
(Uhr kann eine Funktion nicht, Garmin ändert etwas), läuft der Rest weiter.
Teure Rückblicke (Gewicht 120 Tage, Prognosen/VO2max 90 Tage, Ernährung)
laufen nur beim ersten Sync bzw. einmal täglich.
"""
import os
import time
import datetime
import threading

import store
import running
import fit_exercises

TOKEN_DIR = store.path("garmin_tokens")
_pending = {"client": None, "since": 0.0, "email": None}
_pending_lock = threading.Lock()
MFA_TIMEOUT_S = 600


class GarminLoginError(Exception):
    pass


def is_connected() -> bool:
    try:
        return any(os.path.isfile(os.path.join(TOKEN_DIR, f)) for f in os.listdir(TOKEN_DIR))
    except FileNotFoundError:
        return False


def mfa_pending() -> bool:
    with _pending_lock:
        return bool(_pending["client"]) and time.time() - _pending["since"] < MFA_TIMEOUT_S


def _friendly(e: Exception) -> str:
    s = str(e)
    low = s.lower()
    if "429" in low or "too many" in low or "rate limit" in low:
        return "Garmin blockt gerade zu viele Anmeldeversuche. Bitte 15–30 Minuten warten und dann erneut versuchen."
    if "401" in low or "unauthorized" in low or "authentication failed" in low or "credentials" in low:
        return "E-Mail oder Passwort stimmen nicht (oder das Konto ist bei Garmin gesperrt – dann einmal auf connect.garmin.com anmelden)."
    if "mfa" in low and "code" in low:
        return "Der Bestätigungscode wurde nicht akzeptiert. Bitte den neuesten Code aus der E-Mail/App eingeben."
    return f"Anmeldung fehlgeschlagen: {s[:200]}"


def start_login(email: str, password: str) -> str:
    """'ok' (fertig) oder 'mfa' (Code nötig). Wirft GarminLoginError mit lesbarem Text."""
    from garminconnect import Garmin
    os.makedirs(TOKEN_DIR, exist_ok=True)
    try:
        g = Garmin(email.strip(), password, return_on_mfa=True)
        status, _ = g.login()
    except Exception as e:
        raise GarminLoginError(_friendly(e))
    if status == "needs_mfa":
        with _pending_lock:
            _pending.update(client=g, since=time.time(), email=email.strip())
        return "mfa"
    _persist(g)
    return "ok"


def finish_mfa(code: str) -> str:
    with _pending_lock:
        g = _pending["client"]
        fresh = g is not None and time.time() - _pending["since"] < MFA_TIMEOUT_S
    if not fresh:
        raise GarminLoginError("Die Anmeldung ist abgelaufen. Bitte noch einmal E-Mail und Passwort eingeben.")
    try:
        g.resume_login(None, str(code).strip().replace(" ", ""))
    except Exception as e:
        # Falscher Code: Die Bibliothek lässt die MFA-Sitzung offen -> erneut versuchen möglich
        raise GarminLoginError(_friendly(e) if "mfa" in str(e).lower() else
                               "Der Code wurde nicht akzeptiert. Bitte den neuesten Code eingeben.")
    _persist(g)
    with _pending_lock:
        _pending.update(client=None, since=0.0, email=None)
    return "ok"


def cancel_mfa():
    with _pending_lock:
        _pending.update(client=None, since=0.0, email=None)


def _persist(g):
    try:
        g.client.dump(TOKEN_DIR)
    except Exception as e:
        raise GarminLoginError(f"Tokens konnten nicht gespeichert werden: {e}")


def logout():
    try:
        for f in os.listdir(TOKEN_DIR):
            os.remove(os.path.join(TOKEN_DIR, f))
    except FileNotFoundError:
        pass


def client():
    from garminconnect import Garmin
    g = Garmin()
    g.login(TOKEN_DIR)
    return g


def _safe(label, fn, errors: list):
    try:
        return fn()
    except Exception as e:
        msg = str(e)[:160]
        print(f"[garmin] {label} fehlgeschlagen: {msg}")
        errors.append(f"{label}: {msg}")
        return None


def _iso(d: datetime.date) -> str:
    return d.isoformat()


def parse_user_summary(s: dict) -> dict:
    s = s or {}
    def n(k):
        v = s.get(k)
        return v if isinstance(v, (int, float)) else None
    return {"steps": n("totalSteps"), "step_goal": n("dailyStepGoal"),
            "active_kcal": n("activeKilocalories"), "total_kcal": n("totalKilocalories"),
            "bmr_kcal": n("bmrKilocalories"), "mod_min": n("moderateIntensityMinutes"),
            "vig_min": n("vigorousIntensityMinutes"), "rhr": n("restingHeartRate"),
            "stress": n("averageStressLevel"), "km": round((n("totalDistanceMeters") or 0) / 1000, 2)}


def parse_weighins(raw) -> dict:
    """weight/range -> {date: kg}; pro Tag die früheste Messung (morgens)."""
    out = {}
    for day in (raw or {}).get("dailyWeightSummaries") or []:
        date = str(day.get("summaryDate") or "")[:10]
        metrics = day.get("allWeightMetrics") or []
        cand = []
        for m in metrics:
            w = m.get("weight")
            ts = m.get("timestampGMT") or m.get("date") or 0
            if isinstance(w, (int, float)) and w > 0:
                cand.append((ts, w))
        if cand:
            w = sorted(cand)[0][1]
        else:
            lw = (day.get("latestWeight") or {}).get("weight") or day.get("minWeight")
            w = lw if isinstance(lw, (int, float)) else None
        if date and w:
            out[date] = round(w / 1000.0, 2) if w > 1000 else round(float(w), 2)
    for m in (raw or {}).get("dateWeightList") or []:  # anderes Antwortformat
        date = str(m.get("calendarDate") or "")[:10]
        w = m.get("weight")
        if date and isinstance(w, (int, float)) and w > 0 and date not in out:
            out[date] = round(w / 1000.0, 2) if w > 1000 else round(float(w), 2)
    return out


def parse_weight_goal(raw):
    """Zielgewicht in kg oder None (Garmin speichert Gramm)."""
    items = raw if isinstance(raw, list) else [raw]
    for it in items or []:
        if not isinstance(it, dict):
            continue
        for k in ("goalValue", "weightGoal", "value"):
            v = it.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return round(v / 1000.0, 1) if v > 1000 else round(float(v), 1)
    return None


def parse_planned(cal_weeks, by_period, today: datetime.date) -> list:
    """Geplante Workouts (Garmin-Kalender, Garmin-Coach-Pläne) der nächsten 7 Tage."""
    items = []
    for wk in cal_weeks or []:
        for it in (wk or {}).get("calendarItems") or []:
            if it.get("itemType") in ("workout", "trainingPlan", "fbtAdaptiveWorkout") or it.get("workoutId"):
                items.append({"date": str(it.get("date") or "")[:10], "title": it.get("title") or "Workout",
                              "sport": it.get("sportTypeKey") or "", "id": it.get("workoutId") or it.get("id")})
    for it in by_period if isinstance(by_period, list) else []:
        if not isinstance(it, dict):
            continue
        date = str(it.get("calendarDate") or it.get("scheduledDate") or it.get("date") or "")[:10]
        w = it.get("workout") if isinstance(it.get("workout"), dict) else {}
        title = it.get("workoutName") or w.get("workoutName") or it.get("title") or "Workout"
        sport = (it.get("sportType") or w.get("sportType") or {})
        sport = sport.get("sportTypeKey") if isinstance(sport, dict) else (it.get("sportTypeKey") or "")
        items.append({"date": date, "title": title, "sport": sport or "",
                      "id": it.get("workoutId") or w.get("workoutId") or it.get("scheduledWorkoutId")})
    end = today + datetime.timedelta(days=7)
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["date"]):
        if not it["date"] or not (today.isoformat() <= it["date"] <= end.isoformat()):
            continue
        key = (it["date"], it["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def sync(today: datetime.date, state: dict) -> dict:
    """Holt alles von Garmin und legt es in /data ab. Gibt eine Zusammenfassung
    {ok, errors, new_activities} zurück. Wirft nur, wenn schon die Anmeldung scheitert."""
    errors = []
    g = client()
    first = not state.get("garmin_first_sync_done")
    day_key = _iso(today)

    # Aktivitäten (beim ersten Mal die letzten 100, danach die letzten 40)
    raw = _safe("Aktivitäten", lambda: g.get_activities(0, 40 if state.get("bf_acts") else 100), errors)
    raw_acts = raw or []
    if raw is not None:
        state["bf_acts"] = True
    new_ids = []

    def merge_acts(cache):
        for a in raw_acts:
            try:
                n = running.normalize_activity(a)
            except Exception as e:
                print(f"[garmin] Aktivität nicht lesbar: {e}")
                continue
            if not n.get("id") or not n.get("date"):
                continue
            if str(n["id"]) not in cache:
                new_ids.append(n["id"])
            cache[str(n["id"])] = n
        cutoff = _iso(today - datetime.timedelta(days=400))
        return {k: v for k, v in cache.items() if v.get("date", "") >= cutoff}
    acts = store.update("activities.json", {}, merge_acts)

    # Tageswerte: heute, gestern (endgültig) und beim ersten Mal die laufende Woche
    days = [today, today - datetime.timedelta(days=1)]
    if not state.get("bf_daily"):
        days += [today - datetime.timedelta(days=i) for i in range(2, 14)]
        state["bf_daily"] = True
    daily = store.load("daily.json", {})
    for d in days:
        if d != today and d != today - datetime.timedelta(days=1) and _iso(d) in daily:
            continue
        s = _safe(f"Tageswerte {d}", lambda d=d: g.get_user_summary(_iso(d)), errors)
        if s:
            daily[_iso(d)] = parse_user_summary(s)
    store.save("daily.json", store.prune_dates(daily, 400, today))

    # Gewicht von Garmin (Waage oder Eingabe in Garmin Connect)
    span = 14 if state.get("bf_weight") else 120
    wi = _safe("Gewicht", lambda: g.get_weigh_ins(_iso(today - datetime.timedelta(days=span)), day_key), errors)
    if wi is not None:
        state["bf_weight"] = True
        parsed = parse_weighins(wi)

        def merge_w(w):
            gw = w.setdefault("garmin", {})
            gw.update(parsed)
            return w
        store.update("weights.json", {"manual": {}, "garmin": {}, "yazio": {}}, merge_w)

    metrics = store.load("metrics.json", {})
    if metrics.get("daily_done") != day_key:
        goal = _safe("Zielgewicht", lambda: g.get_weight_goal(_iso(today - datetime.timedelta(days=1)), day_key), errors)
        metrics["garmin_weight_goal"] = parse_weight_goal(goal)
        # Prognosen und VO2max einmal täglich, Rückblick nur beim ersten Mal
        if first or not metrics.get("pred_hist") or not metrics.get("vo2_hist"):
            ph = _safe("Prognose-Verlauf", lambda: g.get_race_predictions(_iso(today - datetime.timedelta(days=90)), day_key, "daily"), errors)
            metrics["pred_hist"] = running.parse_prediction_history(ph) if ph else metrics.get("pred_hist", {})
            vh = _safe("VO2max-Verlauf", lambda: g.connectapi(f"/metrics-service/metrics/maxmet/daily/{_iso(today - datetime.timedelta(days=90))}/{day_key}"), errors)
            hist = {}
            for it in vh or []:
                v = running.parse_vo2max(it)
                dd = str((it.get("generic") or {}).get("calendarDate") or it.get("calendarDate") or "")[:10]
                if v and dd:
                    hist[dd] = v
            metrics["vo2_hist"] = hist or metrics.get("vo2_hist", {})
        pred = _safe("Prognose", g.get_race_predictions, errors)
        if pred:
            metrics["predictions"] = running.parse_predictions(pred)
            if metrics["predictions"].get("5k"):
                metrics.setdefault("pred_hist", {})[day_key] = metrics["predictions"]["5k"]
        vo2 = _safe("VO2max", lambda: g.get_max_metrics_latest(day_key), errors)
        v = running.parse_vo2max(vo2) if vo2 else None
        if v:
            metrics["vo2max"] = v
            metrics.setdefault("vo2_hist", {})[day_key] = v
        metrics["pred_hist"] = store.prune_dates(metrics.get("pred_hist") or {}, 365, today)
        metrics["vo2_hist"] = store.prune_dates(metrics.get("vo2_hist") or {}, 365, today)
        metrics["daily_done"] = day_key
    # Rekorde bei jedem Sync (eine Abfrage) - neue Bestzeit soll schnell sichtbar sein
    prs = _safe("Rekorde", g.get_personal_record, errors)
    if prs is not None:
        metrics["prs"] = running.parse_prs(prs)
    # Geplante Workouts (Garmin-Kalender + Garmin-Coach-Pläne)
    cal = [_safe("Kalender", lambda: g.get_calendar_week(day_key), errors),
           _safe("Kalender nächste Woche", lambda: g.get_calendar_week(_iso(today + datetime.timedelta(days=7))), errors)]
    per = _safe("Trainingsplan", lambda: g.get_scheduled_workouts_by_period(day_key, _iso(today + datetime.timedelta(days=7))), errors)
    metrics["planned"] = parse_planned(cal, per, today)
    store.save("metrics.json", metrics)

    # Kraft-Übungen der Gym-Einheiten (nur neue bzw. junge Einheiten, max. 8 Abrufe)
    strength = store.load("strength.json", {})
    budget = 8
    for a in sorted(acts.values(), key=lambda x: x.get("start") or "", reverse=True):
        if a.get("kind") != "strength" or budget <= 0:
            continue
        age = (today - datetime.date.fromisoformat(a["date"])).days
        cached = strength.get(str(a["id"]))
        if cached is not None and age > 3:
            continue
        if age > 120:
            continue
        budget -= 1
        ex = fit_exercises.get_strength_exercises(g, a["id"])
        if cached is not None and not ex:
            continue
        strength[str(a["id"])] = {"activity_id": a["id"], "date": a["date"], "activity_name": a.get("name"), "exercises": ex}
    strength = {k: v for k, v in strength.items() if v.get("date", "") >= _iso(today - datetime.timedelta(days=365))}
    store.save("strength.json", strength)

    state["garmin_first_sync_done"] = True
    return {"ok": True, "errors": errors, "new_activities": new_ids}
