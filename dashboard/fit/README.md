# Dashboard „Fit“ (Fit Coach)

Kopie der Dateien, die in Home Assistant liegen – zur Versionierung und zum Wiederherstellen.
Stand: Karten 0.1.0, passend zur App „Fit Coach“ 0.1.0 (`fit_coach/`).

| Datei hier | Liegt in Home Assistant unter | Inhalt |
|---|---|---|
| `www/fit/fit-cards.js` | `/config/www/fit/fit-cards.js` | eigene Karten: fit-hero, -week, -weight, -food, -run, -gym, -badges, -status |
| `fit-coach.dashboard.json` | Dashboard `fit-coach` (UI-Modus, Titel „Fit“) | Ansichten Heute, Laufen, Gewicht, Gym, Woche (Unterseite), Erfolge, Einstellungen |

Die Karten brauchen keine Helfer in Home Assistant: alle Werte kommen von der App über MQTT
(`sensor.fit_coach_*`), Eingaben laufen über deren `number.`/`select.`/`button.fit_coach_*`-Entitäten.
Ist die App nicht installiert, zeigt das Dashboard nur einen Hinweis statt Fehlermeldungen.

## Wiederherstellen

1. `fit-cards.js` per File Editor oder Samba nach `/config/www/fit/` kopieren.
2. Ressource: Einstellungen › Dashboards › ⋮ › Ressourcen › `/local/fit/fit-cards.js?v=0.1.0` als **JavaScript-Modul**.
   Bei jeder neuen Version die Zahl hinter `?v=` erhöhen, sonst lädt die Companion-App die alte Datei aus dem Cache.
3. Dashboard „Fit“ (`fit-coach`) anlegen › ⋮ › Bearbeiten › ⋮ › Raw-Konfigurationseditor › Inhalt der JSON-Datei einfügen.
