"""B-roll pod hlasem (Marcela 24. 11. 2026): hlas z mluveného videa běží dál, obraz na chvíli převezme jiný záběr.

Zákaznice dá záběry (MP4, MOV) do složky PODKLADY-SEM/B-ROLL v reelu, stálé záběry do složky Reely/MOJE-ZABERY.
Studio je projde (zabery.py: nejlepší chvilky bez rozmazání, tmy, třesu a blikání, katalog) a rozmístí po větách.
Claude k větám přiřadí chvilky podle smyslu („kafe ráno“ k větě o ranní rutině), zbytek doplní studio samo.
Pravidla (kniha střihu studia, vlastní návrh):
- střih na záběr i zpátky přesně na začátku věty nebo na hranici slova (hlas nikdy neskáče, mění se jen obraz);
- s tváří: první věta (nadpis, tvář buduje důvěru) a věta s výzvou do komentáře zůstávají s tváří, záběry nikdy dvě
  věty za sebou;
- jen hlas: záběry pokryjí celý reel, dlouhou větu rozdělí na hranici slova, tvář se neukáže; začátek je rychlý
  (v prvních ~2 s se střídá víc záběrů natvrdo), když je záběrů málo nebo je tempo procítěné, začne jedním klidným;
- tempo úderné / běžné / procítěné: délka záběru, prolnutí mezi záběry, síla pohybu a rychlý začátek;
- pohyb: záběry se střídají v přiblížení, oddálení a pomalém posunu do strany (obraz nikdy nestojí), rychlý začátek
  bez pohybu (pohyb v rychlém střihu je chaos), opakovaný záběr v rychlém začátku blíž (ať vypadá jinak);
- zvuk záběrů tiše pod hlasem (voda, nádobí, kroky): každý kousek přesně tak dlouhý jako jeho záběr, hlasitost
  změřená (20 LU pod hlasem), když mluvíš, ještě se ztiší; titulky, nadpis i efekty jedou dál nad záběrem;
- HDR z iPhonu se převede stejně jako hlavní video (kontrola_videa.filtr_hdr), otočení a rozměr ffmpeg srovná sám.

Spec v osa["prekryvy"]: [{"od", "do", "soubor", "zacatek", "hdr", "prenos", "pohyb", "nabeh", "dobeh", "presah",
"zvuk", "chvilka"}] v čase hotového reelu. presah: o kolik záběr zůstane pod dalším, který se přes něj prolíná.
"""
import json
import re
import subprocess
from pathlib import Path

from .titulky import FPS, SIRKA, VYSKA

PRIPONY = {".mp4", ".mov", ".m4v"}
SLOZKA = "B-ROLL"
MIN_S, MAX_S = 1.6, 4.0
ZACATEK_S = 0.4
PRIBLIZENI = 0.04
PROLNUTI_S = 4 / FPS

TEMPA = {
    # min/max: délka záběru (s); prolnuti: snímky prolnutí mezi záběry; stab: délka záběru v rychlém začátku (None = bez
    # rychlého začátku); pohyb: o kolik se obraz za záběr přiblíží nebo posune
    "uderne": {"min": 1.2, "max": 2.6, "prolnuti": 2, "stab": 0.25, "pohyb": 0.07},
    "bezne": {"min": MIN_S, "max": MAX_S, "prolnuti": 4, "stab": 0.33, "pohyb": 0.05},
    "procitene": {"min": 2.0, "max": 5.5, "prolnuti": 9, "stab": None, "pohyb": 0.035},
}
POHYBY = ("pribliz", "oddal", "posun-vpravo", "pribliz", "posun-vlevo", "oddal")
BLIZE = 1.12                     # opakovaný záběr v rychlém začátku: o tolik blíž


def slozka(podklady):
    return Path(podklady) / SLOZKA


def najdi(podklady):
    """Záběry ve složce B-ROLL (seřazené podle jména), bez skrytých souborů."""
    d = slozka(podklady)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() in PRIPONY and not p.name.startswith("."))


def info(cesta):
    """Délka a barvy záběru (ffprobe přes kontrola_videa). None, když to není čitelné video."""
    from . import kontrola_videa
    try:
        i = kontrola_videa.precti(cesta)
    except Exception:  # noqa: BLE001
        return None
    if not i.get("video") or i["delka_s"] < 1.0:
        return None
    return {"delka": i["delka_s"], "hdr": bool(i["video"].get("hdr")), "prenos": i["video"].get("prenos", ""),
            "zvuk": bool(i.get("zvuk"))}


