"""Společné pomůcky prvků z 3. 11. 2026 (obálka časopisu, časová osa, okna s videi, storyboard, komentář, sledovat).

Klíč stav() u těchto prvků: ("a", n) n-tý snímek od začátku prvku, ("z", n) n-tý snímek odchodu (poslední 0,25 s),
"s" klid. Prvky s pohybem po celou dobu (video, posun, běžící čas) vracejí vždy ("a", n).
"""
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..titulky import FPS, pismo

ODCHOD_S = 0.25
KREM = (251, 246, 239)
SVESTKOVA = (74, 51, 64)
RUZOVA = (212, 139, 160)
CERVENA = (226, 62, 62)


def stav_obecny(spec, t, konec_animace=None):
    od, do = float(spec["od"]), float(spec["do"])
    if t < od or t >= do:
        return None
    if do - t < ODCHOD_S:
        return ("z", int((do - t) * FPS))
    rel = t - od
    if konec_animace is None or rel < konec_animace:
        return ("a", int(rel * FPS))
    return "s"


def rozloz_klic(klic, spec, konec_animace):
    """Vrátí (čas od začátku prvku, průhlednost odchodu 0..1)."""
    if klic == "s":
        return konec_animace, 1.0
    if klic[0] == "z":
        zbyva = klic[1] / FPS
        return float(spec["do"]) - float(spec["od"]) - zbyva, max(0.0, min(1.0, zbyva / ODCHOD_S)) ** 2
    return klic[1] / FPS, 1.0


def hladce(p):
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


def pruzne(p):
    """Pružné naskočení 0 -> 1 s malým přestřelením (meritko)."""
    p = max(0.0, min(1.0, p))
    return 1 + 2.2 * (p - 1) ** 3 + 1.2 * (p - 1) ** 2 if p < 1 else 1.0


def nasob_alfu(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def karta(w, h, barva, radius, stin=90, okraj=None, pad=30):
    """Zaoblená karta se stínem. Vrátí (obrázek, pad) - karta začíná na (pad, pad)."""
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if stin:
        s = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((pad, pad + 10, pad + w, pad + h + 10), radius=radius, fill=(0, 0, 0, stin))
        im = Image.alpha_composite(im, s.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius, fill=tuple(barva),
                        outline=tuple(okraj) if okraj else None, width=3 if okraj else 0)
    return im, pad


@lru_cache(maxsize=8)
def kulata_fotka(cesta, prumer):
    """Kulatý výřez fotky (profilová fotka). Bez souboru šedá silueta."""
    out = Image.new("RGBA", (prumer, prumer), (0, 0, 0, 0))
    m = Image.new("L", (prumer * 4, prumer * 4), 0)
    ImageDraw.Draw(m).ellipse((0, 0, prumer * 4 - 1, prumer * 4 - 1), fill=255)
    m = m.resize((prumer, prumer), Image.LANCZOS)
    if cesta and Path(cesta).exists():
        im = Image.open(cesta).convert("RGB")
        s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
        out.paste(im.resize((prumer, prumer), Image.LANCZOS), (0, 0), m)
    else:
        sil = Image.new("RGBA", (prumer, prumer), (205, 205, 210, 255))
        d = ImageDraw.Draw(sil)
        d.ellipse((prumer * 0.32, prumer * 0.18, prumer * 0.68, prumer * 0.54), fill=(245, 245, 247))
        d.ellipse((prumer * 0.14, prumer * 0.6, prumer * 0.86, prumer * 1.25), fill=(245, 245, 247))
        out.paste(sil, (0, 0), m)
    return out


def text(d, xy, t, soubor, velikost, varianta=None, barva=(0, 0, 0), anchor="la", proklad=0):
    f = pismo(soubor, velikost, varianta)
    if not proklad:
        d.text(xy, t, font=f, fill=barva, anchor=anchor)
        return f.getlength(t)
    x, y = xy
    for z in t:
        d.text((x, y), z, font=f, fill=barva, anchor=anchor)
        x += f.getlength(z) + proklad
    return x - xy[0]


def snimky_videa(zdroj, od, delka, sirka, vyska, cil):
    """Snímky úseku videa zmenšené a oříznuté na sirka x vyska, 30 za sekundu, bez zvuku, do souboru rawvideo RGB.
    Originál se jen čte. Vrátí (cesta, počet snímků)."""
    cil = Path(cil)
    cil.parent.mkdir(parents=True, exist_ok=True)
    if not cil.exists():
        vf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=%d" % (sirka, vyska, sirka, vyska, FPS)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % od, "-t", "%.3f" % delka, "-i", str(zdroj),
                        "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", str(cil)], check=True)
    n = cil.stat().st_size // (sirka * vyska * 3)
    return str(cil), int(n)


