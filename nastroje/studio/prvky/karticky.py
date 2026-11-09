"""Kartičky: 3 až 5 snímků obrazovky jako nakloněné karty (vějíř) v horní polovině, vplouvají jedna po druhé.

Zadání Marcely (19. 10. 2026, „Vogue styl, černobíle“, oddíl 6): obdélníky s mírným náklonem (±3 až 6°),
vplouvají jedna po druhé s rozestupem asi 0,15 s, mají stíny, leží v horní polovině.

Spec v osa["prvky"]:
  {"typ": "karticky", "od": 24.5, "do": 28.0, "soubory": ["a.png", "b.png", "c.jpg"],
   "naklon": [-5, 4, -3], "sirka": 520, "vyrez": "nahore"}
  soubory  názvy ve složce kontext["podklady"] nebo absolutní cesty (PNG, JPG, WEBP); 1 až 5 souborů
  naklon   volitelný seznam úhlů ve stupních (kladný = proti směru hodin); výchozí střídavě -5, +4, -3, +5, -4
  sirka    volitelná šířka karty v px (výchozí 400: tři karty se vejdou do pásma 940 px s překryvem asi třetina)
  vyrez    "nahore" nebo "stred": odkud se bere výřez vysokého obrázku (poměr stran karty nejvýš 4:5);
           výchozí "auto" = PNG (snímek obrazovky) shora, fotka (JPG, WEBP) ze středu

Vzhled (paleta jen černá, bílá, šedá): hranatá karta, teplejší bílý podklad #F4F2EE, tenký bílý rám 3 px,
měkký černý stín. Žádné zaoblení.

Poloha: horní polovina, y od kontext["horni"] + 20 dolů po okno obličeje (minus 24 px), bez okna po 900 px.
Karty jdou zleva doprava s překryvem (vějíř), každá další o kousek níž nebo výš. Když se nevejdou nad obličej,
šířka karty se zmenšuje až na 360 px; když ani to nestačí, položí se co nejvýš a do spec["varovani"]
se zapíše česká hláška (kontrola umístění ji nahlásí).

Animace: karta i přilétá zespodu (posun 140 px) s náběhem průhlednosti za 0,35 s (ease-out), začíná
i × 0,15 s po začátku prvku. Odlet: všechny zmizí za 0,25 s.

pripravit() doplní spec["karty"] (cesta, rozměry, náklon, střed a obdélník každé karty), spec["x"], spec["y"],
spec["sirka"], spec["vyska"] (sjednocení karet bez stínu). Obrázky i hotové karty se drží v mezipaměti
(lru_cache), takže se kreslí jen jednou.
"""
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import BOK, FPS, SIRKA, VYSKA

NABEH_S = 0.35       # náběh jedné karty (posun a průhlednost)
ROZESTUP_S = 0.15    # rozestup mezi kartami
VYSTUP_S = 0.25      # zmizení všech karet
NALET_PX = 140       # odkud zespodu karta přilétá
MEZERA_OBLICEJ = 24  # kolik px musí zůstat mezi kartami a oknem obličeje
STROP_BEZ_OBLICEJE = 900
PRIPONY = {".png", ".jpg", ".jpeg", ".webp"}
MAX_KARET = 5

