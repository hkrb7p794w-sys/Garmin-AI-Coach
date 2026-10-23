"""Bundeslebensmittelschlüssel (BLS) 4.0 - Import und Suche.

Quelle: Max Rubner-Institut (2025): Bundeslebensmittelschlüssel (BLS), Version 4.0.
Karlsruhe. DOI 10.25826/Data20251217-134202-0. Lizenz CC BY 4.0.

Die Datei (~14 MB xlsx, 7.140 Lebensmittel, 138 Nährstoffe) wird beim ersten Start
von der offiziellen Download-Seite https://blsdb.de/download geladen (der Link dort
trägt einen wechselnden Code) und in /data/bls.db übernommen. Klappt der Download
nicht (z. B. Bot-Sperre), kann die Datei (xlsx oder zip) nach /share/ernaehrung/
gelegt werden - sie wird beim nächsten Start bzw. per Knopf in den Einstellungen
importiert. Eine Sperre wird bewusst nicht umgangen.

Spaltenaufbau laut BLS-Dokumentation: A "BLS Code", B "Lebensmittelbezeichnung",
C "Food name", danach je Nährstoff drei Spalten: "CODE Bezeichnung [Einheit/100g]",
"CODE Datenherkunft", "CODE Referenz". Fehlende Werte ("-") sind NICHT 0; "TR"
(Spuren) und "<LOD"/"<LOQ" werden als 0 gezählt.
"""
import csv
import io
import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
import zipfile

import requests

from nutrients import BLS_CODES, KEYS, convert

BLS_DB = os.environ.get("BLS_DB", "/data/bls.db")
SHARE_DIR = os.environ.get("NUTRITION_SHARE", "/share/ernaehrung")
DOWNLOAD_PAGE = "https://blsdb.de/download"
USER_AGENT = "ErnaehrungHA/0.1 (Home-Assistant-Add-on, privat)"
ATTRIBUTION = ("Max Rubner-Institut (2025): Bundeslebensmittelschlüssel (BLS), Version 4.0. "
               "Karlsruhe. DOI 10.25826/Data20251217-134202-0. Lizenz CC BY 4.0.")

_HEADER_RE = re.compile(r"^([A-Z0-9:]+)\s.*\[([^\]/]+)/100\s*g\]\s*$")
_CHALLENGE_RE = re.compile(r"pow-challenge|captcha|cf-chl|just a moment|type=[\"']?password", re.I)

_lock = threading.Lock()
after_import = []   # Callbacks (z. B. gespeicherte BLS-Lebensmittel um neue Nährstoffe ergänzen)
_index = []          # [(code, name, norm_name, per100, is_liquid)]
status = {"state": "leer", "count": 0, "message": "", "updated": None}
# Bei neuen Nährstoffen erhöhen: dann wird der BLS beim Start neu importiert.
SCHEMA = 2


# --------------------------------------------------------------------------
# Normalisierung / Suche
# --------------------------------------------------------------------------

STOPWORDS = {"mit", "und", "der", "die", "das", "ein", "eine", "einem", "einer", "vom", "von", "aus",
             "auf", "zum", "zur", "dem", "den", "des", "ca", "etwa", "stück", "portion"}


def norm(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))  # ä -> a usw.
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


SYNONYMS = {"ei": "huhnerei", "eier": "huhnerei", "ruhreier": "ruhrei", "spiegeleier": "spiegelei",
            "nudeln": "teigwaren", "nudel": "teigwaren", "pasta": "teigwaren", "mohre": "karotte",
            "mohren": "karotte", "kartoffeln": "kartoffel", "haferflocken": "hafer flocken"}
# Zusätze, die ein anderes Lebensmittel bedeuten, wenn sie nicht gesucht wurden
STRONG_EXTRAS = {"alkohol", "zucker", "gezuckert", "gesusst", "honig", "schokolade", "sahne",
                 "kondensmilch", "salz", "gesalzen", "panade", "paniert", "frittiert", "kase", "speck",
                 "pulver", "getrocknet", "konserve", "sirup", "likor"}
