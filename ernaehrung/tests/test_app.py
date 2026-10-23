"""Tests ohne Netz: Gemini und Open Food Facts werden ersetzt, BLS kommt aus einem echten
Auszug (178 Zeilen, BLS 4.0, CC BY 4.0, Max Rubner-Institut)."""
import datetime
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app"))
TMP = tempfile.mkdtemp()
os.environ.update(NUTRITION_DB=os.path.join(TMP, "e.db"), BLS_DB=os.path.join(TMP, "bls.db"),
                  PHOTO_DIR=os.path.join(TMP, "photos"), NUTRITION_SHARE=os.path.join(TMP, "share"),
                  RESTRICT_IPS="0", GEMINI_API_KEY="test")

import analyze  # noqa: E402
import bls  # noqa: E402
import db  # noqa: E402
import gemini  # noqa: E402
import off  # noqa: E402
import targets  # noqa: E402
import web  # noqa: E402
import garmin_bridge  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "bls_extract.csv")


@pytest.fixture(scope="session", autouse=True)
def setup():
    db.init()
    bls.import_file(FIXTURE)
    yield


@pytest.fixture
def client():
    return web.app.test_client()


def est(kcal, p, c, f, **kw):
    d = {"kcal": kcal, "protein_g": p, "carbs_g": c, "fat_g": f}
    d.update(kw)
    return d


# ---------------------------------------------------------------- BLS

def test_bls_import_units():
    egg = bls.get("E111100")
    assert egg["name"] == "Hühnerei roh"
    assert egg["per100"]["kcal"] == 135
    assert egg["per100"]["sodium_mg"] == pytest.approx(154)
    assert egg["per100"]["b12_ug"] == pytest.approx(2.7)
    assert bls.count() == 178


def test_bls_values():
    assert bls.parse_value("<LOD") == 0
    assert bls.parse_value("TR") == 0
    assert bls.parse_value("-") is None
    assert bls.parse_value("1,5") == 1.5


def test_bls_search_compound():
    assert bls.search("Haferflocken", 1)[0]["code"] == "C133000"
    assert bls.search("Vollkornbrot", 1)[0]["name"] == "Vollkornbrot"


def test_download_link():
    html = ('<a href="/assets/uploads/BLS_4_0_Dokumentation_DE.pdf">Doku</a>'
            '<a href="/assets/uploads/BLS_4_0_2025_DE.zip?token=ABCD-1234">Download BLS-Daten</a>')
    assert bls.find_download_link(html, "https://blsdb.de/download") == \
        "https://blsdb.de/assets/uploads/BLS_4_0_2025_DE.zip?token=ABCD-1234"
    assert bls.find_download_link('<a href="https://evil.example/BLS_4_0.zip">x</a>') is None
    # so liefert blsdb.de die Links aus (HTML-Entities, live 22.10.2026)
    enc = '<a href="&#47;assets&#47;uploads&#47;BLS&#95;4&#95;0&#95;2025&#95;DE&#46;zip?token=ASXD-1">D</a>'
    assert bls.find_download_link(enc, "https://blsdb.de/download") == \
        "https://blsdb.de/assets/uploads/BLS_4_0_2025_DE.zip?token=ASXD-1"


# ---------------------------------------------------------------- Abgleich

def test_match_prefers_cooked_rice_by_nutrients():
    it = analyze.match_item({"name": "Reis", "suchbegriff": "Reis poliert, gekocht", "menge_g": 200,
                             "naehrwerte_100g": est(130, 2.7, 28, 0.3)}, personal={})
    assert it["source"] == "bls" and "gekocht" in it["match_name"]


def test_match_falls_back_to_ai_when_db_disagrees():
    # Nur rohe Teigwaren im Auszug: 350 kcal vs. geschätzt 150 kcal gekocht -> KI-Schätzung
    it = analyze.match_item({"name": "Nudeln", "suchbegriff": "Teigwaren gekocht", "menge_g": 250,
                             "naehrwerte_100g": est(150, 5, 30, 1)}, personal={})
    assert it["source"] == "ki"
    assert it["per100"]["kcal"] == 150
    assert it["candidates"], "Alternativen aus dem BLS sollen angeboten werden"


