"""Karty slov: úvodní sekvence slovních karet (jedno až tři slova na kartu) přes ztmavený obraz.

Karty se ukazují postupně jedna za druhou, tvrdou výměnou (bez prolnutí). Každá karta má jiný řez písma,
dokola v pořadí: 1) patkové kapitálky Playfair Display Bold, 2) bezpatkové tučné kapitálky Montserrat ExtraBold,
3) patková kurzíva Instrument Serif Italic (malá písmena). Nástup karty: zvětšení z 0,85 na 1,0 za 0,25 s
a náběh průhlednosti. Po dobu prvku leží přes celý obraz švestková vrstva ("ztmavit" = její průhlednost).

Spec: {"typ": "karty_slov", "od": 0.1, "do": 3.2, "karty": ["NATOČÍM.", "CLAUDE", "stříhá."], "ztmavit": 0.55,
       "trvani_karty": 1.0 (volitelně, výchozí = (do - od) / počet karet), "zvyraznit": 1 (volitelně, index karty
       v růžové, může být i seznam indexů)}
Text leží nahoře mezi bezpečným okrajem (220 px) a horním okrajem okna obličeje (bez okna v horní třetině).
Když se nevejde, zmenšuje se písmo (150 px až 72 px) a text se zalomí na 2 řádky. Když se nevejde ani tak,
zkusí se místo pod bradou (NÁVRH), jinak zůstane nahoře s nejmenším písmem a do spec["varovani"] se zapíše proč.
"""
from PIL import Image

from ..titulky import BOK, DOLNI_OKRAJ, FPS, HORNI_OKRAJ, SIRKA, VYSKA, _vrstva_s_textem, pismo, rozdel

NASTUP_S = 0.25          # zvětšení karty z 0,85 na 1,0
NABEH_ALFA_S = 0.18      # náběh průhlednosti textu (a ztmavení u první karty)
MEZERA = 24              # odstup textu od okrajů povolené oblasti
PAD = 28                 # rezerva kolem textu na stín
REZERVA_TITULKU = 240    # NÁVRH: místo pro dvouřádkové titulky nad spodním bezpečným okrajem (záložní místo pod bradou)
MAX_RADKU = 2

VYCHOZI_STYL = {
    # řezy písma dokola podle pořadí karty; "pismena": velka / mala / jak_je
    "rezy": [
        {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "pismena": "velka"},
        {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "pismena": "velka"},
        {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "pismena": "mala"},
    ],
    "barva": (251, 246, 239),               # krém
    "barva_zvyrazneni": (212, 139, 160),    # růžová (karta v "zvyraznit")
    "stin": 130, "obrys": 0,                # jemný stín (viz titulky._vrstva_s_textem)
    "ztmaveni": (74, 51, 64),               # švestková vrstva přes celý obraz
    "ztmavit": 0.55,                        # výchozí průhlednost ztmavení, když ve spec chybí
    "velikost": 150, "min_velikost": 72, "krok": 6,
    "max_sirka": SIRKA - 2 * BOK, "radek": 1.08,
}


def _styl(styl):
    s = dict(VYCHOZI_STYL)
    s.update(styl or {})
    return s


def _ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def _clamp(x):
    return max(0.0, min(1.0, x))


def _rez(st, i):
    return st["rezy"][i % len(st["rezy"])]


def _text_karty(text, rez):
    """Text karty v písmenech podle řezu. Ruční zalomení (\\n) se dodrží."""
    t = "\n".join(" ".join(r.split()) for r in str(text).split("\n") if r.strip())
    if rez.get("pismena") == "velka":
        return t.upper()
    if rez.get("pismena") == "mala":
        return t.lower()
    return t


def _radky(text, font, max_sirka):
    """Zalomí text karty na řádky podle šířky (vyvážené dva řádky, když se nevejde na jeden)."""
    if "\n" in text:
        return text.split("\n")
    slova = text.split()
    sirky = [font.getlength(s) for s in slova]
    radky, i = [], 0
    for n in rozdel(sirky, font.getlength(" "), max_sirka):
        radky.append(" ".join(slova[i:i + n]))
        i += n
    return radky


