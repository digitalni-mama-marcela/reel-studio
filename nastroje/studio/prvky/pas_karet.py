"""Pás karet: řada vysokých karet (b-roll, obálky reelů, fotky) nad hlavou, která pomalu jede zprava doleva.

Zadání Marcely 3. 11. 2026.
Vzhled: u věty o b-rollu vyjede nad hlavou řada čtyř karet 9:16
se zaoblenými rohy a celá řada se posouvá doleva. Videa v kartách hrají (bez zvuku). Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "pas_karet", "od": 14.5, "do": 16.6, "soubory": ["broll-1.mov", "obalka.jpg", ...],
   "vyska_karty": 330, "y": 250, "posun_px_s": 120}
  soubory      2 až 8 souborů (obrázky nebo videa); řada se opakuje, aby pokryla celou šířku
  vyska_karty  výška karty (šířka = 9:16), výchozí 330 px
  posun_px_s   rychlost posunu doleva (výchozí 120 px/s)
"""
import hashlib
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from ..titulky import FPS, SIRKA
from ._spolecne import VIDEO_PRIPONY, najdi_soubor, nahled, nasob_alfu, snimek_videa, snimky_videa, stav_obecny

MEZERA = 14
NASTUP_S = 0.35
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def pripravit(spec, styl, kontext):
    spec["cesty"] = [najdi_soubor(s, kontext) for s in spec["soubory"][:8]]
    h = int(spec.get("vyska_karty", 330))
    spec["kw"], spec["kh"] = int(h * 9 / 16), h
    spec["x"], spec["y"] = 0, int(spec.get("y") or kontext["horni"] + 30)
    spec["sirka"], spec["vyska"] = SIRKA, h
    delka = float(spec["do"]) - float(spec["od"]) + 0.2
    spec["videa"] = {}
    for c in spec["cesty"]:
        if c.lower().endswith(VIDEO_PRIPONY):
            if Path(c).exists():
                cil = Path(kontext.get("podklady") or tempfile.gettempdir()) / ".nahledy" / ("pas_%s.rgb" % hashlib.sha1(
                    ("%s|%d|%.2f" % (c, h, delka)).encode()).hexdigest()[:12])
                spec["videa"][c] = snimky_videa(c, 1.0, delka, spec["kw"], spec["kh"], cil)


def stav(spec, t):
    return stav_obecny(spec, t, None)      # karty jedou celou dobu, každý snímek je jiný


def obdelnik(spec, styl):
    return (0, spec["y"], SIRKA, spec["y"] + spec["vyska"])


def _karta(spec, c, i_snimku):
    kw, kh = spec["kw"], spec["kh"]
    if c in spec.get("videa", {}):
        cesta, n = spec["videa"][c]
        obr = snimek_videa(cesta, kw, kh, i_snimku, n)
    else:
        obr = nahled(c, kw, kh)
    m = Image.new("L", (kw, kh), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, kw - 1, kh - 1), radius=18, fill=255)
    k = Image.new("RGBA", (kw, kh), (0, 0, 0, 0))
    k.paste(obr, (0, 0), m)
    return k


def vykresli(spec, styl, klic):
    if klic[0] == "z":
        t = float(spec["do"]) - float(spec["od"]) - klic[1] / FPS
        odchod = max(0.0, min(1.0, klic[1] / FPS / 0.25)) ** 2
    else:
        t, odchod = klic[1] / FPS, 1.0
    kw = spec["kw"]
    krok = kw + MEZERA
    nastup = 1 - (1 - min(1.0, t / NASTUP_S)) ** 3
    posun = t * float(spec.get("posun_px_s", 120)) - (1 - nastup) * 400      # vjezd zprava a posun doleva
    plat = Image.new("RGBA", (SIRKA, spec["kh"]), (0, 0, 0, 0))
    n = len(spec["cesty"])
    x0 = 30 - posun
    i = 0
    while x0 + i * krok < SIRKA:
        x = x0 + i * krok
        if x + kw > 0:
            k = _karta(spec, spec["cesty"][i % n], int(t * FPS))
            plat.alpha_composite(k, (max(0, int(x)), 0), (max(0, -int(x)), 0))
        i += 1
    return nasob_alfu(plat, odchod * min(1.0, t / 0.15)), (0, spec["y"])
