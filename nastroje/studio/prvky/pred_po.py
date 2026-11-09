"""Prvek „před a po“: obraz se rozdělí na surovou a hotovou verzi, nebo se přes něj přetáhne nová barva.

Zadání Marcely 3. 11. 2026.
Vzhled: 1) svislá čára jede přes obraz, na jedné straně je obraz bez úprav
(nahoře popisek PŘED), na druhé hotový (PO); 2) u věty o náladě se přes obraz přetáhne tmavší barva.

Spec v osa["prvky"]:
  {"typ": "pred_po", "od": 10.2, "do": 12.4, "rezim": "posuvnik", "popisky": ["PŘED", "PO"]}
  {"typ": "pred_po", "od": 22.8, "do": 24.0, "rezim": "zaclona", "barva": "tmava", "drzet_do": 26.5}
  rezim     "posuvnik": svislá čára jede zprava doleva; vlevo od ní je obraz „surový“ (bez úprav), vpravo hotový.
            Po konci prvku zůstane hotový obraz (reel běží dál beze změny).
            "zaclona": nová barva se přetáhne shora dolů a drží do "drzet_do" (výchozí do konce prvku + 2 s).
  barva     vzhled barvy (BARVY níž): u posuvníku výchozí "surova", u záclony výchozí "tmava"
  popisky   jen u posuvníku: dva krátké popisky nahoře (výchozí PŘED a PO); [] = bez popisků
  obracene  jen u posuvníku: nová barva je vpravo od čáry (vlevo zůstává původní obraz), čára ji odkrývá
            zprava doleva; po konci se obraz vrátí, barvu pak drží následná záclona (3. 11. 2026, „víc cinematic“)
  velikost_popisku  volitelně větší popisky (výchozí podle stylu 30 px)

Barvu obrazu mění ffmpeg na hotovém základu (render._pred_po_zaklad), tento modul kreslí jen čáru a popisky.
Čára a popisky jdou za osobu (pravidlo Marcely 3. 11.: efekty nikdy přes hlavu). Poloha čáry v čase t je
poloha(spec, t) a ffmpeg dostává stejný vzorec (vyraz_ffmpeg), proto čára sedí přesně na hraně barev.
Klíče stav(): číslo snímku při pohybu čáry, None mimo čas nebo u záclony (ta nic nekreslí).
"""
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ..titulky import BOK, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

# filtry ffmpeg pro obraz (NÁVRH hodnot, posoudí Marcela okem); každý končí ve formátu yuv420p jako základ
BARVY = {
    "surova": "eq=contrast=0.86:saturation=0.62:brightness=-0.03:gamma=1.04",       # jako z telefonu, bez úprav
    "tmava": "eq=contrast=1.14:saturation=0.78:brightness=-0.07:gamma=0.88,vignette=angle=PI/4",
    "tepla": "colortemperature=temperature=5200,eq=saturation=1.05",
    "cernobila": "hue=s=0,eq=contrast=1.08",
}

VYCHOZI_STYL = {
    "cara": (255, 255, 255),
    "cara_px": 5,
    "pismo": "Montserrat-wght.ttf",
    "varianta": "SemiBold",
    "velikost": 30,
    "barva": (255, 255, 255),
    "podklad": (22, 48, 38, 200),      # tmavě zelená pilulka pod popiskem
    "proklad": 6,                      # prostrkání písmen popisku (px)
}

START, KONEC = 0.86, 0.14      # posuvník: čára jede z 86 % šířky na 14 %, pak hotový obraz naskočí celý
DOJEZD_S = 0.25                # na konci posuvníku čára dojede ke kraji a zmizí


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _klic_stylu(styl):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in styl.items()))


def rezim(spec):
    return spec.get("rezim", "posuvnik")


def barva(spec):
    b = spec.get("barva") or ("surova" if rezim(spec) == "posuvnik" else "tmava")
    if b not in BARVY:
        raise ValueError("Prvek před a po: barva '%s' neexistuje, vyber z: %s." % (b, ", ".join(BARVY)))
    return b


def drzet_do(spec):
    if rezim(spec) == "posuvnik":
        return float(spec["do"])
    return float(spec.get("drzet_do", float(spec["do"]) + 2.0))


def _hladce(p):
    return p * p * (3 - 2 * p)


def poloha(spec, t):
    """Podíl obrazu (0 až 1), kam sahá změna v čase t. Posuvník: x čáry, vlevo od ní surový obraz.
    Záclona: y spodní hrany nové barvy."""
    od, do = float(spec["od"]), float(spec["do"])
    if rezim(spec) == "posuvnik":
        jizda = max(do - od - DOJEZD_S, 0.1)
        if t < od + jizda:
            p = _hladce(min(max((t - od) / jizda, 0.0), 1.0))
            return START + (KONEC - START) * p
        p = min(max((t - od - jizda) / DOJEZD_S, 0.0), 1.0)
        return KONEC * (1 - p)
    p = _hladce(min(max((t - od) / max(do - od, 0.1), 0.0), 1.0))
    return p


