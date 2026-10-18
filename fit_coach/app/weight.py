"""Gewicht: Quellen zusammenführen, Trend glätten, Tempo bewerten.

Warum ein Trend statt des Tageswerts: Das Körpergewicht schwankt von Tag zu Tag
um bis zu 1-2 kg (Wasser, Salz, Darminhalt, Zyklus). Der Tageswert sagt deshalb
wenig; erst der geglättete Verlauf zeigt, ob Fett ab- oder zunimmt. Regelmäßiges
Wiegen ist in Längsschnittstudien mit mehr Gewichtsabnahme verbunden und nicht
mit negativen psychischen Folgen (Zheng 2015, Obesity, doi:10.1002/oby.20946).

Glättung: exponentiell gewichteter Mittelwert mit 10 % pro Tag (Prinzip aus
„The Hacker's Diet“, auch in Apps wie Libra/Happy Scale). Fehlt ein Tag, zählt
die nächste Messung so, als wäre sie an den fehlenden Tagen gleich gewesen
(höchstens 7 Tage), damit der Trend nach einer Pause nicht ewig hinterherhinkt.

Tempo: Bei Sportlern erhielt eine Abnahme von ~0,7 % des Körpergewichts pro
Woche die Muskelmasse besser als ~1,4 % (Garthe 2011, IJSNEM,
doi:10.1123/ijsnem.21.2.97). Daraus der Zielkorridor 0,5-1 % pro Woche; schneller
ist kein Fehler, wird aber als „schneller als empfohlen“ markiert.

Quellen-Priorität pro Tag: eigene Eingabe im Dashboard > Garmin (Waage/App)
> Yazio. So lässt sich ein falscher Wert durch eine eigene Eingabe korrigieren.
"""
import datetime

ALPHA = 0.10
MAX_GAP_DAYS = 7
SOURCE_PRIORITY = ("manual", "garmin", "yazio")
SOURCE_LABEL = {"manual": "Dashboard", "garmin": "Garmin", "yazio": "Yazio"}
PLAUSIBLE = (30.0, 250.0)
TARGET_BAND_PCT = (0.5, 1.0)  # Abnahme pro Woche in % des Körpergewichts


def _d(s) -> datetime.date:
    return datetime.date.fromisoformat(str(s)[:10])


def merge_sources(sources: dict) -> list:
    """sources = {"manual": {date: kg}, "garmin": {...}, "yazio": {...}} ->
    [{date, kg, source}] sortiert, ein Wert pro Tag, unplausible Werte verworfen."""
    by_day = {}
    for src in reversed(SOURCE_PRIORITY):  # niedrigste Priorität zuerst, höhere überschreiben
        for day, kg in (sources.get(src) or {}).items():
            try:
                v = float(kg)
                _d(day)
            except (TypeError, ValueError):
                continue
            if not (PLAUSIBLE[0] <= v <= PLAUSIBLE[1]):
                continue
            by_day[str(day)[:10]] = {"date": str(day)[:10], "kg": round(v, 2), "source": src}
    return [by_day[k] for k in sorted(by_day)]


def trend_series(points: list) -> list:
    """[{date, kg}] -> [{date, kg, trend}] (EWMA mit Lückenausgleich)."""
    out = []
    trend = None
    prev_day = None
    for p in points:
        day = _d(p["date"])
        w = p["kg"]
        if trend is None:
            trend = w
        else:
            gap = max(1, min(MAX_GAP_DAYS, (day - prev_day).days))
            a = 1 - (1 - ALPHA) ** gap
            trend = trend + a * (w - trend)
        prev_day = day
        out.append({**p, "trend": round(trend, 2)})
    return out


def _trend_at(series: list, day: datetime.date):
    """Trendwert am oder vor `day` (None, wenn es davor nichts gibt)."""
    val = None
    for p in series:
        if _d(p["date"]) <= day:
            val = p["trend"]
        else:
            break
    return val


