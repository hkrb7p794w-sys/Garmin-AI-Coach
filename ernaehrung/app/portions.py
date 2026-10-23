"""Typische Portionsgrößen für schnelle Mengenwahl im Prüf-Fenster.

Richtwerte (essbarer Anteil) in Anlehnung an gängige Portionsangaben der DGE/BZfE und
Verbraucherzentrale; sie ersetzen kein Wiegen, sparen aber das Tippen.
Reihenfolge: Packungsportion (Open Food Facts) > Lebensmittel-Treffer > Grundportionen.
"""
from bls import norm

# Stichwort -> [(Bezeichnung, Gramm)]
TABLE = [
    (("huhnerei", "ei ", "eier", "ruhrei", "spiegelei"), [("1 Ei (M)", 55), ("2 Eier", 110), ("3 Eier", 165)]),
    (("brotchen", "semmel"), [("1 Brötchen", 60), ("2 Brötchen", 120)]),
    (("brot", "toast"), [("1 Scheibe", 45), ("2 Scheiben", 90)]),
    (("banane",), [("1 kleine", 90), ("1 mittlere", 120), ("1 große", 150)]),
    (("apfel", "birne", "orange"), [("1 kleine/r", 120), ("1 mittlere/r", 160)]),
    (("kiwi", "mandarine", "pflaume", "aprikose"), [("1 Stück", 75), ("2 Stück", 150)]),
    (("haferflocken", "hafer flocken", "musli"), [("3 EL", 30), ("6 EL", 60), ("1 Schale", 80)]),
    (("joghurt", "skyr", "quark"), [("1 Becher 150 g", 150), ("1 Becher 250 g", 250), ("1 EL", 20)]),
    (("milch", "drink", "kefir", "buttermilch"), [("Schuss", 30), ("1 Glas", 200), ("1 Becher", 300)]),
    (("kaffee", "tee", "espresso", "cappuccino"), [("1 Espresso", 30), ("1 Tasse", 200), ("1 Becher", 300)]),
    (("wasser", "schorle", "saft", "cola", "limonade"), [("1 Glas", 250), ("0,5 l", 500)]),
    (("kase",), [("1 Scheibe", 25), ("2 Scheiben", 50)]),
    (("butter", "margarine"), [("1 TL", 5), ("1 EL", 10)]),
    (("ol ", "ol,", "olivenol", "rapsol"), [("1 TL", 5), ("1 EL", 10)]),
    (("nuss", "nusse", "mandel", "kern", "samen"), [("1 EL", 10), ("1 Handvoll", 25)]),
    (("reis", "teigwaren", "nudel", "pasta", "spaghetti"), [("1 Portion gekocht", 250), ("½ Portion", 125)]),
    (("kartoffel",), [("1 Kartoffel", 80), ("1 Portion", 250)]),
    (("lachs", "hering", "makrele", "forelle", "kabeljau", "seelachs", "fisch", "filet"),
     [("1 Filet", 125), ("½ Filet", 60)]),
    (("tofu", "linse", "kichererbse", "bohne"), [("1 Portion", 150), ("½ Portion", 75)]),
    (("honig", "marmelade", "konfiture", "zucker"), [("1 TL", 7), ("1 EL", 20)]),
    (("schokolade",), [("1 Rippe", 5), ("1 Riegel", 25)]),
    (("pizza",), [("1 Stück", 120), ("½ Pizza", 200), ("1 Pizza", 400)]),
]


def for_item(name: str, code: str = None, serving_g: float = None):
    n = " " + norm(name) + " "
    out = []
    if serving_g:
        out.append({"label": "1 Portion (Packung)", "grams": round(serving_g)})
    for keys, units in TABLE:
        if any(k in n for k in keys):
            out += [{"label": l, "grams": g} for l, g in units]
            break
    if not out:
        out = [{"label": "50 g", "grams": 50}, {"label": "100 g", "grams": 100}, {"label": "200 g", "grams": 200}]
    return out[:4]
