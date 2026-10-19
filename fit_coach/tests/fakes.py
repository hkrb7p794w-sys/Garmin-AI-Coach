"""Synthetische, aber realistische Testdaten: Laufanfängerin, 10 Wochen.

Struktur der Garmin-Antworten nach python-garminconnect 0.3.19 (Feldnamen aus
garminconnect/typed.py, Rekord-typeIds aus api/achievements.py), Yazio nach
juriadams/yazio (API v20, Schemas in src/api/user/*.ts).
"""
import datetime
import json
import random

TODAY = datetime.date(2026, 10, 18)  # Sonntag
START = TODAY - datetime.timedelta(days=70)


def _dt(d, h=18, m=0):
    return f"{d.isoformat()} {h:02d}:{m:02d}:00"


def make_activities(today=TODAY):
    rnd = random.Random(7)
    acts = []
    aid = 20000000000
    d = START
    run_n = 0
    while d <= today:
        wd = d.weekday()
        if wd in (1, 3, 6) and not (d == today):  # Di, Do, So laufen
            run_n += 1
            progress = (d - START).days / 70
            km = round(2.4 + 2.4 * progress + rnd.uniform(-0.3, 0.4) + (1.0 if wd == 6 else 0), 2)
            pace = 515 - 50 * progress + rnd.uniform(-12, 12)  # s/km, 8:35 -> 7:45
            dur = km * pace
            easy = 0.82 if wd != 3 else 0.55
            z = [dur * 0.25, dur * (easy - 0.25), dur * (1 - easy) * 0.7, dur * (1 - easy) * 0.3, 0]
            aid += 1
            acts.append({"activityId": aid, "activityName": "Laufen" if wd != 6 else "Sonntagslauf",
                         "activityType": {"typeKey": "running"}, "startTimeLocal": _dt(d, 18, 10),
                         "distance": km * 1000, "duration": dur + 60, "movingDuration": dur,
                         "averageHR": 152 - 6 * progress + (8 if wd == 3 else 0), "maxHR": 176,
                         "calories": km * 70, "elevationGain": 22,
                         **{f"hrTimeInZone_{i + 1}": z[i] for i in range(5)}})
        if wd == 4 and d.isocalendar()[1] % 2 == 0:  # jede zweite Woche Fr Gym
            aid += 1
            acts.append({"activityId": aid, "activityName": "Krafttraining", "activityType": {"typeKey": "strength_training"},
                         "startTimeLocal": _dt(d, 19, 0), "distance": 0, "duration": 2700, "movingDuration": 2400,
                         "averageHR": 112, "calories": 180})
        if wd == 5:
            aid += 1
            acts.append({"activityId": aid, "activityName": "Spaziergang", "activityType": {"typeKey": "walking"},
                         "startTimeLocal": _dt(d, 11, 0), "distance": 4200, "duration": 3300, "movingDuration": 3200,
                         "averageHR": 98, "calories": 190})
        d += datetime.timedelta(days=1)
    return sorted(acts, key=lambda a: a["startTimeLocal"], reverse=True)


def exercise_sets(activity_id, n_session):
    """exerciseSets-Antwort: Gewichte in Gramm wie bei Garmin-Workouts."""
    base = 12 + 2 * n_session
    sets = []
    def add(cat, name, reps, kg):
        sets.append({"setType": "ACTIVE", "repetitionCount": reps, "weight": kg * 1000,
                     "exercises": [{"category": cat, "name": name, "probability": 99.0}]})
        sets.append({"setType": "REST", "duration": 60})
    for r in (12, 12, 11 + min(1, n_session)):
        add("SQUAT", "GOBLET_SQUAT", r, base)
    for r in (10, 10, 10):
        add("HIP_RAISE", "BARBELL_HIP_THRUST", r, 30 + 5 * n_session)
    for r in (12, 11, 10):
        add("ROW", "DUMBBELL_ROW", r, 8 + n_session)
    for r in (8, 7, 6):
        add("PUSH_UP", "PUSH_UP", r + n_session, 0)
    return {"activityId": activity_id, "exerciseSets": sets}


