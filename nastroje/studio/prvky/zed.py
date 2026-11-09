"""Instagram zeď: obálky reelů se promění v mřížku profilu na zdi za osobou.

Zadání Marcely (20. 10. 2026, nápad): její obálky reelů tvoří mřížku jako na profilu Instagramu: 3 sloupce dlaždic
3:4 s mezerou 3 px, lehce ztlumené (jas 0,8, sytost 0,85), aby seděly v pokoji. Sloupce vyjedou zdola (zpoza
osoby) po jednom (každý o 0,05 s později, 0,8 s, zpomalení na konci), pak se mřížka pomalu posouvá nahoru jako
feed (190 px/s), na konci sloupce klesnou zpátky dolů (0,35 s, v opačném pořadí) a je vidět čistý pokoj.

Mřížka pokrývá CELÝ obraz za osobou: prvek má za_hlavou=True, Kreslic jeho průhlednost vynásobí (1 − maska osoby),
takže osoba zůstává před zdí. Volitelně spec["obdelnik_zdi"] = [x0, y0, x1, y1] omezí mřížku jen na ten obdélník
(mimo něj se nekreslí; nábytek se zatím neřeší). Měkký stín osoby na mřížce vynechán (maska to neumí); místo něj
jemné ztmavení okrajů mřížky (viněta 10 %) a tenký téměř černý proužek mezi dlaždicemi. Titulky reelu zůstávají
(prvek je neschovává, kreslí se nad zdí i nad osobou).

Spec v osa["prvky"]:
  {"typ": "zed", "od": 2.0, "do": 6.0, "soubory": ["obalka-1.jpg", ...],
   "sloupce": 3, "posun_px_s": 190, "vyrez": "nahore", "obdelnik_zdi": [0, 0, 1080, 1920]}
  soubory       4 až 12 názvů ve složce kontext["podklady"] nebo absolutních cest (PNG, JPG, WEBP); méně než
                9 obálek se opakuje do zaplnění (dlaždice po řádcích: i-tá dlaždice = obálka i mod počet)
  sloupce       volitelné, 2 až 6 (výchozí 3)
  posun_px_s    volitelné, rychlost posunu feedu nahoru v px/s (výchozí 190 ze stylu, 0 = stojí)
  vyrez         volitelné, odkud se vysoká obálka 9:16 ořezává na 3:4: "nahore" (výchozí, střed výřezu ve 42 %
                výšky obálky, obličej a nadpis na obálce bývají nahoře) nebo "stred"
  obdelnik_zdi  volitelné [x0, y0, x1, y1] v px obrazu; bez něj celý obraz

Vzhled: VYCHOZI_STYL přepíše styl["zed"] ze slovníku vzhledu (titulky.STYLY), posun_px_s pak klíč ve spec.

Po pripravit() má spec navíc: cesty (vyřešené cesty obálek), sloupce, dlazdice_sirka, dlazdice_vyska, dlazdice_x
(x levého okraje každého sloupce v px obrazu), posun_px_s, vyrez, x, y, sirka, vyska (celý obraz nebo obdélník
zdi), za_hlavou=True, pres_oblicej=True (prvek je za osobou, kontrola umístění ho neposuzuje).

stav(spec, t): None mimo čas, jinak číslo snímku od začátku (mřížka se hýbe každý snímek).
vykresli(spec, styl, klic): (RGBA obrázek celé plochy mřížky, (x, y)). Rychlost: pro každý sloupec se jednou
sestaví vysoká „páska“ (dlaždice pod sebou, opakované, s mezerami, barevně ztlumené, s vodorovnou vinětou) jako
pole numpy v lru_cache; na snímku se jen vyřízne posunutý výřez každého sloupce, sloupce se posunou podle nástupu
a odchodu a přidá se svislá viněta na horním a spodním pásu. Měření rychlosti: viz test a zpráva ve
vysledky-testu/.
"""
import math
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

from ..titulky import FPS, SIRKA, VYSKA

POMER_DLAZDICE = 4 / 3            # výška / šířka dlaždice (3:4 jako mřížka profilu Instagramu)
MIN_SOUBORU, MAX_SOUBORU = 4, 12
MIN_SLOUPCU, MAX_SLOUPCU = 2, 6
VYCHOZI_SLOUPCU = 3
PODIL_VYREZU = {"nahore": 0.42, "stred": 0.5}   # kde na výšce obálky leží střed výřezu 3:4
PRIPONY = {".png", ".jpg", ".jpeg", ".webp"}
VINETA_PODIL = 0.25               # viněta sahá od každého okraje do 25 % šířky a výšky plochy
MIN_ODCHOD_SLOUPCE_S = 0.12       # nejkratší pád jednoho sloupce při odchodu
MIN_ROZMER_ZDI = 120              # obdélník zdi aspoň takhle široký a vysoký
MIN_SIRKA_DLAZDICE = 24

