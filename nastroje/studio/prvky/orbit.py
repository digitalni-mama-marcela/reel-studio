"""Orbit: 4 až 8 vlastních obálek reelů (9:16) krouží kolem osoby jako prsten.

Zadání Marcely (19. a 20. 10. 2026, nápad): karty na zadní straně prstenu procházejí ZA ní (zakryje je hlava
a ramena přes masku osoby), karty na přední straně PŘED ní ve výšce hrudi, vždy pod obličejem. Používá se na hook
(začátek reelu), trvá 3 až 5 s. Zadní karty menší a ztmavené (hloubka), přední ostré s tenkým rámem a stínem.
Karty naskakují postupně (zvětšení z nuly s malým překmitem), na konci rychle zmizí. Prsten je nakloněný
(elipsa: výška 0,34 šířky).

Spec v osa["prvky"]:
  {"typ": "orbit", "od": 0.1, "do": 4.5, "soubory": ["obalka-1.jpg", ...],
   "karet": 6, "otacka_s": 5.0, "smer": 1, "sirka_karty": 180, "vyrez": "stred"}
  soubory      4 až 8 názvů ve složce kontext["podklady"] nebo absolutních cest (PNG, JPG, WEBP)
  karet        volitelné, počet karet v prstenu (4 až 8); výchozí = počet souborů (nejvýš 8); víc karet než souborů
               = obálky se opakují
  otacka_s     volitelné, sekundy na jednu otáčku (výchozí 5,0)
  smer         1 = zleva doprava vpředu (proti směru hodin při pohledu shora), -1 = opačně
  sirka_karty  volitelné, šířka přední karty v px (výchozí 180; zadní karta má 0,6 ×); při hledání místa se zmenšuje
  vyrez        "stred" (výchozí) nebo "nahore": odkud se bere výřez, když obrázek není 9:16
  radius, barva_ramu, ram_px   volitelné přepsání vzhledu přímo ve spec (vzhled Marcela: radius 20, krémový rám)

Vzhled: VYCHOZI_STYL přepíše styl["orbit"] ze slovníku vzhledu (titulky.STYLY) a pak klíče ve spec.
  Vogue: hranaté nebo rádius nejvýš 8, bílý rám. Marcela: rádius 20, krémový rám (251, 246, 239).

Umístění (pripravit): střed prstenu vodorovně = střed okna obličeje (nejvýš 120 px od středu obrazu), bez okna
střed obrazu. Vodorovný poloměr co největší tak, aby každá karta celá zůstala mezi 40 a 1040 px. Svisle prsten
co nejvýš tak, aby žádná PŘEDNÍ karta nesahala do okna obličeje (30 px mezera) a spodek prstenu zůstal nad
VYSKA − DOLNI_OKRAJ − 20 (1450 px); zadní karty smějí jít za hlavu (maska). Když se nevejde, šířka karty se
zmenšuje po 10 px až na 120; když ani to nestačí, spec["varovani"] (česky) a prsten leží co nejvýš pod obličejem.
Bez okna obličeje (umělé video): střed obrazu, cy = 0,55 × VYSKA.

Pohyb: úhel karty i v čase t = smer · 2π · (t − od) / otacka_s + i · 2π / n; x = cx + rx·cos, y = cy + ry·sin;
hloubka = sin (kladná = vpředu); velikost karty zadní 0,6 → přední 1,0 plynule, jas 0,75 → 1,0 plynule.
Vrstvy: Kreslic volá vykresli() se spec["cast"] = "pozadi" (jen karty s hloubkou ≤ 0, jdou za osobu) a "text"
(jen karty s hloubkou > 0, před osobu). Bez "cast" se kreslí obě.

Po pripravit() má spec navíc: cesty, karet, stred [cx, cy], rx, ry, sirka_karty, vyska_karty, x, y, sirka, vyska
(obdélník celého prstenu po animaci), text_vpredu=True, za_hlavou=True, pres_oblicej=True (zadní karty jdou
za hlavu záměrně, kontrola umístění je nemá hlásit) a okno_obliceje (pro opakovanou přípravu bez okna).

Rychlost: stav() vrací číslo snímku (prsten se hýbe každý snímek). vykresli() kreslí jen výřez kolem prstenu;
hotová karta v plné velikosti (výřez 9:16, rám, rohy) a stín podle rozměru se drží v lru_cache, na snímek se jen
zmenšují a skládají. OVĚŘENO 20. 10. 2026 (MacBook Marcely, 6 obálek 1080x1920, umělé video): obě vrstvy
dohromady průměrně 6 ms na snímek (nejvíc 11 ms), první snímek s načtením obálek 70 ms, pripravit() pod 1 ms.
"""
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA

