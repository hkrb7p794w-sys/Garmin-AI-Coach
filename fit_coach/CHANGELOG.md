# Changelog

## 0.1.2 – 19.10.2026
- Yazio-Anmeldung repariert: Yazio hat die App-Anmeldung umgestellt (Token jetzt über API v22, neuer OAuth-Client der aktuellen App, fremde User-Agents werden mit leerem HTTP 400 abgewiesen). Fit Coach meldet sich jetzt wie die aktuelle Yazio-App an; Abfragen laufen weiter über v20. Der alte Client bleibt als Rückfall.
- Bereits gespeicherte Yazio-Tokens des alten Clients führen zu „bitte neu anmelden“ statt zu Dauerfehlern.

## 0.1.1 – 19.10.2026
- Yazio-Anmeldung: erste Variante jetzt exakt wie das gepflegte Projekt juriadams/yazio; jede Antwort von Yazio steht im Protokoll der App (ohne Passwort), und die Fehlermeldung nennt Yazios eigenen Grund statt nur „HTTP 400“.

## 0.1.0 – 18.10.2026
- Erste Fassung: Garmin-Anmeldung mit Zwei-Faktor-Code, optionale Yazio-Verbindung (inoffizielle API v20/v15).
- Gewicht: Quellen Garmin/Yazio/eigene Eingabe, geglätteter Trend, Tempo im Korridor 0,5–1 %/Woche, Ziel-Fortschritt.
- Essen: Tageswerte, 7-Tage-Schnitt vollständiger Tage, Eiweiß-Richtwert, geschätzter echter Verbrauch.
- Laufen: lockere Pace und Meter pro Herzschlag, Wochenkilometer, Bestzeiten, Garmin-Prognose/VO2max, Hinweise bei Umfangssprüngen.
- Gym: Rekorde (e1RM) aus Garmin-Übungen und eigenen Einträgen, Steigerungshinweise (8–12 Wdh.).
- Wochenziele, Wochenserie, 36 Abzeichen, Tipps mit Quellen.
