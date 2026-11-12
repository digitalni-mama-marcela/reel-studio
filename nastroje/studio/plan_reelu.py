"""Stránka Plán reelu (Marcela 29. 10. 2026): co se v reelu objeví, věta po větě, na jedné místní stránce.

Záložky Text, Scény, Vzhled, Zvuk. Scény jsou karty (typ prvku, věta, obrázek). Knihovna vlastních médií je vidět
pořád: nahrát, přiřadit ke scéně, vyměnit, odložit. Klik na větu ukáže její prvky, klik na kartu ukáže větu.
Stránka mění jen PRACOVNI/plan-strihu.json (scény), PRACOVNI/upravy.json (text, jako editor) a složku podkladů.
Střih, render a export se nemění. Ruční změna scény dostane značku „rucne“, takže ji nový plán nepřepíše (planer).
Server poslouchá jen na tomhle počítači (127.0.0.1). Nic se neodesílá ven. Odložený obrázek se nemaže,
přesune se do PODKLADY-SEM/ODLOZENE. Jen standardní knihovna.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import editor, otisk, planer

OBRAZKY = (".png", ".jpg", ".jpeg", ".webp")
NAHRAVKY = (".mp4", ".mov")              # nahrávky obrazovky: leží v PODKLADY-SEM/NAHRAVKY-OBRAZOVKY (reel.NAHRAVKY)
SLOZKA_NAHRAVEK = "NAHRAVKY-OBRAZOVKY"
MAX_SOUBOR = 50 * 1024 * 1024
MAX_NAHRAVKA = 500 * 1024 * 1024
ZASTUPNY_NAHLED = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 90 160"><rect width="90" height="160" fill="#2b2522"/>'
                   b'<path d="M35 62 L60 80 L35 98 Z" fill="#faf7f2"/></svg>')
# prvky, které jde na stránce vybrat (ostatní zůstanou, jak jsou, mění je Claude podle slov zákaznice)
JEDNODUCHE = ["mini", "karty_slov", "velke_slovo", "vlozka", "karticky", "vyzva", "zoom"]
TEXTOVE = ["mini", "karty_slov", "hook", "velke_slovo", "vyzva", "wow", "nalepky", "stitky", "zapisnik", "zprava"]
ODKAZ_STYLY = "https://claude.ai/artifact/7waF2A4cLZ6AqDNKisjyzN"


def otisk_souboru(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else ""


def bezpecne_jmeno(jmeno):
    """Název souboru bez diakritiky a mezer (pravidlo studia), přípona malými písmeny."""
    p = Path(Path(jmeno).name)
    zaklad = unicodedata.normalize("NFKD", p.stem)
    zaklad = "".join(c for c in zaklad if not unicodedata.combining(c)).lower()
    zaklad = re.sub(r"[^a-z0-9]+", "-", zaklad).strip("-")[:50] or "obrazek"
    return zaklad + p.suffix.lower()


def volne_jmeno(slozka, jmeno):
    cil = Path(slozka) / jmeno
    n = 2
    while cil.exists():
        cil = Path(slozka) / ("%s-%d%s" % (Path(jmeno).stem, n, Path(jmeno).suffix))
        n += 1
    return cil


def cesta_nahravky(podklady, jmeno):
    return Path(podklady) / SLOZKA_NAHRAVEK / jmeno


def nahled_nahravky(video):
    """Jeden snímek z nahrávky (JPG, 360 px) pro knihovnu na stránce. Uloží se do PRACOVNI reelu (jinak do dočasné
    složky) a znovu se dělá, jen když se nahrávka změní. Vrátí cestu, nebo None, když ffmpeg snímek neudělá."""
    video = Path(video)
    pracovni = video.parent.parent.parent / "PRACOVNI"
    slozka = (pracovni if pracovni.is_dir() else Path(tempfile.gettempdir()) / "reel-studio") / "nahledy-nahravek"
    st = video.stat()
    klic = hashlib.sha1(("%s|%d|%d" % (video, st.st_size, int(st.st_mtime))).encode("utf-8")).hexdigest()[:16]
    cil = slozka / (klic + ".jpg")
    if cil.is_file():
        return cil
    slozka.mkdir(parents=True, exist_ok=True)
    for zacatek in ("0.5", "0"):          # velmi krátká nahrávka nemusí mít snímek v 0,5 s
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", zacatek, "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=360:-2", str(cil)], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if cil.is_file() and cil.stat().st_size:
            return cil
    return None


def media(podklady, plan):
    """Obrázky pro stránku: knihovna (soubory v podkladech) a obrázky, na které plán odkazuje odjinud.
    Vrátí (seznam pro stránku, {klíč: cesta} pro server, {text v plánu: klíč})."""
    podklady = Path(podklady)
    povolene, seznam, odkazy = {}, [], {}
    if podklady.is_dir():
        for p in sorted(podklady.iterdir(), key=lambda x: x.stat().st_mtime):
            if p.is_file() and p.suffix.lower() in OBRAZKY:
                povolene[p.name] = p
                seznam.append({"klic": p.name, "jmeno": p.name, "url": "/media/" + quote(p.name), "knihovna": True})
                odkazy[p.name] = p.name
                odkazy[str(p)] = p.name
        nahravky = podklady / SLOZKA_NAHRAVEK
        if nahravky.is_dir():
            for p in sorted(nahravky.iterdir(), key=lambda x: x.stat().st_mtime):
                if p.is_file() and p.suffix.lower() in NAHRAVKY and not p.name.startswith(".") and p.name not in povolene:
                    povolene[p.name] = p
                    seznam.append({"klic": p.name, "jmeno": p.name, "url": "/media/" + quote(p.name), "knihovna": True,
                                   "video": True})
                    odkazy[p.name] = p.name
                    odkazy[str(p)] = p.name
    for rad in list(plan.get("radky", [])) + list(plan.get("bez_vety", [])):
        for kus in str(rad.get("obsah") or "").replace("|", "\n").replace(" / ", "\n").splitlines():
            kus = kus.strip()
            if not kus.lower().endswith(OBRAZKY + NAHRAVKY) or kus in odkazy:
                continue
            p = Path(kus) if Path(kus).is_absolute() else podklady / kus
            if p.is_file():
                klic = "x%d" % len(povolene)
                povolene[klic] = p
                odkazy[kus] = klic
                polozka = {"klic": klic, "jmeno": p.name, "url": "/media/" + klic, "knihovna": False}
                if p.suffix.lower() in NAHRAVKY:
                    polozka["video"] = True
                seznam.append(polozka)
    return seznam, povolene, odkazy


def data_stranky(reel, osa, klipy_vety, nazev, cil_s, nejvic_s, plan, soubor_planu, podklady, video):
    d = editor.data_editoru(osa, klipy_vety, nazev, cil_s, nejvic_s)
    seznam, _, odkazy = media(podklady, plan)
    vz = {}
    try:
        vz = json.loads((Path(soubor_planu).parent / "vzhled.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    d.update({"plan": {"radky": plan.get("radky", []), "bez_vety": plan.get("bez_vety", [])},
              "otisk_planu": otisk_souboru(soubor_planu), "media": seznam, "odkazy": odkazy,
              "jmena": planer.JMENA_PRVKU, "jednoduche": JEDNODUCHE, "textove": TEXTOVE,
              "nahled": otisk.porovnej(reel, video), "video": Path(video).name if video else "",
              "vzhled": {"vzhled": vz.get("vzhled"), "titulky_z": vz.get("titulky_z"), "zoom": vz.get("zoom")},
              "odkaz_styly": ODKAZ_STYLY})
    return d


def zkontroluj_plan(u, zname_vety):
    """Ověří plán z prohlížeče. Každý řádek musí patřit ke známé větě (nebo být v „bez věty“). Vyhodí ValueError."""
    if not isinstance(u, dict) or not isinstance(u.get("radky"), list) or not isinstance(u.get("bez_vety", []), list):
        raise ValueError("plán nemá řádky")
    for seznam, musi_mit_vetu in ((u["radky"], True), (u.get("bez_vety", []), False)):
        for r in seznam:
            if not isinstance(r, dict) or not isinstance(r.get("veta"), str) or not isinstance(r.get("prvek"), str):
                raise ValueError("řádek plánu nemá větu nebo prvek")
            if not isinstance(r.get("obsah", ""), str):
                raise ValueError("obsah řádku musí být text")
            if musi_mit_vetu and r["veta"] not in zname_vety:
                raise ValueError("věta %s v reelu není" % r["veta"])
            if not re.match(r"^[a-z_]{2,20}$", r["prvek"]):
                raise ValueError("neznámý prvek %s" % r["prvek"])
    return u


def pouzite_soubory(plan, podklady):
    return {str(p) for p in otisk.soubory_planu(plan, podklady)}


class _Handler(editor._Handler):
    server_version = "ReelStudioPlan/1"

    def _json(self, kod, data):
        self._posli(kod, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        s = self.server
        cesta = urlparse(self.path).path
        if cesta in ("/", "/plan-reelu.html"):
            self._posli(200, s.html().encode("utf-8"), "text/html; charset=utf-8")
        elif cesta == "/video" and s.video:
            self._video()
        elif cesta == "/stav-nahledu":
            self._json(200, otisk.porovnej(s.reel, s.video))
        elif cesta.startswith("/media/"):
            _, povolene, _ = media(s.podklady, s.nacti_plan())
            p = povolene.get(unquote(cesta[len("/media/"):]))
            if not p:
                self._posli(404, b'{"chyba":"neni"}')
                return
            if p.suffix.lower() in NAHRAVKY:     # nahrávka obrazovky: na stránce jen jeden snímek
                n = nahled_nahravky(p)
                if n:
                    self._posli(200, n.read_bytes(), "image/jpeg")
                else:
                    self._posli(200, ZASTUPNY_NAHLED, "image/svg+xml")
                return
            typ = {".png": "image/png", ".webp": "image/webp"}.get(p.suffix.lower(), "image/jpeg")
            self._posli(200, p.read_bytes(), typ)
        else:
            self._posli(404, b'{"chyba":"neni"}')

    def do_POST(self):
        s = self.server
        url = urlparse(self.path)
        delka = int(self.headers.get("Content-Length", 0) or 0)
        if url.path == "/nahraj":
            self._nahraj(url, delka)
            return
        telo = self.rfile.read(delka) if delka else b""
        try:
            data = json.loads(telo.decode("utf-8")) if telo else {}
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"chyba": "nečitelná data"})
            return
        if url.path == "/uloz-plan":
            with s.zamek:
                if data.get("otisk") != otisk_souboru(s.soubor_planu):
                    self._json(409, {"chyba": "Plán se mezitím změnil (třeba ho upravil Claude). Obnov stránku, tvoje "
                                              "neuložené změny se pak musí udělat znovu."})
                    return
                try:
                    u = zkontroluj_plan(data, s.zname_vety)
                except ValueError as e:
                    self._json(400, {"chyba": str(e)})
                    return
                s.uloz_plan(u["radky"], u.get("bez_vety", []))
                s.zmeny.add("scény")
                self._json(200, {"ok": True, "otisk": otisk_souboru(s.soubor_planu), "nahled": otisk.porovnej(s.reel, s.video)})
        elif url.path == "/uloz-text":
            try:
                u = editor.zkontroluj_upravy(data)
            except ValueError as e:
                self._json(400, {"chyba": str(e)})
                return
            editor.uloz_upravy(s.soubor_uprav, u)
            s.zmeny.add("text")
            s.ulozeno_text = u
            self._json(200, {"ok": True, "nahled": otisk.porovnej(s.reel, s.video)})
        elif url.path == "/odloz":
            self._odloz(data)
        elif url.path == "/konec":
            s.konec = True
            self._json(200, {"ok": True})
        else:
            self._posli(404, b'{"chyba":"neni"}')

    def _nahraj(self, url, delka):
        s = self.server
        jmeno = (parse_qs(url.query).get("jmeno") or [""])[0]
        pripona = Path(jmeno).suffix.lower()
        if pripona not in OBRAZKY + NAHRAVKY:
            self._zahod(delka)
            self._json(400, {"chyba": "%s: studio umí obrázky PNG, JPG a WEBP a nahrávky obrazovky MP4 a MOV. "
                                      "Fotku z iPhonu (HEIC) ulož jako JPG." % (jmeno or "soubor")})
            return
        video = pripona in NAHRAVKY
        limit = MAX_NAHRAVKA if video else MAX_SOUBOR
        if delka <= 0 or delka > limit:
            self._zahod(delka)
            self._json(400, {"chyba": "%s: soubor je prázdný, nebo větší než %d MB." % (jmeno, limit // (1024 * 1024))})
            return
        slozka = s.podklady / SLOZKA_NAHRAVEK if video else s.podklady
        with s.zamek:
            slozka.mkdir(parents=True, exist_ok=True)
            cil = volne_jmeno(slozka, bezpecne_jmeno(jmeno))
            if video and (s.podklady / cil.name).exists():   # stejné jméno jako obrázek v knihovně: nové jméno
                cil = volne_jmeno(slozka, "nahravka-" + cil.name)
            tmp = cil.with_name(cil.name + ".tmp")
            with open(tmp, "wb") as f:       # po kouscích, nahrávka se nedrží celá v paměti
                zbyva = delka
                while zbyva > 0:
                    kus = self.rfile.read(min(zbyva, 1024 * 1024))
                    if not kus:
                        break
                    f.write(kus)
                    zbyva -= len(kus)
            if zbyva > 0:
                tmp.unlink()
                self._json(400, {"chyba": "%s: nahrání se přerušilo, zkus to znovu." % jmeno})
                return
            os.replace(str(tmp), str(cil))
        s.zmeny.add("podklady")
        m = {"klic": cil.name, "jmeno": cil.name, "url": "/media/" + quote(cil.name), "knihovna": True}
        if video:
            m["video"] = True
        self._json(200, {"ok": True, "media": m})

    def _zahod(self, delka):
        while delka > 0:
            kus = self.rfile.read(min(delka, 1024 * 1024))
            if not kus:
                break
            delka -= len(kus)

    def _odloz(self, data):
        """Obrázek z knihovny do PODKLADY-SEM/ODLOZENE (nic se nemaže). Jen když ho žádná scéna nepoužívá."""
        s = self.server
        jmeno = str(data.get("jmeno", ""))
        p = s.podklady / jmeno
        if Path(jmeno).suffix.lower() in NAHRAVKY:
            p = cesta_nahravky(s.podklady, jmeno)
        if Path(jmeno).name != jmeno or not p.is_file():
            self._json(400, {"chyba": "obrázek %s v knihovně není" % jmeno})
            return
        with s.zamek:
            if str(p) in pouzite_soubory(s.nacti_plan(), s.podklady):
                self._json(409, {"chyba": "Obrázek je pořád ve scéně. Nejdřív ho ze scény odeber a ulož."})
                return
            cil = volne_jmeno(s.podklady / "ODLOZENE", jmeno)
            cil.parent.mkdir(exist_ok=True)
            shutil.move(str(p), str(cil))
        s.zmeny.add("podklady")
        self._json(200, {"ok": True})


class Server(editor.Server):
    def __init__(self, reel, data_fce, video, soubor_planu, soubor_uprav, podklady, zname_vety, port=0):
        from http.server import ThreadingHTTPServer
        ThreadingHTTPServer.__init__(self, ("127.0.0.1", port), _Handler)
        self.reel, self.data_fce, self.video = reel, data_fce, str(video) if video else None
        self.soubor_planu, self.soubor_uprav, self.podklady = Path(soubor_planu), Path(soubor_uprav), Path(podklady)
        self.zname_vety = set(zname_vety)
        self.zamek = threading.Lock()
        self.zmeny, self.ulozeno, self.ulozeno_text, self.konec = set(), None, None, False

    def html(self):
        return stranka(self.data_fce())

    def nacti_plan(self):
        try:
            return json.loads(self.soubor_planu.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"radky": []}

    def uloz_plan(self, radky, bez_vety):
        """Zapíše plán (záloha staré verze plan-strihu-<čas>.json, pak přejmenování) a obnoví tabulku plan-strihu.md."""
        plan = self.nacti_plan()
        if self.soubor_planu.exists():
            zaloha = self.soubor_planu.with_name("plan-strihu-%d.json" % int(time.time()))
            if not zaloha.exists():
                shutil.copy2(str(self.soubor_planu), str(zaloha))
        plan.update({"verze": planer.PLAN_VERZE, "radky": radky, "bez_vety": bez_vety, "schvaleno": False})
        tmp = self.soubor_planu.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(str(tmp), str(self.soubor_planu))
        nazev = self.data_fce().get("nazev", "")
        (self.soubor_planu.parent / "plan-strihu.md").write_text(planer.tabulka(radky, nazev, bez_vety), encoding="utf-8")


def spust(server, otevrit=True, cekat_s=7200, po_startu=None):
    """Spustí stránku a čeká, až zákaznice klikne Hotovo (nebo vyprší čas). Vrátí množinu změněných částí."""
    vlakno = threading.Thread(target=server.serve_forever, daemon=True)
    vlakno.start()
    try:
        if po_startu:
            po_startu(server.adresa)
        if otevrit:
            webbrowser.open(server.adresa)
        konec = time.time() + cekat_s
        while time.time() < konec and not server.konec:
            time.sleep(0.3)
        return server.zmeny
    finally:
        server.shutdown()
        server.server_close()


def stranka(data):
    return (STRANKA.replace("__NAZEV__", data["nazev"].replace("<", "&lt;"))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))


STRANKA = (Path(__file__).with_name("plan_reelu.html")).read_text(encoding="utf-8") if Path(__file__).with_name("plan_reelu.html").exists() else ""