BOK_ORBITU = 40          # karta celá mezi 40 a 1040 px
MEZERA_OBLICEJ = 30      # přední karta nejmíň 30 px od okna obličeje
REZERVA_DOLE = 20        # spodek prstenu nad VYSKA − DOLNI_OKRAJ − 20
MIN_SIRKA_KARTY = 120
KROK_SIRKY = 10
MIN_KARET, MAX_KARET = 4, 8
MAX_POSUN_STREDU = 120   # střed prstenu nejvýš takhle daleko od středu obrazu (jinak by byl prsten moc malý)
POMER_KARTY = 16 / 9     # obálka reelu 9:16
PODIL_VYSKY_BEZ_OBLICEJE = 0.55
PRIPONY = {".png", ".jpg", ".jpeg", ".webp"}
UHLU_OBALKY = 360        # kolik poloh karty se zkouší při výpočtu obdélníku a místa
REZERVA_VZORKU = 4       # px navíc kolem okna obličeje při hledání výšky (vzorkování úhlů není spojité)

VYCHOZI_STYL = {
    "ram_px": 4,
    "barva_ramu": (255, 255, 255),
    "radius": 8,
    "stin": (0, 0, 0, 120),
    "stin_posun": (0, 10),
    "stin_rozmaz": 14,
    "zadni_pomer": 0.6,      # velikost zadní karty vůči přední
    "zadni_jas": 0.75,       # jas zadní karty (1,0 = přední)
    "naklon": 0.34,          # výška elipsy / šířka
    "nastup_s": 0.35,        # zvětšení jedné karty z nuly
    "rozestup_s": 0.05,      # každá další karta o tolik později
    "odchod_s": 0.22,        # zmizení všech karet na konci
    "prekmit": 1.06,         # překmit při nástupu
    "sirka_karty": 180,      # výchozí šířka přední karty
    "otacka_s": 5.0,         # sekundy na otáčku
}
VE_SPEC = ("radius", "barva_ramu", "ram_px", "naklon", "zadni_pomer", "zadni_jas")   # klíče vzhledu, které smí přepsat spec


# ---------------------------------------------------------------- styl

def _hash(hodnota):
    if isinstance(hodnota, (list, tuple)):
        return tuple(_hash(h) for h in hodnota)
    return hodnota


def _styl(spec, styl):
    """Sloučený vzhled: výchozí ← styl["orbit"] ze vzhledu ← klíče ve spec."""
    st = dict(VYCHOZI_STYL)
    if styl:
        st.update({k: styl[k] for k in VYCHOZI_STYL if k in styl})
    if spec:
        st.update({k: spec[k] for k in VE_SPEC if k in spec and spec[k] is not None})
    return st


def _styl_klic(st):
    return tuple((k, _hash(st[k])) for k in sorted(VYCHOZI_STYL))


def _barva(b, alfa=255):
    b = tuple(int(v) for v in b)
    return b[:3] + ((b[3],) if len(b) > 3 else (alfa,))


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


# ---------------------------------------------------------------- soubory