VYCHOZI_STYL = {
    "mezera": 3,                     # px mezi dlaždicemi
    "jas": 0.8,                      # ztlumení dlaždic, aby seděly v pokoji
    "sytost": 0.85,
    "kontrast": 0.95,
    "vineta": 0.10,                  # ztmavení okrajů mřížky (0 = žádné)
    "nastup_s": 0.8,                 # vyjetí jednoho sloupce zdola
    "rozestup_s": 0.05,              # každý další sloupec o tolik později
    "odchod_s": 0.35,                # pád všech sloupců dolů na konci
    "posun_px_s": 190,               # posun feedu nahoru
    "barva_mezery": (12, 12, 12),    # téměř černý proužek mezi dlaždicemi
}
VE_SPEC = ("posun_px_s",)           # klíče vzhledu, které smí přepsat spec


# ---------------------------------------------------------------- styl

def _hash(hodnota):
    if isinstance(hodnota, (list, tuple)):
        return tuple(_hash(h) for h in hodnota)
    return hodnota


def _styl(spec, styl):
    """Sloučený vzhled: výchozí ← styl["zed"] ze vzhledu ← posun_px_s ve spec."""
    st = dict(VYCHOZI_STYL)
    if styl:
        st.update({k: styl[k] for k in VYCHOZI_STYL if k in styl})
    if spec:
        st.update({k: spec[k] for k in VE_SPEC if k in spec and spec[k] is not None})
    return st


def _styl_klic(st):
    return tuple((k, _hash(st[k])) for k in sorted(VYCHOZI_STYL))


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


# ---------------------------------------------------------------- soubory

def _normalizuj(nazev):
    """Název pro porovnání: háčky v jednom zápisu (Mac ukládá NFD), pevné mezery jako obyčejné."""
    return unicodedata.normalize("NFC", nazev).replace(" ", " ").replace(" ", " ").casefold()


def najdi_soubor(nazev, spec, kontext):
    """Cesta k obálce: absolutní, nebo název ve složce podkladů. Chybějící soubor = FileNotFoundError česky."""
    cas = spec.get("od", 0)
    if not nazev or not isinstance(nazev, str):
        raise FileNotFoundError("Instagram zeď v čase %.1f s má v klíči \"soubory\" prázdný název." % cas)
    kandidati = []
    p = Path(nazev).expanduser()
    if p.is_absolute():
        kandidati.append(p)
    else:
        podklady = kontext.get("podklady") if kontext else None
        if podklady:
            kandidati.append(Path(podklady) / nazev)
        kandidati.append(Path(nazev))
    for k in list(kandidati):
        if not k.is_file() and k.parent.is_dir():
            cil = _normalizuj(k.name)
            for s in k.parent.iterdir():
                if _normalizuj(s.name) == cil:
                    kandidati.insert(0, s)
                    break
    for k in kandidati:
        if k.is_file():
            if k.suffix.lower() not in PRIPONY:
                raise ValueError("Instagram zeď umí jen PNG, JPG a WEBP. Obálka %s má jinou příponu (HEIC převeď "
                                 "na JPG v Náhledu nebo ve Fotkách)." % k.name)
            return k.resolve()
    hledano = ", ".join(str(k) for k in kandidati)
    raise FileNotFoundError("Obálka pro Instagram zeď \"%s\" (čas %.1f s) nebyla nalezena. Hledal jsem: %s. Ulož ji "
                            "do složky podkladů nebo zapiš celou cestu." % (nazev, cas, hledano))


# ---------------------------------------------------------------- rozhraní prvku

