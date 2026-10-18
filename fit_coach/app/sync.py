"""Ablauf: Daten holen (Garmin, Yazio), auswerten, an Home Assistant senden.

`full_sync()` holt neue Daten (Netzwerk), `refresh()` rechnet nur aus dem, was
in /data liegt, neu und veröffentlicht - das läuft auch nach jeder Eingabe im
Dashboard (Ziel geändert, Gewicht eingetragen), ohne Garmin zu belasten.
"""
import datetime
import threading
import time
import traceback

import store
import publish
import garmin_sync
import yazio
import weight as weight_mod
import nutrition as nutrition_mod
import running as running_mod
import gym as gym_mod
import goals as goals_mod
import tips as tips_mod

DEFAULT_SETTINGS = {"zielgewicht": 0, "gewicht_eintragen": 0, "ziel_laeufe": 3, "ziel_gym": 1,
                    "rekord_kg": 20, "rekord_wdh": 8, "uebung": "Kniebeuge"}
WEIGHTS_DEFAULT = {"manual": {}, "garmin": {}, "yazio": {}}
MIN_INTERVAL_S = 120          # Schutz vor Doppelklicks / Garmin-Sperre
_sync_lock = threading.Lock()
_last_start = {"t": 0.0}
SYNC_HOURS = [6, 12, 20]


def settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    s.update(store.load("settings.json", {}))
    return s


def save_setting(key, value):
    store.update("settings.json", {}, lambda s: {**s, key: value})


def state() -> dict:
    return store.load("state.json", {})


def _save_state(st):
    store.save("state.json", st)


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------- Yazio-Sync
def yazio_sync(today: datetime.date, st: dict) -> dict:
    errors = []
    days = [today, today - datetime.timedelta(days=1)]
    nutr = store.load("nutrition.json", {})
    if not st.get("bf_yazio"):
        days += [today - datetime.timedelta(days=i) for i in range(2, 29) if (today - datetime.timedelta(days=i)).isoformat() not in nutr]
    ok_any = False
    for d in days:
        try:
            nutr[d.isoformat()] = nutrition_mod.parse_daily_summary(yazio.daily_summary(d))
            ok_any = True
        except yazio.YazioAuthError:
            raise
        except Exception as e:
            errors.append(f"Tag {d}: {str(e)[:120]}")
        if len(days) > 2:
            time.sleep(0.4)
    if ok_any and not st.get("bf_yazio"):
        st["bf_yazio"] = True
    store.save("nutrition.json", store.prune_dates(nutr, 400, today))

    # Gewicht aus Yazio: beim ersten Mal rückwärts alle Einträge der letzten 60 Tage
    found = {}
    try:
        if not st.get("bf_yazio_weight"):
            d = today
            for _ in range(45):
                res = yazio.last_weight(d)
                if not res:
                    break
                day, kg = res
                if day in found:  # Schnittstelle ignoriert das Datum -> nicht endlos fragen
                    break
                found[day] = kg
                d = datetime.date.fromisoformat(day) - datetime.timedelta(days=1)
                if (today - d).days > 60:
                    break
                time.sleep(0.3)
            st["bf_yazio_weight"] = True
        else:
            res = yazio.last_weight(today)
            if res:
                found[res[0]] = res[1]
    except yazio.YazioAuthError:
        raise
    except Exception as e:
        errors.append(f"Gewicht: {str(e)[:120]}")
    if found:
        store.update("weights.json", WEIGHTS_DEFAULT, lambda w: {**w, "yazio": {**(w.get("yazio") or {}), **found}})
    return {"ok": ok_any, "errors": errors}


