"""Energie- und Trainingsdaten des Tages für die Ernährungs-App (0.29.0).

Veröffentlicht als sensor.garmin_ai_coach_garmin_energie_heute:
- Zustand: aktive kcal heute (Garmin-Tageszusammenfassung)
- Attribute: date, weight_kg, height_cm, age, sex, bmr_kcal, active_kcal, total_kcal,
  activities [{type, name, start, duration_min, kcal, training_load}],
  training_minutes, endurance_minutes, training_load

Garmin-Abrufe: get_user_summary(heute) bei jedem Sync (1 Request); das Profil
(Gewicht, Größe, Geburtsdatum, Geschlecht) höchstens einmal am Tag
(get_user_profile, zwischengespeichert in /data/profile_cache.json).
Die Aktivitäten kommen aus der ohnehin geladenen Aktivitätsliste.
"""
import datetime
import json
import os

ENDURANCE_KEYS = ("run", "cycl", "bik", "swim", "ride", "row", "elliptical", "ski", "hik", "triathlon", "multi_sport")


def _profile(client, data_dir: str, today: datetime.date) -> dict:
    path = os.path.join(data_dir, "profile_cache.json")
    try:
        with open(path) as f:
            cached = json.load(f)
        if cached.get("fetched") == today.isoformat():
            return cached
    except (OSError, ValueError):
        cached = {}
    try:
        ud = (client.get_user_profile() or {}).get("userData") or {}
    except Exception as e:
        print(f"[energy] Profil nicht abrufbar: {e}")
        return cached
    age = None
    try:
        bd = datetime.date.fromisoformat(str(ud.get("birthDate"))[:10])
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except (TypeError, ValueError):
        pass
    weight = ud.get("weight")
    prof = {
        "fetched": today.isoformat(),
        # Garmin liefert das Gewicht in Gramm
        "weight_kg": round(weight / 1000, 1) if isinstance(weight, (int, float)) and weight > 1000 else weight,
        "height_cm": ud.get("height"),
        "age": age,
        "sex": "female" if str(ud.get("gender", "")).upper() == "FEMALE" else ("male" if ud.get("gender") else None),
    }
    try:
        with open(path, "w") as f:
            json.dump(prof, f)
    except OSError:
        pass
    return prof


def today_activities(activities, today: datetime.date) -> list:
    out = []
    for a in activities or []:
        start = str(a.get("startTimeLocal") or "")
        if start[:10] != today.isoformat():
            continue
        type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
        out.append({
            "type": type_key,
            "name": a.get("activityName"),
            "start": start[11:16],
            "duration_min": round((a.get("duration") or 0) / 60, 1),
            "kcal": round(a.get("calories") or 0),
            "training_load": round(a.get("activityTrainingLoad") or 0, 1),
        })
    return out


def build(client, activities, today: datetime.date, data_dir: str) -> dict:
    prof = _profile(client, data_dir, today)
    summary = {}
    try:
        summary = client.get_user_summary(today.isoformat()) or {}
    except Exception as e:
        print(f"[energy] Tageszusammenfassung nicht abrufbar: {e}")
    acts = today_activities(activities, today)
    endurance = sum(a["duration_min"] for a in acts
                    if any(k in a["type"] for k in ENDURANCE_KEYS) and "walk" not in a["type"])
    return {
        "date": today.isoformat(),
        "weight_kg": prof.get("weight_kg"),
        "height_cm": prof.get("height_cm"),
        "age": prof.get("age"),
        "sex": prof.get("sex"),
        "bmr_kcal": summary.get("bmrKilocalories"),
        "active_kcal": summary.get("activeKilocalories"),
        "total_kcal": summary.get("totalKilocalories"),
        "activities": acts,
        "training_minutes": round(sum(a["duration_min"] for a in acts)),
        "endurance_minutes": round(endurance),
        "training_load": round(sum(a["training_load"] for a in acts)),
    }
