"""Tagesziele - dynamisch nach Trainingstag.

Quellen
- Energie: Grundumsatz nach Mifflin-St Jeor (1990) x Aktivitätsfaktor ohne Sport
  (PAL, Standard 1,4) + Netto-Kalorien der heutigen Garmin-Aktivitäten
  (Aktivitäts-kcal minus Grundumsatz-Anteil derselben Minuten).
- Kohlenhydrate je kg nach Trainingslast: Thomas, Erdman & Burke (2016),
  Position Stand ACSM/AND/DC "Nutrition and Athletic Performance":
  leicht 3-5, moderat (~1 h/Tag) 5-7, hoch (1-3 h/Tag) 6-10, sehr hoch (4-5 h/Tag) 8-12 g/kg.
- Protein 1,8 g/kg (Bereich 1,2-2,0 g/kg laut ACSM 2016; ISSN 2017: 1,4-2,0 g/kg).
- Fett: Rest der Energie, begrenzt auf 20-35 % (ACSM 2016).
- Gesättigte Fettsäuren < 10 % der Energie (DGE), Zucker: Orientierung 10 % der Energie
  (WHO-Wert gilt für *freie* Zucker - hier wird Gesamtzucker inkl. Obst/Milch gezählt,
  daher nur Hinweis, kein Ziel).
- Mikronährstoffe, Ballaststoffe, Wasser: DGE-Referenzwerte für 25 bis < 51 Jahre
  (Stand der Werte siehe dge.de/wissenschaft/referenzwerte).
- Flüssigkeit: DGE-Gesamtwasserzufuhr ~35 ml/kg (inkl. Wasser aus fester Nahrung)
  + ~0,6 l je Stunde Ausdauertraining (Schweißverlust typ. 0,5-2 l/h, ACSM 2016).
"""
import datetime

import nutrients as N

DEFAULT_PROFILE = {"weight_kg": 75.0, "height_cm": 180.0, "age": 35, "sex": "male"}

CARBS_G_PER_KG = {"ruhetag": 3.0, "leicht": 4.0, "moderat": 6.0, "hart": 8.0, "sehr_hart": 10.0}
DAY_LABELS = {"ruhetag": "Ruhetag", "leicht": "Leichter Tag", "moderat": "Moderater Trainingstag",
              "hart": "Harter Trainingstag", "sehr_hart": "Sehr harter Trainingstag"}
# Energie-Defizit/-Überschuss wird an harten Tagen nicht angewendet ("fuel for the work")
GOAL_SCALE = {"ruhetag": 1.0, "leicht": 1.0, "moderat": 0.5, "hart": 0.0, "sehr_hart": 0.0}
GOALS = {"halten": 0, "abnehmen": -15, "aufbauen": 10}

ENDURANCE_TYPES = ("running", "cycling", "swimming", "lap_swimming", "open_water", "trail", "treadmill",
                   "virtual_ride", "indoor_cycling", "rowing", "elliptical", "cross_country", "hiking",
                   "multi_sport", "triathlon", "road_biking", "mountain_biking", "gravel")
STRENGTH_TYPES = ("strength", "fitness_equipment", "hiit", "yoga", "pilates", "training")

MICRO_DGE = {
    "male": {"sodium_mg": 1500, "potassium_mg": 4000, "magnesium_mg": 350, "calcium_mg": 1000,
             "iron_mg": 11, "zinc_mg": 14, "vitd_ug": 20, "b12_ug": 4.0, "vitc_mg": 110, "fiber_g": 30},
    "female": {"sodium_mg": 1500, "potassium_mg": 4000, "magnesium_mg": 300, "calcium_mg": 1000,
               "iron_mg": 16, "zinc_mg": 8, "vitd_ug": 20, "b12_ug": 4.0, "vitc_mg": 95, "fiber_g": 30},
}


def mifflin_st_jeor(weight_kg, height_cm, age, sex) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex != "female" else -161)


def _is_endurance(t: str) -> bool:
    t = (t or "").lower()
    return any(k in t for k in ENDURANCE_TYPES) and "walking" not in t


def classify_day(training: dict):
    """Tagestyp aus heutigen Aktivitäten (Garmin)."""
    acts = (training or {}).get("activities") or []
    endurance = sum(a.get("duration_min") or 0 for a in acts if _is_endurance(a.get("type")))
    total = sum(a.get("duration_min") or 0 for a in acts
                if _is_endurance(a.get("type")) or any(k in (a.get("type") or "") for k in STRENGTH_TYPES))
    load = sum(a.get("training_load") or 0 for a in acts)
    if endurance >= 240:
        t = "sehr_hart"
    elif endurance >= 90 or load >= 150:
        t = "hart"
    elif endurance >= 45 or total >= 75 or load >= 80:
        t = "moderat"
    elif total >= 20:
        t = "leicht"
    else:
        t = "ruhetag"
    return t, {"endurance_min": round(endurance), "training_min": round(total), "training_load": round(load)}