VYCHOZI_STYL = {
    "sirka": 400,                    # výchozí šířka karty (včetně rámu)
    "min_sirka": 360,                # při hledání místa se zmenšuje až sem
    "pomer_max": 1.25,               # výška obrázku nejvýš 4:5 (1,25 × šířka), vyšší se ořízne
    "ram": 3,                        # tloušťka bílého rámu
    "barva_ramu": (255, 255, 255),
    "barva_karty": (244, 242, 238),  # teplejší bílá pod obrázkem
    "stin": True,
    "stin_barva": (10, 10, 10, 150),
    "stin_posun": (0, 18),
    "stin_rozmaz": 22,
    "naklony": (-5, 4, -3, 5, -4),   # výchozí náklon karet ve stupních
    "prekryv": 0.30,                 # nejmenší překryv sousedních karet (podíl šířky)
    "posuny_y": (0, 30, 12, 36, 18),  # svislé odsazení karet ve vějíři
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


# ---------------------------------------------------------------- soubory a obrázky

def _normalizuj(nazev):
    """Název souboru pro porovnání: háčky v jednom zápisu (Mac ukládá NFD), pevné mezery jako obyčejné."""
    return unicodedata.normalize("NFC", nazev).replace(" ", " ").replace(" ", " ").casefold()


def najdi_soubor(nazev, spec, kontext):
    """Cesta k jednomu obrázku: absolutní, nebo název ve složce podkladů. Chybějící soubor = FileNotFoundError česky."""
    cas = spec.get("od", 0)
    if not nazev or not isinstance(nazev, str):
        raise FileNotFoundError("Kartičky v čase %.1f s mají v klíči \"soubory\" prázdný název." % cas)
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
                raise ValueError("Kartičky umí jen PNG, JPG a WEBP. Soubor %s má jinou příponu (HEIC převeď na JPG "
                                 "v Náhledu nebo ve Fotkách)." % k.name)
            return k.resolve()
    hledano = ", ".join(str(k) for k in kandidati)
    raise FileNotFoundError("Obrázek pro kartičky \"%s\" (čas %.1f s) nebyl nalezen. Hledal jsem: %s. Ulož ho do složky "
                            "podkladů nebo zapiš celou cestu." % (nazev, cas, hledano))


@lru_cache(maxsize=64)
def _rozmer_originalu(cesta):
    with Image.open(cesta) as im:
        return im.size


def rozmer_obrazku(cesta, sirka, pomer_max):
    """Rozměr obrázku v kartě pro danou šířku: poměr stran zachovaný, výška nejvýš pomer_max × šířka (ořez)."""
    w, h = _rozmer_originalu(str(cesta))
    vyska = max(1, int(round(h * sirka / w)))
    vyska = min(vyska, int(round(pomer_max * sirka)))
    return int(sirka), int(vyska)


@lru_cache(maxsize=32)
def _nacti_obrazek(cesta, sirka, vyska, vyrez="auto"):
    """Obrázek zmenšený na šířku sirka, RGBA; když je po zmenšení vyšší než vyska, ořízne se (shora u snímku
    obrazovky, ze středu u fotky). Drží se v mezipaměti podle cesty a rozměru."""
    with Image.open(cesta) as im:
        im = im.convert("RGBA")
        w, h = im.size
        prirozena = max(1, int(round(h * sirka / w)))
        if prirozena > vyska + 1:
            im = im.resize((int(sirka), prirozena), Image.LANCZOS)
            if vyrez == "auto":
                vyrez = "nahore" if str(cesta).lower().endswith(".png") else "stred"
            y0 = {"nahore": 0, "stred": int((prirozena - vyska) / 2), "dole": prirozena - int(vyska)}.get(vyrez, 0)
            return im.crop((0, y0, int(sirka), y0 + int(vyska)))
        return im.resize((int(sirka), int(vyska)), Image.LANCZOS)


# ---------------------------------------------------------------- geometrie

def _otoceny_rozmer(sirka, vyska, naklon):
    """Rozměr obdélníku opsaného kartě po otočení o naklon stupňů."""
    a = math.radians(abs(naklon))
    return sirka * math.cos(a) + vyska * math.sin(a), sirka * math.sin(a) + vyska * math.cos(a)


def _naklony(spec, styl, n):
    zadane = spec.get("naklon")
    vychozi = list(_s(styl, "naklony")) or [0]
    out = []
    for i in range(n):
        if isinstance(zadane, (list, tuple)) and i < len(zadane) and zadane[i] is not None:
            out.append(float(zadane[i]))
        else:
            out.append(float(vychozi[i % len(vychozi)]))
    return out


def rozlozeni(spec, styl, sirka_karty, cesty, y, sirka_platna, pomer_max=None, podil_posunu=1.0):
    """Vějíř karet dané šířky s horním okrajem na y. Vrátí slovník s kartami a sjednocením, nebo None, když se
    karty vodorovně nevejdou do pásma mezi okraji BOK (překryv by byl větší než 75 %).
    pomer_max: nejvyšší poměr výška/šířka obrázku (výchozí ze stylu, 4:5); podil_posunu: násobek svislých odsazení."""
    n = len(cesty)
    ram = int(_s(styl, "ram"))
    if pomer_max is None:
        pomer_max = float(_s(styl, "pomer_max"))
    naklony = _naklony(spec, styl, n)
    posuny = list(_s(styl, "posuny_y")) or [0]
    karty = []
    for i, cesta in enumerate(cesty):
        so, vo = rozmer_obrazku(cesta, max(1, int(sirka_karty) - 2 * ram), pomer_max)
        sk, vk = so + 2 * ram, vo + 2 * ram
        rw, rh = _otoceny_rozmer(sk, vk, naklony[i])
        karty.append({"cesta": str(cesta), "sirka_obrazku": so, "vyska_obrazku": vo, "sirka_karty": sk, "vyska_karty": vk,
                      "naklon": naklony[i], "rw": rw, "rh": rh,
                      "posun_y": int(round(posuny[i % len(posuny)] * podil_posunu))})
    volno = sirka_platna - 2 * BOK
    krok = (1.0 - float(_s(styl, "prekryv"))) * sirka_karty
    if n > 1:
        nejsirsi = max(k["rw"] for k in karty)
        krok = min(krok, (volno - nejsirsi) / (n - 1))
        if krok < 0.25 * sirka_karty:
            return None
    else:
        krok = 0
    for i, k in enumerate(karty):
        k["levy"] = i * krok
    u0 = min(k["levy"] for k in karty)
    u1 = max(k["levy"] + k["rw"] for k in karty)
    posun_x = (sirka_platna - (u1 - u0)) / 2 - u0
    for k in karty:
        x0 = k["levy"] + posun_x
        y0 = y + k["posun_y"]
        k["obdelnik"] = [int(round(x0)), int(round(y0)), int(round(x0 + k["rw"])), int(round(y0 + k["rh"]))]
        k["cx"], k["cy"] = x0 + k["rw"] / 2, y0 + k["rh"] / 2
        for pomocny in ("levy", "rw", "rh"):
            k.pop(pomocny)
    x0 = min(k["obdelnik"][0] for k in karty)
    y0 = min(k["obdelnik"][1] for k in karty)
    x1 = max(k["obdelnik"][2] for k in karty)
    y1 = max(k["obdelnik"][3] for k in karty)
    return {"karty": karty, "x": x0, "y": y0, "sirka": x1 - x0, "vyska": y1 - y0}


# ---------------------------------------------------------------- rozhraní prvku

def pripravit(spec, styl, kontext):
    """Najde obrázky, zvolí šířku karet a polohu vějíře nad obličejem a pod horním bezpečným pásmem."""
    soubory = spec.get("soubory")
    if not isinstance(soubory, (list, tuple)) or not soubory:
        raise ValueError("Kartičky v čase %.1f s potřebují klíč \"soubory\" se seznamem 1 až %d obrázků."
                         % (spec.get("od", 0), MAX_KARET))
    if len(soubory) > MAX_KARET:
        raise ValueError("Kartičky v čase %.1f s mají %d obrázků, nejvíc jich smí být %d."
                         % (spec.get("od", 0), len(soubory), MAX_KARET))
    cesty = [najdi_soubor(n, spec, kontext) for n in soubory]
    if "sirka_zadana" not in spec:
        spec["sirka_zadana"] = int(spec.get("sirka") or _s(styl, "sirka"))
    spec.setdefault("vyrez", "auto")
    spec.pop("varovani", None)

    horni = int(kontext.get("horni", 220)) + 20
    dolni = int(kontext.get("vyska", VYSKA)) - int(kontext.get("dolni", 450))
    sirka_platna = int(kontext.get("sirka", SIRKA))
    okno = kontext.get("okno")
    strop = min(dolni, STROP_BEZ_OBLICEJE) if not okno else min(dolni, int(okno[1]) - MEZERA_OBLICEJ)

    min_sirka = int(_s(styl, "min_sirka"))
    kandidati = list(range(spec["sirka_zadana"], min_sirka - 1, -20))
    if not kandidati or kandidati[-1] != min_sirka:
        kandidati.append(min_sirka)
    kandidati = [k for k in kandidati if k >= min_sirka] or [min_sirka]

    # 1. celý výřez 4:5 a plný vějíř, od největší šířky; 2. kratší výřez (1:1) a poloviční svislé odsazení
    pomer_max = float(_s(styl, "pomer_max"))
    pruchody = [(pomer_max, 1.0)]
    if pomer_max > 1.0:
        pruchody.append((1.0, 0.5))
    r = None
    for pomer, podil in pruchody:
        for sirka in kandidati:
            r0 = rozlozeni(spec, styl, sirka, cesty, horni, sirka_platna, pomer, podil)
            if r0 is not None and r0["y"] + r0["vyska"] <= strop:
                r = r0
                break
        if r is not None:
            break
    if r is None:
        # nouze: nejmenší šířka co nejvýš, varování pro kontrolu umístění
        sirka = min_sirka
        r = rozlozeni(spec, styl, sirka, cesty, horni, sirka_platna)
        while r is None and sirka > 120:
            sirka -= 20
            r = rozlozeni(spec, styl, sirka, cesty, horni, sirka_platna)
        if r is None:
            raise ValueError("Kartičky v čase %.1f s: %d karet se vedle sebe nevejde ani při šířce 120 px."
                             % (spec.get("od", 0), len(cesty)))
        spec["varovani"] = ("Kartičky (čas %.1f s, %d obrázků) se nevejdou nad obličej ani při šířce %d px, jsou "
                            "položené co nejvýš a mohou obličej zakrývat. Dej jich míň, posuň je v čase, nebo natoč "
                            "záběr s hlavou níž." % (spec.get("od", 0), len(cesty), sirka))
    spec["karty"] = r["karty"]
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = int(r["x"]), int(r["y"]), int(r["sirka"]), int(r["vyska"])
    spec["sirka_karty"] = int(r["karty"][0]["sirka_karty"])
    return None


def _konec_nastupu(spec):
    n = max(1, len(spec.get("karty") or spec.get("soubory") or [1]))
    return (n - 1) * ROZESTUP_S + NABEH_S


def stav(spec, t):
    """Číslo snímku při nástupu karet (0, 1, ...), "s" v klidu, záporné při zmizení, None mimo čas."""
    t_rel, t_konec = t - spec["od"], spec["do"] - t
    if t_rel < 0 or t_konec <= 0:
        return None
    if t_konec < VYSTUP_S:
        return -(int(t_konec * FPS) + 1)
    if t_rel < _konec_nastupu(spec):
        return int(t_rel * FPS)
    return "s"


def obdelnik(spec, styl):
    """Sjednocení karet (bez stínu) po dokončení animace."""
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


# ---------------------------------------------------------------- kreslení

@lru_cache(maxsize=32)
def _karta(cesta, sirka_obrazku, vyska_obrazku, naklon, vyrez, styl_klic):
    """Hotová klidná karta: podklad, rám, obrázek a stín, otočená o naklon. Střed obrázku = střed karty."""
    styl = _styl_ze_klice(styl_klic)
    ram = int(styl["ram"])
    sk, vk = int(sirka_obrazku) + 2 * ram, int(vyska_obrazku) + 2 * ram
    stin = bool(styl["stin"])
    sx, sy = styl["stin_posun"]
    rozmaz = int(styl["stin_rozmaz"])
    pad = int(rozmaz * 2 + max(abs(sx), abs(sy))) if stin else 4
    W, H = sk + 2 * pad, vk + 2 * pad
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if stin:
        vrstva = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(vrstva).rectangle((pad + sx, pad + sy, pad + sx + sk - 1, pad + sy + vk - 1), fill=tuple(styl["stin_barva"]))
        img.alpha_composite(vrstva.filter(ImageFilter.GaussianBlur(rozmaz)))
    d = ImageDraw.Draw(img)
    d.rectangle((pad, pad, pad + sk - 1, pad + vk - 1), fill=tuple(styl["barva_ramu"]))
    d.rectangle((pad + ram, pad + ram, pad + sk - ram - 1, pad + vk - ram - 1), fill=tuple(styl["barva_karty"]))
    obr = _nacti_obrazek(cesta, int(sirka_obrazku), int(vyska_obrazku), vyrez)
    img.alpha_composite(obr, (pad + ram, pad + ram))
    if abs(float(naklon)) > 0.01:
        img = img.rotate(float(naklon), resample=Image.BICUBIC, expand=True)
    return img


def _pruhlednost(img, alfa):
    if alfa >= 1.0:
        return img
    out = img.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), Image.new("L", out.size, int(255 * alfa))))
    return out


