# Ernährung

Mahlzeiten in wenigen Sekunden erfassen – per **Foto**, **Text**, **Barcode** oder **Suche** – mit Makros,
Mikronährstoffen, Tageszielen nach deinem Training und konkreten Empfehlungen, was du noch essen könntest.
Optik wie das Garmin-AI-Coach-Dashboard (Farben und Schrift kommen aus dem aktiven Home-Assistant-Theme).

## Einrichten

1. **KI für Foto/Text** in der Konfiguration wählen:
   - `ki_anbieter: gemini` + `gemini_api_key` (kostenlos unter aistudio.google.com, derselbe Key wie beim Coach), oder
   - `ki_anbieter: lokal` + `lokal_url` + `lokal_modell`: eigener KI-Server im Heimnetz mit OpenAI-kompatibler
     Schnittstelle, z. B. [Ollama](https://ollama.com) mit einem Bildmodell (`qwen2.5vl:7b`, `gemma3:12b`) auf einem
     PC/Mac mit Grafikkarte bzw. Apple Silicon. Dann verlassen Fotos und Texte das Heimnetz nie.
     Der Raspberry Pi selbst ist dafür zu schwach.
   Ohne KI funktionieren Barcode, Suche, Schnelleintrag und manuelle Eingabe.
2. App über die Seitenleiste „Ernährung“ öffnen (auch in der HA-App auf dem iPhone) oder über die Karte
   „Ernährung“ im Garmin-Coach-Dashboard.
3. Beim ersten Start lädt die App den **Bundeslebensmittelschlüssel (BLS 4.0)** von blsdb.de (~14 MB). Klappt das
   nicht: Datei von https://blsdb.de/download nach `/share/ernaehrung/` legen und in den Einstellungen „BLS neu laden“.
4. **Einstellungen**: Ernährungsweise (Standard: pescetarisch), Körperdaten prüfen, optional **Gewicht von Sensor**
   (z. B. Körperwaage) wählen. Gewicht, Größe, Alter und Trainings kommen sonst aus dem Garmin AI Coach (ab 0.29.0).

## Erfassen

- **Foto**: aufnehmen oder aus der Mediathek wählen. Bei älteren Fotos übernimmt die App Datum und Uhrzeit der
  Aufnahme. Optional ergänzen („mit Olivenöl“).
- **Text**: z. B. „2 Rühreier mit Vollkornbrot und ein Kaffee mit Milch“ (Diktieren per Tastatur geht auch).
- **Barcode**: fotografieren/aus Fotos, live scannen (nur über HTTPS) oder Nummer eintippen. Daten von Open Food
  Facts; einmal gescannte Produkte sind danach offline verfügbar.
- **Suchen**: ohne Eingabe zuletzt/häufig Gegessenes, sonst eigene Lebensmittel + BLS. **Markenprodukte** sucht per
  Knopfdruck in Open Food Facts. **Nur Kalorien** = Schnelleintrag ohne Lebensmittel.
- **+250 ml**: Wasser mit einem Tipp. **Wie gestern** kopiert eine leere Mahlzeit vom Vortag, **Heute nochmal**
  (im Bearbeiten-Fenster) trägt eine Mahlzeit erneut ein, **+** neben einer Mahlzeit fügt direkt dort hinzu.

Alles landet zuerst im Prüf-Fenster: Menge (±, Portionen wie „1 Scheibe“, „2 Eier“), Zuordnung tauschen, Datum,
Uhrzeit, Mahlzeit. **Als Favorit/Rezept merken** – bei Rezepten mit „ergibt Portionen“ trägt „Eintragen“ eine Portion ein.

Quellen-Kennzeichnung: **BLS** (Datenbank), **Produkt** (Open Food Facts), **Eigenes**, **KI-Schätzung**.

## Empfehlungen

**Heute** (Karte „Empfehlungen für heute“, auch im Coach-Dashboard):
- **Vor dem Training** (laut Wochenplan, noch nichts aufgezeichnet): 1–4 g Kohlenhydrate je kg 1–4 h vorher.
- **Nach dem Training** (Einheit in den letzten 3 h beendet): 0,25–0,4 g/kg Protein plus Kohlenhydrate.
- **Proteinverteilung**: 3–4 Mahlzeiten mit ≥ 0,25 g/kg; abends Quark/Skyr (Casein).
- **Passt noch gut in den Tag**: 2–3 konkrete Lebensmittel, die die größten Lücken je Kalorie füllen – passend zur
  Ernährungsweise, zum restlichen Kalorienbudget und zur Tageszeit. Antippen = eintragen.
- Trinken, Zucker/gesättigte Fette über der Orientierung, deutlich über dem Kalorienziel.

**Woche** (ab 3 vollständig erfassten Tagen): Fisch 1–2x (davon einmal fettreich), Hülsenfrüchte, Nüsse,
Obst & Gemüse, Vollkornanteil (DGE 2024), wiederkehrende Lücken bei Eisen, Jod, Omega-3, Magnesium, Calcium,
Kalium, Zink, Ballaststoffen, B12 – jeweils mit den nährstoffreichsten Vorschlägen; Vitamin D im Winterhalbjahr;
Kohlenhydrate an harten Tagen, Protein an Trainingstagen.

**Energiebilanz**: Ab 14 vollständig erfassten Tagen mit regelmäßigen Gewichtswerten schätzt die App deinen
tatsächlichen Verbrauch (Zufuhr minus Gewichtsänderung × 7.700 kcal/kg) und schlägt vor, den Alltagsfaktor anzupassen.

## Tagesziele

| Wert | Grundlage |
|---|---|
| Kalorien | Grundumsatz (Mifflin-St Jeor) × Alltag (PAL 1,4) + Netto-kcal der heutigen Garmin-Aktivitäten. Garmin-Gesamtumsatz nur zum Vergleich (Uhren-Schätzungen streuen stark). Beim Abnehmen nie unter 30 kcal je kg fettfreie Masse + Training |
| Kohlenhydrate | g/kg nach Tagestyp: Ruhetag 3, leicht 4, moderat 6, hart 8, sehr hart 10 (ACSM/AND/DC 2016) |
| Protein | halten 1,8 · aufbauen 2,0 · abnehmen 2,2 g/kg |
| Fett | Rest der Energie, 20–35 % |
| Zucker, gesättigte Fette | Obergrenze je 10 % der Energie (Orientierung) |
| Mikronährstoffe | DGE 25 bis < 51 Jahre; Zink 14 mg (mittlere Phytatzufuhr: Mischkost mit Fisch, Vollkorn, Hülsenfrüchten); **Jod 150 µg** (DGE/ÖGE 2025) |
| Omega-3 (EPA+DHA) | 250 mg (EFSA) |
| Flüssigkeit | 35 ml/kg + ca. 0,6 l je Stunde Ausdauertraining |

Tagestyp: vor dem Training aus dem Coach-Wochenplan, danach aus Garmin (≥ 4 h Ausdauer sehr hart, ≥ 90 min oder
Last ≥ 150 hart, ≥ 45 min / ≥ 75 min Training / Last ≥ 80 moderat, ≥ 20 min leicht). Manuell änderbar.

## Grenzen

- **Foto-Portionen sind Schätzungen** (Studie Fridolfsson 2025: ~36 % mittlerer Fehler bei den besten Bildmodellen,
  große Portionen werden unterschätzt). Nährwerte kommen deshalb aus Datenbanken, nur die Mengen von der KI.
- Datenbankwerte sind Durchschnittswerte; bei Markenprodukten fehlen oft Mikronährstoffe (dann Untergrenze).
- **Jodsalz** zählt die App nicht mit (Salzmenge ist kaum erfassbar) – die Jod-Summe ist also eine Untergrenze.
- Vitamin D kommt überwiegend aus der Sonne; über Essen ist das Ziel kaum erreichbar.
- Empfehlungen sind allgemeine Ernährungsregeln, keine medizinische Beratung.

## Datenschutz

- **Fotos werden nie gespeichert** – weder auf dem Pi noch im Browser. Das Bild existiert nur während der Analyse im
  Arbeitsspeicher; nach dem Speichern bzw. Schließen ist es weg. Fotos älterer Versionen wurden beim Update gelöscht.
- Mit `ki_anbieter: gemini` geht das Foto zur Analyse an Google (im kostenlosen Kontingent darf Google Eingaben zur
  Verbesserung nutzen). Mit `ki_anbieter: lokal` bleibt alles im Heimnetz. Foto-Analyse in den Einstellungen abschaltbar.
- Barcode-Nummern bzw. Suchwörter für Markenprodukte gehen an Open Food Facts.
- Alle anderen Daten liegen lokal in `/data` (Teil der HA-Backups). CSV-Export und „Alle Daten löschen“ in den Einstellungen.

## Home Assistant

Gerät **Ernährung** per MQTT:
- `sensor.ernaehrung_<nährstoff>` (kalorien, protein, kohlenhydrate, fett, ballaststoffe, fluessigkeit, zucker,
  gesaettigte_fettsaeuren, natrium, kalium, magnesium, calcium, eisen, zink, jod, omega_3, vitamin_d, vitamin_b12,
  vitamin_c) – Tageswert, Attribute `ziel`, `prozent`, `art`
- `sensor.ernaehrung_tag` – kcal-Fortschritt in %, Attribute: Tagesauswertung inkl. `recommendations`
- `sensor.ernaehrung_woche` – Anzahl wiederkehrender Lücken, Attribute: 7-Tage-Auswertung, Lebensmittelgruppen,
  Energiebilanz, `recommendations`

Dashboard-Karte `custom:coach-nutrition` (in `coach-cards.js` ab 1.4.0). REST im internen Netz:
`/api/v1/day`, `/api/v1/week`, `/api/v1/export.csv`.

## Quellen

- Max Rubner-Institut (2025): Bundeslebensmittelschlüssel (BLS), Version 4.0. DOI 10.25826/Data20251217-134202-0. CC BY 4.0.
- Open Food Facts (ODbL).
- DGE (2024): Gut essen und trinken – lebensmittelbezogene Ernährungsempfehlungen. https://www.dge.de/gesunde-ernaehrung/gut-essen-und-trinken/dge-empfehlungen/
- DGE/ÖGE (2025): Neue Referenzwerte für die Jodzufuhr (150 µg). https://www.dge.de/presse/meldungen/2025/neue-referenzwerte-fuer-die-jodzufuhr/
- DGE: Referenzwerte (Eisen, Zink, Magnesium, Calcium, Kalium, Natrium, Vitamin C/D/B12, Ballaststoffe, Wasser); FAQ Zink 2019 (Phytatzufuhr); FAQ Nahrungsergänzungsmittel.
- EFSA (2012): Adäquate Zufuhr langkettiger Omega-3-Fettsäuren 250 mg/Tag.
- BfR: Ausgewählte Fragen und Antworten zu Vitamin D (Oktober–März kaum Eigensynthese).
- Thomas DT, Erdman KA, Burke LM (2016): Nutrition and Athletic Performance. Med Sci Sports Exerc 48(3):543–568.
- Kerksick CM et al. (2017): ISSN position stand: nutrient timing. J Int Soc Sports Nutr 14:33. doi:10.1186/s12970-017-0189-4
- Morton RW et al. (2018): Br J Sports Med 52(6):376–384. doi:10.1136/bjsports-2017-097608
- Williamson E et al. (2023): Med Sci Sports Exerc 55(10):1866–1875. doi:10.1249/MSS.0000000000003219
- Aragon AA et al. (2026): ISSN position stand: diets for body weight reduction. doi:10.1080/15502783.2026.2740266
- Mountjoy M et al. (2023): IOC consensus statement on REDs. doi:10.1136/bjsports-2023-106994
- Impey SG et al. (2018): Fuel for the work required. doi:10.1007/s40279-018-0867-7
- O'Driscoll R et al. (2020): Activity monitors and energy expenditure. doi:10.1136/bjsports-2018-099643
- Fridolfsson J et al. (2025): LLMs for nutritional estimation from food images. doi:10.1016/j.cdnut.2025.107556
- Mifflin MD, St Jeor ST et al. (1990): Am J Clin Nutr 51(2):241–247.
- Barcode-Erkennung: ZXing (Apache-2.0). Icons: Material Design Icons (Pictogrammers, Apache-2.0).
