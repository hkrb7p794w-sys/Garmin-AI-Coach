"""Freitext oder Foto -> Lebensmittel, Mengen, Nährwerte.

Ablauf
1. Gemini zerlegt die Mahlzeit in Positionen: Name, Menge in g/ml (wie gegessen),
   Suchbegriff im Stil des Bundeslebensmittelschlüssels und eine eigene Schätzung
   der Nährwerte je 100 g.
2. Jede Position wird mit eigenen Lebensmitteln, Open Food Facts (Barcode auf
   Verpackung) und dem BLS abgeglichen. Unter den Text-Treffern gewinnt der, dessen
   Nährwerte am besten zur Schätzung passen - das fängt z. B. "Nudeln roh" vs.
   "gekocht" (350 vs. 150 kcal/100 g) ab.
3. Ein zweiter, kurzer KI-Aufruf wählt unter den besten BLS-Kandidaten den passenden
   (z. B. "Kaffee mit Milch" statt "Kaffee mit Alkohol") oder verwirft alle.
4. Passt kein Datenbank-Eintrag, bleibt die KI-Schätzung (Quelle "KI") stehen.
   Alles ist vor dem Speichern änderbar; Alternativen werden mitgeliefert.

Grenzen: Portionsgrößen vom Foto sind Schätzungen. Fridolfsson et al. (2025,
Curr Dev Nutr, doi:10.1016/j.cdnut.2025.107556) fanden für ChatGPT-4o/Claude 3.5
rund 36 % mittleren absoluten Fehler bei Gewicht und Energie, für Gemini 1.5 Pro
64-110 %, und bei allen Modellen eine mit der Portionsgröße wachsende
Unterschätzung. Deshalb: Nährwerte aus Datenbanken statt KI, Mengen im
Prüf-Fenster korrigierbar.
"""
import datetime

import bls
import db
import gemini
import nutrients as N
import off

CATEGORY_ENUM = ["fruehstueck", "mittagessen", "abendessen", "snack", "sonstiges"]

_N100_PROPS = {k: {"type": ["number", "null"]} for k in N.KEYS if k != "water_ml"}
_N100_PROPS["water_g"] = {"type": ["number", "null"]}

SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "kategorie": {"type": ["string", "null"], "description": "|".join(CATEGORY_ENUM)},
        "hinweis": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "suchbegriff": {"type": "string"},
                    "menge_g": {"type": "number"},
                    "menge_text": {"type": "string"},
                    "getraenk": {"type": "boolean"},
                    "sicherheit": {"type": "string", "enum": ["hoch", "mittel", "niedrig"]},
                    "eigenes": {"type": ["string", "null"]},
                    "barcode": {"type": ["string", "null"]},
                    "naehrwerte_100g": {"type": "object", "properties": _N100_PROPS,
                                        "required": ["kcal", "protein_g", "carbs_g", "fat_g"]},
                },
                "required": ["name", "suchbegriff", "menge_g", "naehrwerte_100g"],
            },
        },
    },
    "required": ["titel", "items"],
}

