"""Vložka: obrázek nebo krátké video zákaznice (screenshot, fotka, nahrávka obrazovky) v rámečku jako okno nad hlavou.

Spec v osa["prvky"]:
  {"typ": "vlozka", "od": 12.0, "do": 16.0, "soubor": "screenshot.png",
   "nazev": "Přepis s časem každého slova", "kapitola": "02", "efekt": "pop"}
  soubor   název v kontext["podklady"] nebo absolutní cesta (PNG, JPG, WEBP; HEIC neumíme)
           nebo video MP4 / MOV (nahrávka obrazovky z telefonu nebo Macu): bez zvuku, od začátku souboru, nejvýš 8 s,
           po konci videa drží poslední snímek. Stejný rámeček, umístění i výřez jako u obrázku.
  nazev    volitelný text do pilulky pod obrázkem
  kapitola volitelné číslo kapitoly vlevo v pilulce (Playfair Display, růžová)
  efekt    "pop" (zvětšení 0,9 -> 1,0 s náběhem průhlednosti) nebo "zleva" (vjezd 120 px); výstup vždy zmizení
  sirka    volitelná šířka obrázku v px (výchozí 820); výška obrázku nejvýš 900 px
  stin     volitelně True/False (výchozí podle stylu: True)
  pilulka  volitelně "pod" (výchozí) nebo "nad" obrázkem
  vyrez    "nahore", "stred" nebo "dole": která část se nechá, když je obrázek vyšší než rámeček
           (výchozí: PNG a video nahoře, JPG a WEBP uprostřed)

Vzhled: zaoblené rohy, tenký krémový okraj, měkký stín, pilulka se švestkovým podkladem a krémovým textem.
Poloha: nahoře pod bezpečným pásmem (y od kontext["horni"] + 20) a nad oknem obličeje. Když se nevejde,
obrázek se zmenšuje až na 480 px šířky; když ani to nestačí, položí se vpravo nahoru 400 px široký
a do spec["varovani"] se zapíše česká hláška (kontrola umístění ho pak nahlásí).

pripravit() doplní spec["cesta"], spec["x"], spec["y"], spec["sirka"], spec["vyska"] (celý blok bez stínu),
spec["sirka_obrazku"], spec["vyska_obrazku"]. Obrázek se načítá jen jednou (lru_cache podle cesty a šířky).

Video: pripravit() nechá ffmpeg vytáhnout snímky rovnou zmenšené (a oříznuté) na velikost rámečku, 30 snímků
za sekundu, do jednoho souboru rawvideo (RGB) ve složce PRACOVNI reelu (vedle PODKLADY-SEM; když není,
dočasná složka). Celé video se nikdy nedrží v paměti: vykresli() čte jeden snímek přes np.memmap.
Snímek videa v čase t reelu = (t − od) × 30 = (t − od) × fps videa (ffmpeg snímkovost přepočítá).
spec["video"] = {"soubor": cesta k rawvideo, "sirka", "vyska", "snimku", "fps": 30}.
"""
import hashlib
import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import BOK, FPS, SIRKA, VYSKA, pismo

NASTUP_S = 0.30      # délka nástupu (pop nebo zleva)
VYSTUP_S = 0.25      # délka zmizení
MEZERA_OBLICEJ = 24  # kolik px musí zůstat mezi blokem a oknem obličeje
OBRAZKOVE_PRIPONY = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_PRIPONY = {".mp4", ".mov"}
PRIPONY = OBRAZKOVE_PRIPONY | VIDEO_PRIPONY
VIDEO_MAX_S = 8.0    # z videa se použije nejvýš tolik sekund od začátku, pak drží poslední snímek

