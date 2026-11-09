"""Prvek „ikony“: dvě až pět ikon aplikací (obrázky zákaznice) vedle sebe, s malým popiskem pod každou.

Zadání Marcely (22. 10. 2026, b-roll): „Claude a Notion tam dej malým písmem, ale dej tam ty obrázky co máš ve složce.“
Obrázek ikony bývá snímek z plochy telefonu (ikona se zaoblenými rohy na rozmazaném pozadí, pod ní název).
Prvek z něj vyřízne samotnou ikonu (plocha, která se liší od barvy okraje, v horních 80 % obrázku), dá jí
zaoblené rohy (22 % strany) a měkký stín. Ikony naskočí jedna po druhé jako štítky (pružné zvětšení 0,18 s,
rozestup 0,35 s), zůstanou do „do“ a na konci spolu zmizí.

Spec v osa["prvky"]:
  {"typ": "ikony", "od": 1.0, "do": 10.0, "soubory": ["ikona-claude.jpg", "ikona-notion.jpg"],
   "popisky": ["Claude", "Notion"],   # volitelně, jinak název souboru bez přípony
   "velikost": 150,                   # volitelně: strana ikony v px (výchozí 150)
   "y": 1330,                         # volitelně: střed bloku svisle (výchozí nad spodním pásmem)
   "casy": [1.0, 1.35],               # volitelně: čas naskočení každé ikony
   "cele_ikony": True,                # volitelně: obrázky jsou už samotné ikony (čtverec), nic se nevyřezává
   "skrtnout": True,                  # volitelně: červená čára přes každou ikonu (3. 11. 2026, „nepoužívám“)
   "skrtnout_casy": [5.2, 5.75]}      # volitelně: kdy se přeškrtne která ikona (časy reelu)
pripravit() doplní spec["cesty"], spec["x"], spec["y"] (levý horní roh), spec["sirka"], spec["vyska"],
spec["casy_naskoceni"]; zvuk nemíchá (hlavní program přidá „klik“). Klíče stav(): jako u štítků.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..titulky import DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo
from .stitky import NASKOK_S, ROZESTUP_S, VYSTUP_S, MERITKO_OD, _clamp, _meritko_naskoku, _poloz

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf",
    "varianta": "SemiBold",
    "velikost_popisku": 34,
    "barva_popisku": (255, 255, 255),
    "velikost": 150,                 # strana ikony
    "mezera": 70,                    # mezera mezi ikonami
    "mezera_popisku": 14,            # mezera mezi ikonou a popiskem
    "radius": 0.22,                  # zaoblení rohů jako podíl strany
    "stin": 110,                     # průhlednost stínu 0..255
    "stin_popisku": 0.7,
}
PAD_PLATNA = 40
MIN_IKON, MAX_IKON = 1, 5


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl.get("ikony", {}) if isinstance(styl, dict) else {})
    return s


def _najdi_soubor(nazev, kontext):
    p = Path(nazev).expanduser()
    if p.is_absolute() and p.exists():
        return p
    podklady = kontext.get("podklady")
    kandidati = [Path(podklady) / nazev] if podklady else []
    for k in kandidati:
        if k.exists():
            return k
    raise FileNotFoundError("Ikona „%s“ není ve složce podkladů%s." % (nazev, (" (%s)" % podklady) if podklady else ""))


@lru_cache(maxsize=32)
def _ikona(cesta, strana, radius_podil, stin_alfa, cela=False):
    """Vyříznutá ikona se zaoblenými rohy, škálovaná na stranu px, + stín. Vrátí RGBA obrázek s okrajem na stín.
    cela=True: obrázek už je samotná ikona (čtverec bez okolí), nic se nevyřezává."""
    im = Image.open(cesta).convert("RGB")
    a = np.asarray(im).astype(int)
    h, w = a.shape[:2]
    if cela:
        a = np.zeros((h, w, 3), int)
    # barva okraje = průměr pixelů v 4 px rámu; ikona = pixely, které se od ní liší, jen v horních 80 % (popisek pryč)
    ram = np.concatenate([a[:4].reshape(-1, 3), a[-4:].reshape(-1, 3), a[:, :4].reshape(-1, 3), a[:, -4:].reshape(-1, 3)])
    okraj = ram.mean(axis=0)
    rozdil = np.abs(a - okraj).sum(axis=2)
    maska = rozdil > 60
    maska[int(h * 0.8):] = False
    ys, xs = np.where(maska)
    if cela:
        box = (0, 0, w, h)
    elif len(xs) < 50:
        box = (0, 0, w, int(h * 0.8))
    else:
        # ořez na čtverec kolem jádra (10. a 90. percentil, ať neruší rozmazaný stín kolem ikony)
        x0, x1 = int(np.percentile(xs, 2)), int(np.percentile(xs, 98))
        y0, y1 = int(np.percentile(ys, 2)), int(np.percentile(ys, 98))
        s = max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        box = (max(0, cx - s // 2), max(0, cy - s // 2), min(w, cx + s // 2), min(h, cy + s // 2))
    ik = im.crop(box).resize((strana, strana), Image.LANCZOS).convert("RGBA")
    m = Image.new("L", (strana, strana), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, strana - 1, strana - 1), radius=int(strana * radius_podil), fill=255)
    ik.putalpha(m)
    pad = PAD_PLATNA
    out = Image.new("RGBA", (strana + 2 * pad, strana + 2 * pad), (0, 0, 0, 0))
    if stin_alfa:
        st = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(st).rounded_rectangle((pad, pad + 8, pad + strana, pad + strana + 8), radius=int(strana * radius_podil),
                                             fill=(0, 0, 0, int(stin_alfa)))
        out.alpha_composite(st.filter(ImageFilter.GaussianBlur(14)))
    out.alpha_composite(ik, (pad, pad))
    return out


@lru_cache(maxsize=32)
def _popisek(text, velikost, pismo_nazev, varianta, barva, stin_sila):
    font = pismo(pismo_nazev, int(velikost), varianta)
    w = int(font.getlength(text)) + 24
    h = int(velikost * 1.4) + 16
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if stin_sila:
        s = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(s).text((12, 6), text, font=font, fill=(0, 0, 0, int(255 * stin_sila)))
        img.alpha_composite(s.filter(ImageFilter.GaussianBlur(5)), (0, 3))
    ImageDraw.Draw(img).text((12, 6), text, font=font, fill=tuple(barva) + (255,))
    return img


def casy(spec):
    """Časy naskočení v sekundách od začátku prvku a konec poslední animace."""
    n = len(spec["cesty"])
    od = float(spec["od"])
    if spec.get("casy"):
        rel = [max(0.0, float(c) - od) for c in list(spec["casy"])[:n]]
        while len(rel) < n:
            rel.append((rel[-1] if rel else 0.0) + ROZESTUP_S)
    else:
        rel = [i * ROZESTUP_S for i in range(n)]
    return rel, (rel[-1] + NASKOK_S) if rel else 0.0


def pripravit(spec, styl, kontext):
    st = _styl(styl)
    soubory = list(spec.get("soubory") or [])[:MAX_IKON]
    if len(soubory) < MIN_IKON:
        raise ValueError("Ikony potřebují aspoň jeden obrázek.")
    spec["cesty"] = [str(_najdi_soubor(s, kontext)) for s in soubory]
    spec["popisky"] = list(spec.get("popisky") or [Path(s).stem.replace("ikona-", "").capitalize() for s in soubory])[:len(soubory)]
    strana = int(spec.get("velikost") or st["velikost"])
    spec["velikost"] = strana
    mezera = int(st["mezera"])
    if spec.get("sipka"):
        mezera = max(mezera, int(st.get("mezera_sipka", 170)))     # místo na šipku propojení
    n = len(soubory)
    font = pismo(st["pismo"], int(st["velikost_popisku"]), st["varianta"])
    sirky = [max(strana, int(font.getlength(p)) + 24) for p in spec["popisky"]]
    sirka = sum(sirky) + mezera * (n - 1)
    vyska = strana + int(st["mezera_popisku"]) + int(st["velikost_popisku"] * 1.4) + 16
    stred_y = int(spec["y"]) if spec.get("y") else int(VYSKA - DOLNI_OKRAJ - vyska / 2 - 40)
    if spec.get("y"):
        # zadaná poloha platí i ve spodním pásmu (Marcela 22. 10.: ikony níž na klávesnici), jen uvnitř obrazu
        y = max(HORNI_OKRAJ, min(VYSKA - vyska - 20, int(stred_y - vyska / 2)))
    else:
        y = max(HORNI_OKRAJ, min(VYSKA - DOLNI_OKRAJ - vyska, int(stred_y - vyska / 2)))
    x = int((SIRKA - sirka) / 2)
    spec["x"], spec["y_blok"], spec["sirka"], spec["vyska"] = x, y, sirka, vyska
    spec["stredy"] = []
    cx = x
    for sx in sirky:
        spec["stredy"].append(int(cx + sx / 2))
        cx += sx + mezera
    spec["y"] = y
    rel, _ = casy(spec)
    spec["casy_naskoceni"] = [round(float(spec["od"]) + r, 2) for r in rel]
    okno = kontext.get("okno")
    if okno and not (y + vyska < okno[1] or y > okno[3]):
        spec["varovani"] = "Ikony v čase %.1f s leží přes obličej, posuň je (y)." % float(spec["od"])
    return None


SKRT_S = 0.22          # přetažení červené čáry přes jednu ikonu
SKRT_CERVENA = (226, 62, 62)


def _skrt_casy(spec, starty):
    """Začátky čar přes ikony (s od začátku prvku): po naskočení poslední ikony, nebo spec["skrtnout_casy"] (časy reelu)."""
    if spec.get("skrtnout_casy"):
        return [float(c) - float(spec["od"]) for c in spec["skrtnout_casy"]]
    zac = starty[-1] + NASKOK_S + 0.15
    return [zac + i * (SKRT_S + 0.08) for i in range(len(starty))]


def _skrt(platno, spec, strana, x0, y0, starty, t_rel, mizeni):
    """Červená ručně tažená čára šikmo přes každou ikonu (Marcela 3. 11.: „červeně přeškrtni, že je nepoužívám“)."""
    vrstva = Image.new("RGBA", platno.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(vrstva)
    alfa = 255 if mizeni is None else int(255 * mizeni * mizeni)
    tl = max(10, strana // 11)
    cy = int(spec["y"]) + strana / 2 - y0
    for cx, zac in zip(spec["stredy"], _skrt_casy(spec, starty)):
        p = 1.0 if t_rel is None else _clamp((t_rel - zac) / SKRT_S)
        if p <= 0:
            continue
        p = 1 - (1 - p) ** 2
        ax, ay = cx - x0 - strana * 0.62, cy - strana * 0.30
        bx, by = cx - x0 + strana * 0.62, cy + strana * 0.22
        body = []
        for i in range(25):
            u = i / 24 * p
            body.append((ax + (bx - ax) * u, ay + (by - ay) * u + np.sin(u * np.pi) * strana * 0.10))
        d.line(body, fill=SKRT_CERVENA + (alfa,), width=tl, joint="curve")
        for bod in (body[0], body[-1]):
            d.ellipse((bod[0] - tl / 2, bod[1] - tl / 2, bod[0] + tl / 2, bod[1] + tl / 2), fill=SKRT_CERVENA + (alfa,))
    platno.alpha_composite(vrstva)


def stav(spec, t):
    t_rel, zbyva = t - float(spec["od"]), float(spec["do"]) - t
    if t_rel < 0 or zbyva <= 0:
        return None
    if zbyva < VYSTUP_S:
        return -(int(zbyva * FPS) + 1)
    starty, konec = casy(spec)
    if spec.get("skrtnout"):
        konec = max(konec, max(_skrt_casy(spec, starty)) + SKRT_S)
    if t_rel < konec:
        return int(t_rel * FPS)
    return "s"


def obdelnik(spec, styl):
    if "cesty" not in spec:
        pripravit(spec, styl, {"okno": None})
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


def vykresli(spec, styl, klic):
    st = _styl(styl)
    strana = int(spec["velikost"])
    starty, _ = casy(spec)
    x0, y0 = int(spec["x"]) - PAD_PLATNA, int(spec["y"]) - PAD_PLATNA
    platno = Image.new("RGBA", (int(spec["sirka"]) + 2 * PAD_PLATNA, int(spec["vyska"]) + 2 * PAD_PLATNA), (0, 0, 0, 0))
    if klic == "s":
        t_rel, mizeni = None, None
    elif klic >= 0:
        t_rel, mizeni = klic / FPS, None
    else:
        t_rel, mizeni = None, _clamp(((-klic - 1) / FPS) / VYSTUP_S)
    for cesta, popisek, cx, start in zip(spec["cesty"], spec["popisky"], spec["stredy"], starty):
        if t_rel is None:
            meritko, alfa = 1.0, 1.0
        else:
            if t_rel < start:
                continue
            postup = _clamp((t_rel - start) / NASKOK_S)
            meritko, alfa = _meritko_naskoku(postup), _clamp(postup / 0.3)
        if mizeni is not None:
            e = mizeni * mizeni
            meritko, alfa = MERITKO_OD + (1.0 - MERITKO_OD) * e, e
        ik = _ikona(cesta, strana, float(st["radius"]), int(st["stin"]), bool(spec.get("cele_ikony")))
        cy_ik = int(spec["y"]) + strana / 2
        _poloz(platno, ik, cx - x0, cy_ik - y0, meritko, alfa)
        pop = _popisek(popisek, int(st["velikost_popisku"]), st["pismo"], st["varianta"], tuple(st["barva_popisku"]), float(st["stin_popisku"]))
        cy_p = int(spec["y"]) + strana + int(st["mezera_popisku"]) + pop.height / 2
        _poloz(platno, pop, cx - x0, cy_p - y0, 1.0 if t_rel is None and mizeni is None else alfa, alfa)
    if spec.get("skrtnout"):
        _skrt(platno, spec, strana, x0, y0, starty, t_rel, mizeni)
    if spec.get("sipka") and len(spec["stredy"]) >= 2:
        # šipka „propojení“ mezi sousedními ikonami (Marcela 22. 10.): objeví se, až naskočí druhá ikona
        if t_rel is None:
            alfa_s = 1.0 if mizeni is None else mizeni * mizeni
        else:
            alfa_s = _clamp((t_rel - (starty[1] + NASKOK_S)) / 0.25)
        if alfa_s > 0:
            vrstva = Image.new("RGBA", platno.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(vrstva)
            barva = tuple(st["barva_popisku"]) + (int(255 * alfa_s),)
            cy = int(spec["y"]) + strana / 2 - y0
            tl = max(5, strana // 18)
            for i in range(len(spec["stredy"]) - 1):
                x1 = spec["stredy"][i] + strana / 2 + 14 - x0
                x2 = spec["stredy"][i + 1] - strana / 2 - 14 - x0
                if x2 - x1 < 30:
                    continue
                d.line((x1, cy, x2 - tl * 1.5, cy), fill=barva, width=tl)
                h = tl * 2.2
                d.polygon([(x2, cy), (x2 - h * 1.6, cy - h), (x2 - h * 1.6, cy + h)], fill=barva)
            platno.alpha_composite(vrstva)
    return platno, (x0, y0)
