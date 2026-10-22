"""HTTP-Schnittstelle: Web-App (über HA-Ingress) und REST-API /api/v1/...

Die REST-API ist dieselbe, die die Web-App nutzt - Home Assistant oder andere
Add-ons können sie im internen Netz ebenfalls abfragen (Phase 2). Zugriff ist auf
Ingress und das interne Supervisor-Netz (172.30.32.0/23) beschränkt.
"""
import base64
import csv
import datetime
import io
import ipaddress
import os
import threading

from flask import Flask, Response, jsonify, request, send_from_directory, abort

import analyze
import bls
import db
import gemini
import nutrients as N
import off
import summary

VERSION = os.environ.get("APP_VERSION", "dev")
PHOTO_DIR = os.environ.get("PHOTO_DIR", "/data/photos")
STATIC = os.path.join(os.path.dirname(__file__), "static")
ALLOWED_NETS = [ipaddress.ip_network(n) for n in
                os.environ.get("ALLOWED_NETS", "172.30.32.0/23,127.0.0.0/8,::1/128").split(",") if n]
RESTRICT = os.environ.get("RESTRICT_IPS", "1") == "1"

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.json.sort_keys = False  # Reihenfolge der Kategorien/Nährstoffe beibehalten
on_change = []  # Callbacks nach Änderungen (MQTT-Veröffentlichung)


def _changed():
    for fn in on_change:
        threading.Thread(target=fn, daemon=True).start()


@app.before_request
def _guard():
    if not RESTRICT:
        return None
    try:
        ip = ipaddress.ip_address(request.remote_addr or "0.0.0.0")
    except ValueError:
        abort(403)
    if not any(ip in n for n in ALLOWED_NETS):
        abort(403)
    return None


@app.errorhandler(Exception)
def _err(e):
    code = getattr(e, "code", 500)
    if not isinstance(code, int):
        code = 500
    if code >= 500:
        print(f"[web] Fehler: {e!r}")
    return jsonify(error=str(getattr(e, "description", None) or e)), code


def _today():
    return datetime.date.today().isoformat()


# --------------------------------------------------------------------------
# Web-App
# --------------------------------------------------------------------------

@app.get("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/static/<path:name>")
def static_files(name):
    resp = send_from_directory(STATIC, name)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --------------------------------------------------------------------------
# Status / Einstellungen
# --------------------------------------------------------------------------

@app.get("/api/v1/status")
def status():
    return jsonify(version=VERSION, bls=bls.status, bls_count=bls.count(), gemini=gemini.configured(),
                   gemini_model=gemini.last_model() or gemini.MODEL, attribution=bls.ATTRIBUTION,
                   categories=db.CATEGORY_LABELS, nutrients={k: list(v) for k, v in N.NUTRIENTS.items()})


SETTING_KEYS = ("profile", "pal_base", "goal", "goal_adjust_pct", "protein_g_per_kg", "carbs_g_per_kg",
                "body_fat_pct",
                "target_overrides", "day_type_override", "keep_photos", "photo_ai")


@app.get("/api/v1/settings")
def get_settings():
    s = {k: db.get_setting(k) for k in SETTING_KEYS}
    if s["keep_photos"] is None:
        s["keep_photos"] = True
    if s["photo_ai"] is None:
        s["photo_ai"] = True
    return jsonify(s)


@app.put("/api/v1/settings")
def put_settings():
    data = request.get_json(force=True) or {}
    for k, v in data.items():
        if k in SETTING_KEYS:
            db.set_setting(k, v)
    _changed()
    return get_settings()


@app.post("/api/v1/bls/import")
def bls_import():
    threading.Thread(target=lambda: bls.ensure(auto_download=True, force=True), daemon=True).start()
    return jsonify(ok=True, status=bls.status)


# --------------------------------------------------------------------------
# Auswertung
# --------------------------------------------------------------------------

@app.get("/api/v1/day")
def get_day():
    return jsonify(summary.day(request.args.get("date") or _today()))


@app.get("/api/v1/week")
def get_week():
    return jsonify(summary.week(request.args.get("end"), int(request.args.get("days", 7))))


# --------------------------------------------------------------------------
# Erfassung
# --------------------------------------------------------------------------

@app.post("/api/v1/analyze")
def post_analyze():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    image = data.get("image")
    if image and "," in image[:100]:
        image = image.split(",", 1)[1]  # data:-URL
    if not text and not image:
        abort(400, "Text oder Foto fehlt")
    if image and db.get_setting("photo_ai") is False:
        abort(400, "Foto-Analyse ist in den Einstellungen ausgeschaltet")
    if not gemini.configured():
        abort(400, "Kein Gemini API Key hinterlegt (Add-on-Konfiguration)")
    try:
        result = analyze.analyze(text=text, image_b64=image, mime=data.get("mime") or "image/jpeg")
    except gemini.GeminiError as e:
        abort(502, f"KI-Analyse fehlgeschlagen: {e}")
    result.pop("raw", None)
    return jsonify(result)


