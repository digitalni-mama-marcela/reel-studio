"""Prvek „vypínač a plakát“: osoba vyskočí, přepne vypínač na zdi a za ní se rozsvítí plakát.

Zadání Marcely 29. 10. 2026. Vzhled: prázdná zeď, nahoře přepínač jako v telefonu (bílý knoflík
vlevo, šedá kolejnice). Osoba přijde, natahuje se, nedosáhne, vyskočí a prstem ho přepne (kolejnice zezelená, knoflík
přejede doprava). O dva snímky později je za ní na zdi plakát s jemnou září okraje. Osoba odejde, plakát svítí dál.
Osoba je celou dobu PŘED vypínačem i plakátem (maska osoby).

Spec v osa["prvky"]:
  {"typ": "vypinac_plakat", "od": 0.0, "do": 9.1, "cas_zapnuti": "auto",
   "nadpis": ["OD", "DNES"], "datum": "30. 10. 2026", "text": "Tvůj první reel s Claudem",
   "podpis": "Claude Reel Studio", "web": "digitalnimamamarcela.cz", "fotky": ["fotka-1.jpg", "fotka-2.jpg"]}
  cas_zapnuti  čas v reelu, kdy se vypínač přepne; "auto" (výchozí) = nejvyšší bod skoku podle masky osoby
               (dopocitej po spočítání masky); bez masky 40 % délky prvku a varování
  soubor       hotový plakát (obrázek v kontext["podklady"] nebo absolutní cesta), vyplní plochu plakátu (ořez na střed);
               bez něj se plakát složí z nadpis, datum, text, podpis, web, fotky (barvy a písma značky)
  fotky        0 až 2 obrázky do plakátu (bez nich olivová plocha)
  plakat       volitelně [x0, y0, x1, y1] plochy plakátu v px (výchozí 140, 345, 940, 1465: nad spodním pásmem 450 px)
  vypinac_x, vypinac_y  volitelně střed vypínače; "auto" čas doplní x podle zdvižené ruky, y nechá nad plakátem
  nastup       "tvrdy" (výchozí: plakát je tam naráz) nebo "blik" (zářivka: 4 snímky bliká)
  zvuk         True (výchozí): render přidá do osa["zvuky"] cvaknutí vypínače (a bzučení u „blik“)
  vypinac      True (výchozí); False = jen plakát za osobou, rozsvítí se přesně v cas_zapnuti, bez vypínače a cvaknutí
               (Marcela 3. 11. 2026: v knihovně stylů zvlášť karta „Plakát za tebou“)

Vzhled (ODHAD ze snímků): vypínač 150 × 76 px, knoflík přejede za 0,08 s, zelená jako v telefonu. Plakát má ostré
rohy, bílou záři okraje 28 px a první 0,3 s je o 18 % jasnější (rozsvícení). Prvek je za osobou (za_hlavou) a přes
obličej (pres_oblicej), kontrola umístění ho neposuzuje. Ztmavení pokoje po rozsvícení (ve vzhledu slabé) se nedělá:
osoba by zůstala světlá a vypadala vystřižená.

Natáčení: stativ, prázdná světlá zeď, osoba přijde z boku, natáhne se k místu vypínače (asi 30 cm nad hlavou),
vyskočí, dotkne se ho, otočí se k plakátu, odejde. Celé 8 až 10 s, bez řeči, hudba přes Instagram.

Klíče stav(): ("vyp",) před přepnutím, číslo snímku při přepnutí a rozsvícení, ("zap",) potom, None mimo čas.
"""
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from ..titulky import FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "podklad": (251, 246, 239),      # krém značky
    "inkoust": (74, 51, 64),         # švestková
    "akcent": (212, 139, 160),       # růžová
    "plocha": (206, 212, 172),       # olivová, když chybí fotka
    "kolejnice_vyp": (226, 226, 230),
    "kolejnice_zap": (52, 199, 89),  # zelená přepínače v telefonu (ODHAD)
    "knofl": (255, 255, 255),
    "vypinac_sirka": 150,
    "vypinac_vyska": 76,
    "zare": 0.55,                    # síla bílé záře okolo plakátu
    "zare_px": 28,
    "rozsviceni": 0.18,              # o kolik je plakát jasnější hned po rozsvícení
    "pismo": "Montserrat-wght.ttf",
    "pismo_podpis": "InstrumentSerif-Italic.ttf",
}
VYCHOZI_PLAKAT = (140, 345, 940, 1465)
PREPNUTI_S = 0.08        # knoflík přejede
PRODLEVA_S = 0.07        # plakát se objeví o 2 snímky po přepnutí (4,70 s vypínač, 4,74 s plakát)
ROZSVICENI_S = 0.30
BLIK = (1.0, 0.2, 0.85, 0.35)   # průhlednost plakátu v prvních snímcích u nastupu "blik"
ODSTUP_VYPINACE = 34     # mezera mezi vypínačem a horní hranou plakátu
LEM = 60                 # průhledný okraj obrázku kvůli záři


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _ease_in_out(p):
    return 0.5 - 0.5 * math.cos(math.pi * _clamp(p))


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _klic_stylu(st):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in st.items()))


