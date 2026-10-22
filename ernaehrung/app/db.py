"""SQLite-Datenhaltung (Datei unter /data, wird von HA-Backups mitgesichert).

Tabellen
- foods        Lebensmittel mit Nährwerten je 100 g (Quelle bls/off/custom/ai).
               BLS-Einträge werden erst beim ersten Verwenden hierher kopiert,
               damit ein BLS-Neuimport nie gespeicherte Mahlzeiten verändert.
- meals        Mahlzeit (Datum, Uhrzeit, Kategorie, Erfassungsart, Foto).
- meal_items   Positionen einer Mahlzeit: Menge in g/ml + Nährwert-Snapshot je
               100 g. Mengenänderungen rechnen damit immer korrekt neu.
- favorites    Gespeicherte Mahlzeiten-Vorlagen zum schnellen Wiedereintragen.
- settings     Schlüssel/Wert (JSON) für Profil, Ziele, Optionen.
"""
import json
import os
import sqlite3
import threading
import datetime

DB_PATH = os.environ.get("NUTRITION_DB", "/data/ernaehrung.db")
_local = threading.local()

CATEGORIES = ["fruehstueck", "mittagessen", "abendessen", "snack", "sonstiges"]
CATEGORY_LABELS = {
    "fruehstueck": "Frühstück",
    "mittagessen": "Mittagessen",
    "abendessen": "Abendessen",
    "snack": "Snacks",
    "sonstiges": "Sonstiges",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_ref TEXT,
    name TEXT NOT NULL,
    brand TEXT,
    serving_g REAL,
    serving_label TEXT,
    per100 TEXT NOT NULL,
    is_liquid INTEGER DEFAULT 0,
    use_count INTEGER DEFAULT 0,
    last_used TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS foods_src ON foods(source, source_ref) WHERE source_ref IS NOT NULL;
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    time TEXT,
    category TEXT NOT NULL,
    title TEXT,
    method TEXT,
    photo TEXT,
    note TEXT,
    ai_json TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS meals_date ON meals(date);
CREATE TABLE IF NOT EXISTS meal_items (
    id INTEGER PRIMARY KEY,
    meal_id INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    food_id INTEGER REFERENCES foods(id) ON DELETE SET NULL,
    position INTEGER DEFAULT 0,
    name TEXT NOT NULL,
    amount_g REAL NOT NULL,
    amount_text TEXT,
    source TEXT,
    confidence TEXT,
    per100 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS items_meal ON meal_items(meal_id);
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT,
    items TEXT NOT NULL,
    use_count INTEGER DEFAULT 0,
    last_used TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS days (
    date TEXT PRIMARY KEY,
    targets TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != DB_PATH:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        _local.conn = c
        _local.path = DB_PATH
    return c


def init(path: str = None):
    global DB_PATH
    if path:
        DB_PATH = path
        _local.conn = None
    c = conn()
    c.executescript(SCHEMA)
    c.commit()


# --------------------------------------------------------------------------
# Einstellungen
# --------------------------------------------------------------------------

def get_setting(key, default=None):
    row = conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return default


def set_setting(key, value):
    c = conn()
    c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, json.dumps(value, ensure_ascii=False)))
    c.commit()


# --------------------------------------------------------------------------
# Tagesziele (Snapshot je Tag, damit die Wochenansicht die damaligen Ziele kennt)
# --------------------------------------------------------------------------

def save_day_targets(date, targets: dict):
    c = conn()
    c.execute("INSERT INTO days(date, targets, updated_at) VALUES(?,?,?) "
              "ON CONFLICT(date) DO UPDATE SET targets=excluded.targets, updated_at=excluded.updated_at",
              (date, json.dumps(targets, ensure_ascii=False), now_iso()))
    c.commit()


def get_day_targets(date):
    r = conn().execute("SELECT targets FROM days WHERE date=?", (date,)).fetchone()
    return json.loads(r["targets"]) if r else None


# --------------------------------------------------------------------------
# Lebensmittel
# --------------------------------------------------------------------------

def _food_row(r) -> dict:
    if r is None:
        return None
    d = dict(r)
    d["per100"] = json.loads(d["per100"])
    d["is_liquid"] = bool(d.get("is_liquid"))
    return d


def get_food(food_id):
    return _food_row(conn().execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone())


def find_food(source, source_ref):
    return _food_row(conn().execute(
        "SELECT * FROM foods WHERE source=? AND source_ref=?", (source, source_ref)).fetchone())


def upsert_food(source, source_ref, name, per100, brand=None, serving_g=None,
                serving_label=None, is_liquid=False) -> dict:
    c = conn()
    ts = now_iso()
    existing = find_food(source, source_ref) if source_ref else None
    if existing:
        c.execute("UPDATE foods SET name=?, brand=?, serving_g=?, serving_label=?, per100=?, "
                  "is_liquid=?, updated_at=? WHERE id=?",
                  (name, brand, serving_g, serving_label, json.dumps(per100), int(bool(is_liquid)),
                   ts, existing["id"]))
        c.commit()
        return get_food(existing["id"])
    cur = c.execute(
        "INSERT INTO foods(source, source_ref, name, brand, serving_g, serving_label, per100, "
        "is_liquid, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (source, source_ref, name, brand, serving_g, serving_label, json.dumps(per100),
         int(bool(is_liquid)), ts, ts))
    c.commit()
    return get_food(cur.lastrowid)


