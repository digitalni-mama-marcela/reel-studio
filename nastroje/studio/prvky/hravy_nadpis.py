"""Hravý nadpis: krátký nadpis (2 až 4 slova) a pod ním ručně psaný podpis se smyčkou, který si „hraje“ s osobou.

Zadání Marcely 29. 10. 2026. Typ videa: krátké video bez řeči nebo hook na začátku
mluvícího videa, osoba hraje s textem gestem (ruka, tablet, pusa).

Vzhled (ODHAD ze snímků): hlavní řádek tučný sans (Montserrat ExtraBold), pastelově růžový s bílou září; pod ním
vpravo patková kurziva (Instrument Serif Italic, ručně psané písmo zatím nemáme) se smyčkou pod slovem.

Spec v osa["prvky"]:
  {"typ": "hravy_nadpis", "od": 0.0, "do": 2.4, "text": "5 tipů", "podpis": "na zkoušku",
   "nastup": "psani", "pohyb": null, "za_hlavou": true}
  text       hlavní řádek (krátký, vejde se do 1000 px; jinak se písmo zmenšuje)
  podpis     volitelné, menší řádek pod textem
  nastup     "psani" (výchozí: písmena naskakují po jednom, pak se podpis odkryje zleva), "hned", nebo "ruce":
             nadpis se odkrývá od středu do stran tak, jak osoba rozevírá ruce nad hlavou (spec["odkryti"] z masky)
  pohyb      žádný (text stojí, s za_hlavou=true ho osoba zakrývá, když se nakloní) nebo:
             "odlet"     podpis se v čase odlet_v (s od začátku prvku, výchozí 0,8 s před koncem) otočí a odletí nahoru
             "ruka"      text sedí na nejvyšším bodě osoby (zdvižená ruka) a jede s ním; potřebuje spec["draha"]
             "obrazovka" text je v tmavé obrazovce tabletu nebo telefonu v ruce; potřebuje spec["rohy"]
             "pusa"      jedno slovo „vyletí z pusy“: roste z malého do velkého, pulzuje v časech pulzy (s od začátku)
  klice      volitelné, pohyb po bodech: [[t od začátku prvku, střed x, střed y, měřítko], ...], mezi body plynule
             (např. malý nápis na svetru, pak hozený nad hlavu). Jde kombinovat s odletem podpisu.
  podpis_x   kde pod hlavním řádkem podpis začíná (podíl šířky, výchozí 0,18); odlet_dx = vodorovný let podpisu (px)
  y          volitelné, horní okraj bloku; výchozí: za hlavou 250 px (hned pod horním pásmem), jinak pod obličejem
  velikost, barva, zare_px, podpis_velikost   volitelné přepsání vzhledu

draha a rohy se počítají až z videa (dopocitej(), volá render po masce osoby). Snímky videa vidí jen místní
program (OpenCV), nic se nikam neposílá.
"""
import math
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ..titulky import DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 150, "max_sirka": 1000,
    "barva": (246, 198, 238), "zare": (255, 255, 255, 190), "zare_px": 14,
    "stin": (60, 30, 50, 110), "stin_px": 10,    # jemný tmavý stín: na bílé zdi zář nestačí (OVĚŘENO 29. 10., reel Marcely)
    "podpis_pismo": "InstrumentSerif-Italic.ttf", "podpis_velikost": 100, "podpis_barva": (255, 255, 255),
    "smycka": True,
    "psani_s": 0.6,          # všechna písmena hlavního řádku
    "podpis_s": 0.35,        # odkrytí podpisu zleva
    "odlet_s": 0.5,
    "odlet_dx": 40,
    "podpis_x": 0.18,
    "pusa_velikost": 260,
}
MEZERA_POD_OBLICEJEM = 40
NAD_RUKOU = 0.35             # o kolik výšky bloku text sedí nad nejvyšším bodem osoby (prsty zasahují do textu)
TMAVA_OBRAZOVKA = 45         # jas (0..255) pod tímto = obrazovka tabletu
MIN_PODIL_OBRAZOVKY = 0.015  # obrazovka zabírá aspoň tolik plochy snímku
DRZET_ROHY = 5               # když se obrazovka na pár snímků ztratí, drží se poslední poloha


