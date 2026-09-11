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

### 0.15.0
- **Neu: freier Gemini-Chat im Dashboard** (neuer Tab "Chat"). Auslöser: Alex wollte gezielte
  Fragen über die API direkt an Gemini stellen können, statt nur die automatisch generierten
  Coaching-Texte zu lesen. Per `AskUserQuestion` auf drei Punkte eingegrenzt (alle mit der jeweils
  empfohlenen Option beantwortet): (1) **Technik:** MQTT-basiert (Textfeld + Verlauf per Sensor)
  statt einer eigenen iframe-Weboberfläche (Ingress-Session-Risiko, siehe 0.13.0) oder eines
  nativen HA-Assist-Conversation-Agents (eigene Integration nötig, kein reiner Add-on-Task). (2)
  **Kontext:** Gemini bekommt bei jeder Frage automatisch den aktuellen Trainingskontext
  (Readiness, VO2max, Trainingsphase, Wochenvolumen, HRV, Schlaf etc.) mitgegeben, damit z.B. "Wie
  war meine Woche?" ohne weitere Erklärung funktioniert. (3) **Verlauf:** die letzten Frage-Antwort-
  Paare bleiben im Dashboard sichtbar (nicht nur die letzte Antwort).
  - **Neues Modul `chat.py`:** verwaltet den Chatverlauf in `/data/chat_history.json` (analog zu
    `suggestions.py`), begrenzt auf die letzten 30 Austausche. `context_for_prompt()` baut einen
    Gesprächsverlauf-Block der letzten 5 Austausche für Anschlussfragen.
  - **`ai_coach.py`:** neue Funktion `generate_chat_answer(question, data, history, chat_context)`
    - anders als die übrigen `generate_*`-Funktionen ohne erzwungenes Stichpunkt-Format (eine
    Chat-Antwort soll sich an der Frage orientieren, nicht an einer Coaching-Notiz-Schablone).
    Nennt Gemini ausdrücklich, dass keine Sensordaten zu Pace/Watt/Körpergewicht und kein
    Lesezugriff auf die manuell gepflegten Zielzeit-Benchmark-Felder vorliegen, damit dort nichts
    erfunden wird.
  - **`ha_publish.py`:** neue MQTT-`text`-Entity `text.garmin_ai_coach_garmin_chat_frage` (Frage
    eingeben, `optimistic: true`, `max: 255` - das von Home Assistant fest vorgegebene Maximum für
    MQTT-Text-Entities) sowie neuer Sensor `sensor.garmin_ai_coach_garmin_chat_verlauf` (Attribut
    `messages`: Liste der gespeicherten Frage-Antwort-Paare).
  - **`app.py`:** neuer Handler `_handle_chat_question()` (per MQTT-Callback ausgelöst, läuft wie
    der Sync-Button-Handler in einem eigenen Thread, damit ein länger dauernder Gemini-Aufruf den
    MQTT-Netzwerk-Thread nicht blockiert). Nutzt die zuletzt gespeicherten Sync-Daten statt einen
    neuen Garmin-Sync auszulösen (eine Textfrage soll nicht zusätzlich das Garmin-Rate-Limit
    belasten). Ein Gemini-Fehler liefert eine ehrliche Fallback-Antwort statt die Frage stillschweigend
    verschwinden zu lassen.
  - **`Dockerfile`:** `COPY chat.py /chat.py` ergänzt - direkt beim Anlegen des neuen Moduls, um
    genau den Fehler aus 0.14.1 zu vermeiden (dort fehlte die analoge `COPY`-Zeile für
    `suggestions.py`, das Add-on startete deshalb mit `ModuleNotFoundError` nicht mehr).
  - **Neuer Dashboard-Tab "Chat":** Erklärung, Eingabefeld (die neue Text-Entity) sowie eine
    Markdown-Card, die den Verlauf aus den Sensor-Attributen rendert (neueste Frage zuerst).
  - MQTT-Text-Discovery-Schema vorab gegen die offizielle Home-Assistant-Dokumentation
    (https://www.home-assistant.io/integrations/text.mqtt/) geprüft (u.a. das 255-Zeichen-Limit).
  - Alle vier geänderten/neuen Python-Dateien (`chat.py`, `ai_coach.py`, `ha_publish.py`, `app.py`)
    mit `py_compile` verifiziert sowie mit 42 synthetischen Tests gegen echte Modul-Instanzen
    (Stub-Modul für `paho`, da in der Cloud-Sandbox nicht installierbar): Verlauf-Verwaltung
    (Speichern, Begrenzung auf 30 Einträge, Kontext-Block), `generate_chat_answer` (Erfolgsfall,
    leere Frage, fehlender API-Key, 404-Modellwechsel-Fallback, Gesprächskontext im Prompt),
    Discovery-Payloads (Text-Entity, Sensor), `publish_chat_history`, MQTT-Routing sowie ein voller
    End-to-End-Durchlauf über `app._handle_chat_question()` inkl. Fehlerfall und
    Anschlussfrage-Kontext - alle Fälle bestanden.

### 0.14.1
- **Hotfix: Add-on startete nicht mehr (ModuleNotFoundError: No module named 'suggestions').**
  Das in 0.14.0 neu eingefuehrte Modul `suggestions.py` wurde im `Dockerfile` nicht per `COPY`
  in das Container-Image aufgenommen (die anderen vier Python-Dateien schon) - dadurch fehlte die
  Datei im gebauten Image, obwohl sie im Repo lag und `app.py` sie importiert. Fix: `COPY
  suggestions.py /suggestions.py` im Dockerfile ergaenzt. Reiner Build-Fix, keine Logik-Aenderung
  gegenueber 0.14.0.

### 0.14.0
- **Neu: KI-Trainingsplan-Vorschlaege lassen sich jetzt einzeln annehmen oder ablehnen** (neuer
  Dashboard-Tab "Vorschlaege"). Auslöser: Alex wollte einige der Gym-Plan-Vorschlaege nicht
  übernehmen, ohne dass die KI sie ihm wiederholt erneut vorschlägt. Gilt bewusst nur für die
  konkreten Trainingsplan-Einzelvorschläge (Gym-Kritik + der ausgelöste Trainingsplan-Kommentar),
  nicht für die übrigen KI-Texte (Tages-Tipp, Wochenreport, Gym-Coaching-Tipp), die eher
  Status-Kommentare als einzeln bewertbare Empfehlungen sind.
  - **Annehmen** merkt den Vorschlag als angenommen und gibt ihn künftigen
    Trainingsplan-Kommentar-Prompts als Kontext mit ("bereits umgesetzt/akzeptiert, nicht erneut
    vorschlagen, darauf aufbauen"). Ändert NICHT automatisch die Plantexte im Dashboard - die
    pflegt Alex weiterhin selbst.
  - **Ablehnen** merkt den Vorschlag als abgelehnt; er wird der KI-Kontext künftig als "nicht
    erneut vorschlagen" mitgegeben und taucht im Dashboard unter "Abgelehnt" auf. Von dort lässt er
    sich jederzeit wieder auswählen und per erneutem "Annehmen" reaktivieren.
  - **Neues Modul `suggestions.py`:** verwaltet den Zustand (`pending`/`accepted`/`rejected`) je
    Vorschlag in `/data/suggestions_state.json`, stabil über die Vorschlags-`id`.
  - **`ai_coach.py`:** `TRAININGSPLAN_GYM_KRITIK` ist jetzt eine Liste von vier Einzelvorschlägen
    (stabile `id`/`title`/`text`) statt eines Textblocks; `_render_gym_kritik()` blendet abgelehnte
    Punkte im Prompt aus und markiert angenommene. `generate_trainingsplan_kommentar()` lässt
    Gemini zusätzlich ein JSON-Objekt mit strukturierten Einzelvorschlägen liefern (0-3 pro
    Kommentar) statt nur Freitext; `_parse_trainingsplan_response()` parst das defensiv (Fallback
    auf Rohtext ohne Einzelvorschläge, falls Gemini sich nicht ans Format hält - z.B. bei einem
    umschließenden Markdown-Codeblock).
  - **`ha_publish.py`:** neue MQTT-Entities "Garmin Vorschlag Auswahl" (Dropdown aller aktuellen
    Vorschläge, Status als Emoji im Label), "Garmin Vorschlag Annehmen"/"...Ablehnen" (wirken auf
    den ausgewählten Vorschlag) sowie der neue Sensor `sensor.garmin_ai_coach_garmin_vorschlaege`
    (Attribute `pending`/`accepted`/`rejected`, je eine Liste mit `id`/`title`/`text`).
  - Alle neuen Funktionen mit synthetischen Tests verifiziert (Annehmen/Ablehnen/Reaktivieren,
    JSON-Parsing inkl. Codeblock- und Fehlerfällen, vollständiger simulierter MQTT-Roundtrip
    Auswahl -> Annehmen -> Ablehnen -> Reaktivieren).

### 0.13.0
- **Fix: "Jetzt synchronisieren"-Button (Dashboard-Tab "Heute") gab HTTP 401 statt zu syncen.**
  Der Button rief bisher eine im Dashboard fest verdrahtete Ingress-URL
  (`/api/hassio_ingress/<Token>/sync?force=1`) direkt auf. Das funktioniert nur, solange der Browser
  bereits eine gueltige, kurzlebige Ingress-Session fuer dieses Add-on hat (die HA beim Oeffnen der
  Add-on-Weboberflaeche ueber Einstellungen -> Add-ons selbst aufbaut) - ein direkter Klick auf die
  Dashboard-Kachel oeffnet den Link dagegen typischerweise in einem neuen Tab/Kontext ohne diese
  Session, was Supervisor mit 401 Unauthorized quittiert. War bereits als latentes Risiko
  dokumentiert (siehe `claude/status-und-plan.md`, "Dashboard-Ingress-URL fragil"), trat jetzt live
  auf.
- **Fix: robuster durch einen MQTT-Button statt einer Ingress-URL.** Neue Button-Entity "Garmin
  Jetzt Synchronisieren" (`ha_publish.py`, `SYNC_BUTTON_COMMAND_TOPIC =
  "garmin_ai_coach/sync_now/set"`) wird wie die bestehenden Sensoren per MQTT-Discovery angelegt und
  bei jedem (Re-)Connect des MQTT-Clients erneut publiziert (`_on_connect`) - macht sie zusaetzlich
  robust gegen einen Mosquitto-Neustart (siehe Lessons Learned Punkt 10 in
  `claude/status-und-plan.md`). Das Add-on abonniert das Command-Topic und fuehrt bei einer
  Nachricht `do_sync(force=True, also_weekly=True)` in einem eigenen Thread aus (`app.py`,
  `_handle_sync_button_press`), damit der MQTT-Netzwerk-Thread nicht blockiert. Das Dashboard ruft
  jetzt den Service `mqtt.publish` (Topic `garmin_ai_coach/sync_now/set`, Payload `PRESS`) auf statt
  der alten URL - ein ganz normaler Home-Assistant-Service-Call, unabhaengig von Ingress-Sessions.
- **Neu: "Jetzt synchronisieren" erzeugt jetzt gleichzeitig den Wochenreport.** `do_sync()` hat
  einen neuen Parameter `also_weekly` (zusaetzlich zum bisherigen `weekday() == 0`-Automatismus fuer
  den montaeglichen Wochenreport); der Sync-Button setzt ihn auf `True`. Auch der manuelle
  `/sync`-Endpunkt akzeptiert jetzt `?weekly=1` fuer denselben Effekt (z.B. `/sync?force=1&weekly=1`
  ueber die Add-on-Weboberflaeche).

### 0.12.0
- **Neu: phasenspezifischer Gemini-Kommentar zu den Trainingsplaenen (Dashboard-Tab
  "Trainingsplaene").** Bisher hatte dieser Tab keine KI-Anbindung - die Plaene (Gym-Kritik,
  Lauf-/Schwimm-/Radplan je Phase) standen als reiner Text im Dashboard. Neue Funktion
  `generate_trainingsplan_kommentar()` in `ai_coach.py` (Vorbild `generate_gym_coaching_note()`)
  generiert dazu einen Kommentar - **ersetzt aber NICHT den Plan selbst**, der bleibt als stabile
  Referenz stehen.
- **Bewusst NICHT bei jedem Sync**, sondern nur wenn `check_trainingsplan_trigger()` (neu in
  `app.py`) einen konkreten Ausloeser erkennt: (1) Phasenwechsel (Grundlage -> Aufbau 1 -> Aufbau 2
  -> Peak -> Taper, kalenderbasiert, einmalig je Uebergang), (2) Training Readiness im 14-Tage-
  Schnitt unter 60 %, oder (3) VO2max stagniert/sinkt im 7-Tage-Schnitt gegenueber vor ca. 4 Wochen -
  beide Datentrigger mit 21-Tage-Cooldown, damit ein anhaltender Zustand nicht jeden Sync erneut
  ausloest. Zwei weitere in `claude/status-und-plan.md` dokumentierte Trigger (Benchmark-Sprung,
  konsistente Planabweichung) sind bewusst nicht umgesetzt - dafuer fehlen aktuell verlaessliche
  Daten (Zielzeit-Benchmarks liegen nur als manuelle HA-`input_number`-Helper vor, keine
  Wochenvolumen-Historie persistiert).
- Zustand (letzte bekannte Phase, letzter Ausloese-Zeitpunkt je Trigger-Typ) wird in
  `/data/trainingsplan_state.json` gehalten. Tages-Historie (`/data/history.json`) enthaelt ab
  jetzt zusaetzlich `vo2max` je Tag (fuer den Stagnations-Trigger); aeltere Eintraege ohne dieses
  Feld werden von `_history_avg()` einfach uebersprungen, kein Migrationsschritt noetig.
- Neuer Sensor `sensor.garmin_ai_coach_garmin_trainingsplan_kommentar` (`publish_trainingsplan_
  kommentar()` in `ha_publish.py`), mit Attributen `full_text`, `trigger`, `trigger_detail`,
  `generated_at`. Wird nur bei einem tatsaechlichen Ausloeser publiziert (retained) - ohne Ausloeser
  bleibt der zuletzt publizierte Kommentar im Dashboard einfach stehen, statt durch einen leeren/
  generischen Text ersetzt zu werden.
- Trigger-Logik mit synthetischen Testfaellen verifiziert (erster Sync, Phasenwechsel, Cooldown,
  niedrige Readiness, stagnierendes/steigendes VO2max).

### 0.11.3
- **Doppelt gezaehlte Rad-Einheiten (Zwift + Herzfrequenz-Zweitaufzeichnung) behoben.** Alex faehrt
  auf Zwift (laedt die Einheit inkl. echter Distanz nach Garmin hoch) und laesst parallel dazu eine
  zweite Aktivitaet auf der Garmin-Uhr mitlaufen, rein um die Herzfrequenz zu erfassen - die Uhr hat
  keine eigene Distanzmessung fuers Indoor-Fahren und die Aktivitaet wird selbst als "Indoor
  Radfahren" mit 0 km eingeordnet. `_volumes_in_window()` zaehlte bisher jede Aktivitaet mit
  "bik"/"cycl"/"ride" im `activityType`, also auch diese Herzfrequenz-Zweitaufzeichnung - dieselbe
  Fahrt tauchte dadurch als zwei Rad-Einheiten in den Wochenkennzahlen auf (Sessions und Minuten
  verdoppelt, km blieben korrekt, da die Zweitaufzeichnung 0 km beitraegt). Fix: Rad-Aktivitaeten
  zaehlen jetzt nur noch, wenn ihre Distanz > 0 km ist; die reine Herzfrequenz-Aufzeichnung ohne km
  wird ignoriert. Betrifft `weekly_volumes`/`weekly_volumes_prev` (Dashboard-Tab "Woche") und damit
  auch `bike_sessions`, `bike_min` und `total_min`/`volume_change_pct`; `bike_km` war schon vorher
  korrekt.

### 0.11.2
- **Versionsnummer erneut angehoben (0.11.1 -> 0.11.2), damit der Add-on-Store den Rebuild ueberhaupt
  erkennt:** `config.yaml` stand durch einen frueheren, unterbrochenen Aenderungsversuch bereits auf
  0.11.1, und dieser Stand war bereits committet/gepusht/im Add-on installiert - allerdings mit dem
  unten beschriebenen Bug. Der Fix fuer diesen Bug wurde zunaechst faelschlich weiter unter derselben
  Versionsnummer 0.11.1 abgelegt; der HA-Add-on-Store erkennt einen Rebuild aber nur ueber eine
  geaenderte `version`, nicht ueber Dateiinhalte - ohne Versionssprung waere "Neu laden" + Update
  wirkungslos geblieben, obwohl der Code auf GitHub bereits korrigiert war (daher: "hat sich nix
  geaendert" trotz gepushtem Fix). Lehre: bei jeder Code-Aenderung immer pruefen, ob die Version
  bereits dem lokal vorgefundenen Stand entspricht, statt sie unveraendert zu lassen.
- **Wochenreport (Dashboard-Tab "Woche") nutzt jetzt die echte Kalenderwoche (Mo-So) statt eines
  rollierenden 7-Tage-Fensters ab "jetzt".** Vorher zeigte der Report bei manueller Erzeugung (z. B.
  Mittwochs ueber "Wochenreport erzeugen") die letzten 7 Tage ab dem aktuellen Tag zurueck - das
  entspricht keiner echten Woche und macht Wochenvergleiche irrefuehrend, sobald der Report nicht
  exakt montags laeuft. `do_sync()` ermittelt die Trainingsvolumina (`weekly_volumes`/
  `weekly_volumes_prev`) und `build_weekly_summary()` die Datumsbereiche (`period_label`) jetzt ueber
  echte Montag-00:00-bis-Sonntag-Grenzen; bei Erzeugung mitten in der Woche zeigt "diese Woche"
  entsprechend die bisherige Teilwoche (Montag bis heute), "Vorwoche" immer die volle
  abgeschlossene Vorwoche.
  - **Bugfix dabei gefunden:** In `build_weekly_summary()` ueberschrieb ein doppelt vergebener
    Dict-Key (`readiness_avg`/`readiness_avg_prev` war zweimal im selben Dict-Literal gesetzt - ein
    Ueberrest der alten Implementierung) die neue kalenderwochenbasierte Berechnung wieder mit der
    alten rollierenden 7-Tage-Variante. Dadurch waeren Ruhepuls/HRV/Schlaf im Wochenmittel bereits
    korrekt auf die Kalenderwoche umgestellt gewesen, Training Readiness aber weiterhin auf den alten
    rollierenden Wert zurueckgefallen. Doppelten Eintrag entfernt, `py_compile` verifiziert.
  - **Bewusst unveraendert:** Die "Gym Fortschritt"-Liste im Tab "Gym" (`_update_strength_exercises`)
    nutzt weiterhin ein rollierendes 7-Tage-Fenster fuer die dort gelisteten Kraft-Einheiten - das war
    nicht Teil dieser Anfrage (nur der Tab "Woche"), koennte bei Bedarf separat umgestellt werden.

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
