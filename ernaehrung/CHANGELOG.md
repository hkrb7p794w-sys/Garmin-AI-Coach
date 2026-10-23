# Changelog

## 0.3.0
- **Design wie das Garmin-AI-Coach-Dashboard**: Karten, Ring, Balken, Navigation und Farben übernehmen das aktive
  HA-Theme (hell/dunkel); neue Dashboard-Karte `coach-nutrition` (coach-cards.js 1.4.0).
- **Fotos werden nie gespeichert** (nur im Arbeitsspeicher während der Analyse); alte Fotos gelöscht.
  Neu: `ki_anbieter: lokal` für einen eigenen KI-Server im Heimnetz (OpenAI-kompatibel, z. B. Ollama).
- **Empfehlungen**: was und wie noch essen (vor/nach dem Training, Proteinverteilung, Lücken füllen mit konkreten
  Lebensmitteln, Trinken, Grenzen) sowie Wochenmuster nach DGE 2024 (Fisch, Hülsenfrüchte, Nüsse, Obst/Gemüse,
  Vollkorn) und Nährstofflücken; Ernährungsweise einstellbar (Standard pescetarisch).
- Neue Nährstoffe **Jod** (DGE/ÖGE 2025: 150 µg) und **Omega-3 EPA+DHA** (EFSA: 250 mg); BLS wird dafür neu importiert.
- Lebensmittelgruppen je Position (KI, BLS-Gruppe, Stichwörter); Energiebilanz aus Gewichtsverlauf.
- Nach Vergleich mit Yazio, MyFitnessPal, Cronometer, MacroFactor: Markenprodukt-Suche (Open Food Facts),
  Schnelleintrag nur Kalorien, Portionsauswahl („1 Scheibe“, „2 Eier“), „wie gestern“, „Heute nochmal“,
  Datum im Prüf-Fenster, Rezepte mit Portionen, zuletzt Gegessenes in der Suche, Gewicht von Waage-Sensor,
  „Alle Daten löschen“.
- Suche: Plural/Singular („Linsen“ findet „Linse“), Gerichte nach hinten („Quark“ findet Speisequark).

## 0.2.0
- Foto: auch Bilder aus der Mediathek; Datum/Uhrzeit der Aufnahme (EXIF) werden übernommen.
- Tagestyp vor dem Training aus dem Wochenplan des Coach (Kohlenhydrate vor harten Einheiten).
- Protein je Ziel (1,8 / 2,0 / 2,2 g/kg), Zähler für proteinreiche Mahlzeiten (≥ 0,25 g/kg).
- Abnehmen: Untergrenze Energieverfügbarkeit 30 kcal/kg fettfreie Masse; optionales Körperfett-Feld.
- Garmin-Gesamtumsatz zum Vergleich in „Wie das Ziel zustande kommt“.

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
