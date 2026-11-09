"""Karta vzhledu: malá bílá karta „tvůj vzhled“ s ukázkou písma Aa, názvem písma a řadou barevných teček.
Barvy se v daných časech vymění (ukázka, že si studio vezme barvy a písmo značky zákaznice).

Zadání Marcely 3. 11. 2026.
Vzhled: u věty o vlastní značce visí vlevo nahoře karta „tvůj vzhled“
s písmem Aa a pěti barvami; v dalším záběru má jiné písmo a jiné barvy. Jde za osobu (maska).

Spec v osa["prvky"]:
  {"typ": "karta_vzhledu", "od": 28.6, "do": 31.0, "nadpis": "tvůj vzhled", "podpis": "na míru tobě",
   "varianty": [{"cas": 28.6, "pismo": "PlayfairDisplay-wght.ttf", "nazev": "Playfair Display",
                 "barvy": ["#4A3340", "#D48BA0", "#F5D6D9", "#CED4AC", "#FBF6EF"]},
                {"cas": 29.8, "pismo": "InstrumentSerif-Italic.ttf", "nazev": "Instrument Serif",
                 "barvy": ["#1F2A44", "#E9C46A", "#F4A261", "#2A9D8F", "#FFFFFF"]}],
   "x": 70, "y": 300, "meritko": 1.4}
  varianty  1 až 4 vzhledy, každý od svého času; tečky naskočí jedna po druhé
  meritko   velikost karty (výchozí 1,0 = 330 x 300 px)
"""
from PIL import Image, ImageDraw

from ..titulky import pismo
from ._spolecne import karta, nasob_alfu, pruzne, rozloz_klic, stav_obecny

W, H = 330, 300
SEDA = (120, 115, 112)
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def _rgb(h):
    if isinstance(h, (list, tuple)):
        return tuple(h[:3])
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def pripravit(spec, styl, kontext):
    spec["x"] = int(spec.get("x", 70))
    spec["y"] = int(spec.get("y", kontext["horni"] + 80))
    m = float(spec.get("meritko", 1.0))
    spec["sirka"], spec["vyska"] = int(W * m), int(H * m)


def _konec(spec):
    return float(spec["varianty"][-1].get("cas", spec["od"])) - float(spec["od"]) + 0.6


def stav(spec, t):
    return stav_obecny(spec, t, _konec(spec))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])


def vykresli(spec, styl, klic):
    t, odchod = rozloz_klic(klic, spec, _konec(spec))
    t_reel = float(spec["od"]) + t
    var = spec["varianty"]
    i = max([j for j, v in enumerate(var) if float(v.get("cas", spec["od"])) <= t_reel + 1e-6] or [0])
    v = var[i]
    od_var = t_reel - float(v.get("cas", spec["od"]))
    im, pad = karta(W, H, (255, 255, 255, 250), 22, stin=80)
    d = ImageDraw.Draw(im)
    d.text((pad + 24, pad + 18), spec.get("nadpis", "tvůj vzhled"), font=pismo("InstrumentSerif-Italic.ttf", 34), fill=(40, 36, 36))
    # rámeček s ukázkou písma
    d.rectangle((pad + 24, pad + 66, pad + 150, pad + 176), outline=(60, 56, 56), width=2)
    f = pismo(v.get("pismo", "PlayfairDisplay-wght.ttf"), 78, v.get("varianta"))
    d.text((pad + 87, pad + 121), "Aa", font=f, fill=(30, 28, 28), anchor="mm")
    d.text((pad + 166, pad + 80), v.get("nazev", ""), font=pismo("Inter-wght.ttf", 20, "SemiBold"), fill=(40, 36, 36))
    d.text((pad + 166, pad + 106), "písmo nadpisů", font=pismo("Inter-wght.ttf", 17, "Regular"), fill=SEDA)
    barvy = v.get("barvy", [])[:6]
    for j, b in enumerate(barvy):
        q = pruzne((od_var - j * 0.07) / 0.2) if i > 0 or t > 0.2 else pruzne((t - 0.2 - j * 0.07) / 0.2)
        if q <= 0:
            continue
        r = 19 * q
        cx, cy = pad + 44 + j * 50, pad + 214
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgb(b), outline=(215, 210, 205), width=1)
    d.text((pad + 24, pad + 252), spec.get("podpis", "na míru tobě"), font=pismo("InstrumentSerif-Italic.ttf", 24), fill=SEDA)
    q = pruzne(t / 0.3)
    if q < 0.999:
        w2, h2 = max(1, int(im.width * (0.7 + 0.3 * q))), max(1, int(im.height * (0.7 + 0.3 * q)))
        mal = nasob_alfu(im.resize((w2, h2)), min(1.0, t / 0.12))
        im = Image.new("RGBA", im.size, (0, 0, 0, 0))
        im.alpha_composite(mal, ((im.width - w2) // 2, (im.height - h2) // 2))
    m = float(spec.get("meritko", 1.0))
    if m != 1.0:
        im, pad = im.resize((int(im.width * m), int(im.height * m)), Image.LANCZOS), int(pad * m)
    return nasob_alfu(im.rotate(2, resample=Image.BICUBIC), odchod), (spec["x"] - pad, spec["y"] - pad)
