"""Start: Datenbank, BLS-Import im Hintergrund, MQTT-Veröffentlichung, Webserver."""
import datetime
import os
import threading
import time

import bls
import db
import publish
import summary
import web

PORT = int(os.environ.get("PORT", 8099))
PUBLISH_INTERVAL = int(os.environ.get("PUBLISH_INTERVAL", 600))
_pub_lock = threading.Lock()


def publish_now():
    if not _pub_lock.acquire(blocking=False):
        return
    try:
        today = datetime.date.today().isoformat()
        publish.publish(summary.day(today), summary.week(today))
    except Exception as e:
        print(f"[mqtt] Veröffentlichen fehlgeschlagen: {e}")
    finally:
        _pub_lock.release()


def publish_loop():
    try:
        if publish.discovery():
            print("[mqtt] Discovery gesendet")
        else:
            print("[mqtt] kein MQTT (Mosquitto fehlt?) - Sensoren werden nicht veröffentlicht")
            return
    except Exception as e:
        print(f"[mqtt] Discovery fehlgeschlagen: {e}")
        return
    while True:
        publish_now()
        time.sleep(PUBLISH_INTERVAL)


def main():
    db.init()
    threading.Thread(target=bls.ensure, daemon=True, name="bls").start()
    web.on_change.append(publish_now)
    threading.Thread(target=publish_loop, daemon=True, name="mqtt").start()
    from waitress import serve
    print(f"[web] Ernährung {web.VERSION} auf Port {PORT}")
    serve(web.app, host="0.0.0.0", port=PORT, threads=6, max_request_body_size=12 * 1024 * 1024)


if __name__ == "__main__":
    main()