def test_match_personal_food():
    f = db.upsert_food("custom", "custom-shake", "Mein Proteinshake", est(380, 75, 8, 5))
    personal = {bls.norm(f["name"]): f}
    it = analyze.match_item({"name": "Proteinshake", "suchbegriff": "Proteinpulver", "menge_g": 30,
                             "eigenes": "Mein Proteinshake", "naehrwerte_100g": est(370, 70, 10, 5)}, personal)
    assert it["source"] == "custom" and it["food_id"] == f["id"]


def test_rerank_switches_and_rejects(monkeypatch):
    items = [analyze.match_item({"name": "Reis", "suchbegriff": "Reis gekocht", "menge_g": 200,
                                 "naehrwerte_100g": est(130, 2.7, 28, 0.3)}, personal={}),
             analyze.match_item({"name": "Lachs", "suchbegriff": "Lachs", "menge_g": 120,
                                 "naehrwerte_100g": est(200, 20, 0, 13)}, personal={})]
    raw_code = next(c["ref"] for c in items[0]["candidates"] if "roh" in c["name"])
    monkeypatch.setattr(gemini, "generate_json",
                        lambda *a, **k: {"wahl": [{"i": 0, "code": raw_code}, {"i": 1, "code": None}]})
    assert analyze.rerank(items, "Reis und Lachs") == 2
    assert items[0]["ref"] == raw_code
    assert items[1]["source"] == "ki"


def test_analyze_end_to_end(monkeypatch):
    def fake(prompt, image_b64=None, mime=None, schema=None, max_tokens=None):
        if "Bundeslebensmittelschlüssel zu" in prompt:
            return {"wahl": []}
        assert "Rühreier" in prompt
        return {"titel": "Rührei mit Brot", "kategorie": "fruehstueck", "hinweis": "",
                "items": [
                    {"name": "Rührei", "suchbegriff": "Hühnerei", "menge_g": 110, "sicherheit": "mittel",
                     "naehrwerte_100g": est(150, 12.5, 1, 11)},
                    {"name": "Vollkornbrot", "suchbegriff": "Vollkornbrot", "menge_g": 45,
                     "naehrwerte_100g": est(215, 7, 39, 1.2)},
                    {"name": "Kaffee", "suchbegriff": "Kaffee Getränk", "menge_g": 200, "getraenk": True,
                     "naehrwerte_100g": est(2, 0.1, 0, 0, water_g=99)},
                ]}
    monkeypatch.setattr(gemini, "generate_json", fake)
    r = analyze.analyze(text="2 Rühreier mit Vollkornbrot und einem Kaffee")
    assert [i["source"] for i in r["items"]][:2] == ["bls", "bls"]
    assert r["items"][2]["per100"]["water_ml"] == 99  # KI-Schätzung mit water_g -> water_ml
    assert r["category"] == "fruehstueck"


# ---------------------------------------------------------------- Open Food Facts

def test_off_parse_units():
    p = off.parse_product({"code": "4000000000000", "product_name": "Skyr", "brands": "Arla",
                           "product_quantity_unit": "g",
                           "nutriments": {"energy-kcal_100g": 63, "proteins_100g": 11, "carbohydrates_100g": 4,
                                          "sugars_100g": 4, "fat_100g": 0.2, "salt_100g": 0.1,
                                          "calcium_100g": 0.12, "vitamin-d_100g": 0.0000011}})
    assert p["per100"]["sodium_mg"] == pytest.approx(40)
    assert p["per100"]["calcium_mg"] == pytest.approx(120)
    assert p["per100"]["vitd_ug"] == pytest.approx(1.1)


def test_barcode_checksum():
    assert off.valid_barcode("4006381333931")
    assert not off.valid_barcode("4006381333932")