VYCHOZI_STYL = {
    "sirka": 820,                # výchozí šířka obrázku
    "max_vyska": 900,            # obrázek vyšší se zmenší
    "min_sirka": 480,            # při hledání místa se zmenšuje až sem
    "nouzova_sirka": 400,        # šířka při nouzovém položení vpravo nahoru
    "radius": 28,                # zaoblení rámečku
    "okraj": 6,                  # tloušťka krémového okraje
    "barva_okraje": (251, 246, 239),
    "stin": True,
    "stin_barva": (74, 51, 64, 120),
    "stin_posun": (0, 16),
    "stin_rozmaz": 20,
    "pilulka_podklad": (74, 51, 64, 242),
    "pilulka_pismo": "Montserrat-wght.ttf",
    "pilulka_varianta": "SemiBold",
    "pilulka_velikost": 36,
    "pilulka_barva": (251, 246, 239),
    "pilulka_pad": (30, 16),     # vodorovné a svislé vnitřní okraje pilulky
    "pilulka_mezera": 16,        # mezera mezi rámečkem a pilulkou
    "pilulka_max_sirka": 700,    # pilulka smí být širší než úzký rámeček až do této šířky
    "kapitola_pismo": "PlayfairDisplay-wght.ttf",
    "kapitola_varianta": "Bold",
    "kapitola_velikost": 36,
    "kapitola_barva": (212, 139, 160),
    "kapitola_mezera": 18,       # mezera mezi číslem kapitoly a názvem
}


def _s(styl, klic):
    """Hodnota ze stylu prvku, jinak výchozí."""
    return styl.get(klic, VYCHOZI_STYL[klic]) if styl else VYCHOZI_STYL[klic]


def _hash(hodnota):
    """Seznamy ze stylu (z JSON) převede na n-tice, aby šly uložit do mezipaměti."""
    if isinstance(hodnota, (list, tuple)):
        return tuple(_hash(h) for h in hodnota)
    return hodnota


def _styl_klic(styl):
    return tuple((k, _hash(_s(styl, k))) for k in sorted(VYCHOZI_STYL))


def _styl_ze_klice(klic):
    return dict(klic)


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _clamp(x):
    return max(0.0, min(1.0, x))


def je_video(cesta):
    """True pro MP4 a MOV."""
    return Path(str(cesta)).suffix.lower() in VIDEO_PRIPONY


# ---------------------------------------------------------------- soubor a obrázek

def najdi_soubor(spec, kontext):
    """Cesta k obrázku nebo videu: absolutní, nebo název ve složce podkladů. Chybějící soubor = FileNotFoundError česky."""
    nazev = spec.get("soubor")
    if not nazev:
        raise FileNotFoundError("Vložka v čase %.1f s nemá vyplněný klíč \"soubor\"." % spec.get("od", 0))
    kandidati = []
    p = Path(nazev).expanduser()
    if p.is_absolute():
        kandidati.append(p)
    else:
        podklady = kontext.get("podklady") if kontext else None
        if podklady:
            kandidati.append(Path(podklady) / nazev)
            kandidati.append(Path(podklady) / "NAHRAVKY-OBRAZOVKY" / nazev)   # nahrávky obrazovky (reel.NAHRAVKY)
        kandidati.append(Path(nazev))
    # Mac ukládá háčky v názvu jako zvlášť znak (NFD), text z plánu je NFC: porovnej názvy v obou zápisech
    import unicodedata
    for k in list(kandidati):
        if not k.is_file() and k.parent.is_dir():
            klic = lambda n: unicodedata.normalize("NFC", n).replace(" ", " ").replace(" ", " ").casefold()
            cil = klic(k.name)      # snímky obrazovky z Macu mají v názvu pevnou mezeru
            for s in k.parent.iterdir():
                if klic(s.name) == cil:
                    kandidati.insert(0, s)
                    break
    for k in kandidati:
        if k.is_file():
            if k.suffix.lower() not in PRIPONY:
                raise ValueError("Vložka umí jen PNG, JPG, WEBP a video MP4 nebo MOV. Soubor %s má jinou příponu "
                                 "(HEIC převeď na JPG v Náhledu nebo ve Fotkách)." % k.name)
            return k.resolve()
    hledano = ", ".join(str(k) for k in kandidati)
    raise FileNotFoundError("Obrázek pro vložku \"%s\" (čas %.1f s) nebyl nalezen. Hledal jsem: %s. Ulož ho do složky "
                            "podkladů nebo zapiš celou cestu." % (nazev, spec.get("od", 0), hledano))


