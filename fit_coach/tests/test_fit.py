"""Tests mit synthetischen Daten (ohne Netzwerk). Aufruf:
    cd fit_coach && python -m pytest -q tests
"""
import os
import sys
import json
import datetime
import importlib

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)

import fakes  # noqa: E402

TODAY = fakes.TODAY


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FIT_DATA_DIR", str(tmp_path))
    import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    import garmin_sync, publish, yazio, sync
    monkeypatch.setattr(garmin_sync, "TOKEN_DIR", str(tmp_path / "garmin_tokens"))
    os.makedirs(tmp_path / "garmin_tokens", exist_ok=True)
    mq = fakes.FakeMQTT()
    monkeypatch.setattr(publish, "_client", mq)
    fg = fakes.FakeGarmin()
    monkeypatch.setattr(garmin_sync, "client", lambda: fg)
    fy = fakes.FakeYazioHTTP()
    monkeypatch.setattr(yazio.requests, "post", fy.post)
    monkeypatch.setattr(yazio.requests, "get", fy.get)
    monkeypatch.setattr(yazio.time, "sleep", lambda s: None)
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    return {"store": store, "mq": mq, "garmin": fg, "yazio": fy, "tmp": tmp_path}


def attrs(mq, key):
    return json.loads(mq.msgs[f"fit_coach/{key}/attributes"])


def st(mq, key):
    return mq.msgs.get(f"fit_coach/{key}/state")


# ------------------------------------------------------------------ Gewicht
def test_weight_trend_rate_and_tempo():
    import weight
    src = {"garmin": {}, "manual": {}, "yazio": {}}
    d = TODAY - datetime.timedelta(days=40)
    i = 0
    while d <= TODAY:
        if i % 2 == 0:
            src["garmin"][d.isoformat()] = 80 - 0.08 * i + (0.5 if i % 4 == 0 else -0.5)
        d += datetime.timedelta(days=1)
        i += 1
    src["manual"][TODAY.isoformat()] = 76.5
    res = weight.analyze(src, goal_kg=70, today=TODAY)
    assert res["has_data"] and res["last_source"] == "Dashboard"
    # ~0,08 kg/Tag = 0,56 kg/Woche ≈ 0,7 %/Woche -> Zielkorridor
    assert -0.75 < res["rate_kg_week"] < -0.35
    assert res["tempo"]["kind"] == "good"
    assert 0 < res["progress_pct"] < 100 and res["eta"] > TODAY.isoformat()
    # Ausreißer verwerfen, Priorität manuell > Garmin
    src["garmin"]["2026-10-01"] = 500
    merged = {p["date"]: p for p in weight.merge_sources(src)}
    assert "2026-10-01" not in merged or merged["2026-10-01"]["kg"] < 100


def test_weight_too_fast_and_little_data():
    import weight
    fast = {"manual": {(TODAY - datetime.timedelta(days=i)).isoformat(): 80 - (20 - i) * 0.25 for i in range(0, 21)}}
    res = weight.analyze(fast, goal_kg=65, today=TODAY)
    assert res["tempo"]["kind"] == "warn"  # 1,75 kg/Woche > 1 %
    few = weight.analyze({"manual": {TODAY.isoformat(): 70}}, today=TODAY)
    assert few["rate_kg_week"] is None and few["tempo"]["kind"] == "neutral"
    assert weight.analyze({}, today=TODAY)["has_data"] is False


# --------------------------------------------------------------- Ernährung
def test_nutrition_parse_and_hints():
    import nutrition
    p = nutrition.parse_daily_summary(fakes.yazio_summary(TODAY - datetime.timedelta(days=1)))
    assert p["goal_kcal"] == 1700 and p["meals"] >= 3 and p["kcal"] > 1000
    days = {}
    for i in range(1, 8):
        d = (TODAY - datetime.timedelta(days=i)).isoformat()
        days[d] = {"kcal": 1050, "protein": 45, "meals": 3, "goal_kcal": 1600, "goal_effective": 1600}
    res = nutrition.analyze(days, TODAY, goal_kg=65, trend_kg=75)
    ids = {h["id"] for h in res["hints"]}
    assert "low_intake" in ids and "protein_low" in ids
    assert res["protein_target"]["low"] == 78  # 1,2 g × 65 kg


def test_expenditure_estimate():
    import nutrition, weight
    days, wsrc = {}, {"manual": {}}
    for i in range(0, 29):
        d = TODAY - datetime.timedelta(days=i)
        days[d.isoformat()] = {"kcal": 1800, "protein": 90, "meals": 4, "goal_kcal": 1800}
        wsrc["manual"][d.isoformat()] = 75 - (28 - i) * (0.5 / 7)  # 0,5 kg/Woche
    w = weight.analyze(wsrc, today=TODAY)
    est = nutrition.expenditure_estimate(days, w["series"], TODAY)
    assert est["ok"]
    # 0,5 kg/Woche × 7700 / 7 ≈ 550 kcal Defizit -> Verbrauch ≈ 2.350 (Trend hinkt etwas nach)
    assert 2050 <= est["kcal"] <= 2450, est