def _normalizuj(nazev):
    """Název pro porovnání: háčky v jednom zápisu (Mac ukládá NFD), pevné mezery jako obyčejné."""
    return unicodedata.normalize("NFC", nazev).replace(" ", " ").replace(" ", " ").casefold()


def najdi_soubor(nazev, spec, kontext):
    """Cesta k obálce: absolutní, nebo název ve složce podkladů. Chybějící soubor = FileNotFoundError česky."""
    cas = spec.get("od", 0)
    if not nazev or not isinstance(nazev, str):
        raise FileNotFoundError("Orbit v čase %.1f s má v klíči \"soubory\" prázdný název." % cas)
    kandidati = []
    p = Path(nazev).expanduser()
    if p.is_absolute():
        kandidati.append(p)
    else:
        podklady = kontext.get("podklady") if kontext else None
        if podklady:
            kandidati.append(Path(podklady) / nazev)
        kandidati.append(Path(nazev))
    for k in list(kandidati):
        if not k.is_file() and k.parent.is_dir():
            cil = _normalizuj(k.name)
            for s in k.parent.iterdir():
                if _normalizuj(s.name) == cil:
                    kandidati.insert(0, s)
                    break
    for k in kandidati:
        if k.is_file():
            if k.suffix.lower() not in PRIPONY:
                raise ValueError("Orbit umí jen PNG, JPG a WEBP. Obálka %s má jinou příponu (HEIC převeď na JPG "
                                 "v Náhledu nebo ve Fotkách)." % k.name)
            return k.resolve()
    hledano = ", ".join(str(k) for k in kandidati)
    raise FileNotFoundError("Obálka pro orbit \"%s\" (čas %.1f s) nebyla nalezena. Hledal jsem: %s. Ulož ji do složky "
                            "podkladů nebo zapiš celou cestu." % (nazev, cas, hledano))


# ---------------------------------------------------------------- geometrie

def _meritko(hloubka, st):
    """Velikost karty podle hloubky: zadní (−1) zadni_pomer, přední (+1) 1,0, mezi tím plynule."""
    zp = float(st["zadni_pomer"])
    return zp + (1.0 - zp) * (hloubka + 1.0) / 2.0


def _jas(hloubka, st):
    zj = float(st["zadni_jas"])
    return zj + (1.0 - zj) * (hloubka + 1.0) / 2.0


def _karta_pri_uhlu(uhel, cx, cy, rx, ry, sirka, vyska, st, faktor=1.0):
    """Obdélník karty (x0, y0, x1, y1), její střed, rozměr a hloubka pro daný úhel; faktor = animace."""
    hloubka = math.sin(uhel)
    m = _meritko(hloubka, st) * faktor
    w, h = sirka * m, vyska * m
    x, y = cx + rx * math.cos(uhel), cy + ry * hloubka
    return {"hloubka": hloubka, "x": x, "y": y, "sirka": w, "vyska": h, "meritko": m,
            "obdelnik": (x - w / 2, y - h / 2, x + w / 2, y + h / 2)}


def _obalka(cx, cy, rx, ry, sirka, vyska, st):
    """Obdélník, který pokryje kartu ve všech polohách na prstenu (klidový stav, bez stínu)."""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for j in range(UHLU_OBALKY):
        k = _karta_pri_uhlu(2 * math.pi * j / UHLU_OBALKY, cx, cy, rx, ry, sirka, vyska, st)
        a, b, c, d = k["obdelnik"]
        x0, y0, x1, y1 = min(x0, a), min(y0, b), max(x1, c), max(y1, d)
    return x0, y0, x1, y1


def _vodorovny_polomer(cx, sirka, st, sirka_platna):
    """Největší rx, při kterém karta v každé poloze zůstane celá mezi BOK_ORBITU a sirka_platna − BOK_ORBITU."""
    volno = min(cx - BOK_ORBITU, sirka_platna - BOK_ORBITU - cx)
    rx = int(volno)
    while rx > 0:
        ok = True
        for j in range(UHLU_OBALKY):
            u = 2 * math.pi * j / UHLU_OBALKY
            if rx * abs(math.cos(u)) + sirka * _meritko(math.sin(u), st) / 2 > volno:
                ok = False
                break
        if ok:
            return rx
        rx -= 1
    return 0


