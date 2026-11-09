"""Storyboard reelu jako okno, které se pomalu posouvá: záznam po záznamu (čas, délka, typ záběru, věta, efekty).

Zadání Marcely 3. 11. 2026 („ukaž za mnou, jak storyboard vypadá, ten konkrétní můj“). Obsah se skládá ze
skutečného plánu reelu (věty a efekty z časové osy), kreslí ho studio. Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "storyboard", "od": 46.9, "do": 57.7, "y": 240, "vyska": 780,
   "hlavicka": "claude · storyboard", "vpravo": "v2 · 25 záběrů", "rychlost": 38,
   "zaznamy": [{"cas": "0:00,0–0:02,7", "delka": "2,7 s", "typ": "Mluvící záběr",
               "citat": "Nesestříhala jsem z tohohle videa ani sekundu.",
               "body": ["Úvod: karty slov na švestkové ploše"], "radky": [["ZVÝRAZNIT", "SEKUNDU"]]}, ...]}
  rychlost  posun obsahu v px za sekundu (výchozí 38)
"""
from functools import lru_cache

from PIL import Image, ImageDraw

from ..titulky import HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import KREM, RUZOVA, SVESTKOVA, karta, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W = 960
POZADI = (52, 36, 45)
RADEK = (66, 47, 58)
ZLATA = (226, 196, 128)


def pripravit(spec, styl, kontext):
    spec["x"], spec["y"] = (SIRKA - W) // 2, int(spec.get("y") or HORNI_OKRAJ + 20)
    spec["sirka"], spec["vyska"] = W, int(spec.get("vyska", 780))


def stav(spec, t):
    return stav_obecny(spec, t, None)


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + 120)     # do kontroly jen hlavička


def _zalom(text, f, sirka):
    radky, r = [], ""
    for s in text.split():
        zkus = (r + " " + s).strip()
        if f.getlength(zkus) > sirka and r:
            radky.append(r)
            r = s
        else:
            r = zkus
    return radky + ([r] if r else [])


@lru_cache(maxsize=2)
def _obsah(zaznamy_klic):
    """Celý dlouhý obsah (všechny záznamy pod sebou) jako jeden obrázek široký W - 80."""
    sir = W - 80
    fm = pismo("CourierPrime-Bold.ttf", 26)
    fc = pismo("InstrumentSerif-Italic.ttf", 46)
    fb = pismo("Montserrat-wght.ttf", 30, "Medium")
    fk = pismo("CourierPrime-Bold.ttf", 24)
    kusy = []
    for i, (cas, delka, typ, citat, body, radky) in enumerate(zaznamy_klic, 1):
        vys = 70 + 56 * len(_zalom("„%s“" % citat, fc, sir - 40)) + 54 * sum(len(_zalom(b, fb, sir - 90)) for b in body) + 58 * len(radky) + 50
        im = Image.new("RGBA", (sir, vys), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, sir - 1, vys - 16), radius=14, fill=RADEK + (255,))
        d.text((24, 26), "%02d" % i, font=fm, fill=KREM)
        d.text((90, 26), cas, font=fm, fill=(190, 175, 182))
        d.text((90 + fm.getlength(cas) + 30, 26), delka, font=fm, fill=(190, 175, 182))
        x = 90 + fm.getlength(cas + delka) + 70
        d.rectangle((x, 32, x + 20, 52), fill=(150, 130, 140))
        d.text((x + 34, 24), typ, font=pismo("Montserrat-wght.ttf", 28, "SemiBold"), fill=KREM)
        y = 82
        for r in _zalom("„%s“" % citat, fc, sir - 40):
            d.text((24, y), r, font=fc, fill=KREM)
            y += 56
        y += 8
        for b in body:
            for j, r in enumerate(_zalom(b, fb, sir - 90)):
                if j == 0:
                    d.ellipse((30, y + 14, 42, y + 26), fill=KREM)
                d.text((60, y), r, font=fb, fill=(240, 232, 236))
                y += 54
        y += 4
        for k, v in radky:
            d.rectangle((14, y - 4, sir - 14, y + 48), fill=(78, 57, 69))
            d.text((28, y + 8), k, font=fk, fill=(170, 150, 160))
            d.text((250, y + 4), v, font=pismo("Montserrat-wght.ttf", 30, "SemiBold"), fill=ZLATA if k in ("ZVÝRAZNIT", "ZLATĚ") else KREM)
            y += 58
        kusy.append(im)
    celkem = sum(k.height for k in kusy) + 20 * len(kusy)
    out = Image.new("RGBA", (sir, celkem + 400), (0, 0, 0, 0))
    y = 0
    for k in kusy:
        out.alpha_composite(k, (0, y))
        y += k.height + 20
    return out


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, 0)
    vys = spec["vyska"]
    im, pad = karta(W, vys, POZADI + (247,), 22, stin=120)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + W, pad + 64), radius=22, fill=KREM + (255,))
    d.rectangle((pad, pad + 40, pad + W, pad + 64), fill=KREM + (255,))
    d.text((pad + 26, pad + 32), spec.get("hlavicka", "claude · storyboard"), font=pismo("CourierPrime-Bold.ttf", 26), fill=SVESTKOVA, anchor="lm")
    d.text((pad + W - 26, pad + 32), spec.get("vpravo", ""), font=pismo("CourierPrime-Regular.ttf", 24), fill=(120, 100, 110), anchor="rm")
    klic_z = tuple((z["cas"], z["delka"], z["typ"], z["citat"], tuple(z.get("body", [])), tuple(tuple(r) for r in z.get("radky", [])))
                   for z in spec["zaznamy"])
    obsah = _obsah(klic_z)
    okno_v = vys - 64 - 40
    posun = int(max(0.0, t - 0.6) * float(spec.get("rychlost", 38)))
    posun = min(posun, max(0, obsah.height - 400 - okno_v + 200))
    vyrez = obsah.crop((0, posun, obsah.width, posun + okno_v))
    m = Image.new("L", vyrez.size, 255)
    md = ImageDraw.Draw(m)
    for j in range(40):                       # jemné zmizení dole
        md.line((0, okno_v - 1 - j, vyrez.width, okno_v - 1 - j), fill=int(255 * j / 40))
    vyrez.putalpha(Image.composite(vyrez.getchannel("A"), Image.new("L", vyrez.size, 0), m))
    im.alpha_composite(vyrez, (pad + 40, pad + 64 + 24))
    p = pruzne(t / 0.35)
    if p < 0.999:
        w2, h2 = max(1, int(im.width * (0.88 + 0.12 * p))), max(1, int(im.height * (0.88 + 0.12 * p)))
        mal = nasob_alfu(im.resize((w2, h2)), min(1.0, t / 0.2))
        im = Image.new("RGBA", im.size, (0, 0, 0, 0))
        im.alpha_composite(mal, ((im.width - w2) // 2, (im.height - h2) // 2))
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
