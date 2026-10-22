# Ernährung

Mahlzeiten in wenigen Sekunden erfassen – per **Foto**, **Text**, **Barcode** oder **Suche** – mit
Makros, Mikronährstoffen und Tageszielen, die sich nach deinem Training richten.

## Einrichten

1. **Gemini API Key** (für Foto- und Texterkennung) in der Konfiguration eintragen –
   derselbe kostenlose Key wie beim Garmin AI Coach (aistudio.google.com › „Get API key“).
   Ohne Key funktionieren Barcode, Suche und manuelle Eingabe.
2. App starten und über die Seitenleiste „Ernährung“ öffnen (auch in der HA-App auf dem iPhone).
3. Beim ersten Start lädt die App den **Bundeslebensmittelschlüssel (BLS 4.0)** von blsdb.de
   (~14 MB, ein bis zwei Minuten). Klappt das nicht, die Datei von https://blsdb.de/download
   herunterladen und nach `/share/ernaehrung/` legen, dann in den Einstellungen „BLS neu laden“.
4. Unter **Einstellungen** Körperdaten prüfen. Mit dem Garmin AI Coach ab 0.29.0 kommen Gewicht,
   Größe, Alter und die heutigen Aktivitäten automatisch aus Garmin.

## Erfassen

- **Foto**: Mahlzeit fotografieren oder ein Bild aus der Mediathek wählen (iOS fragt nach). Bei älteren Fotos
  übernimmt die App Datum und Uhrzeit der Aufnahme. Optional einen Hinweis ergänzen („mit Olivenöl“), prüfen, speichern.
- **Text**: z. B. „2 Rühreier mit Vollkornbrot und ein Kaffee mit Milch“. Diktieren per iPhone-Tastatur geht auch.
- **Barcode**: Barcode fotografieren (oder live scannen, wenn HA über HTTPS läuft) oder Nummer eintippen.
  Produktdaten von Open Food Facts; einmal gescannte Produkte sind danach offline verfügbar.
- **Suchen**: eigene Lebensmittel und BLS. Fehlt etwas, „Eigenes Lebensmittel anlegen“.
- **+250 ml**: Wasser mit einem Tipp.

Jede Erfassung landet zuerst im Prüf-Fenster: Mengen ändern (±), Zuordnung tauschen („Andere Zuordnung“),
Positionen entfernen oder ergänzen. Gespeicherte Mahlzeiten lassen sich jederzeit antippen und ändern.

Quellen-Kennzeichnung: **BLS** (Datenbank), **Produkt** (Open Food Facts), **Eigenes**,
**KI-Schätzung** (kein passender Datenbank-Eintrag – Werte sind von Gemini geschätzt).

## Tagesziele