def test_barcode_endpoint_caches(client, monkeypatch):
    calls = []

    def fake_lookup(code):
        calls.append(code)
        return off.parse_product({"code": code, "product_name": "Haferdrink", "product_quantity_unit": "ml",
                                  "serving_quantity": 250,
                                  "nutriments": {"energy-kcal_100g": 46, "carbohydrates_100g": 6.7,
                                                 "proteins_100g": 1, "fat_100g": 1.5}})
    monkeypatch.setattr(off, "lookup", fake_lookup)
    r1 = client.post("/api/v1/barcode", json={"code": "4006381333931"})
    r2 = client.post("/api/v1/barcode", json={"code": "4006381333931"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(calls) == 1
    assert r1.json["is_liquid"] is True and r1.json["per100"]["water_ml"] > 80


# ---------------------------------------------------------------- Ziele

def test_targets_rest_vs_hard_day():
    s = {"profile": {"weight_kg": 80, "height_cm": 183, "age": 38, "sex": "male"}}
    rest = targets.compute(s, {"activities": []})
    hard = targets.compute(s, {"activities": [
        {"type": "cycling", "duration_min": 120, "kcal": 1400, "training_load": 180}]})
    assert rest["day_type"] == "ruhetag" and hard["day_type"] == "hart"
    assert hard["targets"]["carbs_g"] == 8 * 80
    assert hard["targets"]["kcal"] > rest["targets"]["kcal"] + 1000
    assert rest["targets"]["protein_g"] == round(1.8 * 80)
    t = rest["targets"]
    fat_share = t["fat_g"] * 9 / t["kcal"]
    assert 0.19 <= fat_share <= 0.36
    assert t["magnesium_mg"] == 350 and t["vitc_mg"] == 110 and t["iron_mg"] == 11


def test_goal_deficit_not_on_hard_days():
    s = {"profile": {"weight_kg": 80, "height_cm": 183, "age": 38, "sex": "male"}, "goal": "abnehmen"}
    hard = targets.compute(s, {"activities": [{"type": "running", "duration_min": 100, "kcal": 1100}]})
    assert hard["energy"]["goal_pct_applied"] == 0
    rest = targets.compute(s, {"activities": []})
    assert rest["energy"]["goal_pct_applied"] == -15


def test_profile_from_garmin_when_settings_empty():
    prof, src = targets.resolve_profile({"weight_kg": None}, {"weight_kg": 77.5, "age": 40})
    assert prof["weight_kg"] == 77.5 and src["weight_kg"] == "garmin"


# ---------------------------------------------------------------- API

def test_meal_flow(client, monkeypatch):
    monkeypatch.setattr(garmin_bridge, "training_today", lambda max_age_s=120, weight_entity=None: None)
    today = datetime.date.today().isoformat()
    body = {"date": today, "time": "07:30", "category": "fruehstueck", "method": "text",
            "items": [{"name": "Haferflocken", "amount_g": 60, "source": "bls", "ref": "C133000"},
                      {"name": "Milch", "amount_g": 200, "source": "bls", "ref": "M111200"}],
            "save_favorite": True, "favorite_title": "Porridge"}
    r = client.post("/api/v1/meals", json=body)
    assert r.status_code == 201, r.json
    meal = r.json
    assert meal["items"][0]["food_id"]
    d = client.get(f"/api/v1/day?date={today}").json
    assert d["totals"]["kcal"] == pytest.approx(348 * 0.6 + bls.get("M111200")["per100"]["kcal"] * 2, rel=0.01)
    assert d["categories"]["fruehstueck"]["meals"][0]["id"] == meal["id"]
    # Menge ändern
    items = meal["items"]
    items[0]["amount_g"] = 80
    r = client.put(f"/api/v1/meals/{meal['id']}", json={"items": items})
    assert r.json["items"][0]["amount_g"] == 80
    # Favorit wieder eintragen
    favs = client.get("/api/v1/favorites").json
    assert favs and favs[0]["title"] == "Porridge"
    r = client.post(f"/api/v1/favorites/{favs[0]['id']}/log", json={"date": today, "category": "snack"})
    assert r.status_code == 201
    # Wasser
    assert client.post("/api/v1/water", json={"ml": 250, "date": today}).status_code == 201
    d = client.get(f"/api/v1/day?date={today}").json
    assert d["totals"]["water_ml"] >= 250
    w = client.get("/api/v1/week").json
    assert len(w["days"]) == 7 and w["logged_days"] >= 1
    csv_text = client.get("/api/v1/export.csv").get_data(as_text=True)
    assert "Haferflocken" in csv_text
    assert client.get("/api/v1/frequent").status_code == 200
    assert client.delete(f"/api/v1/meals/{meal['id']}").status_code == 200


def test_search_and_custom_food(client):
    r = client.post("/api/v1/foods", json={"name": "Skyr Natur", "per100": {"kcal": 63, "protein_g": 11}})
    assert r.status_code == 200
    s = client.get("/api/v1/search?q=skyr").json
    assert s["personal"][0]["name"] == "Skyr Natur"
    s = client.get("/api/v1/search?q=Banane").json
    assert s["bls"][0]["name"] == "Banane roh"


def test_ip_guard():
    web.RESTRICT = True
    try:
        c = web.app.test_client()
        r = c.get("/api/v1/status", environ_base={"REMOTE_ADDR": "192.168.1.50"})
        assert r.status_code == 403
        r = c.get("/api/v1/status", environ_base={"REMOTE_ADDR": "172.30.32.2"})
        assert r.status_code == 200
    finally:
        web.RESTRICT = False


def test_analyze_endpoint_errors(client, monkeypatch):
    assert client.post("/api/v1/analyze", json={}).status_code == 400

    def boom(*a, **k):
        raise gemini.GeminiError("HTTP 503")
    monkeypatch.setattr(gemini, "generate_json", boom)
    r = client.post("/api/v1/analyze", json={"text": "Apfel"})
    assert r.status_code == 502 and "KI-Analyse" in r.json["error"]


def test_gemini_quota_falls_back_fast(monkeypatch):
    calls = []

    class R:
        def __init__(self, code, body=None, text=""):
            self.status_code, self._b, self.text = code, body, text

        def json(self):
            return self._b

    def post(url, **kw):
        model = url.split("/models/")[1].split(":")[0]
        calls.append(model)
        if model == gemini.MODEL:
            return R(429, text="quota")
        if model == "old-lite":
            return R(404, text="no longer available, use models/new-lite instead")
        return R(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]})
    monkeypatch.setattr(gemini.requests, "post", post)
    monkeypatch.setattr(gemini, "_list_flash_models", lambda: ["old-lite"])
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    gemini._state.update(fallback=None, primary_down_until=0.0, dead=set())
    assert gemini.generate_json("x") == {"ok": 1}
    assert calls == [gemini.MODEL, "old-lite", "new-lite"]
    calls.clear()
    assert gemini.generate_json("y") == {"ok": 1}
    assert calls == ["new-lite"]  # Abkühlphase: direkt das funktionierende Ausweichmodell


