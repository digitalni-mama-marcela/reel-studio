"""Prvek „mřížka“: jeden reel se rozmnoží na celý týden.

Přes celý obraz se položí tmavá švestková vrstva, uprostřed se objeví první obálka reelu (větší) a během
0,8 s se „rozmnoží“: ostatní obálky vyletí ze středu na svá místa v mřížce (každá o 0,08 s později, s lehkým
popnutím). Dlaždice mají zaoblené rohy, krémový okraj a mezery. Volitelně je pod mřížkou krátký popisek.

Spec: {"typ": "mrizka", "od": s, "do": s, "soubory": ["r1.png", ...], "sloupce": 3, "ztmavit": 0.5,
       "popisek": "7 reelů za týden"}
  soubory  5 až 9 obálek reelů (poměr 9:16), cesty absolutní nebo relativní k podkladům zákaznice
  sloupce  počet sloupců (výchozí 3)
  ztmavit  síla tmavé vrstvy přes obraz 0 až 1 (výchozí 0,5)
  popisek  volitelný text pod mřížkou

Umístění: nahoře pod bezpečným pásmem a nad oknem obličeje. Když se tam mřížka nevejde ani zmenšená (dlaždice
nejmíň 180 px široké), zapíše se spec["pres_oblicej"] = True a mřížka se položí přes střed obrazu: obličej je po
dobu prvku krátce zakrytý (u tohoto prvku záměr). obdelnik() to poctivě hlásí, kontrola tedy skončí varováním.
Když se mřížka musí natáhnout až do spodního pásma přes titulky, zapíše se spec["pres_titulky"] = True.
Po pripravit() jsou v spec: x, y, sirka, vyska (obdélník celé mřížky), dlazdice (obdélníky [x, y, w, h]),
dlazdice_sirka, velka (obdélník první zvětšené obálky), cesty (vyřešené cesty obrázků).
"""
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "okraj": (251, 246, 239),          # krémový okraj dlaždice
    "okraj_px": 4,
    "rohy": 20,
    "mezera": 18,
    "min_sirka": 180,                  # nejmenší šířka dlaždice
    "ztmaveni": (74, 51, 64),          # švestková vrstva přes obraz
    "pismo": "Montserrat-wght.ttf",    # popisek pod mřížkou
    "varianta": "Bold",
    "velikost": 40,
    "barva": (251, 246, 239),
}

UVOD_S = 0.35          # první obálka vyskočí uprostřed
ROZMNOZENI_S = 0.80    # rozmnožení na celou mřížku
ZPOZDENI_S = 0.08      # další dlaždice vyletí o tolik později
MIN_LET_S = 0.25       # nejkratší let jedné dlaždice
POPISEK_S = 0.25       # popisek se objeví po rozmnožení
ZTMAVENI_S = 0.25      # náběh tmavé vrstvy
VYSTUP_S = 0.20        # zmizení na konci
VELKA = 1.5            # první obálka je o tolik větší než dlaždice
MEZERA_OKOLO = 40      # odstup od obličeje
MIN_POCET, MAX_POCET = 2, 9

_DLAZDICE = {}         # (cesta, w, h) -> hotová dlaždice RGBA


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


def _ease_out_back(p):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _cesty(spec, kontext):
    """Cesty k obálkám: absolutní, nebo relativní ke složce podkladů zákaznice."""
    out, chybi = [], []
    for s in spec["soubory"]:
        p = Path(s).expanduser()
        if not p.is_absolute() and kontext.get("podklady"):
            p = Path(kontext["podklady"]) / s
        if not p.is_file():
            chybi.append(str(p))
        out.append(str(p))
    if chybi:
        raise FileNotFoundError("Mřížka: nenašla jsem obálky reelů: %s" % ", ".join(chybi))
    return out


