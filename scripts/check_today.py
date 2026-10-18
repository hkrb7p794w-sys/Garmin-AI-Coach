"""Konsistenz-Test für coach_today()/coach_today_text() über alle Wochentage.

Spielt jeden Wochentag x Tagesampel (normal/locker/pause) x Zustand (nichts erledigt / alles Feste erledigt)
x Laufzähler durch und prüft Regeln, die für die Anzeige gelten müssen. Home-Assistant-Funktionen sind
minimal nachgebaut (now, states, state_attr, strptime, timedelta, from_json/to_json, Test 'search').
Aufruf: python3 -I check_today.py <pfad zu custom_templates>
"""
import datetime
import itertools
import json
import re
import sys

import jinja2

TPL_DIR = sys.argv[1]
MON = datetime.date(2026, 10, 12)   # Woche 1 des Saisonplans (Grundlage), laufende Woche in den Tests


class State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class States:
    """states('x') und states.sensor.x wie in Home Assistant."""

    def __init__(self, data):
        self._d = data

    def __call__(self, entity, *a):
        s = self._d.get(entity)
        return s.state if s else 'unknown'

    def __getattr__(self, domain):
        d = self._d

        class Dom:
            def __getattr__(self_, name):
                return d.get(f'{domain}.{name}')
        return Dom()


def make_env(today, lvl, done, gym_dates, zones_run):
    reasons = {'normal': ['keine Erholungswerte auffällig'], 'locker': ['HRV-Status unausgeglichen'], 'pause': ['nur 4,5 h Schlaf']}
    advice = {'normal': 'Geplante Einheit wie vorgesehen durchziehen.',
              'locker': 'Einheit machen, aber Intensität raus: harte Intervalle durch lockeres Training ersetzen oder um ein Drittel kürzen.',
              'pause': 'Heute Ruhetag - höchstens 20-30 min sehr locker bewegen.'}
    targets = [{'key': k, 'done': done.get(k, 0), 'min': m, 'max': m} for k, m in
               (('swim', 1), ('run', 2), ('strength', 4), ('bike', 1))]
    data = {
        'sensor.garmin_ai_coach_garmin_tagesempfehlung': State(lvl, {'level': lvl, 'label': lvl, 'advice': advice[lvl], 'reasons': reasons[lvl]}),
        'sensor.garmin_ai_coach_garmin_plan': State('x', {'targets': targets}),
        'sensor.garmin_ai_coach_garmin_krafttraining_uebungen': State('x', {'sessions': [{'date': d} for d in gym_dates]}),
        'sensor.garmin_ai_coach_garmin_herzfrequenzzonen': State('x', {'distribution': {'per_week': (
            [{'week_start': MON.isoformat(), 'run': zones_run}] if zones_run else [])}}),
    }
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TPL_DIR), undefined=jinja2.Undefined)
    st = States(data)
    env.globals.update(
        now=lambda: datetime.datetime.combine(today, datetime.time(14, 0)),
        states=st, timedelta=datetime.timedelta,
        state_attr=lambda e, a: (data.get(e).attributes.get(a) if data.get(e) else None),
        strptime=lambda s, f: datetime.datetime.strptime(s, f),
    )
    env.filters['from_json'] = json.loads
    env.filters['to_json'] = lambda v: json.dumps(v, ensure_ascii=False)
    env.tests['search'] = lambda v, pat: re.search(pat, str(v)) is not None
    return env, st


def render(env, st, macro, today):
    # Importe teilen sich den Kontext nicht: states/now sind Globals, daher reicht ein einfacher Aufruf.
    tpl = env.from_string("{% from 'coach_app.jinja' import " + macro + " %}{{ " + macro + "() }}")
    return tpl.render()


