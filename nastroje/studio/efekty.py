"""Animované textové bloky: nadpis na začátku a krátké nadpisy v průběhu videa (mini nadpisy).

Blok je text na podkladu (zaoblený obdélník) s volitelným emoji na konci a se zvýrazněním slov (pruh, který
se rozjede pod slovem). Vstup se animuje (vyskočení, nebo vjezd zleva), řádky mohou naskakovat se zpožděním,
na konci blok zmizí. Kreslí se v Pillow po snímcích, emoji je obrázek (balicek/pisma/emoji, licence Apache 2.0).
Stejný vzhled musí jít zapsat do CapCutu, animace tam jsou ale NEOVĚŘENO.
"""
from pathlib import Path

from PIL import ImageFilter, Image, ImageChops, ImageDraw

from .titulky import FPS, PISMA, SIRKA, VYSKA, barva_stinu, pismo

VSTUP_S = 0.40       # délka vstupní animace celého bloku
VYSTUP_S = 0.25      # délka mizení
RADEK_S = 0.30       # za jak dlouho naskočí jeden řádek
PISMENO_S = 0.045    # psaní po písmenech (řádek s radky_styl[i]["psani"]), jako na klávesnici


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _ease_out_back(p):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _clamp(x):
    return max(0.0, min(1.0, x))


def radky(spec):
    return [r.strip() for r in spec["text"].split("\n") if r.strip()]


def _emoji_obrazek(znak, vyska):
    kod = "emoji_u%x.png" % ord(znak[0])
    soubor = Path(PISMA) / "emoji" / kod
    if not soubor.exists():
        return None
    im = Image.open(soubor).convert("RGBA")
    return im.resize((int(vyska), int(vyska)), Image.LANCZOS)


def _fonty_radku(spec, styl, velikost):
    """Písmo každého řádku. spec["radky_styl"] (volitelné) dává řádku vlastní poměr velikosti, písmo a řez:
    [{"pomer": 0.5, "pismo": "Montserrat-wght.ttf", "varianta": "Medium"}, {"pomer": 1.0}, ...]
    (Marcela 20. 10.: nadpis „malé / VELKÉ / malé“). Bez toho mají všechny řádky písmo bloku."""
    rr = radky(spec)
    rs = spec.get("radky_styl") or []
    fonty = []
    for i in range(len(rr)):
        s = rs[i] if i < len(rs) else {}
        v = max(12, int(round(velikost * float(s.get("pomer", 1.0)))))
        fonty.append(pismo(s.get("pismo", styl["pismo"]), v, s.get("varianta", styl["varianta"])))
    return rr, fonty


def geometrie(spec, styl, velikost=None):
    """Rozměry bloku bez animace: (šířka, výška, font, šířky řádků, výšky řádků, šířka emoji, fonty řádků)."""
    velikost = velikost or spec["velikost"]
    rr, fonty = _fonty_radku(spec, styl, velikost)
    font = fonty[0] if fonty else pismo(styl["pismo"], velikost, styl["varianta"])
    sirky = [f.getlength(r) for f, r in zip(fonty, rr)]
    vrs = []
    for f in fonty:
        asc, desc = f.getmetrics()
        vrs.append(int((asc + desc) * styl.get("radek", 1.15)))
    ew = int(velikost * 1.15) if spec.get("emoji") else 0
    if ew and sirky:
        sirky[-1] += ew + int(velikost * 0.2)
    px, py = styl.get("podklad_pad", (30, 20))
    return int(max(sirky or [0]) + 2 * px), int(sum(vrs) + 2 * py), font, sirky, vrs, ew, fonty


def velikost_bloku(spec, styl, velikost=None):
    w, h, *_ = geometrie(spec, styl, velikost)
    return w, h


def obdelnik(spec, styl):
    """Obdélník bloku ve videu po dokončení animace: (x0, y0, x1, y1)."""
    w, h = velikost_bloku(spec, styl)
    x0 = int((SIRKA - w) / 2)
    if spec.get("x") is not None:
        # střed bloku zadaný v plánu (STUDIO nad prstem, 2. 11.), nikdy přes boční okraj 70 px
        x0 = int(min(max(spec["x"] - w / 2, 70), SIRKA - 70 - w))
    return x0, int(spec["y"]), x0 + w, int(spec["y"]) + h


