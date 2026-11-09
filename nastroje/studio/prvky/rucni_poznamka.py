"""Ruční poznámka: krátký text psaný rukou (napíše se po písmenech) a zahnutá šipka, která se dokreslí k osobě.

Zadání Marcely 3. 11. 2026.
Vzhled: vlevo nahoře je tenký bílý ručně psaný řádek o dvou řádcích
a pod ním zahnutá šipka mířící k osobě. Písmo Caveat (OFL 1.1, balicek/pisma/OFL-Caveat.txt, čeština OVĚŘENA 3. 11.).

Spec v osa["prvky"]:
  {"typ": "rucni_poznamka", "od": 9.0, "do": 11.5, "text": "jsem prostě\\nmáma", "x": 90, "y": 330,
   "sipka": "vpravo", "rychlost": 16}
  text      jeden nebo dva řádky (\\n)
  x, y      levý horní roh textu (výchozí vlevo nahoře pod bezpečným pásmem)
  sipka     "vpravo" (šipka se stáčí doprava dolů, k osobě uprostřed), "vlevo", nebo None bez šipky
  rychlost  znaků za sekundu (výchozí 16); šipka se kreslí 0,35 s po dopsání
"""
import math

from PIL import Image, ImageDraw, ImageFilter

from ..titulky import pismo
from ._spolecne import nasob_alfu, rozloz_klic, stav_obecny

VYCHOZI_STYL = {"pismo": "Caveat-wght.ttf", "varianta": "Bold", "velikost": 100, "barva": (255, 255, 255), "stin": 230}
SIPKA_S = 0.35
SIPKA_W, SIPKA_H = 190, 150
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def _s(styl):
    return dict(VYCHOZI_STYL, **(styl or {}))


def _rozmer(spec, s):
    f = pismo(s["pismo"], s["velikost"], s["varianta"])
    radky = spec["text"].split("\n")
    a, d = f.getmetrics()
    w = max(f.getlength(r) for r in radky)
    return f, radky, int(w), int((a + d) * 0.95 * len(radky))


def pripravit(spec, styl, kontext):
    s = _s(styl)
    _, _, w, h = _rozmer(spec, s)
    spec["x"] = int(spec.get("x", 80))
    spec["y"] = int(spec.get("y", kontext["horni"] + 110))
    spec["sirka"] = w + (SIPKA_W // 2 if spec.get("sipka", "vpravo") else 0)
    spec["vyska"] = h + (SIPKA_H if spec.get("sipka", "vpravo") else 0)


def _psani_s(spec):
    return len(spec["text"]) / float(spec.get("rychlost", 16))


def _konec(spec):
    return _psani_s(spec) + (SIPKA_S if spec.get("sipka", "vpravo") else 0)


def stav(spec, t):
    return stav_obecny(spec, t, _konec(spec))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])


def _krivka(p, x0, y0, x1, y1, ohyb):
    """Bod na kvadratické křivce z (x0, y0) do (x1, y1), řídicí bod posunutý kolmo o ohyb."""
    cx, cy = (x0 + x1) / 2 + ohyb, (y0 + y1) / 2 - ohyb * 0.3
    return ((1 - p) ** 2 * x0 + 2 * (1 - p) * p * cx + p * p * x1, (1 - p) ** 2 * y0 + 2 * (1 - p) * p * cy + p * p * y1)


def vykresli(spec, styl, klic):
    s = _s(styl)
    t, odchod = rozloz_klic(klic, spec, _konec(spec))
    f, radky, w, h = _rozmer(spec, s)
    pad = 30
    im = Image.new("RGBA", (spec["sirka"] + 2 * pad, spec["vyska"] + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    znaku = int(t * float(spec.get("rychlost", 16)))
    a, de = f.getmetrics()
    y = pad
    for r in radky:
        cast = r[:max(0, znaku)]
        znaku -= len(r) + 1
        d.text((pad, y), cast, font=f, fill=tuple(s["barva"]) + (255,))
        y += (a + de) * 0.95
    smer = spec.get("sipka", "vpravo")
    p = (t - _psani_s(spec)) / SIPKA_S
    if smer and p > 0:
        p = min(1.0, p)
        sx = pad + w * (0.35 if smer == "vpravo" else 0.65)
        x0, y0 = sx, pad + h + 8
        x1, y1 = sx + (SIPKA_W * 0.55 if smer == "vpravo" else -SIPKA_W * 0.55), pad + h + SIPKA_H - 16
        ohyb = -40 if smer == "vpravo" else 40
        body = [_krivka(i / 24 * p, x0, y0, x1, y1, ohyb) for i in range(25)]
        d.line(body, fill=tuple(s["barva"]) + (255,), width=7, joint="curve")
        if p >= 0.999:
            (ax, ay), (bx, by) = body[-2], body[-1]
            uhel = math.atan2(by - ay, bx - ax)
            for o in (0.55, -0.55):
                d.line([(bx, by), (bx - 26 * math.cos(uhel + o), by - 26 * math.sin(uhel + o))],
                       fill=tuple(s["barva"]) + (255,), width=7)
    if s.get("stin"):
        st = Image.new("RGBA", im.size, (0, 0, 0, 0))
        st.putalpha(im.getchannel("A").point(lambda v: v * s["stin"] // 255).filter(ImageFilter.GaussianBlur(6)))
        st.alpha_composite(im)
        im = st
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
