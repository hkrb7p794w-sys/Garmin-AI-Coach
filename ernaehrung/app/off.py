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
}
_TARGET_UNIT = {"kcal": "kcal", "protein_g": "g", "carbs_g": "g", "sugar_g": "g", "fat_g": "g",
                "satfat_g": "g", "fiber_g": "g", "sodium_mg": "mg", "potassium_mg": "mg",
                "magnesium_mg": "mg", "calcium_mg": "mg", "iron_mg": "mg", "zinc_mg": "mg",
                "vitd_ug": "µg", "b12_ug": "µg", "vitc_mg": "mg"}

_lock = threading.Lock()
_calls = []  # Zeitstempel der letzten Abfragen (Rate-Limit 15/min)


def valid_barcode(code: str) -> bool:
    code = re.sub(r"\D", "", code or "")
    if len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def _rate_limit():
    with _lock:
        now = time.time()
        while _calls and now - _calls[0] > 60:
            _calls.pop(0)
        if len(_calls) >= 14:
            raise RuntimeError("Zu viele Barcode-Abfragen in kurzer Zeit - bitte eine Minute warten")
        _calls.append(now)


def parse_product(p: dict) -> dict:
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
        per100[key] = None if v is None else round(convert(v, unit, _TARGET_UNIT[key]), 6)
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
