# Garmin AI Coach

Home Assistant Add-on: synct Garmin-Trainings-/Recovery-Daten per MQTT nach Home Assistant und
erzeugt eine KI-Coaching-Notiz (Anthropic Claude) zur Vorbereitung auf einen Ironman 70.3.

## Changelog

### 0.6.1
- **Kritischer Bugfix:** `services: - mqtt:want` in `config.yaml` injiziert die MQTT-Zugangsdaten
  entgegen der Annahme NICHT automatisch als Umgebungsvariablen - das deklariert nur die
  Abhängigkeit. `run.sh` hat `MQTT_USERNAME`/`MQTT_PASSWORD` nie gesetzt bekommen, wodurch sich
  der Client anonym bei core-mosquitto verbunden hat und dort mit "not authorised" abgelehnt
  wurde. Jeder Sync-Lauf lief technisch fehlerfrei durch, aber praktisch kein einziger Sensor-Wert
  kam in Home Assistant an (die drei alten Sensoren zeigten nur noch eingefrorene, monatealte
  MQTT-Retained-Werte). Fix: `run.sh` fragt die Zugangsdaten jetzt explizit über
  `bashio::services mqtt "host"/"port"/"username"/"password"` ab, wie von den Home-Assistant-
  Entwickler-Docs für App-Kommunikation vorgesehen.

### 0.5.0
- **Kritischer Bugfix:** `/sync` hatte ein `return redirect(".")` vor den Zeilen, die den
  MQTT-Publish und die KI-Coaching-Notiz auslösen — dieser Code wurde nie erreicht, es kam nie
  etwas in Home Assistant an. Sync-Logik in `do_sync()` extrahiert, Reihenfolge korrigiert.
- `sync_hour`-Option ist jetzt tatsächlich verdrahtet (Hintergrund-Scheduler-Thread für einen
  echten täglichen Auto-Sync statt nur beim manuellen Klick).
- Neue Sensoren: `training_readiness` (Score + Level), `training_status`, `hrv_status` /
  `hrv_last_night_avg`, `body_battery`, `sleep_score`, `vo2max`, Wochenvolumen je Disziplin
  (`weekly_swim_km`/`weekly_bike_km`/`weekly_run_km`), `days_to_race`, `training_phase`,
  `last_sync`, `sync_status`.
- Einzelne fehlgeschlagene Garmin-Abfragen (z.B. HRV ohne kompatible Uhr) brechen nicht mehr den
  gesamten Sync ab, sondern werden übersprungen und geloggt.
- `last_sync`/`sync_status` werden jetzt auch bei einem fehlgeschlagenen Sync publiziert, damit
  das im Dashboard sichtbar ist statt dass Sensoren einfach einfrieren.
- 15-Minuten-Mindestabstand zwischen Sync-Versuchen (auch beim manuellen Button) als Schutz vor
  erneuter Garmin-Kontosperre. Override via `/sync?force=1`.
- MQTT-Verbindung robuster (`connect_async` + Reconnect-Delay), falls core-mosquitto beim Start
  noch nicht bereit ist.
- Rohe Exception-Texte landen nicht mehr in der Dashboard-Coaching-Notiz, sondern nur noch im
  Add-on-Log.
- Neue Option `race_date` (Default `2027-08-29`) für Renn-Countdown und periodisierungsbewussten
  KI-Prompt.

### 0.1.0
- Initiales Add-on-Grundgerüst.