def resolve_profile(settings_profile: dict, training: dict):
    """Einstellungen haben Vorrang, sonst Garmin, sonst Standardwerte."""
    prof, src = {}, {}
    for k, default in DEFAULT_PROFILE.items():
        v = (settings_profile or {}).get(k)
        if v not in (None, ""):
            prof[k], src[k] = v, "einstellung"
        elif (training or {}).get(k) not in (None, ""):
            prof[k], src[k] = training[k], "garmin"
        else:
            prof[k], src[k] = default, "standard"
    prof["weight_kg"] = float(prof["weight_kg"])
    prof["height_cm"] = float(prof["height_cm"])
    prof["age"] = int(prof["age"])
    prof["sex"] = "female" if str(prof["sex"]).lower() in ("female", "f", "weiblich", "w") else "male"
    return prof, src


def compute(settings: dict, training: dict = None, date: str = None) -> dict:
    settings = settings or {}
    date = date or datetime.date.today().isoformat()
    is_today = date == datetime.date.today().isoformat()
    training = training if is_today else None
    prof, prof_src = resolve_profile(settings.get("profile"), training)
    w = prof["weight_kg"]

    day_type, tstats = classify_day(training)
    override = settings.get("day_type_override") or {}
    day_source = "garmin" if training and training.get("activities") is not None else "keine Daten"
    if override.get("date") == date and override.get("type") in CARBS_G_PER_KG:
        day_type, day_source = override["type"], "manuell"

    bmr = mifflin_st_jeor(w, prof["height_cm"], prof["age"], prof["sex"])
    pal = float(settings.get("pal_base") or 1.4)
    base_kcal = bmr * pal
    ex_kcal = 0.0
    for a in (training or {}).get("activities") or []:
        kcal, mins = a.get("kcal") or 0, a.get("duration_min") or 0
        ex_kcal += max(0.0, kcal - bmr / 1440 * mins)
    goal = settings.get("goal") or "halten"
    gp = settings.get("goal_adjust_pct")
    goal_pct = float(gp if gp is not None else GOALS.get(goal, 0))
    goal_pct_applied = goal_pct * GOAL_SCALE[day_type]
    energy = (base_kcal + ex_kcal) * (1 + goal_pct_applied / 100)

    protein = float(settings.get("protein_g_per_kg") or 1.8) * w
    carbs_per_kg = (settings.get("carbs_g_per_kg") or {}).get(day_type, CARBS_G_PER_KG[day_type])
    carbs = float(carbs_per_kg) * w
    rest = energy - 4 * protein - 4 * carbs
    fat_min, fat_max = 0.20 * energy / 9, 0.35 * energy / 9
    fat = min(max(rest / 9, fat_min), fat_max)
    if rest / 9 > fat_max:  # übrige Energie den Kohlenhydraten geben
        carbs += (rest - fat * 9) / 4
    energy_total = 4 * protein + 4 * carbs + 9 * fat

    micro = dict(MICRO_DGE[prof["sex"]])
    water = 35 * w + 10 * tstats["endurance_min"] + 5 * max(0, tstats["training_min"] - tstats["endurance_min"])

    t = {
        "kcal": round(energy_total),
        "protein_g": round(protein),
        "carbs_g": round(carbs),
        "fat_g": round(fat),
        "sugar_g": round(0.10 * energy_total / 4),      # Orientierung (max)
        "satfat_g": round(0.10 * energy_total / 9),     # max
        "fiber_g": micro.pop("fiber_g"),
        "water_ml": round(water / 50) * 50,
    }
    t.update(micro)
    for k, v in (settings.get("target_overrides") or {}).items():
        if k in N.KEYS and v not in (None, ""):
            t[k] = float(v)

    return {
        "date": date,
        "targets": t,
        # "max" = Obergrenze statt Mindestziel
        "kind": {"sugar_g": "max", "satfat_g": "max", "sodium_mg": "ref"},
        "day_type": day_type,
        "day_label": DAY_LABELS[day_type],
        "day_source": day_source,
        "training": tstats,
        "activities": (training or {}).get("activities") or [],
        "plan_text": (training or {}).get("plan_text"),
        "profile": prof,
        "profile_source": prof_src,
        "energy": {"bmr": round(bmr), "pal": pal, "base": round(base_kcal), "exercise": round(ex_kcal),
                   "goal": goal, "goal_pct_applied": round(goal_pct_applied, 1)},
        "carbs_g_per_kg": carbs_per_kg,
    }
