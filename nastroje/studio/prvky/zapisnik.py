"""Prvek „zápisník“: karta z linkovaného papíru s kroužkovou vazbou, nadpis a seznam, který se odškrtává po jedné.

Zadání Marcely 29. 10. 2026. Typ videa: mluvící video, kde osoba vyjmenuje, co všechno
se udělalo (seznam úkolů), a položky se na kartě postupně odškrtnou.

Vzhled (ODHAD ze snímků): krémový papír s modrošedými linkami a růžovou svislou linkou okraje, nahoře tmavé kroužky,
jemný stín, náklon asi 1,5 stupně. Nadpis a položky ručně psaným písmem; to zatím nemáme s ověřenou licencí,
proto Instrument Serif Italic (OFL). U položky čtvereček, do kterého se tahem nakreslí fajfka, kolem krátce
zajiskří zlaté hvězdičky.

Spec v osa["prvky"]:
  {"typ": "zapisnik", "od": 3.0, "do": 9.5, "nadpis": "Co dnes udělal Claude",
   "polozky": ["Střih", "Titulky", "Text na obrazovku"], "casy": [4.5, 6.0, 7.5], "y": 420}
  nadpis    volitelné, první řádek karty
  polozky   1 až 6 položek (krátké; dlouhé se zmenší písmem)
  casy      volitelné, čas (s od začátku reelu), kdy se položka objeví a odškrtne; bez nich rovnoměrně
            od 0,8 s po začátku do 0,6 s před koncem
  y         volitelné, horní okraj karty; výchozí 420 px, když tam není obličej, jinak nad něj nebo pod něj
  emoji     volitelné, znak z balicek/pisma/emoji za nadpisem

Po pripravit() jsou v spec: x, y, sirka, vyska (obdélník karty bez kroužků nad ní), velikost (písmo položek),
casy_rel (časy položek od začátku prvku), varovani (když se karta nevejde mezi obličej a bezpečné pásmo).
"""
import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "InstrumentSerif-Italic.ttf",
    "varianta": None,
    "velikost": 58,             # položky
    "min_velikost": 40,
    "nadpis_pomer": 1.12,       # nadpis o tolik větší než položky
    "sirka": 820,
    "papir": (252, 248, 238),
    "linka": (196, 210, 226),
    "okraj_linka": (232, 170, 180),
    "inkoust": (38, 36, 46),
    "fajfka": (38, 36, 46),
    "krouzky": (70, 70, 78),
    "jiskry": (240, 196, 80),
    "stin": 110,
    "rohy": 18,
    "naklon": -1.5,
}

VSTUP_S = 0.35              # karta vyjede shora
VYSTUP_S = 0.25             # zmizení na konci
POLOZKA_S = 0.25            # položka se objeví
FAJFKA_OD_S = 0.15          # fajfka začne po objevení položky
FAJFKA_S = 0.22             # tah fajfky
JISKRY_S = 0.40             # třpyt kolem čtverečku
VJEZD_PX = 90               # odkud karta vyjíždí (px nad cílem)
PAD_X, PAD_Y = 56, 26       # vnitřní okraje karty
KROUZKY_NAD = 26            # kroužky přesahují nad kartu
MEZERA_OKOLO = 40           # odstup od obličeje
LEM = 40                    # průhledný lem obrázku (stín, náklon, jiskry)
VYCHOZI_Y = 420


def _clamp(x):
    return max(0.0, min(1.0, x))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _ease_out_back(p):
    c1 = 1.70158
    return 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _klic_stylu(styl):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in styl.items()))


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _radek(velikost):
    """Výška řádku položky (zároveň rozestup linek papíru)."""
    return int(round(velikost * 1.32))


def _rozmery(spec, styl, velikost):
    """(šířka, výška karty, výška nadpisu, výška řádku, vejde se do šířky)."""
    w = int(styl["sirka"])
    radek = _radek(velikost)
    nadpis_h = _radek(int(velikost * styl["nadpis_pomer"])) + 10 if spec.get("nadpis") else 0
    h = PAD_Y + KROUZKY_NAD // 2 + nadpis_h + radek * len(spec["polozky"]) + PAD_Y
    f = pismo(styl["pismo"], velikost, styl["varianta"])
    ctverec = int(velikost * 0.72)
    volno = w - 2 * PAD_X - ctverec - 22
    vejde = all(f.getlength(p) <= volno for p in spec["polozky"])
    if spec.get("nadpis"):
        fn = pismo(styl["pismo"], int(velikost * styl["nadpis_pomer"]), styl["varianta"])
        vejde = vejde and fn.getlength(spec["nadpis"]) + (velikost if spec.get("emoji") else 0) <= w - 2 * PAD_X
    return w, h, nadpis_h, radek, vejde


