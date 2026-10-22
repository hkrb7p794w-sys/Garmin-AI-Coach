# Changelog

## 0.1.5
- Sensoren bekommen feste IDs `sensor.ernaehrung_*` (MQTT `default_entity_id`) und kürzere Namen
  („Zucker“, „Gesättigte Fettsäuren“, „Heute“, „Woche“).

## 0.1.4
- Gemini: bei Kontingent-Fehler (429) sofort auf ein Ausweichmodell, statt zu warten; bei Überlastung
  (503) nur ein kurzer zweiter Versuch. Nicht mehr verfügbare Modelle werden gemerkt.
  Anlass: Live-Test – gemini-3.6-flash lieferte 429, die erste Analyse dauerte dadurch über 30 s.

## 0.1.3
- Bessere Zuordnung zur Datenbank: ein zweiter KI-Schritt wählt unter den BLS-Kandidaten den passenden
  Eintrag; Treffer mit nicht genannten Zusätzen („mit Alkohol“, „mit Zucker“) werden abgewertet.
  Anlass: Live-Test „Kaffee mit Milch“ landete bei „Kaffee (Getränk) mit Alkohol“.

## 0.1.2
- BLS-Download: Links auf blsdb.de sind als HTML-Entities kodiert (`&#47;` …) – werden jetzt dekodiert.

## 0.1.1
- BLS-Download: Link wird auch in Weiterleitungen (Meta-Refresh/JavaScript) gesucht; bei Fehlschlag
  beschreibt das Log die Download-Seite (Codes gekürzt).

## 0.1.0
- Erste Version: Erfassung per Foto, Text, Barcode, Suche und Wasser-Schnellknopf; Prüf-Fenster mit
  Mengen, Zuordnung und Quellen-Kennzeichnung; Tages- und Wochenübersicht; Favoriten und häufige
  Mahlzeiten; dynamische Tagesziele aus Garmin-Trainingsdaten; BLS 4.0 + Open Food Facts;
  MQTT-Sensoren und REST-API für Home Assistant; CSV-Export.