def _zmer(text, rez, velikost, st):
    """Rozměry karty při dané velikosti písma (bez animace a bez stínu)."""
    font = pismo(rez["pismo"], velikost, rez["varianta"])
    radky = _radky(text, font, st["max_sirka"])
    asc, desc = font.getmetrics()
    vr = int((asc + desc) * st.get("radek", 1.08))
    sirky = [font.getlength(r) for r in radky]
    return {"text": text, "pismo": rez["pismo"], "varianta": rez["varianta"], "velikost": velikost,
            "radky": radky, "sirky": sirky, "radek_px": vr, "sirka": int(max(sirky)) + 1, "vyska": vr * len(radky)}


def _rozloz_kartu(text, rez, st, max_vyska):
    """Největší velikost písma (od st["velikost"] po st["min_velikost"]), při které se karta vejde na šířku,
    na nejvýš 2 řádky a do výšky max_vyska. Vrátí (rozměry, vejde_se)."""
    v = st["velikost"]
    while v >= st["min_velikost"]:
        m = _zmer(text, rez, v, st)
        if len(m["radky"]) <= MAX_RADKU and m["sirka"] <= st["max_sirka"] and m["vyska"] <= max_vyska:
            return m, True
        v -= st["krok"]
    return _zmer(text, rez, st["min_velikost"], st), False


def _rozloz_vsechny(karty, st, max_vyska):
    rozl, ok = [], True
    for i, text in enumerate(karty):
        m, vejde = _rozloz_kartu(text, _rez(st, i), st, max_vyska)
        rozl.append(m)
        ok = ok and vejde
    return rozl, ok


