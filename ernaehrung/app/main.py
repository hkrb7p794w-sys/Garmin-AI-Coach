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
        publish.publish(summary.day_with_recommendations(today), summary.week(today))
    except Exception as e:
        print(f"[mqtt] Veröffentlichen fehlgeschlagen: {e}")
    finally:
        _pub_lock.release()


_bls_thread = None


def publish_loop():
    if _bls_thread is not None:
        _bls_thread.join(timeout=60)   # erst veröffentlichen, wenn der BLS geöffnet ist (sonst leere Vorschläge)
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


def _remove_photo_store():
    """Bis 0.2.x wurden Fotos unter /data/photos gespeichert - seit 0.3.0 nie mehr: löschen."""
    import shutil
    path = os.environ.get("PHOTO_DIR", "/data/photos")
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        print(f"[privacy] gespeicherte Fotos gelöscht ({path})")


def _after_bls_import():
    import recommend
    recommend.reset_cache()
    n = db.merge_missing_nutrients(lambda code: (bls.get(code) or {}).get("per100"))
    if n:
        print(f"[bls] {n} gespeicherte Lebensmittel um neue Nährstoffe ergänzt")


def main():
    db.init()
    _remove_photo_store()
    bls.after_import.append(_after_bls_import)
    global _bls_thread
    _bls_thread = threading.Thread(target=bls.ensure, daemon=True, name="bls")
    _bls_thread.start()
    web.on_change.append(publish_now)
    threading.Thread(target=publish_loop, daemon=True, name="mqtt").start()
    from waitress import serve
    print(f"[web] Ernährung {web.VERSION} auf Port {PORT}")
    serve(web.app, host="0.0.0.0", port=PORT, threads=6, max_request_body_size=12 * 1024 * 1024)


if __name__ == "__main__":
    main()
