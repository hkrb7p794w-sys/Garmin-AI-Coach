"""Lebensmittelgruppen für die Wochenauswertung nach den DGE-Empfehlungen
„Gut essen und trinken“ (2024).

Zuordnung in dieser Reihenfolge:
1. Gruppe aus der KI-Analyse (Feld "gruppe"), wenn vorhanden.
2. BLS-Code: Der erste Buchstabe ist die BLS-Hauptgruppe (B Brot, C Getreide, D Backwaren,
   E Eier/Teigwaren, F Obst, G Gemüse, H Hülsenfrüchte/Nüsse/Samen/Soja, K Kartoffeln/Pilze,
   M Milch, N Getränke, P alkoholische Getränke, Q Fette, R Würzmittel, S Süßwaren,
   T Fisch, U/V Fleisch, W Wurst, X/Y zusammengesetzte Gerichte).
3. Stichwörter im Namen.
Fisch gilt als fettreich ab 1 g EPA+DHA je 100 g (Lachs, Hering, Makrele liegen deutlich darüber).
"""
from bls import norm

GROUPS = {
    "gemuese": "Gemüse",
    "obst": "Obst",
    "vollkorn": "Vollkorn",
    "getreide": "Getreide (Weißmehl)",
    "kartoffel": "Kartoffeln",
    "huelsenfruechte": "Hülsenfrüchte",
    "nuesse": "Nüsse & Samen",
    "milch": "Milch & Milchprodukte",
    "fisch_fett": "Fisch (fettreich)",
    "fisch": "Fisch (mager)",
    "ei": "Eier",
    "fleisch": "Fleisch & Wurst",
    "fett": "Öle & Fette",
    "suess": "Süßes & Snacks",
    "getraenk": "Getränke",
    "alkohol": "Alkohol",
    "gericht": "Gericht",
    "sonstiges": "Sonstiges",
}

_KW = [
    ("fleisch", ("rind", "schwein", "hahnchen", "huhn", "pute", "lamm", "kalb", "wurst", "salami",
                 "schinken", "speck", "hack", "bolognese", "doner", "gyros", "frikadelle", "leberkas",
                 "burger", "steak", "schnitzel", "currywurst", "wiener", "bratwurst", "chicken")),
    ("fisch", ("lachs", "hering", "makrele", "thunfisch", "kabeljau", "dorsch", "seelachs", "forelle",
               "sardine", "fisch", "garnele", "shrimp", "scampi", "sprotte", "matjes", "rotbarsch",
               "pangasius", "zander", "scholle", "tintenfisch", "muschel")),
    ("huelsenfruechte", ("linse", "kichererbse", "bohne", "erbse", "tofu", "tempeh", "edamame", "soja",
                         "hummus", "lupine", "falafel", "dal")),
    ("nuesse", ("nuss", "nusse", "mandel", "cashew", "pistazie", "erdnuss", "kern", "samen", "leinsamen",
                "chia", "sesam", "tahin", "mus")),
    ("milch", ("milch", "joghurt", "quark", "skyr", "kase", "kefir", "buttermilch", "hutten", "mozzarella",
               "feta", "parmesan", "gouda", "frischkase", "ricotta")),
    ("ei", ("ei", "eier", "ruhrei", "spiegelei", "omelett")),
    ("vollkorn", ("vollkorn", "hafer", "haferflocken", "naturreis", "dinkelvollkorn", "pumpernickel",
                  "musli", "porridge", "grahambrot", "roggenvollkorn", "quinoa", "buchweizen", "hirse")),
    ("getreide", ("brot", "brotchen", "nudel", "pasta", "spaghetti", "reis", "toast", "baguette",
                  "couscous", "bulgur", "teigwaren", "pizza", "wrap", "tortilla", "croissant")),
    ("kartoffel", ("kartoffel", "pommes", "rosti", "puree", "kartoffeln", "batate", "susskartoffel")),
    ("obst", ("apfel", "banane", "beere", "orange", "kiwi", "birne", "traube", "mango", "ananas",
              "pfirsich", "kirsche", "pflaume", "melone", "obst", "dattel", "feige", "mandarine")),
    ("gemuese", ("gemuse", "salat", "tomate", "gurke", "paprika", "brokkoli", "broccoli", "spinat",
                 "karotte", "mohre", "zucchini", "kohl", "zwiebel", "pilz", "champignon", "aubergine",
                 "blumenkohl", "rucola", "lauch", "spargel", "kurbis", "rote bete", "mais", "erbsen")),
    ("fett", ("ol", "butter", "margarine", "olivenol", "rapsol")),
    ("suess", ("schokolade", "keks", "kuchen", "torte", "eis", "gummi", "chips", "riegel", "zucker",
               "honig", "marmelade", "nutella", "pudding", "croissant", "donut", "praline")),
    ("alkohol", ("bier", "wein", "sekt", "schnaps", "likor", "radler", "aperol")),
    ("getraenk", ("wasser", "kaffee", "tee", "saft", "schorle", "cola", "limonade", "espresso",
                  "cappuccino", "latte")),
]


