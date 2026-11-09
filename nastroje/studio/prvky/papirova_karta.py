"""Prvek „papírová karta“: kus Instagramu (profil, nálepka s otázkou, komentáře) jako papír, se kterým osoba hraje.

Zadání Marcely 29. 10. 2026. Karty reagují
na rekvizity: nůžky kartu přestřihnou a půlky spadnou, fén nálepku odfoukne, komentáře spadnou do klína.
Studio obraz nevymýšlí: osoba udělá gesto s opravdovou rekvizitou a karta v daný čas zareaguje.

Spec v osa["prvky"]:
  {"typ": "papirova_karta", "od": 0.3, "do": 3.6, "druh": "profil",
   "jmeno": "digitalni_mama_marcela", "popis": "Claude a reely | máma", "cisla": [["145", "příspěvků"], ...],
   "konec": "strih", "cas_konce": 2.9}
  druh       "profil" (hlavička profilu s čísly), "otazka" (nálepka Otázka s psaním po písmenech),
             "komentar" (jeden nebo víc komentářů pod sebou, každý spadne shora ve svém čase)
  jmeno      uživatelské jméno (bez @)
  foto       volitelně obrázek profilu v kontext["podklady"] (jinak kroužek s počátečním písmenem)
  popis      profil: řádek pod čísly
  cisla      profil: 3 dvojice [číslo, popisek]
  text       otázka: text, který se napíše po písmenech; pole = šedý řádek pod ním (výchozí „Napiš odpověď“)
  texty      komentar: seznam textů komentářů; casy = kdy každý spadne (výchozí po 0,4 s od začátku)
  konec      "strih"  karta se v cas_konce rozdělí na dvě půlky (svislý řez v strih_x, 0 až 1, výchozí 0,5)
                      a ty odpadnou dolů z obrazu; nůžky drží osoba
             "odfouknuti"  karta se zachvěje a odletí do strany (smer "vlevo" / "vpravo"), třepotá se
             "dopad"  karta spadne do klína (y_dopad, výchozí 1560), zploští se jako ležící papír a zůstane do „do“
             "zmizi"  jen zmizí (výchozí)
  cas_konce  čas v reelu, kdy se konec spustí (výchozí 0,9 s před „do“); u střihu = chvíle, kdy se nůžky sevřou
  y          volitelně horní okraj karty (jinak nad obličejem, pod horním bezpečným pásmem)

Vzhled (ODHAD ze snímků): bílý papír se zaoblenými rohy, jemná zrnitost, měkký stín, písmo jako Instagram
(Mulish, OFL). Obličej se nezakrývá, karta se položí nad hlavu; když se nevejde, zmenší se až na 640 px.
Zvuky (nůžky, fén, šustnutí papíru) prvek nemíchá, viz zvuky(spec).

Klíče stav(): číslo snímku při animaci, "s" v klidu, None mimo čas.
"""
import math
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, pismo

VYCHOZI_STYL = {
    "pismo": "Mulish-wght.ttf",
    "papir": (253, 252, 250),
    "inkoust": (24, 24, 28),
    "seda": (142, 142, 148),
    "pole": (239, 239, 241),
    "modra": (0, 149, 246),       # kurzor a tlačítka (barva Instagramu, ODHAD)
    "srdce": (237, 73, 86),
    "avatar": (212, 139, 160),    # růžová Marcela, když chybí fotka
    "sirka": 820,
    "min_sirka": 640,
    "rohy": 30,
    "stin": 120,
}

NASTUP_S = 0.35            # pop nebo pád shora
VYSTUP_S = 0.25            # zmizení
CHVENI_S = 0.30            # třes před střihem nebo odfouknutím
PISMENA_ZA_S = 16          # psaní otázky
KURZOR_S = 0.6             # kurzor bliká ještě po dopsání
MEZERA_KOMENTARU = 22
MEZERA_OKOLO = 40          # odstup od obličeje
LEM = 50                   # průhledný okraj obrázku karty (stín)
G = 2600                   # gravitace (px/s²) pro padající půlky
DOPAD_S = 0.55
VYCHOZI_Y = HORNI_OKRAJ + 60


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _ease_out_back(p, s=1.6):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _klic_stylu(styl):
    return tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in styl.items()))


