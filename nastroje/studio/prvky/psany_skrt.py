"""Řádek textu, který se napíše po písmenech a pak ho přeškrtne červená čára (nad velkým slovem za hlavou).

Zadání Marcely 3. 11. 2026 („NIKDY velký nadpis za mnou a editační aplikaci tam napiš a přeškrtni červeně“).
Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "psany_skrt", "od": 61.7, "do": 63.9, "text": "otvírat editační aplikaci", "y": 300,
   "rychlost": 22, "skrt_za": 0.2, "velikost": 46}
  rychlost  znaků za sekundu; skrt_za: pauza po dopsání před přeškrtnutím (s)
"""
from PIL import Image, ImageDraw

from ..titulky import HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import CERVENA, KREM, nasob_alfu, rozloz_klic, stav_obecny

SKRT_S = 0.3


def _casy(spec):
    psani = len(spec["text"]) / float(spec.get("rychlost", 22))
    skrt = psani + float(spec.get("skrt_za", 0.2))
    return psani, skrt


def _font(spec):
    return pismo("Montserrat-wght.ttf", int(spec.get("velikost", 46)), "SemiBold")


def pripravit(spec, styl, kontext):
    f = _font(spec)
    w = int(f.getlength(spec["text"])) + 40
    spec["x"], spec["y"] = (SIRKA - w) // 2, int(spec.get("y") or HORNI_OKRAJ + 60)
    spec["sirka"], spec["vyska"] = w, int(f.size * 1.6)


def stav(spec, t):
    return stav_obecny(spec, t, _casy(spec)[1] + SKRT_S)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])


def vykresli(spec, styl, klic):
    psani, skrt = _casy(spec)
    t, odchod = rozloz_klic(klic, spec, skrt + SKRT_S)
    f = _font(spec)
    txt = spec["text"]
    n = min(len(txt), int(t / max(psani, 0.01) * len(txt)) + 1)
    im = Image.new("RGBA", (spec["sirka"] + 20, spec["vyska"] + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    stin = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(stin).text((32, 12 + f.size * 0.8 + 3), txt[:n], font=f, fill=(0, 0, 0, 110), anchor="ls")
    im.alpha_composite(stin)
    d.text((30, 10 + f.size * 0.8), txt[:n], font=f, fill=KREM, anchor="ls")
    if t >= skrt:
        p = min(1.0, (t - skrt) / SKRT_S)
        p = 1 - (1 - p) ** 2
        y = 10 + f.size * 0.52
        d.line((22, y + 3, 22 + (f.getlength(txt) + 16) * p, y - 2), fill=CERVENA, width=max(5, f.size // 9))
    return nasob_alfu(im, odchod), (spec["x"] - 10, spec["y"] - 10)