# ------------------------------------------------------------------- Laufen
def test_running_analysis():
    import running
    acts = [running.normalize_activity(a) for a in fakes.make_activities()]
    res = running.analyze(acts, TODAY, 3, prs=running.parse_prs(fakes.FakeGarmin().get_personal_record()))
    assert res["has_data"] and res["total_runs"] >= 25
    assert res["pace"]["easy_pace"] and res["pace"]["easy_pace_delta"] < 0  # schneller geworden
    labels = [p["label"] for p in res["prs"]]
    assert labels == ["1 km", "5 km", "Längster Lauf"]
    assert res["next"]["title"]
    assert len(res["weeks"]) == 12


def test_volume_jump_hint():
    import running
    base = []
    for wk, km in ((2, 4.0), (1, 4.0), (0, 9.0)):
        day = running.monday(TODAY) - datetime.timedelta(weeks=wk)
        base.append({"id": wk, "date": day.isoformat(), "start": day.isoformat() + " 18:00", "kind": "run", "km": km,
                     "sec": km * 450, "pace": 450, "easy": 0.9, "zones_min": [10, 20, 2, 0, 0], "m_per_beat": 1.0, "hr": 150, "name": ""})
    hints, _ = running.guardrails(base, TODAY)
    assert any(h["id"] == "volume_jump" for h in hints)


# ---------------------------------------------------------------------- Gym
def test_gym_records_and_manual():
    import gym
    sessions = []
    for n, d in enumerate(["2026-09-11", "2026-09-25", "2026-10-09"]):
        raw = fakes.exercise_sets(n, n)
        import fit_exercises
        sessions.append({"activity_id": n, "date": d, "exercises": fit_exercises.parse_exercise_sets(raw)})
    manual = [gym.manual_entry("Kniebeuge", 22.5, 10, TODAY)]
    res = gym.analyze(sessions, manual, [{"date": "2026-10-09", "start": "2026-10-09 19:00", "sec": 2400, "kind": "strength", "name": "x"}], TODAY, 1)
    names = {r["name"]: r for r in res["records"]}
    assert "Kniebeuge" in names and names["Kniebeuge"]["source"] == "manuell" and names["Kniebeuge"]["new"]
    assert names["Kniebeuge"]["e1rm"] == round(22.5 * (1 + 10 / 30), 1)
    assert res["pr_count"] >= 3
    assert any(p["name"] == "Liegestütze" for p in res["progression"])
    assert gym.epley(50, 15) is None


# ------------------------------------------------------------ Ziele/Abzeichen
def test_weekly_streak_and_badges():
    import goals, running
    acts = [running.normalize_activity(a) for a in fakes.make_activities()]
    wk = goals.weekly(acts, {}, 3, 0, TODAY)
    assert wk["streak"] >= 4
    m = goals.metrics(acts, None, {"sessions_total": 4, "pr_count": 2}, {"has_data": True, "start_kg": 78, "trend": 74.6, "progress_pct": 40},
                      wk, {}, 3, 8, [{"type": 3, "value": 2290}])
    lst, earned, new = goals.badges(m, {}, TODAY)
    got = {b["id"] for b in lst if b["earned"]}
    assert {"lauf_1", "lauf_10", "lauf_5km", "kg_3", "fuenf_40", "yazio_7", "rekord_1"} <= got
    assert "fuenf_35" not in got
    lst2, earned2, new2 = goals.badges(m, earned, TODAY + datetime.timedelta(days=1))
    assert new2 == [] and earned2 == earned  # bleibt verdient, nichts doppelt


