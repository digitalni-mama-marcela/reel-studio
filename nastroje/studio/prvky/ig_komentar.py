"""Komentář jako na Instagramu: výzva nahoře, pole komentáře, do kterého se napíše slovo, odeslání a odpověď autorky.

Zadání Marcely 3. 11. 2026 („napiš STUDIO do komentáře“ – ať to vypadá jako komentář na Instagramu, který se
napíše a já hned odpovím). Vlastní kresba (bílé kapsle, kulaté fotky), žádné logo. Leží nad hlavou.

Spec v osa["prvky"]:
  {"typ": "ig_komentar", "od": 72.8, "do": 76.1, "vyzva": "Napiš do komentáře\\nSTUDIO",
   "slovo": "STUDIO", "kdo": "tvuj_ucet", "autorka": "digitalni_mama_marcela",
   "odpoved": "Posílám ti všechny informace.", "fotka": "/cesta/profilovka.png", "y": 240,
   "zacni_psat": 0.5, "rychlost": 9}
  zacni_psat  kdy se začne psát (s od začátku prvku); rychlost: znaků za sekundu
Klíč stav: ("a", snímek) během animace, pak "s".
"""
from functools import lru_cache

from PIL import Image, ImageDraw

from ..titulky import HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import SVESTKOVA, karta, kulata_fotka, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W = 860
CERNA = (20, 20, 20)
SEDA = (142, 142, 142)


def _casy(spec):
    zac = float(spec.get("zacni_psat", 0.5))
    psani = len(spec.get("slovo", "STUDIO")) / float(spec.get("rychlost", 9))
    odeslani = zac + psani + 0.3
    return zac, psani, odeslani, odeslani + 0.5      # odpověď naskočí 0,5 s po odeslání


def pripravit(spec, styl, kontext):
    spec["x"], spec["y"] = (SIRKA - W) // 2, int(spec.get("y") or HORNI_OKRAJ + 20)
    spec["sirka"], spec["vyska"] = W, 420


def stav(spec, t):
    return stav_obecny(spec, t, _casy(spec)[3] + 0.4)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + spec["vyska"])


@lru_cache(maxsize=2)
def _vyzva(text):
    f = pismo("Montserrat-wght.ttf", 46, "ExtraBold")
    radky = text.split("\n")
    w = int(max(f.getlength(r) for r in radky)) + 60
    h = 64 * len(radky) + 26
    im, pad = karta(w, h, (255, 255, 255, 250), 22, stin=60, pad=20)
    d = ImageDraw.Draw(im)
    for i, r in enumerate(radky):
        d.text((pad + w / 2, pad + 45 + i * 64), r, font=f, fill=CERNA, anchor="mm")
    return im


def _pole(slovo_napsane, kurzor, odeslano_p, fotka_kdo):
    """Pole komentáře: kulatá fotka, napsaný text s kurzorem, vpravo kulaté tlačítko odeslat."""
    h = 104
    im, pad = karta(W, h, (255, 255, 255, 252), h // 2, stin=60, pad=20)
    d = ImageDraw.Draw(im)
    im.alpha_composite(kulata_fotka(fotka_kdo, 66), (pad + 20, pad + 19))
    f = pismo("Montserrat-wght.ttf", 40, "Bold")
    if slovo_napsane:
        d.text((pad + 110, pad + h / 2), slovo_napsane, font=f, fill=CERNA, anchor="lm")
    else:
        d.text((pad + 110, pad + h / 2), "Přidej komentář…", font=pismo("Montserrat-wght.ttf", 36, "Medium"), fill=SEDA, anchor="lm")
    if kurzor:
        x = pad + 112 + f.getlength(slovo_napsane)
        d.line((x, pad + 30, x, pad + h - 30), fill=(0, 120, 255), width=3)
    cx, cy, r = pad + W - 58, pad + h / 2, 34
    barva = SVESTKOVA if slovo_napsane else (205, 200, 203)
    if odeslano_p:
        r = r * (1 + 0.18 * (1 - abs(1 - 2 * min(1.0, odeslano_p))))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=barva)
    d.line((cx, cy + 14, cx, cy - 14), fill=(255, 255, 255), width=5)
    d.line((cx - 12, cy - 2, cx, cy - 15), fill=(255, 255, 255), width=5)
    d.line((cx + 12, cy - 2, cx, cy - 15), fill=(255, 255, 255), width=5)
    return im


