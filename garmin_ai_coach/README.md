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

### 0.11.0
- **Neu: eigener Dashboard-Tab "Gym" fuer Kraft-Fortschritt.** Bisher tauchten Kraft-Uebungen nur
  als Attribut eines einzelnen Sensors auf. Der neue Tab im "Garmin Coach"-Dashboard listet die
  Kraft-Einheiten der letzten 7 Tage mit Datum, Uebungsname, Wiederholungen und Gewicht je Satz.
- **Neu: eigener KI-Coaching-Tipp nur fuers Krafttraining** (`generate_gym_coaching_note()` in
  `ai_coach.py`, neuer Sensor `sensor.garmin_ai_coach_garmin_gym_coaching_tipp`, publiziert ueber
  `publish_gym_coaching_note()`). Getrennt vom bisherigen allgemeinen Tages-Coaching-Tipp, damit
  er nicht mit der Ausdauer-/Erholungsperspektive vermischt wird. Bewertet die Muskelgruppen-Balance
  der Woche (Push/Pull/Beine/Rumpf) und gibt eine konkrete Empfehlung fuer die naechste Einheit -
  inkl. Gewichtsangaben je Satz (der bisherige Wochenbericht nutzt weiterhin nur Wiederholungen ohne
  Gewicht). Laeuft unabhaengig vom Hauptsync durch (eigenes try/except), ein Fehler hier bricht den
  Sync nicht ab.
  - **Hinweis:** Saetze ohne erfasstes Zusatzgewicht am Geraet werden im Prompt explizit als
    "Koerpergewicht/ohne Angabe" gekennzeichnet und nicht als Datenfehler behandelt - das kann schlicht
    bedeuten, dass am Geraet kein Gewicht eingetragen wurde.

### 0.10.2
- **Live bestaetigt: exerciseSets-API (0.10.1) liefert echte Uebungsnamen, Gewichte und
  Wiederholungen.** Nach dem ersten Sync mit 0.10.1 zeigte `sensor.garmin_ai_coach_garmin_
  krafttraining_uebungen` fuer eine neue Kraft-Einheit z.B. `Row (SEATED_CABLE_ROW)` 13x/110kg,
  `Curl (CABLE_BICEPS_CURL)` 9x/50kg, `Pull Up (KNEELING_LAT_PULLDOWN)` 8x/52.5kg - realistische
  Werte, die vormals offene Feldnamen-Unsicherheit (`repetitionCount` vs. `reps`, Gramm vs. Kilogramm)
  ist damit ausgeraeumt.
- **Fix: kaputte Cache-Eintraege aus der v0.10.0-Aera wurden nie neu abgerufen.** Der dauerhafte
  Uebungs-Cache (`/data/strength_exercises.json`) ueberspringt Aktivitaeten, die bereits einen
  Eintrag haben - auch wenn dieser Eintrag (aus v0.10.0) leer war oder nur den Codename-Platzhalter
  `"Uebung (Code (None, None, None))"` enthielt. Dadurch blieben 2 von 4 Kraft-Einheiten der ersten
  Woche dauerhaft kaputt, obwohl der Bug selbst (v0.10.1) laengst behoben war. Neue Funktion
  `_is_broken_strength_entry()` erkennt genau diese beiden Faelle (leere Liste, Codename-Platzhalter)
  und verwirft sie beim Laden aus dem Cache, sodass sie beim naechsten Sync automatisch neu ueber die
  exerciseSets-API abgerufen werden - einmalig, danach bleiben sie wie gewohnt gecacht.

