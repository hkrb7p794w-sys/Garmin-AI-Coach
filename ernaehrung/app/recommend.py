"""Empfehlungen: was und wie noch essen - für heute und als Wochenmuster.

Regelbasiert und nachvollziehbar (keine KI): jede Empfehlung nennt ihren Grund und
ihre Quelle. Lebensmittelvorschläge kommen aus einer kuratierten Liste typischer,
schnell verfügbarer Lebensmittel; deren Nährwerte werden zur Laufzeit aus dem BLS
gelesen, damit die Zahlen stimmen.

Quellen
- Thomas DT, Erdman KA, Burke LM (2016), ACSM/AND/DC: Kohlenhydrate 1-4 g/kg 1-4 h vor
  dem Training; nach harten Einheiten mit < 8 h Pause 1,0-1,2 g/kg/h.
- Kerksick CM et al. (2017), ISSN Nutrient Timing: 0,25-0,4 g/kg Protein je Mahlzeit
  alle 3-4 h; 30-40 g Casein (z. B. Quark) vor dem Schlafen.
- DGE „Gut essen und trinken“ (2024): Fisch 1-2x/Woche (ideal 1x fettreich), Hülsenfrüchte
  mind. 1x/Woche, täglich eine Handvoll Nüsse, 5 Portionen Obst/Gemüse, Vollkorn,
  Milchprodukte täglich, Fleisch/Wurst max. 300 g/Woche.
- DGE Eisen: Vitamin C verbessert, Polyphenole (Kaffee, schwarzer Tee) hemmen die Aufnahme.
- DGE/ÖGE (2025) Jod 150 µg: Jodsalz, Milch, Seefisch 1-2x/Woche.
- BfR: Oktober-März kaum Vitamin-D-Bildung über die Haut; DGE: 20 µg/Tag bei fehlender
  Eigensynthese (dann als Präparat).
"""
import datetime

import bls
import nutrients as N

DIETS = {"omnivor": "Mischkost", "pescetarisch": "Pescetarisch (Fisch, kein Fleisch)",
         "vegetarisch": "Vegetarisch", "vegan": "Vegan"}