def test_planned_day_type_before_training():
    s = {"profile": {"weight_kg": 80, "height_cm": 183, "age": 38, "sex": "male"}}
    plan = [{"type": "bike", "text": "Lange Radeinheit + Koppellauf (Sa oder So)"}]
    r = targets.compute(s, {"activities": [], "plan_items": plan})
    assert r["day_type"] == "hart" and r["day_source"] == "geplant"
    # sobald trainiert wurde, zählt das Aufgezeichnete
    r = targets.compute(s, {"activities": [{"type": "strength_training", "duration_min": 50, "kcal": 300}],
                            "plan_items": plan})
    assert r["day_type"] == "leicht" and r["day_source"] == "garmin"


def test_protein_by_goal_and_energy_availability_floor():
    base = {"profile": {"weight_kg": 80, "height_cm": 183, "age": 38, "sex": "male"}}
    assert targets.compute(base, {"activities": []})["protein_g_per_kg"] == 1.8
    cut = dict(base, goal="abnehmen", goal_adjust_pct=-40)
    r = targets.compute(cut, {"activities": []})
    assert r["protein_g_per_kg"] == 2.2
    assert r["energy"]["ea_floor"] is True
    assert r["energy"]["energy_availability"] >= 29.9
    own = dict(base, protein_g_per_kg=1.6)
    assert targets.compute(own, {"activities": []})["targets"]["protein_g"] == 128


