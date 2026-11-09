"""Prvek „sprej“: velký nápis jako ze spreje, písmena se nastříkají zleva doprava a z nich stečou kapky.

Zadání Marcely 29. 10. 2026.
Ve vzhledu osoba drží sprej a stříká slovo pro komentář do výzvy na konci; pod ním se napíše malý řádek.
Studio slovo nastříká samo v daném čase; osoba může držet opravdový sprej (nebo jen ruku) a pohybovat jím zleva doprava.

Spec v osa["prvky"]:
  {"typ": "sprej", "od": 34.6, "do": 37.5, "text": "REEL", "podpis": "napiš do komentáře", "y": 980}
  text       krátké slovo (nejvíc 10 znaků), kreslí se velkými písmeny
  podpis     volitelný malý řádek pod nápisem, píše se po písmenech po dostříkání
  psani_s    jak dlouho trvá nastříkání celého slova (výchozí 1,2 s)
  y          volitelně horní okraj nápisu (jinak pod bradou, na hrudi)

Vzhled (ODHAD ze snímků): pastelově růžová s bílou září, rozprášený okraj, kapky stékají 0,5 až 1,5 s.
Písmo Montserrat Black (OFL).
Klíče stav(): číslo snímku při animaci, "s" v klidu, None mimo čas.
"""
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf",
    "varianta": "Black",
    "velikost": 250,
    "max_sirka": SIRKA - 2 * BOK,
    "barva": (238, 128, 184),
    "svetla": (252, 186, 220),
    "zare": (255, 236, 246),
    "podpis_pismo": "Mulish-wght.ttf",
    "podpis_velikost": 46,
    "podpis_barva": (255, 255, 255),
}

PSANI_S = 1.2
STEKANI_S = 1.4            # kapky dorostou
PODPIS_ZNAKU_S = 22
LEM = 60                   # průhledný okraj (záře)
MEZERA_OKOLO = 50
VYSTUP_S = 0.2


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _klic_stylu(styl):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in styl.items()))


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _velikost(text, st):
    v = int(st["velikost"])
    while v > 90:
        f = pismo(st["pismo"], v, st["varianta"])
        if f.getlength(text) <= st["max_sirka"] - 2 * LEM:
            break
        v -= 10
    return v


@lru_cache(maxsize=8)
def _vrstvy(text, st_klic):
    """Tvar nápisu (L), hranice písmen v x, kapky [(x, y_začátek, šířka, délka, zpoždění)], rozměr obrázku."""
    st = dict(st_klic)
    v = _velikost(text, st)
    f = pismo(st["pismo"], v, st["varianta"])
    w = int(f.getlength(text)) + 2 * LEM
    x0, y0, x1, y1 = f.getbbox(text)
    h_textu = y1 - y0
    h = h_textu + 2 * LEM + int(v * 0.75)          # místo na kapky
    tvar = Image.new("L", (w, h), 0)
    ImageDraw.Draw(tvar).text((LEM, LEM - y0), text, font=f, fill=255)
    hranice, x = [], LEM
    for ch in text:
        hranice.append((x, x + f.getlength(ch)))
        x += f.getlength(ch)
    # kapky: 1 až 2 na písmeno, tam, kde má písmeno inkoust u spodního okraje
    rnd = random.Random(sum(map(ord, text)))
    spodek = LEM + h_textu - 4
    kapky = []
    for i, (a, b) in enumerate(hranice):
        kandidati = [xx for xx in range(int(a) + 8, int(b) - 8, 4) if tvar.getpixel((xx, spodek)) > 128]
        for xx in rnd.sample(kandidati, min(len(kandidati), rnd.choice((1, 2)))):
            kapky.append((xx, spodek - 6, rnd.randint(9, 16), rnd.randint(int(v * 0.15), int(v * 0.6)), rnd.uniform(0.0, 0.35), i))
    return tvar, tuple(hranice), tuple(kapky), (w, h), h_textu, v


def _sprej_hrana(w, h, x_hrana, seed):
    """Maska odkrytí: vše vlevo od x_hrana, okraj rozprášený (tečky), ne ostrý."""
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rectangle([0, 0, max(0, int(x_hrana) - 18), h], fill=255)
    rnd = random.Random(seed)
    for _ in range(int(h * 0.9)):
        x = x_hrana - 18 + rnd.random() ** 1.6 * 46
        y = rnd.uniform(0, h)
        r = rnd.uniform(1.5, 4.5)
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return m


