# Dashboard „Garmin Coach“

Kopie der Dateien, die in Home Assistant liegen – zur Versionierung und zum Wiederherstellen.
Das Add-on selbst braucht sie nicht; Home Assistant liest sie aus `/config`.
Stand: Karten 1.3.0, passend zu Add-on 0.25.x.

| Datei hier | Liegt in Home Assistant unter | Inhalt |
|---|---|---|
| `www/coach/coach-cards.js` | `/config/www/coach/coach-cards.js` | eigene Karten: coach-hero, -week, -nav, -trend, -metrics, -zones, -hr, -gym, -lifts, -phases |
| `www/coach/coach-nutrition.js` | `/config/www/coach/coach-nutrition.js` | Karte coach-nutrition (Ernährung), nutzt die Basisklasse aus coach-cards.js |
| `custom_templates/*.jinja` | `/config/custom_templates/` | Saisonplan (`coach_plan`), Tages-/Wochenlogik (`coach_app`), Texte der Sport-Reiter (`coach_ui`, `coach_sub`, `coach_list`, `coach_views`), Gym/HF (`coach_gym_hf`, `coach_hf5`), Wochenrahmen (`coach_days`) |
| `garmin-coach.dashboard.json` | Dashboard `garmin-coach` (UI-Modus) | alle Ansichten und Karten |

Nicht mehr genutzt (seit Karten 1.1 ersetzt durch `coach-gym` und `coach-hr`, liegen nur noch als Referenz in HA):
`coach_gym_hf.jinja`, `coach_hf5.jinja` sowie in `coach_ui.jinja` die Makros `swim_status`, `bike_status`, `run_status`,
`zwift_library`, `gym_status` und `gym_lifts`. Die Volumen-Texte darin („ab 10 Sätzen das Maximum“) sind überholt –
maßgeblich ist die Formulierung in der Karte (Schoenfeld 2017: graduelle Dosis-Wirkung; Pelland 2025: abnehmender Ertrag).

## Regel: Hinweise nur an einer Stelle

Alle Hinweise zu einer Einheit („nicht heute“, „⅓ weniger Sätze“, „heute nur Z2“, „fällt diese Woche aus“) entstehen
ausschließlich in `coach_today()` (`coach_app.jinja`). Karte (`coach-hero`) und Push-Nachricht (`coach_today_text()`)
zeigen nur an, was dort steht – so können sich beide nicht widersprechen. Maßgeblich ist der Wochentag: Am Sonntag
(`dl` = 0) gibt es kein „nicht heute“ mehr, weil kein späterer Tag folgt; harte Einheiten wandern dann in die Liste
„Fällt diese Woche aus“. Neue Hinweise also immer in `_chip()` ergänzen, nicht in der Karte.

Konsistenz-Test: `check_today.py` (liegt in `scripts/`, zusammen mit `check_addon.py`; Aufruf: `python3 -I scripts/check_today.py dashboard/custom_templates` (braucht `pip install jinja2`)) spielt alle
Wochentage × Tagesampel × erledigt/offen durch und prüft die Regeln.

## Wiederherstellen

1. `coach-cards.js` und die Templates per File Editor oder Samba an die Stellen oben kopieren.
2. Ressource eintragen: Einstellungen › Dashboards › ⋮ › Ressourcen › `/local/coach/coach-cards.js?v=1.3.0` als **JavaScript-Modul**.
   Bei jeder neuen Version die Zahl hinter `?v=` erhöhen – sonst lädt die Companion-App die alte Datei aus dem Cache.
3. Nach Änderungen an Templates: Entwicklerwerkzeuge › Aktionen › `homeassistant.reload_custom_templates`.
4. Dashboard: Dashboard öffnen › ⋮ › Bearbeiten › ⋮ › Raw-Konfigurationseditor › Inhalt der JSON-Datei einfügen (der Editor akzeptiert JSON).

Helfer (`input_*.coach_*`) und die Automation für den Morgen-Push liegen nur in Home Assistant
und sind über die normalen HA-Backups gesichert.