def weekly_rate(points: list, today: datetime.date, window_days: int = 28):
    """Steigung (kg/Woche) per linearer Regression der Messwerte im Fenster.
    Braucht mindestens 5 Messungen, die mindestens 14 Tage auseinander liegen -
    sonst None (zu wenig Daten für eine ehrliche Aussage)."""
    start = today - datetime.timedelta(days=window_days)
    pts = [(_d(p["date"]), p["kg"]) for p in points if _d(p["date"]) >= start]
    if len(pts) < 5 or (pts[-1][0] - pts[0][0]).days < 14:
        return None
    xs = [(d - pts[0][0]).days for d, _ in pts]
    ys = [w for _, w in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return round(slope * 7, 3)


def de(x, digits=1) -> str:
    """Deutsche Zahl: 0.6 -> „0,6“."""
    return f"{x:.{digits}f}".replace(".", ",")


def tempo(rate_kg_week, trend_kg, wants_loss: bool = True) -> dict:
    """Einordnung des Tempos. kind: good | warn | neutral."""
    if rate_kg_week is None or not trend_kg:
        return {"kind": "neutral", "label": "Noch zu wenig Messungen",
                "text": "Für ein Tempo braucht es mindestens 5 Messungen über 2 Wochen."}
    pct = rate_kg_week / trend_kg * 100
    lo, hi = TARGET_BAND_PCT
    if not wants_loss:
        if abs(pct) <= 0.25:
            return {"kind": "good", "label": "Gewicht stabil", "text": "Das Gewicht hält sich – passt zum Ziel."}
        return {"kind": "neutral", "label": "Trend " + ("steigt" if pct > 0 else "fällt"), "text": ""}
    if pct < -hi:
        return {"kind": "warn", "label": "Schneller als empfohlen",
                "text": f"{de(abs(pct))} % pro Woche. Langsamer (0,5–1 %) erhält mehr Muskeln – lieber etwas mehr essen, vor allem Eiweiß."}
    if pct <= -lo:
        return {"kind": "good", "label": "Im Zielkorridor",
                "text": f"{de(abs(pct))} % pro Woche – genau das empfohlene Tempo (0,5–1 %)."}
    if pct < -0.15:
        return {"kind": "good", "label": "Langsam und stetig",
                "text": f"{de(abs(pct))} % pro Woche. Etwas langsamer als der Korridor, aber nachhaltig."}
    if pct <= 0.15:
        return {"kind": "neutral", "label": "Gerade stabil",
                "text": "Der Trend bewegt sich kaum. Wassereinlagerungen (z. B. nach neuem Training oder im Zyklus) können Fortschritt 1–2 Wochen verdecken."}
    return {"kind": "neutral", "label": "Trend steigt leicht",
            "text": "Kein Grund zur Sorge bei einzelnen Wochen – schau auf die nächsten 2–3 Wochen."}


def analyze(sources: dict, goal_kg=None, start_kg=None, today: datetime.date = None,
            series_days: int = 120) -> dict:
    """Gesamtauswertung für Sensor + Dashboard."""
    today = today or datetime.date.today()
    points = merge_sources(sources)
    series = trend_series(points)
    if not series:
        return {"has_data": False, "goal": goal_kg, "series": [], "measurements": 0}
    last = series[-1]
    trend = last["trend"]
    first = series[0]
    start = float(start_kg) if start_kg else first["kg"]
    wants_loss = goal_kg is None or float(goal_kg) < trend + 0.5
    rate = weekly_rate(points, today)
    t7 = _trend_at(series, today - datetime.timedelta(days=7))
    t30 = _trend_at(series, today - datetime.timedelta(days=30))
    res = {
        "has_data": True,
        "measurements": len(points),
        "last_date": last["date"],
        "last_kg": last["kg"],
        "last_source": SOURCE_LABEL.get(last["source"], last["source"]),
        "days_since_last": (today - _d(last["date"])).days,
        "trend": trend,
        "start_kg": round(start, 1),
        "start_date": first["date"],
        "change_total": round(trend - start, 1),
        "change_7d": round(trend - t7, 1) if t7 is not None else None,
        "change_30d": round(trend - t30, 1) if t30 is not None else None,
        "rate_kg_week": rate,
        "rate_pct_week": round(rate / trend * 100, 2) if rate is not None and trend else None,
        "tempo": tempo(rate, trend, wants_loss),
        "goal": round(float(goal_kg), 1) if goal_kg else None,
        "weighins_7d": sum(1 for p in points if (today - _d(p["date"])).days < 7),
    }
    if goal_kg:
        g = float(goal_kg)
        res["remaining"] = round(trend - g, 1)
        span = start - g
        res["progress_pct"] = max(0, min(100, round((start - trend) / span * 100))) if span > 0 else None
        res["goal_reached"] = trend <= g + 0.05 if span > 0 else None
        # Grobe Hochrechnung nur bei plausiblem Tempo: Abnahme verlangsamt sich
        # in der Realität (Thomas 2013, Int J Obes, doi:10.1038/ijo.2013.51), daher
        # nur als „bei aktuellem Tempo etwa“ und höchstens 2 Jahre voraus.
        if rate is not None and rate < -0.05 and res["remaining"] > 0:
            weeks = res["remaining"] / abs(rate)
            if weeks <= 104:
                res["eta"] = (today + datetime.timedelta(weeks=weeks)).isoformat()
                res["eta_weeks"] = round(weeks)
    cutoff = (today - datetime.timedelta(days=series_days)).isoformat()
    res["series"] = [{"d": p["date"], "w": p["kg"], "t": p["trend"], "s": p["source"][0]}
                     for p in series if p["date"] >= cutoff]
    return res


def weighin_streak(sources: dict, today: datetime.date = None) -> int:
    """Wie viele Tage in Folge (bis heute oder gestern) wurde gewogen?"""
    today = today or datetime.date.today()
    days = {p["date"] for p in merge_sources(sources)}
    d = today if today.isoformat() in days else today - datetime.timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= datetime.timedelta(days=1)
    return n
