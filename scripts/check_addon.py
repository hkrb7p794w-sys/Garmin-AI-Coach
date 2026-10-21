import sys, datetime
sys.path.insert(0, sys.argv[1])
import plan, recommendation, ai_coach
cap = {}
def fake(prompt, kind, json_mode=False):
    cap['p'] = prompt
    return '{"punkte":["x"]}', 'test'
ai_coach._generate = fake
race = datetime.date(2027, 8, 29)
def state(day, bike=1, run=1, swim=1, strength=3):
    return plan.build_plan_state(day, race, {'bike_sessions': bike, 'run_sessions': run, 'swim_sessions': swim, 'strength_sessions': strength})
rec = {'level': 'locker', 'label': 'Locker / verkürzt', 'advice': recommendation.LEVEL_ADVICE['locker'], 'reasons': ['HRV-Status unausgeglichen']}
ok = True
def check(c, msg):
    global ok
    print(('OK   ' if c else 'FAIL ') + msg); ok &= bool(c)
note = lambda ps: ai_coach.generate_coaching_note({'phase': 'Grundlage', 'weekly_volumes': {}, 'days_to_race': 315}, rec=rec, plan_state=ps)

sun = datetime.date(2026, 10, 18); ps = state(sun)
check(ps['today_fixed'][0].get('done') is True and 'schon erledigt' in ps['today_fixed'][0]['text'], 'So + Rad 1/1 -> Einheit als erledigt markiert')
check(ps['days_left_in_week'] == 0, 'So -> days_left_in_week 0')
ps2 = state(sun, bike=0)
check(not ps2['today_fixed'][0].get('done') and 'schon erledigt' not in ps2['today_fixed'][0]['text'], 'So + Rad 0/1 -> nicht markiert')
check(state(datetime.date(2026, 10, 17))['today_fixed'][0].get('done') is True, 'Sa + Rad 1/1 -> erledigt')
for d in range(12, 17):
    check(not any(i.get('done') for i in state(datetime.date(2026, 10, d))['today_fixed']), f'{d}.10. (Mo-Fr): nichts als erledigt markiert')
# Almere-Aufbau: Rad-Soll 2 -> eine Einheit unter der Woche reicht am Samstag nicht
sat703 = datetime.date(2027, 6, 19)
check(plan.current_phase(sat703, race) == 'Almere-Aufbau', 'Testdatum liegt im Almere-Aufbau')
check(not any(i.get('done') for i in state(sat703, bike=1)['today_fixed']), 'Almere-Aufbau Sa + Rad 1/2 -> nicht erledigt')
check(any(i.get('done') for i in state(sat703, bike=2)['today_fixed']), 'Almere-Aufbau Sa + Rad 2/2 -> erledigt')

note(ps); pr = cap['p']
check('LETZTE Tag der Woche' in pr, 'Prompt So: letzter Tag benannt')
check('schon erledigt' in pr, 'Prompt So: Zwift als erledigt aufgeführt')
check('nicht noch einmal verordnen' in pr, 'Prompt: Regel „Erledigtes nicht erneut verordnen“')
note(state(datetime.date(2026, 10, 14)))
check('LETZTE Tag' not in cap['p'], 'Prompt Mi: kein Letzter-Tag-Satz')

n = recommendation.fallback_note(rec, ps)
print(n)
check('letzter Tag der Woche' in n and 'entfällt' in n, 'Fallback So gelb: Offenes entfällt')
check('nur noch heute möglich' in recommendation.fallback_note(dict(rec, level='normal'), ps), 'Fallback So grün: nur noch heute möglich')
check('Diese Woche noch offen' in recommendation.fallback_note(rec, state(datetime.date(2026, 10, 14))), 'Fallback Mi: unverändert')
sys.exit(0 if ok else 1)