def _stred_pod_oblicejem(okno, cx, rx, ry, sirka, vyska, st, horni):
    """Nejmenší cy, při kterém žádná přední karta (hloubka > 0) nezasáhne okno obličeje s mezerou a horní okraj
    prstenu (zadní karta) nejde nad horní bezpečné pásmo."""
    # vodorovně se okno bere o REZERVA_VZORKU širší a úhly jemněji, aby karta těsně u kraje okna neproklouzla
    ox0, ox1 = okno[0] - MEZERA_OBLICEJ - REZERVA_VZORKU, okno[2] + MEZERA_OBLICEJ + REZERVA_VZORKU
    oy1 = okno[3] + MEZERA_OBLICEJ + 1
    cy = horni + ry + vyska * _meritko(-1.0, st) / 2
    kroku = UHLU_OBALKY * 4
    for j in range(kroku):
        u = 2 * math.pi * j / kroku
        hloubka = math.sin(u)
        if hloubka <= 0:
            continue
        m = _meritko(hloubka, st)
        w, h = sirka * m, vyska * m
        x = cx + rx * math.cos(u)
        if x + w / 2 <= ox0 or x - w / 2 >= ox1:
            continue                                   # karta je vedle obličeje, svisle ji nic neomezuje
        cy = max(cy, oy1 - ry * hloubka + h / 2)
    return cy


def rozlozeni_v_case(spec, styl, t_rel, animace=True):
    """Karty v čase t_rel (s od začátku prvku): seznam slovníků i, uhel, hloubka, x, y, sirka, vyska, jas, meritko,
    obdelnik; seřazeno zezadu dopředu. animace=False dává klidový stav (bez nástupu a odchodu)."""
    st = _styl(spec, styl)
    n = int(spec["karet"])
    cx, cy = spec["stred"]
    rx, ry = float(spec["rx"]), float(spec["ry"])
    sirka, vyska = float(spec["sirka_karty"]), float(spec["vyska_karty"])
    smer = -1.0 if float(spec.get("smer", 1)) < 0 else 1.0
    otacka = float(spec.get("otacka_s") or st["otacka_s"])
    delka = float(spec["do"]) - float(spec["od"])
    odchod = _odchod(delka - t_rel, st) if animace else 1.0
    out = []
    for i in range(n):
        faktor = (_nastup(i, t_rel, st) if animace else 1.0) * odchod
        if faktor <= 0.0:
            continue
        uhel = smer * 2 * math.pi * t_rel / otacka + i * 2 * math.pi / n
        k = _karta_pri_uhlu(uhel, cx, cy, rx, ry, sirka, vyska, st, faktor)
        k.update({"i": i, "uhel": uhel, "jas": _jas(k["hloubka"], st), "faktor": faktor})
        out.append(k)
    out.sort(key=lambda k: k["hloubka"])
    return out


# ---------------------------------------------------------------- animace

def _nastup(i, t_rel, st):
    """Zvětšení karty i z nuly s překmitem: 0 před startem, prekmit kolem 65 % náběhu, pak 1,0."""
    p = (t_rel - i * float(st["rozestup_s"])) / max(1e-6, float(st["nastup_s"]))
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    prekmit = float(st["prekmit"])
    if p < 0.65:
        q = p / 0.65
        return prekmit * (1.0 - (1.0 - q) ** 3)
    q = (p - 0.65) / 0.35
    return prekmit - (prekmit - 1.0) * (3 * q * q - 2 * q * q * q)


def _odchod(t_konec, st):
    """Zmenšení všech karet na konci: 1,0 v klidu, k nule za odchod_s (rychle na začátku)."""
    odchod = float(st["odchod_s"])
    if t_konec >= odchod:
        return 1.0
    q = _clamp(t_konec / max(1e-6, odchod))
    return q * q