def chvilky_ze_souboru(soubory):
    """Bez katalogu: celý záběr jako jedna chvilka (od 0,4 s). soubory: [(Path, info)]."""
    out = []
    for p, inf in soubory:
        out.append({"id": Path(p).stem, "soubor": str(p), "od": ZACATEK_S, "do": max(ZACATEK_S + 1.0, inf["delka"] - 0.2),
                    "skore": 0.5, "energie": "klidná", "nalada": "", "popis": "", "hdr": inf.get("hdr", False),
                    "prenos": inf.get("prenos", ""), "zvuk": inf.get("zvuk", False)})
    return out


def _konec_useku(slova, od, max_s, min_s=MIN_S):
    """Konec úseku od času od: nejvýš max_s, na hranici slova (konec slova), aspoň min_s, když to věta dovolí."""
    konec = od
    for w in slova:
        if w["end"] <= od:
            continue
        if w["end"] - od > max_s and konec - od >= min_s:
            break
        konec = w["end"]
    return konec


class _Zasobnik:
    """Chvilky a kolik z nich už je použito: každé další použití bere navazující kus, pak se vrátí na začátek."""

    def __init__(self, chvilky):
        self.chv = {c["id"]: c for c in chvilky}
        self.pouzito = {c["id"]: 0.0 for c in chvilky}
        self.pocet = {c["id"]: 0 for c in chvilky}
        self.poradi = [c["id"] for c in chvilky]

    def delka(self, cid):
        c = self.chv[cid]
        return c["do"] - c["od"]

    def zbyva(self, cid, d):
        """Kolik souvislého obrazu chvilka dá pro záběr délky d (došlá chvilka začne znovu)."""
        z = self.delka(cid) - self.pouzito[cid]
        return self.delka(cid) if z < min(d * 0.75, self.delka(cid)) else z

    def vezmi(self, cid, d):
        """Vrátí (začátek v souboru, skutečná délka). Krátká chvilka dá, co má."""
        c = self.chv[cid]
        zbyva = c["do"] - c["od"] - self.pouzito[cid]
        if zbyva < min(d * 0.75, self.delka(cid)):
            self.pouzito[cid] = 0.0                 # chvilka došla: znovu od jejího začátku
            zbyva = self.delka(cid)
        d = min(d, zbyva)
        zac = c["od"] + self.pouzito[cid]
        self.pouzito[cid] += d
        self.pocet[cid] += 1
        return zac, d

    def vyber(self, d, posledni=None, energie=None, vyloucit=()):
        """Nejlepší chvilka pro záběr délky d: nepoužitá, z jiného souboru než minule, s náladou, s nejvyšším skóre."""
        kand = [cid for cid in self.poradi if cid not in vyloucit]
        if not kand:
            kand = list(self.poradi)

        def klic(cid):
            c = self.chv[cid]
            return (c["soubor"] == posledni,                                    # jiný soubor než předchozí záběr
                    self.delka(cid) < min(d, 4.0) * 0.9,                        # ať se vejde (žádný useknutý zbytek)
                    self.pocet[cid],                                            # nejdřív nejméně použité (střídání)
                    energie is not None and c.get("energie") != energie,        # nálada (rychlý začátek chce živé)
                    -c.get("skore", 0.5))
        return min(kand, key=klic) if kand else None


def _usek(z, cid, od, do, pohyb, nabeh, dobeh):
    c = z.chv[cid]
    zac, d = z.vezmi(cid, do - od)
    return {"od": round(od, 3), "do": round(od + d, 3), "soubor": c["soubor"], "zacatek": round(zac, 3),
            "hdr": c.get("hdr", False), "prenos": c.get("prenos", ""), "pohyb": pohyb, "nabeh": round(nabeh, 3),
            "dobeh": round(dobeh, 3), "presah": 0.0, "zvuk": bool(c.get("zvuk")) and not pohyb.startswith("stab"),
            "chvilka": cid}


