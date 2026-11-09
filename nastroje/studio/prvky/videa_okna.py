"""Okna se surovými videi vedle sebe nad hlavou (natočené záběry, nepovedené pokusy), volitelně se štítkem a popiskem.

Zadání Marcely 3. 11. 2026: „ukaž, kolik videí jsem nahrála, ať je vidět to surové video“ a „nahoru tři videa
s nepovedenými záběry“. Videa jsou úseky originálů zákaznice (jen se čtou), hrají bez zvuku ve smyčce.
Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "videa_okna", "od": 24.6, "do": 27.0,
   "videa": [{"soubor": "/cesta/klip.mov", "od": 3.0, "delka": 2.5}, ...],   # 1 až 6 oken
   "sirka": 170, "y": 240, "rozestup": 0.18,
   "stitek": "NEPOVEDENÝ ZÁBĚR",        # volitelně: nakloněný štítek přes každé okno
   "cisla": True,                       # volitelně: pořadí okna vlevo nahoře (1, 2, 3…)
   "popisek": ["5 videí", " · 6:42 surového záznamu"]}   # volitelně: pilulka pod okny, první část zvýrazněná
"""
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from ..titulky import FPS, HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import KREM, RUZOVA, SVESTKOVA, karta, nasob_alfu, pruzne, rozloz_klic, snimek_videa, snimky_videa, stav_obecny

MEZERA = 18
NASKOK_S = 0.3
RAM = 6


def _rozmery(spec):
    w = int(spec.get("sirka", 170))
    return w, int(w * 16 / 9)


def pripravit(spec, styl, kontext):
    w, h = _rozmery(spec)
    n = len(spec["videa"])
    celkem = n * w + (n - 1) * MEZERA
    spec["x"] = (SIRKA - celkem) // 2
    spec["y"] = int(spec.get("y") or HORNI_OKRAJ + 20)
    spec["sirka"], spec["vyska_okna"] = w, h
    spec["vyska"] = h + (90 if spec.get("popisek") else 0)
    pracovni = Path(spec.get("pracovni") or (Path(kontext.get("podklady") or ".").parent / "PRACOVNI" / "prvky-videa"))
    spec["_snimky"] = []
    for i, v in enumerate(spec["videa"]):
        cil = pracovni / ("%s_%.2f_%.2f_%dx%d.rgb" % (Path(v["soubor"]).stem, float(v["od"]), float(v["delka"]), w, h))
        spec["_snimky"].append(snimky_videa(v["soubor"], float(v["od"]), float(v["delka"]), w, h, cil))


def stav(spec, t):
    return stav_obecny(spec, t, None)


def obdelnik(spec, styl):
    n = len(spec["videa"])
    return (spec["x"], spec["y"], spec["x"] + n * spec["sirka"] + (n - 1) * MEZERA, spec["y"] + spec["vyska"])


@lru_cache(maxsize=4)
def _stitek(text, sirka):
    vel = max(16, int(sirka * 0.11))
    f = pismo("Montserrat-wght.ttf", vel, "ExtraBold")
    while f.getlength(text) + 36 > sirka * 0.98 and vel > 14:      # štítek se vejde do šířky okna
        vel -= 1
        f = pismo("Montserrat-wght.ttf", vel, "ExtraBold")
    tw = f.getlength(text)
    im = Image.new("RGBA", (int(tw + 36), int(f.size * 1.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, im.width - 1, im.height - 1), fill=KREM + (255,), outline=(200, 70, 80, 255), width=3)
    d.text((im.width / 2, im.height / 2), text, font=f, fill=(200, 70, 80), anchor="mm")
    return im.rotate(-7, expand=True, resample=Image.BICUBIC)


@lru_cache(maxsize=2)
def _popisek(cast1, cast2):
    f = pismo("Montserrat-wght.ttf", 40, "ExtraBold")
    w = int(f.getlength(cast1) + f.getlength(cast2)) + 56
    im, pad = karta(w, 66, (255, 255, 255, 250), 16, stin=70, pad=20)
    d = ImageDraw.Draw(im)
    d.text((pad + 28, pad + 33), cast1, font=f, fill=RUZOVA, anchor="lm")
    d.text((pad + 28 + f.getlength(cast1), pad + 33), cast2, font=f, fill=(25, 25, 25), anchor="lm")
    return im, pad


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, 0)
    w, h = spec["sirka"], spec["vyska_okna"]
    n = len(spec["videa"])
    rozestup = float(spec.get("rozestup", 0.18))
    sirka_vse = n * w + (n - 1) * MEZERA
    plat = Image.new("RGBA", (sirka_vse + 80, spec["vyska"] + 80), (0, 0, 0, 0))
    for i, (cesta, pocet) in enumerate(spec["_snimky"]):
        zac = i * rozestup
        if t < zac:
            continue
        snimek = snimek_videa(cesta, w, h, int((t - zac) * FPS) % max(pocet, 1), pocet)
        okno, pad = karta(w + 2 * RAM, h + 2 * RAM, (255, 255, 255, 255), 18, stin=90, pad=20)
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=13, fill=255)
        okno.paste(snimek, (pad + RAM, pad + RAM), m)
        if spec.get("cisla"):
            d = ImageDraw.Draw(okno)
            d.rounded_rectangle((pad + 14, pad + 14, pad + 54, pad + 50), radius=9, fill=SVESTKOVA + (230,))
            d.text((pad + 34, pad + 32), str(i + 1), font=pismo("Montserrat-wght.ttf", 24, "Bold"), fill=KREM, anchor="mm")
        if spec.get("stitek"):
            st = _stitek(spec["stitek"], w)
            okno.alpha_composite(st, (max(0, (okno.width - st.width) // 2), int(pad + h * 0.62)))
        p = pruzne((t - zac) / NASKOK_S)
        if p < 0.999:
            ow, oh = max(1, int(okno.width * (0.6 + 0.4 * min(p, 1)))), max(1, int(okno.height * (0.6 + 0.4 * min(p, 1))))
            mal = nasob_alfu(okno.resize((ow, oh)), min(1.0, (t - zac) / 0.15))
            plat.alpha_composite(mal, (40 + i * (w + MEZERA) - pad + (okno.width - ow) // 2, 40 - pad + (okno.height - oh) // 2 + 20))
        else:
            plat.alpha_composite(okno, (40 + i * (w + MEZERA) - pad, 40 - pad + 20))
    if spec.get("popisek"):
        c1, c2 = (list(spec["popisek"]) + [""])[:2]
        pop, pad = _popisek(c1, c2)
        a = min(1.0, max(0.0, (t - n * rozestup) / 0.25))
        if a > 0:
            plat.alpha_composite(nasob_alfu(pop, a), ((plat.width - pop.width) // 2, 40 + 20 + h + 2 * RAM + 14 - pad))
    return nasob_alfu(plat, odchod), (spec["x"] - 40, spec["y"] - 40)