# ---------------------------------------------------------------- rozhraní prvku

def pripravit(spec, styl, kontext):
    """Najde obálky, zvolí šířku karty, poloměry a střed prstenu pod obličejem v bezpečném pásmu."""
    kontext = kontext or {}
    cas = spec.get("od", 0)
    soubory = spec.get("soubory")
    if not isinstance(soubory, (list, tuple)) or not soubory:
        raise ValueError("Orbit v čase %.1f s potřebuje klíč \"soubory\" se seznamem %d až %d obálek."
                         % (cas, MIN_KARET, MAX_KARET))
    if len(soubory) < MIN_KARET:
        raise ValueError("Orbit v čase %.1f s má %d obálek, potřebuje aspoň %d." % (cas, len(soubory), MIN_KARET))
    if len(soubory) > MAX_KARET:
        raise ValueError("Orbit v čase %.1f s má %d obálek, nejvíc jich smí být %d." % (cas, len(soubory), MAX_KARET))
    cesty = [najdi_soubor(n, spec, kontext) for n in soubory]
    karet = int(spec.get("karet") or min(len(cesty), MAX_KARET))
    if not MIN_KARET <= karet <= MAX_KARET:
        raise ValueError("Orbit v čase %.1f s: klíč \"karet\" musí být %d až %d, je %d." % (cas, MIN_KARET, MAX_KARET, karet))
    spec["karet"] = karet
    spec["cesty"] = [str(cesty[i % len(cesty)]) for i in range(karet)]
    st = _styl(spec, styl)
    if "sirka_karty_zadana" not in spec:
        spec["sirka_karty_zadana"] = int(spec.get("sirka_karty") or st["sirka_karty"])
    otacka = float(spec.get("otacka_s") or st["otacka_s"])
    if otacka <= 0:
        raise ValueError("Orbit v čase %.1f s: \"otacka_s\" musí být kladné číslo sekund na otáčku." % cas)
    spec["otacka_s"] = otacka
    spec["smer"] = -1 if float(spec.get("smer", 1)) < 0 else 1
    if spec.get("vyrez") not in ("stred", "nahore"):
        spec["vyrez"] = "stred"
    spec.pop("varovani", None)

    sirka_platna = int(kontext.get("sirka", SIRKA))
    vyska_platna = int(kontext.get("vyska", VYSKA))
    horni = int(kontext.get("horni", HORNI_OKRAJ))
    dolni_hranice = vyska_platna - int(kontext.get("dolni", DOLNI_OKRAJ)) - REZERVA_DOLE
    okno = kontext.get("okno")
    if okno is None and spec.get("okno_obliceje"):
        okno = tuple(spec["okno_obliceje"])        # opakovaná příprava: priprav_vsechny u prvků za hlavou okno nedává
    if okno:
        spec["okno_obliceje"] = [int(round(v)) for v in okno]
        cx = (okno[0] + okno[2]) / 2.0
        cx = _clamp(cx, sirka_platna / 2.0 - MAX_POSUN_STREDU, sirka_platna / 2.0 + MAX_POSUN_STREDU)
    else:
        spec.pop("okno_obliceje", None)
        cx = sirka_platna / 2.0
    naklon = float(st["naklon"])

    kandidati = list(range(max(MIN_SIRKA_KARTY, int(spec["sirka_karty_zadana"])), MIN_SIRKA_KARTY - 1, -KROK_SIRKY))
    if kandidati[-1] != MIN_SIRKA_KARTY:
        kandidati.append(MIN_SIRKA_KARTY)
    vysledek = None
    for sirka in kandidati:
        vyska = int(round(sirka * POMER_KARTY))
        rx = _vodorovny_polomer(cx, sirka, st, sirka_platna)
        ry = naklon * rx
        if okno:
            cy = _stred_pod_oblicejem(okno, cx, rx, ry, sirka, vyska, st, horni)
        else:
            cy = PODIL_VYSKY_BEZ_OBLICEJE * vyska_platna
        vysledek = (sirka, vyska, rx, ry, cy)
        if cy + ry + vyska / 2.0 <= dolni_hranice:
            break
    else:
        spec["varovani"] = ("Orbit (čas %.1f s): záběr je moc blízko, přední karty se pod obličej nevejdou ani při "
                            "šířce %d px. Orbit vynech nebo natoč dál od kamery." % (cas, MIN_SIRKA_KARTY))
    sirka, vyska, rx, ry, cy = vysledek
    spec["sirka_karty"], spec["vyska_karty"] = int(sirka), int(vyska)
    spec["stred"] = [round(cx, 1), round(cy, 1)]
    spec["rx"], spec["ry"] = int(rx), round(ry, 1)
    x0, y0, x1, y1 = _obalka(cx, cy, rx, ry, sirka, vyska, st)
    spec["x"], spec["y"] = int(math.floor(x0)), int(math.floor(y0))
    spec["sirka"], spec["vyska"] = int(math.ceil(x1)) - spec["x"], int(math.ceil(y1)) - spec["y"]
    spec["text_vpredu"] = True      # přední karty kreslí Kreslic před osobu (cast "text")
    spec["za_hlavou"] = True        # zadní karty za osobu (cast "pozadi", maska)
    spec["pres_oblicej"] = True     # zadní karty jdou za hlavu záměrně, kontrola umístění je nemá hlásit
    return None


