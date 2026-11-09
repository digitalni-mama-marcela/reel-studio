"""Prvek „štítky“: dvě až pět pilulek s krátkým textem (REEL / CAROUSEL / NEWSLETTER), které naskočí jedna po druhé.

Zadání Marcely (21. 10. 2026): u věty „Třeba nápad na Reel, carousel nebo newsletter“ rychle naskočí tři štítky.
Pilulka = zaoblený obdélník s textem velkým písmem. Každá naskočí s krátkým pružným zvětšením (0,18 s: z 0,6×
přes 1,06× na 1,0×), další o 0,35 s později (nebo podle času slova, když spec dá „casy“). Zůstanou do „do“,
na konci spolu zmizí (0,15 s zmenšení).

Spec v osa["prvky"]:
  {"typ": "stitky", "od": 12.4, "do": 15.0, "texty": ["REEL", "CAROUSEL", "NEWSLETTER"],
   "casy": [12.4, 12.9, 13.5],      # volitelně: čas naskočení každého štítku (sekundy v reelu)
   "y": 700}                        # volitelně: střed bloku svisle (jinak se najde místo mimo obličej)
  texty   2 až 5 krátkých textů (kreslí se velkými písmeny, když styl má "velka": True)

Rozložení: vedle sebe do řádku, když se vejdou (šířka všech + mezery ≤ 900 px), jinak pod sebou. Vždy uprostřed
šířky. Blok nesmí být v horních 220 px ani spodních 450 px. Poloha bez zadaného „y“: nahoře pod bezpečným pásmem;
když by zakrýval obličej, pod bradou nad titulky, nebo nad obličejem; když se nevejde nikam, nahoře a do
spec["varovani"] jde česká hláška (kontrola umístění ji nahlásí).

pripravit() doplní spec["pilulky"] (text, střed, rozměr každé pilulky), spec["x"], spec["y"] (levý horní roh bloku),
spec["sirka"], spec["vyska"], spec["velikost"] a spec["casy_naskoceni"] (čas naskočení každého štítku v sekundách
reelu). Zvuk prvek nemíchá: hlavní program k časům naskočení přidá „klik“ (studio/zvuky.py), pomůže zvuky(spec).

Kreslení: každá pilulka se vykreslí jednou (mezipaměť), při animaci se jen zmenší nebo zvětší a položí.
Klíče stav(): číslo snímku při naskakování, "s" v klidu, záporné číslo při mizení, None mimo čas.
"""
import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf",
    "varianta": "ExtraBold",
    "velikost": 64,
    "min_velikost": 44,              # když se pilulky nevejdou, písmo se zmenšuje až sem
    "velka": True,                   # text velkými písmeny
    "barva": (255, 255, 255),        # text
    "podklad": (212, 139, 160),      # pilulka: pudrově růžová značky (marker z mini_silny vzhledu marcela)
    "pad": (40, 18),                 # vnitřní okraj pilulky (vodorovně, svisle)
    "mezera": 24,                    # mezera mezi pilulkami v řádku
    "mezera_svisle": 18,             # mezera mezi pilulkami pod sebou
    "max_sirka": 900,                # řádek vedle sebe jen do této šířky
    "stin": 90,                      # průhlednost stínu 0..255 (0 = bez stínu)
}

NASKOK_S = 0.18          # pružné zvětšení jedné pilulky
ROZESTUP_S = 0.35        # další pilulka o tolik později
VYSTUP_S = 0.15          # zmizení všech na konci
MERITKO_OD = 0.6         # odkud pilulka naskočí
MERITKO_PRES = 1.06      # přes kolik se přehoupne
MIN_TEXTU, MAX_TEXTU = 2, 5
MEZERA_OBLICEJ = 40      # odstup bloku od okna obličeje
TITULKY_REZERVA = 230    # výška, kterou si nad spodním pásmem nechávají titulky
PAD_PLATNA = 36          # okraj kolem bloku (stín a přehoupnutí přes 1,0×)


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _hash(hodnota):
    if isinstance(hodnota, (list, tuple)):
        return tuple(_hash(h) for h in hodnota)
    return hodnota


def _styl_klic(st):
    return tuple((k, _hash(st[k])) for k in sorted(VYCHOZI_STYL))


