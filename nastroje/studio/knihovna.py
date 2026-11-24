"""Knihovna stylů v počítači zákaznice (Marcela 20. 11. 2026). Jen standardní knihovna.

Dřív byla knihovna stránka na claude.ai (artefakt Marcely). Výběr se k Claudovi zákaznice nedostal, protože
databáze artefaktu patří účtu Marcely (testerka 1, bod 4), a stránka se otevírala mimo chat (bod 3).
Teď je stejná stránka součástí pluginu (nastroje/knihovna/index.html) a tenhle server ji ukazuje jen na tomhle
počítači (127.0.0.1). Celá cesta bez mezikroku:

  1. Claude spustí krok `knihovna --reel <složka>` na pozadí. Server vypíše STATUS knihovna READY <adresa>
     a otevře stránku (ve výchozím prohlížeči, nebo ji Claude otevře vedle chatu).
  2. Zákaznice vybírá. Průběžný výběr a „Moje styly“ se ukládají do <Reely>/NASTAVENI/knihovna/ (přežijí
     aktualizaci i jiný prohlížeč; dřív localStorage a databáze artefaktu).
  3. Tlačítko „Uložit výběr pro tenhle reel“ pošle záznam {…, kod, ulozeno}. Server ho bezpečně zapíše do
     <reel>/PRACOVNI/knihovna/pro-reel.json (dočasný soubor + výměna) a hned spustí krok styl --z-knihovny
     (stejný, který dřív Claude spouštěl ručně, s testy v test_styl.py). Vypíše jeho výsledek.
  4. Server skončí. Claude dostane upozornění, že příkaz skončil, přečte výstup a pokračuje plánem a vzhledem.
     Zákaznice do chatu nic psát nemusí.
Když stránku zavře bez uložení, server skončí za 30 s a vypíše to. Nejdéle běží 2 hodiny.
Ukázková videa (asi 24 MB) jsou ve složce studia (stáhne je příprava, start.py), ne v pluginu.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import projekt
from .cesty import PISMA

STRANKA = Path(__file__).resolve().parents[1] / "knihovna" / "index.html"
PORT = 4848
LIMIT_S = 2 * 3600
PO_ZAVRENI_S = 30
TYPY = {".html": "text/html; charset=utf-8", ".ttf": "font/ttf", ".mp4": "video/mp4", ".jpg": "image/jpeg",
        ".json": "application/json"}
JMENO = re.compile(r"^data/users/me/([a-z0-9-]{1,40})$")


def zapis_bezpecne(cil, data):
    """Dočasný soubor ve stejné složce, pak výměna: nikdo nepřečte napůl zapsaný soubor."""
    cil = Path(cil)
    cil.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(cil.parent), prefix="." + cil.stem + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cil)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, reel, ukazky, port):
        try:
            super().__init__(("127.0.0.1", port), Handler)
        except OSError:                         # port obsazený: jakýkoli volný
            super().__init__(("127.0.0.1", 0), Handler)
        self.reel = Path(reel)
        s = projekt.slozky(self.reel)
        self.pracovni = s["pracovni"]
        self.nastaveni = s["reely"] / "NASTAVENI" / "knihovna"
        self.ukazky = Path(ukazky) if ukazky else None
        self.vysledek = None                    # (ok, text) po uložení
        self.konec = threading.Event()
        self.zavreno_v = None
        self.zamek = threading.Lock()

    def soubor_zaznamu(self, jmeno):
        if jmeno == "pro-reel":
            return self.pracovni / "knihovna" / "pro-reel.json"
        return self.nastaveni / (jmeno + ".json")

    def pouzij_styl(self, soubor):
        """Krok styl --z-knihovny ve stejném Pythonu. Vrátí (ok, výstup)."""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        p = subprocess.run([sys.executable, "-m", "studio", "styl", "--reel", str(self.reel), "--z-knihovny", str(soubor)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        return p.returncode == 0, (p.stdout + p.stderr).strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "ReelStudioKnihovna/1"

    def log_message(self, *a):                  # tichý server: výstup čte Claude
        pass

    def _posli(self, kod, telo, typ="application/json; charset=utf-8", hlavicky=None):
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (hlavicky or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(telo)

    def _json(self, kod, data):
        self._posli(kod, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _jen_mistni(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._posli(403, b"jen tento pocitac", "text/plain")
            return False
        self.server.zavreno_v = None            # stránka žije
        return True

    def _soubor(self, cesta):
        """Statický soubor s podporou Range (přehrávání videa v Safari a přetáčení)."""
        if not cesta.is_file():
            self._posli(404, b"neni", "text/plain")
            return
        data = cesta.read_bytes()
        typ = TYPY.get(cesta.suffix.lower(), "application/octet-stream")
        rozsah = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)$", rozsah or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                od = int(m.group(1))
                do = int(m.group(2)) if m.group(2) else len(data) - 1
            else:
                od, do = max(0, len(data) - int(m.group(2))), len(data) - 1
            do = min(do, len(data) - 1)
            if od > do:
                self._posli(416, b"", typ, {"Content-Range": "bytes */%d" % len(data)})
                return
            self._posli(206, data[od:do + 1], typ, {"Content-Range": "bytes %d-%d/%d" % (od, do, len(data)),
                                                     "Accept-Ranges": "bytes"})
            return
        self._posli(200, data, typ, {"Accept-Ranges": "bytes"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._jen_mistni():
            return
        u = urlparse(self.path)
        cesta = unquote(u.path)
        if cesta in ("/", "/index.html"):
            self._soubor(STRANKA)
        elif cesta.startswith("/pisma/"):
            self._soubor(PISMA / Path(cesta).name)
        elif cesta.startswith("/video/"):
            if self.server.ukazky is None:
                self._posli(404, b"ukazky nejsou stazene", "text/plain")
            else:
                self._soubor(self.server.ukazky / Path(cesta).name)
        elif cesta == "/db":
            m = JMENO.match((parse_qs(u.query).get("p") or [""])[0])
            if not m:
                self._json(400, {"chyba": "neznámý záznam"})
                return
            soubor = self.server.soubor_zaznamu(m.group(1))
            try:
                self._json(200, json.loads(soubor.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                self._json(200, None)
        else:
            self._posli(404, b"neni", "text/plain")

    def do_POST(self):
        if not self._jen_mistni():
            return
        u = urlparse(self.path)
        delka = int(self.headers.get("Content-Length") or 0)
        if delka > 2 * 1024 * 1024:
            self._json(413, {"chyba": "příliš velké"})
            return
        telo = self.rfile.read(delka) if delka else b""
        if u.path == "/zavreno":
            self.server.zavreno_v = time.time()
            self._posli(204, b"", "text/plain")
            return
        if u.path != "/db":
            self._posli(404, b"neni", "text/plain")
            return
        m = JMENO.match((parse_qs(u.query).get("p") or [""])[0])
        try:
            data = json.loads(telo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        if not m or not isinstance(data, dict):
            self._json(400, {"chyba": "neplatný záznam"})
            return
        jmeno = m.group(1)
        soubor = self.server.soubor_zaznamu(jmeno)
        with self.server.zamek:
            try:
                zapis_bezpecne(soubor, data)
            except OSError as e:
                self._json(500, {"chyba": "nejde zapsat (%s)" % e})
                return
            if jmeno != "pro-reel":
                self._json(200, {"ok": True})
                return
            if not str(data.get("kod") or "").strip():
                self._json(400, {"chyba": "výběr nemá kód stylu"})
                return
            ok, vystup = self.server.pouzij_styl(soubor)
        self.server.vysledek = (ok, vystup)
        if ok:
            self._json(200, {"ok": True})
            threading.Timer(3.0, self.server.konec.set).start()   # stránka ještě ukáže „Uloženo“
        else:
            self._json(500, {"chyba": "styl se nepodařilo použít"})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="STUDIO knihovna")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--ukazky", default=os.environ.get("REEL_STUDIO_UKAZKY"), help="složka s ukázkovými videi")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--bez-prohlizece", action="store_true", help="neotevírat prohlížeč (Claude stránku otevře sám)")
    ap.add_argument("--limit", type=float, default=LIMIT_S, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    reel = Path(a.reel).expanduser()
    if not (reel / "PRACOVNI").is_dir():
        print("🔴 Knihovna: složka reelu %s neexistuje. Udělej: nejdřív založ reel." % reel)
        return 1
    if not STRANKA.is_file():
        print("🔴 Knihovna: v pluginu chybí stránka knihovny. Udělej: napiš Marcele.")
        return 1
    srv = Server(reel, a.ukazky, a.port)
    adresa = "http://127.0.0.1:%d/" % srv.server_address[1]
    vlakno = threading.Thread(target=srv.serve_forever, daemon=True)
    vlakno.start()
    print("STATUS knihovna READY %s" % adresa, flush=True)
    if not a.ukazky or not Path(a.ukazky).is_dir():
        print("ℹ️ Ukázková videa ještě nejsou stažená, karty efektů budou bez videa.", flush=True)
    print("ℹ️ Knihovna stylů je otevřená. Až zákaznice klikne na „Uložit výběr pro tenhle reel“, styl se použije "
          "sám a tenhle krok skončí.", flush=True)
    if not a.bez_prohlizece:
        try:
            webbrowser.open(adresa)
        except Exception:  # noqa: BLE001
            pass
    zacatek = time.time()
    while not srv.konec.wait(1.0):
        if srv.zavreno_v and time.time() - srv.zavreno_v > PO_ZAVRENI_S:
            break
        if time.time() - zacatek > a.limit:
            break
    srv.shutdown()
    if srv.vysledek:
        ok, vystup = srv.vysledek
        print(vystup)
        if ok:
            print("✅ Knihovna: výběr uložený a použitý v reelu (PRACOVNI/knihovna/pro-reel.json). Další krok: plán "
                  "obrazovky (STUDIO plan --reel \"%s\") a vzhled s plánem." % reel)
            return 0
        print("🔴 Knihovna: výběr je uložený, ale styl se nepodařilo použít (výpis výš). Udělej: spusť "
              "STUDIO styl --reel \"%s\" --z-knihovny \"%s\"." % (reel, srv.soubor_zaznamu("pro-reel")))
        return 1
    print("ℹ️ Knihovna se zavřela bez uložení výběru. Reel zůstává ve stylu, který měl. Zeptej se zákaznice, "
          "jestli chce knihovnu otevřít znovu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