PROMPT = """Du bist ein präziser Ernährungsassistent für eine deutsche Ernährungs-App.
Zerlege die Mahlzeit in einzelne Lebensmittel und Getränke und antworte NUR mit JSON.

Regeln:
- menge_g: verzehrte Menge in Gramm, so wie gegessen (gekochte Nudeln/Reis = Gewicht gekocht).
  Getränke in ml, als Zahl in menge_g (1 ml = 1 g). Vom Nutzer genannte Mengen haben Vorrang.
- menge_text: kurz und menschlich, z. B. "2 Stück", "1 Scheibe", "1 Tasse (200 ml)".
- suchbegriff: generische deutsche Bezeichnung im Stil des Bundeslebensmittelschlüssels (BLS),
  Hauptwort zuerst, dann Zustand/Zubereitung. Beispiele: "Hühnerei gekocht", "Hühnerei Rührei",
  "Vollkornbrot", "Roggenmischbrot", "Teigwaren gekocht", "Reis poliert, gekocht",
  "Kartoffel gekocht", "Milch 3,5 % Fett", "Milch fettarm 1,5 % Fett", "Kaffee Getränk",
  "Hähnchen Brustfilet gebraten", "Hafer Flocken", "Banane roh", "Butter", "Rapsöl", "Trinkwasser".
- Zusammengesetztes: in Bestandteile zerlegen, wenn das die Datenbanksuche verbessert
  (Kaffee mit Milch = Kaffee + Milch; Müsli = Haferflocken + Milch + Obst; Rührei = Ei + Butter/Öl).
  Klassische Gerichte (Pizza, Lasagne, Döner, Currywurst) als Ganzes lassen.
- Typische Portionen, wenn nichts angegeben: Ei (M) ohne Schale 55 g, Scheibe Brot 45 g,
  Brötchen 60 g, Tasse Kaffee 200 ml, Becher 300 ml, Glas 250 ml, Schuss Milch 30 ml,
  EL Öl 10 g, TL Butter 5 g, Portion Nudeln/Reis gekocht 250 g, Apfel 150 g, Banane (geschält) 120 g,
  Scheibe Käse 25 g, Scheibe Wurst 15 g, Proteinshake-Pulver 30 g.
- naehrwerte_100g: deine beste Schätzung je 100 g so wie verzehrt (kcal, protein_g, carbs_g,
  sugar_g, fat_g, satfat_g, fiber_g, water_g, sodium_mg, potassium_mg, magnesium_mg, calcium_mg,
  iron_mg, zinc_mg, vitd_ug, b12_ug, vitc_mg). Unbekanntes als null.
- sicherheit: "hoch" bei klaren Angaben, "mittel" bei Standardportion, "niedrig" bei Unsicherheit.
- eigenes: wenn eine Position eindeutig zu einem der "eigenen Lebensmittel" unten passt, genau
  dessen Namen eintragen, sonst null.
- barcode: nur wenn auf dem Foto eine Strichcode-Nummer vollständig lesbar ist, sonst null.
- kategorie: nur setzen, wenn der Nutzer die Mahlzeit ausdrücklich nennt ("zum Frühstück",
  "als Snack", "Mittagessen") -> fruehstueck, mittagessen, abendessen, snack; bei reinen Getränken
  oder Supplements -> sonstiges. Sonst null (dann entscheidet die Uhrzeit). titel: kurzer deutscher Titel (max. 40 Zeichen).
- hinweis: ein kurzer Satz zu Unsicherheiten (z. B. verdeckte Zutaten, Ölmenge), sonst "".
{photo_rules}
Eigene Lebensmittel des Nutzers: {personal}

Mahlzeit: {text}
"""

PHOTO_RULES = """- Foto: Schätze Mengen über Bezugsgrößen (Teller ca. 26 cm, Besteck, Glas, Hand).
  Typische Unterschätzung bei Öl, Soßen, Dressings, Butter: sichtbare oder sehr wahrscheinliche
  Fette separat aufführen. Große Portionen werden von Bildmodellen systematisch unterschätzt -
  Teller-/Schüsselfüllung und Höhe der Speisen bewusst einbeziehen. Bei Verpackungen
  Produktname mit Marke als name.
"""

JSON_SHAPE_HINT = """Antwortformat (JSON): {"titel": str, "kategorie": str|null, "hinweis": str,
"items": [{"name": str, "suchbegriff": str, "menge_g": number, "menge_text": str, "getraenk": bool,
"sicherheit": "hoch|mittel|niedrig", "eigenes": str|null, "barcode": str|null,
"naehrwerte_100g": {"kcal": number, "protein_g": number, ...}}]}
"""


def guess_category(now: datetime.datetime = None) -> str:
    t = (now or datetime.datetime.now()).time()
    h = t.hour + t.minute / 60
    if 4 <= h < 10.5:
        return "fruehstueck"
    if 10.5 <= h < 14.5:
        return "mittagessen"
    if 17.5 <= h < 21.5:
        return "abendessen"
    return "snack"


def _estimate_per100(raw: dict) -> dict:
    raw = dict(raw or {})
    if "water_g" in raw and "water_ml" not in raw:
        raw["water_ml"] = raw.pop("water_g")
    est = N.clean(raw)
    return est


