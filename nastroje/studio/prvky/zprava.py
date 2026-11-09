"""Prvek "zprava": zpráva, kterou zákaznice píše Claudovi, jako chatová kapsle.

Spec v osa["prvky"]:
  {"typ": "zprava", "od": 6.0, "do": 10.5, "text": "Udělej to víc estetické.",
   "komu": "PRO CLAUDA", "odeslano": "Odesláno",
   "rychlost": 18,                  # volitelně, znaků za sekundu (výchozí 18)
   "odpoved": "Jasně, upravím to."}  # volitelně: krátká odpověď Clauda, druhá kapsle po odeslání

Průběh: text se píše po znacích s blikajícím kurzorem, po dopsání 0,35 s pauza, pak vpravo vyskočí kulaté
tlačítko se šipkou nahoru a štítek nahoře se změní na "odeslano" se zeleným ✓. Když je "odpoved", 0,3 s po
odeslání nastoupí zleva druhá kapsle (švestková s krémovým textem).

pripravit() doplní spec["x"], spec["y"], spec["sirka"], spec["vyska"] (celá plocha včetně odpovědi) a případně
spec["varovani"], když se kapsle nevešla mimo obličej. Klíče stav():
  (n, k)            píše se: n napsaných znaků, k = 0/1 fáze kurzoru (bliká po 0,5 s)
  ("odeslano", i)   i-tý snímek animace po odeslání (tlačítko, ✓, nástup odpovědi)
  "s"               klid po animaci
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import FPS, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf",
    "varianta": "Medium",            # text zprávy
    "velikost": 44,
    "min_velikost": 34,              # při zalamování na 2 řádky se písmo zmenšuje až sem
    "radek": 1.25,                   # výška řádku v násobku velikosti písma
    "barva": (74, 51, 64),           # švestková: text zprávy a kurzor
    "podklad": (251, 246, 239),      # krémová kapsle
    "radius": 34,
    "sirka": 900,
    "pad": (40, 28),                 # vnitřní okraj kapsle (vodorovně, svisle)
    "stin": 70,                      # průhlednost stínu 0..255 (0 = bez stínu)
    "stitek_varianta": "SemiBold",   # malý štítek nahoře (komu / odesláno)
    "stitek_velikost": 26,
    "stitek_prostrkani": 3,          # mezera mezi písmeny štítku v px
    "stitek_barva": (138, 120, 133),
    "tlacitko": (212, 139, 160),     # růžové kulaté tlačítko
    "tlacitko_sipka": (255, 255, 255),
    "tlacitko_prumer": 64,
    "fajfka": (206, 212, 172),       # olivové kolečko u "odesláno"
    "fajfka_barva": (74, 51, 64),    # samotná ✓ v kolečku
    "odpoved_podklad": (74, 51, 64),
    "odpoved_barva": (251, 246, 239),
    "odpoved_velikost": 40,
    "odpoved_varianta": "Medium",
    "odpoved_mezera": 18,            # mezera mezi kapslí zprávy a odpovědí
}

PAUZA_S = 0.35          # pauza po dopsání před odesláním
KURZOR_S = 0.5          # perioda blikání kurzoru (0,5 s vidět, 0,5 s schovaný)
TLACITKO_S = 0.28       # vyskočení tlačítka a ✓
ODPOVED_ZPOZDENI_S = 0.30
ODPOVED_VSTUP_S = 0.35
PAD_STIN = 30           # okraj obrázku kolem kapsle kvůli stínu
TITULKY_REZERVA = 230   # výška, kterou si nad spodním pásmem nechávají titulky


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _clamp(x):
    return max(0.0, min(1.0, x))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _ease_out_back(p):
    c1 = 1.70158
    return 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _zalom(text, font, max_sirka):
    """Rozdělí text na řádky po slovech tak, aby se vešly do max_sirka. Vrátí seznam řádků (text)."""
    slova = text.split()
    radky, radek = [], []
    for s in slova:
        zkouska = " ".join(radek + [s])
        if radek and font.getlength(zkouska) > max_sirka:
            radky.append(" ".join(radek))
            radek = [s]
        else:
            radek.append(s)
    if radek:
        radky.append(" ".join(radek))
    return radky or [""]


def _radky_s_velikosti(text, styl, soubor, varianta, velikost, min_velikost, max_sirka, max_radku=2):
    """Zmenšuje písmo od velikost k min_velikost, dokud se text nevejde na max_radku řádků."""
    v = velikost
    while True:
        font = pismo(soubor, v, varianta)
        radky = _zalom(text, font, max_sirka)
        if len(radky) <= max_radku or v - 2 < min_velikost:
            return v, font, radky
        v -= 2


def rozlozeni(spec, styl):
    """Rozměry kapsle (bez animace): slovník s písmy, řádky a výškami. Šířka je pevná (styl["sirka"])."""
    st = _styl(styl)
    px, py = st["pad"]
    w = int(st["sirka"])
    prumer = int(st["tlacitko_prumer"])
    max_sirka_textu = w - 2 * px - prumer - 16
    velikost, font, radky = _radky_s_velikosti(
        spec["text"], st, st["pismo"], st["varianta"], int(st["velikost"]), int(st["min_velikost"]), max_sirka_textu)
    vr = int(velikost * st["radek"])
    stitek = pismo(st["pismo"], int(st["stitek_velikost"]), st["stitek_varianta"])
    s_asc, s_desc = stitek.getmetrics()
    vyska_stitku = s_asc + s_desc
    mezera = 12
    h1 = py + vyska_stitku + mezera + vr * len(radky) + py
    h1 = max(h1, py + vyska_stitku + mezera + prumer + py)
    out = {"st": st, "w": w, "h1": int(h1), "px": px, "py": py, "velikost": velikost, "font": font, "radky": radky,
           "vr": vr, "stitek": stitek, "vyska_stitku": vyska_stitku, "mezera": mezera, "prumer": prumer,
           "text_y": py + vyska_stitku + mezera, "odpoved": None, "h": int(h1)}
    odp = (spec.get("odpoved") or "").strip()
    if odp:
        ov, ofont, oradky = _radky_s_velikosti(odp, st, st["pismo"], st["odpoved_varianta"], int(st["odpoved_velikost"]),
                                               int(st["min_velikost"]), w - 2 * px)
        ovr = int(ov * st["radek"])
        ow = int(min(w, max(ofont.getlength(r) for r in oradky) + 2 * px))
        oh = int(py + ovr * len(oradky) + py)
        out["odpoved"] = {"velikost": ov, "font": ofont, "radky": oradky, "vr": ovr, "w": ow, "h": oh,
                          "y": out["h1"] + int(st["odpoved_mezera"])}
        out["h"] = out["odpoved"]["y"] + oh
    return out


def _doplnit_rozmery(spec, styl):
    r = rozlozeni(spec, styl)
    spec["sirka"], spec["vyska"] = r["w"], r["h"]
    spec.setdefault("x", int((SIRKA - r["w"]) / 2))
    return r


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def pripravit(spec, styl, kontext):
    """Poloha: nahoře pod bezpečným pásmem, nad obličejem. Když se tam nevejde, pod oknem obličeje nad titulky.
    Když ani tak, nahoře i za cenu překrytí vlasů (spec["varovani"])."""
    r = _doplnit_rozmery(spec, styl)
    horni = kontext.get("horni", 220)
    dolni = kontext.get("dolni", 450)
    vyska_platna = kontext.get("vyska", VYSKA)
    okno = kontext.get("okno")
    x, w, h = spec["x"], r["w"], r["h"]
    spec.pop("varovani", None)
    y_nahore = horni + 20
    if not okno or not _protina((x, y_nahore, x + w, y_nahore + h), okno):
        spec["y"] = int(y_nahore)
        return
    y_pod = int(okno[3]) + 20
    spodni_hranice = vyska_platna - dolni - TITULKY_REZERVA
    if y_pod + h <= spodni_hranice and not _protina((x, y_pod, x + w, y_pod + h), okno):
        spec["y"] = int(y_pod)
        return
    spec["y"] = int(y_nahore)
    spec["varovani"] = "zpráva v čase %.1f s se nevešla mimo obličej, leží nahoře a může překrýt vlasy" % spec["od"]


def _casy(spec):
    """Vrátí (délka psaní, čas odeslání, délka animace po odeslání) v sekundách od začátku prvku."""
    rychlost = float(spec.get("rychlost") or 18)
    n = len(" ".join(spec["text"].split()))
    t_pis = n / rychlost
    t_odeslani = t_pis + PAUZA_S
    animace = TLACITKO_S
    if (spec.get("odpoved") or "").strip():
        animace = max(animace, ODPOVED_ZPOZDENI_S + ODPOVED_VSTUP_S)
    return t_pis, t_odeslani, animace


def stav(spec, t):
    """Klíč snímku v čase t (sekundy od začátku reelu), None mimo <od, do)."""
    if not (spec["od"] <= t < spec["do"]):
        return None
    t_rel = t - spec["od"]
    t_pis, t_odeslani, animace = _casy(spec)
    n_celkem = len(" ".join(spec["text"].split()))
    rychlost = float(spec.get("rychlost") or 18)
    if t_rel < t_odeslani:
        n = min(n_celkem, int(t_rel * rychlost))
        kurzor = int(t_rel / KURZOR_S) % 2
        return (n, kurzor)
    i = int((t_rel - t_odeslani) * FPS)
    if i < int(animace * FPS) + 1:
        return ("odeslano", i)
    return "s"


def obdelnik(spec, styl):
    """Plocha prvku po animaci (kapsle zprávy a případná odpověď): (x0, y0, x1, y1)."""
    if "sirka" not in spec or "vyska" not in spec or "x" not in spec:
        _doplnit_rozmery(spec, styl)
    y = int(spec.get("y", 240))
    return int(spec["x"]), y, int(spec["x"]) + int(spec["sirka"]), y + int(spec["vyska"])


def _stitek(d, x, y, text, r, barva):
    """Prostrkaný štítek velkými písmeny. Vrátí x za posledním písmenem."""
    font, mez = r["stitek"], r["st"]["stitek_prostrkani"]
    for ch in text.upper():
        d.text((x, y), ch, font=font, fill=barva)
        x += font.getlength(ch) + mez
    return x


def _kresli_kapsli(r, n, kurzor, odeslano_p):
    """Krémová kapsle: štítek, text (n znaků), kurzor, tlačítko (odeslano_p = postup animace 0..1, nebo None)."""
    st, w, h, px, py = r["st"], r["w"], r["h1"], r["px"], r["py"]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=st["radius"], fill=tuple(st["podklad"]) + (255,))
    # štítek
    if odeslano_p is None:
        _stitek(d, px, py, r.get("komu", ""), r, tuple(st["stitek_barva"]))
    else:
        konec = _stitek(d, px, py, r.get("odeslano", ""), r, tuple(st["stitek_barva"]))
        prumer = int(r["vyska_stitku"] * 1.1)
        p = _ease_out_back(_clamp(odeslano_p))
        pr = max(2, int(prumer * p))
        cx, cy = konec + 8 + prumer / 2, py + r["vyska_stitku"] / 2
        d.ellipse((cx - pr / 2, cy - pr / 2, cx + pr / 2, cy + pr / 2), fill=tuple(st["fajfka"]) + (255,))
        if p > 0.6:
            s = pr / 2
            d.line([(cx - s * 0.48, cy + s * 0.02), (cx - s * 0.12, cy + s * 0.40), (cx + s * 0.50, cy - s * 0.38)],
                   fill=tuple(st["fajfka_barva"]) + (255,), width=max(2, int(pr * 0.13)), joint="curve")
    # text po znacích
    font, vr, barva = r["font"], r["vr"], tuple(st["barva"]) + (255,)
    asc, desc = font.getmetrics()
    y = r["text_y"]
    poz_kurzoru = (px, y + int((vr - (asc + desc)) / 2))
    zacatek = 0                      # index prvního znaku řádku v celém textu (řádky odděluje jedna mezera)
    for i, radek in enumerate(r["radky"]):
        kolik = max(0, min(len(radek), n - zacatek))
        cast = radek[:kolik]
        yy = y + i * vr + int((vr - (asc + desc)) / 2)
        if cast:
            d.text((px, yy), cast, font=font, fill=barva)
        if n >= zacatek:             # kurzor stojí na posledním řádku, kam už psaní došlo
            poz_kurzoru = (px + font.getlength(cast) + 3, yy)
        zacatek += len(radek) + 1
    if odeslano_p is None and kurzor == 0:
        kx, ky = poz_kurzoru
        d.rounded_rectangle((kx, ky + asc * 0.08, kx + 4, ky + asc + desc * 0.4), radius=2, fill=barva)
    # tlačítko vpravo
    if odeslano_p is not None:
        p = _ease_out_back(_clamp(odeslano_p))
        prumer = int(r["prumer"] * max(0.0, p))
        if prumer > 2:
            cx = w - px - r["prumer"] / 2
            cy = r["text_y"] + (h - py - r["text_y"]) / 2
            d.ellipse((cx - prumer / 2, cy - prumer / 2, cx + prumer / 2, cy + prumer / 2),
                      fill=tuple(st["tlacitko"]) + (255,))
            s = prumer * 0.22
            sirka_cary = max(2, int(prumer * 0.085))
            sipka = tuple(st["tlacitko_sipka"]) + (255,)
            d.line([(cx, cy + s), (cx, cy - s)], fill=sipka, width=sirka_cary)
            d.line([(cx - s * 0.9, cy - s * 0.1), (cx, cy - s), (cx + s * 0.9, cy - s * 0.1)],
                   fill=sipka, width=sirka_cary, joint="curve")
    return img


def _kresli_odpoved(r):
    o, st, px, py = r["odpoved"], r["st"], r["px"], r["py"]
    img = Image.new("RGBA", (o["w"], o["h"]), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, o["w"] - 1, o["h"] - 1), radius=st["radius"], fill=tuple(st["odpoved_podklad"]) + (255,))
    asc, desc = o["font"].getmetrics()
    for i, radek in enumerate(o["radky"]):
        yy = py + i * o["vr"] + int((o["vr"] - (asc + desc)) / 2)
        d.text((px, yy), radek, font=o["font"], fill=tuple(st["odpoved_barva"]) + (255,))
    return img


def _poloz(platno, vrstva, poz):
    """alpha_composite s ořezem: Pillow nepřijme zápornou polohu, při nástupu zleva k ní dochází."""
    x, y = int(poz[0]), int(poz[1])
    ox, oy = max(0, -x), max(0, -y)
    if ox >= vrstva.width or oy >= vrstva.height:
        return
    platno.alpha_composite(vrstva, (max(0, x), max(0, y)), (ox, oy))


def _se_stinem(platno, vrstva, poz, stin_alfa):
    """Položí vrstvu na plátno i s měkkým stínem pod ní."""
    if stin_alfa:
        stin = Image.new("RGBA", platno.size, (0, 0, 0, 0))
        maska = Image.new("L", platno.size, 0)
        maska.paste(vrstva.getchannel("A"), (int(poz[0]), int(poz[1]) + 8))
        maska = maska.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * stin_alfa / 255))
        stin.putalpha(maska)
        platno.alpha_composite(stin)
    _poloz(platno, vrstva, poz)


def vykresli(spec, styl, klic):
    """Snímek prvku pro klíč ze stav(). Vrátí (RGBA obrázek, (x, y)) pro položení na plátno 1080x1920."""
    r = rozlozeni(spec, styl)
    r["komu"] = spec.get("komu", "PRO CLAUDA")
    r["odeslano"] = spec.get("odeslano", "Odesláno")
    st = r["st"]
    n_celkem = len(" ".join(spec["text"].split()))
    if klic == "s":
        n, kurzor, odeslano_p, odpoved_p = n_celkem, 1, 1.0, 1.0
    elif isinstance(klic, tuple) and klic[0] == "odeslano":
        t_anim = klic[1] / FPS
        n, kurzor = n_celkem, 1
        odeslano_p = _clamp(t_anim / TLACITKO_S)
        odpoved_p = _clamp((t_anim - ODPOVED_ZPOZDENI_S) / ODPOVED_VSTUP_S)
    else:
        n, kurzor = int(klic[0]), int(klic[1])
        odeslano_p, odpoved_p = None, 0.0
    platno = Image.new("RGBA", (r["w"] + 2 * PAD_STIN, r["h"] + 2 * PAD_STIN), (0, 0, 0, 0))
    _se_stinem(platno, _kresli_kapsli(r, n, kurzor, odeslano_p), (PAD_STIN, PAD_STIN), st["stin"])
    if r["odpoved"] and odpoved_p > 0:
        odp = _kresli_odpoved(r)
        p = _ease_out_cubic(odpoved_p)
        if p < 1.0:
            a = ImageChops.multiply(odp.getchannel("A"), Image.new("L", odp.size, int(255 * p)))
            odp.putalpha(a)
        dx = int(-140 * (1 - p))
        _se_stinem(platno, odp, (PAD_STIN + dx, PAD_STIN + r["odpoved"]["y"]), st["stin"])
    x = int(spec.get("x", (SIRKA - r["w"]) / 2))
    y = int(spec.get("y", 240))
    return platno, (x - PAD_STIN, y - PAD_STIN)
