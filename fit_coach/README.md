# Fit Coach

Eigene Home-Assistant-App für ein persönliches Fitness-Dashboard: **Garmin** (Laufen, Gym, Schritte, Gewicht)
und optional **Yazio** (Kalorien, Eiweiß) – mit Lauf-Pace-Verlauf, Gym-Rekorden, Abnehm-Trend, Wochenzielen und Erfolgen.

- Anmeldung direkt in der App (Seitenleiste „Fit Coach“), auch mit Garmin-Zwei-Faktor-Code. Passwörter werden nicht gespeichert.
- Alle Werte als Home-Assistant-Sensoren (`sensor.fit_coach_*`) und Eingaben (`number.`/`select.`/`button.fit_coach_*`) über MQTT.
- Passendes Dashboard „Fit“ mit eigenen Karten (`/local/fit/fit-cards.js`).
- Keine KI, keine Weitergabe: Regeln mit Quellenangabe statt Ratespiel.

Unabhängig vom „Garmin AI Coach“ im selben Repository – beide können parallel laufen (eigene Konten, eigene Daten).
Details: Reiter „Dokumentation“.