# key, Anzeigename, BLS-Code (live geprüft 23.10.2026), Ersatz-Suchwörter, Portion g, Portionstext,
# Tags, tierisch ("fisch" | "milch" | "ei" | None)
CANDIDATES = [
    ("magerquark", "Magerquark", "M713100", ["speisequark", "magerstufe"], 250, "1 Becher (250 g)",
     {"protein", "abend", "fruehstueck", "snack"}, "milch"),
    ("skyr", "Skyr", "M710100", ["skyr"], 200, "1 Becher (200 g)",
     {"protein", "abend", "fruehstueck", "snack"}, "milch"),
    ("huettenkaese", "Körniger Frischkäse", "M711100", ["korniger", "frischkase"], 200, "1 Becher (200 g)",
     {"protein", "abend", "snack"}, "milch"),
    ("joghurt", "Naturjoghurt 1,5 %", "M141200", ["joghurt", "fettarm"], 150, "1 Schale (150 g)",
     {"fruehstueck", "snack", "calcium"}, "milch"),
    ("milch", "Milch 1,5 %", "M111200", ["milch", "fettarm"], 250, "1 Glas (250 ml)",
     {"fruehstueck", "snack", "calcium", "nach"}, "milch"),
    ("kaese", "Emmentaler", "M304600", ["emmentaler"], 30, "1 Scheibe (30 g)", {"calcium", "snack"}, "milch"),
    ("ei", "Eier, gekocht", "E111132", ["huhnerei", "gekocht"], 110, "2 Eier", {"protein", "fruehstueck"}, "ei"),
    ("lachs", "Lachs", "T410100", ["lachs", "roh"], 125, "1 Filet (125 g)",
     {"protein", "omega3", "vitd", "hauptmahlzeit"}, "fisch"),
    ("hering", "Hering", "T102100", ["hering", "roh"], 100, "1 Filet (100 g)",
     {"protein", "omega3", "vitd", "hauptmahlzeit"}, "fisch"),
    ("makrele", "Makrele, geräuchert", "T107600", ["makrele", "gerauchert"], 100, "1 Filet (100 g)",
     {"protein", "omega3", "vitd", "hauptmahlzeit", "snack"}, "fisch"),
    ("kabeljau", "Kabeljau, gedünstet", "T204152", ["kabeljau", "gedunstet"], 150, "1 Filet (150 g)",
     {"protein", "jod", "hauptmahlzeit"}, "fisch"),
    ("seelachs", "Seelachs, gedünstet", "T207152", ["seelachs", "gedunstet"], 150, "1 Filet (150 g)",
     {"protein", "jod", "hauptmahlzeit"}, "fisch"),
    ("thunfisch", "Thunfisch im eigenen Saft", "T121902", ["thunfisch", "saft"], 100, "1 kleine Dose",
     {"protein", "snack", "hauptmahlzeit"}, "fisch"),
    ("linsen", "Linsen, gekocht", "H730132", ["linse", "reif", "gekocht"], 150, "1 Portion (150 g)",
     {"protein", "eisen", "ballast", "hauptmahlzeit", "huelsen"}, None),
    ("kichererbsen", "Kichererbsen, gekocht", "G770432", ["kichererbse", "reif", "gekocht"], 150,
     "1 Portion (150 g)", {"protein", "eisen", "ballast", "hauptmahlzeit", "huelsen"}, None),
    ("bohnen", "Kidneybohnen, gekocht", "H742132", ["kidneybohne", "gekocht"], 150, "1 Portion (150 g)",
     {"protein", "eisen", "ballast", "hauptmahlzeit", "huelsen"}, None),
    ("tofu", "Tofu", "H861000", ["tofu"], 150, "1 Portion (150 g)",
     {"protein", "eisen", "calcium", "hauptmahlzeit", "huelsen"}, None),
    ("hummus", "Hummus", "H960000", ["hummus"], 60, "3 EL (60 g)", {"snack", "ballast", "huelsen"}, None),
    ("haferflocken", "Haferflocken", "C133000", ["hafer", "flocken"], 60, "6 EL (60 g)",
     {"kh", "fruehstueck", "ballast", "eisen", "magnesium", "vor"}, None),
    ("vollkornbrot", "Vollkornbrot", None, ["vollkornbrot"], 90, "2 Scheiben (90 g)",
     {"kh", "fruehstueck", "ballast"}, None),
    ("naturreis", "Naturreis, gekocht", "C351032", ["reis", "unpoliert", "gekocht"], 200, "1 Portion (200 g)",
     {"kh", "hauptmahlzeit", "vor", "nach"}, None),
    ("vollkornnudeln", "Vollkornnudeln, gekocht", "E500032", ["vollkornteigwaren", "gekocht"], 200,
     "1 Portion (200 g)", {"kh", "hauptmahlzeit", "ballast", "nach"}, None),
    ("kartoffeln", "Kartoffeln, gekocht", "K110132", ["kartoffel", "geschalt", "gekocht"], 250,
     "1 Portion (250 g)", {"kh", "hauptmahlzeit", "kalium"}, None),
    ("banane", "Banane", "F503100", ["banane", "roh"], 120, "1 Banane", {"kh", "snack", "vor", "kalium"}, None),
    ("datteln", "Datteln, getrocknet", "F504400", ["dattel", "getrocknet"], 40, "4 Stück (40 g)",
     {"kh", "snack", "vor"}, None),
    ("reiswaffeln", "Reiswaffeln", "C532700", ["reiswaffel"], 30, "3 Stück", {"kh", "snack", "vor"}, None),
    ("apfel", "Apfel", "F110100", ["apfel", "roh"], 150, "1 Apfel", {"snack", "obst"}, None),
    ("orange", "Orange", None, ["orange", "roh"], 150, "1 Orange", {"snack", "obst", "vitc"}, None),
    ("kiwi", "Kiwi", None, ["kiwi", "roh"], 150, "2 Kiwis", {"snack", "obst", "vitc"}, None),
    ("beeren", "Heidelbeeren", "F304100", ["heidelbeere", "roh"], 125, "1 Schale (125 g)",
     {"snack", "obst", "fruehstueck"}, None),
    ("brokkoli", "Brokkoli, gekocht", "G312132", ["broccoli", "gekocht"], 200, "1 Portion (200 g)",
     {"gemuese", "hauptmahlzeit", "vitc", "calcium", "ballast"}, None),
    ("spinat", "Spinat, gekocht", "G210132", ["spinat", "gekocht"], 150, "1 Portion (150 g)",
     {"gemuese", "hauptmahlzeit", "magnesium", "eisen"}, None),
    ("paprika", "Paprika rot, roh", "G543100", ["gemusepaprika", "rot", "roh"], 150, "1 Paprika",
     {"gemuese", "snack", "vitc"}, None),
    ("karotte", "Karotte, roh", "G620100", ["karotte", "roh"], 100, "1 große Karotte", {"gemuese", "snack"}, None),
    ("walnuesse", "Walnüsse", "H120100", ["walnuss"], 25, "1 Handvoll (25 g)", {"nuesse", "snack", "magnesium"},
     None),
    ("mandeln", "Mandeln", "H210100", ["mandel", "suss"], 25, "1 Handvoll (25 g)",
     {"nuesse", "snack", "magnesium", "calcium"}, None),
    ("kuerbiskerne", "Kürbiskerne", "H310100", ["kurbiskern"], 25, "1 Handvoll (25 g)",
     {"nuesse", "snack", "eisen", "magnesium", "zink"}, None),
    ("leinsamen", "Leinsamen", None, ["leinsamen"], 15, "1 EL (15 g)", {"nuesse", "fruehstueck", "ballast"}, None),
]