def pripravit(spec, styl, kontext):
    """Najde obálky, spočítá dlaždice a plochu zdi (celý obraz nebo obdelnik_zdi). Prvek jde vždy za osobu."""
    kontext = kontext or {}
    cas = spec.get("od", 0)
    soubory = spec.get("soubory")
    if not isinstance(soubory, (list, tuple)) or not soubory:
        raise ValueError("Instagram zeď v čase %.1f s potřebuje klíč \"soubory\" se seznamem %d až %d obálek."
                         % (cas, MIN_SOUBORU, MAX_SOUBORU))
    if len(soubory) < MIN_SOUBORU:
        raise ValueError("Instagram zeď v čase %.1f s má %d obálek, potřebuje aspoň %d." % (cas, len(soubory), MIN_SOUBORU))
    if len(soubory) > MAX_SOUBORU:
        raise ValueError("Instagram zeď v čase %.1f s má %d obálek, nejvíc jich smí být %d." % (cas, len(soubory), MAX_SOUBORU))
    spec["cesty"] = [str(najdi_soubor(n, spec, kontext)) for n in soubory]

    sloupce = int(spec.get("sloupce") or VYCHOZI_SLOUPCU)
    if not MIN_SLOUPCU <= sloupce <= MAX_SLOUPCU:
        raise ValueError("Instagram zeď v čase %.1f s: klíč \"sloupce\" musí být %d až %d, je %d."
                         % (cas, MIN_SLOUPCU, MAX_SLOUPCU, sloupce))
    spec["sloupce"] = sloupce
    if spec.get("vyrez") not in PODIL_VYREZU:
        spec["vyrez"] = "nahore"
    st = _styl(spec, styl)
    posun = float(st["posun_px_s"])
    if posun < 0:
        raise ValueError("Instagram zeď v čase %.1f s: \"posun_px_s\" nesmí být záporné (0 = mřížka stojí)." % cas)
    spec["posun_px_s"] = posun
    spec.pop("varovani", None)

    sirka_platna = int(kontext.get("sirka", SIRKA))
    vyska_platna = int(kontext.get("vyska", VYSKA))
    zed = spec.get("obdelnik_zdi")
    if zed is not None:
        if not isinstance(zed, (list, tuple)) or len(zed) != 4:
            raise ValueError("Instagram zeď v čase %.1f s: \"obdelnik_zdi\" má být [x0, y0, x1, y1] v px obrazu." % cas)
        x0, y0 = max(0, int(round(zed[0]))), max(0, int(round(zed[1])))
        x1, y1 = min(sirka_platna, int(round(zed[2]))), min(vyska_platna, int(round(zed[3])))
        if x1 - x0 < MIN_ROZMER_ZDI or y1 - y0 < MIN_ROZMER_ZDI:
            raise ValueError("Instagram zeď v čase %.1f s: \"obdelnik_zdi\" %s je moc malý nebo leží mimo obraz "
                             "(aspoň %d × %d px uvnitř 0 až %d × %d)." % (cas, list(zed), MIN_ROZMER_ZDI, MIN_ROZMER_ZDI,
                                                                           sirka_platna, vyska_platna))
        spec["obdelnik_zdi"] = [x0, y0, x1, y1]
    else:
        x0, y0, x1, y1 = 0, 0, sirka_platna, vyska_platna
    spec["x"], spec["y"], spec["sirka"], spec["vyska"] = x0, y0, x1 - x0, y1 - y0

    mez = int(st["mezera"])
    w = (spec["sirka"] - (sloupce - 1) * mez) // sloupce
    if w < MIN_SIRKA_DLAZDICE:
        raise ValueError("Instagram zeď v čase %.1f s: na %d sloupců je plocha %d px moc úzká." % (cas, sloupce, spec["sirka"]))
    h = int(round(w * POMER_DLAZDICE))
    okraj_vlevo = (spec["sirka"] - (sloupce * w + (sloupce - 1) * mez)) // 2
    spec["dlazdice_sirka"], spec["dlazdice_vyska"] = int(w), int(h)
    spec["dlazdice_x"] = [int(x0 + okraj_vlevo + c * (w + mez)) for c in range(sloupce)]
    spec["za_hlavou"] = True        # mřížka jde za osobu (maska), i když hlava sahá k hornímu okraji
    spec["pres_oblicej"] = True     # je za osobou záměrně, kontrola umístění ji nemá hlásit
    return None


def stav(spec, t):
    """Číslo snímku od začátku prvku (mřížka se hýbe každý snímek), None mimo čas."""
    if t < spec["od"] or t >= spec["do"]:
        return None
    return int(math.floor((t - spec["od"]) * FPS + 1e-6))


def obdelnik(spec, styl):
    """Celá plocha mřížky (celý obraz nebo obdélník zdi)."""
    x, y = int(spec["x"]), int(spec["y"])
    return x, y, x + int(spec["sirka"]), y + int(spec["vyska"])


# ---------------------------------------------------------------- animace

def _ease_out_cubic(p):
    return 1.0 - (1.0 - p) ** 3


def _casy_odchodu(st, sloupce):
    """(rozestup, délka pádu jednoho sloupce) tak, aby poslední sloupec dopadl přesně na konci prvku."""
    odchod = max(0.05, float(st["odchod_s"]))
    rozestup = max(0.0, float(st["rozestup_s"]))
    pad = odchod - (sloupce - 1) * rozestup
    nejmene = min(MIN_ODCHOD_SLOUPCE_S, odchod)
    if pad < nejmene:
        pad = nejmene
        rozestup = (odchod - pad) / max(1, sloupce - 1)
    return rozestup, pad