def vyraz_ffmpeg(spec):
    """Výraz pro ffmpeg blend (A = základ, B = obraz v nové barvě), stejný průběh jako poloha().
    Posuvník: B (surový) vlevo od čáry. Záclona: B nad spodní hranou."""
    od, do = float(spec["od"]), float(spec["do"])
    if rezim(spec) == "posuvnik":
        jizda = max(do - od - DOJEZD_S, 0.1)
        q = "clip((T-%.4f)/%.4f\\,0\\,1)" % (od, jizda)
        r = "clip((T-%.4f)/%.4f\\,0\\,1)" % (od + jizda, DOJEZD_S)
        pos = "if(lt(T\\,%.4f)\\,%.4f+(%.4f)*(%s)*(%s)*(3-2*(%s))\\,%.4f*(1-(%s)))" % (
            od + jizda, START, KONEC - START, q, q, q, KONEC, r)
        if spec.get("obracene"):
            return "if(lt(X\\,W*(%s))\\,A\\,B)" % pos
        return "if(lt(X\\,W*(%s))\\,B\\,A)" % pos
    q = "clip((T-%.4f)/%.4f\\,0\\,1)" % (od, max(do - od, 0.1))
    return "if(lt(Y\\,H*(%s)*(%s)*(3-2*(%s)))\\,B\\,A)" % (q, q, q)


def pripravit(spec, styl, kontext):
    barva(spec)                          # chybná barva se ohlásí hned, ne až při renderu
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = BOK, HORNI_OKRAJ + 30, SIRKA - 2 * BOK, 60
    if rezim(spec) == "posuvnik" and drzet_do(spec) < float(spec["do"]):
        spec["varovani"] = "drzet_do je dřív než konec prvku"


def stav(spec, t):
    if rezim(spec) != "posuvnik" or not (float(spec["od"]) <= t < float(spec["do"])):
        return None
    return int(round(t * FPS))


@lru_cache(maxsize=4)
def _popisek(text, st_klic):
    st = dict(st_klic)
    f = pismo(st["pismo"], st["velikost"], st["varianta"])
    sirky = [f.getlength(z) for z in text]
    w = int(sum(sirky) + st["proklad"] * (len(text) - 1)) + 2 * 22
    h = int(st["velikost"] * 1.0) + 2 * 12
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=tuple(st["podklad"]))
    x = 22
    for z, sz in zip(text, sirky):
        d.text((x, h // 2), z, font=f, fill=tuple(st["barva"]), anchor="lm")
        x += sz + st["proklad"]
    return im


def vykresli(spec, styl, klic):
    st = _styl(styl)
    if spec.get("velikost_popisku"):
        st["velikost"] = int(spec["velikost_popisku"])
    t = klic / FPS
    x = int(round(poloha(spec, t) * SIRKA))
    im = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pul = st["cara_px"] // 2
    if 0 < x < SIRKA:
        stin = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
        ImageDraw.Draw(stin).rectangle([x - pul - 3, 0, x + pul + 3, VYSKA], fill=(0, 0, 0, 90))
        im = Image.alpha_composite(im, stin.filter(ImageFilter.GaussianBlur(6)))
        d = ImageDraw.Draw(im)
        d.rectangle([x - pul, 0, x + pul, VYSKA], fill=tuple(st["cara"]) + (255,))
        # úchyt uprostřed čáry jako u posuvníku v aplikaci
        cy = VYSKA // 2
        d.ellipse([x - 26, cy - 26, x + 26, cy + 26], fill=tuple(st["cara"]) + (255,))
        d.polygon([(x - 6, cy - 9), (x - 15, cy), (x - 6, cy + 9)], fill=(40, 40, 40, 255))
        d.polygon([(x + 6, cy - 9), (x + 15, cy), (x + 6, cy + 9)], fill=(40, 40, 40, 255))
    popisky = spec.get("popisky", ["PŘED", "PO"])
    if len(popisky) == 2 and x > 0:
        y = HORNI_OKRAJ + 30
        kl = _klic_stylu(st)
        levy, pravy = _popisek(popisky[0], kl), _popisek(popisky[1], kl)
        if x > levy.width + 60:
            im.alpha_composite(levy, (max(40, x // 2 - levy.width // 2), y))
        if SIRKA - x > pravy.width + 60:
            im.alpha_composite(pravy, (min(SIRKA - 40 - pravy.width, x + (SIRKA - x) // 2 - pravy.width // 2), y))
    return im, (0, 0)


def obdelnik(spec, styl):
    # čára přes celou výšku i barva přes celý obraz jsou záměr (jdou za osobu); do kontroly se hlásí jen pás popisků
    return (BOK, HORNI_OKRAJ + 30, SIRKA - BOK, HORNI_OKRAJ + 30 + 60)