TOPIC_SOURCES = {
    "timing_vor": "Thomas et al. 2016 (ACSM/AND/DC)",
    "timing_nach": "Kerksick et al. 2017 (ISSN Nutrient Timing)",
    "protein": "Kerksick et al. 2017 (ISSN Nutrient Timing)",
    "abend": "Kerksick et al. 2017 (ISSN): 30–40 g Casein vor dem Schlafen",
    "dge": "DGE „Gut essen und trinken“ 2024",
    "eisen": "DGE-Referenzwerte Eisen",
    "jod": "DGE/ÖGE Jod 2025",
    "vitd": "BfR FAQ Vitamin D; DGE-Referenzwerte Vitamin D",
    "b12": "DGE FAQ Nahrungsergänzungsmittel",
    "bilanz": "Schätzung aus Gewichtsverlauf (≈ 7.700 kcal je kg)",
}

_resolved = {}


def _resolve(key):
    """BLS-Eintrag zu einem Vorschlag: fester Code, sonst kürzester Name mit allen Suchwörtern."""
    if _resolved.get(key):
        return _resolved[key]
    cand = next(c for c in CANDIDATES if c[0] == key)
    code, must = cand[2], cand[3]
    hit = bls.get(code) if code else None
    if hit and hit["per100"].get("kcal") is not None:
        _resolved[key] = {"code": hit["code"], "bls_name": hit["name"], "per100": hit["per100"],
                          "is_liquid": hit["is_liquid"]}
        return _resolved[key]
    best = None
    for c, name, nn, per100, liquid in bls.index_rows():
        words = nn.split()
        if not all(any(w.startswith(m) for w in words) for m in must):
            continue
        if per100.get("kcal") is None or c[:1] in ("X", "Y", "D"):
            continue
        if best is None or len(nn) < best[0]:
            best = (len(nn), {"code": c, "bls_name": name, "per100": per100, "is_liquid": liquid})
    _resolved[key] = best[1] if best else None
    return _resolved[key]


def reset_cache():
    _resolved.clear()


def allowed(animal, diet):
    if diet in (None, "omnivor", "pescetarisch"):
        return True
    if diet == "vegetarisch":
        return animal != "fisch"
    if diet == "vegan":
        return animal is None
    return True


def candidates(diet="pescetarisch"):
    out = []
    for key, label, _code, _m, grams, text, tags, animal in CANDIDATES:
        if not allowed(animal, diet):
            continue
        r = _resolve(key)
        if not r:
            continue
        out.append({"key": key, "name": label, "grams": grams, "portion": text, "tags": tags,
                    "per100": r["per100"], "bls_code": r["code"], "bls_name": r["bls_name"],
                    "is_liquid": r["is_liquid"], "nutr": N.scale(r["per100"], grams)})
    return out


# --------------------------------------------------------------------------
# Heute
# --------------------------------------------------------------------------

def expected_fraction(now: datetime.datetime) -> float:
    """Wie viel vom Tagesziel bis jetzt ungefähr gegessen sein dürfte (7 Uhr 10 %, 21 Uhr 100 %)."""
    h = now.hour + now.minute / 60
    if h <= 7:
        return 0.1
    if h >= 21:
        return 1.0
    return round(0.1 + 0.9 * (h - 7) / 14, 2)


GAP_WEIGHTS = {"protein_g": 1.6, "carbs_g": 1.0, "fiber_g": 0.8, "water_ml": 0.0,
               "iron_mg": 0.5, "magnesium_mg": 0.4, "calcium_mg": 0.4, "potassium_mg": 0.3,
               "zinc_mg": 0.4, "iodine_ug": 0.4, "omega3_mg": 0.5, "vitc_mg": 0.3, "b12_ug": 0.3,
               "vitd_ug": 0.2}


def _gaps(totals, targets, frac, keys):
    gaps = {}
    for k in keys:
        t = targets.get(k)
        if not t:
            continue
        need = t * frac - (totals.get(k) or 0)
        if need > 0:
            gaps[k] = need
    return gaps