def _clamp(x):
    return max(0.0, min(1.0, x))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _meritko_naskoku(p):
    """Měřítko pilulky v postupu naskočení p (0..1): 0,6× → 1,06× (rychle, zpomaluje) → 1,0× (měkce zpět)."""
    if p <= 0:
        return MERITKO_OD
    if p >= 1:
        return 1.0
    if p < 0.62:
        q = _ease_out_cubic(p / 0.62)
        return MERITKO_OD + (MERITKO_PRES - MERITKO_OD) * q
    q = (p - 0.62) / 0.38
    return MERITKO_PRES + (1.0 - MERITKO_PRES) * (0.5 - 0.5 * math.cos(math.pi * q))


def _text(text, st):
    t = " ".join(str(text).split())
    return t.upper() if st.get("velka") else t


# ---------------------------------------------------------------- rozložení

def _rozmer_pilulky(text, velikost, st):
    """(šířka, výška) pilulky s textem v dané velikosti písma."""
    font = pismo(st["pismo"], int(velikost), st["varianta"])
    asc, desc = font.getmetrics()
    px, py = st["pad"]
    w = int(math.ceil(font.getlength(_text(text, st)))) + 2 * int(px)
    h = asc + desc + 2 * int(py)
    return w, h


def rozlozeni(texty, velikost, st):
    """Pilulky v dané velikosti písma vedle sebe (když se vejdou do max_sirka), jinak pod sebou. Vrátí slovník
    {"pilulky": [{"text", "w", "h", "dx", "dy"}], "sirka", "vyska", "radek": True/False}; dx, dy jsou polohy
    levého horního rohu vůči levému hornímu rohu bloku."""
    rozmery = [_rozmer_pilulky(t, velikost, st) for t in texty]
    mezera, mezera_sv = int(st["mezera"]), int(st["mezera_svisle"])
    sirka_radku = sum(w for w, _ in rozmery) + mezera * (len(rozmery) - 1)
    pilulky = []
    if sirka_radku <= int(st["max_sirka"]):
        vyska = max(h for _, h in rozmery)
        x = 0
        for t, (w, h) in zip(texty, rozmery):
            pilulky.append({"text": t, "w": w, "h": h, "dx": x, "dy": int((vyska - h) / 2)})
            x += w + mezera
        return {"pilulky": pilulky, "sirka": sirka_radku, "vyska": vyska, "radek": True}
    sirka = max(w for w, _ in rozmery)
    y = 0
    for t, (w, h) in zip(texty, rozmery):
        pilulky.append({"text": t, "w": w, "h": h, "dx": int((sirka - w) / 2), "dy": y})
        y += h + mezera_sv
    return {"pilulky": pilulky, "sirka": sirka, "vyska": y - mezera_sv, "radek": False}


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _texty(spec):
    texty = spec.get("texty")
    if not isinstance(texty, (list, tuple)) or not all(isinstance(t, str) and t.strip() for t in texty):
        raise ValueError("Štítky v čase %.1f s potřebují klíč \"texty\" se seznamem %d až %d krátkých textů."
                         % (spec.get("od", 0), MIN_TEXTU, MAX_TEXTU))
    if not MIN_TEXTU <= len(texty) <= MAX_TEXTU:
        raise ValueError("Štítky v čase %.1f s mají %d textů, musí jich být %d až %d."
                         % (spec.get("od", 0), len(texty), MIN_TEXTU, MAX_TEXTU))
    return [str(t) for t in texty]


def _casy_rel(spec):
    """Časy naskočení jednotlivých štítků v sekundách od začátku prvku (z „casy“, jinak rozestup 0,35 s)."""
    n = len(spec.get("pilulky") or spec.get("texty") or [])
    od, do = float(spec["od"]), float(spec["do"])
    nejpozdeji = max(0.0, do - od - VYSTUP_S - NASKOK_S)
    zadane = spec.get("casy")
    out = []
    for i in range(n):
        if isinstance(zadane, (list, tuple)) and i < len(zadane) and zadane[i] is not None:
            t = float(zadane[i]) - od
        elif out:
            t = out[-1] + ROZESTUP_S
        else:
            t = 0.0
        out.append(round(min(max(0.0, t), nejpozdeji), 3))
    return out


def casy(spec):
    """(časy naskočení od začátku prvku, konec naskakování) v sekundách."""
    starty = _casy_rel(spec)
    konec = (max(starty) + NASKOK_S) if starty else 0.0
    return starty, konec


def zvuky(spec):
    """Návrh zvuků pro hlavní program: „klik“ při každém naskočení (prvek sám nic nemíchá)."""
    return [{"typ": "klik", "cas": round(c, 2), "db": -20} for c in spec.get("casy_naskoceni", [])]