# ---------------------------------------------------------------- 0.3.0

import ai  # noqa: E402
import groups  # noqa: E402
import recommend  # noqa: E402
import summary  # noqa: E402


def test_bls_new_nutrients_and_plural_search():
    lachs = bls.get("T410100")["per100"]
    assert lachs["omega3_mg"] > 1000          # EPA + DHA addiert, g -> mg
    assert lachs["iodine_ug"] is not None
    assert bls.search("Linsen", 1)[0]["name"].startswith("Linse")
    assert bls.search("Quark", 1)[0]["code"].startswith("M")   # kein Quark-Gericht vorn


def test_groups():
    assert groups.classify("Lachs roh", "bls", "T410100", bls.get("T410100")["per100"]) == "fisch_fett"
    assert groups.classify("Dorsch/Kabeljau, roh", "bls", "T204100", bls.get("T204100")["per100"]) == "fisch"
    assert groups.classify("Hafer Flocken", "bls", "C133000") == "vollkorn"
    assert groups.classify("Reis poliert, roh", "bls", "C352000") == "getreide"
    assert groups.classify("Tofu", "bls", "H861000") == "huelsenfruechte"
    assert groups.classify("Walnuss", "bls", "H120100") == "nuesse"
    assert groups.classify("Spaghetti Bolognese", "ki") == "fleisch"
    assert groups.classify("Linsencurry", "ki", ai_group="huelsenfruechte") == "huelsenfruechte"
    assert groups.classify("Gemischter Salat", "ki") == "gemuese"


def test_candidates_resolve_from_codes():
    c = {f["key"]: f for f in recommend.candidates("pescetarisch")}
    assert "lachs" in c and "magerquark" in c and c["lachs"]["bls_code"] == "T410100"
    veg = {f["key"] for f in recommend.candidates("vegetarisch")}
    assert "lachs" not in veg and "magerquark" in veg
    vegan = {f["key"] for f in recommend.candidates("vegan")}
    assert "magerquark" not in vegan and "tofu" in vegan


def _day(totals, targets, **kw):
    d = {"date": datetime.date.today().isoformat(), "totals": totals, "targets": targets,
         "target_kind": {"sugar_g": "max", "satfat_g": "max"}, "progress": {k: 0 for k in targets},
         "profile": {"weight_kg": 78}, "meals_count": 2, "protein_meals": 0, "protein_meal_min_g": 20,
         "categories": {}, "activities": [], "day_type": "leicht", "day_source": "garmin"}
    d.update(kw)
    return d


def test_day_recommendations_evening_protein_gap():
    tg = {"kcal": 2500, "protein_g": 140, "carbs_g": 300, "fat_g": 80, "fiber_g": 30, "water_ml": 2700,
          "sugar_g": 60, "satfat_g": 27, "iron_mg": 11, "magnesium_mg": 350, "calcium_mg": 1000,
          "potassium_mg": 4000, "zinc_mg": 14, "iodine_ug": 150, "omega3_mg": 250, "vitc_mg": 110, "b12_ug": 4}
    tot = {k: 0 for k in tg} | {"kcal": 1500, "protein_g": 50, "carbs_g": 200, "water_ml": 2500, "fiber_g": 25}
    now = datetime.datetime.combine(datetime.date.today(), datetime.time(19, 30))
    recs = recommend.day_recommendations(_day(tot, tg), "pescetarisch", now)
    ids = [r["id"] for r in recs]
    assert "protein_verteilung" in ids and "essen" in ids
    foods = next(r for r in recs if r["id"] == "essen")["foods"]
    assert foods and any(f["protein_g"] >= 20 for f in foods)
    assert sum(f["kcal"] for f in foods) <= 1000 + 150


