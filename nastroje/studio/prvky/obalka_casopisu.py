"""Obálka časopisu za osobou: tenký zlatý rám, velký název časopisu, drobné titulky obálky a čárový kód.

Zadání Marcely 3. 11. 2026 („jako z magazínu Vogue, ať i pozadí za mnou vypadá jako obálka“). Jde za osobu
(maska), název časopisu leží za hlavou jako na skutečné obálce.

Spec v osa["prvky"]:
  {"typ": "obalka_casopisu", "od": 18.3, "do": 21.4, "nazev": "VOGUE",
   "rubrika": "JEDNA VĚTA", "titulek": "Celé video,\\nsestříhané.", "vpravo": "@digitalni_mama_marcela",
   "radek": "Č. 01 · LISTOPAD 2026 · SESTŘÍHAL CLAUDE", "kod": "Č. 01 LIS 2026", "y_nazvu": 560}
Vše kromě "nazev" je volitelné. Prvky naskočí postupně za 0,6 s (rám, texty, název, kód).
"""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from ..titulky import HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import KREM, hladce, nasob_alfu, rozloz_klic, stav_obecny, text

ZLATA = (214, 186, 120)
OKRAJ_X, Y0, Y1 = 50, HORNI_OKRAJ + 10, 1430
ANIMACE_S = 0.7


def pripravit(spec, styl, kontext):
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = OKRAJ_X, Y0, SIRKA - 2 * OKRAJ_X, Y1 - Y0


def stav(spec, t):
    return stav_obecny(spec, t, ANIMACE_S)


def obdelnik(spec, styl):
    return (OKRAJ_X, Y0, SIRKA - OKRAJ_X, Y0 + 300)        # do kontroly jen horní pás s texty


def _carovy_kod(w, h, popisek):
    im = Image.new("RGBA", (w, h), (250, 248, 242, 255))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(11)
    x = 10
    while x < w - 12:
        sirka = int(rng.choice([2, 2, 3, 4, 6]))
        d.rectangle((x, 10, x + sirka - 1, h - 34), fill=(20, 20, 20))
        x += sirka + int(rng.choice([2, 3, 4]))
    d.text((w // 2, h - 8), popisek, font=pismo("CourierPrime-Regular.ttf", 18), fill=(20, 20, 20), anchor="ms")
    return im


@lru_cache(maxsize=4)
def _vrstvy(nazev, rubrika, titulek, vpravo, radek, kod, y_nazvu):
    """Tři vrstvy plátna celé obálky: rám a drobné texty, název, čárový kód."""
    w, h = SIRKA - 2 * OKRAJ_X, Y1 - Y0
    ram = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ram)
    d.rectangle((0, 0, w - 1, h - 1), outline=ZLATA + (235,), width=3)
    if rubrika:
        text(d, (40, 48), rubrika, "CourierPrime-Bold.ttf", 26, barva=KREM + (230,), proklad=6)
    if titulek:
        f = pismo("Montserrat-wght.ttf", 50, "Bold")
        for i, r in enumerate(titulek.split("\n")):
            d.text((40, 92 + i * 60), r, font=f, fill=KREM + (255,))
    if vpravo:
        d.text((w - 40, 52), vpravo, font=pismo("CourierPrime-Regular.ttf", 24), fill=KREM + (220,), anchor="ra")
    if radek:
        f = pismo("CourierPrime-Bold.ttf", 25)
        sirka = sum(f.getlength(z) + 7 for z in radek)
        text(d, ((w - sirka) / 2, y_nazvu - Y0 - 70), radek, "CourierPrime-Bold.ttf", 25, barva=KREM + (230,), proklad=7)
    vrstva_nazvu = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dn = ImageDraw.Draw(vrstva_nazvu)
    vel = 260
    f = pismo("BodoniModa-wght.ttf", vel, "Bold")
    while f.getlength(nazev) > w - 40 and vel > 120:
        vel -= 10
        f = pismo("BodoniModa-wght.ttf", vel, "Bold")
    dn.text((w / 2, y_nazvu - Y0), nazev, font=f, fill=KREM + (255,), anchor="mt")
    kod_im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if kod:
        kod_im.alpha_composite(_carovy_kod(200, 120, kod), (40, h - 300))
    return ram, vrstva_nazvu, kod_im


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, ANIMACE_S)
    ram, nazev, kod = _vrstvy(spec.get("nazev", "VOGUE"), spec.get("rubrika", ""), spec.get("titulek", ""),
                              spec.get("vpravo", ""), spec.get("radek", ""), spec.get("kod", ""),
                              int(spec.get("y_nazvu", 560)))
    out = Image.new("RGBA", ram.size, (0, 0, 0, 0))
    for vrstva, zac in ((ram, 0.0), (nazev, 0.12), (kod, 0.3)):
        a = hladce((t - zac) / 0.3) * odchod
        if a > 0:
            out.alpha_composite(nasob_alfu(vrstva, a))
    return out, (OKRAJ_X, Y0)