### 0.10.1
- **Fix: Kraft-Uebungen jetzt ueber Garmins offizielle exerciseSets-API statt FIT-Parsing.** Die
  v0.10.0-Implementierung (FIT-Datei herunterladen + selbst parsen) war ungetestet gegen echte Daten
  geschrieben worden und lieferte am ersten echten Sync tatsaechlich unbrauchbare Ergebnisse: von 4
  Kraft-Einheiten der Woche zeigten 2 gar keine Uebungen, die anderen 2 nur `"Uebung (Code (None,
  None, None))"` ohne Gewichtsangabe - fitparse konnte die Uebungs-Enums der Original-FIT-Datei
  nicht in Klartext aufloesen. Nachdem `cyberjunky/python-garminconnect` als Projekt-Quelle
  synchronisiert wurde, zeigte der echte Quellcode einen viel direkteren Weg:
  `Garmin.get_activity_exercise_sets(activity_id)` liest Garmins eigenen JSON-Endpunkt
  (`.../activity/{id}/exerciseSets`) - dieselben, von Garmin bereits aufgeloesten Uebungsdaten, die
  auch die Garmin-Connect-App selbst anzeigt. Kein FIT-Download, kein ZIP, kein `fitparse` mehr
  (Abhaengigkeit wieder entfernt). Uebungsnamen werden ueber den mitgelieferten 1527-Uebungen-
  Katalog `garminconnect.exercises` aufgeloest. Datei bleibt aus Kompatibilitaetsgruenden weiter
  `fit_exercises.py`, macht inhaltlich aber keinen FIT-Umweg mehr.
  - **Weiterhin offen:** Die genauen JSON-Feldnamen fuer Wiederholungen/Gewicht innerhalb eines
    Satzes (z.B. `repetitionCount` vs. `reps`) sind nicht durch eine echte Beispielantwort bestaetigt,
    nur die Uebungs-Zuordnung selbst (`category`/`name`) ist durch den Quellcode-Docstring direkt
    belegt. Der Code probiert mehrere plausible Feldnamen und bleibt bei Fehlern defensiv (leere
    Liste statt Sync-Abbruch). **Bitte nach dem naechsten Sync erneut die Attribute von
    `sensor.garmin_ai_coach_garmin_krafttraining_uebungen`** (Entwicklerwerkzeuge -> Zustaende)
    pruefen.
  - Das Dashboard wurde weiterhin bewusst NICHT um diese Daten erweitert, bis Wiederholungen/Gewicht
    an echten Daten bestaetigt sind.

### 0.10.0
- **Neu (Best-Effort): einzelne Kraft-Uebungen je Einheit** ueber FIT-Datei-Parsing - siehe 0.10.1,
  dieser Ansatz wurde direkt im ersten echten Test durch die exerciseSets-API ersetzt.

### 0.9.0
- **Coaching-Notiz und Wochenreport jetzt als Stichpunkte:** Beide Gemini-Prompts fordern jetzt
  explizit Markdown-Bulletpoints statt Fliesstext an (2-3 bzw. 3-4 kurze Punkte, je 1-2 Saetze,
  keine Wiederholung der reinen Zahlen aus der Tabelle) - auf Wunsch besser scanbar als ein
  Textabsatz.
- **Bugfix/Klarstellung Wochenreport-Zeitraum:** Die Tabelle im Dashboard nannte die beiden
  7-Tage-Fenster "Diese Woche"/"Vorwoche". Da der Report montags automatisch ueber die gerade
  abgeschlossene Woche laeuft (und `/weekly` jederzeit manuell ausloesbar ist), war das
  irrefuehrend - die als "Diese Woche" bezeichneten Einheiten waren faktisch die der zuletzt
  abgeschlossenen Woche. Fix: `build_weekly_summary()` berechnet jetzt konkrete Datumsbereiche
  (`period_label`/`period_prev_label`, z.B. "01.09.–07.09."), Tabelle und KI-Prompt nennen jetzt
  das echte Datum statt einer relativen Wochenbezeichnung.
- **Dashboard-Feinschliff:** Die kleinen bubble-card-Kacheln waren auf schmalen Bildschirmen
  (4 pro Zeile) so eng, dass Name und Wert abgeschnitten wurden. Auf 2 pro Zeile verbreitert plus
  Text darf jetzt umbrechen statt abgeschnitten zu werden. Training Readiness, Body Battery und
  Schritte heute laufen jetzt zusaetzlich als Gauge-Karten (0-100 % bzw. 0-12.000 Schritte mit
  Farbzonen, Schritte-Ziel 8.000 gruen markiert) - fest begrenzte Skala, damit ein Wert visuell nie
  wie "ueber 100 %" aussehen kann (der reine History-Graph hatte hier automatisch eine y-Achse bis
  160 gewaehlt, obwohl der Messwert selbst korrekt bei 97 % lag - eine reine Grafikskalierung, kein
  Datenfehler).