def test_day_recommendations_before_training():
    tg = {"kcal": 3000, "protein_g": 140, "carbs_g": 500, "fat_g": 80, "fiber_g": 30, "water_ml": 3000}
    tot = {k: 0 for k in tg} | {"kcal": 400, "carbs_g": 60, "protein_g": 20, "water_ml": 300}
    now = datetime.datetime.combine(datetime.date.today(), datetime.time(10, 0))
    d = _day(tot, tg, day_type="hart", day_source="geplant", plan_text="Lange Radeinheit")
    recs = recommend.day_recommendations(d, "pescetarisch", now)
    assert recs[0]["id"] == "vor_training"
    essen = next(r for r in recs if r["id"] == "essen")
    assert any(f["carbs_g"] >= 25 for f in essen["foods"])


def test_week_recommendations_fish_and_legumes(client, monkeypatch):
    monkeypatch.setattr(garmin_bridge, "training_today", lambda max_age_s=120, weight_entity=None: None)
    base = datetime.date.today() - datetime.timedelta(days=1)
    for i in range(3):
        dd = (base - datetime.timedelta(days=i)).isoformat()
        r = client.post("/api/v1/meals", json={"date": dd, "time": "12:00", "category": "mittagessen", "items": [
            {"name": "Reis", "amount_g": 900, "source": "bls", "ref": "C352000"},
            {"name": "Hühnerei", "amount_g": 300, "source": "bls", "ref": "E111100"}]})
        assert r.status_code == 201
    w = summary.week(base.isoformat())
    ids = [r["id"] for r in w["recommendations"]]
    assert "fisch" in ids and "huelsen" in ids
    assert w["food_groups"]["grams"]["ei"] >= 900


def test_copy_quick_and_no_photo(client):
    today = datetime.date.today().isoformat()
    r = client.post("/api/v1/meals", json={"date": today, "category": "snack", "photo": "data:image/jpeg;base64,AAAA",
                                          "items": [{"name": "Banane", "amount_g": 120, "source": "bls",
                                                     "ref": "F503100"}]})
    m = r.json
    assert m.get("photo") is None
    assert not os.path.exists(os.path.join(TMP, "photos"))
    c = client.post(f"/api/v1/meals/{m['id']}/copy", json={}).json
    assert c["id"] != m["id"] and c["items"][0]["name"] == "Banane"
    assert c["items"][0]["food_group"] == "obst"
    q = client.post("/api/v1/quick", json={"kcal": 350, "protein_g": 20, "name": "Riegel"})
    assert q.status_code == 201 and round(q.json["items"][0]["per100"]["kcal"]) == 350
    y = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    r = client.post("/api/v1/copy_category", json={"from": y, "to": today, "category": "mittagessen"})
    assert r.status_code == 201
    d = client.get(f"/api/v1/day?date={today}").json
    assert "recommendations" in d


def test_local_ai_provider(monkeypatch):
    calls = []

    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def post(url, headers=None, json=None, timeout=None):
        calls.append((url, json))
        return R()
    monkeypatch.setattr(ai, "PROVIDER", "lokal")
    monkeypatch.setattr(ai, "LOCAL_URL", "http://192.168.1.20:11434")
    monkeypatch.setattr(ai, "LOCAL_MODEL", "qwen2.5vl:7b")
    monkeypatch.setattr(ai.requests, "post", post)
    assert ai.generate_json("x", image_b64="AAAA", schema={"type": "object"}) == {"ok": True}
    url, body = calls[0]
    assert url == "http://192.168.1.20:11434/v1/chat/completions"
    assert body["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert body["response_format"]["type"] == "json_schema"


def test_recipe_servings(client):
    r = client.post("/api/v1/favorites", json={"title": "Linsencurry", "servings": 4, "items": [
        {"name": "Linsen", "amount_g": 800, "source": "bls", "ref": "H861000"}]})
    fav = r.json
    assert fav["servings"] == 4
    m = client.post(f"/api/v1/favorites/{fav['id']}/log", json={}).json
    assert m["items"][0]["amount_g"] == 200


def test_zz_delete_all(client):
    assert client.delete("/api/v1/data", json={}).status_code == 400
    assert client.delete("/api/v1/data", json={"confirm": "LÖSCHEN"}).status_code == 200
    assert db.list_favorites() == []