def _vyska_popisku(spec, styl):
    if not spec.get("popisek"):
        return 0
    f = pismo(styl["pismo"], styl["velikost"], styl["varianta"])
    asc, desc = f.getmetrics()
    return int((asc + desc) * 1.1) + styl["mezera"]


def _rozmer_dlazdice(n, sloupce, styl, sirka_dost, vyska_dost, popisek_v):
    """Šířka dlaždice, aby se mřížka vešla do dané šířky a výšky. Vrátí (řádky, šířka dlaždice)."""
    radky = int(math.ceil(n / sloupce))
    mez = styl["mezera"]
    w_sirka = (sirka_dost - (sloupce - 1) * mez) // sloupce
    h_vyska = (vyska_dost - popisek_v - (radky - 1) * mez) // radky
    return radky, int(min(w_sirka, h_vyska * 9 // 16))


def _rozloz(spec, styl, w, x0, y0):
    """Obdélníky dlaždic [x, y, w, h] v mřížce s levým horním rohem (x0, y0); neúplný poslední řádek je uprostřed."""
    n, sloupce, mez = len(spec["cesty"]), spec.get("sloupce", 3), styl["mezera"]
    h = int(round(w * 16 / 9))
    sirka_mrizky = sloupce * w + (sloupce - 1) * mez
    out = []
    for i in range(n):
        r, c = divmod(i, sloupce)
        v_radku = min(sloupce, n - r * sloupce)
        sirka_radku = v_radku * w + (v_radku - 1) * mez
        x = x0 + (sirka_mrizky - sirka_radku) // 2 + c * (w + mez)
        out.append([int(x), int(y0 + r * (h + mez)), int(w), int(h)])
    return out


def pripravit(spec, styl, kontext):
    """Doplní cesty, rozměry a polohu mřížky a první zvětšené obálky."""
    styl = _styl(styl)
    spec["cesty"] = _cesty(spec, kontext)
    n = len(spec["cesty"])
    if not MIN_POCET <= n <= MAX_POCET:
        raise ValueError("Mřížka chce 5 až 9 obálek (snese 2 až 9), dostala %d." % n)
    sloupce = int(spec.get("sloupce", 3))
    if sloupce < 1:
        raise ValueError("Mřížka: počet sloupců musí být aspoň 1.")
    spec["sloupce"] = sloupce
    spec.setdefault("ztmavit", 0.5)
    okno = kontext.get("okno")
    horni = kontext.get("horni", HORNI_OKRAJ) + 10
    dolni_titulky = kontext.get("vyska", VYSKA) - kontext.get("dolni", DOLNI_OKRAJ) - 220   # nad blokem titulků (2 řádky 70 px)
    dolni_pasmo = kontext.get("vyska", VYSKA) - kontext.get("dolni", DOLNI_OKRAJ) - 10
    sirka_dost = kontext.get("sirka", SIRKA) - 2 * BOK
    popisek_v = _vyska_popisku(spec, styl)

    # kam zkusit: nad obličej (nahoře), přes obličej uprostřed, přes obličej až k titulkům
    kandidati = []
    if okno:
        kandidati.append((horni, min(int(okno[1]) - MEZERA_OKOLO, dolni_titulky), False, False))
    kandidati.append((horni, dolni_titulky, bool(okno), False))
    kandidati.append((horni, dolni_pasmo, bool(okno), True))
    volba = None
    for y0, y1, pres, pres_titulky in kandidati:
        if y1 - y0 < 100:
            continue
        radky, w = _rozmer_dlazdice(n, sloupce, styl, sirka_dost, y1 - y0, popisek_v)
        if w >= styl["min_sirka"]:
            volba = (y0, y1, pres, pres_titulky, radky, w)
            break
    spec["nevejde_se"] = volba is None
    if volba is None:
        y0, y1, pres, pres_titulky = kandidati[-1]
        radky = int(math.ceil(n / sloupce))
        volba = (y0, y1, pres, pres_titulky, radky, styl["min_sirka"])
    y0, y1, pres, pres_titulky, radky, w = volba
    spec["pres_oblicej"] = pres
    spec["pres_titulky"] = pres_titulky
    h = int(round(w * 16 / 9))
    sirka_mrizky = sloupce * w + (sloupce - 1) * styl["mezera"]
    vyska_mrizky = radky * h + (radky - 1) * styl["mezera"] + popisek_v
    x = (kontext.get("sirka", SIRKA) - sirka_mrizky) // 2
    # nad obličejem nahoře pod pásmem; přes obličej (nebo přes titulky) uprostřed pásma
    y = y0 if not (pres or pres_titulky) else y0 + max(0, (y1 - y0 - vyska_mrizky) // 2)
    spec.update({"x": int(x), "y": int(y), "sirka": int(sirka_mrizky), "vyska": int(vyska_mrizky),
                 "dlazdice_sirka": int(w), "dlazdice": _rozloz(spec, styl, w, x, y)})
    # první obálka: větší, uprostřed dlaždic (bez popisku)
    stred_x = x + sirka_mrizky / 2
    stred_y = y + (vyska_mrizky - popisek_v) / 2
    wv = min(w * VELKA, sirka_dost, (y1 - y0) * 9 / 16)
    hv = wv * 16 / 9
    spec["velka"] = [int(stred_x - wv / 2), int(stred_y - hv / 2), int(wv), int(hv)]
    spec["stred"] = [int(stred_x), int(stred_y)]


def obdelnik(spec, styl):
    """Obdélník celé mřížky (i s popiskem) po animaci. Přes obličej = kontrola to má hlásit."""
    return spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"]


def casy_dlazdic(spec):
    """Kdy která dlaždice vylétá a jak dlouho letí: (starty, délka letu, konec rozmnožení)."""
    n = len(spec.get("cesty") or spec["soubory"])
    let = max(MIN_LET_S, ROZMNOZENI_S - max(0, n - 2) * ZPOZDENI_S)
    starty = [UVOD_S + max(0, i - 1) * ZPOZDENI_S for i in range(n)]
    return starty, let, max(s + let for s in starty)


def delka_animace(spec):
    _, _, konec = casy_dlazdic(spec)
    return konec + (POPISEK_S if spec.get("popisek") else 0.0)


def stav(spec, t):
    """Číslo snímku animace, 's' v klidu, záporné číslo při mizení, None mimo čas prvku."""
    t_rel = t - spec["od"]
    if t_rel < 0 or t >= spec["do"]:
        return None
    zbyva = spec["do"] - t
    if zbyva < VYSTUP_S:
        return -(int(zbyva * FPS) + 1)
    if t_rel < delka_animace(spec):
        return int(t_rel * FPS)
    return "s"


def _dlazdice(cesta, w, h, styl):
    """Obálka oříznutá na 9:16, zaoblené rohy, krémový okraj. Hotové dlaždice se pamatují."""
    klic = (cesta, w, h)
    if klic in _DLAZDICE:
        return _DLAZDICE[klic]
    o, r = styl["okraj_px"], styl["rohy"]
    im = Image.open(cesta).convert("RGB")
    cil = (max(1, w - 2 * o), max(1, h - 2 * o))
    pomer = max(cil[0] / im.width, cil[1] / im.height)
    im = im.resize((max(1, int(round(im.width * pomer))), max(1, int(round(im.height * pomer)))), Image.LANCZOS)
    lx, ly = (im.width - cil[0]) // 2, (im.height - cil[1]) // 2
    im = im.crop((lx, ly, lx + cil[0], ly + cil[1]))
    maska = Image.new("L", cil, 0)
    ImageDraw.Draw(maska).rounded_rectangle((0, 0, cil[0] - 1, cil[1] - 1), radius=max(1, r - o), fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=tuple(styl["okraj"]) + (255,))
    out.paste(im, (o, o), maska)
    _DLAZDICE[klic] = out
    return out


def _poloz(platno, dl, x, y, w, h, alfa):
    """Položí dlaždici zmenšenou na w x h na plátno, s průhledností alfa."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    im = dl if (w, h) == dl.size else dl.resize((w, h), Image.LANCZOS)
    if alfa < 1.0:
        im = im.copy()
        im.putalpha(ImageChops.multiply(im.getchannel("A"), Image.new("L", im.size, int(255 * alfa))))
    _poloz_bezpecne(platno, im, x, y)


def vykresli(spec, styl, klic):
    """Snímek mřížky pro klíč z stav(). Vrátí (RGBA obrázek 1080x1920, (0, 0))."""
    styl = _styl(styl)
    if klic == "s":
        t_rel, alfa_celku = 99.0, 1.0
    elif klic >= 0:
        t_rel, alfa_celku = klic / FPS, 1.0
    else:
        t_rel, alfa_celku = 99.0, _clamp(((-klic - 1) / FPS) / VYSTUP_S)
    ztmav = _clamp(float(spec.get("ztmavit", 0.5))) * _clamp(t_rel / ZTMAVENI_S)
    platno = Image.new("RGBA", (SIRKA, VYSKA), tuple(styl["ztmaveni"]) + (int(255 * ztmav),))
    w, h = spec["dlazdice_sirka"], spec["dlazdice"][0][3]
    vx, vy, vw, vh = spec["velka"]
    sx, sy = spec["stred"]
    starty, let, _ = casy_dlazdic(spec)
    # ostatní dlaždice vylétají zpoza první, proto se kreslí dřív a první nakonec navrch
    for i in range(len(spec["cesty"]) - 1, -1, -1):
        dl = _dlazdice(spec["cesty"][i], w, h, styl)
        cx, cy, cw, ch = spec["dlazdice"][i]
        p = _clamp((t_rel - starty[i]) / let)
        if i == 0:
            if t_rel < UVOD_S:
                q = _ease_out_back(_clamp(t_rel / UVOD_S))
                tw, th = vw * max(0.05, q), vh * max(0.05, q)
                _poloz(platno, dl, sx - tw / 2, sy - th / 2, tw, th, _clamp(t_rel / 0.12))
                continue
            e = _ease_out_cubic(p)
            tw, th = vw + (cw - vw) * e, vh + (ch - vh) * e
            tx, ty = vx + (cx - vx) * e, vy + (cy - vy) * e
            _poloz(platno, dl, tx, ty, tw, th, 1.0)
        else:
            if p <= 0:
                continue
            e = _ease_out_cubic(p)
            m = 0.55 + 0.45 * _ease_out_back(p)
            tw, th = cw * m, ch * m
            # střed dlaždice letí ze středu mřížky do středu svého místa
            tx = (sx - tw / 2) + ((cx + cw / 2) - sx) * e
            ty = (sy - th / 2) + ((cy + ch / 2) - sy) * e
            _poloz(platno, dl, tx, ty, tw, th, _clamp(p / 0.25))
    if spec.get("popisek"):
        _, _, konec = casy_dlazdic(spec)
        a = _clamp((t_rel - konec) / POPISEK_S)
        if a > 0:
            f = pismo(styl["pismo"], styl["velikost"], styl["varianta"])
            text = spec["popisek"]
            tw = f.getlength(text)
            ty = spec["y"] + spec["vyska"] - _vyska_popisku(spec, styl) + styl["mezera"] + int(10 * (1 - a))
            ImageDraw.Draw(platno).text((int((SIRKA - tw) / 2), ty), text, font=f, fill=tuple(styl["barva"]) + (int(255 * a),))
    if alfa_celku < 1.0:
        platno.putalpha(ImageChops.multiply(platno.getchannel("A"), Image.new("L", platno.size, int(255 * alfa_celku))))
    return platno, (0, 0)
