"""Open Food Facts - Produktabfrage per Barcode.

API v2: GET https://world.openfoodfacts.org/api/v2/product/{barcode}
Regeln laut OFF-Doku: eigener User-Agent "App/Version (Kontakt)", max. 15
Produktabfragen/Minute. Ergebnisse werden lokal in `foods` gespeichert, ein
zweiter Scan desselben Produkts braucht daher keinen Netzzugriff.
Daten: Open Database License (ODbL), Open Food Facts contributors.
"""
import re
import time
import threading

import requests

from nutrients import KEYS, convert

BASE = "https://world.openfoodfacts.org/api/v2/product/{code}"
USER_AGENT = "ErnaehrungHA/0.1 (Home-Assistant-Add-on; privat)"
FIELDS = ("code,product_name,product_name_de,generic_name_de,brands,quantity,serving_size,"
          "serving_quantity,nutriments,categories_tags,product_quantity_unit")

# OFF-Feld -> (kanonischer Schlüssel, Einheit in OFF *_100g)
# OFF speichert Mineralstoffe/Vitamine in *_100g in Gramm.
MAP = {
    "energy-kcal": ("kcal", "kcal"),
    "proteins": ("protein_g", "g"),
    "carbohydrates": ("carbs_g", "g"),
    "sugars": ("sugar_g", "g"),
    "fat": ("fat_g", "g"),
    "saturated-fat": ("satfat_g", "g"),
    "fiber": ("fiber_g", "g"),
    "sodium": ("sodium_mg", "g"),
    "potassium": ("potassium_mg", "g"),
    "magnesium": ("magnesium_mg", "g"),
    "calcium": ("calcium_mg", "g"),
    "iron": ("iron_mg", "g"),
    "zinc": ("zinc_mg", "g"),
    "vitamin-d": ("vitd_ug", "g"),
    "vitamin-b12": ("b12_ug", "g"),
    "vitamin-c": ("vitc_mg", "g"),
    "iodine": ("iodine_ug", "g"),
    "eicosapentaenoic-acid": ("omega3_mg", "g"),
    "docosahexaenoic-acid": ("omega3_mg", "g"),
}
_TARGET_UNIT = {"kcal": "kcal", "protein_g": "g", "carbs_g": "g", "sugar_g": "g", "fat_g": "g",
                "satfat_g": "g", "fiber_g": "g", "sodium_mg": "mg", "potassium_mg": "mg",
                "magnesium_mg": "mg", "calcium_mg": "mg", "iron_mg": "mg", "zinc_mg": "mg",
                "vitd_ug": "µg", "b12_ug": "µg", "vitc_mg": "mg", "iodine_ug": "µg", "omega3_mg": "mg"}

_lock = threading.Lock()
_calls = []  # Zeitstempel der letzten Abfragen (Rate-Limit 15/min)
_search_calls = []  # Textsuche: max. 10/min laut OFF
SEARCH_URL = "https://search.openfoodfacts.org/search"
LEGACY_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
SEARCH_FIELDS = "code,product_name,product_name_de,brands,quantity,nutriments,serving_quantity,serving_size,product_quantity_unit,categories_tags"


def valid_barcode(code: str) -> bool:
    code = re.sub(r"\D", "", code or "")
    if len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def _rate_limit(calls=None, limit=14, what="Barcode-Abfragen"):
    calls = _calls if calls is None else calls
    with _lock:
        now = time.time()
        while calls and now - calls[0] > 60:
            calls.pop(0)
        if len(calls) >= limit:
            raise RuntimeError(f"Zu viele {what} in kurzer Zeit - bitte eine Minute warten")
        calls.append(now)


def _txt(v):
    """Search-a-licious liefert Textfelder teils als {"de": ..., "main": ...} oder Liste."""
    if isinstance(v, dict):
        return v.get("de") or v.get("main") or v.get("en") or next(iter(v.values()), "")
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return v


