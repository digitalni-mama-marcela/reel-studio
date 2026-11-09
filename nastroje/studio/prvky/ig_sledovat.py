"""Karta profilu s tlačítkem Sledovat, které se po ťuknutí změní na Sledováno (jako na Instagramu).

Zadání Marcely 3. 11. 2026 („dej follow“ – ať je vidět sledování jako na Instagramu, s mou profilovou fotkou).
Vlastní kresba bez loga. Je to výzva, proto zůstává vpředu nad titulky (jako karta výzvy na hrudi).

Spec v osa["prvky"]:
  {"typ": "ig_sledovat", "od": 76.6, "do": 79.9, "jmeno": "digitalni_mama_marcela",
   "popis": "Praktické AI tipy", "fotka": "/cesta/profilovka.png", "tuk": 1.3, "y": 1110}
  tuk  kdy se ťukne na tlačítko (s od začátku prvku)
"""
from PIL import Image, ImageDraw

from ..titulky import SIRKA, pismo
from ._spolecne import karta, kulata_fotka, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W, H = 820, 150
MODRA = (0, 149, 246)


def pripravit(spec, styl, kontext):
    spec["x"], spec["y"] = (SIRKA - W) // 2, int(spec.get("y") or 1110)
    spec["sirka"], spec["vyska"] = W, H
    spec.setdefault("za_hlavou", False)


def stav(spec, t):
    return stav_obecny(spec, t, float(spec.get("tuk", 1.3)) + 0.6)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + H)


def vykresli(spec, styl, klic):
    tuk = float(spec.get("tuk", 1.3))
    t, odchod = rozloz_klic(klic, spec, tuk + 0.6)
    im, pad = karta(W, H, (255, 255, 255, 252), H // 2, stin=70, pad=24)
    d = ImageDraw.Draw(im)
    im.alpha_composite(kulata_fotka(spec.get("fotka"), 104), (pad + 24, pad + 23))
    fj = pismo("Montserrat-wght.ttf", 34, "Bold")
    jmeno = spec.get("jmeno", "digitalni_mama_marcela")
    while fj.getlength(jmeno) > 400 and fj.size > 24:
        fj = pismo("Montserrat-wght.ttf", fj.size - 2, "Bold")
    d.text((pad + 148, pad + 46), jmeno, font=fj, fill=(20, 20, 20))
    d.text((pad + 148, pad + 92), spec.get("popis", ""), font=pismo("Montserrat-wght.ttf", 26, "Medium"), fill=(142, 142, 142))
    bx0, by0, bx1, by1 = pad + W - 250, pad + 40, pad + W - 30, pad + H - 40
    stisk = 0.0
    if tuk <= t < tuk + 0.18:
        stisk = 1 - abs(1 - 2 * (t - tuk) / 0.18)
    if stisk:
        s = 6 * stisk
        bx0, by0, bx1, by1 = bx0 + s, by0 + s, bx1 - s, by1 - s
    fb = pismo("Montserrat-wght.ttf", 30, "Bold")
    if t < tuk + 0.09:
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=16, fill=MODRA)
        d.text(((bx0 + bx1) / 2, (by0 + by1) / 2), "Sledovat", font=fb, fill=(255, 255, 255), anchor="mm")
    else:
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=16, fill=(239, 239, 239), outline=(219, 219, 219), width=2)
        d.text(((bx0 + bx1) / 2, (by0 + by1) / 2), "Sledováno", font=fb, fill=(20, 20, 20), anchor="mm")
    if tuk - 0.05 <= t < tuk + 0.45:                       # kruh ťuknutí
        p = (t - tuk + 0.05) / 0.5
        r = 20 + 60 * p
        cx, cy = (bx0 + bx1) / 2 + 40, (by0 + by1) / 2
        vr = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(vr).ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, int(220 * (1 - p))), width=6)
        ImageDraw.Draw(vr).ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(40, 40, 40, int(120 * (1 - p))))
        im.alpha_composite(vr)
    p = pruzne(t / 0.3)
    if p < 0.999:
        w2, h2 = max(1, int(im.width * (0.7 + 0.3 * p))), max(1, int(im.height * (0.7 + 0.3 * p)))
        mal = nasob_alfu(im.resize((w2, h2)), min(1.0, t / 0.15))
        im = Image.new("RGBA", im.size, (0, 0, 0, 0))
        im.alpha_composite(mal, ((im.width - w2) // 2, (im.height - h2) // 2))
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