def _styl(spec, styl):
    st = dict(VYCHOZI_STYL)
    st.update(styl or {})
    for k in VYCHOZI_STYL:
        if k in spec:
            st[k] = spec[k]
    return st


def _klic(st):
    return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in st.items()))


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _ease_out_back(p, s=1.7):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


# ---------- kreslení bloku ----------

def _stin_pod(img, st):
    """Rozmazaný tmavý stín tvaru textu (kopie alfy obarvená na st["stin"])."""
    stin = Image.new("RGBA", img.size, tuple(st["stin"][:3]) + (0,))
    stin.putalpha(img.getchannel("A").point(lambda v: v * st["stin"][3] // 255))
    return stin.filter(ImageFilter.GaussianBlur(st["stin_px"]))


@lru_cache(maxsize=64)
def _radek(text, st_klic, velikost=None):
    """Hlavní řádek s září. Vrátí (RGBA obrázek, šířky prefixů po písmenech) pro psaní po písmenech."""
    st = dict(st_klic)
    v = velikost or st["velikost"]
    f = pismo(st["pismo"], v, st["varianta"])
    while f.getlength(text) > st["max_sirka"] and v > 60:
        v -= 6
        f = pismo(st["pismo"], v, st["varianta"])
    z = st["zare_px"]
    x0, y0, x1, y1 = f.getbbox(text)
    w, h = int(x1 - x0) + 4 * z, int(y1 - y0) + 4 * z
    zare = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(zare).text((2 * z - x0, 2 * z - y0), text, font=f, fill=tuple(st["zare"]))
    img = _stin_pod(zare, st)
    img.alpha_composite(zare.filter(ImageFilter.GaussianBlur(z)))
    ImageDraw.Draw(img).text((2 * z - x0, 2 * z - y0), text, font=f, fill=tuple(st["barva"]) + (255,))
    prefixy = [2 * z + f.getlength(text[:i]) for i in range(len(text) + 1)]
    return img, tuple(prefixy)


@lru_cache(maxsize=64)
def _podpis(text, st_klic):
    """Podpis kurzivou se smyčkou pod slovem (ruční tah: lomená čára po Bézierově křivce)."""
    st = dict(st_klic)
    f = pismo(st["podpis_pismo"], st["podpis_velikost"])
    x0, y0, x1, y1 = f.getbbox(text)
    w, h = int(x1 - x0) + 40, int(y1 - y0) + 70
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    barva = tuple(st["podpis_barva"]) + (255,)
    d.text((20 - x0, 10 - y0), text, font=f, fill=barva)
    if st["smycka"]:
        # smyčka: z levého spodku pod slovem doprava, malé očko a ocásek nahoru (jako tah perem)
        b = [(20, h - 40), (w * 0.45, h - 8), (w * 0.62, h - 30), (w * 0.52, h - 48),
             (w * 0.44, h - 30), (w * 0.62, h - 14), (w - 14, h - 34)]
        body = []
        for i in range(len(b) - 1):
            for s in range(12):
                p = s / 12
                body.append((b[i][0] + (b[i + 1][0] - b[i][0]) * p, b[i][1] + (b[i + 1][1] - b[i][1]) * p))
        body.append(b[-1])
        d.line(body, fill=barva, width=4, joint="curve")
    out = _stin_pod(img, st)
    out.alpha_composite(img.filter(ImageFilter.GaussianBlur(0.6)))
    return out


def _blok(spec, st, k_psani=None, k_podpis=1.0, velikost=None):
    """Složí hlavní řádek a podpis do jednoho obrázku. k_psani = kolik písmen je vidět (None = všechna)."""
    radek, prefixy = _radek(spec["text"], _klic(st), velikost)
    w, h = radek.size
    if k_psani is not None and k_psani < len(spec["text"]):
        orez = int(prefixy[k_psani]) if k_psani > 0 else 0
        r = Image.new("RGBA", radek.size, (0, 0, 0, 0))
        if orez > 0:
            r.paste(radek.crop((0, 0, orez, h)), (0, 0))
        radek = r
    pod = _podpis(spec["podpis"], _klic(st)) if spec.get("podpis") else None
    if pod is None:
        return radek
    pw, ph = pod.size
    px = int(w * st["podpis_x"])       # podpis začíná kousek zprava pod hlavním řádkem
    py = int(h * 0.62)                 # a zasahuje do jeho spodku
    W, H = max(w, px + pw), py + ph
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(radek, (0, 0))
    if k_podpis > 0:
        img.alpha_composite(pod.crop((0, 0, max(1, int(pw * k_podpis)), ph)), (px, py))
    return img


def _rozmer(spec, st):
    return _blok(spec, st).size


# ---------- rozhraní prvku ----------

def pripravit(spec, styl, kontext):
    st = _styl(spec, styl)
    pohyb = spec.get("pohyb")
    if pohyb in ("ruka", "pusa", "obrazovka"):
        spec.setdefault("za_hlavou", False)    # ruka, tablet i pusa jsou před textem jen vpředu
    w, h = _rozmer(spec, st)
    spec["sirka"], spec["vyska"] = w, h
    spec["x"] = (SIRKA - w) // 2
    okno = kontext.get("okno")
    if "y" not in spec:
        if spec.get("za_hlavou") or not okno:
            spec["y"] = kontext.get("horni", HORNI_OKRAJ) + 30
        else:
            spec["y"] = int(okno[3]) + MEZERA_POD_OBLICEJEM
    spod = VYSKA - kontext.get("dolni", DOLNI_OKRAJ)
    if spec["y"] + h > spod and pohyb != "pusa":
        spec["y"] = max(kontext.get("horni", HORNI_OKRAJ), spod - h)
        spec["varovani"] = "nadpis se pod obličej nevešel, posunut výš"
    if spec.get("za_hlavou"):
        spec["pres_oblicej"] = True       # osoba ho záměrně zakrývá, kontrola to nehlásí
    if pohyb == "pusa":
        spec["pres_oblicej"] = True
        if "stred" not in spec:
            if okno:
                x0, y0, x1, y1 = okno
                spec["stred"] = [int((x0 + x1) / 2), int(y0 + (y1 - y0) * 0.78)]   # ústa ve spodní čtvrtině obličeje
            else:
                spec["stred"] = [SIRKA // 2, int(VYSKA * 0.42)]
        spec.setdefault("pulzy", [0.0, 0.55])
    if pohyb == "ruka" and not spec.get("draha"):
        spec["varovani"] = "chybí dráha ruky (dopocitej po masce osoby), text zůstane stát"
    if pohyb == "obrazovka" and not spec.get("rohy"):
        spec["varovani"] = "obrazovka tabletu nenalezena (dopocitej), text se nezobrazí"


def _nastup_konec(spec, st):
    """Kdy nástup skončí (s od začátku prvku); do té doby se kreslí každý snímek."""
    if spec.get("nastup", "psani") == "psani":
        return st["psani_s"] + (st["podpis_s"] if spec.get("podpis") else 0)
    if spec.get("nastup") == "ruce":
        return len(spec.get("odkryti") or []) / FPS
    return 0.0


def _konec_pohybu(spec, st):
    kl = spec.get("klice")
    return max(_nastup_konec(spec, st), kl[-1][0] if kl else 0.0)


def stav(spec, t):
    st = _styl(spec, {})
    t_rel = t - spec["od"]
    k = int(round(t_rel * FPS))
    pohyb = spec.get("pohyb")
    if pohyb in ("ruka", "obrazovka", "pusa"):
        return k
    if pohyb == "odlet" and t_rel >= _odlet_v(spec, st):
        return k
    if t_rel < _konec_pohybu(spec, st):
        return k
    return "stoji"


def _odlet_v(spec, st):
    return spec.get("odlet_v", max(0.0, spec["do"] - spec["od"] - 0.8))


def _poloha(spec, t_rel):
    """Levý horní roh bloku a měřítko v čase t_rel. S klíči plynule (smoothstep) mezi body [t, střed x, střed y, měřítko]."""
    kl = spec.get("klice")
    if not kl:
        return spec["x"], spec["y"], 1.0
    if t_rel <= kl[0][0]:
        _, cx, cy, m = kl[0]
    elif t_rel >= kl[-1][0]:
        _, cx, cy, m = kl[-1]
    else:
        for a, b in zip(kl, kl[1:]):
            if a[0] <= t_rel <= b[0]:
                p = (t_rel - a[0]) / max(1e-6, b[0] - a[0])
                p = p * p * (3 - 2 * p)
                cx, cy, m = (a[n] + (b[n] - a[n]) * p for n in (1, 2, 3))
                break
    return int(cx - spec["sirka"] * m / 2), int(cy - spec["vyska"] * m / 2), m


def obdelnik(spec, styl):
    if spec.get("pohyb") == "pusa":
        st = _styl(spec, styl)
        img = _radek(spec["text"], _klic(st), st["pusa_velikost"])[0]
        cx, cy = spec["stred"]
        return (cx - img.width // 2, cy - img.height // 2, cx + img.width // 2, cy + img.height // 2)
    x, y, m = _poloha(spec, 1e9)
    return (x, y, x + int(spec["sirka"] * m), y + int(spec["vyska"] * m))


def _nastupni_stav(spec, st, t_rel):
    if spec.get("nastup", "psani") != "psani":
        return None, 1.0
    n = len(spec["text"])
    k_psani = min(n, int(math.ceil(n * t_rel / st["psani_s"]))) if t_rel < st["psani_s"] else None
    k_podpis = _clamp((t_rel - st["psani_s"]) / st["podpis_s"])
    return k_psani, k_podpis


def _zmensi(img, m):
    if abs(m - 1.0) < 0.01:
        return img
    return img.resize((max(1, int(img.width * m)), max(1, int(img.height * m))), Image.LANCZOS)


def _odkryj_od_stredu(img, x, polovina, stred_obrazu=SIRKA / 2):
    """Nechá z bloku jen pás |x − stred_obrazu| < polovina (ruce „rozepisují“ nadpis od místa dlaní do stran)."""
    stred = stred_obrazu - x
    l, r = int(max(0, stred - polovina)), int(min(img.width, stred + polovina))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    if r > l:
        out.paste(img.crop((l, 0, r, img.height)), (l, 0))
    return out


def vykresli(spec, styl, k):
    st = _styl(spec, styl)
    pohyb = spec.get("pohyb")
    # „stoji“ = nástup i pohyb po bodech skončily a odlet ještě nezačal (odlet má vlastní čísla snímků)
    t_rel = _konec_pohybu(spec, st) if k == "stoji" else k / FPS
    k_psani, k_podpis = _nastupni_stav(spec, st, t_rel)

    if pohyb == "pusa":
        return _pusa(spec, st, t_rel)
    if pohyb == "obrazovka":
        return _na_obrazovce(spec, st, k)

    x, y, m = _poloha(spec, t_rel)
    if pohyb == "odlet" and spec.get("podpis") and t_rel >= _odlet_v(spec, st):
        p = _clamp((t_rel - _odlet_v(spec, st)) / st["odlet_s"])
        posun = (st["odlet_dx"] * p, -(y + 400) * p * p)     # zrychluje nahoru a ven z obrazu
        uhel, alfa = 200 * p, 1 - p * 0.3
        # podpis letí sám: hlavní řádek zůstává, podpis se kreslí zvlášť na posunutou polohu
        zaklad = _zmensi(_blok(dict(spec, podpis=None), st, k_psani), m)
        plat = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
        plat.alpha_composite(zaklad, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
        pod = _zmensi(_podpis(spec["podpis"], _klic(st)), m).rotate(uhel, expand=True, resample=Image.BICUBIC)
        a = pod.getchannel("A").point(lambda v: int(v * alfa))
        pod.putalpha(a)
        px, py = x + int(zaklad.width * st["podpis_x"] + posun[0]), y + int(zaklad.height * 0.62 + posun[1])
        if py + pod.height > 0 and px < SIRKA:
            plat.alpha_composite(pod, (max(0, px), max(0, py)), (max(0, -px), max(0, -py)))
        return plat, (0, 0)
    img = _blok(spec, st, k_psani, k_podpis)
    if spec.get("nastup") == "ruce" and k != "stoji":
        odkryti = spec.get("odkryti") or []
        if 0 <= k < len(odkryti):
            img = _odkryj_od_stredu(img, x, odkryti[k], spec.get("odkryti_stred", SIRKA / 2))
    img = _zmensi(img, m)
    if pohyb == "ruka" and spec.get("draha"):
        draha = spec["draha"]
        vrch = draha[min(max(0, k), len(draha) - 1)] if k != "stoji" else None
        if vrch is not None:
            y = min(spec["y"], int(vrch - img.height * NAD_RUKOU))
            y = max(-img.height // 2, y)                   # smí odjet kousek z obrazu nahoru, jako ve vzhledu
        if y < 0:
            img = img.crop((0, -y, img.width, img.height))
            y = 0
    return img, (x, y)


def _pusa(spec, st, t_rel):
    """Slovo vyletí z pusy: z 12 % velikosti s překmitem do plné, chvíli drží, splaskne; opakuje se v pulzech."""
    meritko = 0.0
    for p0 in spec.get("pulzy", [0.0]):
        dt = t_rel - p0
        if dt < 0:
            continue
        if dt < 0.18:
            m = 0.12 + 0.88 * _ease_out_back(dt / 0.18)
        elif dt < 0.30:
            m = 1.0
        elif dt < 0.45:
            m = 1.0 - 0.7 * _ease_out_cubic((dt - 0.30) / 0.15)
        else:
            m = 0.3
        meritko = m
    img, _ = _radek(spec["text"], _klic(st), st["pusa_velikost"])
    if meritko <= 0.01:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0)
    w, h = max(1, int(img.width * meritko)), max(1, int(img.height * meritko))
    img = img.resize((w, h), Image.LANCZOS)
    cx, cy = spec["stred"]
    x, y = int(cx - w / 2), int(cy - h / 2)
    plat = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
    plat.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
    return plat, (0, 0)


def _koeficienty(cil, zdroj):
    """Koeficienty pro Image.transform(PERSPECTIVE): bod výstupu (cil) -> bod vstupu (zdroj), 4 dvojice."""
    import numpy as np
    a, b = [], []
    for (x, y), (u, v) in zip(cil, zdroj):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    return np.linalg.solve(np.array(a, float), np.array(b, float)).tolist()


def _na_obrazovce(spec, st, k):
    rohy = spec.get("rohy") or []
    r = rohy[min(max(0, k), len(rohy) - 1)] if rohy else None
    if not r:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0)
    blok = _blok(spec, st)
    w, h = blok.size
    okraj = 0.12                                   # text nevyplní obrazovku až do rohů
    zdroj = [(-w * okraj, -h * okraj), (w * (1 + okraj), -h * okraj), (w * (1 + okraj), h * (1 + okraj)), (-w * okraj, h * (1 + okraj))]
    koef = _koeficienty(r, zdroj)
    plat = blok.transform((SIRKA, VYSKA), Image.PERSPECTIVE, koef, Image.BICUBIC)
    return plat, (0, 0)


# ---------- výpočet z videa (místně, po masce osoby) ----------

def zmer_drahu_ruky(maska, od, do, fps=FPS):
    """Nejvyšší bod osoby v každém snímku úseku (px v 1080x1920), None kde osoba není. Zdvižená ruka = nejvyšší bod."""
    import numpy as np
    out = []
    for i in range(int(round(od * fps)), int(round(do * fps))):
        m = maska.mala(i)
        radky = np.nonzero((m > 128).any(axis=1))[0]
        out.append(int(radky[0]) * (VYSKA // m.shape[0]) if len(radky) else None)
    # klouzavý průměr přes 3 snímky, ať text necuká
    hladka = []
    for i in range(len(out)):
        okoli = [v for v in out[max(0, i - 1):i + 2] if v is not None]
        hladka.append(int(sum(okoli) / len(okoli)) if okoli else None)
    return hladka


def najdi_obrazovky(video, od, do, fps=FPS):
    """Tmavý čtyřúhelník (obrazovka tabletu nebo telefonu) v každém snímku úseku: 4 rohy v px 1080x1920, nebo None.

    ffmpeg dekóduje úsek zmenšený na 270x480 do roury, OpenCV hledá největší tmavou plochu se 4 rohy.
    """
    import cv2
    import numpy as np
    w, h, s = 270, 480, 4
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", "%.3f" % od, "-t", "%.3f" % (do - od), "-i", str(video),
                          "-vf", "scale=%d:%d,fps=%d" % (w, h, fps), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         stdout=subprocess.PIPE)
    out, posledni, chybi = [], None, 0
    while True:
        data = p.stdout.read(w * h)
        if len(data) < w * h:
            break
        g = np.frombuffer(data, np.uint8).reshape(h, w)
        _, tmave = cv2.threshold(cv2.GaussianBlur(g, (5, 5), 0), TMAVA_OBRAZOVKA, 255, cv2.THRESH_BINARY_INV)
        tmave = cv2.morphologyEx(tmave, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        obrysy, _ = cv2.findContours(tmave, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        nejlepsi = None
        for o in sorted(obrysy, key=cv2.contourArea, reverse=True)[:3]:
            if cv2.contourArea(o) < MIN_PODIL_OBRAZOVKY * w * h:
                break
            a = cv2.approxPolyDP(o, 0.04 * cv2.arcLength(o, True), True)
            if len(a) == 4 and cv2.isContourConvex(a):
                nejlepsi = a.reshape(4, 2)
                break
        if nejlepsi is not None:
            # pořadí rohů: levý horní, pravý horní, pravý dolní, levý dolní
            sou, roz = nejlepsi.sum(1), np.diff(nejlepsi, axis=1).ravel()
            serazene = [nejlepsi[sou.argmin()], nejlepsi[roz.argmin()], nejlepsi[sou.argmax()], nejlepsi[roz.argmax()]]
            posledni, chybi = [(int(x) * s, int(y) * s) for x, y in serazene], 0
            out.append(posledni)
        else:
            chybi += 1
            out.append(posledni if chybi <= DRZET_ROHY else None)
    p.wait()
    return out


def zmer_rozevreni(maska, od, do, cil, fps=FPS):
    """Jak daleko od spojených dlaní sahají ruce nad hlavou (px), v každém snímku úseku. Vrátí (seznam, střed dlaní x).

    Bere horních 150 px postavy (při rukou nad hlavou jsou to dlaně), krajní body vlevo a vpravo. Střed = medián
    středu dlaní v prvních 10 snímcích (dlaně spojené; OVĚŘENO 29. 10.: u Marcely 470 px, ne střed obrazu).
    Hodnota jen roste (nadpis se znovu nezavírá, když ruce klesnou). Seznam končí, když ruce odkryjí celý nadpis.
    """
    import numpy as np
    kraje = []
    for i in range(int(round(od * fps)), int(round(do * fps))):
        m = maska.mala(i)
        sk = VYSKA // m.shape[0]
        radky = np.nonzero((m > 128).any(axis=1))[0]
        if len(radky):
            pas = m[radky[0]:radky[0] + 150 // sk] > 128
            sloupce = np.nonzero(pas.any(axis=0))[0]
            kraje.append((sloupce[0] * sk, (sloupce[-1] + 1) * sk))
        else:
            kraje.append(None)
    zacatek = [(a + b) / 2 for k in kraje[:10] if k for a, b in [k]]
    stred = float(np.median(zacatek)) if zacatek else SIRKA / 2
    out, nej = [], 0.0
    for k in kraje:
        if k:
            nej = max(nej, stred - k[0], k[1] - stred)
        out.append(int(nej))
        if nej >= cil + abs(stred - SIRKA / 2):
            break
    return out, int(stred)


def dopocitej(spec, video, maska):
    """Doplní spec["draha"] nebo spec["rohy"] z hotového základu videa. Volá render po spočítání masky osoby."""
    if spec.get("pohyb") == "ruka" and maska is not None and not spec.get("draha"):
        spec["draha"] = zmer_drahu_ruky(maska, spec["od"], spec["do"])
        spec.pop("varovani", None)
    if spec.get("nastup") == "ruce" and maska is not None and not spec.get("odkryti"):
        spec["odkryti"], spec["odkryti_stred"] = zmer_rozevreni(maska, spec["od"], spec["do"], spec["sirka"] / 2 + 20)
    if spec.get("pohyb") == "obrazovka" and not spec.get("rohy"):
        spec["rohy"] = najdi_obrazovky(video, spec["od"], spec["do"])
        if any(spec["rohy"]):
            spec.pop("varovani", None)