# Zubereitungs-/Zustandswörter zählen weniger als das eigentliche Lebensmittel
STATE_WORDS = {"roh", "gekocht", "gegart", "gebraten", "gedunstet", "gedampft", "gebacken", "frisch",
               "getrocknet", "konserve", "abgetropft", "tiefgefroren", "gegrillt", "geschalt",
               "ungesalzen", "gesalzen", "pasteurisiert", "zubereitet"}


def _terms(query: str):
    out = []
    for w in norm(query).split():
        w = SYNONYMS.get(w, w)
        for part in w.split():
            if len(part) < 3 or part in STOPWORDS:
                continue
            # einfache Pluralformen: "bananen" -> "banane", "kartoffeln" -> "kartoffel"
            if len(part) > 5 and part.endswith("n") and not part.endswith("en"):
                part = part[:-1]
            if part not in out:
                out.append(part)
    # Lebensmittelwörter vor Zustandswörter
    return [t for t in out if t not in STATE_WORDS] + [t for t in out if t in STATE_WORDS]


def _variants(t: str):
    """Singular-/Pluralvarianten: "linsen" ~ "linse", "bohnen" ~ "bohne", "eier" ~ "ei"."""
    out = []
    if len(t) > 4 and t.endswith("n"):
        out.append(t[:-1])
    if len(t) > 5 and t.endswith(("en", "er")):
        out.append(t[:-2])
    if len(t) > 3 and t.endswith("s"):
        out.append(t[:-1])
    return out


def score_name(terms, name_norm: str, code: str = "") -> float:
    if not terms:
        return 0.0
    words = name_norm.split()
    compact = name_norm.replace(" ", "")  # "Hafer Flocken" ~ "Haferflocken"
    hits = weight_sum = 0.0
    food_hit = False
    for i, t in enumerate(terms):
        w = 0.4 if t in STATE_WORDS else (1.2 if i == 0 else 1.0)
        weight_sum += w
        variants = _variants(t)
        if t in words or any(v in words for v in variants):
            h = w
        elif t in name_norm:
            h = w * 0.8
        elif t in compact:
            h = w * 0.7
        elif len(t) > 6 and t[:-2] in name_norm:  # Flexion ("gekochte" ~ "gekocht")
            h = w * 0.45
        else:
            h = 0.0
        if h and t not in STATE_WORDS:
            food_hit = True
        hits += h
        # Gegenteiliger Zustand ("roh" gesucht, "gekocht" gefunden) leicht abwerten
    if not food_hit:
        return 0.0
    coverage = hits / weight_sum
    first_bonus = 0.15 if words and terms[0] in words[0] else 0.0
    # Zusätzliche Inhaltswörter im Treffer, die nicht gesucht wurden ("Kaffee mit Alkohol")
    extra = 0.0
    for w in set(words):
        if len(w) < 4 or w in STOPWORDS or w in STATE_WORDS or any(t in w or w in t for t in terms):
            continue
        extra += 0.12 if w in STRONG_EXTRAS else 0.04
    # Zusammengesetzte Gerichte (X/Y) und Backwaren (D) nach hinten, wenn nicht ausdrücklich
    # gesucht - "Quark" soll Speisequark finden, nicht "Quark-Mokka-Creme".
    dish = 0.18 if code[:1] in ("X", "Y") else (0.1 if code[:1] == "D" else 0.0)
    return coverage + first_bonus - min(extra, 0.3) - dish


def search(query: str, limit: int = 20):
    """Volltextsuche im BLS (Teilwort-Treffer für deutsche Komposita)."""
    terms = _terms(query)
    if not terms:
        return []
    scored = []
    with _lock:
        for code, name, nn, per100, liquid in _index:
            s = score_name(terms, nn, code)
            if s > 0.3:
                scored.append((s, code, name, per100, liquid))
    scored.sort(key=lambda x: -x[0])
    return [{"code": c, "name": n, "per100": p, "is_liquid": liq, "score": round(s, 3)}
            for s, c, n, p, liq in scored[:limit]]