# ------------------------------------------------------------------ Gesamt
def test_full_sync_end_to_end(env):
    import sync, garmin_sync, yazio
    # Garmin "angemeldet" (Token-Datei), Yazio-Login mit falschem und richtigem Passwort
    open(os.path.join(garmin_sync.TOKEN_DIR, "garmin_tokens.json"), "w").write("{}")
    with pytest.raises(yazio.YazioAuthError):
        yazio.login("jana@example.org", "falsch")
    assert len([c for c in env["yazio"].calls if c[0] == "POST"]) == 1  # kein Durchprobieren mit falschem Passwort
    yazio.login("jana@example.org", "geheim")
    tok = json.load(open(env["tmp"] / "yazio_token.json"))
    assert "password" not in json.dumps(tok) and tok["refresh_token"] == "RT"
    assert oct(os.stat(env["tmp"] / "yazio_token.json").st_mode)[-3:] == "600"

    assert sync.full_sync("test", force=True)
    mq = env["mq"]
    assert st(mq, "status") == "bereit"
    s = attrs(mq, "status")
    assert s["garmin"]["connected"] and s["yazio"]["connected"]
    w = attrs(mq, "abnahme")
    assert w["has_data"] and w["goal"] == 70.0 and w["goal_source"] == "Yazio" and w["measurements"] > 40
    n = attrs(mq, "ernaehrung")
    assert n["has_data"] and n["avg7_kcal"] and n["logged7"] >= 4
    assert n["expenditure"]["ok"], n["expenditure"]
    r = attrs(mq, "laufen")
    assert r["has_data"] and r["vo2max"] == 38.1 and r["predictions"]["5k"] == 2130
    assert r["next"]["source"] == "garmin"  # Garmin-Coach-Workout hat Vorrang
    assert len(r["prediction_history"]) > 5 and len(r["vo2_history"]) > 3
    g = attrs(mq, "gym")
    assert g["records"] and g["sessions_total"] >= 4
    assert attrs(mq, "erfolge")["earned"] >= 8
    assert attrs(mq, "tipp")["tips"]
    assert st(mq, "plan") == "Locker 25 min (Garmin Coach)"
    # Attribute bleiben unter der Recorder-Grenze von 16 KB
    for topic, payload in mq.msgs.items():
        if topic.endswith("/attributes"):
            assert len(payload) < 16000, (topic, len(payload))
    # Zweiter Sync: keine erneuten Rückblicke
    env["garmin"].calls.clear()
    sync._last_start["t"] = 0
    assert sync.full_sync("test2", force=True)
    calls = env["garmin"].calls
    assert "activities:40" in calls and "pred_hist" not in calls
    assert not any(c.startswith("weighins:") and c != f"weighins:{(TODAY - datetime.timedelta(days=14)).isoformat()}" for c in calls)


def test_dashboard_commands(env):
    import main, sync
    mq = env["mq"]
    main.on_command("gewicht_eintragen", "73.4")
    w = json.loads(mq.msgs["fit_coach/abnahme/attributes"])
    assert w["last_kg"] == 73.4 and w["last_source"] == "Dashboard"
    main.on_command("gewicht_eintragen", "12")  # unplausibel -> ignoriert
    assert json.loads(mq.msgs["fit_coach/abnahme/attributes"])["last_kg"] == 73.4
    main.on_command("gewicht_rueckgaengig", "PRESS")
    assert json.loads(mq.msgs["fit_coach/abnahme/attributes"])["has_data"] is False
    main.on_command("uebung", "Hüftstoß")
    main.on_command("rekord_kg", "40")
    main.on_command("rekord_wdh", "10")
    main.on_command("rekord_speichern", "PRESS")
    g = json.loads(mq.msgs["fit_coach/gym/attributes"])
    assert g["records"][0]["name"] == "Hüftstoß" and g["records"][0]["kg"] == 40
    main.on_command("ziel_laeufe", "2")
    assert sync.settings()["ziel_laeufe"] == 2
    main.on_command("rekord_rueckgaengig", "PRESS")
    assert json.loads(mq.msgs["fit_coach/gym/attributes"])["records"] == []


def test_discovery_payloads(env):
    import publish
    publish.discovery()
    mq = env["mq"]
    cfg = json.loads(mq.msgs["homeassistant/sensor/fit_coach_gewicht_trend/config"])
    assert cfg["default_entity_id"] == "sensor.fit_coach_gewicht_trend" and cfg["state_class"] == "measurement"
    num = json.loads(mq.msgs["homeassistant/number/fit_coach_zielgewicht/config"])
    assert num["command_topic"] == "fit_coach/zielgewicht/set" and num["mode"] == "box"
    sel = json.loads(mq.msgs["homeassistant/select/fit_coach_uebung/config"])
    assert sel["options"]
    for t, p in mq.msgs.items():
        if t.startswith("homeassistant/") and t.endswith("/config"):
            c = json.loads(p)
            assert c["unique_id"].startswith("fit_coach_") and c["availability_topic"] == "fit_coach/availability"


def test_web_pages(env):
    import main
    client = main.app.test_client()
    r = client.get("/")
    assert r.status_code == 200 and "Garmin verbinden" in r.get_data(as_text=True)
    r = client.post("/yazio/login", data={"email": "a@b.de", "password": "falsch"}, headers={"X-Ingress-Path": "/api/hassio_ingress/abc"})
    assert r.status_code == 303 and r.headers["Location"].startswith("/api/hassio_ingress/abc/?m=")