def naplanuj(vety, chvilky, prirazeni=None, jen_hlas=False, delka=None, vyhradit=(), tempo="bezne"):
    """vety: [(id_vety, [slova s start/end v čase reelu])] v pořadí reelu.
    chvilky: [{id, soubor, od, do, skore, energie, hdr, prenos, zvuk}] (zabery.chvilky nebo chvilky_ze_souboru).
    Starší tvar [(Path, info)] se převede sám. prirazeni: {id_vety: id chvilky nebo cesta souboru} (podle smyslu).
    vyhradit: id vět, které zůstávají s tváří (výzva). Vrátí úseky bez mezer mezi sebou, seřazené."""
    if chvilky and isinstance(chvilky[0], tuple):
        chvilky = chvilky_ze_souboru(chvilky)
    if not chvilky or not vety:
        return []
    t = TEMPA.get(tempo, TEMPA["bezne"])
    z = _Zasobnik(chvilky)
    prolnuti = t["prolnuti"] / FPS

    def k_chvilce(x):
        x = str(x)
        if x in z.chv:
            return x
        ze_souboru = [c for c in chvilky if c["soubor"] == x or Path(c["soubor"]).name.lower() == Path(x).name.lower()]
        return max(ze_souboru, key=lambda c: c.get("skore", 0))["id"] if ze_souboru else None

    prani = {vid: k_chvilce(x) for vid, x in (prirazeni or {}).items()}
    prani = {vid: cid for vid, cid in prani.items() if cid}
    # chvilky jen z přiřazení (stálá knihovna) se samy nedoplňují: jsou jen u věty, ke které je Claude dal
    auto = [c["id"] for c in chvilky if not c.get("jen_prirazeni")]
    pohyb_i = [0]

    def dalsi_pohyb():
        p = POHYBY[pohyb_i[0] % len(POHYBY)]
        pohyb_i[0] += 1
        return p

    out = []
    if jen_hlas:
        konec = delka or vety[-1][1][-1]["end"]
        hrany = [s[0]["start"] for _, s in vety if s] + [konec]
        hrany[0] = 0.0
        posledni = None
        od0 = 0.0
        # rychlý začátek
        n_auto = len(auto)
        if t["stab"] and n_auto >= 3 and vety[0][1]:
            stabu = (8 if tempo == "uderne" else 7) if n_auto >= 6 else 5
            cil = stabu * t["stab"]
            slova0 = vety[0][1]
            konec_burstu = next((w["end"] for w in slova0 if w["end"] >= cil - 0.1), slova0[-1]["end"])
            konec_burstu = min(konec_burstu, hrany[1])
            if konec_burstu >= 1.2:
                krok = konec_burstu / stabu
                uz = []
                for i in range(stabu):
                    cid = z.vyber(krok, posledni, "živá", vyloucit=[c for c in z.poradi if c not in auto] + uz[-(n_auto - 1):])
                    opak = cid in uz
                    uz.append(cid)
                    u = _usek(z, cid, i * krok, (i + 1) * krok, "stab-blize" if opak else "stab", 0.0, 0.0)
                    u["do"] = round((i + 1) * krok, 3)          # natvrdo, bez mezery
                    out.append(u)
                    posledni = u["soubor"]
                od0 = konec_burstu
        for j, (vid, slova) in enumerate(vety):
            od, konec_vety = max(hrany[j], od0), hrany[j + 1]
            while konec_vety - od > 0.3:
                do = konec_vety if konec_vety - od <= t["max"] + 0.8 else _konec_useku(slova, od, t["max"], t["min"])
                if do <= od + 0.3:
                    do = konec_vety
                cid = prani.get(vid) if od == max(hrany[j], od0) else None
                cid = cid or z.vyber(do - od, posledni, "klidná" if tempo == "procitene" else None,
                                     vyloucit=[c for c in z.poradi if c not in auto])
                ma = z.zbyva(cid, do - od)
                if ma < do - od:                                 # chvilka kratší: střih dřív, na hranici slova
                    kratsi = _konec_useku(slova, od, ma, min(t["min"], ma))
                    if od + 0.8 <= kratsi < do and konec_vety - kratsi > 0.6:
                        do = kratsi
                u = _usek(z, cid, od, do, dalsi_pohyb(), 0.0 if od < 0.01 else prolnuti, 0.0)
                if u["do"] < do - 0.01:                          # pořád kratší: zbytek doplní další záběr
                    do = u["do"]
                out.append(u)
                posledni = u["soubor"]
                od = do
            if out and konec_vety - od > 0.001:              # drobný zbytek věty: předchozí záběr potrvá déle
                out[-1]["do"] = round(konec_vety, 3)
        # prolínání: předchozí záběr zůstane pod dalším, dokud se přes něj nepřeloží
        for a, b in zip(out, out[1:]):
            if b["nabeh"] > 0 and abs(a["do"] - b["od"]) < 0.01:
                a["presah"] = round(b["nabeh"], 3)
        for u in out:
            u["sila"] = t["pohyb"]
        return out

    volne = [(vid, s) for vid, s in vety[1:] if s and vid not in vyhradit]
    if not volne:
        return []
    posledni = None
    for vid, s in volne:
        if vid in prani:
            out.append(_usek(z, prani[vid], s[0]["start"], _konec_useku(s, s[0]["start"], t["max"], t["min"]),
                             dalsi_pohyb(), prolnuti, prolnuti))
    obsazene = {i for i, (vid, _) in enumerate(volne) if vid in prani}
    kandidati = [i for i in range(len(volne)) if i not in obsazene and i - 1 not in obsazene and i + 1 not in obsazene]
    volne_auto = [c for c in auto if c not in prani.values()]
    if volne_auto and kandidati:
        n = min(len(volne_auto), (len(kandidati) + 1) // 2)
        krok = len(kandidati) / float(n)
        vybrane, predchozi = [], -9
        for j in range(n):
            i = kandidati[min(len(kandidati) - 1, int(j * krok + krok / 2))]
            if i - predchozi < 2 and i + 1 in kandidati:
                i += 1
            if i - predchozi < 2:
                continue
            vybrane.append(i)
            predchozi = i
        for i in vybrane:
            s = volne[i][1]
            do = _konec_useku(s, s[0]["start"], t["max"], t["min"])
            cid = z.vyber(do - s[0]["start"], posledni, vyloucit=[c for c in z.poradi if c not in volne_auto])
            u = _usek(z, cid, s[0]["start"], do, dalsi_pohyb(), prolnuti, prolnuti)
            out.append(u)
            posledni = u["soubor"]
    out.sort(key=lambda x: x["od"])
    for a, b in zip(out, out[1:]):
        b["od"] = max(b["od"], a["do"])
    out = [x for x in out if x["do"] - x["od"] >= 1.0]
    for u in out:
        u["sila"] = t["pohyb"]
    return out


def _pohyb_filtr(pohyb, d, sila):
    """Pohyb v záběru: výřez obrazu (přiblížení, oddálení, posun) s přesností pod pixel (perspective, kubicky).
    OVĚŘENO 24. 11. 2026: zoompan posouval po celých pixelech (krok 0 / 1,5 px, cukání), perspective plynule."""
    n = max(1, int(round(d * FPS)))
    if pohyb == "pribliz":
        z = "(1+%.4f*in/%d)" % (sila, n)
    elif pohyb == "oddal":
        z = "(%.4f-%.4f*in/%d)" % (1 + sila, sila, n)
    elif pohyb in ("posun-vpravo", "posun-vlevo"):
        z = "%.4f" % (1 + sila)
    elif pohyb == "stab-blize":
        z = "%.3f" % BLIZE
    else:
        return ""
    if pohyb.startswith("posun"):
        cast = ("in/%d" % n) if pohyb == "posun-vpravo" else ("(1-in/%d)" % n)
        x0 = "(W-W/%s)*%s" % (z, cast)
        x1 = "%s+W/%s" % (x0, z)
    else:
        x0, x1 = "W/2-W/(2*%s)" % z, "W/2+W/(2*%s)" % z
    y0, y2 = "H/2-H/(2*%s)" % z, "H/2+H/(2*%s)" % z
    return ("perspective=x0='%s':y0='%s':x1='%s':y1='%s':x2='%s':y2='%s':x3='%s':y3='%s':interpolation=cubic:eval=%s," %
            (x0, y0, x1, y0, x0, y2, x1, y2, "init" if pohyb == "stab-blize" else "frame"))


def filtr(p, vstup, vystup, base_in, base_out):
    """Řetězec filter_complex: záběr přes celý obraz v čase od..do (+ přesah pod dalším), s pohybem a prolnutím."""
    from .kontrola_videa import filtr_hdr
    d = p["do"] - p["od"]
    presah = float(p.get("presah", 0.0))
    celkem = d + presah
    barvy = ("," + filtr_hdr({"prenos": p.get("prenos")})) if p.get("hdr") else ""
    sila = float(p.get("sila", PRIBLIZENI))
    pohyb = _pohyb_filtr(p.get("pohyb", "pribliz"), celkem, sila)
    nabeh = float(p.get("nabeh", PROLNUTI_S))
    dobeh = 0.0 if presah > 0 else float(p.get("dobeh", PROLNUTI_S))
    prechody = ""
    if nabeh > 0:
        prechody += ",fade=t=in:st=0:d=%.3f:alpha=1" % nabeh
    if dobeh > 0:
        prechody += ",fade=t=out:st=%.4f:d=%.3f:alpha=1" % (max(0.0, celkem - dobeh), dobeh)
    return ("[%d:v]fps=%d,scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d%s,%s"
            "setsar=1,trim=duration=%.4f,format=yuva420p%s,setpts=PTS-STARTPTS+%.4f/TB[%s];"
            "[%s][%s]overlay=0:0:eof_action=pass:enable='between(t,%.4f,%.4f)'[%s]") % (
        vstup, FPS, SIRKA, VYSKA, SIRKA, VYSKA, barvy, pohyb, celkem, prechody, p["od"], vystup + "b",
        base_in, vystup + "b", p["od"], p["od"] + celkem, base_out)


def vstupy(prekryvy):
    """Vstupy ffmpeg pro záběry: úsek od zacatek, délka úseku (+ přesah), bez zvuku."""
    out = []
    for p in prekryvy:
        out += ["-ss", "%.4f" % p["zacatek"], "-t", "%.4f" % (p["do"] - p["od"] + float(p.get("presah", 0)) + 0.25),
                "-an", "-i", p["soubor"]]
    return out


# ---------- zvuk prostředí ----------

POD_HLASEM_LU = 20.0


def _lufs(cesta):
    r = subprocess.run(["ffmpeg", "-v", "info", "-nostdin", "-i", str(cesta), "-af", "loudnorm=print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+|-inf)"', r.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


def zvuk_prostredi(prekryvy, delka, cil):
    """Stopa se zvukem záběrů: každý kousek přesně na svém záběru, krátké náběhy a doběhy. None, když nic nezní."""
    kusy = [p for p in prekryvy if p.get("zvuk")]
    if not kusy:
        return None
    vstupy_, f = [], []
    for i, p in enumerate(kusy):
        d = p["do"] - p["od"] + float(p.get("presah", 0))
        vstupy_ += ["-ss", "%.4f" % p["zacatek"], "-t", "%.4f" % d, "-i", p["soubor"]]
        nab = min(0.25, d / 4)
        f.append("[%d:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:%.4f,asetpts=PTS-STARTPTS,"
                 "afade=t=in:d=%.3f,afade=t=out:st=%.4f:d=%.3f,adelay=%d:all=1[a%d]" %
                 (i, d, nab, max(0.0, d - 0.3), min(0.3, d / 3), int(round(p["od"] * 1000)), i))
    # bez atrim na konci: atrim za adelay/amix posunutí zahodí (OVĚŘENO 24. 11. 2026, ffmpeg 9), délku hlídá -t
    f.append("%samix=inputs=%d:normalize=0:duration=longest,apad=whole_dur=%.3f,highpass=f=80[out]" %
             ("".join("[a%d]" % i for i in range(len(kusy))), len(kusy), delka))
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin"] + vstupy_ +
                       ["-filter_complex", ";".join(f), "-map", "[out]", "-t", "%.3f" % delka, "-c:a", "pcm_s16le", str(cil)],
                       capture_output=True)
    return Path(cil) if r.returncode == 0 and Path(cil).exists() else None


def primichej_prostredi(hlas, prostredi, cil, pod=POD_HLASEM_LU):
    """Zvuk záběrů pod hlas: hlasitost změřená (pod LU pod hlasem), když se mluví, ztiší se ještě víc.
    Vrátí (cesta, zesílení v dB) nebo (None, None)."""
    lh, lp = _lufs(hlas), _lufs(prostredi)
    if lh is None or lp is None:
        return None, None
    zisk = max(-40.0, min(12.0, lh - pod - lp))
    f = ("[1:a]volume=%.2fdB,aformat=sample_rates=48000:channel_layouts=stereo[p];"
         "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[h1][h2];"
         "[p][h2]sidechaincompress=threshold=0.03:ratio=4:attack=25:release=400[d];"
         "[h1][d]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[out]" % zisk)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(hlas), "-i", str(prostredi),
                        "-filter_complex", f, "-map", "[out]", "-c:a", "pcm_s16le", str(cil)], capture_output=True)
    return (Path(cil), zisk) if r.returncode == 0 else (None, None)