def weighins(start, end):
    rnd = random.Random(3)
    out = []
    d = START
    while d <= end:
        if d >= start and rnd.random() < 0.72:
            days = (d - START).days
            kg = 78.4 - 0.065 * days + rnd.uniform(-0.6, 0.6)
            ts = int(datetime.datetime.combine(d, datetime.time(7, 10)).timestamp() * 1000)
            out.append({"summaryDate": d.isoformat(), "numOfWeightEntries": 1,
                        "allWeightMetrics": [{"weight": round(kg * 1000), "timestampGMT": ts, "calendarDate": d.isoformat()}],
                        "latestWeight": {"weight": round(kg * 1000), "calendarDate": d.isoformat()}})
        else:
            rnd.random()
        d += datetime.timedelta(days=1)
    return {"dailyWeightSummaries": list(reversed(out)), "totalAverage": {}}


class FakeGarmin:
    def __init__(self, today=TODAY):
        self.today = today
        self.calls = []
        self._acts = make_activities(today)
        self._strength_ids = [a["activityId"] for a in reversed(self._acts) if a["activityType"]["typeKey"] == "strength_training"]

    def login(self, tokenstore=None):
        self.calls.append("login")
        return None, None

    def get_activities(self, start=0, limit=20):
        self.calls.append(f"activities:{limit}")
        return self._acts[start:start + limit]

    def get_user_summary(self, cdate):
        self.calls.append(f"summary:{cdate}")
        d = datetime.date.fromisoformat(cdate)
        rnd = random.Random(d.toordinal())
        return {"calendarDate": cdate, "totalSteps": rnd.randint(5200, 11800), "dailyStepGoal": 8000,
                "activeKilocalories": rnd.randint(250, 650), "totalKilocalories": rnd.randint(1900, 2350),
                "bmrKilocalories": 1450, "moderateIntensityMinutes": rnd.randint(5, 40),
                "vigorousIntensityMinutes": rnd.randint(0, 25), "restingHeartRate": 61, "totalDistanceMeters": 6000}

    def get_weigh_ins(self, startdate, enddate):
        self.calls.append(f"weighins:{startdate}")
        return weighins(datetime.date.fromisoformat(startdate), datetime.date.fromisoformat(enddate))

    def get_weight_goal(self, start, end):
        return {"goalValue": 70000}

    def get_race_predictions(self, startdate=None, enddate=None, _type=None):
        if _type == "daily":
            self.calls.append("pred_hist")
            s = datetime.date.fromisoformat(startdate)
            out = []
            for i in range(0, 91, 3):
                d = s + datetime.timedelta(days=i)
                if d < START + datetime.timedelta(days=20):
                    continue
                out.append({"calendarDate": d.isoformat(), "time5K": 2280 - (d - START).days * 3})
            return out
        return {"calendarDate": self.today.isoformat(), "time5K": 2130, "time10K": 4480,
                "timeHalfMarathon": 10100, "timeMarathon": 21900}

    def connectapi(self, path, **kw):
        self.calls.append(f"connectapi:{path}")
        if "maxmet/daily" in path:
            return [{"generic": {"calendarDate": (START + datetime.timedelta(days=i)).isoformat(),
                                 "vo2MaxPreciseValue": 36.0 + i * 0.03}} for i in range(25, 70, 5)]
        return None

    def get_max_metrics_latest(self, cdate=None):
        return {"generic": {"calendarDate": self.today.isoformat(), "vo2MaxPreciseValue": 38.1}}

    def get_personal_record(self, **kw):
        return [{"typeId": 1, "activityType": "running", "value": 402.0, "prStartTimeLocalFormatted": "2026-10-13 18:20:00"},
                {"typeId": 3, "activityType": "running", "value": 2290.0, "prStartTimeLocalFormatted": "2026-10-11 18:15:00"},
                {"typeId": 7, "activityType": "running", "value": 6100.0, "prStartTimeLocalFormatted": "2026-10-11 18:15:00"},
                {"typeId": 12, "activityType": None, "value": 15000}]

    def get_calendar_week(self, cdate=None, first_day_of_week=1):
        d = datetime.date.fromisoformat(cdate)
        if d <= self.today:
            return {"calendarItems": [{"itemType": "workout", "title": "Locker 25 min (Garmin Coach)",
                                       "date": (self.today + datetime.timedelta(days=2)).isoformat(),
                                       "sportTypeKey": "running", "workoutId": 123}]}
        return {"calendarItems": []}

    def get_scheduled_workouts_by_period(self, start, end):
        return []

    def get_activity_exercise_sets(self, activity_id):
        self.calls.append(f"sets:{activity_id}")
        n = self._strength_ids.index(activity_id) if activity_id in self._strength_ids else 0
        return exercise_sets(activity_id, n)


