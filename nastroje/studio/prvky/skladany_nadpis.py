"""Skládaný nadpis: hook nad hlavou, který přibývá po řádcích, jak osoba mluví (řádky zůstávají, dokud prvek běží).

Zadání Marcely 3. 11. 2026. Nadpis se skládá
po frázích: bílé bezpatkové řádky a mezi nimi žlutá patková kurzíva, větší. Hlava zakrývá spodek písmen
(za osobou, maska). Nový řádek naskočí krátkým pružným zvětšením.

Spec v osa["prvky"]:
  {"typ": "skladany_nadpis", "od": 2.6, "do": 6.4, "y": 260,
   "radky": [{"text": "naučíme se,", "cas": 2.6},
             {"text": "jak nechat Clauda", "cas": 3.6, "kurziva": true},
             {"text": "stříhat reely", "cas": 4.4}]}
  cas      čas reelu, kdy řádek naskočí (výchozí rovnoměrně od začátku prvku)
  kurziva  řádek patkovou kurzívou ve zvýrazňující barvě (výchozí: každý druhý řádek)
  y        horní okraj nadpisu (výchozí 260 px, za hlavou)
Styl vzhledu (styl["skladany_nadpis"]): pismo, varianta, velikost, barva, pismo_kurziva, barva_kurziva, pomer_kurziva.
"""
from PIL import Image, ImageDraw, ImageFilter

from ..titulky import SIRKA, pismo
from ._spolecne import nasob_alfu, pruzne, rozloz_klic, stav_obecny

VYCHOZI_STYL = {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 92, "barva": (255, 255, 255),
                "pismo_kurziva": "InstrumentSerif-Italic.ttf", "barva_kurziva": (247, 210, 84), "pomer_kurziva": 1.22,
                "radek": 1.02, "max_sirka": 960, "stin": 170}
NASTUP_S = 0.22
ZA_HLAVOU = True          # pravidlo Marcely 3. 11. 2026: efekty vždy za osobou (maska)


def _s(styl):
    return dict(VYCHOZI_STYL, **(styl or {}))


def _radky(spec):
    radky = spec["radky"]
    od, do = float(spec["od"]), float(spec["do"])
    krok = (do - od - 0.6) / max(1, len(radky))
    out = []
    for i, r in enumerate(radky):
        r = {"text": r} if isinstance(r, str) else dict(r)
        r.setdefault("cas", od + i * krok)
        r.setdefault("kurziva", i % 2 == 1)
        out.append(r)
    return out


def _font(r, s, velikost=None):
    v = velikost or s["velikost"]
    if r["kurziva"]:
        return pismo(s["pismo_kurziva"], int(v * s["pomer_kurziva"]), None)
    return pismo(s["pismo"], v, s["varianta"])


def _velikost(spec, s):
    """Písmo se zmenší, když se nejdelší řádek nevejde do max_sirka."""
    v = s["velikost"]
    while v > 48 and any(_font(r, s, v).getlength(r["text"]) > s["max_sirka"] for r in _radky(spec)):
        v -= 4
    return v


def pripravit(spec, styl, kontext):
    s = _s(styl)
    spec["velikost"] = _velikost(spec, s)
    spec["x"], spec["sirka"] = (SIRKA - s["max_sirka"]) // 2, s["max_sirka"]
    spec["y"] = int(spec.get("y") or kontext["horni"] + 40)
    spec["vyska"] = int(sum(_vyska_radku(r, s, spec["velikost"]) for r in _radky(spec)))


def _vyska_radku(r, s, v):
    a, d = _font(r, s, v).getmetrics()
    return (a + d) * s["radek"]


def _konec(spec):
    return max(float(r["cas"]) for r in _radky(spec)) - float(spec["od"]) + NASTUP_S


def stav(spec, t):
    return stav_obecny(spec, t, _konec(spec))


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])


def vykresli(spec, styl, klic):
    s = _s(styl)
    t, odchod = rozloz_klic(klic, spec, _konec(spec))
    t_reel = float(spec["od"]) + t
    pad = 40
    w, h = spec["sirka"] + 2 * pad, spec["vyska"] + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = pad
    for r in _radky(spec):
        vr = _vyska_radku(r, s, spec["velikost"])
        p = (t_reel - float(r["cas"])) / NASTUP_S
        if p >= 0:
            f = _font(r, s, spec["velikost"])
            barva = s["barva_kurziva"] if r["kurziva"] else s["barva"]
            sirka = f.getlength(r["text"])
            vrs = Image.new("RGBA", (int(sirka) + 40, int(vr) + 40), (0, 0, 0, 0))
            st = Image.new("L", vrs.size, 0)
            ImageDraw.Draw(st).text((22, 25), r["text"], font=f, fill=s["stin"])
            stin = Image.new("RGBA", vrs.size, (0, 0, 0, 0))
            stin.putalpha(st.filter(ImageFilter.GaussianBlur(8)))
            vrs.alpha_composite(stin)
            ImageDraw.Draw(vrs).text((20, 20), r["text"], font=f, fill=tuple(barva) + (255,))
            m = pruzne(p) * 0.25 + 0.75 if p < 1 else 1.0
            if m < 0.999:
                vrs = nasob_alfu(vrs.resize((max(1, int(vrs.width * m)), max(1, int(vrs.height * m)))), min(1.0, p * 2))
            im.alpha_composite(vrs, (int((w - vrs.width) / 2), int(y + vr / 2 - vrs.height / 2)))
        y += vr
    return nasob_alfu(im, odchod), (spec["x"] - pad, spec["y"] - pad)