fails = []
cases = 0
for off, lvl, all_done, run_done, zr_name in itertools.product(
        range(7), ['normal', 'locker', 'pause'], [False, True], [0, 1, 2],
        ['easy', 'hard', None]):
    today = MON + datetime.timedelta(days=off)
    zones = {'easy': {'easy_pct': 97, 'mid_pct': 3, 'hard_pct': 0},
             'hard': {'easy_pct': 40, 'mid_pct': 40, 'hard_pct': 20}, None: None}[zr_name]
    done = {'run': run_done, 'bike': 1 if (all_done and off >= 5) else 0, 'swim': 1 if (all_done and off >= 2) else 0,
            'strength': 3 if all_done else 0}
    gym = [today.isoformat()] if (all_done and off in (0, 2, 4)) else []
    env, st = make_env(today, lvl, done, gym, zones)
    try:
        t = json.loads(render(env, st, 'coach_today', today))
        txt = render(env, st, 'coach_today_text', today)
    except Exception as e:  # pragma: no cover
        fails.append((off, lvl, all_done, run_done, zr_name, f'Template-Fehler: {e!r}'))
        continue
    cases += 1
    ctx = (['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][off], lvl, 'erledigt' if all_done else 'offen', f'Läufe={run_done}', f'HF={zr_name}')
    last_day = off == 6
    chips = [x['a'] for x in t['items'] + t['open'] if x.get('a')]

    # R1: am letzten Tag nie „nicht heute“ (es gibt kein anderes Mal mehr)
    if last_day and any(c == 'nicht heute' for c in chips) or (last_day and 'nicht heute' in txt):
        fails.append((*ctx, 'R1: „nicht heute“ am Sonntag'))
    # R2: „nicht heute“ nur, wenn danach noch Tage kommen
    if t.get('dl', 6 - off) == 0 and 'nicht heute' in json.dumps(t, ensure_ascii=False):
        fails.append((*ctx, 'R2: „nicht heute“ trotz dl=0'))
    # R3: Offene Einheiten tragen nie das Chip der Tageseinheiten und umgekehrt (kein „⅓ weniger Sätze“ unter „offen“)
    if any(x.get('a') == '⅓ weniger Sätze' for x in t['open']):
        fails.append((*ctx, 'R3: Satz-Hinweis bei offener Einheit'))
    # R4: Bei normaler Ampel kein Hinweis, keine skip-Liste
    if lvl == 'normal' and (chips or t.get('skip')):
        fails.append((*ctx, 'R4: Hinweis bei grüner Ampel'))
    # R5: skip-Liste nur am letzten Tag
    if t.get('skip') and not last_day:
        fails.append((*ctx, 'R5: Ausfall vor dem letzten Tag'))
    # R6: Kein Eintrag in open UND skip
    if {x['t'] for x in t['open']} & {x['t'] for x in t.get('skip', [])}:
        fails.append((*ctx, 'R6: Einheit doppelt gelistet'))
    # R7: erledigte Einheit nie mit Hinweis
    if any(x.get('ok') and x.get('a') for x in t['items']):
        fails.append((*ctx, 'R7: Hinweis bei erledigter Einheit'))
    # R8: Ratschlag nennt keine Nachholung, wenn alles Feste erledigt ist
    fixed = [x for x in t['items'] if x['s'] != 'rest']
    if fixed and all(x['ok'] for x in fixed) and lvl in ('locker', 'pause') and 'Intervalle' in t['advice']:
        fails.append((*ctx, 'R8: Ratschlag ignoriert erledigte Einheit'))
    # R9: Push-Text widerspricht Karte nicht
    for x in t['items'] + t['open']:
        if x.get('a') and x['a'] not in txt:
            fails.append((*ctx, f'R9: Chip „{x["a"]}“ fehlt im Push-Text'))
    for x in t.get('skip', []):
        if 'Entfällt diese Woche' not in txt:
            fails.append((*ctx, 'R9: Ausfall fehlt im Push-Text'))
    if last_day and 'frischen Tag' in txt:
        fails.append((*ctx, 'R10: Push verweist am Sonntag auf frischen Tag'))
    # R11: „Noch 1 Lauf“ nur, wenn die HF-Verteilung nichts entscheidet
    if any(x['t'] == 'Noch 1 Lauf' for x in t['open']) and run_done == 1 and zr_name in ('easy', 'hard'):
        fails.append((*ctx, 'R11: Lauf nicht aufgelöst trotz HF-Daten'))
    # R12: Sonntag: nach erledigtem Zwift darf nichts mit „Sa oder So“ als offen erscheinen
    if last_day and any(x['s'] == 'bike' and x['t'] == 'Zwift (Sa oder So)' and x['ok'] for x in t['items']):
        fails.append((*ctx, 'R12: Sonntag zeigt erledigtes Zwift als „Sa oder So“'))

print(f'{cases} Fälle geprüft, {len(fails)} Verstöße')
seen = set()
for f in fails:
    key = f[-1] if len(f) > 1 else f
    if key in seen:
        continue
    seen.add(key)
    print('  ', f)
sys.exit(1 if fails else 0)