def _protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _f(st, velikost, varianta="Regular"):
    return pismo(st["pismo"], velikost, varianta)


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
    return radky or [""]


# ---------- kreslení papíru ----------

def _papir(w, h, st, seed=7):
    """Bílý papír se zrnitostí a zaoblenými rohy, se stínem v lemu LEM. Vrátí (obrázek, (ox, oy) papíru v obrázku)."""
    W, H = w + 2 * LEM, h + 2 * LEM
    tvar = Image.new("L", (w, h), 0)
    ImageDraw.Draw(tvar).rounded_rectangle([0, 0, w - 1, h - 1], st["rohy"], fill=255)
    zrno = Image.effect_noise((w, h), 9).point(lambda v: 255 - (255 - v) // 12)
    papir = Image.merge("RGB", [ImageChops.multiply(Image.new("L", (w, h), c), zrno) for c in st["papir"]])
    papir = papir.convert("RGBA")
    papir.putalpha(tvar)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stin = Image.new("L", (W, H), 0)
    stin.paste(tvar.point(lambda v: v * st["stin"] // 255), (LEM, LEM + 10))
    out.putalpha(stin.filter(ImageFilter.GaussianBlur(18)))
    out.alpha_composite(papir, (LEM, LEM))
    return out, (LEM, LEM)


def _avatar(prumer, jmeno, foto, st):
    a = Image.new("RGBA", (prumer, prumer), (0, 0, 0, 0))
    kruh = Image.new("L", (prumer * 4, prumer * 4), 0)
    ImageDraw.Draw(kruh).ellipse([0, 0, prumer * 4 - 1, prumer * 4 - 1], fill=255)
    kruh = kruh.resize((prumer, prumer), Image.LANCZOS)
    if foto:
        img = ImageOps.fit(Image.open(foto).convert("RGB"), (prumer, prumer), Image.LANCZOS)
        a.paste(img, (0, 0), kruh)
        return a
    a.paste(Image.new("RGB", (prumer, prumer), tuple(st["avatar"])), (0, 0), kruh)
    f = _f(st, int(prumer * 0.48), "Bold")
    znak = (jmeno or "?")[0].upper()
    ImageDraw.Draw(a).text((prumer / 2, prumer / 2), znak, font=f, fill=(255, 255, 255), anchor="mm")
    return a


@lru_cache(maxsize=32)
def _profil(jmeno, popis, cisla, foto, w, st_klic):
    st = dict(st_klic)
    m = w / 820
    h = int(300 * m)
    img, (ox, oy) = _papir(w, h, st)
    d = ImageDraw.Draw(img)
    s = lambda v: int(round(v * m))
    d.text((ox + s(36), oy + s(52)), "‹", font=_f(st, s(54)), fill=st["inkoust"], anchor="lm")
    d.text((ox + s(90), oy + s(52)), jmeno, font=_f(st, s(36), "Bold"), fill=st["inkoust"], anchor="lm")
    d.text((ox + w - s(40), oy + s(46)), "···", font=_f(st, s(36), "Bold"), fill=st["inkoust"], anchor="rm")
    av = _avatar(s(130), jmeno, foto, st)
    img.alpha_composite(av, (ox + s(36), oy + s(104)))
    x0, sloupec = ox + s(220), (w - s(250)) / 3
    for i, (cislo, nazev) in enumerate(cisla[:3]):
        cx = int(x0 + sloupec * (i + 0.5))
        d.text((cx, oy + s(150)), cislo, font=_f(st, s(36), "Bold"), fill=st["inkoust"], anchor="mm")
        d.text((cx, oy + s(192)), nazev, font=_f(st, s(26)), fill=st["inkoust"], anchor="mm")
    if popis:
        d.text((ox + s(36), oy + s(266)), popis, font=_f(st, s(28)), fill=st["inkoust"], anchor="lm")
    return img


def _otazka_rozmer(text, w, st):
    m = w / 820
    f = _f(st, int(56 * m), "SemiBold")
    radky = _zalom(text, f, w - int(100 * m))
    return f, radky, int((150 + 72 * len(radky) + 120) * m)


@lru_cache(maxsize=256)
def _otazka(text, pole, jmeno, foto, w, napsano, kurzor, st_klic):
    """Nálepka s otázkou: kroužek profilu přesahuje nahoru, text (prvních `napsano` znaků), šedé pole."""
    st = dict(st_klic)
    m = w / 820
    s = lambda v: int(round(v * m))
    f, radky, h = _otazka_rozmer(text, w, st)
    karta, (ox, oy) = _papir(w, h, st)
    img = Image.new("RGBA", (karta.width, karta.height + s(60)), (0, 0, 0, 0))
    img.alpha_composite(karta, (0, s(60)))
    oy += s(60)
    av = _avatar(s(110), jmeno, foto, st)
    ram = Image.new("RGBA", (s(126), s(126)), (0, 0, 0, 0))
    ImageDraw.Draw(ram).ellipse([0, 0, s(125), s(125)], fill=tuple(st["papir"]) + (255,))
    ram.alpha_composite(av, (s(8), s(8)))
    img.alpha_composite(ram, (ox + w // 2 - s(63), oy - s(63)))
    d = ImageDraw.Draw(img)
    zbyva = napsano
    y = oy + s(110)
    posledni = (ox + w // 2, y)
    for r in radky:
        cast = r[:max(0, zbyva)]
        zbyva -= len(r) + 1
        sirka_radku = f.getlength(r)
        x = ox + (w - sirka_radku) / 2
        if cast:
            d.text((x, y), cast, font=f, fill=st["inkoust"], anchor="lt")
        if zbyva >= -len(r) - 1 and cast:
            posledni = (x + f.getlength(cast) + s(4), y)
        y += s(72)
    if kurzor:
        d.rectangle([posledni[0], posledni[1] + s(4), posledni[0] + s(5), posledni[1] + s(62)], fill=st["modra"])
    py = oy + h - s(110)
    d.rounded_rectangle([ox + s(60), py, ox + w - s(60), py + s(76)], s(20), fill=st["pole"])
    d.text((ox + w / 2, py + s(38)), pole, font=_f(st, s(30), "SemiBold"), fill=st["seda"], anchor="mm")
    return img


def _komentar_rozmer(text, w, st):
    m = w / 820
    f = _f(st, int(32 * m))
    radky = _zalom(text, f, w - int(220 * m))
    return f, radky, int((110 + 42 * len(radky)) * m)


@lru_cache(maxsize=64)
def _komentar(jmeno, text, foto, w, st_klic):
    st = dict(st_klic)
    m = w / 820
    s = lambda v: int(round(v * m))
    f, radky, h = _komentar_rozmer(text, w, st)
    img, (ox, oy) = _papir(w, h, st)
    d = ImageDraw.Draw(img)
    img.alpha_composite(_avatar(s(64), jmeno, foto, st), (ox + s(28), oy + s(26)))
    fj = _f(st, s(28), "Bold")
    d.text((ox + s(110), oy + s(30)), jmeno, font=fj, fill=st["inkoust"], anchor="lt")
    d.text((ox + s(122) + fj.getlength(jmeno), oy + s(30)), "1 h", font=_f(st, s(26)), fill=st["seda"], anchor="lt")
    y = oy + s(66)
    for r in radky:
        d.text((ox + s(110), y), r, font=f, fill=st["inkoust"], anchor="lt")
        y += s(42)
    d.text((ox + s(110), y + s(4)), "Odpovědět", font=_f(st, s(24), "SemiBold"), fill=st["seda"], anchor="lt")
    # srdíčko vpravo (dva kruhy a trojúhelník)
    cx, cy, r = ox + w - s(54), oy + s(58), s(11)
    d.ellipse([cx - 2 * r, cy - r, cx, cy + r], fill=st["srdce"])
    d.ellipse([cx, cy - r, cx + 2 * r, cy + r], fill=st["srdce"])
    d.polygon([(cx - 2 * r + 1, cy + 3), (cx + 2 * r - 1, cy + 3), (cx, cy + 2.3 * r)], fill=st["srdce"])
    return img


# ---------- příprava ----------

def _foto(spec, kontext):
    if not spec.get("foto"):
        return None
    from pathlib import Path
    p = Path(spec["foto"])
    if not p.is_absolute() and kontext.get("podklady"):
        p = Path(kontext["podklady"]) / p
    if not p.exists():
        raise ValueError("Papírová karta: obrázek profilu %s nenalezen." % p)
    return str(p)


def _vyska(spec, st, w):
    druh = spec["druh"]
    if druh == "profil":
        return int(300 * w / 820)
    if druh == "otazka":
        return _otazka_rozmer(spec["text"], w, st)[2] + int(60 * w / 820)
    vys = [_komentar_rozmer(t, w, st)[2] for t in spec["texty"]]
    return sum(vys) + MEZERA_KOMENTARU * (len(vys) - 1)


def pripravit(spec, styl, kontext):
    """Zkontroluje obsah, zvolí šířku a polohu nad obličejem a časy konce."""
    st = _styl(styl)
    druh = spec.setdefault("druh", "profil")
    if druh not in ("profil", "otazka", "komentar"):
        raise ValueError("Papírová karta: druh musí být profil, otazka nebo komentar, zadáno %r." % druh)
    spec.setdefault("jmeno", "digitalni_mama_marcela")
    if druh == "profil":
        spec["cisla"] = [list(map(str, c)) for c in (spec.get("cisla") or [["145", "příspěvků"], ["104 tis.", "sledujících"], ["6", "sleduji"]])]
        if len(spec["cisla"]) != 3:
            raise ValueError("Papírová karta (profil): cisla musí mít 3 dvojice.")
    elif druh == "otazka":
        if not str(spec.get("text", "")).strip():
            raise ValueError("Papírová karta (otázka): chybí text.")
        spec.setdefault("pole", "Napiš odpověď")
    else:
        texty = [str(t).strip() for t in spec.get("texty") or [] if str(t).strip()]
        if not texty:
            raise ValueError("Papírová karta (komentář): zadej aspoň jeden text v texty.")
        spec["texty"] = texty
        casy = spec.get("casy") or [spec["od"] + 0.4 * i for i in range(len(texty))]
        spec["casy_rel"] = [max(0.0, c - spec["od"]) for c in casy]
    konec = spec.setdefault("konec", "zmizi")
    if konec not in ("strih", "odfouknuti", "dopad", "zmizi"):
        raise ValueError("Papírová karta: konec musí být strih, odfouknuti, dopad nebo zmizi, zadáno %r." % konec)
    spec["konec_rel"] = (spec.get("cas_konce") if spec.get("cas_konce") is not None else spec["do"] - 0.9) - spec["od"]
    spec["fotka"] = _foto(spec, kontext)

    okno = kontext.get("okno")
    w = int(st["sirka"])
    while True:
        h = _vyska(spec, st, w)
        y = spec["y"] if spec.get("y") is not None else VYCHOZI_Y
        x = (SIRKA - w) // 2
        obd = (x, y, x + w, y + h)
        if spec.get("y") is not None or not okno or not _protina(obd, (okno[0] - MEZERA_OKOLO, okno[1] - MEZERA_OKOLO,
                                                                       okno[2] + MEZERA_OKOLO, okno[3] + MEZERA_OKOLO)):
            break
        if w > st["min_sirka"]:
            w = max(int(st["min_sirka"]), w - 60)
            continue
        spec["varovani"] = "karta se nevejde nad obličej ani zmenšená na %d px, zakrývá část hlavy" % w
        break
    spec.update({"x": x, "y": y, "sirka": w, "vyska": h})
    spec.setdefault("y_dopad", VYSKA - DOLNI_OKRAJ + 110)
    spec.setdefault("smer", "vpravo")
    spec.setdefault("strih_x", 0.5)


def zvuky(spec):
    """Kdy a jaký zvuk by k prvku patřil (hlavní program je zatím nemíchá: zvuky nůžek a fénu ve studiu nejsou)."""
    jaky = {"strih": "nuzky", "odfouknuti": "fen", "dopad": "papir"}.get(spec.get("konec"))
    return [(spec["od"] + spec["konec_rel"], jaky)] if jaky else []


# ---------- čas ----------

def _konec_animace(spec):
    """Kdy (od začátku prvku) je karta zase v klidu nebo pryč."""
    k = spec["konec_rel"]
    return {"strih": k + 1.4, "odfouknuti": k + 1.2, "dopad": k + DOPAD_S + 0.25, "zmizi": k + VYSTUP_S}[spec["konec"]]


def stav(spec, t):
    if t < spec["od"] or t >= spec["do"]:
        return None
    t_rel = t - spec["od"]
    snimek = int(round(t * FPS))
    k = spec["konec_rel"]
    if spec["konec"] in ("strih", "odfouknuti", "zmizi") and t_rel >= _konec_animace(spec):
        return None
    if t_rel < NASTUP_S:
        return snimek
    if spec["druh"] == "otazka" and t_rel < NASTUP_S + len(spec["text"]) / PISMENA_ZA_S + KURZOR_S:
        return snimek
    if spec["druh"] == "komentar" and t_rel < max(spec["casy_rel"]) + NASTUP_S:
        return snimek
    if t_rel >= k - CHVENI_S:
        return snimek if t_rel < _konec_animace(spec) else "dopad"
    return "s"


# ---------- kreslení ----------

def _obraz_karty(spec, st_klic, t_rel):
    """Celá karta v klidu (pro komentáře seznam karet s posunem y)."""
    st = dict(st_klic)
    w = spec["sirka"]
    if spec["druh"] == "profil":
        return [(_profil(spec["jmeno"], spec.get("popis", ""), tuple(map(tuple, spec["cisla"])), spec["fotka"], w, st_klic), 0, 0.0)]
    if spec["druh"] == "otazka":
        zacatek = NASTUP_S
        n = len(spec["text"]) if t_rel is None else int(_clamp((t_rel - zacatek) * PISMENA_ZA_S, 0, len(spec["text"])))
        dopsano_rel = zacatek + len(spec["text"]) / PISMENA_ZA_S
        kurzor = t_rel is not None and t_rel < dopsano_rel + KURZOR_S and int(t_rel * 3) % 2 == 0
        return [(_otazka(spec["text"], spec["pole"], spec["jmeno"], spec["fotka"], w, n, kurzor, st_klic), 0, 0.0)]
    out, y = [], 0
    for i, text in enumerate(spec["texty"]):
        img = _komentar(spec["jmeno"], text, spec["fotka"], w, st_klic)
        out.append((img, y, spec["casy_rel"][i]))
        y += img.height - 2 * LEM + MEZERA_KOMENTARU
    return out


def _poloz(platno, img, cx, cy, uhel=0.0, sx=1.0, sy=1.0, alfa=1.0):
    if sx != 1.0 or sy != 1.0:
        img = img.resize((max(1, int(img.width * sx)), max(1, int(img.height * sy))), Image.BICUBIC)
    if uhel:
        img = img.rotate(uhel, resample=Image.BICUBIC, expand=True)
    if alfa < 1.0:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alfa)))
    platno.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2))) if (
        -img.width < cx < SIRKA + img.width and -img.height < cy < VYSKA + img.height) else None


