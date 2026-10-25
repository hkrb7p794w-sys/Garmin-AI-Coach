#!/usr/bin/env python3
"""Garmin-Login-Tokens auf diesem Rechner erzeugen und als eine JSON-Zeile ausgeben.

Gedacht für den Fall, dass Garmin die IP des Home-Assistant-Servers für Passwort-Logins sperrt
(HTTP 429/403). Auf einem Rechner in einem anderen Netz (z. B. per Handy-Hotspot) ausführen,
die Ausgabe in der Add-on-Ansicht unter „Login-Tokens von einem anderen Rechner einfügen“ einfügen.

    pip install "garminconnect==0.3.20"
    python3 garmin_token_export.py

Die Ausgabe enthält ein Refresh-Token mit vollem Kontozugriff - wie ein Passwort behandeln und
nach dem Einfügen aus Terminal-Verlauf und Zwischenablage löschen.
"""
import getpass
import json
import os
import tempfile

from garminconnect import Garmin


def main():
    email = input("Garmin-E-Mail: ").strip()
    password = getpass.getpass("Passwort: ")
    store = tempfile.mkdtemp(prefix="garmin_tokens_")
    api = Garmin(email, password, prompt_mfa=lambda: input("MFA-Code (E-Mail/App): ").strip())
    api.login(store)
    path = os.path.join(store, "garmin_tokens.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    os.remove(path)
    os.rmdir(store)
    print("\nTokens (komplette Zeile kopieren):\n")
    print(json.dumps({k: data[k] for k in ("di_token", "di_refresh_token", "di_client_id")}))


if __name__ == "__main__":
    main()