# ---------------------------------------------------------------- Gesamtsync
def full_sync(reason: str = "zeitplan", force: bool = False) -> bool:
    if not force and time.time() - _last_start["t"] < MIN_INTERVAL_S:
        print(f"[sync] übersprungen ({reason}): letzter Start vor weniger als {MIN_INTERVAL_S} s")
        return False
    if not _sync_lock.acquire(blocking=False):
        print(f"[sync] läuft bereits ({reason})")
        return False
    _last_start["t"] = time.time()
    try:
        today = datetime.date.today()
        st = state()
        st["sync_running"] = True
        _save_state(st)
        publish_status(st)
        print(f"[sync] Start ({reason})")
        if garmin_sync.is_connected():
            try:
                res = garmin_sync.sync(today, st)
                st["garmin"] = {"last_sync": _now_iso(), "last_error": None,
                                "partial_errors": res["errors"][:8]}
                print(f"[sync] Garmin ok ({len(res['new_activities'])} neue Aktivitäten, {len(res['errors'])} Teilfehler)")
            except Exception as e:
                msg = str(e)[:240]
                print(f"[sync] Garmin fehlgeschlagen: {msg}")
                g = st.get("garmin") or {}
                g.update(last_error=msg, last_error_at=_now_iso())
                low = msg.lower()
                if ("Authentication" in type(e).__name__ or "401" in msg or "auth" in low or "token" in low
                        or "password are required" in low):
                    g["needs_login"] = True  # Tokens verworfen/abgelaufen -> Dashboard bittet um neue Anmeldung
                st["garmin"] = g
        if yazio.is_connected():
            try:
                res = yazio_sync(today, st)
                st["yazio"] = {"last_sync": _now_iso(), "last_error": "; ".join(res["errors"][:3]) or None}
            except yazio.YazioAuthError as e:
                st["yazio"] = {**(st.get("yazio") or {}), "last_error": str(e), "needs_login": True,
                               "last_error_at": _now_iso()}
            except Exception as e:
                st["yazio"] = {**(st.get("yazio") or {}), "last_error": str(e)[:200], "last_error_at": _now_iso()}
        st["last_sync"] = _now_iso()
        st["sync_running"] = False
        _save_state(st)
        refresh()
        return True
    except Exception as e:
        print(f"[sync] unerwarteter Fehler: {e}\n{traceback.format_exc()}")
        st = state()
        st["sync_running"] = False
        st["last_error"] = str(e)[:200]
        _save_state(st)
        publish_status(st)
        return False
    finally:
        _sync_lock.release()


def full_sync_async(reason, force=False):
    threading.Thread(target=full_sync, args=(reason, force), daemon=True).start()


# --------------------------------------------------------------- Auswertung
def _goal_weight(s, nutr, metrics):
    if s.get("zielgewicht") and float(s["zielgewicht"]) > 0:
        return float(s["zielgewicht"]), "Dashboard"
    for d in sorted(nutr, reverse=True):
        g = (nutr[d] or {}).get("weight_goal")
        if g:
            return float(g), "Yazio"
    if metrics.get("garmin_weight_goal"):
        return float(metrics["garmin_weight_goal"]), "Garmin"
    return None, None


def compute(today: datetime.date = None) -> dict:
    today = today or datetime.date.today()
    s = settings()
    acts = list(store.load("activities.json", {}).values())
    daily = store.load("daily.json", {})
    weights = store.load("weights.json", WEIGHTS_DEFAULT)
    nutr = store.load("nutrition.json", {})
    metrics = store.load("metrics.json", {})
    strength = list(store.load("strength.json", {}).values())
    manual = store.load("manual_records.json", [])
    run_target = int(s.get("ziel_laeufe") or 0)
    gym_target = int(s.get("ziel_gym") or 0)

    goal, goal_src = _goal_weight(s, nutr, metrics)
    w = weight_mod.analyze(weights, goal_kg=goal, today=today)
    w["goal_source"] = goal_src
    w["weighin_streak"] = weight_mod.weighin_streak(weights, today)
    trend = w.get("trend")
    day = daily.get(today.isoformat()) or {}
    n = nutrition_mod.analyze(nutr, today, goal_kg=goal, trend_kg=trend, weight_series=w.get("series"),
                              garmin_total_kcal=day.get("total_kcal"))
    n["logged_streak"] = nutrition_mod.logged_streak(nutr, today)
    planned = metrics.get("planned") or []
    run_plan = next((p for p in planned if "run" in (p.get("sport") or "").lower() or not p.get("sport")), None)
    r = running_mod.analyze(acts, today, run_target, prs=metrics.get("prs"), predictions=metrics.get("predictions"),
                            pred_hist=metrics.get("pred_hist"), vo2max=metrics.get("vo2max"),
                            vo2_hist=metrics.get("vo2_hist"), planned=run_plan)
    strength_acts = [a for a in acts if a.get("kind") == "strength"]
    g = gym_mod.analyze(strength, manual, strength_acts, today, gym_target)
    wk = goals_mod.weekly(acts, daily, run_target, gym_target, today)
    m = goals_mod.metrics(acts, None, g, w, wk, daily, w["weighin_streak"], n["logged_streak"], r.get("prs"))
    earned = store.load("achievements.json", {})
    badge_list, earned2, new = goals_mod.badges(m, earned, today, goals_mod.achieved_dates(acts))
    if new:
        store.save("achievements.json", earned2)
        print(f"[erfolge] neu: {', '.join(new)}")
    t = tips_mod.build(w, n, r, g, wk, today)
    return {"today": today, "settings": s, "weight": w, "nutrition": n, "running": r, "gym": g,
            "week": wk, "badges": badge_list, "new_badges": new, "tips": t, "daily": day,
            "planned": planned, "metrics": metrics}