def casy_psani(spec):
    """Řádky psané po písmenech: [(index řádku, začátek psaní od začátku bloku, počet znaků)]."""
    rs = spec.get("radky_styl") or []
    zp = spec.get("zpozdeni_radku") or []
    out = []
    for i, r in enumerate(radky(spec)):
        if i < len(rs) and rs[i].get("psani"):
            out.append((i, zp[i] if i < len(zp) else 0.0, len(r)))
    return out


def delka_vstupu(spec):
    zp = spec.get("zpozdeni_radku") or [0.0]
    konec = max(VSTUP_S, max(zp) + RADEK_S)
    for _, od, n in casy_psani(spec):
        konec = max(konec, od + n * PISMENO_S)
    if spec.get("zvyraznit"):
        konec = max(konec, spec.get("marker_od", 0.0) + spec.get("marker_delka", 0.45))
    return konec


def krok(spec, t_rel, t_do_konce):
    """Klíč stavu animace v daném okamžiku: stejný klíč = stejný snímek."""
    vstup = delka_vstupu(spec)
    if t_do_konce < VYSTUP_S:
        return -(int(t_do_konce * FPS) + 1)
    if t_rel < vstup:
        return int(t_rel * FPS)
    return "s"


def _kresli_blok(spec, styl, t_rel, velikost=None):
    """Blok v čase t_rel od začátku (bez vstupní a výstupní transformace celého bloku)."""
    w, h, font, sirky, vrs, ew, fonty = geometrie(spec, styl, velikost)
    if spec.get("staticky"):
        t_rel = 99.0                     # bez nástupu řádků a bez animace zvýraznění (b-roll, Marcela 22. 10.)
    rozmaz = int(styl.get("podklad_rozmaz") or 0)
    pad = 24 + 2 * rozmaz
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px, py = styl.get("podklad_pad", (30, 20))
    if styl.get("podklad") and rozmaz:
        # měkce ztmavené místo jen za nadpisem (okraje rozplynuté), ne tvrdý obdélník
        vrstva = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(vrstva).rounded_rectangle((pad, pad, pad + w, pad + h), radius=styl.get("podklad_radius", 28), fill=tuple(styl["podklad"]))
        img.alpha_composite(vrstva.filter(ImageFilter.GaussianBlur(rozmaz)))
    elif styl.get("podklad"):
        d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=styl.get("podklad_radius", 28), fill=styl["podklad"])
    rr = radky(spec)
    zp = spec.get("zpozdeni_radku") or [0.0] * len(rr)
    rs_bloku = spec.get("radky_styl") or []
    zvr = spec.get("zvyraznit") or []
    prog = _clamp((t_rel - spec.get("marker_od", 0.0)) / spec.get("marker_delka", 0.45)) if zvr else 0.0
    prog = _ease_out_cubic(prog)
    text_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(text_img)
    y_radku = pad + py
    for i, r in enumerate(rr):
        font = fonty[i]
        vr = vrs[i]
        mezera_sirka = font.getlength(" ")
        f = _clamp((t_rel - (zp[i] if i < len(zp) else 0.0)) / RADEK_S)
        sirka_r = sirky[i] if i < len(sirky) else font.getlength(r)
        psani = i < len(rs_bloku) and rs_bloku[i].get("psani")
        if psani:
            # po písmenech: řádek stojí na svém místě (zarovnaný podle celé délky), přibývají znaky, bez prolnutí
            n_vid = int(max(0.0, t_rel - (zp[i] if i < len(zp) else 0.0)) / PISMENO_S) + 1
            if t_rel < (zp[i] if i < len(zp) else 0.0):
                y_radku += vr
                continue
            r = r[:n_vid]
            f = 1.0
        if f <= 0:
            y_radku += vr
            continue
        a = int(255 * _ease_out_cubic(f))
        dy = int(16 * (1 - _ease_out_cubic(f)))
        x = pad + px + (w - 2 * px - sirka_r) / 2
        y = y_radku + dy
        y_radku += vr
        # slovo po slovu kvůli zvýraznění
        casti = r.split(" ")
        cx = x
        for c in casti:
            cw = font.getlength(c)
            jeZv = any(z.lower().strip(".,!?") in c.lower().strip(".,!?") for z in zvr) if zvr else False
            if jeZv:
                sirka_pruhu = (cw + 20) * prog
                if sirka_pruhu > 1:
                    pruh = Image.new("RGBA", img.size, (0, 0, 0, 0))
                    ImageDraw.Draw(pruh).rounded_rectangle(
                        (cx - 10, y + vr * 0.12, cx - 10 + sirka_pruhu, y + vr * 0.92), radius=14, fill=styl["marker"])
                    img.alpha_composite(pruh)
                barva = styl["barva_zvyrazneni"] if prog > 0.35 else styl["barva"]
            else:
                # řádek může mít vlastní barvu (radky_styl[i]["barva"], kurzíva žlutě ve vzhledu jedno_slovo)
                barva = (rs_bloku[i].get("barva") if i < len(rs_bloku) else None) or styl["barva"]
            td.text((cx, y), c, font=font, fill=tuple(barva) + (a,))
            cx += cw + mezera_sirka
        if spec.get("emoji") and i == len(rr) - 1:
            e = _emoji_obrazek(spec["emoji"], velikost * 1.15 if velikost else spec["velikost"] * 1.15)
            if e is not None:
                ea = e.getchannel("A").point(lambda v, a=a: int(v * a / 255))
                e.putalpha(ea)
                text_img.alpha_composite(e, (int(cx - mezera_sirka + spec["velikost"] * 0.2 + 2), int(y + vr * 0.06)))
    if styl.get("stin"):
        # měkký stín pod textem (bez podkladu), ať je bílé písmo čitelné na světlé stěně
        stin = Image.new("RGBA", img.size, barva_stinu(styl.get("barva"), styl) + (0,))
        stin.putalpha(text_img.getchannel("A").point(lambda v: int(v * styl.get("stin_sila", 0.55))))
        stin = stin.filter(ImageFilter.GaussianBlur(styl.get("stin", 8)))
        img.alpha_composite(stin, (0, int(styl.get("stin_posun", 6))))
    img.alpha_composite(text_img)
    return img, pad