def _keyword(name: str):
    words = norm(name).split()
    joined = " ".join(words)
    for grp, kws in _KW:
        for kw in kws:
            if " " in kw:
                if kw in joined:
                    return grp
            elif any(w == kw or (len(kw) >= 4 and w.startswith(kw)) or (len(kw) >= 5 and kw in w)
                     for w in words):
                return grp
    return None


def _fish_kind(per100):
    o3 = (per100 or {}).get("omega3_mg")
    fat = (per100 or {}).get("fat_g") or 0
    if o3 is not None:
        return "fisch_fett" if o3 >= 1000 else "fisch"
    return "fisch_fett" if fat >= 8 else "fisch"


def _from_bls(code: str, name: str, per100):
    c = (code or "").upper()
    n = norm(name)
    if not c:
        return None
    head = c[0]
    if head in ("B", "C") or c[:2] in ("E4", "E5", "E6"):
        return "vollkorn" if any(k in n for k in ("vollkorn", "hafer", "naturreis", "roggenschrot",
                                                     "pumpernickel", "grahambrot", "hirse", "quinoa",
                                                     "buchweizen")) else "getreide"
    if c[:2] in ("E1",):
        return "ei"
    if head == "D":
        return "suess"
    if head == "F":
        return "getraenk" if "saft" in n else "obst"
    if head == "G":
        return "gemuese"
    if head == "H":
        if any(k in n for k in ("linse", "bohne", "erbse", "kichererbse", "soja", "tofu", "lupine", "hummus",
                                "tempeh")):
            return "huelsenfruechte"
        return "nuesse"
    if head == "K":
        return "kartoffel" if any(k in n for k in ("kartoffel", "batate", "pommes")) else "gemuese"
    if head == "M":
        return "fett" if "butter" in n and "milch" not in n else "milch"
    if head == "N":
        return "getraenk"
    if head == "P":
        return "alkohol"
    if head == "Q":
        return "fett"
    if head == "S":
        return "suess"
    if head == "T":
        return _fish_kind(per100)
    if head in ("U", "V", "W"):
        return "fleisch"
    return None  # X/Y Gerichte, R Würzmittel -> Stichwörter


def classify(name: str, source: str = None, ref: str = None, per100=None, ai_group: str = None) -> str:
    if ai_group in GROUPS:
        g = ai_group
        if g in ("fisch", "fisch_fett"):
            g = _fish_kind(per100) if (per100 or {}).get("omega3_mg") is not None else g
        return g
    g = _from_bls(ref, name, per100) if source == "bls" and ref else None
    if g:
        return g
    g = _keyword(name)
    if g == "fisch":
        return _fish_kind(per100)
    return g or "sonstiges"