### 0.8.0
- **Neuer Wochenreport** (`sensor.…_garmin_wochenreport`): KI-Rückblick auf die vergangene Woche mit
  Soll/Ist-Vergleich der Wochenstruktur, Vorwochenvergleich je Disziplin und Erholungstrends. Läuft
  automatisch montags, jederzeit manuell über `/weekly` auslösbar (nutzt die zuletzt gesyncten
  Daten, löst also keine zusätzliche Garmin-Abfrage aus). Alle Kennzahlen hängen als Attribute am
  Sensor statt als eigene Entities.
- **Athletenprofil im Prompt:** Coach kennt jetzt die reale Wochenstruktur (Di/Do Bürotage mit
  Schwimmen + Beinen, Push/Pull im Home-Gym an Homeoffice-Tagen, 1x Zone-2-Lauf, 1x Intervall/
  Schwelle, Wochenende optional Longrun oder Zwift) sowie die Zielzeit (neue Option `race_goal`).
  Er darf explizit **nicht** mehr Zeit fordern, sondern nur innerhalb dieses Rahmens umschichten,
  und berücksichtigt den heutigen Wochentag.
- **Einheiten-Zähler + Krafttraining:** Aktivitäten werden jetzt auch als Anzahl Einheiten je
  Disziplin erfasst (der Plan ist in Einheiten/Woche gedacht), Krafttraining wird mitgezählt.
- **Rollierende Tages-Historie** (`/data/history.json`, 60 Tage) für Wochentrends bei Ruhepuls, HRV,
  Schlaf und Readiness – ohne zusätzliche Garmin-Requests. Der Report weist offen darauf hin,
  solange noch zu wenige Tage für belastbare Trends vorliegen.
- **Bugfix VO2max:** `get_max_metrics(today)` fragt nur den heutigen Tag ab, Garmin berechnet VO2max
  aber nur nach qualifizierenden Einheiten – der Tageseintrag ist meist leer, der Sensor blieb
  deshalb dauerhaft „unbekannt". Jetzt wird ein 14-Tage-Fenster in **einem** Request abgefragt und
  der jüngste Eintrag mit Wert genommen.
- **Bugfix Endurance Score:** Es wurde die Zeitraum-Variante abgefragt (liefert `avg`/`max`/
  `groupMap`), aber nach `overallScore` gesucht – das Feld gibt es dort gar nicht, der Sensor konnte
  nie einen Wert bekommen. Jetzt Einzeltag-Abfrage plus Unterstützung beider Antwortformen.

### 0.7.3
- **Timeout erhöht (30s → 120s, per `GEMINI_TIMEOUT` änderbar):** `gemini-3.6-flash` brauchte für
  den Coaching-Prompt länger als 30 Sekunden, der Aufruf lief in `Read timed out`.
- **Messwerte sind von der KI entkoppelt:** `do_sync()` publiziert jetzt erst alle Garmin-Sensoren
  (`publish_state`) und den Sync-Status, und fragt *danach* Gemini; die Notiz geht separat über die
  neue Funktion `publish_coaching_note()` raus. Vorher hingen alle Sensorwerte an der KI-Antwort -
  ein langsamer oder fehlschlagender LLM-Aufruf hat den kompletten Sync blockiert bzw. verzögert.

### 0.7.2
- **Modell gewechselt:** `gemini-2.5-flash` liefert für neu angelegte Accounts nur noch HTTP 404
  ("This model ... is no longer available to new users. Please update your code to use
  models/gemini-3.6-flash"). Standardmodell ist daher jetzt `gemini-3.6-flash`.
- **Selbstheilung bei künftigen Modell-Abkündigungen:** Bei einem 404 liest das Add-on das von
  Google in der Fehlermeldung genannte Nachfolgemodell aus und wiederholt den Aufruf automatisch
  damit (`_model_from_404`). Ein Modellwechsel bei Google erzwingt damit kein manuelles Update
  mehr; der Wechsel wird im Log protokolliert. Überschreibbar per `GEMINI_MODEL`-Env-Var.
- Hinweis: `generateContent` funktioniert weiterhin; Google empfiehlt in der Meldung zusätzlich die
  neuere "Interactions API" - ein möglicher späterer Umbau, aktuell nicht nötig.

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
