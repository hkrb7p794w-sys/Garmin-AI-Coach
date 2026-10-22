# Ernährung – Home-Assistant-Add-on

Ernährungs-Tracking per Foto, Text oder Barcode, mit Makro- und Mikronährstoffen und Tageszielen,
die sich nach dem Garmin-Training richten. Läuft lokal auf Home Assistant OS (aarch64/amd64),
Bedienung als Web-App über die HA-Seitenleiste.

## Installation

Liegt im selben Add-on-Repository wie der Garmin AI Coach (`https://github.com/hkrb7p794w-sys/Garmin-AI-Coach`) –
im Add-on-Store „Ernährung“ installieren. Details: [DOCS.md](DOCS.md).

## Architektur

```
iPhone (HA-App) ── Ingress ──► Flask/Waitress (Port 8099)
                                 ├─ SQLite /data/ernaehrung.db   Mahlzeiten, Lebensmittel, Favoriten, Ziele
                                 ├─ SQLite /data/bls.db           BLS 4.0 (7.140 Lebensmittel)
                                 ├─ Gemini (Foto/Text → Positionen + Schätzung) → Abgleich mit BLS/OFF
                                 ├─ Open Food Facts (Barcode, lokal zwischengespeichert)
                                 ├─ HA-API: sensor.garmin_ai_coach_garmin_energie_heute (Training, Körperdaten)
                                 └─ MQTT Discovery → sensor.ernaehrung_* (Tag, Woche, je Nährstoff)
```

## Entwicklung

```
pip install flask waitress requests paho-mqtt openpyxl pytest
python -m pytest tests
NUTRITION_DB=/tmp/e.db BLS_DB=/tmp/bls.db RESTRICT_IPS=0 python app/main.py   # http://localhost:8099
```

Testdaten: Auszug aus dem BLS 4.0 (178 Lebensmittel, CC BY 4.0, Max Rubner-Institut).
