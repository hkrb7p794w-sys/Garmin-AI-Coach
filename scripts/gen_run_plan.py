"""Markiert wettkampfspezifische Laufeinheiten im Saisonplan und erzeugt run_plan.json fürs Add-on.

Auftrag Alex 21.10.2026: Laufeinheiten zur Vorbereitung auf einen Wettkampf (Marathontempo, Renntempo
Almere, Taper- und Rennwochen-Tempo, Longrun-Abschnitte im Marathontempo) werden als „Wettkampf“
gekennzeichnet und einzeln angenommen oder abgelehnt. Abgelehnt -> Alternative aus dem Grundmuster
(Schwelle oder 4×4 im Wechsel, im Taper kurze Schwelle, Longrun komplett locker).

Schreibt die Felder qw/qa/qca (Qualitätslauf) und lw/la (Longrun) in den RAW-Block von
dashboard/custom_templates/coach_plan.jinja und garmin_ai_coach/run_plan.json.
Aufruf: python3 scripts/gen_run_plan.py  (idempotent)
"""
import json
import re

JINJA = "dashboard/custom_templates/coach_plan.jinja"
OUT = "garmin_ai_coach/run_plan.json"
COMP = ("Marathontempo", "Taper", "Rennwoche", "Renntempo-Lauf")
Q44 = ("Intervall 4×4 min", "Intervall 4×4 min: 4×4 min bei 90–95 % HFmax (Richtwert §I§ /km), 3 min Trab")
QSCHW = ("Schwelle 3×2 km", "Schwelle 3×2 km: 3×2 km @ §T§ /km, 2 min Trab")
QTAPER = ("Schwelle 2×2 km", "Schwelle 2×2 km: 2×2 km @ §T§ /km, 2 min Trab (kurz, Taper)")
QRACE = ("Rennwoche locker", "Rennwoche: Di/Mi 30 min locker + 4 Steigerungen · danach nur noch locker")

s = open(JINJA, encoding="utf-8").read()
a = s.index('{"weeks":[')
b = s.index("{% endraw %}")
d = json.loads(s[a:b])
weeks = d["weeks"]
last_kind = None
out = []
for w in weeks:
    for k in ("qw", "qa", "qca", "lw", "la"):
        w.pop(k, None)
    qc = w.get("qc") or ""
    if qc.startswith(COMP):
        w["qw"] = 1
        if "Taper" in w["ph"] and not qc.startswith("Rennwoche"):
            alt = QTAPER
        elif qc.startswith("Rennwoche"):
            alt = QRACE
        else:
            alt = QSCHW if last_kind == "4x4" else Q44
        w["qca"], w["qa"] = alt
    elif qc.startswith("Schwelle"):
        last_kind = "schwelle"
    elif qc.startswith("Intervall"):
        last_kind = "4x4"
    if w.get("qw") and w["qca"].startswith("Schwelle 3×2"):
        last_kind = "schwelle"
    elif w.get("qw") and w["qca"].startswith("Intervall"):
        last_kind = "4x4"
    l = w.get("l") or ""
    if "§MP§" in l and w.get("key") != "marathon":
        w["lw"] = 1
        w["la"] = f"{str(w['lr']).replace('.', ',')} km komplett locker (§E§ bzw. HF Zone 2)"
    out.append({k: w.get(k) for k in ("w", "ph", "f", "q", "qc", "qw", "qa", "qca", "l", "lr", "lw", "la", "key")})

lines = ",\n".join(json.dumps(w, ensure_ascii=False, separators=(",", ":")) for w in weeks)
raw = s[a:b]
rest = raw[raw.index('],\n"zw"'):]
s = s[:a] + '{"weeks":[\n' + lines + rest + s[b:]
open(JINJA, "w", encoding="utf-8").write(s)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for w in out:
    if w.get("qw") or w.get("lw"):
        print(w["w"], w["ph"], "| Q:", w["qc"] if w.get("qw") else "-", "->", w.get("qca") or "-", "| L:", (w["l"] if w.get("lw") else "-")[:40])
