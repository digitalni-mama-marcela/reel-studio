"""Prvek „nálepky“: pootočené štítky přes část obrazu (jako nálepky „ŠPATNÝ ZÁBĚR“) a přeškrtnutý text.

Štítek je krémový obdélník se švestkovým textem velkými písmeny, pootočený střídavě o -8 až +10 stupňů.
Padá shora s malým odrazem (0,35 s), každý další o 0,2 s později. Přeškrtnutý text je řádek slov (krém,
Montserrat ExtraBold 64 px) na švestkové pilulce, přes který se za 0,25 s zleva doprava přetáhne červená čára.

Spec: {"typ": "nalepky", "od": s, "do": s, "stitky": ["ŠPATNÝ ZÁBĚR", "PŘEŘEK"], "oblast": [140, 300, 940, 1100],
       "preskrtnout": ["CapCut", "Edits"]}
  stitky       volitelné, texty štítků (kreslí se velkými písmeny)
  oblast       [x0, y0, x1, y1] kam štítky padají (výchozí [140, 300, 940, 1100])
  preskrtnout  volitelné, slova v jednom řádku, která se přeškrtnou (řádek je pod štítky)

Oblast nesmí protínat okno obličeje: když protíná, posune se nad okno (když to nejde, pod něj); když se tam
štítky nevejdou, zmenší se písmo (nejmíň 28 px). Když se nevejdou ani tak, zapíše se spec["nevejde_se"] = True
a kontrola to ohlásí. Po pripravit() jsou v spec: oblast (použitá), oblast_zadana, velikost, rozlozeni
(střed a úhel každého štítku), skrt (řádek přeškrtnutí), x, y, sirka, vyska (obdélník všeho, co je vidět).
"""
import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf",
    "varianta": "ExtraBold",
    "velikost": 40,
    "min_velikost": 28,
    "podklad": (251, 246, 239),            # krémový štítek
    "barva": (74, 51, 64),                 # švestkový text
    "pad": (22, 12),
    "rohy": 6,
    "stin": 90,                            # průhlednost stínu pod štítkem (0 = bez stínu)
    "skrt_velikost": 64,
    "skrt_barva": (251, 246, 239),
    "skrt_cara": (192, 57, 43),            # červená čára
    "skrt_tloustka": 8,
    "skrt_podklad": (74, 51, 64, 215),     # švestková pilulka pod řádkem
    "skrt_pad": (34, 16),
}

UHLY = (-8, 10, -6, 8)      # úhly štítků, střídají se
PAD_S = 0.35                # pád jednoho štítku i s odrazem
ZPOZDENI_S = 0.20           # další štítek o tolik později
SKRT_S = 0.25               # přetažení červené čáry
SKRT_PAUZA_S = 0.10         # čára začne až po dopadu štítků
VYSTUP_S = 0.20             # zmizení na konci
VYSKA_PADU = 260            # odkud štítek padá (px nad cílem)
MEZERA_STITKU = 14          # svisle mezi štítky
MEZERA_SKRTU = 30           # mezi štítky a řádkem přeškrtnutí
MEZERA_OKOLO = 40           # odstup od obličeje
VYCHOZI_OBLAST = [140, 300, 940, 1100]


def _poloz_bezpecne(platno, im, x, y):
    """Položí obrázek i částečně mimo plátno (Pillow jinak odmítne záporné souřadnice)."""
    x, y = int(round(x)), int(round(y))
    ox, oy = max(0, -x), max(0, -y)
    if ox >= im.width or oy >= im.height or x >= platno.width or y >= platno.height:
        return
    platno.alpha_composite(im, (max(0, x), max(0, y)), (ox, oy))


def _clamp(x):
    return max(0.0, min(1.0, x))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _klic_stylu(styl):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in styl.items()))


OKRAJ_STITKU = 12       # průhledný lem kolem štítku kvůli stínu (do rozměrů se nepočítá)