def yazio_summary(d: datetime.date):
    rnd = random.Random(d.toordinal() * 7)
    if rnd.random() < 0.12:  # ab und zu nichts eingetragen
        return {"activity_energy": 0, "consume_activity_energy": False, "steps": 0, "water_intake": 0,
                "goals": {"energy.energy": 1700, "water": 2000, "activity.step": 8000, "nutrient.protein": 100,
                          "nutrient.fat": 60, "nutrient.carb": 180, "bodyvalue.weight": 70},
                "units": {"unit_energy": "kcal"}, "user": {"start_weight": 78.5, "current_weight": 74.2, "goal": "lose"},
                "meals": {m: {"energy_goal": 400, "nutrients": {"energy.energy": 0, "nutrient.carb": 0, "nutrient.protein": 0, "nutrient.fat": 0}}
                          for m in ("breakfast", "lunch", "dinner", "snack")}}
    def meal(k):
        return {"energy_goal": 400, "nutrients": {"energy.energy": k, "nutrient.carb": k * 0.11,
                                                  "nutrient.protein": k * 0.05, "nutrient.fat": k * 0.035}}
    return {"activity_energy": 320, "consume_activity_energy": False, "steps": 8000, "water_intake": 1500,
            "goals": {"energy.energy": 1700, "water": 2000, "activity.step": 8000, "nutrient.protein": 100,
                      "nutrient.fat": 60, "nutrient.carb": 180, "bodyvalue.weight": 70},
            "units": {"unit_mass": "kg", "unit_energy": "kcal", "unit_serving": "g", "unit_length": "cm"},
            "user": {"start_weight": 78.5, "current_weight": 74.2, "goal": "lose", "sex": "female"},
            "meals": {"breakfast": meal(rnd.randint(320, 480)), "lunch": meal(rnd.randint(480, 650)),
                      "dinner": meal(rnd.randint(450, 650)), "snack": meal(rnd.randint(0, 250))}}


class FakeResponse:
    def __init__(self, status, data=None, text=""):
        self.status_code = status
        self._data = data
        self.text = text or (json.dumps(data) if data is not None else "")

    def json(self):
        return self._data


class FakeYazioHTTP:
    """Ersetzt requests.post/get im Modul yazio."""
    def __init__(self, today=TODAY, password="geheim"):
        self.today = today
        self.password = password
        self.calls = []
        self.weights = {}
        rnd = random.Random(11)
        d = TODAY - datetime.timedelta(days=60)
        while d <= TODAY:
            if rnd.random() < 0.4:
                self.weights[d.isoformat()] = round(78.0 - 0.06 * (d - START).days + rnd.uniform(-0.5, 0.5), 1)
            d += datetime.timedelta(days=1)

    def post(self, url, json=None, data=None, headers=None, timeout=None):
        body = json or data or {}
        if isinstance(body, (bytes, str)):  # JSON als Text (wie die Yazio-App)
            import json as _j
            body = _j.loads(body)
        self.calls.append(("POST", url, body.get("grant_type")))
        if body.get("grant_type") == "password" and body.get("password") != self.password:
            return FakeResponse(400, {"error": "invalid_grant"})
        return FakeResponse(200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 172800, "token_type": "bearer"})

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, (params or {}).get("date")))
        d = datetime.date.fromisoformat(params["date"])
        if url.endswith("/user/widgets/daily-summary"):
            return FakeResponse(200, yazio_summary(d))
        if url.endswith("/user/bodyvalues/weight/last"):
            cands = [k for k in self.weights if k <= d.isoformat()]
            if not cands:
                return FakeResponse(204)
            k = max(cands)
            return FakeResponse(200, {"id": "x", "date": f"{k} 07:30:00", "value": self.weights[k], "source": None,
                                      "gateway": None, "external_id": None})
        return FakeResponse(404)


class FakeMQTT:
    def __init__(self):
        self.msgs = {}

    def publish(self, topic, payload, retain=False):
        self.msgs[topic] = payload
