"""Složka: bílé okno nad hlavou, vlevo hromádka náhledů klipů, vpravo modrá složka. Klipy přeletí do složky.

Zadání Marcely 3. 11. 2026.
Vzhled: u věty „klipy hodím do složky“ přeletí hromádka fotek do složky
s popiskem, ve složce zůstane malá fotka a červený odznak. Kreslí se vlastní obecná složka (bez loga systému).
Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "slozka", "od": 13.0, "do": 14.6, "soubory": ["klip-1.mov", "klip-2.mov", "klip-3.mov"],
   "nazev": "moje klipy", "presun": 13.5, "y": 250}
  soubory  1 až 4 náhledy do hromádky (obrázky nebo videa, z videa snímek v 1. sekundě)
  nazev    popisek pod složkou
  presun   čas reelu, kdy hromádka přeletí do složky (výchozí 0,45 s po začátku)
"""
import math

from PIL import Image, ImageDraw

from ..titulky import SIRKA, pismo
from ._spolecne import karta, karta_s_nahledem, najdi_soubor, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W, H = 560, 230
LET_S = 0.45
MODRA = (95, 170, 230)
MODRA_TMAVA = (70, 145, 210)
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def pripravit(spec, styl, kontext):
    spec["cesty"] = [najdi_soubor(s, kontext) for s in spec["soubory"][:4]]
    spec["x"], spec["y"] = (SIRKA - W) // 2, int(spec.get("y") or kontext["horni"] + 30)
    spec["sirka"], spec["vyska"] = W, H


def _presun(spec):
    return float(spec.get("presun", float(spec["od"]) + 0.45)) - float(spec["od"])


def _konec(spec):
    return _presun(spec) + LET_S + 0.25


def stav(spec, t):
    return stav_obecny(spec, t, _konec(spec))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + H)


def _slozka(d, x, y, w, h, meritko=1.0):
    w, h = w * meritko, h * meritko
    x, y = x - w / 2, y - h / 2
    d.rounded_rectangle((x, y, x + w * 0.42, y + h * 0.3), radius=int(10 * meritko), fill=MODRA_TMAVA)
    d.rounded_rectangle((x, y + h * 0.14, x + w, y + h), radius=int(12 * meritko), fill=MODRA)


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, _konec(spec))
    im, pad = karta(W, H, (255, 255, 255, 248), 28, stin=90)
    d = ImageDraw.Draw(im)
    fx, fy = pad + W * 0.72, pad + H * 0.43
    p = max(0.0, min(1.0, (t - _presun(spec)) / LET_S))
    u = (t - _presun(spec) - LET_S) / 0.25          # složka se po dopadu klipů krátce nafoukne
    _slozka(d, fx, fy, 150, 112, 1.0 + 0.12 * math.sin(math.pi * u) if 0 < u < 1 else 1.0)
    f = pismo("Inter-wght.ttf", 26, "Medium")
    d.text((fx, pad + H * 0.43 + 80), spec.get("nazev", "moje klipy"), font=f, fill=(60, 60, 60), anchor="mt")
    # hromádka: karty mírně natočené přes sebe; při přesunu letí obloukem do složky a zmenšují se
    hx, hy = pad + W * 0.24, pad + H * 0.5
    for j, c in enumerate(spec["cesty"]):
        k = karta_s_nahledem(c, 96, 126, okraj=4, radius=6)
        k = k.rotate((-8, 5, -3, 9)[j % 4], resample=Image.BICUBIC, expand=True)
        q = max(0.0, min(1.0, p * 1.15 - j * 0.05))
        e = q * q * (3 - 2 * q)
        x = hx + (fx - hx) * e + j * 6
        y = hy + (fy - hy) * e - 70 * 4 * e * (1 - e)
        m = 1.0 - 0.7 * e
        if q >= 0.999:
            continue
        k = k.resize((max(1, int(k.width * m)), max(1, int(k.height * m))), Image.BILINEAR)
        im.alpha_composite(k, (int(x - k.width / 2), int(y - k.height / 2)))
    if p >= 1.0:
        # ve složce zůstane malý náhled a odznak s počtem klipů
        k = karta_s_nahledem(spec["cesty"][0], 40, 52, okraj=3, radius=4).rotate(-6, expand=True)
        im.alpha_composite(k, (int(fx - 50), int(fy - 50)))
        d = ImageDraw.Draw(im)
        b = pruzne(min(1.0, (t - _presun(spec) - LET_S) / 0.2))
        r = 17 * b
        d.ellipse((fx + 60 - r, fy - 55 - r, fx + 60 + r, fy - 55 + r), fill=(235, 72, 60))
        if b > 0.6:
            d.text((fx + 60, fy - 55), str(len(spec["cesty"])), font=pismo("Inter-wght.ttf", 22, "Bold"), fill=(255, 255, 255), anchor="mm")
    q = pruzne(t / 0.25)
    if q < 0.999:
        w2, h2 = max(1, int(im.width * (0.8 + 0.2 * q))), max(1, int(im.height * (0.8 + 0.2 * q)))
        mal = nasob_alfu(im.resize((w2, h2)), min(1.0, t / 0.12))
        im = Image.new("RGBA", im.size, (0, 0, 0, 0))
        im.alpha_composite(mal, ((im.width - w2) // 2, (im.height - h2) // 2))
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