def test_badge_dates_from_activities():
    import goals, running
    acts = [running.normalize_activity(a) for a in fakes.make_activities()]
    dates = goals.achieved_dates(acts)
    runs = sorted([a for a in acts if a["kind"] == "run"], key=lambda a: a["start"])
    assert dates["lauf_1"] == runs[0]["date"] and dates["lauf_10"] == runs[9]["date"]
    assert dates["lauf_5km"] == next(r["date"] for r in runs if r["km"] >= 5)
    m = goals.metrics(acts, None, {}, None, goals.weekly(acts, {}, 3, 0, TODAY), {}, 0, 0, [])
    lst, earned, _ = goals.badges(m, {}, TODAY, dates)
    assert earned["lauf_1"] == runs[0]["date"]


def test_unknown_state_published_as_none(env):
    import publish
    publish.state("gewicht", None)
    assert env["mq"].msgs["fit_coach/gewicht/state"] == "None"
    publish.state("gewicht", 71.234)
    assert env["mq"].msgs["fit_coach/gewicht/state"] == "71.23"


def test_garmin_mfa_flow(env, monkeypatch):
    """Login mit Zwei-Faktor-Code: erst 'mfa', nach dem Code werden Tokens gespeichert."""
    import garmin_sync, sys, types
    calls = {}

    class G:
        def __init__(self, email=None, password=None, return_on_mfa=False, **kw):
            calls["init"] = (email, return_on_mfa)
            self.client = types.SimpleNamespace(dump=lambda p: open(os.path.join(p, "garmin_tokens.json"), "w").write("{}"))
        def login(self, tokenstore=None):
            return "needs_mfa", None
        def resume_login(self, state, code):
            if code != "123456":
                raise Exception("MFA code invalid")
            return None, None
    fake_mod = types.SimpleNamespace(Garmin=G)
    monkeypatch.setitem(sys.modules, "garminconnect", fake_mod)
    assert garmin_sync.start_login(" jana@example.org ", "pw") == "mfa"
    assert calls["init"] == ("jana@example.org", True) and garmin_sync.mfa_pending()
    assert not garmin_sync.is_connected()
    with pytest.raises(garmin_sync.GarminLoginError):
        garmin_sync.finish_mfa("000000")
    assert garmin_sync.mfa_pending()  # falscher Code: neuer Versuch möglich
    assert garmin_sync.finish_mfa("123 456") == "ok"
    assert garmin_sync.is_connected() and not garmin_sync.mfa_pending()


def test_web_garmin_login_with_mfa(env, monkeypatch):
    import main, sync, sys, types

    class G:
        def __init__(self, email=None, password=None, return_on_mfa=False, **kw):
            self.client = types.SimpleNamespace(dump=lambda p: open(os.path.join(p, "garmin_tokens.json"), "w").write("{}"))
        def login(self, tokenstore=None):
            return "needs_mfa", None
        def resume_login(self, state, code):
            return None, None
    monkeypatch.setitem(sys.modules, "garminconnect", types.SimpleNamespace(Garmin=G))
    started = []
    monkeypatch.setattr(sync, "full_sync_async", lambda reason, force=False: started.append(reason))
    c = main.app.test_client()
    hdr = {"X-Ingress-Path": "/api/hassio_ingress/tok"}
    r = c.post("/garmin/login", data={"email": "j@x.de", "password": "pw"}, headers=hdr)
    assert r.status_code == 303 and "Code" in r.headers["Location"] or "Code" in __import__("urllib.parse").parse.unquote(r.headers["Location"])
    page = c.get("/").get_data(as_text=True)
    assert "Bestätigungscode" in page and 'name="code"' in page
    r = c.post("/garmin/mfa", data={"code": "123456"}, headers=hdr)
    assert r.status_code == 303 and started == ["anmeldung"]
    page = c.get("/").get_data(as_text=True)
    assert "Garmin trennen" in page and "Jetzt synchronisieren" in page
    st = json.loads(env["mq"].msgs["fit_coach/status/attributes"])
    assert st["garmin"]["connected"] is True


def test_expired_garmin_tokens_ask_for_new_login(env, monkeypatch):
    import sync, garmin_sync

    class GarminConnectAuthenticationError(Exception):
        pass

    def boom():
        raise GarminConnectAuthenticationError("Username and password are required")
    open(os.path.join(garmin_sync.TOKEN_DIR, "garmin_tokens.json"), "w").write("{}")
    monkeypatch.setattr(garmin_sync, "client", boom)
    sync._last_start["t"] = 0
    assert sync.full_sync("test", force=True)
    assert st(env["mq"], "status") == "neu anmelden"
    assert attrs(env["mq"], "status")["garmin"]["needs_login"] is True
