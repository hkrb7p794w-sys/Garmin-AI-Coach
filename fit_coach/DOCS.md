# Fit Coach – Dokumentation

## Einrichten (einmalig, ca. 3 Minuten)

1. **App starten.** Nach der Installation auf „Starten“ tippen. „Beim Booten starten“ und „Watchdog“ dürfen an bleiben.
   Voraussetzung: Die App **Mosquitto broker** läuft (ist für den Garmin AI Coach ohnehin installiert).
2. **Anmelden.** In der Seitenleiste **Fit Coach** öffnen (sichtbar auch für Nicht-Admins):
   - **Garmin:** E-Mail und Passwort wie in der Garmin-Connect-App. Ist die Zwei-Faktor-Anmeldung aktiv, erscheint danach ein Feld
     für den Code aus der E-Mail bzw. Authenticator-App.
   - **Yazio (optional):** E-Mail und **Yazio-Passwort**. Konten, die nur über „Mit Apple/Google anmelden“ laufen, haben kein
     Yazio-Passwort – dann einfach weglassen; Gewicht kann im Dashboard eingetragen werden.
3. **Fertig.** Der erste Abruf läuft sofort und holt auch die letzten Wochen nach (Aktivitäten, 120 Tage Gewicht, 4 Wochen Essen).
   Danach automatisch um 6, 12 und 20 Uhr (Option „Abrufzeiten“).
4. **Dashboard „Fit“** in der Seitenleiste öffnen. Tipp: In der Companion-App unter Profil › Dashboard „Fit“ als Standard wählen.

Passwörter werden nie gespeichert – nur die Anmelde-Tokens (`/data`, nur für die App lesbar). Garmin-Tokens erneuern sich selbst;
neu anmelden ist nur nötig, wenn das Dashboard „bitte neu anmelden“ zeigt (z. B. nach einer Passwortänderung).

## Was wird angezeigt?

| Bereich | Inhalt | Quelle |
|---|---|---|
| Heute | Bewegung der Woche, Schritte, Kalorien, Gewichtstrend, nächster Lauf, Tipps | Garmin, Yazio |
| Laufen | Läufe/km der Woche, lockere Pace + Verlauf, Meter pro Herzschlag, Bestzeiten, 5-km-Prognose, VO2max, km pro Woche | Garmin |
| Gewicht | Trend, 7/30-Tage-Änderung, Tempo, Weg zum Ziel, Eingabe | Garmin-Waage/App, Yazio, eigene Eingabe |
| Essen | Kalorien und Makros heute, 14 Tage, Ø vollständig erfasster Tage, Eiweiß-Richtwert, geschätzter echter Verbrauch | Yazio |
| Gym | Rekorde je Übung (bester Satz, e1RM), Steigerungshinweise, eigene Rekord-Eingabe | Garmin-Krafttraining, Eingabe |
| Erfolge | 36 Abzeichen in 5 Gruppen | alle |

Zielgewicht: Dashboard-Einstellung (wenn > 0) vor Yazio-Ziel vor Garmin-Ziel.
Gewicht pro Tag: eigene Eingabe vor Garmin vor Yazio.

## Wie gerechnet wird (mit Quellen)

- **Gewichtstrend:** exponentiell geglättet (10 %/Tag), Tempo per linearer Regression der letzten 28 Tage (mind. 5 Messungen über 14 Tage).
  Zielkorridor 0,5–1 % pro Woche – bei ~0,7 % blieb mehr Muskelmasse erhalten als bei ~1,4 %
  (Garthe 2011, doi:10.1123/ijsnem.21.2.97). Regelmäßiges Wiegen: Zheng 2015, doi:10.1002/oby.20946.
- **Echter Verbrauch:** Ø Aufnahme vollständiger Tage − Trendänderung × 7.700 kcal/kg ÷ Tage (ab 10 vollständigen Tagen).
  Uhren schätzen den Verbrauch ungenau (Shcherbina 2017, doi:10.3390/jpm7020003); die Hochrechnung bleibt eine Schätzung
  (Thomas 2013, doi:10.1038/ijo.2013.51).