def pick_foods(gaps, targets, remaining_kcal, pool, mode=None, n=3, limits=None):
    """Gierige Auswahl: jeweils das Lebensmittel, das die größten Lücken je Kalorie füllt."""
    gaps = dict(gaps)
    limits = dict(limits or {})
    chosen = []
    used_tags = set()
    budget = remaining_kcal
    for _ in range(n):
        best = None
        for f in pool:
            if f in chosen:
                continue
            kcal = f["nutr"].get("kcal") or 0
            if budget < 150 and kcal > 150:
                continue
            if kcal > max(budget, 150) + 100:
                continue
            benefit = 0.0
            for k, gap in gaps.items():
                c = f["nutr"].get(k) or 0
                w = GAP_WEIGHTS.get(k, 0.3)
                if mode == "vor" and k == "carbs_g":
                    w = 2.0
                if mode == "nach" and k in ("protein_g", "carbs_g"):
                    w = 1.8
                benefit += w * min(c, gap) / (targets.get(k) or 1)
            for k, room in limits.items():   # Zucker/gesättigte Fette über der Restmenge
                c = f["nutr"].get(k) or 0
                if c > room:
                    benefit -= 0.2 * (c - room) / max(room, 5)
            tags = f["tags"]
            if mode and mode in tags:
                benefit *= 1.4
            if mode == "vor" and ("ballast" in tags and "kh" not in tags or (f["nutr"].get("fat_g") or 0) > 15):
                benefit *= 0.4   # vor dem Training leicht verdaulich
            if tags & used_tags & {"protein", "kh", "obst", "nuesse", "gemuese"}:
                benefit *= 0.6   # Abwechslung
            score = benefit / max(kcal, 60) * 100
            if benefit > 0.03 and (best is None or score > best[0]):
                best = (score, f)
        if not best:
            break
        f = best[1]
        chosen.append(f)
        used_tags |= f["tags"]
        budget -= f["nutr"].get("kcal") or 0
        for k in list(gaps):
            gaps[k] -= f["nutr"].get(k) or 0
            if gaps[k] <= 0:
                del gaps[k]
        for k in list(limits):
            limits[k] -= f["nutr"].get(k) or 0
    return chosen


def _food_out(f):
    n = f["nutr"]
    return {"key": f["key"], "name": f["name"], "portion": f["portion"], "grams": f["grams"],
            "kcal": round(n.get("kcal") or 0), "protein_g": round(n.get("protein_g") or 0, 1),
            "carbs_g": round(n.get("carbs_g") or 0, 1), "fat_g": round(n.get("fat_g") or 0, 1),
            "bls_code": f["bls_code"], "bls_name": f["bls_name"], "is_liquid": f["is_liquid"],
            "per100": f["per100"]}


def _activity_end(a, date):
    try:
        hh, mm = (a.get("start") or "").split(":")
        start = datetime.datetime.combine(date, datetime.time(int(hh), int(mm)))
        return start + datetime.timedelta(minutes=a.get("duration_min") or 0)
    except (ValueError, AttributeError):
        return None