def _komentar(kdo, slovo, autorka, odpoved, fotka_kdo, fotka_autorky, ukaz_odpoved):
    h = 230 if ukaz_odpoved else 112
    im, pad = karta(W, h, (255, 255, 255, 252), 28, stin=60, pad=20)
    d = ImageDraw.Draw(im)
    fj = pismo("Montserrat-wght.ttf", 30, "Bold")
    ft = pismo("Montserrat-wght.ttf", 34, "Medium")
    fs = pismo("Montserrat-wght.ttf", 24, "Medium")
    im.alpha_composite(kulata_fotka(fotka_kdo, 64), (pad + 22, pad + 22))
    d.text((pad + 104, pad + 22), kdo, font=fj, fill=CERNA)
    d.text((pad + 104 + fj.getlength(kdo) + 14, pad + 26), "teď", font=fs, fill=SEDA)
    d.text((pad + 104, pad + 60), slovo, font=ft, fill=CERNA)
    if ukaz_odpoved:
        im.alpha_composite(kulata_fotka(fotka_autorky, 56), (pad + 104, pad + 134))
        d.text((pad + 176, pad + 132), autorka, font=fj, fill=CERNA)
        sir = fj.getlength(autorka)
        d.ellipse((pad + 186 + sir, pad + 138, pad + 210 + sir, pad + 162), fill=(0, 149, 246))
        d.text((pad + 198 + sir, pad + 150), "✓", font=pismo("DMSans-wght.ttf", 18, "Bold"), fill=(255, 255, 255), anchor="mm")
        d.text((pad + 176, pad + 172), odpoved, font=ft, fill=CERNA)
    return im


def vykresli(spec, styl, klic):
    zac, psani, odeslani, odpoved_t = _casy(spec)
    t, odchod = rozloz_klic(klic, spec, odpoved_t + 0.4)
    slovo = spec.get("slovo", "STUDIO")
    fotka_kdo, fotka_autorky = spec.get("fotka_kdo"), spec.get("fotka")
    plat = Image.new("RGBA", (W + 80, 520), (0, 0, 0, 0))
    vy = _vyzva(spec.get("vyzva", "Napiš do komentáře\nSTUDIO"))
    p = pruzne(t / 0.3)
    if p < 0.999:
        w2, h2 = max(1, int(vy.width * (0.7 + 0.3 * p))), max(1, int(vy.height * (0.7 + 0.3 * p)))
        plat.alpha_composite(nasob_alfu(vy.resize((w2, h2)), min(1.0, t / 0.15)), ((plat.width - w2) // 2, (vy.height - h2) // 2))
    else:
        plat.alpha_composite(vy, ((plat.width - vy.width) // 2, 0))
    y2 = vy.height - 10
    if t < odeslani + 0.2:
        n = 0 if t < zac else min(len(slovo), int((t - zac) / max(psani, 0.01) * len(slovo)) + 1)
        kurzor = t < odeslani and int(t * 2.5) % 2 == 0
        pole = _pole(slovo[:n], kurzor, max(0.0, (t - odeslani) / 0.2) if t >= odeslani else 0.0, fotka_kdo)
        a = min(1.0, max(0.0, (t - 0.15) / 0.2))
        plat.alpha_composite(nasob_alfu(pole, a), ((plat.width - pole.width) // 2, y2))
    else:
        km = _komentar(spec.get("kdo", "tvuj_ucet"), slovo, spec.get("autorka", "digitalni_mama_marcela"),
                       spec.get("odpoved", ""), fotka_kdo, fotka_autorky, t >= odpoved_t)
        posun = int(30 * (1 - min(1.0, (t - odeslani - 0.2) / 0.2)))
        plat.alpha_composite(nasob_alfu(km, min(1.0, (t - odeslani - 0.2) / 0.15)), ((plat.width - km.width) // 2, y2 + posun))
    return nasob_alfu(plat, odchod), (spec["x"] - 40, spec["y"] - 20)
