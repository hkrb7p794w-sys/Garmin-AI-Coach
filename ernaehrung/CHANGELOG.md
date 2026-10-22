# Changelog

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