def snimek_videa(cesta, sirka, vyska, i, n):
    if n <= 0:
        return Image.new("RGB", (sirka, vyska), (30, 30, 30))
    data = np.memmap(cesta, dtype=np.uint8, mode="r", shape=(n, vyska, sirka, 3))
    return Image.fromarray(np.array(data[max(0, min(n - 1, i))]))


VIDEO_PRIPONY = (".mp4", ".mov", ".m4v")


def najdi_soubor(nazev, kontext):
    """Absolutní cesta k souboru zákaznice (název ve složce podkladů nebo absolutní cesta). Nenalezený vrátí, jak je."""
    p = Path(str(nazev)).expanduser()
    if not p.is_absolute() and kontext and kontext.get("podklady"):
        p = Path(kontext["podklady"]) / p
    return str(p)


@lru_cache(maxsize=64)
def nahled(cesta, sirka, vyska, cas=1.0):
    """Náhled souboru oříznutý na sirka x vyska (RGB). U videa snímek v čase cas (originál se jen čte, 3. 11. 2026).
    Chybějící soubor = šedá plocha (prvek se vykreslí, kontrola reelu ho nahlásí podle spec["varovani"])."""
    p = Path(cesta)
    im = None
    if p.exists() and p.suffix.lower() in VIDEO_PRIPONY:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.2f" % cas, "-i", str(p), "-frames:v", "1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.returncode == 0 and r.stdout:
            import io
            im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    elif p.exists():
        im = Image.open(p).convert("RGB")
    if im is None:
        return Image.new("RGB", (sirka, vyska), (150, 150, 150))
    k = max(sirka / im.width, vyska / im.height)
    im = im.resize((max(sirka, int(im.width * k + 0.5)), max(vyska, int(im.height * k + 0.5))), Image.LANCZOS)
    x, y = (im.width - sirka) // 2, int((im.height - vyska) * 0.3)
    return im.crop((x, y, x + sirka, y + vyska))


def karta_s_nahledem(cesta, sirka, vyska, okraj=5, radius=10, barva_okraje=(255, 255, 255)):
    """Fotka v zaobleném bílém rámečku (RGBA, bez stínu)."""
    im = Image.new("RGBA", (sirka + 2 * okraj, vyska + 2 * okraj), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius + okraj, fill=tuple(barva_okraje) + (255,))
    m = Image.new("L", (sirka, vyska), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, sirka - 1, vyska - 1), radius=radius, fill=255)
    im.paste(nahled(cesta, sirka, vyska), (okraj, okraj), m)
    return im


def se_stinem(im, sila=110, rozmazani=10, posun=8):
    """Obrázek s měkkým stínem pod sebou. Vrátí (obrázek, odsazení původního obrázku)."""
    pad = rozmazani * 2 + posun
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    st = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = im.getchannel("A").point(lambda v: v * sila // 255)
    st.paste((0, 0, 0, 255), (pad, pad + posun), a)
    out.alpha_composite(st.filter(ImageFilter.GaussianBlur(rozmazani)))
    out.alpha_composite(im, (pad, pad))
    return out, pad