def _rozmer_stitku(text, velikost, uhel, styl):
    """Viditelný rozměr štítku bez lemu: (šířka, výška) rovně a (šířka, výška) obdélníku po pootočení."""
    f = pismo(styl["pismo"], velikost, styl["varianta"])
    px, py = styl["pad"]
    px, py = int(px * velikost / 40), int(py * velikost / 40)
    asc, desc = f.getmetrics()
    w, h = int(math.ceil(f.getlength(text))) + 2 * px, asc + desc + 2 * py
    si, co = abs(math.sin(math.radians(uhel))), abs(math.cos(math.radians(uhel)))
    return w, h, int(math.ceil(w * co + h * si)), int(math.ceil(w * si + h * co))


@lru_cache(maxsize=256)
def _stitek(text, velikost, uhel, klic_stylu):
    """Hotový pootočený štítek (RGBA, i s lemem pro stín). Pamatuje se podle textu, velikosti a úhlu."""
    styl = dict(klic_stylu)
    f = pismo(styl["pismo"], velikost, styl["varianta"])
    px, py = styl["pad"]
    px, py = int(px * velikost / 40), int(py * velikost / 40)
    w, h, _, _ = _rozmer_stitku(text, velikost, uhel, styl)
    okraj = OKRAJ_STITKU
    im = Image.new("RGBA", (w + 2 * okraj, h + 2 * okraj), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if styl.get("stin"):
        d.rounded_rectangle((okraj + 4, okraj + 6, okraj + w + 4, okraj + h + 6), radius=styl["rohy"],
                            fill=(30, 18, 24, int(styl["stin"])))
    d.rounded_rectangle((okraj, okraj, okraj + w, okraj + h), radius=styl["rohy"], fill=tuple(styl["podklad"]) + (255,))
    d.text((okraj + px, okraj + py), text, font=f, fill=tuple(styl["barva"]) + (255,))
    return im.rotate(uhel, resample=Image.BICUBIC, expand=True)


def _rozmer_skrtu(slova, velikost, styl):
    """Rozměr řádku přeškrtnutí (pilulka): (šířka, výška, písmo, šířka textu)."""
    f = pismo(styl["pismo"], velikost, styl["varianta"])
    text = "   ".join(slova)
    tw = int(math.ceil(f.getlength(text)))
    asc, desc = f.getmetrics()
    px, py = styl["skrt_pad"]
    return tw + 2 * px, asc + desc + 2 * py, f, tw


def _velikost_skrtu(velikost, styl):
    return max(styl["min_velikost"], int(round(styl["skrt_velikost"] * velikost / styl["velikost"])))


def _rozloz(spec, styl, velikost, oblast):
    """Rozloží štítky a řádek přeškrtnutí do oblasti. Vrátí (rozložení, skrt, obdélník, vejde se)."""
    ks = _klic_stylu(styl)
    stitky = [s.upper() for s in spec.get("stitky") or []]
    ox0, oy0, ox1, oy1 = oblast
    ow = ox1 - ox0
    rozlozeni, boxy = [], []
    y = oy0
    vejde = True
    for i, text in enumerate(stitky):
        uhel = UHLY[i % len(UHLY)]
        w, h, rw, rh = _rozmer_stitku(text, velikost, uhel, styl)
        if rw > ow:
            vejde = False
        # střídavě trochu vlevo a vpravo, ale uvnitř oblasti a okrajů obrazu
        posun = -0.10 * ow if i % 2 == 0 else 0.10 * ow
        cx = (ox0 + ox1) / 2 + posun
        cx = max(ox0 + rw / 2, min(ox1 - rw / 2, cx))
        cx = max(BOK + rw / 2, min(SIRKA - BOK - rw / 2, cx))
        cy = y + rh / 2
        rozlozeni.append({"text": text, "cx": int(round(cx)), "cy": int(round(cy)), "uhel": uhel})
        boxy.append((cx - rw / 2, cy - rh / 2, cx + rw / 2, cy + rh / 2))
        # pootočené štítky se v rozích překrývají jen průhledně, proto krok o něco menší než celý obdélník
        y += rh - 0.5 * (rh - h) + MEZERA_STITKU
    skrt = None
    slova = spec.get("preskrtnout") or []
    if slova:
        sv = _velikost_skrtu(velikost, styl)
        sw, sh, _, _ = _rozmer_skrtu(slova, sv, styl)
        if sw > ow or sw > SIRKA - 2 * BOK:
            vejde = False
        if stitky:
            y += MEZERA_SKRTU - MEZERA_STITKU
        else:
            y = (oy0 + oy1) / 2 - sh / 2    # jen přeškrtnutí: uprostřed oblasti
        cx = max(BOK + sw / 2, min(SIRKA - BOK - sw / 2, (ox0 + ox1) / 2))
        skrt = {"slova": list(slova), "velikost": sv, "cx": int(round(cx)), "cy": int(round(y + sh / 2)), "w": sw, "h": sh}
        boxy.append((cx - sw / 2, y, cx + sw / 2, y + sh))
        y += sh
    konec = max(b[3] for b in boxy) if boxy else y
    if konec > oy1 + 0.5:
        vejde = False
    if not boxy:
        return rozlozeni, skrt, (ox0, oy0, ox0, oy0), True
    # skupina štítků uprostřed oblasti (svisle), když je v ní místo navíc
    if stitky and konec < oy1:
        posun = int((oy1 - konec) / 2)
        for st in rozlozeni:
            st["cy"] += posun
        if skrt:
            skrt["cy"] += posun
        boxy = [(b[0], b[1] + posun, b[2], b[3] + posun) for b in boxy]
    obd = (int(min(b[0] for b in boxy)), int(min(b[1] for b in boxy)),
           int(math.ceil(max(b[2] for b in boxy))), int(math.ceil(max(b[3] for b in boxy))))
    return rozlozeni, skrt, obd, vejde


def pripravit(spec, styl, kontext):
    """Vybere oblast mimo obličej a velikost písma, rozloží štítky a řádek přeškrtnutí."""
    styl = _styl(styl)
    if not spec.get("stitky") and not spec.get("preskrtnout"):
        raise ValueError("Nálepky: zadej aspoň jeden štítek (stitky) nebo slovo k přeškrtnutí (preskrtnout).")
    zadana = [int(v) for v in (spec.get("oblast") or VYCHOZI_OBLAST)]
    spec["oblast_zadana"] = list(zadana)
    okno = kontext.get("okno")
    horni = kontext.get("horni", HORNI_OKRAJ) + 10
    dolni = kontext.get("vyska", VYSKA) - kontext.get("dolni", DOLNI_OKRAJ) - 10
    kandidati = [zadana]
    # pevna_oblast: oblast ověřená na snímcích (pás nad hlavou), okno obličeje s rezervou na vlasy ji jinak odsune
    if okno and _protina(zadana, okno) and not spec.get("pevna_oblast"):
        vyska = zadana[3] - zadana[1]
        y1 = int(okno[1]) - MEZERA_OKOLO
        nad = [zadana[0], max(horni, y1 - vyska), zadana[2], y1]
        y0 = int(okno[3]) + MEZERA_OKOLO
        pod = [zadana[0], y0, zadana[2], min(dolni, y0 + vyska)]
        kandidati = [o for o in (nad, pod) if o[3] - o[1] >= 60]
        if not kandidati:
            kandidati = [nad]
    volba = None
    for oblast in kandidati:
        for velikost in range(styl["velikost"], styl["min_velikost"] - 1, -4):
            rozlozeni, skrt, obd, vejde = _rozloz(spec, styl, velikost, oblast)
            if vejde:
                volba = (oblast, velikost, rozlozeni, skrt, obd)
                break
        if volba:
            break
    spec["nevejde_se"] = volba is None
    if volba is None:
        oblast = kandidati[0]
        velikost = styl["min_velikost"]
        rozlozeni, skrt, obd, _ = _rozloz(spec, styl, velikost, oblast)
        volba = (oblast, velikost, rozlozeni, skrt, obd)
    oblast, velikost, rozlozeni, skrt, obd = volba
    spec.update({"oblast": [int(v) for v in oblast], "velikost": int(velikost), "rozlozeni": rozlozeni, "skrt": skrt,
                 "x": obd[0], "y": obd[1], "sirka": obd[2] - obd[0], "vyska": obd[3] - obd[1]})


def obdelnik(spec, styl):
    """Obdélník všeho, co je po dopadu vidět (štítky i řádek přeškrtnutí)."""
    return spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"]


def casy(spec):
    """(starty pádů štítků, začátek čáry nebo None, konec animace)."""
    n = len(spec.get("rozlozeni") or [])
    starty = [i * ZPOZDENI_S for i in range(n)]
    konec = (starty[-1] + PAD_S) if starty else 0.0
    skrt_od = None
    if spec.get("skrt"):
        skrt_od = konec + SKRT_PAUZA_S
        konec = skrt_od + SKRT_S
    return starty, skrt_od, konec


def stav(spec, t):
    """Číslo snímku animace, 's' v klidu, záporné číslo při mizení, None mimo čas prvku."""
    t_rel = t - spec["od"]
    if t_rel < 0 or t >= spec["do"]:
        return None
    zbyva = spec["do"] - t
    if zbyva < VYSTUP_S:
        return -(int(zbyva * FPS) + 1)
    _, _, konec = casy(spec)
    if t_rel < konec:
        return int(t_rel * FPS)
    return "s"


def _pad(p):
    """Svislý posun štítku při pádu (záporný = nad cílem): zrychlený pád, pak malý odraz."""
    if p >= 1.0:
        return 0.0
    if p < 0.65:
        q = p / 0.65
        return -VYSKA_PADU * (1 - q * q)
    q = (p - 0.65) / 0.35
    return -0.10 * VYSKA_PADU * math.sin(math.pi * q)


def _plocha(spec):
    """Kus obrazu, do kterého se prvek kreslí (štítky i s pádem shora): (x0, y0, x1, y1) v mezích obrazu."""
    x0, y0, x1, y1 = obdelnik(spec, None)
    return (max(0, x0 - 60), max(0, y0 - VYSKA_PADU - 60), min(SIRKA, x1 + 60), min(VYSKA, y1 + 60))


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
    px0, py0, px1, py1 = _plocha(spec)
    platno = Image.new("RGBA", (max(1, px1 - px0), max(1, py1 - py0)), (0, 0, 0, 0))
    starty, skrt_od, _ = casy(spec)
    skrt = spec.get("skrt")
    if skrt and skrt_od is not None and t_rel >= skrt_od:
        sv = skrt["velikost"]
        sw, sh, f, tw = _rozmer_skrtu(skrt["slova"], sv, styl)
        x0, y0 = skrt["cx"] - sw / 2 - px0, skrt["cy"] - sh / 2 - py0
        d = ImageDraw.Draw(platno)
        d.rounded_rectangle((x0, y0, x0 + sw, y0 + sh), radius=sh / 2, fill=tuple(styl["skrt_podklad"]))
        spx, spy = styl["skrt_pad"]
        d.text((x0 + spx, y0 + spy), "   ".join(skrt["slova"]), font=f, fill=tuple(styl["skrt_barva"]) + (255,))
        p = _ease_out_cubic(_clamp((t_rel - skrt_od) / SKRT_S))
        delka = (tw + 2 * spx - 16) * p
        if delka > 2:
            tl = styl["skrt_tloustka"]
            cy = y0 + sh / 2 + tl * 0.3
            d.rounded_rectangle((x0 + 8, cy - tl / 2, x0 + 8 + delka, cy + tl / 2), radius=tl / 2,
                                fill=tuple(styl["skrt_cara"]) + (255,))
    for i, st in enumerate(spec.get("rozlozeni") or []):
        p = _clamp((t_rel - starty[i]) / PAD_S)
        if p <= 0:
            continue
        uhel = st["uhel"] * (1.0 + 0.35 * (1 - _ease_out_cubic(p)))
        im = _stitek(st["text"], spec["velikost"], round(uhel * 2) / 2, ks)
        a = _clamp(p / 0.12)
        if a < 1.0:
            im = im.copy()
            im.putalpha(ImageChops.multiply(im.getchannel("A"), Image.new("L", im.size, int(255 * a))))
        x = st["cx"] - im.width / 2 - px0
        y = st["cy"] - im.height / 2 - py0 + _pad(p)
        _poloz_bezpecne(platno, im, x, y)
    if alfa_celku < 1.0:
        platno.putalpha(ImageChops.multiply(platno.getchannel("A"), Image.new("L", platno.size, int(255 * alfa_celku))))
    return platno, (px0, py0)