def nastup_sloupce(c, t_rel, st):
    """Jak moc je sloupec c vyjetý nahoru: 0 = celý dole (mimo obraz), 1 = na místě. Zpomalení na konci."""
    p = (t_rel - c * float(st["rozestup_s"])) / max(1e-6, float(st["nastup_s"]))
    return _ease_out_cubic(_clamp(p))


def odchod_sloupce(c, t_rel, delka, st, sloupce):
    """Jak moc sloupec c klesl zpátky dolů: 0 = na místě, 1 = celý dole. Opačné pořadí (poslední sloupec první),
    zrychlení (pád)."""
    rozestup, pad = _casy_odchodu(st, sloupce)
    start = delka - float(st["odchod_s"]) + (sloupce - 1 - c) * rozestup
    q = _clamp((t_rel - start) / max(1e-6, pad))
    return q * q


def posun_sloupce(spec, styl, c, t_rel):
    """O kolik px je sloupec c v čase t_rel (s od začátku prvku) posunutý dolů (0 = na místě, výška plochy = mimo)."""
    st = _styl(spec, styl)
    delka = float(spec["do"]) - float(spec["od"])
    dole = max(1.0 - nastup_sloupce(c, t_rel, st), odchod_sloupce(c, t_rel, delka, st, int(spec["sloupce"])))
    return int(round(int(spec["vyska"]) * dole))


def posun_feedu(spec, styl, t_rel):
    """O kolik px se mřížka (feed) posunula nahoru od začátku prvku."""
    st = _styl(spec, styl)
    return int(round(float(st["posun_px_s"]) * t_rel))


# ---------------------------------------------------------------- dlaždice a pásky

