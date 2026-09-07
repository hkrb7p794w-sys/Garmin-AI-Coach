# Garmin AI Coach

Home Assistant Add-on: synct Garmin-Trainings-/Recovery-Daten per MQTT nach Home Assistant und
erzeugt eine KI-Coaching-Notiz (Google Gemini, kostenloses Kontingent) zur Vorbereitung auf einen
Ironman 70.3.

## Coaching-Notiz einrichten (kostenlos)

Die KI-Coaching-Notiz nutzt die Gemini API von Google, die ein kostenloses Nutzungskontingent ohne
Kreditkarte bietet (Stand 09/2026, siehe https://ai.google.dev/gemini-api/docs/pricing):

1. Auf https://aistudio.google.com mit einem Google-Konto einloggen.
2. Links auf "Get API key" -> "Create API key" klicken, Key kopieren.
3. In Home Assistant unter Einstellungen -> Add-ons -> Garmin AI Coach -> Konfiguration das Feld
   `gemini_api_key` mit diesem Key befüllen und speichern.
4. Add-on neu starten bzw. bis zum nächsten automatischen Sync warten.

Ohne gesetzten Key läuft der Sync trotzdem normal durch (alle Garmin-Sensoren werden weiterhin
aktualisiert), nur die Coaching-Notiz zeigt dann einen Platzhaltertext.

## Changelog

### 0.7.1
- **Bugfix Coaching-Notiz blieb leer:** `gemini-2.5-flash` ist ein "Thinking"-Modell - die internen
  Denk-Tokens zählen gegen `maxOutputTokens`. Mit dem bisherigen Budget von 300 verbrauchte das
  Modell alles fürs Denken und lieferte einen Kandidaten ganz ohne Text-Part zurück
  (`finishReason: MAX_TOKENS`), ohne HTTP-Fehler. Die Funktion gab dann einen leeren String
  zurück, `publish_state()` überspringt leere Notizen - im Dashboard blieb kommentarlos die alte
  Notiz stehen. Budget auf 2000 erhöht.
- Leerer Antworttext und HTTP-Fehler werfen jetzt eine aussagekräftige Exception (inkl.
  `finishReason`, `usageMetadata` bzw. Antwortkörper), statt still zu scheitern.
- `PYTHONUNBUFFERED=1` in `run.sh`: Python pufferte seine `print()`-Diagnosen blockweise, weil
  stdout kein TTY ist - `[sync]`/`[ai_coach]`-Zeilen tauchten im Add-on-Log gar nicht auf, während
  die Flask-Zugriffslogs sofort sichtbar waren. Das hat die Fehlersuche unnötig erschwert.

### 0.7.0
- **KI-Anbieter von Anthropic Claude auf Google Gemini umgestellt**, um eine kostenlose Nutzung zu
  ermöglichen (Gemini API bietet ein kostenloses Kontingent ohne Kreditkarte, Anthropic-API-Nutzung
  ist dagegen kostenpflichtig). Neue Add-on-Option `gemini_api_key` ersetzt `anthropic_api_key`.
  Modell: `gemini-2.5-flash` (per `GEMINI_MODEL`-Env-Var änderbar). Funktional identischer
  periodisierungsbewusster Coaching-Prompt, nur der API-Aufruf und die Antwort-Verarbeitung wurden
  auf das Gemini-`generateContent`-Format umgestellt.

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