# ---------------------------------------------------------------- rozhraní prvku

def pripravit(spec, styl, kontext):
    """Zvolí velikost písma a rozložení (řádek, nebo sloupec), najde polohu mimo obličej a bezpečná pásma."""
    st = _styl(styl)
    texty = _texty(spec)
    if "stred_y_zadany" not in spec:
        spec["stred_y_zadany"] = spec.get("y")
    spec.pop("varovani", None)
    horni = int(kontext.get("horni", HORNI_OKRAJ)) + 20
    dolni = int(kontext.get("vyska", VYSKA)) - int(kontext.get("dolni", DOLNI_OKRAJ))
    sirka_platna = int(kontext.get("sirka", SIRKA))
    okno = kontext.get("okno")

    # velikost písma: od zadané dolů, dokud se blok vejde na šířku (mezi okraje BOK) i na výšku pásma
    velikost = int(spec.get("velikost_zadana") or st["velikost"])
    spec["velikost_zadana"] = velikost
    r = None
    while True:
        r0 = rozlozeni(texty, velikost, st)
        if (r0["sirka"] <= sirka_platna - 2 * BOK and r0["vyska"] <= dolni - horni) or velikost - 4 < int(st["min_velikost"]):
            r = r0
            break
        velikost -= 4
    if r["sirka"] > sirka_platna - 2 * BOK:
        spec["varovani"] = ("Štítek \"%s\" (čas %.1f s) je moc dlouhý: ani při písmu %d px se nevejde na šířku. Zkrať ho."
                            % (max(texty, key=len), spec["od"], velikost))
    w, h = r["sirka"], r["vyska"]
    x = int((sirka_platna - w) / 2)

    # poloha: zadaný střed, jinak nahoře pod pásmem, pod bradou nad titulky, nad obličejem, nouzově nahoře
    kandidati = []
    if spec["stred_y_zadany"] is not None:
        kandidati.append(("zadano", int(round(float(spec["stred_y_zadany"]) - h / 2))))
    kandidati.append(("nahore", horni))
    if okno:
        kandidati.append(("pod_bradou", int(okno[3]) + MEZERA_OBLICEJ))
        kandidati.append(("nad_oblicejem", int(okno[1]) - MEZERA_OBLICEJ - h))
    spec.pop("nad_oblicejem", None)
    y = None
    for kde, y0 in kandidati:
        y0 = max(horni, min(y0, dolni - h))
        if kde == "pod_bradou" and y0 + h > dolni - TITULKY_REZERVA and not spec.get("skryt_titulky"):
            continue
        if okno and _protina((x, y0, x + w, y0 + h), okno):
            continue
        y = y0
        if kde == "nad_oblicejem":
            spec["nad_oblicejem"] = True
        break
    if y is None:
        y = horni
        spec["varovani"] = ("Štítky v čase %.1f s se nevešly mimo obličej, leží nahoře a mohou překrýt vlasy. "
                            "Posuň je v čase, nebo dej míň štítků." % spec["od"])
    elif spec["stred_y_zadany"] is not None and kandidati[0][1] != y and okno:
        spec["varovani"] = ("Štítky v čase %.1f s: zadaná výška by zakryla obličej, blok je posunutý." % spec["od"])

    spec["pilulky"] = [{"text": _text(p["text"], st), "w": p["w"], "h": p["h"],
                        "cx": x + p["dx"] + p["w"] / 2, "cy": y + p["dy"] + p["h"] / 2} for p in r["pilulky"]]
    spec["radek"] = bool(r["radek"])
    spec["velikost"] = int(velikost)
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = int(x), int(y), int(w), int(h)
    starty, _ = casy(spec)
    spec["casy_naskoceni"] = [round(float(spec["od"]) + s, 2) for s in starty]
    return None


def stav(spec, t):
    """Číslo snímku při naskakování (0, 1, …), "s" v klidu, záporné při mizení, None mimo čas."""
    t_rel, zbyva = t - float(spec["od"]), float(spec["do"]) - t
    if t_rel < 0 or zbyva <= 0:
        return None
    if zbyva < VYSTUP_S:
        return -(int(zbyva * FPS) + 1)
    _, konec = casy(spec)
    if t_rel < konec:
        return int(t_rel * FPS)
    return "s"


def obdelnik(spec, styl):
    """Plocha bloku pilulek po dokončení animace: (x0, y0, x1, y1)."""
    if "pilulky" not in spec:
        pripravit(spec, styl, {"okno": None})
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