def publish_status(st=None):
    st = st or state()
    g_conn = garmin_sync.is_connected()
    y_conn = yazio.is_connected()
    g = st.get("garmin") or {}
    y = st.get("yazio") or {}
    if st.get("sync_running"):
        s = "synchronisiert"
    elif not g_conn and not y_conn:
        s = "nicht angemeldet"
    elif (g_conn and g.get("needs_login")) or (y_conn and y.get("needs_login")):
        s = "neu anmelden"
    elif g_conn and g.get("last_error") and (g.get("last_error_at") or "") >= (g.get("last_sync") or ""):
        s = "fehler"
    else:
        s = "bereit"
    nxt = next_run_at(datetime.datetime.now())
    publish.state("status", s, {
        "garmin": {"connected": g_conn, "last_sync": g.get("last_sync"), "last_error": g.get("last_error"),
                   "needs_login": bool(g.get("needs_login")) and g_conn, "mfa_pending": garmin_sync.mfa_pending(),
                   "partial_errors": g.get("partial_errors") or []},
        "yazio": {"connected": y_conn, "last_sync": y.get("last_sync"), "last_error": y.get("last_error"),
                  "needs_login": bool(y.get("needs_login")) and y_conn},
        "next_sync": nxt.isoformat(timespec="minutes") if nxt else None,
        "sync_hours": SYNC_HOURS, "version": publish.VERSION,
    })
    if st.get("last_sync"):
        publish.state("letzter_sync", st["last_sync"])


