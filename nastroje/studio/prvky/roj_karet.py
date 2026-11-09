"""Roj karet: náhledy záběrů (fotky nebo videa) vyletí od osoby do všech stran, chvíli se vznášejí a pak spadnou dolů.

Zadání Marcely 3. 11. 2026.
Vzhled: při větě o spoustě natočených klipů vyletí asi 16 malých náhledů
s bílým rámečkem kolem osoby a po vteřině se sesypou dolů. Pravidlo Marcely 3. 11.: všechny karty jdou za osobu.

Spec v osa["prvky"]:
  {"typ": "roj_karet", "od": 12.3, "do": 13.6, "soubory": ["klip-1.mov", "fotka.jpg", ...], "karet": 16,
   "stred": [540, 760], "pad": 13.0}
  soubory  1 až 16 souborů (obrázky nebo videa; z videa se vezme snímek v 1. sekundě); méně souborů se opakuje
  karet    kolik karet vyletí (výchozí 16, nejvíc 24)
  stred    odkud karty vyletí (výchozí střed obrazu ve výšce hrudi)
  pad      čas reelu, kdy karty začnou padat (výchozí 0,5 s před koncem)
  polomer  [od, do] jak daleko od středu karty doletí (výchozí 220 až 430 px; u záběru zblízka víc, ať nejsou za hlavou)
"""
import math
import random

from PIL import Image

from ..titulky import SIRKA, VYSKA
from ._spolecne import karta_s_nahledem, najdi_soubor, nasob_alfu, stav_obecny

KARTA_W, KARTA_H = 118, 158
VYLET_S = 0.4
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def pripravit(spec, styl, kontext):
    spec["cesty"] = [najdi_soubor(s, kontext) for s in spec["soubory"]]
    n = max(1, min(24, int(spec.get("karet", 16))))
    sx, sy = spec.get("stred") or (SIRKA // 2, int(VYSKA * 0.42))
    rnd = random.Random(len(spec["cesty"]) * 31 + n)
    cile = []
    for i in range(n):
        uhel = 2 * math.pi * i / n + rnd.uniform(-0.25, 0.25)
        r = rnd.uniform(*spec.get("polomer", (220, 430)))
        x = min(SIRKA - 90, max(90, sx + math.cos(uhel) * r * 1.05))
        y = min(VYSKA - 520, max(kontext["horni"] + 60, sy + math.sin(uhel) * r * 1.25))
        cile.append([x, y, rnd.uniform(-12, 12), rnd.uniform(0, 0.12), rnd.uniform(-90, 90)])
    spec["cile"], spec["start"] = cile, [sx, sy]
    spec["x"], spec["y"] = 60, kontext["horni"]
    spec["sirka"], spec["vyska"] = SIRKA - 120, VYSKA - kontext["horni"] - 450


def _pad(spec):
    return float(spec.get("pad", float(spec["do"]) - 0.5)) - float(spec["od"])


def stav(spec, t):
    # karty se pohybují celou dobu (vznášení a pád): každý snímek je jiný
    k = stav_obecny(spec, t, None)
    return None if k is None else ("a", int((t - float(spec["od"])) * 30))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])


def vykresli(spec, styl, klic):
    t = klic[1] / 30.0
    plat = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
    sx, sy = spec["start"]
    pad = _pad(spec)
    for i, (cx, cy, rot, zpozdeni, rot_pad) in enumerate(spec["cile"]):
        p = max(0.0, min(1.0, (t - zpozdeni) / VYLET_S))
        if p <= 0:
            continue
        e = 1 - (1 - p) ** 3
        x, y = sx + (cx - sx) * e, sy + (cy - sy) * e
        y += math.sin(t * 2.2 + i) * 6 * e                 # lehké vznášení
        r = rot * e
        meritko = 0.3 + 0.7 * e
        alfa = min(1.0, p * 3)
        if t > pad:
            tp = t - pad - (i % 5) * 0.03
            if tp > 0:
                y += 2600 * tp * tp                         # pád s gravitací
                r += rot_pad * tp * 2
                alfa *= max(0.0, 1 - tp / 0.55)
        if alfa <= 0.01:
            continue
        k = karta_s_nahledem(spec["cesty"][i % len(spec["cesty"])], KARTA_W, KARTA_H, okraj=5, radius=6)
        k = k.resize((max(1, int(k.width * meritko)), max(1, int(k.height * meritko))), Image.BILINEAR)
        k = k.rotate(r, resample=Image.BICUBIC, expand=True)
        _poloz(plat, nasob_alfu(k, alfa), x, y)
    return plat, (0, 0)


def _poloz(plat, k, x, y):
    x0, y0 = int(x - k.width / 2), int(y - k.height / 2)
    if x0 >= SIRKA or y0 >= VYSKA or x0 + k.width <= 0 or y0 + k.height <= 0:
        return
    plat.alpha_composite(k, (max(0, x0), max(0, y0)), (max(0, -x0), max(0, -y0)))