def vykresli(spec, styl, k):
    """Snímek pro klíč k ze stav(): karty s nástupem (přílet zespodu, průhlednost) nebo zmizením. Vrátí jen
    výřez kolem karet (včetně stínu a místa pro přílet), ne celé plátno."""
    styl_klic = _styl_klic(styl)
    vyrez = spec.get("vyrez", "auto")
    karty = spec["karty"]
    obrazky, polohy = [], []
    for kt in karty:
        img = _karta(kt["cesta"], int(kt["sirka_obrazku"]), int(kt["vyska_obrazku"]), float(kt["naklon"]), vyrez, styl_klic)
        obrazky.append(img)
        polohy.append((int(round(kt["cx"] - img.width / 2)), int(round(kt["cy"] - img.height / 2))))
    x0 = min(p[0] for p in polohy)
    y0 = min(p[1] for p in polohy)
    x1 = max(p[0] + im.width for p, im in zip(polohy, obrazky))
    y1 = max(p[1] + im.height for p, im in zip(polohy, obrazky)) + NALET_PX
    plat = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for i, (img, (px, py)) in enumerate(zip(obrazky, polohy)):
        alfa, dy = 1.0, 0
        if isinstance(k, int) and k >= 0:
            p = _clamp(((k / FPS) - i * ROZESTUP_S) / NABEH_S)
            if p <= 0:
                continue
            e = _ease_out_cubic(p)
            alfa, dy = e, int(round(NALET_PX * (1 - e)))
        elif isinstance(k, int):
            alfa = _clamp(((-k - 1) / FPS) / VYSTUP_S)
        plat.alpha_composite(_pruhlednost(img, alfa), (px - x0, py - y0 + dy))
    return plat, (x0, y0)