@app.post("/api/v1/barcode")
def post_barcode():
    code = "".join(ch for ch in str((request.get_json(force=True) or {}).get("code", "")) if ch.isdigit())
    if not off.valid_barcode(code):
        abort(400, f"Ungültiger Barcode: {code or '-'}")
    try:
        food = analyze.barcode_food(code)
    except RuntimeError as e:
        abort(429, str(e))
    except Exception as e:
        print(f"[barcode] {code}: {e}")
        abort(502, "Open Food Facts gerade nicht erreichbar – später erneut versuchen oder Produkt selbst anlegen")
    if not food:
        abort(404, f"Produkt {code} nicht in Open Food Facts (oder ohne Nährwerte) - bitte manuell anlegen")
    return jsonify(food)


@app.get("/api/v1/search")
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify(personal=[], bls=[])
    nq = bls.norm(q)
    terms = bls._terms(q)
    personal = []
    for f in db.personal_foods(400):
        nn = bls.norm(f["name"] + " " + (f.get("brand") or ""))
        s = bls.score_name(terms, nn) if terms else (1.0 if nq in nn else 0)
        if s > 0.3 or nq in nn:
            personal.append((s + 0.3, f))
    personal.sort(key=lambda x: -x[0])
    return jsonify(personal=[f for _s, f in personal[:10]],
                   bls=bls.search(q, 25))


@app.get("/api/v1/frequent")
def frequent():
    return jsonify(items=db.frequent_items(), meals=db.frequent_meals())


# --------------------------------------------------------------------------
# Lebensmittel
# --------------------------------------------------------------------------