def pripravit(spec, styl, kontext):
    st = _styl(styl)
    text = str(spec.get("text", "")).strip().upper()
    if not text:
        raise ValueError("Sprej: chybí text.")
    if len(text) > 10:
        raise ValueError("Sprej: text nejvýš 10 znaků (zadáno %d), delší by byl moc malý." % len(text))
    spec["text"] = text
    spec.setdefault("psani_s", PSANI_S)
    # nápis je výzva na hrudi: zůstává před osobou jako karta výzvy, za osobou by ho zakrylo tělo (3. 11. 2026)
    spec.setdefault("za_hlavou", False)
    _, _, _, (w, h), h_textu, v = _vrstvy(text, _klic_stylu(st))
    podpis_h = int(st["podpis_velikost"] * 1.6) if spec.get("podpis") else 0
    vyska = h_textu + int(v * 0.4) + podpis_h
    okno = kontext.get("okno")
    if spec.get("y") is not None:
        y = int(spec["y"])
    else:
        y = max(HORNI_OKRAJ + 40, (okno[3] + MEZERA_OKOLO) if okno else 900)
        if y + vyska > VYSKA - DOLNI_OKRAJ:
            y = VYSKA - DOLNI_OKRAJ - vyska
            if okno and _protina((0, y, SIRKA, y + vyska), okno):
                spec["varovani"] = "nápis se nevejde pod bradu nad spodní pásmo, zakrývá část obličeje"
    spec.update({"x": (SIRKA - (w - 2 * LEM)) // 2, "y": y, "sirka": w - 2 * LEM, "vyska": vyska})


def zvuky(spec):
    """Sprej (syčení) během psaní; hlavní program ho zatím nemíchá, zvuk ve studiu není."""
    return [(spec["od"], "sprej")]


def _konec_animace(spec):
    return spec["psani_s"] + STEKANI_S + 0.4 + len(spec.get("podpis") or "") / PODPIS_ZNAKU_S


def stav(spec, t):
    if t < spec["od"] or t >= spec["do"]:
        return None
    t_rel = t - spec["od"]
    if t_rel < _konec_animace(spec) or t >= spec["do"] - VYSTUP_S:
        return int(round(t * FPS))
    return "s"


def vykresli(spec, styl, klic):
    st = _styl(styl)
    st_klic = _klic_stylu(st)
    tvar, hranice, kapky, (w, h), h_textu, v = _vrstvy(spec["text"], st_klic)
    t_rel = _konec_animace(spec) + 1 if klic == "s" else klic / FPS - spec["od"]
    psani = spec["psani_s"]
    p = _clamp(t_rel / psani)
    x_hrana = LEM + (w - 2 * LEM) * p + (40 if p >= 1 else 0)
    odkryto = ImageChops.multiply(tvar, _sprej_hrana(w, h, x_hrana, int(t_rel * FPS) if p < 1 else 0))

    # kapky: rostou dolů od chvíle, kdy je jejich písmeno nastříkané
    d_kapky = Image.new("L", (w, h), 0)
    dk = ImageDraw.Draw(d_kapky)
    n = len(hranice)
    for x, y, sir, delka, zpozdeni, i in kapky:
        hotovo_pismeno = psani * (i + 1) / n
        q = _clamp((t_rel - hotovo_pismeno - zpozdeni) / STEKANI_S)
        if q <= 0:
            continue
        L = delka * _ease_out_cubic(q)
        dk.rounded_rectangle([x - sir / 2, y, x + sir / 2, y + L], radius=sir / 2, fill=255)
        r = sir * 0.75
        dk.ellipse([x - r, y + L - r, x + r, y + L + r], fill=255)
    alfa = ImageChops.lighter(odkryto, d_kapky)

    # barva: světlejší nahoře, sytější dole; jemný šum spreje
    prechod = Image.linear_gradient("L").resize((w, h))
    barva = Image.composite(Image.new("RGB", (w, h), st["barva"]), Image.new("RGB", (w, h), st["svetla"]), prechod)
    zrno = Image.effect_noise((w, h), 30).point(lambda q: 225 + q // 9)
    barva = Image.merge("RGB", [ImageChops.multiply(c, zrno) for c in barva.split()])
    pismo_img = barva.convert("RGBA")
    pismo_img.putalpha(alfa)

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    zare = Image.new("RGBA", (w, h), tuple(st["zare"]) + (0,))
    zare.putalpha(alfa.filter(ImageFilter.GaussianBlur(10)).point(lambda q: q * 3 // 4))
    mlha = Image.new("RGBA", (w, h), tuple(st["barva"]) + (0,))
    mlha.putalpha(odkryto.filter(ImageFilter.GaussianBlur(28)).point(lambda q: q // 4))
    out.alpha_composite(mlha)
    out.alpha_composite(zare)
    out.alpha_composite(pismo_img)

    if spec.get("podpis"):
        fp = pismo(st["podpis_pismo"], st["podpis_velikost"], "SemiBold")
        n_zn = int(_clamp((t_rel - psani - 0.2) * PODPIS_ZNAKU_S, 0, len(spec["podpis"])))
        text = spec["podpis"][:n_zn]
        if text:
            vyska_podpisu = int(st["podpis_velikost"] * 1.6)
            vetsi = Image.new("RGBA", (w, max(h, LEM + h_textu + int(v * 0.4) + vyska_podpisu)), (0, 0, 0, 0))
            vetsi.alpha_composite(out)
            out = vetsi
            vrstva = Image.new("RGBA", out.size, (0, 0, 0, 0))
            dp = ImageDraw.Draw(vrstva)
            sirka_cela = fp.getlength(spec["podpis"])
            pozice = ((w - sirka_cela) / 2, LEM + h_textu + int(v * 0.4) - vyska_podpisu // 2)
            dp.text(pozice, text, font=fp, fill=(40, 30, 40, 150))
            vrstva = vrstva.filter(ImageFilter.GaussianBlur(3))
            ImageDraw.Draw(vrstva).text(pozice, text, font=fp, fill=tuple(st["podpis_barva"]) + (255,))
            out.alpha_composite(vrstva)

    if t_rel > spec["do"] - spec["od"] - VYSTUP_S:
        k = _clamp((spec["do"] - spec["od"] - t_rel) / VYSTUP_S)
        out.putalpha(out.getchannel("A").point(lambda q: int(q * k)))
    return out, (spec["x"] - LEM, spec["y"] - LEM)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])