def stav(spec, t):
    """Číslo snímku od začátku prvku (prsten se hýbe každý snímek), None mimo čas."""
    if t < spec["od"] or t >= spec["do"]:
        return None
    return int(math.floor((t - spec["od"]) * FPS + 1e-6))


def obdelnik(spec, styl):
    """Obdélník celého prstenu po animaci (všechny polohy karet, bez stínu)."""
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


# ---------------------------------------------------------------- kreslení

@lru_cache(maxsize=64)
def _maska_rohu(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=max(0, int(r)), fill=255)
    return m


def _vyrez_9_16(im, w, h, vyrez):
    """Obrázek zmenšený a oříznutý tak, aby vyplnil w × h (poměr karty); u vyšších shora nebo ze středu."""
    W0, H0 = im.size
    k = max(w / float(W0), h / float(H0))
    nw, nh = max(w, int(round(W0 * k))), max(h, int(round(H0 * k)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x0 = (nw - w) // 2
    y0 = 0 if vyrez == "nahore" else (nh - h) // 2
    return im.crop((x0, y0, x0 + w, y0 + h))


@lru_cache(maxsize=32)
def _karta_plna(cesta, w, h, vyrez, styl_klic):
    """Hotová karta v plné velikosti: rám se zaoblenými rohy a obálka oříznutá na poměr karty. Bez stínu."""
    st = dict(styl_klic)
    ram, r = int(st["ram_px"]), int(st["radius"])
    karta = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(karta).rounded_rectangle((0, 0, w - 1, h - 1), radius=max(0, r), fill=_barva(st["barva_ramu"]))
    with Image.open(cesta) as im:
        obr = _vyrez_9_16(im.convert("RGBA"), max(1, w - 2 * ram), max(1, h - 2 * ram), vyrez)
    obr.putalpha(ImageChops.multiply(obr.getchannel("A"), _maska_rohu(obr.width, obr.height, max(0, r - ram))))
    karta.alpha_composite(obr, (ram, ram))
    return karta


@lru_cache(maxsize=128)
def _stin(w, h, styl_klic):
    """Měkký stín pod kartou w × h (rozměr zaokrouhlený na 4 px). Vrátí (obrázek, odsazení pad)."""
    st = dict(styl_klic)
    sx, sy = (int(v) for v in st["stin_posun"])
    rozmaz = int(st["stin_rozmaz"])
    pad = rozmaz * 2 + max(abs(sx), abs(sy))
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((pad + sx, pad + sy, pad + sx + w - 1, pad + sy + h - 1),
                                          radius=max(0, int(st["radius"])), fill=_barva(st["stin"], 120))
    return img.filter(ImageFilter.GaussianBlur(rozmaz)), pad


def _ztmav(img, jas):
    if jas >= 0.995:
        return img
    out = Image.blend(Image.new("RGBA", img.size, (0, 0, 0, 0)), img, jas)
    out.putalpha(img.getchannel("A"))
    return out


def _pruhlednost(img, alfa):
    if alfa >= 1.0:
        return img
    out = img.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), Image.new("L", out.size, int(255 * alfa))))
    return out