def nutrient_distance(cand: dict, est: dict) -> float:
    """0 = gleiche Nährwerte; ~1 = deutlich anders. Basis: kcal und Makros."""
    ke, kc = est.get("kcal"), cand.get("kcal")
    if ke is None or kc is None:
        return 0.5
    d_kcal = abs(kc - ke) / max(ke, kc, 40)
    pe, ce, fe = (est.get(k) or 0 for k in ("protein_g", "carbs_g", "fat_g"))
    pc, cc, fc = (cand.get(k) or 0 for k in ("protein_g", "carbs_g", "fat_g"))
    d_macro = (abs(pc - pe) + abs(cc - ce) + abs(fc - fe)) / max(pe + ce + fe, pc + cc + fc, 5)
    return round(0.6 * d_kcal + 0.4 * d_macro, 3)


def _personal_index():
    out = {}
    for f in db.personal_foods():
        out.setdefault(bls.norm(f["name"]), f)
    return out


def match_item(raw: dict, personal: dict = None) -> dict:
    """Eine KI-Position mit den Datenbanken abgleichen."""
    personal = personal if personal is not None else _personal_index()
    name = (raw.get("name") or "").strip() or "Unbekannt"
    term = (raw.get("suchbegriff") or name).strip()
    try:
        amount = max(0.0, float(raw.get("menge_g") or 0))
    except (TypeError, ValueError):
        amount = 0.0
    est = _estimate_per100(raw.get("naehrwerte_100g"))
    item = {
        "name": name,
        "amount_g": round(amount, 1),
        "amount_text": raw.get("menge_text") or "",
        "is_liquid": bool(raw.get("getraenk")),
        "confidence": raw.get("sicherheit") or "mittel",
        "estimate": est,
        "candidates": [],
    }

    # 1) eigenes Lebensmittel
    own_key = bls.norm(raw.get("eigenes") or "")
    own = personal.get(own_key) if own_key else None
    if own is None:
        own = personal.get(bls.norm(name))
    if own:
        item.update(source=own["source"], food_id=own["id"], ref=str(own["id"]),
                    match_name=own["name"], per100=own["per100"], distance=nutrient_distance(own["per100"], est))
        return item

    # 2) Barcode vom Foto
    code = (raw.get("barcode") or "").strip()
    if code and off.valid_barcode(code):
        try:
            food = barcode_food(code)
            if food:
                item.update(source="off", food_id=food["id"], ref=code, match_name=food["name"],
                            per100=food["per100"], distance=nutrient_distance(food["per100"], est))
                return item
        except Exception as e:
            print(f"[analyze] Barcode {code}: {e}")

    # 3) BLS
    cands = {}
    for c in bls.search(term, 15) + bls.search(name, 8):
        if c["code"] not in cands or cands[c["code"]]["score"] < c["score"]:
            cands[c["code"]] = c
    ranked = []
    for c in cands.values():
        d = nutrient_distance(c["per100"], est)
        ranked.append((c["score"] - 0.9 * d, d, c))
    ranked.sort(key=lambda x: -x[0])
    item["candidates"] = [{"source": "bls", "ref": c["code"], "name": c["name"],
                           "kcal": c["per100"].get("kcal"), "distance": d,
                           "per100": c["per100"]} for _s, d, c in ranked[:8]]
    if ranked:
        _combined, d, best = ranked[0]
        if best["score"] >= 0.55 and d <= 0.5:
            item.update(source="bls", food_id=None, ref=best["code"], match_name=best["name"],
                        per100=best["per100"], distance=d)
            if best["is_liquid"]:
                item["is_liquid"] = True
            return item

    # 4) KI-Schätzung
    item.update(source="ki", food_id=None, ref=None, match_name=None, per100=est, distance=None)
    return item


RERANK_PROMPT = """Ordne jeder Position den passenden Eintrag aus dem Bundeslebensmittelschlüssel zu.
Regeln: gleiches Lebensmittel und gleiche Zubereitung wie beschrieben; keine Varianten mit Zutaten,
die nicht genannt sind (z. B. "mit Alkohol", "mit Zucker", "paniert"); Mengenangaben ignorieren.
Passt kein Kandidat, "code": null. Antworte NUR mit JSON: {{"wahl": [{{"i": 0, "code": "N410100"}}]}}

Ursprüngliche Beschreibung: {text}
Positionen:
{items}
"""
RERANK_SCHEMA = {"type": "object", "properties": {"wahl": {"type": "array", "items": {
    "type": "object", "properties": {"i": {"type": "integer"}, "code": {"type": ["string", "null"]}},
    "required": ["i", "code"]}}}, "required": ["wahl"]}


