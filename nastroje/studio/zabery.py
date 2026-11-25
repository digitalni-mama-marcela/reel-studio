"""Záběry pro b-roll pod hlasem (Marcela 24. 11. 2026): příprava, hodnocení kvality, chvilky a katalog.

Zákaznice nahraje záběry tak, jak je natočila (dlouhé, neučesané). Studio je projde samo:
- každý záběr dekóduje jednou (malé snímky, jen výřez 9:16, který bude v reelu opravdu vidět) a změří po snímcích
  ostrost (Laplace), světlo (průměrný jas, přepal, tma), roztřesení kamery (posun mezi snímky fázovou korelací;
  plynulý posun telefonu je v pořádku, škubání tam a zpátky ne) a dění v záběru (změna obrazu po srovnání posunu);
- najde 3 až 4 nejlepší chvilky po 6 až 9 s, které se nepřekrývají (kratší záběr dá jednu kratší chvilku);
- každou vybranou chvilku zkontroluje na blikání světel v plné snímkové frekvenci (zářivky a LED blikají
  snímek po snímku nahoru a dolů, pohyb ani střih ne); blikající chvilka se vyřadí, nic se „neopravuje“;
- připraví náhledy (časová řada snímků celého záběru a pro každou chvilku začátek, střed a konec), aby Claude
  viděl, co na nich opravdu je, pojmenoval je podle obsahu a vyřadil chvilky, kde člověk odejde ze záběru.
Všechno se pamatuje v katalogu (katalog-zaberu.json + čitelný KATALOG-ZABERU.txt vedle záběrů), příště se znovu
měří a prohlíží jen nový nebo změněný záběr. Originály se nikdy nemění ani nekopírují, chvilka je jen úsek od–do.

iPhone v režimu Filmový ukládá dvojici: IMG_1234.MOV bez rozostření a IMG_E1234.MOV s rozostřením. Když jsou
obě, bere se jen ta s E.
Stálá knihovna MOJE-ZABERY (ve složce Reely) slouží pro všechny reely; její záběry se do reelu dávají jen podle
přiřazení (Claude je vybírá podle smyslu věty), záběry v B-ROLL reelu i samy.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

PRIPONY = {".mp4", ".mov", ".m4v"}
KNIHOVNA = "MOJE-ZABERY"
KATALOG = "katalog-zaberu.json"
KATALOG_TXT = "KATALOG-ZABERU.txt"
VERZE = 1

DLAZDICE = (180, 320)        # náhled 9:16
ZACATEK_S, KONEC_S = 0.4, 0.3    # začátek bývá roztřesený od dotyku na displej, konec od zastavení
CHVILKA_S, CHVILKA_MAX_S, CHVILKA_MIN_S = 7.0, 9.0, 1.2
NEJVIC_CHVILEK = 4
OSTROST_MIN = 45.0           # Laplaceův rozptyl na 180x320 (čtvrtina nejhorších snímků) pod tímhle je rozmazané
OSTROST_PODIL = 0.30         # a taky když je ostrost pod touhle částí nejlepšího místa záběru (rozmazání pohybem)
OSTROST_DOBRA = 220.0        # od téhle ostrosti je ostrost v hodnocení plná
JAS_MIN, JAS_MAX = 48, 218   # průměrný jas, mimo je chvilka tmavá nebo přepálená
TRES_MAX = 1.5               # třes kamery (px na 180x320 mezi sousedními snímky), nad tím je chvilka roztřesená
DENI_ZIVA = 1.6              # průměrná změna obrazu po srovnání kamery, nad tím je chvilka živá
ROHY_SHODA = 1.0             # o kolik px se smí rohy obrazu rozejít, aby to byl pohyb kamery
STRIH_PRAH = 0.45            # změna histogramu jasu mezi vzorky, nad tím je to střih (jiná scéna)
BLIK_MIN = 3                 # kolik kmitů jasu v chvilce znamená blikání


def _tichy(*a, **kw):
    kw.setdefault("capture_output", True)
    return subprocess.run(*a, **kw)


def je_zaber(p):
    return p.is_file() and p.suffix.lower() in PRIPONY and not p.name.startswith((".", "_"))


def _filmovy_par(soubory):
    """IMG_1234 + IMG_E1234 → nechá jen E (Filmový režim). Vrátí (seznam, {vyřazený: náhrada})."""
    jmena = {p.stem.lower(): p for p in soubory}
    pryc = {}
    for p in soubory:
        s = p.stem.lower()
        for t in (("img_e" + s[4:]) if s.startswith("img_") else None, s + "_e", s + "-e"):
            if t and t in jmena and jmena[t] != p and jmena[t].parent == p.parent:
                pryc[p] = jmena[t]
    return [p for p in soubory if p not in pryc], pryc


def najdi(slozka, rekurzivne=False):
    """Záběry ve složce (podle názvu). Složky a soubory začínající _ nebo . se vynechají."""
    d = Path(slozka)
    if not d.is_dir():
        return []
    if rekurzivne:
        vse = [p for p in d.rglob("*") if je_zaber(p)
               and not any(c.startswith(("_", ".")) for c in p.relative_to(d).parts[:-1])]
    else:
        vse = [p for p in d.iterdir() if je_zaber(p)]
    return sorted(_filmovy_par(vse)[0], key=lambda p: str(p).lower())


def knihovna(reel):
    """Stálá složka MOJE-ZABERY vedle reelů (ve složce Reely)."""
    return Path(reel).parent / KNIHOVNA


def otisk(cesta):
    """Velikost + kontrolní součet začátku a konce: změněný soubor se pozná, přejmenovaný taky."""
    p = Path(cesta)
    n = p.stat().st_size
    h = hashlib.sha1(str(n).encode())
    with open(p, "rb") as f:
        h.update(f.read(1 << 16))
        if n > 1 << 17:
            f.seek(-(1 << 16), 2)
            h.update(f.read(1 << 16))
    return "%d-%s" % (n, h.hexdigest()[:16])


def _info(cesta):
    from . import kontrola_videa, poloha
    i = kontrola_videa.precti(cesta)
    if not i.get("video"):
        return None
    w, h, _ = poloha.rozmer_klipu(cesta)
    v = i["video"]
    return {"delka": float(i["delka_s"]), "hdr": bool(v.get("hdr")), "prenos": v.get("prenos", ""),
            "zvuk": bool(i.get("zvuk")), "sirka": w, "vyska": h, "fps": float(v.get("fps") or 30.0)}


def _vf(inf, w, h, fps=None, pary=None):
    """Zmenšení na výřez 9:16 (to, co bude v reelu vidět), pak teprve převod HDR (na malém obrázku je rychlý).
    pary=K: z každých K snímků vezme dva sousední (rychlost kamery v 1/30 s, z ní se pozná třes)."""
    from .kontrola_videa import filtr_hdr
    barvy = ("," + filtr_hdr({"prenos": inf["prenos"]})) if inf.get("hdr") else ""
    vyber = ("select='lt(mod(n,%d),2)',setpts=N/TB," % pary) if pary else ""
    f = ("fps=%s," % fps) if fps else ""
    return "%s%sscale=%d:%d:force_original_aspect_ratio=increase:flags=bilinear,crop=%d:%d%s" % (vyber, f, w, h, w, h, barvy)


def _dekoduj(cesta, vf, w, h, od=None, delka=None, kanaly=3):
    """Snímky jako pole numpy (rgb24 nebo gray). Na Macu zkusí hardwarové dekódování, jinak obyčejné."""
    pix = "rgb24" if kanaly == 3 else "gray"
    pred = (["-ss", "%.3f" % od] if od is not None else [])
    po = (["-t", "%.3f" % delka] if delka is not None else [])
    for hw in ((["-hwaccel", "videotoolbox"], []) if sys.platform == "darwin" else ([],)):
        r = _tichy(["ffmpeg", "-v", "error", "-nostdin"] + hw + pred + ["-i", str(cesta)] + po +
                   ["-an", "-vf", vf, "-fps_mode", "passthrough", "-pix_fmt", pix, "-f", "rawvideo", "-"])
        if r.returncode == 0 and r.stdout:
            velikost = w * h * kanaly
            n = len(r.stdout) // velikost
            pole = np.frombuffer(r.stdout[:n * velikost], dtype=np.uint8)
            return pole.reshape((n, h, w, kanaly) if kanaly == 3 else (n, h, w))
    return np.zeros((0, h, w, kanaly) if kanaly == 3 else (0, h, w), dtype=np.uint8)


def _rychlost(a, b, okno):
    """Posun kamery mezi dvěma sousedními snímky (px) a jistota měření."""
    import cv2
    (dx, dy), jistota = cv2.phaseCorrelate(a, b, okno)
    return float(dx), float(dy), float(jistota)


def mereni_snimku(pary):
    """Měření z dvojic sousedních snímků (pole (n, 2, h, w) uint8, šedé): ostrost, jas, přepal, tma,
    rychlost kamery (dx, dy za 1 snímek) a dění (změna obrazu po srovnání posunu kamery)."""
    import cv2
    out = []
    if not len(pary):
        return out
    h, w = pary.shape[2], pary.shape[3]
    okno = cv2.createHanningWindow((w, h), cv2.CV_32F)
    pw, ph = w * 4 // 9, h * 2 // 5
    rohy = [(0, 0), (w - pw, 0), (0, h - ph), (w - pw, h - ph)]
    okno_rohu = cv2.createHanningWindow((pw, ph), cv2.CV_32F)
    for a8, b8 in pary:
        a, b = a8.astype(np.float32), b8.astype(np.float32)
        dx, dy, jist = _rychlost(a, b, okno)
        # kamera: všechny čtyři rohy se posunou stejně; pohyb v záběru (ruce, barvy) jen některé
        r = np.array([_rychlost(a[y:y + ph, x:x + pw], b[y:y + ph, x:x + pw], okno_rohu)[:2] for x, y in rohy])
        stred = np.median(r, axis=0)
        shoda = float(np.max(np.linalg.norm(r - stred, axis=1)))
        M = np.float32([[1, 0, -dx], [0, 1, -dy]])
        srovnany = cv2.warpAffine(b, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        out.append({"ostrost": float(cv2.Laplacian(a8, cv2.CV_64F).var()), "jas": float(a8.mean()),
                    "prepal": float((a8 >= 250).mean()), "tma": float((a8 <= 8).mean()),
                    "dx": dx, "dy": dy, "jistota": jist, "kx": float(stred[0]), "ky": float(stred[1]),
                    "kamera_jista": shoda <= ROHY_SHODA,
                    "deni": float(np.abs(srovnany - a)[6:-6, 6:-6].mean()),
                    "hist": cv2.calcHist([a8], [0], None, [32], [0, 256]).ravel() / a8.size})
    return out


def dopln_treseni(mer):
    """Ke každému vzorku třes kamery: o kolik se jeho rychlost kamery liší od plynulého průběhu okolních vzorků
    (průměr dvou vzorků před a dvou po). Plynulý posun telefonu = 0, škubání tam a zpátky = hodně."""
    if not mer:
        return mer
    v = np.array([(m.get("kx", m["dx"]), m.get("ky", m["dy"])) for m in mer], dtype=float)
    jiste = np.array([m.get("kamera_jista", True) for m in mer])
    for i, m in enumerate(mer):
        sousede = [j for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(mer) and jiste[j]]
        if not jiste[i] or len(sousede) < 2:
            m["tres"] = 0.0                     # rohy se neshodnou: hýbe se obsah, ne kamera
            continue
        m["tres"] = float(np.linalg.norm(v[i] - v[sousede].mean(axis=0)))
    return mer


def hodnot_usek(mer, fps_m, od, do, ostrost_klipu=None):
    """Hodnocení úseku od–do (s) z měření. ostrost_klipu: nejlepší ostrost záběru (rozmazané místo se pozná i
    v záběru, kde je málo detailů). Vrátí slovník se skóre a vadami."""
    a, b = int(od * fps_m), max(int(od * fps_m) + 1, int(round(do * fps_m)))
    s = mer[a:b]
    if not s:
        return None
    ostrost = float(np.median([m["ostrost"] for m in s]))
    ostrost_nejhorsi = float(np.percentile([m["ostrost"] for m in s], 25))
    jas = float(np.mean([m["jas"] for m in s]))
    prepal = float(np.mean([m["prepal"] for m in s]))
    tma = float(np.mean([m["tma"] for m in s]))
    tres = float(np.mean([m.get("tres", 0.0) for m in s]))
    deni = float(np.mean([m["deni"] for m in s]))
    vady = []
    if ostrost_nejhorsi < OSTROST_MIN or (ostrost_klipu and ostrost_nejhorsi < OSTROST_PODIL * ostrost_klipu):
        vady.append("rozmazané")
    if jas < JAS_MIN or tma > 0.35:
        vady.append("tmavé")
    if jas > JAS_MAX or prepal > 0.30:
        vady.append("přepálené")
    if tres > TRES_MAX:
        vady.append("roztřesené")
    q_ostr = min(1.0, max(0.0, (ostrost - OSTROST_MIN) / (OSTROST_DOBRA - OSTROST_MIN)))
    q_svetlo = max(0.0, 1.0 - abs(jas - 128) / 128.0) * (1.0 - min(1.0, prepal * 2 + tma * 2))
    q_klid = max(0.0, 1.0 - tres / TRES_MAX)
    skore = 0.45 * q_ostr + 0.30 * q_svetlo + 0.25 * q_klid
    return {"od": round(od, 2), "do": round(do, 2), "skore": round(skore, 3), "ostrost": round(ostrost, 1),
            "jas": round(jas, 1), "treseni": round(tres, 2), "deni": round(deni, 2),
            "energie": "živá" if deni >= DENI_ZIVA else "klidná", "vady": vady}


def kmity(rada, prah):
    """Kolikrát jas kmitne nahoru a hned dolů (nebo obráceně) o víc než práh."""
    d = np.diff(np.asarray(rada, dtype=float))
    if len(d) < 2:
        return 0
    return int(np.sum((np.abs(d[1:]) > prah) & (np.abs(d[:-1]) > prah) & (d[1:] * d[:-1] < 0)))


def blikani(cesta, inf, od, do):
    """Počet kmitů jasu v plné snímkové frekvenci (celý snímek i vodorovné pruhy, které dělá zářivka)."""
    g = _dekoduj(cesta, _vf(inf, 64, 114), 64, 114, od=od, delka=do - od, kanaly=1)
    if len(g) < 6:
        return 0
    cely = g.reshape(len(g), -1).mean(axis=1)
    pruhy = g.mean(axis=2).std(axis=1)
    return max(kmity(cely, 2.5), kmity(pruhy, 1.2))


def strihy(mer, fps_m):
    """Střihy uvnitř záběru (obraz se mezi dvěma vzorky změní skokem, ne pohybem): pořadí prvního vzorku po střihu."""
    import cv2
    out = []
    for i in range(1, len(mer)):
        a, b = mer[i - 1].get("hist"), mer[i].get("hist")
        if a is None or b is None:
            continue
        if cv2.compareHist(a.astype(np.float32), b.astype(np.float32), cv2.HISTCMP_BHATTACHARYYA) > STRIH_PRAH:
            out.append(i)
    return out


def vyber_chvilky(mer, fps_m, delka, nejvic=NEJVIC_CHVILEK):
    """Nejlepší chvilky bez vad, nepřekrývající se. Vrátí [hodnocení] seřazené podle času."""
    zac, kon = min(ZACATEK_S, delka * 0.1), max(0.0, delka - KONEC_S)
    ostr = float(np.percentile([m["ostrost"] for m in mer], 90)) if mer else None
    cuty = strihy(mer, fps_m)

    def pres_strih(od, do):
        return any(int(od * fps_m) < c < int(round(do * fps_m)) for c in cuty)
    pouzitelne = kon - zac
    if pouzitelne < CHVILKA_MIN_S:
        return []
    if pouzitelne <= CHVILKA_MAX_S and not pres_strih(zac, kon):
        h = hodnot_usek(mer, fps_m, zac, kon, ostr)
        return [h] if h and not h["vady"] else []
    if pouzitelne <= CHVILKA_MAX_S:
        L = max(CHVILKA_MIN_S * 2, pouzitelne / 2)
    else:
        L = CHVILKA_S if pouzitelne >= CHVILKA_S * 1.6 else min(CHVILKA_MAX_S, pouzitelne / 1.4 if pouzitelne > 10 else pouzitelne)
    kandidati = []
    t = zac
    while t + L <= kon + 1e-6:
        if not pres_strih(t, t + L):
            h = hodnot_usek(mer, fps_m, t, t + L, ostr)
            if h and not h["vady"]:
                kandidati.append(h)
        t += 0.5
    kandidati.sort(key=lambda h: -h["skore"])
    vybrane = []
    for h in kandidati:
        if len(vybrane) >= nejvic:
            break
        if any(h["od"] < v["do"] and v["od"] < h["do"] for v in vybrane):
            continue
        vybrane.append(h)
    # okraj s vadou (rozmazání pohybem, zhasnutí) se z chvilky ořízne po půl sekundě
    for v in vybrane:
        while v["do"] - v["od"] > 3.0:
            h = hodnot_usek(mer, fps_m, v["do"] - 1.0, v["do"], ostr)
            if h and not h["vady"]:
                break
            v["do"] = round(v["do"] - 0.5, 2)
        while v["do"] - v["od"] > 3.0:
            h = hodnot_usek(mer, fps_m, v["od"], v["od"] + 1.0, ostr)
            if h and not h["vady"]:
                break
            v["od"] = round(v["od"] + 0.5, 2)
    # dobrou chvilku natáhnout až na CHVILKA_MAX_S, když okolí taky nemá vady
    for v in vybrane:
        for _ in range(4):
            nove = min(kon, v["do"] + 0.5)
            if nove - v["od"] > CHVILKA_MAX_S or nove <= v["do"] or pres_strih(v["od"], nove) or any(o is not v and nove > o["od"] and v["od"] < o["od"] for o in vybrane):
                break
            h = hodnot_usek(mer, fps_m, v["do"], nove, ostr)
            if not h or h["vady"]:
                break
            v["do"] = round(nove, 2)
    return sorted(vybrane, key=lambda h: h["od"])


def proc_nic(mer, fps_m, delka):
    """Proč záběr nedal žádnou chvilku, slovy (co s tím udělat)."""
    h = hodnot_usek(mer, fps_m, 0, delka)
    if not h:
        return "nejde přečíst"
    if delka < ZACATEK_S + KONEC_S + CHVILKA_MIN_S:
        return "je moc krátký (pod 2 s)"
    muz = {"rozmazané": "rozmazaný", "tmavé": "tmavý", "přepálené": "přepálený", "roztřesené": "roztřesený"}
    return ("je celý %s" % " a ".join(muz.get(v, v) for v in h["vady"])) if h["vady"] else "nemá klidnou ostrou chvilku"


def analyzuj(cesta):
    """Změří záběr a najde chvilky. Vrátí (záznam do katalogu, snímky pro náhled, kolik snímků náhledu na 1 s)."""
    inf = _info(cesta)
    if not inf or inf["delka"] < 1.0:
        return {"vyrazeno": "nejde přečíst nebo je kratší než 1 s", "chvilky": []}, None, 0
    fps_m = max(0.5, min(4.0, 300.0 / inf["delka"]))
    k = max(2, int(round(inf["fps"] / fps_m)))
    fps_m = inf["fps"] / k
    w, h = DLAZDICE
    snimky = _dekoduj(cesta, _vf(inf, w, h, pary=k), w, h)
    snimky = snimky[:len(snimky) // 2 * 2]
    if not len(snimky):
        return dict(inf, vyrazeno="nejde přečíst", chvilky=[]), None, 0
    import cv2
    sede = np.stack([cv2.cvtColor(x, cv2.COLOR_RGB2GRAY) for x in snimky]).reshape(-1, 2, h, w)
    mer = dopln_treseni(mereni_snimku(sede))
    nahled = snimky[0::2]
    chv = vyber_chvilky(mer, fps_m, inf["delka"])
    hotove = []
    for c in chv:
        bl = blikani(cesta, inf, c["od"], c["do"])
        if bl >= BLIK_MIN:
            continue
        c["blikani"] = bl
        hotove.append(c)
    zaznam = dict(inf, chvilky=[dict(c, c=i + 1, nazev="", popis="", nalada="", vyradit=False) for i, c in enumerate(hotove)],
                  popis="", vyrazeno=None)
    if not hotove:
        zaznam["vyrazeno"] = ("bliká světlo (zářivka nebo LED) ve všech dobrých chvilkách" if chv else proc_nic(mer, fps_m, inf["delka"]))
    return zaznam, nahled, fps_m


# ---------- katalog ----------

def nacti_katalog(slozka):
    p = Path(slozka) / KATALOG
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("verze") == VERZE:
            return d
    except (OSError, ValueError):
        pass
    return {"verze": VERZE, "zabery": {}}


def uloz_katalog(slozka, kat):
    slozka = Path(slozka)
    (slozka / KATALOG).write_text(json.dumps(kat, ensure_ascii=False, indent=1), encoding="utf-8")
    radky = ["Katalog záběrů (studio ho píše samo; co je v kterém záběru a jeho nejlepší chvilky).", ""]
    for jm, z in sorted(kat["zabery"].items()):
        radky.append("%s  (%s)%s" % (jm, cas(z.get("delka", 0)), ("  " + z["popis"]) if z.get("popis") else ""))
        if z.get("vyrazeno"):
            radky.append("   nepoužitelný: %s" % z["vyrazeno"])
        for c in z.get("chvilky", []):
            radky.append("   %s  %s–%s  %s%s%s" % (
                id_chvilky(jm, c), cas(c["od"]), cas(c["do"]), c["energie"],
                (", " + c["nalada"]) if c.get("nalada") else "", ("  " + c["popis"]) if c.get("popis") else "")
                + ("  (vyřazená: %s)" % (c["vyradit"] if isinstance(c["vyradit"], str) else "Claude") if c.get("vyradit") else ""))
        radky.append("")
    (slozka / KATALOG_TXT).write_text("\n".join(radky), encoding="utf-8")


def cas(s):
    s = float(s)
    return "%d:%04.1f" % (int(s // 60), s % 60) if s >= 60 else "%.1f s" % s


def id_chvilky(jmeno, c):
    return c.get("nazev") or "%s-%d" % (Path(jmeno).stem, c["c"])


def aktualizuj(slozka, nahledy=None, rekurzivne=False, hlaseni=None):
    """Projde záběry ve složce, nové a změněné změří, smazané z katalogu vyškrtne. Náhledy nových uloží
    do složky nahledy. Vrátí (katalog, [nově změřené jméno]). Jméno v katalogu je cesta vůči složce."""
    slozka = Path(slozka)
    kat = nacti_katalog(slozka)
    soubory = najdi(slozka, rekurzivne)
    jmena = {p.relative_to(slozka).as_posix(): p for p in soubory}
    nove = []
    for jm, p in jmena.items():
        try:
            ot = otisk(p)
        except OSError:
            continue
        stary = kat["zabery"].get(jm)
        if stary and stary.get("otisk") == ot:
            continue
        if hlaseni:
            hlaseni("Prohlížím záběr %s…" % jm)
        zaznam, snimky, fps_m = analyzuj(p)
        zaznam["otisk"] = ot
        if stary and stary.get("otisk") != ot:
            zaznam["popis"] = ""
        kat["zabery"][jm] = zaznam
        nove.append(jm)
        if nahledy is not None and snimky is not None:
            nahled_zaberu(jm, zaznam, snimky, fps_m, Path(nahledy))
    for jm in [j for j in kat["zabery"] if j not in jmena]:
        del kat["zabery"][jm]
    if slozka.is_dir():
        uloz_katalog(slozka, kat)
    return kat, nove


def zapis_popis(slozka, popis):
    """Claude zapíše, co na záběrech je: {jméno: {"popis", "chvilky": [{"c", "nazev", "popis", "nalada", "vyradit"}]}}.
    Názvy chvilek se upraví na tvar bez mezer a diakritiky (kavarna-kava), ať jdou psát do --broll."""
    from .reel import slug
    kat = nacti_katalog(slozka)
    neznam = []
    for jm, p in popis.items():
        z = kat["zabery"].get(jm) or next((v for k, v in kat["zabery"].items() if Path(k).name.lower() == Path(jm).name.lower()), None)
        if not z:
            neznam.append(jm)
            continue
        if p.get("popis"):
            z["popis"] = str(p["popis"])
        for pc in p.get("chvilky", []):
            c = next((x for x in z["chvilky"] if x["c"] == int(pc.get("c", 0))), None)
            if not c:
                continue
            for klic in ("popis", "nalada", "vyradit"):
                if klic in pc:
                    c[klic] = pc[klic]
            if pc.get("nazev"):
                c["nazev"] = slug(str(pc["nazev"]), 30)
    uloz_katalog(slozka, kat)
    return kat, neznam


def chvilky(slozka, kat=None, jen_popsane=False):
    """Použitelné chvilky z katalogu složky pro plán: [{id, soubor, od, do, skore, energie, nalada, popis, hdr, prenos, zvuk}]."""
    slozka = Path(slozka)
    kat = kat or nacti_katalog(slozka)
    out = []
    for jm, z in sorted(kat["zabery"].items()):
        if z.get("vyrazeno"):
            continue
        for c in z.get("chvilky", []):
            if c.get("vyradit") or (jen_popsane and not c.get("popis")):
                continue
            out.append({"id": id_chvilky(jm, c), "soubor": str(slozka / jm), "od": c["od"], "do": c["do"],
                        "skore": c["skore"], "energie": c["energie"], "nalada": c.get("nalada", ""),
                        "popis": c.get("popis", ""), "hdr": z.get("hdr", False), "prenos": z.get("prenos", ""),
                        "zvuk": z.get("zvuk", False)})
    return out


# ---------- náhledy pro Clauda ----------

def _pismo(velikost):
    from PIL import ImageFont
    from .cesty import PISMA
    try:
        return ImageFont.truetype(str(PISMA / "Inter-wght.ttf"), velikost)
    except OSError:
        return ImageFont.load_default(size=velikost)


def nahled_zaberu(jmeno, zaznam, snimky, fps_m, slozka_nahledu):
    """Časová řada celého záběru (nejvýš 30 dlaždic) s časem a vyznačenými chvilkami."""
    from PIL import Image, ImageDraw
    slozka_nahledu.mkdir(parents=True, exist_ok=True)
    n = len(snimky)
    krok = max(1, int(np.ceil(n / 30.0)))
    vybrane = list(range(0, n, krok))
    w, h = DLAZDICE
    sl = 6
    radky = (len(vybrane) + sl - 1) // sl
    platno = Image.new("RGB", (sl * w, radky * (h + 22) + 40), (24, 24, 24))
    d = ImageDraw.Draw(platno)
    d.text((8, 8), "%s  (%s)" % (jmeno, cas(zaznam.get("delka", 0))), fill=(255, 255, 255), font=_pismo(22))
    barvy = [(255, 70, 140), (40, 200, 120), (255, 190, 40), (90, 160, 255)]
    for k, i in enumerate(vybrane):
        t = i / fps_m
        x, y = (k % sl) * w, 40 + (k // sl) * (h + 22)
        platno.paste(Image.fromarray(snimky[i]), (x, y))
        c = next((c for c in zaznam["chvilky"] if c["od"] <= t <= c["do"]), None)
        if c:
            b = barvy[(c["c"] - 1) % len(barvy)]
            d.rectangle([x, y + h, x + w - 1, y + h + 21], fill=b)
            d.text((x + 6, y + h + 2), "%s  chvilka %d" % (cas(t), c["c"]), fill=(0, 0, 0), font=_pismo(16))
        else:
            d.text((x + 6, y + h + 2), cas(t), fill=(200, 200, 200), font=_pismo(16))
    cil = slozka_nahledu / (_bezpecne(jmeno) + ".jpg")
    platno.save(cil, quality=82)
    # chvilky: začátek, střed, konec vedle sebe
    if zaznam["chvilky"]:
        platno = Image.new("RGB", (3 * w + 260, len(zaznam["chvilky"]) * (h + 10) + 10), (24, 24, 24))
        d = ImageDraw.Draw(platno)
        for r, c in enumerate(zaznam["chvilky"]):
            y = 10 + r * (h + 10)
            for s, t in enumerate((c["od"] + 0.2, (c["od"] + c["do"]) / 2, c["do"] - 0.2)):
                platno.paste(Image.fromarray(snimky[min(n - 1, int(t * fps_m))]), (s * w, y))
            d.text((3 * w + 12, y + 6), "chvilka %d" % c["c"], fill=barvy[(c["c"] - 1) % len(barvy)], font=_pismo(24))
            d.text((3 * w + 12, y + 40), "%s – %s" % (cas(c["od"]), cas(c["do"])), fill=(255, 255, 255), font=_pismo(18))
            d.text((3 * w + 12, y + 66), "%s, skóre %.2f" % (c["energie"], c["skore"]), fill=(200, 200, 200), font=_pismo(18))
        platno.save(slozka_nahledu / (_bezpecne(jmeno) + "-chvilky.jpg"), quality=82)
    return cil


def _bezpecne(jmeno):
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in jmeno.replace("/", "__"))