def pripravit(spec, styl, kontext):
    """Doplní do spec rozložení karet (spec["rozlozeni"]) a společný obdélník (x, y, sirka, vyska)."""
    st = _styl(styl)
    kontext = kontext or {}
    horni = kontext.get("horni", HORNI_OKRAJ)
    dolni = kontext.get("dolni", DOLNI_OKRAJ)
    vyska = kontext.get("vyska", VYSKA)
    sirka = kontext.get("sirka", SIRKA)
    okno = kontext.get("okno")
    karty = [_text_karty(k, _rez(st, i)) for i, k in enumerate(spec.get("karty") or [])]
    spec["varovani"] = []
    if not karty:
        spec["rozlozeni"] = []
        spec["x"], spec["y"], spec["sirka"], spec["vyska"] = sirka // 2, horni, 0, 0
        spec["varovani"].append("Prvek karty_slov nemá žádné karty.")
        return
    # kam text zkusit: 1) nahoře mezi bezpečným okrajem a obličejem (bez okna: horní třetina), 2) pod bradou (záloha)
    if okno:
        oblasti = [(horni + MEZERA, int(okno[1]) - MEZERA),
                   (int(okno[3]) + MEZERA, vyska - dolni - REZERVA_TITULKU - MEZERA)]
    else:
        oblasti = [(horni + MEZERA, vyska // 3 - MEZERA)]
    vybrane, nouze = None, None
    for y0, y1 in oblasti:
        if y1 - y0 < st["min_velikost"]:
            continue
        rozl, ok = _rozloz_vsechny(karty, st, y1 - y0)
        if ok:
            vybrane = (y0, y1, rozl)
            break
        if nouze is None:
            nouze = (y0, y1, rozl)
    if vybrane is None:
        if nouze is None:
            y0, y1 = horni + MEZERA, vyska // 3 - MEZERA
            nouze = (y0, y1, _rozloz_vsechny(karty, st, y1 - y0)[0])
        vybrane = nouze
        spec["varovani"].append("Karty slov se nevejdou mimo obličej ani s nejmenším písmem (%d px)." % st["min_velikost"])
    y0, y1, rozl = vybrane
    stred = (y0 + y1) / 2
    for r in rozl:
        r["x"] = int((sirka - r["sirka"]) / 2)
        r["y"] = max(y0, int(stred - r["vyska"] / 2))
    spec["rozlozeni"] = rozl
    spec["x"] = min(r["x"] for r in rozl)
    spec["y"] = min(r["y"] for r in rozl)
    spec["sirka"] = max(r["x"] + r["sirka"] for r in rozl) - spec["x"]
    spec["vyska"] = max(r["y"] + r["vyska"] for r in rozl) - spec["y"]


def _pripraveno(spec, styl):
    if "rozlozeni" not in spec or len(spec["rozlozeni"]) != len(spec.get("karty") or []):
        pripravit(spec, styl, {"okno": None})


def obdelnik(spec, styl):
    """Společný obdélník všech karet po animaci (bez ztmavení): (x0, y0, x1, y1)."""
    _pripraveno(spec, styl)
    return spec["x"], spec["y"], spec["x"] + spec["sirka"], spec["y"] + spec["vyska"]


def trvani_karty(spec):
    n = max(1, len(spec.get("karty") or []))
    return float(spec.get("trvani_karty") or (spec["do"] - spec["od"]) / n)


def stav(spec, t):
    """(index karty, číslo snímku nástupu nebo "s" v klidu), nebo None mimo čas prvku."""
    if not spec.get("karty") or not (spec["od"] <= t < spec["do"]):
        return None
    trv = trvani_karty(spec)
    i = min(len(spec["karty"]) - 1, int((t - spec["od"]) / trv + 1e-6))
    t_rel = t - spec["od"] - i * trv
    if t_rel < NASTUP_S:
        return (i, max(0, int(t_rel * FPS + 1e-6)))
    return (i, "s")


def _zvyraznena(spec, i):
    zv = spec.get("zvyraznit")
    if isinstance(zv, (list, tuple)):
        return i in zv
    return zv is not None and zv == i


def vykresli(spec, styl, klic):
    """Snímek pro klíč ze stav(). Se ztmavením vrátí celý snímek 1080x1920 na (0, 0), jinak jen plochu karty."""
    st = _styl(styl)
    _pripraveno(spec, styl)
    i, k = klic
    r = spec["rozlozeni"][i]
    t_rel = NASTUP_S if k == "s" else k / FPS
    mierka = 0.85 + 0.15 * _ease_out_cubic(_clamp(t_rel / NASTUP_S))
    alfa = _clamp(t_rel / NABEH_ALFA_S)
    barva = tuple(st["barva_zvyrazneni"] if _zvyraznena(spec, i) else st["barva"])
    font = pismo(r["pismo"], r["velikost"], r["varianta"])
    plocha = (r["sirka"] + 2 * PAD, r["vyska"] + 2 * PAD)
    polozky = [(PAD + (r["sirka"] - s) / 2, PAD + j * r["radek_px"], radek, barva, 1.0)
               for j, (radek, s) in enumerate(zip(r["radky"], r["sirky"]))]
    img = _vrstva_s_textem(plocha, polozky, st, font, alfa)
    sx, sy = r["x"] - PAD, r["y"] - PAD
    if mierka < 0.999:
        nw, nh = max(1, int(img.width * mierka)), max(1, int(img.height * mierka))
        cx, cy = sx + img.width / 2, sy + img.height / 2
        img = img.resize((nw, nh), Image.LANCZOS)
        sx, sy = int(cx - nw / 2), int(cy - nh / 2)
    ztmavit = float(spec.get("ztmavit", st["ztmavit"]) or 0.0)
    cast = spec.get("cast")            # "text" = jen karta (před osobu), "pozadi" = jen ztmavení (za osobu)
    if ztmavit <= 0 or cast == "text":
        return img, (int(sx), int(sy))
    # ztmavení celého obrazu: u první karty nabíhá spolu s textem, dál drží, na konci prvku zmizí tvrdě
    a = ztmavit * (alfa if i == 0 else 1.0)
    snimek = Image.new("RGBA", (SIRKA, VYSKA), tuple(st["ztmaveni"]) + (int(round(255 * a)),))
    if cast != "pozadi":
        snimek.alpha_composite(img, (max(0, sx), max(0, sy)), (max(0, -sx), max(0, -sy)))
    return snimek, (0, 0)