def day_recommendations(d: dict, diet="pescetarisch", now: datetime.datetime = None) -> list:
    """Empfehlungen für einen Tag (Ergebnis von summary.day)."""
    now = now or datetime.datetime.now()
    date = datetime.date.fromisoformat(d["date"])
    is_today = date == now.date()
    t, g, kind = d["totals"], d["targets"], d.get("target_kind") or {}
    frac = expected_fraction(now) if is_today else 1.0
    remaining = (g.get("kcal") or 0) - (t.get("kcal") or 0)
    w = (d.get("profile") or {}).get("weight_kg") or 75
    recs = []
    pool = candidates(diet) if bls.count() else []

    # Kontext: vor / nach dem Training, Abend
    mode = None
    last_meal = None
    for c in (d.get("categories") or {}).values():
        for m in c.get("meals", []):
            if m.get("time") and (last_meal is None or m["time"] > last_meal):
                last_meal = m["time"]
    if is_today:
        ends = [e for e in (_activity_end(a, date) for a in d.get("activities") or []) if e]
        recent = [e for e in ends if datetime.timedelta(0) <= now - e <= datetime.timedelta(hours=3)]
        if recent and (last_meal is None or last_meal < max(recent).strftime("%H:%M")):
            mode = "nach"
        elif d.get("day_source") == "geplant" and d.get("day_type") in ("moderat", "hart", "sehr_hart") \
                and now.hour < 20:
            mode = "vor"
        elif now.hour >= 19:
            mode = "abend"

    if not is_today:
        frac = 1.0

    # 1) Timing rund ums Training
    if mode == "vor":
        lo, hi = round(1 * w), round(4 * w)
        recs.append({"id": "vor_training", "type": "timing", "icon": "lightningBolt",
                     "title": "Vor der Einheit Kohlenhydrate tanken",
                     "text": f"Heute steht {d.get('plan_text') or 'eine Einheit'} an. 1–4 Stunden vorher "
                             f"helfen 1–4 g Kohlenhydrate je kg ({lo}–{hi} g, je nach Abstand). "
                             "Leicht verdaulich: wenig Fett und Ballaststoffe kurz vorher.",
                     "source": TOPIC_SOURCES["timing_vor"]})
    elif mode == "nach":
        p = round(0.3 * w)
        hard = d.get("day_type") in ("hart", "sehr_hart")
        recs.append({"id": "nach_training", "type": "timing", "icon": "run",
                     "title": "Nach dem Training: Protein + Kohlenhydrate",
                     "text": f"Etwa {p} g Protein (0,25–0,4 g/kg) in den nächsten 1–2 Stunden"
                             + (f", dazu reichlich Kohlenhydrate ({round(1.0 * w)}–{round(1.2 * w)} g je Stunde "
                                "in den ersten Stunden, wenn morgen wieder hart trainiert wird)." if hard else
                                ", dazu Kohlenhydrate für die Glykogenspeicher."),
                     "source": TOPIC_SOURCES["timing_nach"]})

    # 2) Proteinverteilung
    pm, pmin = d.get("protein_meals", 0), d.get("protein_meal_min_g", round(0.25 * w))
    expected_pm = 0 if not is_today else (1 if now.hour >= 11 else 0) + (1 if now.hour >= 15 else 0) + \
        (1 if now.hour >= 20 else 0)
    if not is_today:
        expected_pm = 3
    if pm < expected_pm and (t.get("protein_g") or 0) < (g.get("protein_g") or 0):
        recs.append({"id": "protein_verteilung", "type": "wie", "icon": "dumbbell",
                     "title": f"Nächste Mahlzeit mit mindestens {pmin} g Protein",
                     "text": f"Bisher {pm} proteinreiche Mahlzeit(en). 3–4 Mahlzeiten mit je ≥ {pmin} g "
                             "über den Tag verteilt nutzt der Muskel besser als eine große Portion."
                             + (" Am Abend eignet sich Quark oder Skyr (Casein)." if mode == "abend" else ""),
                     "source": TOPIC_SOURCES["abend" if mode == "abend" else "protein"]})

    # 3) Was noch essen: Lücken füllen
    keys = ["protein_g", "carbs_g", "fiber_g"]
    if not is_today or now.hour >= 14:
        keys += ["iron_mg", "magnesium_mg", "calcium_mg", "potassium_mg", "zinc_mg", "iodine_ug",
                 "omega3_mg", "vitc_mg", "b12_ug"]
    gaps = _gaps(t, g, frac, keys)
    if is_today and pool and remaining > 80 and gaps:
        limits = {k: (g.get(k) or 0) - (t.get(k) or 0) for k in ("sugar_g", "satfat_g")}
        foods = pick_foods(gaps, g, remaining, pool, mode=mode, n=3, limits=limits)
        if foods:
            main = sorted(gaps, key=lambda k: -gaps[k] / (g.get(k) or 1) * GAP_WEIGHTS.get(k, 0.3))[:3]
            labels = ", ".join(N.NUTRIENTS[k][0] for k in main)
            recs.append({"id": "essen", "type": "essen", "icon": "silverwareForkKnife",
                         "title": "Passt noch gut in den Tag",
                         "text": f"Noch {round(remaining)} kcal offen. Am meisten fehlt gerade: {labels}.",
                         "foods": [_food_out(f) for f in foods],
                         "source": "BLS 4.0 (Nährwerte), Ziele siehe „Wie das Ziel zustande kommt“"})

    # 4) Flüssigkeit
    wt, wg = t.get("water_ml") or 0, g.get("water_ml") or 0
    if is_today and wg and wt < wg * frac * 0.75:
        missing = round((wg * frac - wt) / 50) * 50
        recs.append({"id": "wasser", "type": "wie", "icon": "cupWater", "title": "Etwas trinken",
                     "text": f"Gut {missing} ml hinter dem Tagesverlauf. Wasser oder ungesüßter Tee "
                             "– vor und nach dem Training besonders.",
                     "source": "DGE-Referenzwerte Wasser"})

    # 5) Grenzen
    for k, label in (("sugar_g", "Zucker"), ("satfat_g", "gesättigte Fettsäuren")):
        if kind.get(k) == "max" and g.get(k) and (t.get(k) or 0) > g[k] * 1.1:
            recs.append({"id": f"grenze_{k}", "type": "hinweis", "icon": "alertCircleOutline",
                         "title": f"{label.capitalize()} heute über der Orientierung",
                         "text": f"{round(t.get(k) or 0)} g von höchstens {round(g[k])} g. Kein Drama an einem Tag – "
                                 "im Wochenmittel sollte es darunter bleiben."
                                 + (" Zucker zählt hier inkl. Obst und Milch; Sportgetränke an harten Tagen "
                                    "sind gewollt." if k == "sugar_g" else ""),
                         "source": "DGE/WHO (Orientierung)"})
    if (g.get("kcal") or 0) and (t.get("kcal") or 0) > g["kcal"] * 1.15 and (not is_today or now.hour >= 18):
        recs.append({"id": "kcal_hoch", "type": "hinweis", "icon": "fire",
                     "title": "Mehr Energie als geplant",
                     "text": "Heute gut 15 % über dem Ziel. Wenn das öfter vorkommt, zeigt die Woche es an.",
                     "source": "Tagesziel"})

    # 6) Alles im Lot
    core = ["kcal", "protein_g", "carbs_g", "fiber_g"]
    if not recs and d.get("meals_count") and all((d["progress"].get(k) or 0) >= 90 * frac for k in core):
        recs.append({"id": "gut", "type": "lob", "icon": "thumbUpOutline", "title": "Läuft gut",
                     "text": "Energie, Protein, Kohlenhydrate und Ballaststoffe liegen im Plan.",
                     "source": ""})
    return recs