def rerank(items: list, text: str) -> int:
    """Zweiter KI-Schritt: unter den Datenbank-Kandidaten den passenden wählen.
    Gibt die Anzahl geänderter Positionen zurück; bei Fehler bleibt die Heuristik."""
    todo = [(i, it) for i, it in enumerate(items) if it["source"] in ("bls", "ki") and it.get("candidates")]
    if not todo:
        return 0
    lines = []
    for i, it in todo:
        cands = "; ".join(f'{c["ref"]} = {c["name"]} ({round(c["kcal"] or 0)} kcal)' for c in it["candidates"])
        est = (it.get("estimate") or {}).get("kcal")
        lines.append(f'{i}: "{it["name"]}" (Schätzung {round(est) if est is not None else "?"} kcal/100 g) -> {cands}')
    try:
        data = gemini.generate_json(RERANK_PROMPT.format(text=text or "(Foto)", items="\n".join(lines)),
                                    schema=RERANK_SCHEMA, max_tokens=3000)
    except gemini.GeminiError as e:
        print(f"[analyze] Zuordnung per KI übersprungen: {e}")
        return 0
    changed = 0
    by_index = {i: it for i, it in todo}
    for w in (data or {}).get("wahl") or []:
        it = by_index.get(w.get("i"))
        if it is None:
            continue
        code = w.get("code")
        if code:
            c = next((c for c in it["candidates"] if c["ref"] == code), None)
            if c and (it["source"] != "bls" or it.get("ref") != code):
                it.update(source="bls", food_id=None, ref=code, match_name=c["name"], per100=c["per100"],
                          distance=c["distance"])
                changed += 1
        elif it["source"] == "bls" and it.get("estimate", {}).get("kcal") is not None:
            it.update(source="ki", food_id=None, ref=None, match_name=None, per100=it["estimate"], distance=None)
            changed += 1
    return changed


def barcode_food(code: str):
    """Barcode -> Lebensmittel aus lokalem Speicher oder Open Food Facts."""
    code = "".join(ch for ch in code if ch.isdigit())
    food = db.find_food("off", code)
    if food:
        return food
    p = off.lookup(code)
    if not p or not p["has_nutrition"]:
        return None
    name = p["name"] if not p.get("brand") or p["brand"].lower() in p["name"].lower() \
        else f"{p['name']} ({p['brand']})"
    return db.upsert_food("off", code, name, p["per100"], brand=p.get("brand"),
                          serving_g=p.get("serving_g"), serving_label=p.get("serving_label"),
                          is_liquid=p.get("is_liquid"))


def analyze(text: str = None, image_b64: str = None, mime: str = "image/jpeg") -> dict:
    personal_foods = db.personal_foods(60)
    personal = {}
    for f in personal_foods:
        personal.setdefault(bls.norm(f["name"]), f)
    names = ", ".join(f["name"] for f in personal_foods[:40]) or "(keine)"
    prompt = PROMPT.format(
        photo_rules=PHOTO_RULES if image_b64 else "",
        personal=names,
        text=(text or "").strip() or ("(siehe Foto)" if image_b64 else ""),
    )
    try:
        data = gemini.generate_json(prompt, image_b64=image_b64, mime=mime, schema=SCHEMA)
    except gemini.GeminiError as e:
        if "Schema" in str(e):
            data = gemini.generate_json(prompt + JSON_SHAPE_HINT, image_b64=image_b64, mime=mime)
        else:
            raise
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        raise gemini.GeminiError("KI-Antwort ohne Lebensmittel-Liste")
    items = [match_item(r, personal) for r in raw_items if isinstance(r, dict)]
    if bls.count():
        rerank(items, text)
    cat = data.get("kategorie") if data.get("kategorie") in CATEGORY_ENUM else None
    return {
        "title": (data.get("titel") or "").strip()[:60],
        "category": cat,
        "category_guess": guess_category(),
        "hint": data.get("hinweis") or "",
        "items": items,
        "model": gemini.last_model(),
        "raw": data,
    }
