"""Časová osa střihového programu nad hlavou: stopy s náhledy záběrů, vlna zvuku, bloky textu a běžící hlava přehrávání.

Zadání Marcely 3. 11. 2026 („o střihu videí nic nevím“ – ukázat, jak vypadá střihový program). Kreslí se vlastní
obecné rozhraní (žádné logo ani vzhled konkrétní aplikace), náhledy a vlna jsou ze skutečných záběrů zákaznice.
Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "casova_osa", "od": 21.6, "do": 24.1, "nahledy": ["/cesta/n1.jpg", ...], "vlna": [0.2, 0.8, ...],
   "nazev": "Časová osa", "y": 240}
  nahledy  obrázky záběrů do stopy V1 (opakují se po celé šířce)
  vlna     hlasitost řeči 0..1 (libovolný počet hodnot) pro stopu A1
"""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from ..titulky import FPS, HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import karta, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W, H = 960, 470
STOPY = ["T1", "V2", "V1", "A1", "A2"]
LEVY = 92                 # šířka sloupce s názvy stop
HORNI = 112               # záhlaví a pravítko
VYSKA_STOPY = 66
POZADI = (24, 22, 26)
CERVENA = (232, 84, 104)


def pripravit(spec, styl, kontext):
    y = int(spec.get("y") or HORNI_OKRAJ + 20)
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = (SIRKA - W) // 2, y, W, H


def stav(spec, t):
    return stav_obecny(spec, t, None)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + H)


@lru_cache(maxsize=2)
def _panel(nahledy, vlna, nazev):
    im, pad = karta(W, H, POZADI + (245,), 26, stin=110)
    d = ImageDraw.Draw(im)
    ox, oy = pad, pad
    d.text((ox + 26, oy + 22), nazev, font=pismo("Montserrat-wght.ttf", 28, "Bold"), fill=(235, 235, 235))
    # pravítko
    f = pismo("CourierPrime-Regular.ttf", 18)
    for i in range(7):
        x = ox + LEVY + i * (W - LEVY - 20) / 6
        d.text((x, oy + 74), "0:%02d" % (i * 10), font=f, fill=(150, 150, 150))
        for j in range(10):
            xx = x + j * (W - LEVY - 20) / 60
            d.line((xx, oy + 98, xx, oy + 104 if j else oy + 108), fill=(110, 110, 110), width=1)
    fs = pismo("CourierPrime-Bold.ttf", 20)
    sirka_stop = W - LEVY - 20
    for i, s in enumerate(STOPY):
        y = oy + HORNI + i * VYSKA_STOPY
        d.text((ox + 24, y + VYSKA_STOPY / 2), s, font=fs, fill=(170, 170, 170), anchor="lm")
        d.ellipse((ox + 62, y + VYSKA_STOPY / 2 - 3, ox + 68, y + VYSKA_STOPY / 2 + 3), fill=(120, 120, 120))
        x0, x1 = ox + LEVY, ox + LEVY + sirka_stop
        y0, y1 = y + 8, y + VYSKA_STOPY - 8
        if s == "V2":
            rng = np.random.default_rng(4)
            x = x0 + 30
            while x < x1 - 60:
                w = int(rng.integers(36, 110))
                d.rounded_rectangle((x, y0, min(x + w, x1), y1), radius=7, fill=(238, 232, 222))
                x += w + int(rng.integers(14, 70))
        elif s == "V1" and nahledy:
            vys = y1 - y0
            sir = int(vys * 0.75)
            x, k = x0, 0
            while x < x1:
                n = Image.open(nahledy[k % len(nahledy)]).convert("RGB")
                n = n.resize((sir, int(sir * n.height / n.width))).crop((0, 0, sir, vys))
                im.paste(n.crop((0, 0, min(sir, int(x1 - x)), vys)), (int(x), int(y0)))
                x += sir
                k += 1
            for x in np.linspace(x0, x1, 5)[1:-1]:
                d.line((x, y0, x, y1), fill=POZADI, width=4)
        elif s == "A1" and vlna:
            d.rounded_rectangle((x0, y0, x1, y1), radius=6, fill=(84, 104, 92))
            v = np.interp(np.linspace(0, len(vlna) - 1, int(sirka_stop / 3)), np.arange(len(vlna)), vlna)
            stred = (y0 + y1) / 2
            for j, a in enumerate(v):
                hh = max(1.5, a * (y1 - y0) * 0.45)
                d.line((x0 + j * 3, stred - hh, x0 + j * 3, stred + hh), fill=(170, 196, 178), width=2)
        elif s == "A2":
            rng = np.random.default_rng(9)
            for a, b in ((0.0, 0.46), (0.57, 0.68)):
                xa, xb = x0 + a * sirka_stop, x0 + b * sirka_stop
                d.rounded_rectangle((xa, y0, xb, y1), radius=6, fill=(150, 128, 70))
                for xx in np.arange(xa + 3, xb - 3, 3):
                    hh = (0.25 + 0.6 * rng.random()) * (y1 - y0) * 0.42
                    d.line((xx, (y0 + y1) / 2 - hh, xx, (y0 + y1) / 2 + hh), fill=(214, 190, 120), width=2)
    return im, pad


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, 0)
    panel, pad = _panel(tuple(spec.get("nahledy") or ()), tuple(round(float(v), 3) for v in spec.get("vlna") or ()),
                        spec.get("nazev", "Časová osa"))
    im = panel.copy()
    d = ImageDraw.Draw(im)
    delka = float(spec["do"]) - float(spec["od"])
    sirka_stop = W - LEVY - 20
    x = pad + LEVY + sirka_stop * (0.18 + 0.6 * min(1.0, t / max(delka, 0.1)))
    d.line((x, pad + 96, x, pad + H - 14), fill=CERVENA, width=3)
    d.polygon([(x - 11, pad + 84), (x + 11, pad + 84), (x + 11, pad + 98), (x, pad + 108), (x - 11, pad + 98)], fill=CERVENA)
    snimky = int(round((float(spec["od"]) + t) * FPS))
    s = snimky // FPS
    tc = "00:00:%02d:%02d" % (s % 60, snimky % FPS)
    d.text((pad + W / 2, pad + 38), tc, font=pismo("CourierPrime-Bold.ttf", 30), fill=(235, 235, 235), anchor="mm")
    p = pruzne(t / 0.35)
    if p < 0.999:
        w2, h2 = max(1, int(im.width * (0.85 + 0.15 * p))), max(1, int(im.height * (0.85 + 0.15 * p)))
        mal = im.resize((w2, h2))
        im = Image.new("RGBA", panel.size, (0, 0, 0, 0))
        im.alpha_composite(nasob_alfu(mal, min(1.0, t / 0.2)), ((panel.width - w2) // 2, (panel.height - h2) // 2))
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
