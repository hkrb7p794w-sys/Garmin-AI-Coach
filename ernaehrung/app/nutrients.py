"""Kanonische Nährwert-Schlüssel.

Alle Lebensmittel (BLS, Open Food Facts, KI-Schätzung, eigene) werden auf
diese Schlüssel und Einheiten normalisiert - "je 100 g" in der Tabelle
`foods`, absolute Mengen in `meal_items`. Die Reihenfolge hier ist auch die
Anzeige-Reihenfolge in der App und in den Home-Assistant-Attributen.
"""

# key: (Anzeigename, Einheit, Gruppe)
NUTRIENTS = {
    "kcal": ("Kalorien", "kcal", "makro"),
    "protein_g": ("Protein", "g", "makro"),
    "carbs_g": ("Kohlenhydrate", "g", "makro"),
    "sugar_g": ("davon Zucker", "g", "makro"),
    "fat_g": ("Fett", "g", "makro"),
    "satfat_g": ("davon gesättigt", "g", "makro"),
    "fiber_g": ("Ballaststoffe", "g", "makro"),
    "water_ml": ("Flüssigkeit", "ml", "mikro"),
    "sodium_mg": ("Natrium", "mg", "mikro"),
    "potassium_mg": ("Kalium", "mg", "mikro"),
    "magnesium_mg": ("Magnesium", "mg", "mikro"),
    "calcium_mg": ("Calcium", "mg", "mikro"),
    "iron_mg": ("Eisen", "mg", "mikro"),
    "zinc_mg": ("Zink", "mg", "mikro"),
    "vitd_ug": ("Vitamin D", "µg", "mikro"),
    "b12_ug": ("Vitamin B12", "µg", "mikro"),
    "vitc_mg": ("Vitamin C", "mg", "mikro"),
}

KEYS = list(NUTRIENTS)
MACRO_KEYS = [k for k, v in NUTRIENTS.items() if v[2] == "makro"]
MICRO_KEYS = [k for k, v in NUTRIENTS.items() if v[2] == "mikro"]

# BLS-4.0-Komponentencodes -> kanonischer Schlüssel und Ziel-Einheit
# (Dokumentation BLS 4.0, Max Rubner-Institut 2025). WATER [g/100g] wird
# 1:1 als ml gezählt (Dichte ~1) - "Flüssigkeit" umfasst damit auch das
# Wasser aus fester Nahrung, wie bei der DGE-Gesamtwasserzufuhr.
BLS_CODES = {
    "ENERCC": ("kcal", "kcal"),
    "PROT625": ("protein_g", "g"),
    "CHO": ("carbs_g", "g"),
    "SUGAR": ("sugar_g", "g"),
    "FAT": ("fat_g", "g"),
    "FASAT": ("satfat_g", "g"),
    "FIBT": ("fiber_g", "g"),
    "WATER": ("water_ml", "g"),
    "NA": ("sodium_mg", "mg"),
    "K": ("potassium_mg", "mg"),
    "MG": ("magnesium_mg", "mg"),
    "CA": ("calcium_mg", "mg"),
    "FE": ("iron_mg", "mg"),
    "ZN": ("zinc_mg", "mg"),
    "VITD": ("vitd_ug", "µg"),
    "VITB12": ("b12_ug", "µg"),
    "VITC": ("vitc_mg", "mg"),
}

_UNIT_FACTORS = {  # Umrechnung in die kanonische Einheit
    ("g", "g"): 1, ("mg", "g"): 0.001, ("µg", "g"): 1e-6, ("ug", "g"): 1e-6,
    ("g", "mg"): 1000, ("mg", "mg"): 1, ("µg", "mg"): 0.001, ("ug", "mg"): 0.001,
    ("g", "µg"): 1e6, ("mg", "µg"): 1000, ("µg", "µg"): 1, ("ug", "µg"): 1,
    ("kcal", "kcal"): 1, ("kj", "kcal"): 1 / 4.184,
}


def convert(value, from_unit: str, to_unit: str):
    if value is None:
        return None
    f = _UNIT_FACTORS.get(((from_unit or "").strip().lower().replace("μ", "µ"), to_unit))
    if f is None:
        return None
    return value * f


def unit_of(key: str) -> str:
    return NUTRIENTS[key][1]


def empty() -> dict:
    return {k: None for k in KEYS}


def scale(per100: dict, amount_g: float) -> dict:
    """Nährwerte je 100 g auf eine Menge hochrechnen. None bleibt None
    (fehlender Wert ist nicht 0 - wichtig für die Vollständigkeitsanzeige)."""
    out = {}
    factor = (amount_g or 0) / 100.0
    for k in KEYS:
        v = (per100 or {}).get(k)
        out[k] = None if v is None else round(v * factor, 4)
    return out


def add(total: dict, part: dict) -> dict:
    for k in KEYS:
        v = (part or {}).get(k)
        if v is not None:
            total[k] = (total.get(k) or 0) + v
    return total


def clean(d: dict) -> dict:
    """Nur bekannte Schlüssel, Zahlen als float, negative/kaputte Werte -> None."""
    out = {}
    for k in KEYS:
        v = (d or {}).get(k)
        try:
            v = None if v is None or v == "" else float(v)
        except (TypeError, ValueError):
            v = None
        if v is not None and (v < 0 or v != v):
            v = None
        out[k] = v
    return out


def plausible_per100(d: dict) -> bool:
    """Grobe Plausibilität je 100 g (Masse der Makros <= ~100 g, kcal <= 900)."""
    kcal = d.get("kcal") or 0
    mass = sum((d.get(k) or 0) for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"))
    return kcal <= 905 and mass <= 105
