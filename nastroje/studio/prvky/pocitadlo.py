"""Překlápěcí počítadlo nad hlavou (jako hodiny s listy): popisek nahoře a čas v dlaždicích, které se překlopí.

Zadání Marcely 3. 11. 2026 („za pár minut mám přesně to, na co se díváš“ – časovač jako ve vzhledu, nad hlavou,
ať tam není díra bez efektu). Průběh: čas rychle naběhne od 0:00 na první hodnotu, při dalším kroku se změněné
číslice překlopí. Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "pocitadlo", "od": 29.0, "do": 31.6, "y": 250, "nabeh": 0.9,
   "kroky": [{"cas": 29.0, "popisek": "SUROVÝ ZÁZNAM", "hodnota": "3:52"},
             {"cas": 30.6, "popisek": "HOTOVÝ REEL", "hodnota": "1:15"}]}
  cas    čas reelu, kdy krok začne; hodnota ve tvaru m:ss
  nabeh  jak dlouho první hodnota naskakuje od 0:00 (s)
"""
from PIL import Image, ImageDraw

from ..titulky import HORNI_OKRAJ, SIRKA, pismo
from ._spolecne import KREM, SVESTKOVA, karta, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W, H = 620, 300
DLAZDICE = (58, 39, 50)
PREKLOP_S = 0.22


def _sekundy(h):
    m, s = h.split(":")
    return int(m) * 60 + int(s)


def _text(sek):
    return "%d:%02d" % (sek // 60, sek % 60)


def pripravit(spec, styl, kontext):
    spec["x"], spec["y"] = (SIRKA - W) // 2, int(spec.get("y") or HORNI_OKRAJ + 30)
    spec["sirka"], spec["vyska"] = W, H


def _konec_animace(spec):
    return float(spec["kroky"][-1]["cas"]) - float(spec["od"]) + PREKLOP_S + 0.05


def stav(spec, t):
    return stav_obecny(spec, t, _konec_animace(spec))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + W, spec["y"] + H)


def _stav_casu(spec, t_reel):
    """(popisek, text času, předchozí text, postup překlopení 0..1)."""
    kroky = spec["kroky"]
    i = max([j for j, k in enumerate(kroky) if float(k["cas"]) <= t_reel] or [0])
    k = kroky[i]
    od_kroku = t_reel - float(k["cas"])
    if i == 0:
        nabeh = float(spec.get("nabeh", 0.9))
        p = min(1.0, max(0.0, od_kroku / nabeh))
        return k["popisek"], _text(int(round(_sekundy(k["hodnota"]) * (1 - (1 - p) ** 2)))), None, 1.0
    return k["popisek"], k["hodnota"], kroky[i - 1]["hodnota"], min(1.0, max(0.0, od_kroku / PREKLOP_S))


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, _konec_animace(spec))
    popisek, hodnota, predchozi, p = _stav_casu(spec, float(spec["od"]) + t)
    im, pad = karta(W, H, SVESTKOVA + (250,), 26, stin=110)
    d = ImageDraw.Draw(im)
    f_pop = pismo("CourierPrime-Bold.ttf", 30)
    sirka_pop = sum(f_pop.getlength(z) + 8 for z in popisek)
    x = pad + (W - sirka_pop) / 2
    for z in popisek:
        d.text((x, pad + 30), z, font=f_pop, fill=(226, 200, 140))
        x += f_pop.getlength(z) + 8
    f = pismo("BodoniModa-wght.ttf", 170, "Medium")
    znaky = list(hodnota)
    stare = list(predchozi) if predchozi and len(predchozi) == len(hodnota) else None
    sirky = [64 if z == ":" else 150 for z in znaky]
    x = pad + (W - sum(sirky) - 14 * (len(znaky) - 1)) / 2
    y0, y1 = pad + 84, pad + H - 26
    for j, (z, sw) in enumerate(zip(znaky, sirky)):
        if z == ":":
            d.text((x + sw / 2, (y0 + y1) / 2 - 8), ":", font=f, fill=KREM, anchor="mm")
            x += sw + 14
            continue
        d.rounded_rectangle((x, y0, x + sw, y1), radius=14, fill=DLAZDICE)
        dl = Image.new("RGBA", (int(sw), int(y1 - y0)), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dl)
        menit = stare is not None and stare[j] != z and p < 1.0
        if menit:
            # list se překlápí: horní polovina staré číslice se smršťuje, pak naskočí nová
            if p < 0.5:
                dd.text((sw / 2, dl.height / 2), stare[j], font=f, fill=KREM, anchor="mm")
                vys = max(1, int(dl.height * (1 - 2 * p)))
                dl = dl.resize((dl.width, vys))
                im.alpha_composite(dl, (int(x), int(y0 + ((y1 - y0) - vys) / 2)))
            else:
                dd.text((sw / 2, dl.height / 2), z, font=f, fill=KREM, anchor="mm")
                vys = max(1, int(dl.height * (2 * p - 1)))
                dl = dl.resize((dl.width, vys))
                im.alpha_composite(dl, (int(x), int(y0 + ((y1 - y0) - vys) / 2)))
        else:
            dd.text((sw / 2, dl.height / 2), z, font=f, fill=KREM, anchor="mm")
            im.alpha_composite(dl, (int(x), int(y0)))
        d.line((x + 4, (y0 + y1) / 2, x + sw - 4, (y0 + y1) / 2), fill=SVESTKOVA + (255,), width=3)
        x += sw + 14
    q = pruzne(t / 0.3)
    if q < 0.999:
        w2, h2 = max(1, int(im.width * (0.75 + 0.25 * q))), max(1, int(im.height * (0.75 + 0.25 * q)))
        mal = nasob_alfu(im.resize((w2, h2)), min(1.0, t / 0.15))
        im = Image.new("RGBA", im.size, (0, 0, 0, 0))
        im.alpha_composite(mal, ((im.width - w2) // 2, (im.height - h2) // 2))
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