def update_food(food_id, **fields):
    allowed = {"name", "brand", "serving_g", "serving_label", "per100", "is_liquid"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "per100":
            v = json.dumps(v)
        if k == "is_liquid":
            v = int(bool(v))
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return get_food(food_id)
    vals += [now_iso(), food_id]
    conn().execute(f"UPDATE foods SET {', '.join(sets)}, updated_at=? WHERE id=?", vals)
    conn().commit()
    return get_food(food_id)


def personal_foods(limit=400):
    """Eigene + bereits benutzte Lebensmittel, häufigste zuerst."""
    rows = conn().execute(
        "SELECT * FROM foods WHERE source IN ('custom','off') OR use_count > 0 "
        "ORDER BY use_count DESC, updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [_food_row(r) for r in rows]


def mark_food_used(food_id):
    conn().execute("UPDATE foods SET use_count = use_count + 1, last_used=? WHERE id=?",
                   (now_iso(), food_id))


# --------------------------------------------------------------------------
# Mahlzeiten
# --------------------------------------------------------------------------

def _item_row(r) -> dict:
    d = dict(r)
    d["per100"] = json.loads(d["per100"])
    return d


def get_meal(meal_id):
    c = conn()
    m = c.execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone()
    if not m:
        return None
    meal = dict(m)
    meal["ai"] = json.loads(meal.pop("ai_json") or "null")
    meal["items"] = [_item_row(r) for r in c.execute(
        "SELECT mi.*, COALESCE(f.is_liquid, 0) AS is_liquid FROM meal_items mi "
        "LEFT JOIN foods f ON f.id = mi.food_id WHERE mi.meal_id=? ORDER BY mi.position, mi.id", (meal_id,))]
    for it in meal["items"]:
        it["is_liquid"] = bool(it["is_liquid"])
    return meal


def meals_between(date_from: str, date_to: str):
    c = conn()
    rows = c.execute("SELECT id FROM meals WHERE date BETWEEN ? AND ? ORDER BY date, time, id",
                     (date_from, date_to)).fetchall()
    return [get_meal(r["id"]) for r in rows]


def save_meal(meal: dict, meal_id=None) -> dict:
    """Legt eine Mahlzeit an oder ersetzt sie komplett (inkl. Positionen)."""
    c = conn()
    ts = now_iso()
    category = meal.get("category") if meal.get("category") in CATEGORIES else "sonstiges"
    fields = (meal["date"], meal.get("time"), category, meal.get("title"), meal.get("method"),
              meal.get("photo"), meal.get("note"),
              json.dumps(meal.get("ai")) if meal.get("ai") is not None else None)
    if meal_id:
        c.execute("UPDATE meals SET date=?, time=?, category=?, title=?, method=?, photo=?, note=?, "
                  "ai_json=COALESCE(?, ai_json), updated_at=? WHERE id=?", fields + (ts, meal_id))
        c.execute("DELETE FROM meal_items WHERE meal_id=?", (meal_id,))
    else:
        cur = c.execute("INSERT INTO meals(date, time, category, title, method, photo, note, ai_json, "
                        "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", fields + (ts, ts))
        meal_id = cur.lastrowid
    for pos, it in enumerate(meal.get("items") or []):
        c.execute(
            "INSERT INTO meal_items(meal_id, food_id, position, name, amount_g, amount_text, source, "
            "confidence, per100) VALUES(?,?,?,?,?,?,?,?,?)",
            (meal_id, it.get("food_id"), pos, it["name"], float(it["amount_g"]), it.get("amount_text"),
             it.get("source"), it.get("confidence"), json.dumps(it["per100"])))
        if it.get("food_id"):
            mark_food_used(it["food_id"])
    c.commit()
    return get_meal(meal_id)


def delete_meal(meal_id):
    c = conn()
    row = c.execute("SELECT photo FROM meals WHERE id=?", (meal_id,)).fetchone()
    c.execute("DELETE FROM meals WHERE id=?", (meal_id,))
    c.commit()
    return row["photo"] if row else None


def frequent_items(days=60, limit=20):
    """Häufig gegessene Lebensmittel der letzten Wochen (für Schnellauswahl)."""
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn().execute(
        "SELECT mi.food_id, mi.name, mi.per100, mi.source, COUNT(*) AS n, "
        "AVG(mi.amount_g) AS avg_g, MAX(m.date) AS last_date "
        "FROM meal_items mi JOIN meals m ON m.id = mi.meal_id "
        "WHERE m.date >= ? GROUP BY COALESCE(mi.food_id, mi.name) "
        "ORDER BY n DESC, last_date DESC LIMIT ?", (since, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["per100"] = json.loads(d["per100"])
        d["avg_g"] = round(d["avg_g"] or 0)
        out.append(d)
    return out


def frequent_meals(days=60, limit=8):
    """Wiederkehrende Mahlzeiten (gleiche Lebensmittel-Kombination)."""
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    c = conn()
    rows = c.execute("SELECT id FROM meals WHERE date >= ? ORDER BY date DESC, time DESC", (since,)).fetchall()
    groups = {}
    for r in rows:
        meal = get_meal(r["id"])
        if not meal["items"]:
            continue
        sig = tuple(sorted((it.get("food_id") or it["name"].lower()) for it in meal["items"]))
        g = groups.setdefault(sig, {"count": 0, "meal": meal})
        g["count"] += 1
    ranked = sorted((g for g in groups.values() if g["count"] >= 2), key=lambda g: -g["count"])
    return [{"count": g["count"], "meal": g["meal"]} for g in ranked[:limit]]


# --------------------------------------------------------------------------
# Favoriten
# --------------------------------------------------------------------------

def list_favorites():
    rows = conn().execute("SELECT * FROM favorites ORDER BY use_count DESC, title").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["items"] = json.loads(d["items"])
        out.append(d)
    return out


def get_favorite(fav_id):
    r = conn().execute("SELECT * FROM favorites WHERE id=?", (fav_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["items"] = json.loads(d["items"])
    return d


def save_favorite(title, category, items, fav_id=None):
    c = conn()
    clean_items = [{k: it.get(k) for k in ("food_id", "name", "amount_g", "amount_text", "source", "per100")}
                   for it in items]
    if fav_id:
        c.execute("UPDATE favorites SET title=?, category=?, items=? WHERE id=?",
                  (title, category, json.dumps(clean_items), fav_id))
    else:
        fav_id = c.execute("INSERT INTO favorites(title, category, items, created_at) VALUES(?,?,?,?)",
                           (title, category, json.dumps(clean_items), now_iso())).lastrowid
    c.commit()
    return get_favorite(fav_id)


def use_favorite(fav_id):
    conn().execute("UPDATE favorites SET use_count = use_count + 1, last_used=? WHERE id=?", (now_iso(), fav_id))
    conn().commit()


def delete_favorite(fav_id):
    conn().execute("DELETE FROM favorites WHERE id=?", (fav_id,))
    conn().commit()