def _poloz(plat, img, x, y):
    """Položí img na plat na (x, y); část mimo plátno ořízne."""
    x0, y0 = max(0, -x), max(0, -y)
    x1, y1 = min(img.width, plat.width - x), min(img.height, plat.height - y)
    if x1 <= x0 or y1 <= y0:
        return
    plat.alpha_composite(img, (x + x0, y + y0), (x0, y0, x1, y1))


def _platno(spec, st):
    """Výřez plátna kolem prstenu: obdélník prstenu plus stín a překmit."""
    sx, sy = (int(v) for v in st["stin_posun"])
    pad = int(st["stin_rozmaz"]) * 2 + max(abs(sx), abs(sy))
    extra = int(math.ceil(float(spec["vyska_karty"]) * (float(st["prekmit"]) - 1.0) / 2)) + 2
    x0, y0, x1, y1 = obdelnik(spec, None)
    return x0 - pad - extra, y0 - pad - extra, x1 + pad + extra, y1 + pad + extra


def vykresli(spec, styl, k):
    """Snímek k (číslo od začátku prvku): karty na prstenu s nástupem a odchodem. Podle spec["cast"] kreslí jen
    zadní ("pozadi", hloubka ≤ 0) nebo jen přední ("text", hloubka > 0) karty. Vrátí jen výřez kolem prstenu."""
    st = _styl(spec, styl)
    styl_klic = _styl_klic(st)
    cast = spec.get("cast")
    vyrez = spec.get("vyrez", "stred")
    t_rel = float(k) / FPS
    delka = float(spec["do"]) - float(spec["od"])
    alfa = _clamp((delka - t_rel) / max(1e-6, float(st["odchod_s"])))
    px0, py0, px1, py1 = _platno(spec, st)
    plat = Image.new("RGBA", (px1 - px0, py1 - py0), (0, 0, 0, 0))
    plna_w = int(math.ceil(float(spec["sirka_karty"]) * float(st["prekmit"])))
    plna_h = int(round(plna_w * POMER_KARTY))
    for kt in rozlozeni_v_case(spec, styl, t_rel):
        if cast == "pozadi" and kt["hloubka"] > 0:
            continue
        if cast == "text" and kt["hloubka"] <= 0:
            continue
        w, h = max(2, int(round(kt["sirka"]))), max(2, int(round(kt["vyska"])))
        plna = _karta_plna(spec["cesty"][kt["i"]], plna_w, plna_h, vyrez, styl_klic)
        img = plna if (w, h) == plna.size else plna.resize((w, h), Image.LANCZOS)
        img = _pruhlednost(_ztmav(img, kt["jas"]), alfa)
        x, y = int(round(kt["x"] - w / 2.0)) - px0, int(round(kt["y"] - h / 2.0)) - py0
        stin, pad = _stin(max(4, (w + 2) // 4 * 4), max(4, (h + 2) // 4 * 4), styl_klic)
        _poloz(plat, _pruhlednost(stin, alfa * kt["jas"]), x + (w - (stin.width - 2 * pad)) // 2 - pad,
               y + (h - (stin.height - 2 * pad)) // 2 - pad)
        _poloz(plat, img, x, y)
    return plat, (px0, py0)