def _najdi(nazev, kontext):
    p = Path(nazev)
    if p.is_absolute() and p.exists():
        return p
    podklady = (kontext or {}).get("podklady")
    if podklady and (Path(podklady) / nazev).exists():
        return Path(podklady) / nazev
    raise ValueError("Vypínač a plakát: obrázek „%s“ nenalezen (podklady: %s)." % (nazev, podklady))


# ---------- příprava ----------

def pripravit(spec, styl, kontext):
    st = _styl(styl)
    cas = spec.get("od", 0.0)
    if spec.get("do", 0) - cas < 1.0:
        raise ValueError("Vypínač a plakát v čase %.1f s: prvek musí trvat aspoň 1 s." % cas)
    x0, y0, x1, y1 = [int(v) for v in (spec.get("plakat") or VYCHOZI_PLAKAT)]
    if x1 - x0 < 300 or y1 - y0 < 400:
        raise ValueError("Vypínač a plakát v čase %.1f s: plocha plakátu %s je moc malá (aspoň 300 × 400 px)."
                         % (cas, [x0, y0, x1, y1]))
    spec["plakat"] = [x0, y0, x1, y1]
    if spec.get("soubor"):
        spec["cesta"] = str(_najdi(spec["soubor"], kontext))
    spec["cesty_fotek"] = [str(_najdi(f, kontext)) for f in (spec.get("fotky") or [])[:2]]
    vh = st["vypinac_vyska"]
    if "vypinac_x" not in spec or spec.get("vypinac_x_auto"):
        spec["vypinac_x"], spec["vypinac_x_auto"] = (x0 + x1) // 2, True
    spec.setdefault("vypinac_y", max(HORNI_OKRAJ + vh // 2 + 4, y0 - ODSTUP_VYPINACE - vh // 2))
    spec.pop("varovani", None)
    if spec.get("cas_zapnuti") in (None, "auto"):
        spec["cas_zapnuti_s"] = cas + 0.4 * (spec["do"] - cas)
        spec["varovani"] = ("Vypínač a plakát v čase %.1f s: čas přepnutí se změří z masky osoby při renderu "
                            "(zatím %.2f s)." % (cas, spec["cas_zapnuti_s"]))
    else:
        spec["cas_zapnuti_s"] = float(spec["cas_zapnuti"])
        if not cas < spec["cas_zapnuti_s"] < spec["do"]:
            raise ValueError("Vypínač a plakát: cas_zapnuti %.2f s leží mimo prvek (%.1f až %.1f s)."
                             % (spec["cas_zapnuti_s"], cas, spec["do"]))
    spec["za_hlavou"] = True
    spec["pres_oblicej"] = True
    return None


def zmer_skok(maska, od, do, fps=FPS):
    """Snímek, kdy je osoba nejvýš (vrchol skoku = dotyk vypínače). Vrátí (čas, y, x) v px 1080x1920, nebo None."""
    import numpy as np
    nejlepsi = None
    for i in range(int(round(od * fps)), int(round(do * fps))):
        m = maska.mala(i)
        radky = np.nonzero((m > 128).any(axis=1))[0]
        if not len(radky):
            continue
        r = int(radky[0])
        if nejlepsi is None or r < nejlepsi[1]:
            sloupce = np.nonzero(m[r] > 128)[0]
            nejlepsi = (i, r, float(sloupce.mean()), m.shape)
    if nejlepsi is None:
        return None
    i, r, s, (h, w) = nejlepsi
    return i / fps, int(r * VYSKA / h), int(s * SIRKA / w)


def dopocitej(spec, video, maska):
    """Volá render po spočítání masky: čas přepnutí z vrcholu skoku a vodorovná poloha vypínače nad prstem."""
    if spec.get("cas_zapnuti") not in (None, "auto") or maska is None:
        return
    skok = zmer_skok(maska, spec["od"], spec["do"])
    if skok is None:
        spec["varovani"] = "Vypínač a plakát: v úseku %.1f až %.1f s není osoba, čas přepnutí odhadnut." % (spec["od"], spec["do"])
        return
    t, y, x = skok
    spec["cas_zapnuti_s"] = min(max(t, spec["od"] + 0.1), spec["do"] - 0.2)
    if spec.get("vypinac_x_auto"):
        x0, _, x1, _ = spec["plakat"]
        spec["vypinac_x"] = int(_clamp(x, x0 + 90, x1 - 90))
    spec["vrchol_prstu_y"] = y
    spec.pop("varovani", None)


def zvuky(spec):
    """Zvuky k prvku: cvaknutí v okamžiku přepnutí, u nástupu „blik“ i bzučení zářivky."""
    if not spec.get("zvuk", True):
        return []
    t = spec["cas_zapnuti_s"]
    if not spec.get("vypinac", True):
        return [{"typ": "bzuk", "cas": round(t, 3), "db": -24}] if spec.get("nastup") == "blik" else []
    out = [{"typ": "cvak", "cas": round(t, 3), "db": -14}]
    if spec.get("nastup") == "blik":
        out.append({"typ": "bzuk", "cas": round(t + PRODLEVA_S, 3), "db": -24})
    return out


# ---------- čas ----------

def stav(spec, t):
    if t < spec["od"] or t >= spec["do"]:
        return None
    tz = spec["cas_zapnuti_s"]
    if not spec.get("vypinac", True):
        tz -= PRODLEVA_S          # bez vypínače se plakát rozsvítí přesně v cas_zapnuti
    if t < tz:
        return ("vyp",)
    if t < tz + PRODLEVA_S + ROZSVICENI_S + 1.0 / FPS:
        return int(math.floor((t - tz) * FPS + 1e-6))
    return ("zap",)


# ---------- kreslení ----------

@lru_cache(maxsize=64)
def _vypinac(poloha, st_klic):
    """Přepínač jako v telefonu, poloha 0 = vypnuto (knoflík vlevo), 1 = zapnuto."""
    st = dict(st_klic)
    w, h = st["vypinac_sirka"], st["vypinac_vyska"]
    k = 4
    W, H = (w + 40) * k, (h + 40) * k
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stin = Image.new("L", (W, H), 0)
    ImageDraw.Draw(stin).rounded_rectangle([20 * k, 24 * k, (20 + w) * k, (24 + h) * k], h * k // 2, fill=70)
    img.putalpha(stin.filter(ImageFilter.GaussianBlur(7 * k)))
    d = ImageDraw.Draw(img)
    a, b = st["kolejnice_vyp"], st["kolejnice_zap"]
    barva = tuple(int(a[i] + (b[i] - a[i]) * poloha) for i in range(3))
    d.rounded_rectangle([20 * k, 20 * k, (20 + w) * k, (20 + h) * k], h * k // 2, fill=barva + (255,))
    okraj = 6
    r = h // 2 - okraj
    cx = 20 + okraj + r + (w - 2 * okraj - 2 * r) * poloha
    cy = 20 + h // 2
    stin_k = Image.new("L", (W, H), 0)
    ImageDraw.Draw(stin_k).ellipse([(cx - r) * k, (cy - r + 3) * k, (cx + r) * k, (cy + r + 3) * k], fill=90)
    vrstva = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vrstva.putalpha(stin_k.filter(ImageFilter.GaussianBlur(3 * k)))
    img.alpha_composite(vrstva)
    ImageDraw.Draw(img).ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=tuple(st["knofl"]) + (255,))
    return img.resize((w + 40, h + 40), Image.LANCZOS)


def _vloz_fotku(platno, cesta, box, st):
    x0, y0, x1, y1 = [int(v) for v in box]
    if cesta:
        foto = ImageOps.fit(Image.open(cesta).convert("RGB"), (x1 - x0, y1 - y0), Image.LANCZOS)
        platno.paste(foto, (x0, y0))
    else:
        ImageDraw.Draw(platno).rectangle([x0, y0, x1 - 1, y1 - 1], fill=tuple(st["plocha"]))


def _velikost_na_sirku(text, soubor, varianta, sirka, max_v):
    v = max_v
    while v > 20:
        if pismo(soubor, v, varianta).getlength(text) <= sirka:
            return v
        v -= 4
    return v


def _zalom(text, f, sirka):
    radky, radek = [], ""
    for slovo in str(text).split():
        zkus = (radek + " " + slovo).strip()
        if f.getlength(zkus) <= sirka or not radek:
            radek = zkus
        else:
            radky.append(radek)
            radek = slovo
    if radek:
        radky.append(radek)
    return radky


@lru_cache(maxsize=4)
def _plakat(w, h, cesta, obsah, st_klic):
    """Plakát bez záře: hotový obrázek, nebo složený z textů a fotek (barvy a písma značky)."""
    st = dict(st_klic)
    if cesta:
        return ImageOps.fit(Image.open(cesta).convert("RGB"), (w, h), Image.LANCZOS)
    nadpis, datum, text, podpis, web, fotky = obsah
    img = Image.new("RGB", (w, h), tuple(st["podklad"]))
    d = ImageDraw.Draw(img)
    p = int(w * 0.06)
    sloupec = (w - 3 * p) // 2
    ink = tuple(st["inkoust"])
    # vlevo nahoře velký nadpis, každý řádek na šířku sloupce
    y = p
    if nadpis:
        v = min(_velikost_na_sirku(r, st["pismo"], "Black", sloupec, 230) for r in nadpis)
        f = pismo(st["pismo"], v, "Black")
        for r in nadpis:
            d.text((p, y), r, font=f, fill=ink, anchor="lt")
            y += int(v * 0.98)
    if datum:
        f = pismo(st["pismo"], int(w * 0.05), "Bold")
        d.text((p, y + int(w * 0.02)), datum, font=f, fill=tuple(st["akcent"]), anchor="lt")
    # vpravo nahoře fotka, vlevo dole druhá fotka
    vf = int(h * 0.48)
    _vloz_fotku(img, fotky[0] if len(fotky) > 0 else None, (2 * p + sloupec, p, w - p, p + vf), st)
    _vloz_fotku(img, fotky[1] if len(fotky) > 1 else None, (p, 2 * p + vf, p + sloupec, h - p), st)
    # vpravo dole text, podpis, web
    xt, yt = 2 * p + sloupec, 2 * p + vf
    if text:
        f = pismo(st["pismo"], int(w * 0.052), "ExtraBold")
        for r in _zalom(str(text).upper(), f, sloupec):
            d.text((xt, yt), r, font=f, fill=ink, anchor="lt")
            yt += int(w * 0.062)
    if podpis:
        f = pismo(st["pismo_podpis"], int(w * 0.05))
        d.text((xt, yt + int(w * 0.04)), podpis, font=f, fill=ink, anchor="lt")
    if web:
        f = pismo(st["pismo"], int(w * 0.026), "Medium")
        d.line([xt, h - p - int(w * 0.05), w - p, h - p - int(w * 0.05)], fill=ink, width=2)
        d.text((xt, h - p), web, font=f, fill=ink, anchor="lb")
    return img


@lru_cache(maxsize=4)
def _plakat_se_zari(w, h, cesta, obsah, st_klic):
    st = dict(st_klic)
    out = Image.new("RGBA", (w + 2 * LEM, h + 2 * LEM), (0, 0, 0, 0))
    zare = Image.new("L", out.size, 0)
    ImageDraw.Draw(zare).rectangle([LEM - 6, LEM - 6, LEM + w + 5, LEM + h + 5], fill=int(255 * st["zare"]))
    bila = Image.new("RGBA", out.size, (255, 255, 255, 0))
    bila.putalpha(zare.filter(ImageFilter.GaussianBlur(st["zare_px"] / 2)))
    out.alpha_composite(bila)
    out.paste(_plakat(w, h, cesta, obsah, st_klic), (LEM, LEM))
    return out


def _obsah(spec):
    nadpis = spec.get("nadpis") or []
    if isinstance(nadpis, str):
        nadpis = nadpis.split("\n")
    return (tuple(nadpis), spec.get("datum"), spec.get("text"), spec.get("podpis"), spec.get("web"),
            tuple(spec.get("cesty_fotek") or ()))


def obdelnik(spec, styl):
    st = _styl(styl)
    x0, y0, x1, y1 = spec["plakat"]
    if not spec.get("vypinac", True):
        return x0, y0, x1, y1
    vx, vy = spec["vypinac_x"], spec["vypinac_y"]
    vw, vh = st["vypinac_sirka"], st["vypinac_vyska"]
    return min(x0, vx - vw // 2), min(y0, vy - vh // 2), max(x1, vx + vw // 2), max(y1, vy + vh // 2)


def vykresli(spec, styl, klic):
    st = _styl(styl)
    sk = _klic_stylu(st)
    x0, y0, x1, y1 = obdelnik(spec, styl)
    ox, oy = x0 - LEM, y0 - LEM
    platno = Image.new("RGBA", (x1 - x0 + 2 * LEM, y1 - y0 + 2 * LEM), (0, 0, 0, 0))
    if klic == ("vyp",):
        poloha, plakat_alfa, jas = 0.0, 0.0, 0.0
    elif klic == ("zap",):
        poloha, plakat_alfa, jas = 1.0, 1.0, 0.0
    else:
        t = klic / FPS
        poloha = _ease_in_out(t / PREPNUTI_S)
        tp = t - PRODLEVA_S
        if tp < 0:
            plakat_alfa, jas = 0.0, 0.0
        else:
            snimek = int(round(tp * FPS))
            plakat_alfa = BLIK[snimek] if spec.get("nastup") == "blik" and snimek < len(BLIK) else 1.0
            jas = st["rozsviceni"] * (1 - _clamp(tp / ROZSVICENI_S))
    if plakat_alfa > 0:
        px0, py0, px1, py1 = spec["plakat"]
        p = _plakat_se_zari(px1 - px0, py1 - py0, spec.get("cesta"), _obsah(spec), sk)
        if jas > 0.005:
            a = p.getchannel("A")
            p = ImageEnhance.Brightness(p.convert("RGB")).enhance(1 + jas).convert("RGBA")
            p.putalpha(a)
        if plakat_alfa < 1:
            p = p.copy()
            p.putalpha(p.getchannel("A").point(lambda v: int(v * plakat_alfa)))
        platno.alpha_composite(p, (px0 - LEM - ox, py0 - LEM - oy))
    if not spec.get("vypinac", True):
        return platno, (ox, oy)
    v = _vypinac(round(poloha, 3), sk)
    platno.alpha_composite(v, (spec["vypinac_x"] - v.width // 2 - ox, spec["vypinac_y"] - v.height // 2 - oy))
    return platno, (ox, oy)