def vykresli(spec, styl, k):
    """Snímek bloku pro klíč k (z krok()). Vrátí (obrázek, (x, y), obdélník po animaci)."""
    vstup = delka_vstupu(spec)
    if k == "s":
        t_rel, t_konec = vstup, 99.0
    elif k >= 0:
        t_rel, t_konec = k / FPS, 99.0
    else:
        t_rel, t_konec = vstup, (-k - 1) / FPS
    img, pad = _kresli_blok(spec, styl, t_rel)
    ob = obdelnik(spec, styl)
    sx, sy = ob[0] - pad, ob[1] - pad
    p = _clamp(t_rel / VSTUP_S)
    efekt = spec.get("efekt", "pop")
    alfa = 1.0 if (spec.get("staticky") or efekt == "zadny") else _clamp(t_rel / 0.18)
    mierka, dx = 1.0, 0
    if efekt == "zadny":
        pass
    elif efekt == "pop":
        mierka = 0.80 + 0.20 * _ease_out_back(p)
    elif efekt == "zleva":
        dx = int(-110 * (1 - _ease_out_cubic(p)))
    if t_konec < VYSTUP_S:
        alfa = min(alfa, _clamp(t_konec / VYSTUP_S))
        mierka *= 0.97 + 0.03 * _clamp(t_konec / VYSTUP_S)
    if alfa < 1.0:
        a = ImageChops.multiply(img.getchannel("A"), Image.new("L", img.size, int(255 * alfa)))
        img.putalpha(a)
    if abs(mierka - 1.0) > 0.004:
        nw, nh = max(1, int(img.width * mierka)), max(1, int(img.height * mierka))
        cx, cy = sx + img.width / 2, sy + img.height / 2
        img = img.resize((nw, nh), Image.LANCZOS)
        sx, sy = int(cx - nw / 2), int(cy - nh / 2)
    return img, (int(sx + dx), int(sy)), ob
