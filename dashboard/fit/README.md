# Dashboard „Fit“ (Fit Coach)

Kopie der Dateien, die in Home Assistant liegen – zur Versionierung und zum Wiederherstellen.
Stand: Karten 0.1.0, Daisy 0.2.0, passend zur App „Fit Coach“ 0.1.0 (`fit_coach/`).

| Datei hier | Liegt in Home Assistant unter | Inhalt |
|---|---|---|
| `www/fit/fit-cards.js` | `/config/www/fit/fit-cards.js` | eigene Karten: fit-hero, -week, -weight, -food, -run, -gym, -badges, -status |
| `www/fit/fit-daisy.js` | `/config/www/fit/fit-daisy.js` | Daisy, die Tamagotchi-Trainerin (Stimmung, Bedürfnisse, Tagesauftrag, Streicheln, Leckerli, Level) |
| `fit-coach.dashboard.json` | Dashboard `fit-coach` (UI-Modus, Titel „Fit“) | Ansichten Heute, Laufen, Gewicht, Gym, Woche (Unterseite), Erfolge, Einstellungen |

Die Karten brauchen keine Helfer in Home Assistant: alle Werte kommen von der App über MQTT
(`sensor.fit_coach_*`), Eingaben laufen über deren `number.`/`select.`/`button.fit_coach_*`-Entitäten.
Ist die App nicht installiert, zeigt das Dashboard nur einen Hinweis statt Fehlermeldungen.

## Wiederherstellen

1. `fit-cards.js` per File Editor oder Samba nach `/config/www/fit/` kopieren.
2. Ressourcen: Einstellungen › Dashboards › ⋮ › Ressourcen › `/local/fit/fit-cards.js?v=0.1.0` und `/local/fit/fit-daisy.js?v=0.2.0`, jeweils als **JavaScript-Modul**.
   Bei jeder neuen Version die Zahl hinter `?v=` erhöhen, sonst lädt die Companion-App die alte Datei aus dem Cache.
3. Dashboard „Fit“ (`fit-coach`) anlegen › ⋮ › Bearbeiten › ⋮ › Raw-Konfigurationseditor › Inhalt der JSON-Datei einfügen.

## Daisy

Daisy steht ganz oben in „Heute“ und reagiert nur auf die vorhandenen `sensor.fit_coach_*`-Werte:

- **Aussehen**: animierte SVG-Zeichnung nach Daisys Fotos (struppiges goldenes Fell, helle Schnauze mit Bart,
  Schlappohren, hellblaues Blümchen-Halstuch, graues Halsband). Sie wedelt, blinzelt, hechelt, wackelt mit den Ohren,
  atmet im Liegen und springt beim Streicheln auf. Bei „Bewegung reduzieren“ im System steht sie still.
- **Stimmung** (sitzend oder liegend): wartet an der Tür (nicht angemeldet), platt & stolz (heute trainiert),
  überglücklich (Wochenziel, neuer Rekord oder Abzeichen), Ruhetag, zufrieden, will raus,
  langweilt sich, vermisst dich (≥ 3 Tage kein Training), schläft (22–6 Uhr).
- **Bedürfnisse**: Auslauf (Training heute / letzte Aktivität / Schritte), Wochenziel, Check-in (gewogen, Essen erfasst).
- **Sprüche**: wichtigstes zuerst (Fürsorge → Feiern → Stimmung → Plan → Fortschritt), Sprechblase antippen für mehr.
  Leitplanken: kein Lob fürs Hungern oder zu schnelles Abnehmen, kein Schimpfen wegen Gewicht oder Essen.
- **Streicheln / Leckerli / Level**: Leckerli gibt es pro Training der Woche; gemerkt wird pro Gerät im Browser.
- Option `name` (Standard: Vorname des HA-Benutzers).