def _vyrez_3_4(im, w, h, vyrez):
    """Obrázek zmenšený a oříznutý na w × h; u vyšších obálek střed výřezu v PODIL_VYREZU výšky."""
    W0, H0 = im.size
    k = max(w / float(W0), h / float(H0))
    nw, nh = max(w, int(round(W0 * k))), max(h, int(round(H0 * k)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x0 = (nw - w) // 2
    y0 = int(round(PODIL_VYREZU.get(vyrez, 0.42) * nh - h / 2.0))
    y0 = max(0, min(nh - h, y0))
    return im.crop((x0, y0, x0 + w, y0 + h))


@lru_cache(maxsize=48)
def _dlazdice(cesta, w, h, vyrez, styl_klic):
    """Hotová dlaždice jako pole (h, w, 3) uint8: výřez 3:4, ztlumený jas, sytost a kontrast."""
    st = dict(styl_klic)
    with Image.open(cesta) as im:
        obr = _vyrez_3_4(im.convert("RGB"), w, h, vyrez)
    if abs(float(st["sytost"]) - 1.0) > 1e-3:
        obr = ImageEnhance.Color(obr).enhance(float(st["sytost"]))
    if abs(float(st["kontrast"]) - 1.0) > 1e-3:
        obr = ImageEnhance.Contrast(obr).enhance(float(st["kontrast"]))
    if abs(float(st["jas"]) - 1.0) > 1e-3:
        obr = ImageEnhance.Brightness(obr).enhance(float(st["jas"]))
    return np.ascontiguousarray(np.asarray(obr, dtype=np.uint8))


def _vineta_1d(delka, od, do, vineta):
    """Činitel ztmavení (×256) pro souřadnice od..do na ose dlouhé delka: 1 − vineta na okraji, 1 uvnitř."""
    pas = max(1.0, VINETA_PODIL * delka)
    x = np.arange(od, do, dtype=np.float64)
    d = np.minimum(x + 0.5, delka - x - 0.5) / pas
    u = np.clip(d, 0.0, 1.0)
    s = 1.0 - u * u * (3.0 - 2.0 * u)
    return np.round(256.0 * (1.0 - vineta * s)).astype(np.uint16)


def _sloupce_pasky(spec, st):
    """Pro každý sloupec (začátek, konec, odsazení dlaždice) v px od levého okraje plochy; krajní sloupce berou
    i zbylé pixely po stranách (vyplní se barvou mezery), mezera patří ke sloupci vlevo od ní."""
    W, w, mez = int(spec["sirka"]), int(spec["dlazdice_sirka"]), int(st["mezera"])
    n = int(spec["sloupce"])
    x0 = int(spec["x"])
    out = []
    for c in range(n):
        xc = int(spec["dlazdice_x"][c]) - x0
        zacatek = 0 if c == 0 else xc
        konec = W if c == n - 1 else xc + w + mez
        out.append((zacatek, konec, xc - zacatek))
    return out


@lru_cache(maxsize=24)
def _paska(cesty, c, sloupce, w, h, vyrez, styl_klic, sirka_pasky, ox, zacatek, sirka_plochy, vyska_plochy):
    """Páska sloupce c: dlaždice pod sebou (obálky po řádcích, opakované), mezery, vodorovná viněta.
    Vrátí (pole (výška pásky + výška plochy + rozteč, šířka pásky, 4) uint8, výška pásky): posun se bere modulo
    výška pásky a výřez vysoký jako plocha se vždy vejde bez přetečení."""
    st = dict(styl_klic)
    mez = int(st["mezera"])
    n = len(cesty)
    rozt = h + mez
    perioda = n // math.gcd(n, sloupce)             # po tolika řádcích se obálky ve sloupci opakují
    radku = perioda
    while radku * rozt < vyska_plochy:
        radku += perioda
    vyska_pasky = radku * rozt
    barva = tuple(int(v) for v in st["barva_mezery"])[:3] + (255,)
    paska = np.empty((vyska_pasky, sirka_pasky, 4), dtype=np.uint8)
    paska[:, :, :] = np.array(barva, dtype=np.uint8)
    for r in range(radku):
        dl = _dlazdice(cesty[(r * sloupce + c) % n], w, h, vyrez, styl_klic)
        paska[r * rozt:r * rozt + h, ox:ox + w, :3] = dl
    vineta = float(st["vineta"])
    if vineta > 0:
        f = _vineta_1d(sirka_plochy, zacatek, zacatek + sirka_pasky, vineta)
        paska[:, :, :3] = ((paska[:, :, :3].astype(np.uint16) * f[None, :, None]) >> 8).astype(np.uint8)
    potreba = vyska_pasky + vyska_plochy + rozt
    kopii = int(math.ceil(potreba / float(vyska_pasky)))
    ext = np.ascontiguousarray(np.concatenate([paska] * kopii, axis=0)[:potreba])
    return ext, vyska_pasky


@lru_cache(maxsize=8)
def _vineta_y(vyska_plochy, vineta):
    """Činitele svislé viněty (×256) pro horní a spodní pás plochy; (pás v px, činitele horní, činitele spodní)."""
    pas = int(round(VINETA_PODIL * vyska_plochy))
    horni = _vineta_1d(vyska_plochy, 0, pas, vineta)
    spodni = _vineta_1d(vyska_plochy, vyska_plochy - pas, vyska_plochy, vineta)
    return pas, horni, spodni


def vykresli(spec, styl, k):
    """Snímek k (číslo od začátku prvku): sloupce mřížky posunuté o feed, s nástupem zdola a odchodem dolů.
    Vrátí (RGBA obrázek celé plochy zdi, (x, y)); kde sloupec ještě nevyjel, je plocha průhledná (vidět pokoj)."""
    st = _styl(spec, styl)
    styl_klic = _styl_klic(st)
    t_rel = float(k) / FPS
    W, H = int(spec["sirka"]), int(spec["vyska"])
    w, h = int(spec["dlazdice_sirka"]), int(spec["dlazdice_vyska"])
    sloupce = int(spec["sloupce"])
    cesty = tuple(spec["cesty"])
    out = np.zeros((H, W, 4), dtype=np.uint8)
    feed = posun_feedu(spec, styl, t_rel)
    for c, (zacatek, konec, ox) in enumerate(_sloupce_pasky(spec, st)):
        dy = posun_sloupce(spec, styl, c, t_rel)
        if dy >= H:
            continue
        ext, vyska_pasky = _paska(cesty, c, sloupce, w, h, spec.get("vyrez", "nahore"), styl_klic,
                                  konec - zacatek, ox, zacatek, W, H)
        off = feed % vyska_pasky
        out[dy:H, zacatek:konec] = ext[off:off + H - dy]
    vineta = float(st["vineta"])
    if vineta > 0:
        pas, horni, spodni = _vineta_y(H, vineta)
        if pas > 0:
            out[:pas, :, :3] = ((out[:pas, :, :3].astype(np.uint16) * horni[:, None, None]) >> 8).astype(np.uint8)
            out[H - pas:, :, :3] = ((out[H - pas:, :, :3].astype(np.uint16) * spodni[:, None, None]) >> 8).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), (int(spec["x"]), int(spec["y"]))