def _pulky(img, strih_x):
    """Rozdělí kartu svislým řezem (lehce klikatým, jako od nůžek) na levou a pravou půlku."""
    w, h = img.size
    rez = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rez)
    x = LEM + (w - 2 * LEM) * strih_x
    rnd = random.Random(11)
    body = [(x + rnd.uniform(-4, 4), y) for y in range(0, h + 24, 24)]
    d.polygon([(0, 0)] + body + [(0, h)], fill=255)
    leva = img.copy()
    leva.putalpha(ImageChops.multiply(img.getchannel("A"), rez))
    prava = img.copy()
    prava.putalpha(ImageChops.multiply(img.getchannel("A"), ImageChops.invert(rez)))
    return leva, prava, x


def vykresli(spec, styl, klic):
    st = _styl(styl)
    st_klic = _klic_stylu(st)
    t_rel = (klic / FPS - spec["od"]) if isinstance(klic, int) else None
    platno = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
    k, konec = spec["konec_rel"], spec["konec"]
    if klic == "dopad":
        t_rel = _konec_animace(spec)
    karty = _obraz_karty(spec, st_klic, None if klic in ("s", "dopad") else t_rel)
    cx0 = spec["x"] + spec["sirka"] / 2
    for i, (img, dy, cas) in enumerate(karty):
        cy0 = spec["y"] + dy - LEM + img.height / 2
        tl = None if t_rel is None else t_rel - cas
        if tl is not None and tl < 0:
            continue
        # nástup: pop (profil, otázka), pád shora (komentáře)
        sx = sy = 1.0
        cx, cy, uhel, alfa = cx0, cy0, 0.0, 1.0
        if tl is not None and tl < NASTUP_S:
            p = tl / NASTUP_S
            if spec["druh"] == "komentar":
                cy = cy0 - 260 * (1 - _ease_out_back(p, 1.2))
                uhel = 6 * (1 - p) * (1 if i % 2 else -1)
                alfa = _clamp(p * 2.5)
            else:
                sx = sy = 0.6 + 0.4 * _ease_out_back(p)
                alfa = _clamp(p * 2.5)
        if t_rel is not None and t_rel >= k - CHVENI_S:
            dt = t_rel - k
            smer = -1 if spec["smer"] == "vlevo" else 1
            if dt < 0 and konec in ("strih", "odfouknuti"):
                faze = (t_rel * FPS) % 2
                uhel += (1.4 if faze else -1.4) * (1 if konec == "odfouknuti" else 0.5)
                cx += (2 if faze else -2) * (konec == "strih")
            elif konec == "strih" and dt >= 0:
                leva, prava, rx = _pulky(img, spec["strih_x"])
                for kus, s in ((leva, -1), (prava, 1)):
                    _poloz(platno, kus, cx + s * (40 + 170 * dt), cy - 90 * dt + 0.5 * G * dt * dt,
                           uhel=-s * (35 * dt + 80 * dt * dt) + (i * 4), alfa=_clamp(1.4 - dt))
                continue
            elif konec == "odfouknuti" and dt >= 0:
                cx += smer * (180 * dt + 1500 * dt * dt)
                cy += -260 * dt + 40 * math.sin(16 * dt)
                uhel += -smer * (30 * dt + 14 * math.sin(20 * dt))
                sx = 1 - 0.4 * _clamp(dt * 2) * abs(math.sin(9 * dt + 0.6))
                sy = 1 - 0.15 * _clamp(dt * 2)
            elif konec == "dopad" and dt >= 0:
                p = _clamp(dt / DOPAD_S)
                cil = spec["y_dopad"] + i * 70
                cy = cy0 + (cil - cy0) * (p * p if p < 1 else 1) - (18 * math.sin(math.pi * _clamp((dt - DOPAD_S) / 0.25)) if p >= 1 else 0)
                cx = cx0 + (i * 2 - 1) * 60 * p
                uhel = (8 if i % 2 else -9) * p
                sy = 1 - 0.45 * _ease_out_cubic(p)        # leží: zploštělý papír
            elif konec == "zmizi" and dt >= 0:
                alfa = _clamp(1 - dt / VYSTUP_S)
        _poloz(platno, img, cx, cy, uhel, sx, sy, alfa)
    box = platno.getbbox()
    if not box:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0)
    return platno.crop(box), (box[0], box[1])


def obdelnik(spec, styl):
    return (spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"])