## Gamification entfernt (18.10.2026)

Level/XP, Wochenserie mit Joker und Pausenwoche, Abzeichen, Meilensteine und das adaptive Wochenziel sind raus
(Karten `coach-level`/`coach-achievements`, Ansicht „Erfolge“, `coach_game.jinja`, Zähler und Meilenstein-Helfer,
Skript `coach_xp_vergeben`, fünf Automationen). Die Wochenquote bleibt als reine Anzeige „x von y Einheiten“
(Makro `quote()` jetzt in `coach_app.jinja`). Sicherung davor: HA-Backup „Vor Entfernen Gamification 2026-10-18“.

## Coach im Reiter Chat (18.10.2026, Add-on 0.23.0)

Der Abschnitt „Coach“ (KI-Gym-Tipp, offene Vorschläge nach Disziplin, Annehmen/Ablehnen) steht jetzt im Reiter
**Chat** statt im Reiter Gym. Die Vorschläge kommen aus einem gemeinsamen Pool (Add-on `suggestions.py`):
Wochenreport (alle Disziplinen), Plan-Kommentar und feste Gym-Punkte – ohne Dubletten, eine neue Einschätzung
ersetzt ältere offene KI-Vorschläge. Die Karte „Übungsnamen zusammengeführt“ (`gym_mapping_list()` in
`coach_views.jinja`) ist ausgeblendet; die Zusammenführung der Übungsnamen läuft im Add-on weiter.

## Feedback, Rest der Woche, Listen (21.10.2026, Karten 1.3.0, Add-on 0.25.0)

- **Feedback je Einheit:** Das Add-on schreibt pro Einheit einen kurzen Text in `sensor.garmin_ai_coach_garmin_tagesform_leistung`
  (Attribut `sessions[].feedback`, gebaut in `tagesform.feedback()`). `coach_today()` hängt ihn an erledigte Einheiten von heute
  (`items[].fb`); Einheiten von gestern und zusätzliche von heute stehen unter `done` („Erledigt“). Die Morgen-Push enthält „Gestern …“.
- **Rest der Woche:** `coach_today().week` listet alle noch kommenden Einheiten mit festem Tag (Do Beine/Schwimmen, Fr Push+Pull,
  Sa/So Zwift). Die Läufe ohne festen Tag stehen getrennt unter „Noch offen · ohne festen Tag“ (früher „Diese Woche noch offen“).
- **Listen in Markdown-Karten:** jede Markdown-Karte hat `card_mod: style: "ha-card { --markdown-list-indent: 1em; }"`
  (HA-Variable `--markdown-list-indent` aus `ha-markdown.ts`, Standard = Browser-Einzug 40 px).
- **Qualitätslauf:** nur noch Schwelle und 4×4 min (90–95 % HFmax) – keine 1000er-Intervalle mehr (`coach_plan.jinja`).
- **Automation „Garmin Coach: Schwimm-Ausrüstung am Vorabend“** (20:30): Push, wenn die Schwimmeinheit morgen Ausrüstung braucht
  (Sensor `sensor.garmin_ai_coach_garmin_schwimm_equipment`).

## Ernährung (23.10.2026, coach-nutrition.js 1.0.0, Add-on „Ernährung“ 0.3.0)

Neue Karte `custom:coach-nutrition` (Reiter **Ernährung** und unten auf **Heute**): kcal-Ring, Makros, Empfehlungen
des Tages und Wochenhinweise aus `sensor.ernaehrung_tag` / `sensor.ernaehrung_woche`. Antippen öffnet die
Ernährungs-App (Seitenleisten-Panel `/1c76c417_ernaehrung`, sonst `/hassio/ingress/1c76c417_ernaehrung`).
Optionen: `max_recs` (Standard 2), `max_week` (Standard 2). Ressource: `/local/coach/coach-nutrition.js?v=1.0.0` als JavaScript-Modul (zusätzlich zu coach-cards.js).