@lru_cache(maxsize=32)
def _udaje_videa(cesta):
    """Šířka a výška videa po otočení (ffprobe, nic se nedekóduje). Chyba = ValueError česky."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height:stream_side_data=rotation", "-of", "json", str(cesta)],
                             capture_output=True, text=True, timeout=60)
        d = json.loads(out.stdout or "{}")
        proud = (d.get("streams") or [{}])[0]
        w, h = int(proud.get("width") or 0), int(proud.get("height") or 0)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        raise ValueError("Video pro vložku %s nejde přečíst (ffprobe: %s). Zkus ho uložit znovu jako MP4." % (Path(cesta).name, e))
    if w <= 0 or h <= 0:
        raise ValueError("Video pro vložku %s nemá obrazovou stopu nebo ho ffprobe nepřečetl. Zkus ho uložit znovu jako MP4."
                         % Path(cesta).name)
    otoceni = 0
    for sd in proud.get("side_data_list") or []:
        if sd.get("rotation") is not None:
            try:
                otoceni = int(round(float(sd["rotation"])))
            except (TypeError, ValueError):
                otoceni = 0
    if abs(otoceni) % 180 == 90:          # telefon natočený na výšku s otočením v metadatech: ffmpeg obraz otočí sám
        w, h = h, w
    return w, h


@lru_cache(maxsize=32)
def _rozmer_originalu(cesta):
    if je_video(cesta):
        return _udaje_videa(cesta)
    with Image.open(cesta) as im:
        return im.size


def rozmer_obrazku(cesta, sirka, max_vyska):
    """Rozměr obrázku po zmenšení na danou šířku (poměr stran zachovaný, výška nejvýš max_vyska)."""
    w, h = _rozmer_originalu(str(cesta))
    vyska = max(1, int(round(h * sirka / w)))
    if vyska > max_vyska:
        vyska = max_vyska
        sirka = max(1, int(round(w * vyska / h)))
    return int(sirka), int(vyska)


def _vychozi_vyrez(cesta):
    """Screenshot (PNG) a nahrávka obrazovky mají to důležité nahoře; fotka (JPG, WEBP) uprostřed."""
    c = str(cesta).lower()
    return "nahore" if (c.endswith(".png") or je_video(c)) else "stred"


def _y_vyrezu(vyrez, prirozena, vyska):
    return {"nahore": 0, "stred": int((prirozena - vyska) / 2), "dole": prirozena - int(vyska)}.get(vyrez, 0)


@lru_cache(maxsize=16)
def _nacti_obrazek(cesta, sirka, vyska, vyrez="auto"):
    """Obrázek zmenšený na šířku sirka, RGBA; když je po zmenšení vyšší než vyska, ořízne se shora (horní část
    screenshotu je ta důležitá). Drží se v mezipaměti podle cesty a rozměru."""
    with Image.open(cesta) as im:
        im = im.convert("RGBA")
        w, h = im.size
        prirozena = max(1, int(round(h * sirka / w)))
        if prirozena > vyska + 1:
            im = im.resize((int(sirka), prirozena), Image.LANCZOS)
            if vyrez == "auto":
                vyrez = _vychozi_vyrez(cesta)
            y0 = _y_vyrezu(vyrez, prirozena, vyska)
            return im.crop((0, y0, int(sirka), y0 + int(vyska)))
        return im.resize((int(sirka), int(vyska)), Image.LANCZOS)


# ---------------------------------------------------------------- video: snímky z ffmpeg

def _slozka_snimku(kontext):
    """Složka PRACOVNI reelu (vedle PODKLADY-SEM); když ji neznáme, dočasná složka."""
    if kontext:
        prac = kontext.get("pracovni")
        if prac:
            return Path(prac)
        podklady = kontext.get("podklady")
        if podklady:
            kand = Path(podklady).parent / "PRACOVNI"
            if kand.is_dir():
                return kand
    slozka = Path(tempfile.gettempdir()) / "claude-reel-studio-vlozka"
    slozka.mkdir(parents=True, exist_ok=True)
    return slozka


def _pripravit_video(spec, kontext):
    """Vytáhne snímky videa ffmpegem zmenšené na rozměr obrázku v rámečku do jednoho souboru rawvideo RGB.
    Už hotový soubor (stejné video, rozměr a výřez) se znovu nedělá. Doplní spec["video"]."""
    cesta = Path(spec["cesta"])
    sirka, vyska = int(spec["sirka_obrazku"]), int(spec["vyska_obrazku"])
    w, h = _rozmer_originalu(str(cesta))
    prirozena = max(1, int(round(h * sirka / w)))
    vyrez = spec.get("vyrez") or "auto"
    if vyrez == "auto":
        vyrez = _vychozi_vyrez(cesta)
    filtry = ["fps=%d" % FPS]
    if prirozena > vyska + 1:
        y0 = _y_vyrezu(vyrez, prirozena, vyska)
        filtry += ["scale=%d:%d" % (sirka, prirozena), "crop=%d:%d:0:%d" % (sirka, vyska, y0)]
    else:
        filtry += ["scale=%d:%d" % (sirka, vyska)]
    filtry.append("format=rgb24")
    st = cesta.stat()
    otisk = hashlib.sha1(("%s|%d|%d|%s|%d|%.1f|%d" % (cesta, st.st_size, int(st.st_mtime), ",".join(filtry), FPS,
                                                     VIDEO_MAX_S, 2)).encode("utf-8")).hexdigest()[:12]
    slozka = _slozka_snimku(kontext)
    soubor = slozka / ("vlozka-%s-%s-%dx%d.rgb" % (cesta.stem[:40].replace(" ", "_"), otisk, sirka, vyska))
    bajtu = sirka * vyska * 3
    if not (soubor.is_file() and soubor.stat().st_size >= bajtu and soubor.stat().st_size % bajtu == 0):
        docasny = soubor.with_suffix(".rozdelano")
        cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(cesta), "-t", "%.2f" % VIDEO_MAX_S, "-an",
               "-vf", ",".join(filtry), "-f", "rawvideo", "-pix_fmt", "rgb24", str(docasny)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as e:
            raise ValueError("Video pro vložku %s se nepodařilo připravit (ffmpeg: %s)." % (cesta.name, e))
        if p.returncode != 0 or not docasny.is_file() or docasny.stat().st_size < bajtu:
            chyba = (p.stderr or "").strip().splitlines()
            if docasny.exists():
                docasny.unlink()
            raise ValueError("Video pro vložku %s se nepodařilo připravit (ffmpeg: %s). Zkus ho uložit znovu jako MP4."
                             % (cesta.name, chyba[-1] if chyba else "bez hlášky"))
        os.replace(docasny, soubor)
    snimku = soubor.stat().st_size // bajtu
    spec["video"] = {"soubor": str(soubor), "sirka": sirka, "vyska": vyska, "snimku": int(snimku), "fps": FPS}
    spec["vyrez"] = vyrez


_SNIMKY_VIDEA = {}   # cesta k rawvideo -> np.memmap (n, výška, šířka, 3); otevírá se jednou, nic se nekopíruje do RAM


def _snimek_videa(video, idx):
    """Snímek idx (0 až snimku − 1) jako RGB obrázek z memmapu; za koncem drží poslední snímek."""
    import numpy as np
    klic = video["soubor"]
    mm = _SNIMKY_VIDEA.get(klic)
    if mm is None or mm.shape[0] != video["snimku"]:
        mm = np.memmap(klic, dtype=np.uint8, mode="r", shape=(int(video["snimku"]), int(video["vyska"]), int(video["sirka"]), 3))
        _SNIMKY_VIDEA[klic] = mm
    idx = max(0, min(int(idx), int(video["snimku"]) - 1))
    return Image.frombuffer("RGB", (int(video["sirka"]), int(video["vyska"])), mm[idx].tobytes(), "raw", "RGB", 0, 1)


def snimek_videa(spec, t):
    """Číslo snímku videa v čase t reelu: (t − od) × 30, po konci videa poslední snímek."""
    v = spec["video"]
    idx = int(round((t - spec["od"]) * v.get("fps", FPS)))
    return max(0, min(idx, int(v["snimku"]) - 1))


# ---------------------------------------------------------------- geometrie

def _fonty(styl):
    fp = pismo(_s(styl, "pilulka_pismo"), int(_s(styl, "pilulka_velikost")), _s(styl, "pilulka_varianta"))
    fk = pismo(_s(styl, "kapitola_pismo"), int(_s(styl, "kapitola_velikost")), _s(styl, "kapitola_varianta"))
    return fp, fk


def _text_pilulky(spec):
    nazev = (spec.get("nazev") or "").strip()
    kapitola = str(spec.get("kapitola") or "").strip()
    return nazev, kapitola


def _zkrat(text, font, max_sirka):
    """Zkrátí text s výpustkou, aby se vešel do max_sirka."""
    if font.getlength(text) <= max_sirka:
        return text
    while text and font.getlength(text + "…") > max_sirka:
        text = text[:-1].rstrip()
    return (text + "…") if text else "…"


def _pilulka_geometrie(spec, styl, sirka_ramecku, uzka=False):
    """(šířka, výška, font názvu, font kapitoly, název, kapitola) pilulky; (0, 0, ...) bez textu.
    uzka=True drží pilulku v šířce rámečku (nouzová poloha v rohu)."""
    nazev, kapitola = _text_pilulky(spec)
    if not nazev and not kapitola:
        return 0, 0, None, None, "", ""
    fp, fk = _fonty(styl)
    px, py = _s(styl, "pilulka_pad")
    mezera = _s(styl, "kapitola_mezera") if (nazev and kapitola) else 0
    max_sirka = int(sirka_ramecku) if uzka else min(max(int(sirka_ramecku), int(_s(styl, "pilulka_max_sirka"))),
                                                     SIRKA - 2 * BOK)
    kw = fk.getlength(kapitola) if kapitola else 0
    volno = max_sirka - 2 * px - kw - mezera
    if nazev:
        nazev = _zkrat(nazev, fp, volno)
    nw = fp.getlength(nazev) if nazev else 0
    vyska = 0
    for f, t in ((fp, nazev), (fk, kapitola)):
        if t:
            a, d = f.getmetrics()
            vyska = max(vyska, a + d)
    return int(kw + mezera + nw + 2 * px), int(vyska + 2 * py), fp, fk, nazev, kapitola


def rozlozeni(spec, styl, sirka_obrazku, uzka=False, orez=None):
    """Rozměry bloku pro danou šířku obrázku: slovník s rozměry rámečku, pilulky a celku (bez stínu).
    orez: nejvyšší výška obrázku; vyšší obrázek se v téhle šířce ořízne shora (ne zmenší)."""
    cesta = spec["cesta"]
    if orez:
        so, vo = rozmer_obrazku(cesta, sirka_obrazku, 10 ** 6)
        vo = min(vo, int(orez))
    else:
        so, vo = rozmer_obrazku(cesta, sirka_obrazku, _s(styl, "max_vyska"))
    okraj = int(_s(styl, "okraj"))
    sr, vr = so + 2 * okraj, vo + 2 * okraj
    sp, vp, *_ = _pilulka_geometrie(spec, styl, sr, uzka)
    mezera = _s(styl, "pilulka_mezera") if vp else 0
    return {"sirka_obrazku": so, "vyska_obrazku": vo, "sirka_ramecku": sr, "vyska_ramecku": vr,
            "sirka_pilulky": sp, "vyska_pilulky": vp, "mezera": mezera,
            "sirka": max(sr, sp), "vyska": vr + mezera + vp}


# ---------------------------------------------------------------- rozhraní prvku

def pripravit(spec, styl, kontext):
    """Najde obrázek nebo video, zvolí velikost a polohu nad obličejem a pod horním bezpečným pásmem.
    U videa pak nechá ffmpeg připravit snímky v této velikosti."""
    spec["cesta"] = str(najdi_soubor(spec, kontext))
    if "sirka_zadana" not in spec:
        spec["sirka_zadana"] = int(spec.get("sirka") or _s(styl, "sirka"))
    if "pilulka_zadana" not in spec:
        spec["pilulka_zadana"] = spec.get("pilulka")
    spec.setdefault("efekt", "pop")
    spec.pop("varovani", None)
    spec.pop("video", None)
    horni = int(kontext.get("horni", 220)) + 20
    dolni = int(kontext.get("vyska", VYSKA)) - int(kontext.get("dolni", 450))
    sirka_platna = int(kontext.get("sirka", SIRKA))
    okno = kontext.get("okno")
    strop = dolni if not okno else min(dolni, int(okno[1]) - MEZERA_OBLICEJ)
    max_sirka_bloku = sirka_platna - 2 * BOK
    volno = strop - horni

    min_sirka = int(_s(styl, "min_sirka"))
    so0, vo0 = rozmer_obrazku(spec["cesta"], 1000, 10 ** 6)
    if vo0 < so0:
        min_sirka = min(min_sirka, 360)          # široký obrázek (okno programu) smí být užší, hlavně celý (Marcela 21. 10.)
    kandidati = list(range(spec["sirka_zadana"], min_sirka - 1, -20))
    if not kandidati or kandidati[-1] != min_sirka:
        kandidati.append(min_sirka)
    spec["pilulka_uzka"] = False
    for k in ("orez", "skryt_titulky", "pod_bradou", "nad_oblicejem"):
        spec.pop(k, None)

    def zkus(y0, volno_y, orez_povolen):
        """Největší šířka z kandidátů, která se vejde do výšky volno_y; s ořezem shora, když je povolený
        (nejvýš 70 % obrázku pryč). Vrátí rozložení nebo None."""
        for sirka in kandidati:                       # 1. celý obrázek, od největší šířky
            r0 = rozlozeni(spec, styl, sirka)
            if r0["vyska"] <= volno_y and r0["sirka"] <= max_sirka_bloku:
                spec.pop("orez", None)
                return r0
        if orez_povolen:                              # 2. teprve pak ořez (Marcela 19. 10.: tlačítko bylo uříznuté)
            for sirka in kandidati:
                r0 = rozlozeni(spec, styl, sirka)
                r1 = rozlozeni(spec, styl, sirka, orez=max(1, volno_y - (r0["vyska"] - r0["vyska_obrazku"])))
                prirozena = rozmer_obrazku(spec["cesta"], sirka, 10 ** 6)[1]
                if r1["vyska"] <= volno_y and r1["sirka"] <= max_sirka_bloku and r1["vyska_obrazku"] >= 0.3 * prirozena:
                    spec["orez"] = r1["vyska_obrazku"]
                    return r1
        return None

    r = zkus(horni, volno, False)                       # 1. nad obličejem, celý obrázek
    if r is not None:
        spec["x"], spec["y"], spec["pilulka"] = int((sirka_platna - r["sirka"]) / 2), horni, spec["pilulka_zadana"] or "pod"
    if r is None and okno:
        # 2. nad obličejem, vlasy nevadí (horních 28 % okna jako u nadpisu), vysoký obrázek oříznutý shora
        strop_vlasy = min(dolni, int(okno[1] + 0.28 * (okno[3] - okno[1])) - MEZERA_OBLICEJ)
        r = zkus(horni, strop_vlasy - horni, False)        # nejdřív celý obrázek i přes vlasy (Marcela 21. 10.: „celou fotku“)
        if r is None:
            r = zkus(horni, strop_vlasy - horni, True)     # ořez až jako poslední možnost
        if r is not None:
            spec["x"], spec["y"], spec["pilulka"] = int((sirka_platna - r["sirka"]) / 2), horni, spec["pilulka_zadana"] or "pod"
            spec["nad_oblicejem"] = True
    if r is None and okno:
        # 3. pod bradou místo titulků (titulky se po dobu vložky schovají)
        y0 = int(okno[3]) + MEZERA_OBLICEJ
        r = zkus(y0, dolni - 20 - y0, True)
        if r is not None:
            spec["x"], spec["y"], spec["pilulka"] = int((sirka_platna - r["sirka"]) / 2), y0, spec["pilulka_zadana"] or "nad"
            spec["skryt_titulky"], spec["pod_bradou"] = True, True
    if r is None:
        # nouze: menší obrázek vpravo nahoru, pilulka nad ním a jen v šířce rámečku, varování pro kontrolu
        spec["pilulka_uzka"] = True
        r = rozlozeni(spec, styl, int(_s(styl, "nouzova_sirka")), uzka=True)
        spec["x"] = int(sirka_platna - BOK - r["sirka"])
        spec["y"] = horni
        spec["pilulka"] = spec["pilulka_zadana"] or "nad"
        spec["varovani"] = ("Vložka \"%s\" (čas %.1f s) se nevejde nad obličej, je položená vpravo nahoru a může "
                            "obličej zakrývat. Zkrať ji, posuň v čase, nebo natoč záběr s hlavou níž."
                            % (spec.get("nazev") or spec.get("soubor"), spec.get("od", 0)))
    spec["sirka"], spec["vyska"] = r["sirka"], r["vyska"]
    spec["sirka_obrazku"], spec["vyska_obrazku"] = r["sirka_obrazku"], r["vyska_obrazku"]
    if je_video(spec["cesta"]):
        _pripravit_video(spec, kontext)
    return None


def stav(spec, t):
    """Číslo snímku animace při nástupu (0, 1, ...), záporné při zmizení, "s" v klidu, None mimo čas.
    U videa dvojice (klíč animace, číslo snímku videa): každý snímek videa je jiný obrázek, po konci videa stejný."""
    t_rel, t_konec = t - spec["od"], spec["do"] - t
    if t_rel < 0 or t_konec <= 0:
        return None
    if t_konec < VYSTUP_S:
        k = -(int(t_konec * FPS) + 1)
    elif t_rel < NASTUP_S:
        k = int(t_rel * FPS)
    else:
        k = "s"
    if spec.get("video"):
        return (k, snimek_videa(spec, t))
    return k


def obdelnik(spec, styl):
    """Plocha bloku (rámeček a pilulka, bez stínu) po dokončení animace."""
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


# ---------------------------------------------------------------- kreslení

def _zaobleny_obrazek(im, radius):
    maska = Image.new("L", im.size, 0)
    ImageDraw.Draw(maska).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius, fill=255)
    out = im.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), maska))
    return out


@lru_cache(maxsize=8)
def _maska_rohu(sirka, vyska, radius):
    """Maska zaoblených rohů obrázku (L), jednou pro daný rozměr: u videa se jí ořezává každý snímek."""
    maska = Image.new("L", (int(sirka), int(vyska)), 0)
    ImageDraw.Draw(maska).rounded_rectangle((0, 0, int(sirka) - 1, int(vyska) - 1), radius=radius, fill=255)
    return maska


@lru_cache(maxsize=16)
def _blok(cesta, sirka_obrazku, nazev, kapitola, stin, pilulka, orez, uzka, styl_klic, vyrez="auto", obrazek=True):
    """Klidný snímek bloku (rámeček s obrázkem, pilulka, stín). Vrátí (RGBA obrázek, okraj stínu, (x, y) obrázku
    uvnitř bloku). obrazek=False nechá okno rámečku prázdné (video: snímek se vkládá při každém kreslení)."""
    styl = _styl_ze_klice(styl_klic)
    spec = {"cesta": cesta, "nazev": nazev, "kapitola": kapitola}
    r = rozlozeni(spec, styl, sirka_obrazku, uzka, orez)
    pad = int(styl["stin_rozmaz"] * 2 + max(abs(styl["stin_posun"][0]), abs(styl["stin_posun"][1]))) if stin else 8
    W, H = r["sirka"] + 2 * pad, r["vyska"] + 2 * pad
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # poloha rámečku a pilulky uvnitř bloku (vodorovně na střed)
    rx = pad + int((r["sirka"] - r["sirka_ramecku"]) / 2)
    px_ = pad + int((r["sirka"] - r["sirka_pilulky"]) / 2)
    if pilulka == "nad" and r["vyska_pilulky"]:
        py_ = pad
        ry = pad + r["vyska_pilulky"] + r["mezera"]
    else:
        ry = pad
        py_ = pad + r["vyska_ramecku"] + r["mezera"]
    ramecek = (rx, ry, rx + r["sirka_ramecku"], ry + r["vyska_ramecku"])
    pil = (px_, py_, px_ + r["sirka_pilulky"], py_ + r["vyska_pilulky"]) if r["vyska_pilulky"] else None
    radius = int(styl["radius"])

    # měkký stín
    if stin:
        sx, sy = styl["stin_posun"]
        vrstva = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(vrstva)
        d.rounded_rectangle((ramecek[0] + sx, ramecek[1] + sy, ramecek[2] + sx, ramecek[3] + sy), radius=radius,
                            fill=tuple(styl["stin_barva"]))
        if pil:
            d.rounded_rectangle((pil[0] + sx, pil[1] + sy, pil[2] + sx, pil[3] + sy), radius=int(r["vyska_pilulky"] / 2),
                                fill=tuple(styl["stin_barva"]))
        img.alpha_composite(vrstva.filter(ImageFilter.GaussianBlur(styl["stin_rozmaz"])))

    # rámeček (krémový okraj) a obrázek se zaoblenými rohy
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(ramecek, radius=radius, fill=tuple(styl["barva_okraje"]))
    okraj = int(styl["okraj"])
    poloha_obrazku = (ramecek[0] + okraj, ramecek[1] + okraj)
    if obrazek:
        obr = _nacti_obrazek(cesta, r["sirka_obrazku"], r["vyska_obrazku"], vyrez)
        img.alpha_composite(_zaobleny_obrazek(obr, max(0, radius - okraj)), poloha_obrazku)

    # pilulka: číslo kapitoly (Playfair, růžová) a název (Montserrat, krém)
    if pil:
        sp, vp, fp, fk, nazev_z, kapitola_z = _pilulka_geometrie(spec, styl, r["sirka_ramecku"], uzka)
        d.rounded_rectangle(pil, radius=int(vp / 2), fill=tuple(styl["pilulka_podklad"]))
        x = pil[0] + styl["pilulka_pad"][0]
        stred_y = (pil[1] + pil[3]) / 2
        if kapitola_z:
            d.text((x, stred_y), kapitola_z, font=fk, fill=tuple(styl["kapitola_barva"]), anchor="lm")
            x += fk.getlength(kapitola_z) + (styl["kapitola_mezera"] if nazev_z else 0)
        if nazev_z:
            d.text((x, stred_y), nazev_z, font=fp, fill=tuple(styl["pilulka_barva"]), anchor="lm")
    return img, pad, poloha_obrazku


def vykresli(spec, styl, k):
    """Snímek pro klíč k ze stav(): klidný blok s nástupem (pop, zleva) nebo zmizením.
    U videa je k dvojice (klíč animace, snímek videa): do hotového rámečku se vloží jeden snímek z memmapu."""
    video = spec.get("video")
    idx = None
    if video and isinstance(k, tuple):
        k, idx = k
    stin = bool(spec.get("stin", _s(styl, "stin")))
    nazev, kapitola = _text_pilulky(spec)
    img, pad, poloha_obrazku = _blok(spec["cesta"], int(spec["sirka_obrazku"]), nazev, kapitola, stin, spec.get("pilulka", "pod"),
                                     spec.get("orez"), bool(spec.get("pilulka_uzka")), _styl_klic(styl), spec.get("vyrez", "auto"),
                                     not video)
    img = img.copy()
    if video:
        radius = max(0, int(_s(styl, "radius")) - int(_s(styl, "okraj")))
        snimek = _snimek_videa(video, 0 if idx is None else idx)
        img.paste(snimek, poloha_obrazku, _maska_rohu(snimek.width, snimek.height, radius))
    x0, y0 = int(spec["x"]) - pad, int(spec["y"]) - pad
    if k == "s":
        return img, (x0, y0)
    alfa, mierka, dx = 1.0, 1.0, 0
    if isinstance(k, int) and k >= 0:
        p = _ease_out_cubic(_clamp((k / FPS) / NASTUP_S))
        alfa = p
        if spec.get("efekt", "pop") == "zleva":
            dx = int(-120 * (1 - p))
        else:
            mierka = 0.9 + 0.1 * p
    else:
        alfa = _clamp(((-k - 1) / FPS) / VYSTUP_S)
    if alfa < 1.0:
        img.putalpha(ImageChops.multiply(img.getchannel("A"), Image.new("L", img.size, int(255 * alfa))))
    if abs(mierka - 1.0) > 0.004:
        nw, nh = max(1, int(img.width * mierka)), max(1, int(img.height * mierka))
        cx, cy = x0 + img.width / 2, y0 + img.height / 2
        img = img.resize((nw, nh), Image.LANCZOS)
        x0, y0 = int(cx - nw / 2), int(cy - nh / 2)
    return img, (x0 + dx, y0)
