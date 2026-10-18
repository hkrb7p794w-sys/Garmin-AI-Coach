"""Tipps des Tages - feste Regeln statt KI, jede Regel mit Quelle.

Reihenfolge: zuerst Sicherheit (zu schnell abgenommen, sehr wenig gegessen,
Laufumfang zu stark gesteigert), dann das, was diese Woche am meisten bringt,
dann Lob. Höchstens drei Tipps, damit es übersichtlich bleibt.
"""
import datetime

SOURCES = {
    "garthe2011": ("Garthe 2011, IJSNEM", "https://doi.org/10.1123/ijsnem.21.2.97"),
    "jensen2014": ("Jensen 2014, Circulation", "https://doi.org/10.1161/01.cir.0000437739.71477.ee"),
    "reds2023": ("IOC-Konsens REDs 2023", "https://doi.org/10.1136/bjsports-2023-106994"),
    "nielsen2014": ("Nielsen 2014, JOSPT", "https://doi.org/10.2519/jospt.2014.5164"),
    "munoz2014": ("Muñoz 2014, IJSPP", "https://doi.org/10.1123/ijspp.2012-0350"),
    "cava2017": ("Cava 2017, Adv Nutr", "https://doi.org/10.3945/an.116.014506"),
    "morton2018": ("Morton 2018, BJSM", "https://doi.org/10.1136/bjsports-2017-097608"),
    "harvey2019": ("Harvey 2019, Obesity", "https://doi.org/10.1002/oby.22382"),
    "zheng2015": ("Zheng 2015, Obesity", "https://doi.org/10.1002/oby.20946"),
    "paluch2022": ("Paluch 2022, Lancet Public Health", "https://doi.org/10.1016/S2468-2667(21)00302-9"),
    "who2020": ("WHO-Leitlinie 2020", "https://doi.org/10.1136/bjsports-2020-102955"),
}


def _tip(prio, cat, title, text, src=None, kind="info"):
    s = SOURCES.get(src) if src else None
    return {"prio": prio, "cat": cat, "title": title, "text": text, "kind": kind,
            "source": s[0] if s else None, "url": s[1] if s else None}


def build(weight=None, nutrition=None, running=None, gym=None, week=None, today=None, connected=None) -> list:
    today = today or datetime.date.today()
    tips = []
    weight = weight or {}
    nutrition = nutrition or {}
    running = running or {}
    gym = gym or {}
    cur = (week or {}).get("current") or {}

    # --- Sicherheit ---------------------------------------------------------
    t = weight.get("tempo") or {}
    if t.get("kind") == "warn":
        tips.append(_tip(1, "gewicht", "Etwas langsamer abnehmen",
                         "Du nimmst gerade schneller ab als 1 % pro Woche. Bei ~0,7 % pro Woche blieb in einer Studie mehr Muskelmasse erhalten – "
                         "gönn dir etwas mehr, vor allem Eiweiß und Kohlenhydrate rund ums Training.", "garthe2011", "warn"))
    for h in nutrition.get("hints") or []:
        if h["id"] == "low_intake":
            tips.append(_tip(1, "essen", "Genug essen", h["text"], "jensen2014", "warn"))
    for h in running.get("hints") or []:
        if h["id"] == "volume_jump":
            tips.append(_tip(1, "laufen", "Umfang langsam steigern", h["text"], "nielsen2014", "warn"))

    # --- Wirkung diese Woche --------------------------------------------------
    for h in running.get("hints") or []:
        if h["id"] == "too_hard":
            tips.append(_tip(3, "laufen", "Langsamer ist schneller", h["text"], "munoz2014"))
        if h["id"] == "back_to_back":
            tips.append(_tip(4, "laufen", "Pause einplanen", h["text"]))
    for h in nutrition.get("hints") or []:
        if h["id"] == "protein_low":
            tips.append(_tip(3, "essen", "Mehr Eiweiß", h["text"], "morton2018"))
        if h["id"] == "log_more" and nutrition.get("has_data"):
            tips.append(_tip(4, "essen", "Weiter eintragen", h["text"], "harvey2019"))
    gym_target = cur.get("gym_target") or 0
    if gym_target and cur.get("gym", 0) < gym_target and cur.get("days_left", 0) <= 3 and weight.get("has_data"):
        tips.append(_tip(4, "gym", "Krafttraining nicht vergessen",
                         "Beim Abnehmen hilft Krafttraining, die Muskeln zu behalten – schon eine kurze Einheit mit Kniebeugen, Hüftstoß, Rudern und Liegestützen zählt.",
                         "cava2017"))
    if weight.get("has_data") and (weight.get("weighins_7d") or 0) < 3:
        tips.append(_tip(5, "gewicht", "Regelmäßig wiegen",
                         "3–7× pro Woche morgens nach dem Toilettengang wiegen. Der Trend zählt, nicht der einzelne Tag – Schwankungen von 1 kg sind normal.",
                         "zheng2015"))
    sa, sg = cur.get("steps_avg"), cur.get("step_goal")
    if sa and sg and sa < 0.7 * sg and today.weekday() >= 2:
        tips.append(_tip(5, "alltag", "Mehr Schritte",
                         f"Diese Woche Ø {sa:,} Schritte (Ziel {sg:,}). Ein 20-Minuten-Spaziergang bringt ca. 2.000 Schritte und zählt auch für den Kalorienverbrauch.".replace(",", "."),
                         "paluch2022"))
    if cur and cur.get("active_min", 0) < 150 and cur.get("days_left", 7) <= 2 and cur.get("active_min", 0) >= 90:
        tips.append(_tip(5, "alltag", "Fast 150 Minuten",
                         f"Noch {150 - cur['active_min']} Minuten bis zur WHO-Empfehlung diese Woche – ein flotter Spaziergang reicht.", "who2020"))

    # --- Lob -----------------------------------------------------------------
    if cur.get("workouts_ok"):
        tips.append(_tip(6, "lob", "Wochenziel geschafft", "Alle geplanten Einheiten erledigt – stark! Der Rest der Woche darf locker sein."))
    if t.get("kind") == "good" and weight.get("rate_pct_week") is not None and weight["rate_pct_week"] < -0.15:
        tips.append(_tip(6, "lob", "Gutes Tempo", t.get("text", "")))
    pd = (running.get("pace") or {}).get("easy_pace_delta")
    if pd is not None and pd <= -10:
        tips.append(_tip(6, "lob", "Du wirst schneller",
                         f"Deine lockere Pace ist {abs(pd)} s/km schneller als vor einem Monat – bei gleichem Gefühl."))
    if any(r.get("new") for r in gym.get("records") or []):
        tips.append(_tip(6, "lob", "Neuer Gym-Rekord", "Diese Woche hast du eine Übung verbessert – weiter so."))

    if not tips:
        tips.append(_tip(9, "allgemein", "Dranbleiben",
                         "Regelmäßigkeit schlägt Intensität: lieber oft und locker als selten und hart."))
    tips.sort(key=lambda x: x["prio"])
    seen, out = set(), []
    for tip in tips:
        if tip["title"] in seen:
            continue
        seen.add(tip["title"])
        out.append(tip)
    return out[:3]