# ---------------------------------------------------------------- kreslení

@lru_cache(maxsize=64)
def _pilulka(text, velikost, styl_klic):
    """Hotová pilulka (RGBA, bez stínu): zaoblený obdélník s textem uprostřed. Kreslí se jednou, pak se jen škáluje."""
    st = dict(styl_klic)
    font = pismo(st["pismo"], int(velikost), st["varianta"])
    w, h = _rozmer_pilulky(text, velikost, st)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=tuple(st["podklad"])[:3] + (255,))
    asc, desc = font.getmetrics()
    px, py = st["pad"]
    d.text((int(px), int(py)), text, font=font, fill=tuple(st["barva"])[:3] + (255,))
    return img


@lru_cache(maxsize=64)
def _stin(text, velikost, styl_klic):
    """Měkký stín pod pilulkou (o PAD_PLATNA větší než pilulka), nebo None bez stínu."""
    st = dict(styl_klic)
    alfa = int(st["stin"])
    if alfa <= 0:
        return None
    pil = _pilulka(text, velikost, styl_klic)
    maska = Image.new("L", (pil.width + 2 * PAD_PLATNA, pil.height + 2 * PAD_PLATNA), 0)
    maska.paste(pil.getchannel("A"), (PAD_PLATNA, PAD_PLATNA + 8))
    maska = maska.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * alfa / 255))
    stin = Image.new("RGBA", maska.size, (0, 0, 0, 0))
    stin.putalpha(maska)
    return stin


def _poloz(platno, vrstva, cx, cy, meritko, alfa):
    """Položí vrstvu se středem (cx, cy) na plátno, zmenšenou nebo zvětšenou na meritko a s průhledností alfa."""
    if meritko <= 0.01 or alfa <= 0.0:
        return
    if abs(meritko - 1.0) > 0.002:
        w = max(1, int(round(vrstva.width * meritko)))
        h = max(1, int(round(vrstva.height * meritko)))
        vrstva = vrstva.resize((w, h), Image.BILINEAR)
    if alfa < 1.0:
        vrstva = vrstva.copy()
        vrstva.putalpha(ImageChops.multiply(vrstva.getchannel("A"), Image.new("L", vrstva.size, int(255 * alfa))))
    x, y = int(round(cx - vrstva.width / 2)), int(round(cy - vrstva.height / 2))
    ox, oy = max(0, -x), max(0, -y)
    if ox >= vrstva.width or oy >= vrstva.height or x >= platno.width or y >= platno.height:
        return
    platno.alpha_composite(vrstva, (max(0, x), max(0, y)), (ox, oy))


def vykresli(spec, styl, klic):
    """Snímek prvku pro klíč ze stav(). Vrátí (RGBA obrázek bloku s okrajem, (x, y) na plátně 1080x1920)."""
    st = _styl(styl)
    sk = _styl_klic(st)
    velikost = int(spec["velikost"])
    starty, _ = casy(spec)
    x0, y0 = int(spec["x"]) - PAD_PLATNA, int(spec["y"]) - PAD_PLATNA
    platno = Image.new("RGBA", (int(spec["sirka"]) + 2 * PAD_PLATNA, int(spec["vyska"]) + 2 * PAD_PLATNA), (0, 0, 0, 0))
    if klic == "s":
        t_rel, mizeni = None, None
    elif klic >= 0:
        t_rel, mizeni = klic / FPS, None
    else:
        t_rel, mizeni = None, _clamp(((-klic - 1) / FPS) / VYSTUP_S)   # 1 = právě začíná mizet, 0 = pryč
    for p, start in zip(spec["pilulky"], starty):
        if t_rel is None:
            meritko, alfa = 1.0, 1.0
        else:
            postup = _clamp((t_rel - start) / NASKOK_S)
            if t_rel < start:
                continue
            meritko, alfa = _meritko_naskoku(postup), _clamp(postup / 0.3)
        if mizeni is not None:
            e = mizeni * mizeni                       # zrychlené zmenšení
            meritko, alfa = MERITKO_OD + (1.0 - MERITKO_OD) * e, e
        cx, cy = p["cx"] - x0, p["cy"] - y0
        stin = _stin(p["text"], velikost, sk)
        if stin is not None:
            _poloz(platno, stin, cx, cy, meritko, alfa)
        _poloz(platno, _pilulka(p["text"], velikost, sk), cx, cy, meritko, alfa)
    return platno, (x0, y0)