def get(code: str):
    with _lock:
        for c, name, _nn, per100, liquid in _index:
            if c == code:
                return {"code": c, "name": name, "per100": per100, "is_liquid": liquid}
    return None


def index_rows():
    with _lock:
        return list(_index)


def count() -> int:
    return len(_index)


# --------------------------------------------------------------------------
# Parsen
# --------------------------------------------------------------------------

def parse_value(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "-", "–", "n.a.", "NA"):
        return None
    if s.upper() in ("TR", "SPUREN") or s.upper().startswith("<LO"):
        return 0.0
    s = s.replace(" ", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def column_map(header):
    """Spaltenindex -> (kanonischer Schlüssel, Einheit) anhand der Kopfzeile."""
    cols = {}
    idx_code = idx_name = idx_en = None
    for i, h in enumerate(header):
        h = (str(h) if h is not None else "").strip()
        if h == "BLS Code":
            idx_code = i
        elif h == "Lebensmittelbezeichnung":
            idx_name = i
        elif h == "Food name":
            idx_en = i
        m = _HEADER_RE.match(h)
        if m and m.group(1) in BLS_CODES:
            key, target_unit = BLS_CODES[m.group(1)]
            cols[i] = (key, m.group(2).strip(), target_unit)
    if idx_code is None or idx_name is None:
        raise ValueError("Kopfzeile ohne 'BLS Code'/'Lebensmittelbezeichnung' - unbekanntes Format")
    missing = set(k for k, _ in BLS_CODES.values()) - set(v[0] for v in cols.values())
    return idx_code, idx_name, idx_en, cols, missing


def is_liquid_code(code: str, name: str) -> bool:
    n = norm(name)
    if code.startswith("N"):  # Getränke
        return True
    return any(w in n.split() for w in ("milch", "saft", "smoothie", "kefir", "buttermilch", "drink")) \
        and "pulver" not in n


def rows_to_records(rows):
    """Iterator über Zeilen (erste = Kopf) -> Liste von Datensätzen."""
    it = iter(rows)
    header = next(it)
    idx_code, idx_name, idx_en, cols, missing = column_map(header)
    records = []
    for row in it:
        if not row or idx_code >= len(row) or not row[idx_code]:
            continue
        code = str(row[idx_code]).strip()
        name = str(row[idx_name]).strip() if row[idx_name] else code
        per100 = {k: None for k in KEYS}
        for i, (key, unit, target_unit) in cols.items():
            if i < len(row):
                v = parse_value(row[i])
                if v is None:
                    continue
                v = convert(v, unit, target_unit)
                if v is None:
                    continue
                # mehrere Codes je Schlüssel (EPA + DHA) addieren
                per100[key] = round((per100[key] or 0) + v, 6)
        records.append({
            "code": code,
            "name": name,
            "name_en": (str(row[idx_en]).strip() if idx_en is not None and idx_en < len(row) and row[idx_en] else ""),
            "per100": per100,
            "is_liquid": is_liquid_code(code, name),
        })
    return records, missing


def read_file(path: str):
    """xlsx, csv oder zip (mit xlsx/csv darin) einlesen."""
    lower = path.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv"))
                     and "daten" in n.lower()] or \
                    [n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv"))]
            if not names:
                raise ValueError("ZIP enthält keine xlsx/csv-Datei")
            data = z.read(names[0])
            return _read_bytes(names[0], data)
    with open(path, "rb") as f:
        return _read_bytes(path, f.read())


def _read_bytes(name: str, data: bytes):
    if name.lower().endswith(".csv"):
        text = data.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t")
        return rows_to_records(csv.reader(io.StringIO(text), dialect))
    import openpyxl  # nur bei Bedarf laden (Speicher auf dem Pi)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    best = None
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        try:
            first = next(rows)
        except StopIteration:
            continue
        if first and "BLS Code" in [str(c).strip() if c is not None else "" for c in first]:
            best = (first, rows)
            break
    if best is None:
        raise ValueError("Kein Tabellenblatt mit Spalte 'BLS Code' gefunden")
    first, rows = best

    def all_rows():
        yield first
        yield from rows
    return rows_to_records(all_rows())


# --------------------------------------------------------------------------
# Speicher (bls.db) und Index
# --------------------------------------------------------------------------

def _db():
    c = sqlite3.connect(BLS_DB, timeout=15)
    c.execute("CREATE TABLE IF NOT EXISTS bls (code TEXT PRIMARY KEY, name TEXT, name_en TEXT, "
              "per100 TEXT, is_liquid INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    return c


def store(records, origin: str):
    c = _db()
    with c:
        c.execute("DELETE FROM bls")
        c.executemany("INSERT INTO bls VALUES(?,?,?,?,?)",
                      [(r["code"], r["name"], r["name_en"], json.dumps(r["per100"]), int(r["is_liquid"]))
                       for r in records])
        c.execute("INSERT OR REPLACE INTO meta VALUES('origin', ?)", (origin,))
        c.execute("INSERT OR REPLACE INTO meta VALUES('schema', ?)", (str(SCHEMA),))
        c.execute("INSERT OR REPLACE INTO meta VALUES('imported_at', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
    c.close()


def load_index() -> int:
    global _index
    if not os.path.exists(BLS_DB):
        return 0
    c = _db()
    rows = c.execute("SELECT code, name, per100, is_liquid FROM bls").fetchall()
    meta = dict(c.execute("SELECT key, value FROM meta").fetchall())
    c.close()
    idx = [(code, name, norm(name), json.loads(p), bool(liq)) for code, name, p, liq in rows]
    with _lock:
        _index = idx
    status.update(state="bereit" if idx else "leer", count=len(idx),
                  updated=meta.get("imported_at"), origin=meta.get("origin"),
                  schema=int(meta.get("schema") or 1))
    return len(idx)


def import_file(path: str) -> int:
    records, missing = read_file(path)
    if len(records) < 50:
        raise ValueError(f"Nur {len(records)} Zeilen gefunden - Datei unvollständig?")
    store(records, os.path.basename(path))
    n = load_index()
    msg = f"{n} Lebensmittel aus {os.path.basename(path)} importiert"
    if missing:
        msg += f" (Spalten fehlen: {', '.join(sorted(missing))})"
    status.update(message=msg)
    print(f"[bls] {msg}")
    for cb in after_import:
        try:
            cb()
        except Exception as e:
            print(f"[bls] Nacharbeit nach Import fehlgeschlagen: {e}")
    return n


# --------------------------------------------------------------------------
# Download von blsdb.de
# --------------------------------------------------------------------------

def find_download_link(html: str, page_url: str = DOWNLOAD_PAGE):
    """Download-Link (zip/xlsx der BLS-Daten) auf derselben Domain finden.

    Durchsucht href-Attribute und auch Weiterleitungen in Meta-Refresh/JavaScript
    (window.location = '...')."""
    from urllib.parse import urljoin, urlparse
    import html as htmllib
    host = urlparse(page_url).netloc
    html = htmllib.unescape(html)  # blsdb.de kodiert Links als Entities (&#47; usw.)
    raw = re.findall(r"""href\s*=\s*["']([^"']+)["']""", html, re.I)
    raw += re.findall(r"""["'(=]\s*((?:https?://[^"'\s]+)?/[^"'\s<>]*BLS[^"'\s<>]*\.(?:zip|xlsx)[^"'\s<>]*)""", html, re.I)
    links = set()
    for href in raw:
        url = urljoin(page_url, href.strip())
        u = urlparse(url)
        if u.scheme == "https" and u.netloc == host and \
                re.search(r"/BLS[^/]*\.(zip|xlsx)$", u.path, re.I) and "doku" not in u.path.lower():
            links.add(url)
    # Datendatei bevorzugen (es gibt auch Doku-Links)
    ranked = sorted(links, key=lambda x: (0 if "daten" in x.lower() or x.lower().split("?")[0].endswith(".zip") else 1, x))
    return ranked[0] if ranked else None


def _mask(text: str) -> str:
    return re.sub(r"(=[A-Za-z0-9]{4})[A-Za-z0-9-]+", lambda m: m.group(1) + "…", text)


def _diagnose(html: str, url: str) -> str:
    """Kurzbeschreibung der Seite fürs Log (Codes gekürzt)."""
    import html as htmllib
    html = htmllib.unescape(html)
    title = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    hrefs = re.findall(r"""href\s*=\s*["']([^"']+)["']""", html, re.I)
    interesting = [_mask(h) for h in hrefs if re.search(r"bls|download|upload|files|\.zip|\.xlsx", h, re.I)]
    title_text = (title.group(1).strip() if title else "-")[:60]
    return (f"URL {_mask(url)}, Titel '{title_text}', {len(hrefs)} Links, "
            f"relevant: {interesting[:12]}, {len(html)} Zeichen")


def download(target_dir: str) -> str:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    r = s.get(DOWNLOAD_PAGE, timeout=60)
    r.raise_for_status()
    if _CHALLENGE_RE.search(r.text) or _CHALLENGE_RE.search(r.url):
        raise RuntimeError("blsdb.de zeigt eine Bot-Sperre/Anmeldung - wird bewusst nicht umgangen")
    link = find_download_link(r.text, r.url)
    if not link:
        print(f"[bls] Download-Seite: {_diagnose(r.text, r.url)}")
        raise RuntimeError("Kein Download-Link auf blsdb.de/download gefunden")
    f = s.get(link, timeout=300, stream=True)
    f.raise_for_status()
    ctype = f.headers.get("content-type", "")
    if "html" in ctype:
        raise RuntimeError("Download liefert eine HTML-Seite statt der Datei (Sperre?)")
    name = link.split("?")[0].rsplit("/", 1)[-1] or "bls.zip"
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, name)
    with open(path, "wb") as out:
        for chunk in f.iter_content(1 << 16):
            out.write(chunk)
    print(f"[bls] Datei geladen: {name} ({os.path.getsize(path) // 1024} KB)")
    return path


def local_candidates():
    if not os.path.isdir(SHARE_DIR):
        return []
    files = [os.path.join(SHARE_DIR, f) for f in os.listdir(SHARE_DIR)
             if f.lower().startswith("bls") and f.lower().endswith((".zip", ".xlsx", ".csv"))]
    return sorted(files, key=os.path.getmtime, reverse=True)


def ensure(auto_download: bool = True, force: bool = False):
    """Beim Start: vorhandenen Index laden, sonst importieren (lokale Datei vor Download)."""
    if not force and load_index() > 1000 and status.get("schema") == SCHEMA:
        return
    status.update(state="import", message="BLS wird importiert …")
    try:
        files = local_candidates()
        if files:
            import_file(files[0])
            return
        if not auto_download:
            status.update(state="leer", message="Keine BLS-Datei in /share/ernaehrung gefunden")
            return
        path = download("/data/bls_download")
        import_file(path)
        try:
            os.remove(path)  # 14 MB nicht doppelt aufheben
        except OSError:
            pass
    except Exception as e:  # App läuft ohne BLS weiter (OFF + KI-Schätzung)
        status.update(state="fehler" if not _index else "bereit",
                      message=f"BLS-Import fehlgeschlagen: {e}. Datei manuell nach /share/ernaehrung/ legen.")
        print(f"[bls] {status['message']}")