- **Vollständiger Tag:** mindestens 3 Mahlzeiten oder die Hälfte des Kalorienziels eingetragen.
- **Eiweiß:** 1,2–1,6 g pro kg Zielgewicht (Cava 2017, doi:10.3945/an.116.014506; Morton 2018, doi:10.1136/bjsports-2017-097608).
- **Hinweis „genug essen“:** Ø unter 1.200 kcal an ≥ 4 vollständigen Tagen (Jensen 2014, doi:10.1161/01.cir.0000437739.71477.ee;
  IOC REDs 2023, doi:10.1136/bjsports-2023-106994).
- **Lockere Pace:** Median der Läufe mit ≥ 70 % Zeit in Garmin-Zone 1–2, letzte 4 Wochen vs. 4 Wochen davor.
  Ziel ≈ 80 % locker (Muñoz 2014, doi:10.1123/ijspp.2012-0350).
- **Umfangs-Hinweis:** diese Woche > 1,3 × Ø der beiden Vorwochen (Nielsen 2014, doi:10.2519/jospt.2014.5164);
  bewusst nicht die 10-%-Regel (Buist 2008, doi:10.1177/0363546507307505).
- **Nächster Lauf:** ein geplantes Garmin-Workout (z. B. Garmin Coach, kostenlos in Garmin Connect › Training) hat Vorrang,
  sonst einfache Regeln (Lauf-Geh-Einheiten am Anfang, kein Lauf an zwei Tagen hintereinander, am Wochenende etwas länger).
- **Gym:** Rekord = bester Satz nach e1RM (Epley, bis 12 Wdh.). Steigerung per doppelter Progression in 8–12 Wdh.
  (Isolation 10–15), Laststeigerung 2–10 % (ACSM 2009, doi:10.1249/MSS.0b013e3181915670).
  Die aktualisierte ACSM-Übersicht nennt für mehr Kraft ≥ 2 Einheiten/Woche mit 2–3 Sätzen (Currier 2026, doi:10.1249/MSS.0000000000003897);
  das Standardziel „1× Gym pro Woche“ ist bewusst ein niedriger Einstieg und im Dashboard änderbar.
  Eigene Zuordnungen von Garmin-Übungsnamen: `/share/fit_coach/exercise_aliases.json` (Format wie beim Garmin AI Coach).
- **Woche:** Wochenziel = geplante Läufe und Gym-Einheiten; Bewegungsziel = 150 min (WHO 2020, doi:10.1136/bjsports-2020-102955).
  Die Serie zählt Wochen, in denen eins von beidem erreicht ist.

Keine medizinische Beratung. Bei Beschwerden, Vorerkrankungen oder in der Schwangerschaft ärztlich abklären.

## Entitäten

Sensoren: `sensor.fit_coach_status`, `_heute`, `_woche`, `_serie`, `_abnahme`, `_gewicht`, `_gewicht_trend`, `_ernaehrung`,
`_kalorien`, `_kalorien_ziel`, `_protein`, `_laufen`, `_lauf_km_woche`, `_pace_locker`, `_prognose_5k`, `_vo2max`, `_gym`,
`_schritte`, `_aktiv_kcal`, `_erfolge`, `_tipp`, `_plan`, `_letzter_sync`.

Eingaben: `number.fit_coach_zielgewicht`, `_gewicht_eintragen`, `_ziel_laeufe`, `_ziel_gym`, `_rekord_kg`, `_rekord_wdh`,
`select.fit_coach_uebung`, `button.fit_coach_sync`, `_rekord_speichern`, `_rekord_rueckgaengig`, `_gewicht_rueckgaengig`.

## Fehlersuche

- **„Garmin blockt gerade zu viele Anmeldeversuche“:** 15–30 Minuten warten, dann erneut anmelden.
- **Dashboard zeigt „App noch nicht installiert“:** App läuft nicht oder Mosquitto fehlt – Protokoll der App prüfen.
- **Keine Gym-Rekorde trotz Krafttraining:** Garmin speichert Übungen nur, wenn sie auf der Uhr erkannt oder in Garmin Connect
  › Aktivität › Übungen eingetragen wurden (mit Gewicht).
- **Yazio „Hinweis“:** Die Schnittstelle ist inoffiziell; ändert Yazio sie, bleibt der Rest des Dashboards funktionsfähig.