@app.post("/api/v1/foods")
def create_food():
    d = request.get_json(force=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        abort(400, "Name fehlt")
    per100 = N.clean(d.get("per100"))
    if per100["kcal"] is None:
        abort(400, "Kalorien je 100 g fehlen")
    ref = d.get("barcode") or f"custom-{datetime.datetime.now().timestamp():.0f}"
    source = "off" if d.get("barcode") else "custom"
    food = db.upsert_food(source, ref, name, per100, brand=d.get("brand"), serving_g=d.get("serving_g"),
                          serving_label=d.get("serving_label"), is_liquid=d.get("is_liquid"))
    return jsonify(food)


@app.put("/api/v1/foods/<int:food_id>")
def update_food(food_id):
    d = request.get_json(force=True) or {}
    if "per100" in d:
        d["per100"] = N.clean(d["per100"])
    food = db.update_food(food_id, **d)
    if not food:
        abort(404)
    return jsonify(food)


@app.get("/api/v1/bls/<code>")
def bls_item(code):
    item = bls.get(code)
    if not item:
        abort(404)
    return jsonify(item)


# --------------------------------------------------------------------------
# Mahlzeiten
# --------------------------------------------------------------------------

def _resolve_items(items):
    out = []
    for it in items or []:
        try:
            amount = float(it.get("amount_g"))
        except (TypeError, ValueError):
            abort(400, f"Menge fehlt bei {it.get('name')}")
        source = it.get("source") or "ki"
        food_id = it.get("food_id")
        per100 = it.get("per100")
        name = (it.get("name") or "").strip()
        if source == "bls" and it.get("ref") and not food_id:
            b = bls.get(it["ref"])
            if b:
                f = db.upsert_food("bls", b["code"], b["name"], b["per100"], is_liquid=b["is_liquid"])
                food_id, per100 = f["id"], per100 or b["per100"]
        if food_id and not per100:
            f = db.get_food(food_id)
            per100 = f["per100"] if f else None
        if not per100:
            abort(400, f"Nährwerte fehlen bei {name or 'Position'}")
        out.append({"food_id": food_id, "name": name or "Unbekannt", "amount_g": max(0.0, amount),
                    "amount_text": it.get("amount_text"), "source": source,
                    "confidence": it.get("confidence"), "per100": N.clean(per100)})
    return out


def _save_photo(meal_id, b64):
    if not b64 or db.get_setting("keep_photos") is False:
        return None
    if "," in b64[:100]:
        b64 = b64.split(",", 1)[1]
    os.makedirs(PHOTO_DIR, exist_ok=True)
    name = f"{meal_id}.jpg"
    with open(os.path.join(PHOTO_DIR, name), "wb") as f:
        f.write(base64.b64decode(b64))
    return name


def _meal_payload(d):
    cat = d.get("category") or analyze.guess_category()
    return {"date": d.get("date") or _today(), "time": d.get("time") or datetime.datetime.now().strftime("%H:%M"),
            "category": cat, "title": (d.get("title") or "").strip()[:80] or None,
            "method": d.get("method") or "manuell", "note": d.get("note"), "ai": d.get("ai"),
            "items": _resolve_items(d.get("items"))}


@app.post("/api/v1/meals")
def create_meal():
    d = request.get_json(force=True) or {}
    payload = _meal_payload(d)
    if not payload["items"]:
        abort(400, "Keine Lebensmittel")
    meal = db.save_meal(payload)
    photo = _save_photo(meal["id"], d.get("photo"))
    if photo:
        payload["photo"] = photo
        meal = db.save_meal(payload, meal["id"])
    if d.get("save_favorite"):
        db.save_favorite(d.get("favorite_title") or meal["title"] or "Favorit", meal["category"], meal["items"])
    _changed()
    return jsonify(meal), 201


@app.get("/api/v1/meals/<int:meal_id>")
def get_meal(meal_id):
    m = db.get_meal(meal_id)
    if not m:
        abort(404)
    return jsonify(m)


@app.put("/api/v1/meals/<int:meal_id>")
def update_meal(meal_id):
    old = db.get_meal(meal_id)
    if not old:
        abort(404)
    d = request.get_json(force=True) or {}
    payload = _meal_payload({**old, **d, "items": d.get("items", old["items"])})
    payload["photo"] = old.get("photo")
    meal = db.save_meal(payload, meal_id)
    _changed()
    return jsonify(meal)


@app.delete("/api/v1/meals/<int:meal_id>")
def delete_meal(meal_id):
    photo = db.delete_meal(meal_id)
    if photo:
        try:
            os.remove(os.path.join(PHOTO_DIR, photo))
        except OSError:
            pass
    _changed()
    return jsonify(ok=True)


@app.get("/api/v1/meals/<int:meal_id>/photo")
def meal_photo(meal_id):
    m = db.get_meal(meal_id)
    if not m or not m.get("photo"):
        abort(404)
    return send_from_directory(PHOTO_DIR, m["photo"])


@app.post("/api/v1/water")
def add_water():
    d = request.get_json(force=True) or {}
    ml = float(d.get("ml") or 250)
    per100 = N.empty()
    w = bls.search("Trinkwasser", 1)
    if w and "wasser" in bls.norm(w[0]["name"]):
        per100 = w[0]["per100"]
        item = {"source": "bls", "ref": w[0]["code"], "name": "Wasser", "amount_g": ml}
    else:
        per100.update(kcal=0.0, water_ml=100.0)
        item = {"source": "custom", "name": "Wasser", "amount_g": ml, "per100": per100}
    meal = db.save_meal({"date": d.get("date") or _today(), "time": datetime.datetime.now().strftime("%H:%M"),
                         "category": "sonstiges", "title": "Wasser", "method": "schnell",
                         "items": _resolve_items([item])})
    _changed()
    return jsonify(meal), 201


# --------------------------------------------------------------------------
# Favoriten
# --------------------------------------------------------------------------

@app.get("/api/v1/favorites")
def favorites():
    return jsonify(db.list_favorites())


@app.post("/api/v1/favorites")
def create_favorite():
    d = request.get_json(force=True) or {}
    items = _resolve_items(d.get("items"))
    if not items:
        abort(400, "Keine Lebensmittel")
    return jsonify(db.save_favorite(d.get("title") or "Favorit", d.get("category"), items, d.get("id"))), 201


@app.delete("/api/v1/favorites/<int:fav_id>")
def delete_favorite(fav_id):
    db.delete_favorite(fav_id)
    return jsonify(ok=True)


@app.post("/api/v1/favorites/<int:fav_id>/log")
def log_favorite(fav_id):
    fav = db.get_favorite(fav_id)
    if not fav:
        abort(404)
    d = request.get_json(force=True) or {}
    factor = float(d.get("factor") or 1)
    items = [{**it, "amount_g": it["amount_g"] * factor} for it in fav["items"]]
    meal = db.save_meal({"date": d.get("date") or _today(),
                         "time": d.get("time") or datetime.datetime.now().strftime("%H:%M"),
                         "category": d.get("category") or fav.get("category") or analyze.guess_category(),
                         "title": fav["title"], "method": "favorit", "items": _resolve_items(items)})
    db.use_favorite(fav_id)
    _changed()
    return jsonify(meal), 201


# --------------------------------------------------------------------------
# Export (Datenhoheit)
# --------------------------------------------------------------------------

@app.get("/api/v1/export.csv")
def export_csv():
    start = request.args.get("from") or "2000-01-01"
    end = request.args.get("to") or "2999-12-31"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["datum", "uhrzeit", "kategorie", "mahlzeit", "lebensmittel", "menge_g", "quelle"] + N.KEYS)
    for m in db.meals_between(start, end):
        for it in m["items"]:
            vals = N.scale(it["per100"], it["amount_g"])
            w.writerow([m["date"], m["time"], m["category"], m["title"] or "", it["name"],
                        round(it["amount_g"], 1), it["source"]] +
                       ["" if vals[k] is None else str(round(vals[k], 2)).replace(".", ",") for k in N.KEYS])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ernaehrung.csv"})