# --------------------------------------------------------------------------
# Woche
# --------------------------------------------------------------------------

def week_food_groups(meals_by_day: dict) -> dict:
    """Gramm je Lebensmittelgruppe über alle Tage + Anzahl Mahlzeiten mit Fisch/Hülsenfrüchten."""
    import groups
    grams = {k: 0.0 for k in groups.GROUPS}
    fish_meals, fatty_fish_meals, legume_meals = 0, 0, 0
    for meals in meals_by_day.values():
        for m in meals:
            mg = {}
            for it in m["items"]:
                grp = it.get("food_group") or groups.classify(it["name"], it.get("source"), None, it["per100"])
                grams[grp] = grams.get(grp, 0) + (it["amount_g"] or 0)
                mg[grp] = mg.get(grp, 0) + (it["amount_g"] or 0)
            if mg.get("fisch", 0) + mg.get("fisch_fett", 0) >= 60:
                fish_meals += 1
            if mg.get("fisch_fett", 0) >= 60:
                fatty_fish_meals += 1
            if mg.get("huelsenfruechte", 0) >= 60:
                legume_meals += 1
    return {"grams": {k: round(v) for k, v in grams.items()}, "fish_meals": fish_meals,
            "fatty_fish_meals": fatty_fish_meals, "legume_meals": legume_meals}


def nutrient_oracle(key, diet="pescetarisch", n=3):
    """Lebensmittel aus der Vorschlagsliste mit dem meisten <Nährstoff> je Portion."""
    pool = candidates(diet) if bls.count() else []
    # viel je Portion UND je Kalorie (Nährstoffdichte): Menge / Wurzel(kcal)
    ranked = sorted((f for f in pool if (f["nutr"].get(key) or 0) > 0),
                    key=lambda f: -(f["nutr"].get(key) or 0) / max(f["nutr"].get("kcal") or 0, 30) ** 0.5)
    name, unit, _g = N.NUTRIENTS[key]
    out = []
    for f in ranked[:n]:
        amt = f["nutr"].get(key) or 0
        out.append(_food_out(f) | {"amount": round(amt, 1),
                                   "highlight": f"{amt:.0f} {unit} {name}" if amt >= 10 else
                                   f"{amt:.1f} {unit} {name}".replace(".", ",")})
    return out