| Wert | Grundlage |
|---|---|
| Kalorien | Grundumsatz (Mifflin-St Jeor) × Alltagsaktivität (PAL 1,4) + Netto-kcal der heutigen Garmin-Aktivitäten. Der Garmin-Gesamtumsatz wird nur zum Vergleich angezeigt: Uhren-Schätzungen des Energieverbrauchs streuen stark (O'Driscoll 2020). Beim Abnehmen nie unter 30 kcal je kg fettfreie Masse plus Training (Energieverfügbarkeit, IOC-Konsensus REDs 2023) |
| Kohlenhydrate | g/kg nach Tagestyp: Ruhetag 3, leicht 4, moderat 6, hart 8, sehr hart 10 (ACSM/AND/DC 2016: 3–5 / 5–7 / 6–10 / 8–12) |
| Protein | nach Ziel: halten 1,8 · aufbauen 2,0 · abnehmen 2,2 g/kg (Ausdauer: Bedarf ~1,8–1,9 g/kg, Williamson 2023; Muskelaufbau: Plateau ~1,6, Spanne bis 2,2, Morton 2018; Defizit: 1,9–3,2, ISSN 2026). Verteilt auf ≥ 3–4 Mahlzeiten mit je ≥ 0,25 g/kg (ISSN 2017) – die App zählt sie mit |
| Fett | Rest der Energie, 20–35 % |
| Zucker, gesättigte Fette | Obergrenze je 10 % der Energie (Orientierung; Zucker = Gesamtzucker inkl. Obst/Milch) |
| Mikronährstoffe, Ballaststoffe | DGE-Referenzwerte 25 bis < 51 Jahre |
| Flüssigkeit | 35 ml/kg (DGE-Gesamtwasser inkl. Wasser aus Lebensmitteln) + ca. 0,6 l je Stunde Ausdauertraining |

Tagestyp: Solange heute noch kein Training aufgezeichnet ist, gilt der Tagestyp aus dem Wochenplan des Coach
(Kohlenhydrate gehören vor die Einheit, „fuel for the work required“, Impey 2018). Danach aus Garmin: ≥ 4 h Ausdauer = sehr hart, ≥ 90 min Ausdauer oder Trainingslast ≥ 150 = hart,
≥ 45 min Ausdauer / ≥ 75 min Training / Last ≥ 80 = moderat, ≥ 20 min = leicht, sonst Ruhetag.
Manuell änderbar („Tagestyp ändern“). Ziel „Abnehmen“ (−15 %) wirkt nur an Ruhe-/leichten Tagen voll,
an moderaten halb und an harten gar nicht.

## Grenzen

- **Foto-Portionen sind Schätzungen.** In einer Studie mit Standardfotos (Fridolfsson et al. 2025) lag der
  mittlere Fehler der besten Bildmodelle bei rund 36 % für Gewicht und Energie; ältere Gemini-Versionen
  lagen deutlich darüber, und große Portionen wurden von allen Modellen systematisch unterschätzt.
  Die App nimmt deshalb die Nährwerte aus Datenbanken und nur die Mengen von der KI – die Mengen bitte
  kurz prüfen. Für genaue Werte: Text mit Grammangaben, Küchenwaage oder Barcode.
- Datenbankwerte sind Durchschnittswerte; einzelne Mikronährstoffe fehlen bei manchen Produkten
  (Open Food Facts) – die App zeigt dann einen Hinweis, die Summe ist eine Untergrenze.
- Vitamin D kommt überwiegend aus der Eigensynthese (Sonne); über die Nahrung ist das DGE-Ziel kaum erreichbar.
- Keine medizinische Beratung.

## Datenschutz

Alle Daten liegen lokal in der App (`/data`, Teil der HA-Backups; die BLS-Datenbank ist ausgenommen,
sie lässt sich jederzeit neu laden). Nach außen gehen nur: Fotos/Texte zur Analyse an Google Gemini
(im kostenlosen Kontingent darf Google sie zur Produktverbesserung nutzen – Fotos werden verkleinert,
Standortdaten entfernt; Foto-Analyse in den Einstellungen abschaltbar) und Barcode-Nummern an Open Food Facts.
Export aller Einträge als CSV in den Einstellungen.

## Home Assistant

Per MQTT (Mosquitto) erscheinen das Gerät **Ernährung** und die Sensoren:

- `sensor.ernaehrung_kalorien`, `_protein`, `_kohlenhydrate`, `_fett`, `_ballaststoffe`, `_fluessigkeit`,
  `_zucker`, `_gesaettigte_fettsaeuren`, `_natrium`, `_kalium`, `_magnesium`, `_calcium`, `_eisen`, `_zink`,
  `_vitamin_d`, `_vitamin_b12`, `_vitamin_c` – Tageswert, Attribute `ziel`, `prozent`, `art`
- `sensor.ernaehrung_tag` – kcal-Fortschritt in %, Attribute: komplette Tagesauswertung
- `sensor.ernaehrung_woche` – Anzahl wiederkehrender Lücken, Attribute: 7-Tage-Auswertung
  (Durchschnitt, Trefferquote je Nährstoff, Lücken, Kohlenhydrate an harten Tagen, Protein an Trainingstagen)

REST-API im internen Netz: `GET /api/v1/day?date=YYYY-MM-DD`, `GET /api/v1/week`, `GET /api/v1/export.csv`.

## Quellen

- Max Rubner-Institut (2025): Bundeslebensmittelschlüssel (BLS), Version 4.0. Karlsruhe.
  DOI 10.25826/Data20251217-134202-0. Lizenz CC BY 4.0.
- Open Food Facts (ODbL), https://world.openfoodfacts.org
- Thomas DT, Erdman KA, Burke LM (2016): Nutrition and Athletic Performance. Med Sci Sports Exerc 48(3):543–568.
- Jäger R et al. (2017): ISSN Position Stand: Protein and Exercise. J Int Soc Sports Nutr 14:20.
- Fridolfsson J et al. (2025): Performance Evaluation of 3 Large Language Models for Nutritional Content Estimation from Food Images. Curr Dev Nutr 9(10):107556. doi:10.1016/j.cdnut.2025.107556
- Morton RW et al. (2018): Protein supplementation and resistance training. Br J Sports Med 52(6):376–384. doi:10.1136/bjsports-2017-097608
- Williamson E et al. (2023): Protein requirements are increased in endurance-trained athletes. Med Sci Sports Exerc 55(10):1866–1875. doi:10.1249/MSS.0000000000003219
- Aragon AA et al. (2026): ISSN position stand: diets for body weight reduction. J Int Soc Sports Nutr 23(1). doi:10.1080/15502783.2026.2740266
- Kerksick CM et al. (2017): ISSN position stand: nutrient timing. J Int Soc Sports Nutr 14:33. doi:10.1186/s12970-017-0189-4
- Mountjoy M et al. (2023): IOC consensus statement on REDs. Br J Sports Med 57(17):1073–1097. doi:10.1136/bjsports-2023-106994
- Impey SG et al. (2018): Fuel for the work required. Sports Med 48(5):1031–1048. doi:10.1007/s40279-018-0867-7
- O'Driscoll R et al. (2020): How well do activity monitors estimate energy expenditure? Br J Sports Med 54(6):332–340. doi:10.1136/bjsports-2018-099643
- Mifflin MD, St Jeor ST et al. (1990): A new predictive equation for resting energy expenditure. Am J Clin Nutr 51(2):241–247.
- Deutsche Gesellschaft für Ernährung: Referenzwerte für die Nährstoffzufuhr, https://www.dge.de/wissenschaft/referenzwerte/
- Barcode-Erkennung im Browser: ZXing (Apache-2.0).