def pripravit(spec, styl, kontext):
    """Zvolí velikost písma, polohu mimo obličej a časy položek."""
    styl = _styl(styl)
    polozky = [str(p).strip() for p in spec.get("polozky") or [] if str(p).strip()]
    if not polozky:
        raise ValueError("Zápisník: zadej aspoň jednu položku (polozky).")
    if len(polozky) > 6:
        raise ValueError("Zápisník: nejvíc 6 položek, zadáno %d." % len(polozky))
    spec["polozky"] = polozky
    velikost = int(styl["velikost"])
    while True:
        w, h, _, _, vejde = _rozmery(spec, styl, velikost)
        if vejde or velikost <= styl["min_velikost"]:
            break
        velikost -= 2
    spec["velikost"] = velikost
    if not vejde:
        spec["varovani"] = "text je na kartu dlouhý, zkrať položku nebo nadpis"

    horni = kontext.get("horni", HORNI_OKRAJ) + KROUZKY_NAD + 10
    dolni = kontext.get("vyska", VYSKA) - kontext.get("dolni", DOLNI_OKRAJ) - 10
    x = int(spec.get("x", (SIRKA - w) // 2))
    x = max(BOK // 2, min(SIRKA - BOK // 2 - w, x))
    y = int(spec.get("y", styl.get("y", VYCHOZI_Y)))
    okno = kontext.get("okno")
    if okno and _protina((x, y, x + w, y + h), okno):
        # nahoře jako ve vzoru: nad hlavu, nebo přes vlasy (horních 28 % okna obličeje, jako u nadpisů), i s menším
        # písmem (nejmíň min_velikost); teprve potom pod bradu s původní velikostí
        puvodni = velikost
        y_nahore = None
        while y_nahore is None:
            w, h, _, _, _ = _rozmery(spec, styl, velikost)
            nad = int(okno[1]) - MEZERA_OKOLO - h
            nad_vlasy = int(okno[1] + 0.28 * (okno[3] - okno[1])) - 10 - h
            if nad >= horni:
                y_nahore = nad
            elif nad_vlasy >= horni:
                y_nahore, spec["nad_oblicejem"] = nad_vlasy, True
            elif velikost - 2 >= styl["min_velikost"]:
                velikost -= 2
            else:
                break
        if y_nahore is not None:
            y = y_nahore
        else:
            velikost = puvodni
            w, h, _, _, _ = _rozmery(spec, styl, velikost)
            pod = int(okno[3]) + MEZERA_OKOLO
            if pod + h <= dolni:
                y = pod
            else:
                y = max(horni, int(okno[1]) - MEZERA_OKOLO - h)
                spec["varovani"] = "karta se nevejde mimo obličej, zakryje ho zčásti (zkus méně položek)"
        spec["velikost"] = velikost
    y = max(horni, min(dolni - h, y))
    spec.update({"x": x, "y": y, "sirka": w, "vyska": h})

    delka = spec["do"] - spec["od"]
    if spec.get("casy"):
        casy = [max(0.0, float(c) - spec["od"]) for c in spec["casy"]][:len(polozky)]
        while len(casy) < len(polozky):
            casy.append(casy[-1] + 1.2 if casy else 0.8)
    else:
        zacatek, konec = min(0.8, delka * 0.2), max(0.9, delka - 0.6 - FAJFKA_OD_S - FAJFKA_S)
        krok = (konec - zacatek) / max(1, len(polozky) - 1) if len(polozky) > 1 else 0
        casy = [zacatek + i * krok for i in range(len(polozky))]
    # první položka až po vjezdu karty, další aspoň 0,5 s po předchozí (slovo zaznělo dřív, než karta vyjela)
    for i in range(len(casy)):
        casy[i] = max(casy[i], VSTUP_S + 0.15 if i == 0 else casy[i - 1] + 0.5)
    spec["casy_rel"] = [round(c, 3) for c in casy]


def obdelnik(spec, styl):
    return spec["x"], spec["y"] - KROUZKY_NAD, spec["x"] + spec["sirka"], spec["y"] + spec["vyska"]


def _konec_animace(spec):
    return max(spec["casy_rel"]) + FAJFKA_OD_S + max(FAJFKA_S, JISKRY_S) if spec["casy_rel"] else VSTUP_S


def stav(spec, t):
    """Číslo snímku animace, 's' v klidu, záporné číslo při mizení, None mimo čas prvku."""
    t_rel = t - spec["od"]
    if t_rel < 0 or t >= spec["do"]:
        return None
    zbyva = spec["do"] - t
    if zbyva < VYSTUP_S:
        return -(int(zbyva * FPS) + 1)
    if t_rel < max(VSTUP_S, _konec_animace(spec)):
        return int(t_rel * FPS)
    return "s"


@lru_cache(maxsize=16)
def _papir(nadpis, emoji, n, velikost, ks):
    """Prázdná karta s nadpisem, linkami a kroužky (RGBA i s lemem). Pamatuje se."""
    styl = dict(ks)
    spec = {"nadpis": nadpis, "emoji": emoji, "polozky": ["x"] * n}
    w, h, nadpis_h, radek, _ = _rozmery(spec, styl, velikost)
    im = Image.new("RGBA", (w + 2 * LEM, h + 2 * LEM + KROUZKY_NAD), (0, 0, 0, 0))
    ox, oy = LEM, LEM + KROUZKY_NAD
    if styl.get("stin"):
        stin = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(stin).rounded_rectangle((ox + 6, oy + 12, ox + w + 6, oy + h + 12), radius=styl["rohy"],
                                               fill=(30, 22, 28, int(styl["stin"])))
        im.alpha_composite(stin.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((ox, oy, ox + w, oy + h), radius=styl["rohy"], fill=tuple(styl["papir"]) + (255,))
    # linky papíru: pod nadpisem a pod každou položkou, svislá linka okraje vlevo
    zac = oy + PAD_Y + KROUZKY_NAD // 2 + nadpis_h
    for i in range(n + 1):
        yl = zac + i * radek - 4
        if yl < oy + h - 10:
            d.line((ox + 14, yl, ox + w - 14, yl), fill=tuple(styl["linka"]) + (255,), width=2)
    d.line((ox + PAD_X - 18, oy + 8, ox + PAD_X - 18, oy + h - 8), fill=tuple(styl["okraj_linka"]) + (255,), width=2)
    # kroužková vazba: díra v papíru a kovový oblouk přes horní hranu
    pocet = max(5, w // 90)
    krok = (w - 80) / (pocet - 1)
    for i in range(pocet):
        cx = ox + 40 + i * krok
        d.ellipse((cx - 8, oy + 14, cx + 8, oy + 30), fill=(205, 198, 186, 255))
        d.rounded_rectangle((cx - 7, oy - KROUZKY_NAD, cx + 7, oy + 24), radius=7,
                            outline=tuple(styl["krouzky"]) + (255,), width=5)
    if nadpis:
        vn = int(velikost * styl["nadpis_pomer"])
        fn = pismo(styl["pismo"], vn, styl["varianta"])
        ty = oy + PAD_Y + KROUZKY_NAD // 2
        d.text((ox + PAD_X, ty), nadpis, font=fn, fill=tuple(styl["inkoust"]) + (255,))
        if emoji:
            from ..efekty import _emoji_obrazek
            e = _emoji_obrazek(emoji, int(vn * 0.9))
            if e is not None:
                im.alpha_composite(e, (int(ox + PAD_X + fn.getlength(nadpis) + 14), int(ty + vn * 0.12)))
    return im


def _fajfka(d, x0, y0, s, p, barva, tl):
    """Fajfka do čtverečku o straně s, nakreslená do podílu p (0 až 1)."""
    a, b, c = (x0 + s * 0.20, y0 + s * 0.52), (x0 + s * 0.42, y0 + s * 0.76), (x0 + s * 0.84, y0 + s * 0.20)
    l1, l2 = math.dist(a, b), math.dist(b, c)
    delka = (l1 + l2) * p
    if delka <= 0:
        return
    if delka <= l1:
        k = delka / l1
        d.line((a, (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)), fill=barva, width=tl)
        return
    k = (delka - l1) / l2
    d.line((a, b, (b[0] + (c[0] - b[0]) * k, b[1] + (c[1] - b[1]) * k)), fill=barva, width=tl, joint="curve")


def _jiskry(d, cx, cy, s, p, barva):
    """Zlaté čtyřcípé hvězdičky, které se rozletí od čtverečku a zhasnou."""
    if p <= 0 or p >= 1:
        return
    alfa = int(255 * (1 - p) ** 1.5)
    for i in range(7):
        uhel = i * 2 * math.pi / 7 + 0.4
        r = s * (0.7 + 0.9 * _ease_out_cubic(p))
        x, y = cx + math.cos(uhel) * r, cy + math.sin(uhel) * r
        v = s * 0.16 * (1 - 0.5 * p) * (1.0 if i % 2 else 0.7)
        d.polygon([(x, y - v), (x + v * 0.3, y - v * 0.3), (x + v, y), (x + v * 0.3, y + v * 0.3),
                   (x, y + v), (x - v * 0.3, y + v * 0.3), (x - v, y), (x - v * 0.3, y - v * 0.3)],
                  fill=tuple(barva) + (alfa,))


def vykresli(spec, styl, klic):
    """Snímek prvku pro klíč z stav(). Vrátí (RGBA obrázek, (x, y) na plátně 1080x1920)."""
    styl = _styl(styl)
    ks = _klic_stylu(styl)
    if klic == "s":
        t_rel, alfa_celku = 99.0, 1.0
    elif klic >= 0:
        t_rel, alfa_celku = klic / FPS, 1.0
    else:
        t_rel, alfa_celku = 99.0, _clamp(((-klic - 1) / FPS) / VYSTUP_S)
    velikost = spec["velikost"]
    im = _papir(spec.get("nadpis") or "", spec.get("emoji") or "", len(spec["polozky"]), velikost, ks).copy()
    w, h, nadpis_h, radek, _ = _rozmery(spec, styl, velikost)
    ox, oy = LEM, LEM + KROUZKY_NAD
    d = ImageDraw.Draw(im)
    f = pismo(styl["pismo"], velikost, styl["varianta"])
    s = int(velikost * 0.72)
    inkoust = tuple(styl["inkoust"])
    zac = oy + PAD_Y + KROUZKY_NAD // 2 + nadpis_h
    for i, text in enumerate(spec["polozky"]):
        t0 = spec["casy_rel"][i]
        p = _clamp((t_rel - t0) / POLOZKA_S)
        if p <= 0:
            continue
        a = int(255 * _ease_out_cubic(p))
        posun = int(16 * (1 - _ease_out_cubic(p)))
        ry = zac + i * radek
        bx, by = ox + PAD_X, ry + (radek - s) // 2 - 6
        d.rounded_rectangle((bx + posun, by, bx + posun + s, by + s), radius=6, outline=inkoust + (a,), width=3)
        d.text((bx + s + 22 + posun, ry + (radek - velikost) // 2 - 10), text, font=f, fill=inkoust + (a,))
        pf = _clamp((t_rel - t0 - FAJFKA_OD_S) / FAJFKA_S)
        _fajfka(d, bx, by, s, _ease_out_cubic(pf), tuple(styl["fajfka"]) + (255,), max(4, s // 8))
        _jiskry(d, bx + s / 2, by + s / 2, s, _clamp((t_rel - t0 - FAJFKA_OD_S) / JISKRY_S), styl["jiskry"])
    # vjezd shora s malým přeskokem, náklon, zmizení
    pv = _clamp(t_rel / VSTUP_S)
    dy = -VJEZD_PX * (1 - _ease_out_back(pv))
    if styl.get("naklon"):
        im = im.rotate(styl["naklon"], resample=Image.BICUBIC, expand=False)
    alfa = alfa_celku * _clamp(pv / 0.4)
    if alfa < 1.0:
        im.putalpha(ImageChops.multiply(im.getchannel("A"), Image.new("L", im.size, int(255 * alfa))))
    x = spec["x"] - LEM
    y = int(round(spec["y"] - KROUZKY_NAD - LEM + dy))
    if x < 0 or y < 0:
        orez = (max(0, -x), max(0, -y), im.width, im.height)
        im = im.crop(orez)
        x, y = max(0, x), max(0, y)
    return im, (x, y)
