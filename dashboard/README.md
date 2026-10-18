# Dashboard „Garmin Coach“

Kopie der Dateien, die in Home Assistant liegen – zur Versionierung und zum Wiederherstellen.
Das Add-on selbst braucht sie nicht; Home Assistant liest sie aus `/config`.
Stand: Karten 1.1.1, passend zu Add-on 0.22.1.

| Datei hier | Liegt in Home Assistant unter | Inhalt |
|---|---|---|
| `www/coach/coach-cards.js` | `/config/www/coach/coach-cards.js` | eigene Karten: coach-hero, -week, -level, -nav, -trend, -metrics, -zones, -hr, -gym, -lifts, -phases, -achievements |
| `custom_templates/*.jinja` | `/config/custom_templates/` | Saisonplan (`coach_plan`), Tages-/Wochenlogik (`coach_app`), Texte der Sport-Reiter (`coach_ui`, `coach_sub`, `coach_list`, `coach_views`), Spielregeln (`coach_game`), Gym/HF (`coach_gym_hf`, `coach_hf5`), Wochenrahmen (`coach_days`) |
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
2. Ressource eintragen: Einstellungen › Dashboards › ⋮ › Ressourcen › `/local/coach/coach-cards.js?v=1.1.1` als **JavaScript-Modul**.
   Bei jeder neuen Version die Zahl hinter `?v=` erhöhen – sonst lädt die Companion-App die alte Datei aus dem Cache.
3. Nach Änderungen an Templates: Entwicklerwerkzeuge › Aktionen › `homeassistant.reload_custom_templates`.
4. Dashboard: Dashboard öffnen › ⋮ › Bearbeiten › ⋮ › Raw-Konfigurationseditor › Inhalt der JSON-Datei einfügen (der Editor akzeptiert JSON).

Helfer (`input_*.coach_*`, `counter.coach_*`) und die Automationen für Serie, XP und Push liegen nur in Home Assistant
und sind über die normalen HA-Backups gesichert.
