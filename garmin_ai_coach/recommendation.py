"""Regelbasierte Tagesempfehlung (seit v0.18.0, Review-Punkt 15).

Die Entscheidung "normal / locker / Pause" trifft ab jetzt dieses Modul -
deterministisch, nachvollziehbar und ohne Netzwerk. Gemini formuliert nur noch
den Text dazu. Fällt Gemini aus (wie seit ~20.09.2026 dauerhaft mit HTTP 503),
bleibt die Empfehlung trotzdem korrekt im Dashboard stehen.

Grundlagen der Regeln:
- HRV: maßgeblich ist der 7-Tage-Schnitt relativ zur persönlichen Baseline
  (Garmin "HRV-Status"), nicht die Einzelnacht - Einzelwerte schwanken stark,
  Wochenmittel bilden Anpassung/Ermüdung zuverlässiger ab (Plews et al. 2012/
  2013; Garmin-Handbuch "Heart Rate Variability Status").
- Readiness: Garmins eigene Stufen (1-24 Poor, 25-49 Low, 50-74 Moderate,
  75-94 High, 95-100 Prime). Genutzt wird sie NUR nach unten (Low/Poor): ein
  hoher Wert nach einer trainingsfreien Woche ist kein Qualitätsmerkmal, weil
  die akute Belastung selbst in den Score einfließt (Review-Punkt 2).
- Ruhepuls: deutlich über dem eigenen 7-Tage-Schnitt (+5 bpm) als Warnsignal.
- Schlaf: < 5 h rot, < 6 h gelb.
"""

LEVEL_LABEL = {
    "normal": "Normal trainieren",
    "locker": "Locker / verkürzt",
    "pause": "Ruhetag oder sehr locker",
}
LEVEL_ADVICE = {
    "normal": "Geplante Einheit wie vorgesehen durchziehen.",
    "locker": "Einheit machen, aber Intensität raus: harte Intervalle durch lockeres Training ersetzen oder um ein Drittel kürzen.",
    "pause": "Heute Ruhetag - höchstens 20-30 min sehr locker bewegen.",
}

HRV_STATUS_DE = {
    "BALANCED": "ausgeglichen",
    "UNBALANCED": "unausgeglichen",
    "LOW": "niedrig",
    "POOR": "schlecht",
    "NONE": "noch kein Status",
}


def _worse(a: str, b: str) -> str:
    order = {"normal": 0, "locker": 1, "pause": 2}
    return a if order[a] >= order[b] else b


def evaluate(metrics: dict, rhr_7d_avg=None, hrv_baseline: dict = None, hrv_7d=None) -> dict:
    """metrics: Ausgabe von ha_publish.extract_metrics(). Gibt ein Dict mit
    level, label, advice, reasons (Liste Klartext) zurück."""
    level = "normal"
    reasons = []

    status = (metrics.get("hrv_status") or "").upper() or None
    if status in ("LOW", "POOR"):
        level = _worse(level, "pause")
        reasons.append(f"HRV-Status {HRV_STATUS_DE[status]} (7-Tage-Schnitt deutlich unter deiner Baseline)")
    elif status == "UNBALANCED":
        low = (hrv_baseline or {}).get("balancedLow")
        if isinstance(hrv_7d, (int, float)) and isinstance(low, (int, float)) and hrv_7d < low:
            level = _worse(level, "locker")
            reasons.append("HRV-Status unausgeglichen, 7-Tage-Schnitt unter deiner Baseline")
        else:
            # Über der Baseline: nicht automatisch gut (kann bei viel lockerem Umfang
            # auf Überlastung hindeuten) - nur benennen, nicht herabstufen.
            reasons.append("HRV-Status unausgeglichen (über der Baseline) - im Blick behalten")
    elif status == "BALANCED":
        reasons.append("HRV-Status ausgeglichen")

    score = metrics.get("training_readiness_score")
    if isinstance(score, (int, float)):
        if score < 25:
            level = _worse(level, "pause")
            reasons.append(f"Readiness {score} (Garmin-Stufe „Poor“)")
        elif score < 50:
            level = _worse(level, "locker")
            reasons.append(f"Readiness {score} (Garmin-Stufe „Low“)")

    rhr = metrics.get("resting_hr")
    if isinstance(rhr, (int, float)) and isinstance(rhr_7d_avg, (int, float)) and rhr >= rhr_7d_avg + 5:
        level = _worse(level, "locker")
        reasons.append(f"Ruhepuls {round(rhr)} bpm, {round(rhr - rhr_7d_avg)} über deinem 7-Tage-Schnitt")

    sleep_h = metrics.get("sleep_hours")
    if isinstance(sleep_h, (int, float)):
        if sleep_h < 5:
            level = _worse(level, "pause")
            reasons.append(f"nur {sleep_h} h Schlaf")
        elif sleep_h < 6:
            level = _worse(level, "locker")
            reasons.append(f"kurzer Schlaf ({sleep_h} h)")

    if not reasons:
        reasons.append("keine Erholungswerte auffällig")

    return {
        "level": level,
        "label": LEVEL_LABEL[level],
        "advice": LEVEL_ADVICE[level],
        "reasons": reasons,
    }


def fallback_note(rec: dict, plan_state: dict) -> str:
    """Tagesnotiz ohne KI - wird publiziert, wenn Gemini nicht erreichbar ist."""
    lines = [f"- **{rec['label']}:** {rec['advice']}"]
    lines.append("- Grund: " + "; ".join(rec["reasons"]) + ".")
    today = [i["text"] for i in (plan_state or {}).get("today_fixed") or []]
    if today:
        lines.append("- Heute laut Wochenrahmen: " + ", ".join(today) + ".")
    open_items = (plan_state or {}).get("week_open") or []
    if open_items:
        lines.append("- Diese Woche noch offen: " + ", ".join(open_items) + ".")
    return "\n".join(lines)