def parse_product(p: dict) -> dict:
    p = {k: (_txt(v) if k in ("product_name", "product_name_de", "generic_name_de", "brands", "quantity",
                              "serving_size") else v) for k, v in p.items()}
    n = p.get("nutriments") or {}
    per100 = {k: None for k in KEYS}
    for off_key, (key, unit) in MAP.items():
        v = n.get(f"{off_key}_100g")
        if v is None and off_key == "energy-kcal" and n.get("energy_100g") is not None:
            v, unit = n.get("energy_100g"), "kj"  # nur kJ angegeben
        try:
            v = float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            continue
        v = round(convert(v, unit, _TARGET_UNIT[key]), 6)
        per100[key] = v if per100[key] is None else round(per100[key] + v, 6)  # EPA + DHA
    if per100["sodium_mg"] is None and n.get("salt_100g") not in (None, ""):
        try:
            per100["sodium_mg"] = round(float(n["salt_100g"]) / 2.5 * 1000, 3)  # Salz = Na x 2,5
        except (TypeError, ValueError):
            pass
    unit = (p.get("product_quantity_unit") or "").lower()
    cats = " ".join(p.get("categories_tags") or [])
    is_liquid = unit == "ml" or "beverages" in cats or "drinks" in cats
    if is_liquid and per100.get("water_ml") is None:
        # Getränke: Wasseranteil grob = Rest nach Trockenmasse (für die Flüssigkeitsbilanz)
        dry = sum((per100.get(k) or 0) for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"))
        per100["water_ml"] = round(max(0.0, 100 - dry), 1)
    name = (p.get("product_name_de") or p.get("product_name") or p.get("generic_name_de") or "").strip()
    try:
        serving_g = float(p.get("serving_quantity")) if p.get("serving_quantity") else None
    except (TypeError, ValueError):
        serving_g = None
    return {
        "barcode": p.get("code"),
        "name": name or f"Produkt {p.get('code')}",
        "brand": (p.get("brands") or "").split(",")[0].strip() or None,
        "quantity": p.get("quantity"),
        "serving_g": serving_g,
        "serving_label": p.get("serving_size"),
        "is_liquid": is_liquid,
        "per100": per100,
        "has_nutrition": per100["kcal"] is not None,
    }


def lookup(barcode: str):
    """Produkt holen. None = nicht in OFF vorhanden."""
    code = re.sub(r"\D", "", barcode or "")
    _rate_limit()
    r = requests.get(BASE.format(code=code), params={"fields": FIELDS},
                     headers={"User-Agent": USER_AGENT}, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    if data.get("status") in (0, "failure") or not data.get("product"):
        return None
    return parse_product(data["product"])


def search(query: str, limit: int = 12):
    """Textsuche nach Markenprodukten (Search-a-licious, Ersatz: klassische Suche).
    Ergebnisse ohne Nährwerte werden ausgelassen."""
    _rate_limit(_search_calls, 9, "Produktsuchen")
    headers = {"User-Agent": USER_AGENT}
    products = []
    try:
        r = requests.get(SEARCH_URL, params={"q": query, "langs": "de,en", "page_size": 30,
                                             "fields": SEARCH_FIELDS}, headers=headers, timeout=20)
        r.raise_for_status()
        products = r.json().get("hits") or []
    except Exception as e:
        print(f"[off] search-a-licious nicht verfügbar ({e}), nutze klassische Suche")
        r = requests.get(LEGACY_SEARCH_URL, params={"search_terms": query, "search_simple": 1, "json": 1,
                                                    "page_size": 30, "fields": SEARCH_FIELDS,
                                                    "lc": "de", "cc": "de"},
                         headers=headers, timeout=25)
        r.raise_for_status()
        products = r.json().get("products") or []
    out = []
    for p in products:
        try:
            parsed = parse_product(p)
        except Exception:
            continue
        if parsed["has_nutrition"] and parsed.get("barcode"):
            out.append(parsed)
        if len(out) >= limit:
            break
    return out