def week_recommendations(w: dict, fg: dict, diet="pescetarisch", today: datetime.date = None) -> list:
    today = today or datetime.date.today()
    days = max(1, w.get("complete_days") or 0)
    if (w.get("complete_days") or 0) < 3:
        return [{"id": "zu_wenig", "type": "info", "icon": "informationOutline",
                 "title": "Noch zu wenig Daten für Wochenmuster",
                 "text": "Ab 3 vollständig erfassten Tagen zeigt die App, wo es regelmäßig hakt.", "source": ""}]
    recs = []
    gr = fg["grams"]
    avg = w.get("average") or {}

    def low(key, thresh=80):
        tgt = [d["targets"].get(key) for d in w["days"] if d["meals_count"] and d["targets"].get(key)]
        if not tgt or avg.get(key) is None:
            return None
        pct = 100 * avg[key] / (sum(tgt) / len(tgt))
        return round(pct) if pct < thresh else None

    # Fisch (DGE: 1-2x/Woche, ideal einmal fettreich) - Wochenfenster 7 Tage
    if diet in ("omnivor", "pescetarisch"):
        if fg["fish_meals"] == 0:
            recs.append({"id": "fisch", "type": "dge", "icon": "fish", "title": "Diese Woche noch kein Fisch",
                         "text": "1–2 Fischmahlzeiten pro Woche, davon eine fettreich (Lachs, Hering, Makrele) – "
                                 "liefern Omega-3, Jod und Vitamin D.",
                         "foods": [f for f in nutrient_oracle("omega3_mg", diet, 2)],
                         "source": TOPIC_SOURCES["dge"]})
        elif fg["fatty_fish_meals"] == 0:
            recs.append({"id": "fisch_fett", "type": "dge", "icon": "fish", "title": "Einmal fettreichen Fisch",
                         "text": f"{fg['fish_meals']} Fischmahlzeit(en), aber keine fettreiche. Lachs, Hering oder "
                                 "Makrele decken den Omega-3-Bedarf (EPA+DHA) für mehrere Tage.",
                         "foods": nutrient_oracle("omega3_mg", diet, 2), "source": TOPIC_SOURCES["dge"]})
    if fg["legume_meals"] == 0:
        recs.append({"id": "huelsen", "type": "dge", "icon": "leaf", "title": "Hülsenfrüchte einplanen",
                     "text": "Mindestens einmal pro Woche Linsen, Kichererbsen, Bohnen oder Tofu – Protein, "
                             "Ballaststoffe und Eisen ohne Fleisch.",
                     "foods": [f for f in nutrient_oracle("protein_g", diet, 6)
                               if f["key"] in ("linsen", "kichererbsen", "bohnen", "tofu")][:2],
                     "source": TOPIC_SOURCES["dge"]})
    nuts = gr.get("nuesse", 0) / days
    if nuts < 15:
        recs.append({"id": "nuesse", "type": "dge", "icon": "nutrition", "title": "Täglich eine Handvoll Nüsse",
                     "text": f"Im Schnitt {round(nuts)} g Nüsse/Samen pro Tag, empfohlen sind etwa 25 g.",
                     "source": TOPIC_SOURCES["dge"]})
    vegfruit = (gr.get("gemuese", 0) + gr.get("obst", 0)) / days
    if vegfruit < 400:
        recs.append({"id": "obst_gemuese", "type": "dge", "icon": "foodAppleOutline",
                     "title": "Mehr Obst und Gemüse",
                     "text": f"Im Schnitt {round(vegfruit)} g pro Tag – empfohlen sind 5 Portionen (≈ 550 g). "
                             "Eine Portion Gemüse zu jeder Hauptmahlzeit plus Obst als Snack reicht meist.",
                     "source": TOPIC_SOURCES["dge"]})
    grains = gr.get("vollkorn", 0) + gr.get("getreide", 0)
    if grains > 300 and gr.get("vollkorn", 0) / grains < 0.5:
        recs.append({"id": "vollkorn", "type": "dge", "icon": "leaf", "title": "Öfter Vollkorn",
                     "text": f"Nur {round(100 * gr.get('vollkorn', 0) / grains)} % der Getreideprodukte waren Vollkorn. "
                             "Vollkornbrot, Haferflocken, Naturreis: mehr Ballaststoffe, Magnesium und Eisen.",
                     "source": TOPIC_SOURCES["dge"]})

    # Nährstoffe mit wiederkehrender Lücke
    p = low("iron_mg")
    if p:
        recs.append({"id": "eisen", "type": "naehrstoff", "icon": "nutrition", "title": f"Eisen im Schnitt bei {p} %",
                     "text": "Pflanzliches Eisen wird besser aufgenommen mit Vitamin C in derselben Mahlzeit "
                             "(Paprika, Orange, Kiwi). Kaffee und schwarzen Tee lieber mit Abstand zum Essen.",
                     "foods": nutrient_oracle("iron_mg", diet, 3), "source": TOPIC_SOURCES["eisen"]})
    p = low("iodine_ug")
    if p:
        recs.append({"id": "jod", "type": "naehrstoff", "icon": "nutrition", "title": f"Jod im Schnitt bei {p} %",
                     "text": "Konsequent Jodsalz verwenden (zählt die App nicht mit), täglich Milchprodukte und "
                             "1–2x pro Woche Seefisch wie Kabeljau oder Seelachs.",
                     "foods": nutrient_oracle("iodine_ug", diet, 2), "source": TOPIC_SOURCES["jod"]})
    p = low("omega3_mg", 60)
    if p and not any(r["id"].startswith("fisch") for r in recs):
        recs.append({"id": "omega3", "type": "naehrstoff", "icon": "fish",
                     "title": f"Omega-3 (EPA+DHA) bei {p} %",
                     "text": "EPA und DHA stecken fast nur in Fisch; ALA aus Lein- und Walnüssen wird nur zu "
                             "einem kleinen Teil umgewandelt.",
                     "foods": nutrient_oracle("omega3_mg", diet, 2), "source": "EFSA 2012 (250 mg/Tag)"})
    for key in ("magnesium_mg", "calcium_mg", "potassium_mg", "zinc_mg", "fiber_g"):
        p = low(key, 75)
        if p:
            recs.append({"id": key, "type": "naehrstoff", "icon": "nutrition",
                         "title": f"{N.NUTRIENTS[key][0]} im Schnitt bei {p} %",
                         "text": "Am meisten liefern pro Portion:",
                         "foods": nutrient_oracle(key, diet, 3), "source": "DGE-Referenzwerte, BLS 4.0"})
    p = low("b12_ug", 70)
    if p:
        recs.append({"id": "b12", "type": "naehrstoff", "icon": "nutrition", "title": f"Vitamin B12 bei {p} %",
                     "text": "Fisch, Milchprodukte und Eier liefern B12. Bei vorwiegend vegetarischer Ernährung "
                             "rät die DGE, die Versorgung ärztlich prüfen zu lassen.",
                     "foods": nutrient_oracle("b12_ug", diet, 2), "source": TOPIC_SOURCES["b12"]})
    if today.month in (10, 11, 12, 1, 2, 3):
        recs.append({"id": "vitd", "type": "naehrstoff", "icon": "weatherSunny", "title": "Vitamin D im Winterhalbjahr",
                     "text": "Von Oktober bis März bildet die Haut in Deutschland kaum Vitamin D, über Essen "
                             "kommen nur wenige µg. Für diesen Fall nennt die DGE 20 µg/Tag als Präparat – "
                             "am besten Spiegel (25-OH-D) ärztlich prüfen lassen.",
                     "source": TOPIC_SOURCES["vitd"]})

    # Training und Ernährung
    f = w.get("fueling") or {}
    if f.get("hard_days") and (f.get("carbs_pct_hard_days") or 100) < 85:
        recs.append({"id": "kh_hart", "type": "training", "icon": "lightningBolt",
                     "title": f"Harte Tage: Kohlenhydrate nur bei {f['carbs_pct_hard_days']} %",
                     "text": "An Tagen mit langen oder harten Einheiten fehlen Kohlenhydrate – das kostet Qualität "
                             "in der Einheit und Erholung danach. Extra-Portion Reis, Kartoffeln, Haferflocken oder "
                             "Banane einplanen.", "source": TOPIC_SOURCES["timing_vor"]})
    if f.get("protein_pct_training_days") is not None and f["protein_pct_training_days"] < 85:
        recs.append({"id": "protein_training", "type": "training", "icon": "dumbbell",
                     "title": f"Protein an Trainingstagen bei {f['protein_pct_training_days']} %",
                     "text": "Für Regeneration und Kraftaufbau eine proteinreiche Komponente zu jeder Mahlzeit.",
                     "foods": nutrient_oracle("protein_g", diet, 3), "source": TOPIC_SOURCES["protein"]})
    bal = w.get("energy_balance")
    if bal and bal.get("suggest_pal"):
        recs.append({"id": "bilanz", "type": "training", "icon": "scaleBathroom",
                     "title": "Kalorienziel an deinen Verbrauch anpassen",
                     "text": bal["text"], "source": TOPIC_SOURCES["bilanz"]})

    if len(recs) <= (1 if today.month in (10, 11, 12, 1, 2, 3) else 0):
        recs.insert(0, {"id": "woche_gut", "type": "lob", "icon": "thumbUpOutline",
                        "title": "Die Woche passt",
                        "text": "Keine wiederkehrenden Lücken bei Makros, Mikronährstoffen und Lebensmittelgruppen.",
                        "source": ""})
    return recs