def refresh():
    """Neu rechnen und alles veröffentlichen (ohne Netzwerkabruf)."""
    try:
        c = compute()
    except Exception as e:
        print(f"[auswertung] fehlgeschlagen: {e}\n{traceback.format_exc()}")
        publish_status()
        return
    s, w, n, r, g, wk, d = c["settings"], c["weight"], c["nutrition"], c["running"], c["gym"], c["week"], c["daily"]
    publish_status()
    for key in ("zielgewicht", "gewicht_eintragen", "ziel_laeufe", "ziel_gym", "rekord_kg", "rekord_wdh"):
        publish.state(key, s.get(key))
    opts = gym_mod.exercise_options(g.get("seen_ids") or [])
    if s.get("uebung") and s["uebung"] not in opts:
        opts = sorted(opts + [s["uebung"]], key=str.lower)
    publish.publish_select("uebung", opts, s.get("uebung"))
    publish.state("uebung", s.get("uebung"))

    nt = n.get("today") or {}
    publish.state("heute", d.get("steps"), {
        "date": c["today"].isoformat(), "steps": d.get("steps"), "step_goal": d.get("step_goal"),
        "active_kcal": d.get("active_kcal"), "total_kcal": d.get("total_kcal"),
        "intensity_min": goals_mod.intensity_minutes(d) if d else None,
        "kcal": nt.get("kcal"), "kcal_goal": nt.get("goal"), "kcal_remaining": nt.get("remaining"),
        "protein": nt.get("protein"), "protein_goal": nt.get("protein_goal"),
        "carbs": nt.get("carbs"), "carbs_goal": nt.get("carbs_goal"), "fat": nt.get("fat"), "fat_goal": nt.get("fat_goal"),
        "water_ml": nt.get("water_ml"), "water_goal": nt.get("water_goal"),
        "weight_trend": w.get("trend"), "weight_last": w.get("last_kg"), "weight_last_date": w.get("last_date"),
        "weighed_today": w.get("last_date") == c["today"].isoformat(),
        "ran_today": any(x["date"] == c["today"].isoformat() for x in r.get("recent") or []),
        "next": r.get("next"), "yazio": n.get("has_data"),
    })
    publish.state("schritte", d.get("steps"))
    publish.state("aktiv_kcal", d.get("active_kcal"))
    publish.state("kalorien", nt.get("kcal"))
    publish.state("kalorien_ziel", nt.get("goal"))
    publish.state("protein", nt.get("protein"))
    publish.state("gewicht", w.get("last_kg"))
    publish.state("gewicht_trend", w.get("trend"))
    publish.state("abnahme", w.get("tempo", {}).get("label") if w.get("has_data") else "keine Daten",
                  {k: v for k, v in w.items()})
    publish.state("ernaehrung", nt.get("kcal") if n.get("has_data") else "keine Daten", n)
    publish.state("laufen", r.get("week_runs"), {k: v for k, v in r.items() if k != "last_run"})
    publish.state("lauf_km_woche", r.get("week_km"))
    publish.state("pace_locker", (r.get("pace") or {}).get("easy_pace"))
    publish.state("prognose_5k", (r.get("predictions") or {}).get("5k"))
    publish.state("vo2max", r.get("vo2max"))
    publish.state("gym", g.get("sessions_month"), g)
    cur = wk["current"]
    publish.state("woche", cur["pct"], {**wk, "history": wk["history"][-8:]})
    publish.state("serie", wk["streak"])
    earned = [b for b in c["badges"] if b["earned"]]
    nxt = sorted([b for b in c["badges"] if not b["earned"]], key=lambda b: -b["progress"])[:4]
    publish.state("erfolge", len(earned), {"badges": c["badges"], "earned": len(earned), "total": len(c["badges"]),
                                         "latest": sorted(earned, key=lambda b: b["earned"], reverse=True)[:3],
                                         "next": nxt, "new": c["new_badges"]})
    t = c["tips"]
    publish.state("tipp", t[0]["title"] if t else "", {"tips": t})
    pl = c["planned"]
    publish.state("plan", pl[0]["title"] if pl else "nichts geplant", {"items": pl})


# ---------------------------------------------------------------- Zeitplan
def parse_hours(raw) -> list:
    out = []
    for part in str(raw or "").split(","):
        try:
            h = int(part.strip())
        except ValueError:
            continue
        if 0 <= h <= 23 and h not in out:
            out.append(h)
    return sorted(out) or [6, 12, 20]


def next_run_at(now: datetime.datetime):
    cands = []
    for h in SYNC_HOURS:
        t = now.replace(hour=h, minute=5, second=0, microsecond=0)
        if t <= now:
            t += datetime.timedelta(days=1)
        cands.append(t)
    return min(cands) if cands else None


def scheduler_loop():
    nxt = next_run_at(datetime.datetime.now())
    print(f"[zeitplan] Sync um {SYNC_HOURS} Uhr (jeweils :05), nächster {nxt:%d.%m. %H:%M}")
    last_day = datetime.date.today()
    while True:
        time.sleep(max(5.0, min(300.0, (nxt - datetime.datetime.now()).total_seconds())))
        now = datetime.datetime.now()
        if now.date() != last_day:  # Tageswechsel: Woche/Heute neu rechnen
            last_day = now.date()
            refresh()
        if now >= nxt:
            if garmin_sync.is_connected() or yazio.is_connected():
                full_sync("zeitplan", force=True)
            nxt = next_run_at(datetime.datetime.now())
