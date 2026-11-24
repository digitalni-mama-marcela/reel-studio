"""B-roll pod hlasem (Marcela 24. 11. 2026): hlas z mluveného videa běží dál, obraz na chvíli převezme jiný záběr.

Zákaznice dá záběry (MP4, MOV) do složky PODKLADY-SEM/B-ROLL v reelu. Studio je samo rozmístí po větách, nebo podle
jejího přání („záběr kavárny k větě 4“). Pravidla (kniha střihu studia, vlastní návrh):
- střih na záběr i zpátky přesně na začátku věty (hlas nikdy neskáče, mění se jen obraz);
- první věta (nadpis, tvář buduje důvěru) a věta s výzvou do komentáře zůstávají s tváří;
- jeden záběr 1,6 až 4 s, když je věta delší, vrátí se obraz zpátky na tvář v půlce věty na hranici slova;
- záběr se jemně přibližuje (4 % za záběr), nástup a odchod prolnutím 4 snímků;
- zvuk záběru je vypnutý, hlas zůstává; titulky, nadpis i efekty jedou dál nad záběrem;
- HDR z iPhonu se převede stejně jako hlavní video (kontrola_videa.filtr_hdr), otočení a rozměr ffmpeg srovná sám;
- z každého záběru se bere úsek od 0,4 s (začátek bývá roztřesený od dotyku na displej).
Režim „jen hlas“: záběry pokryjí celý reel, střídají se po větách (dlouhou větu rozdělí), tvář se neukáže vůbec.

Spec v osa["prekryvy"]: [{"od", "do", "soubor", "zacatek", "hdr", "prenos"}] v čase hotového reelu.
"""
from pathlib import Path

from .titulky import FPS, SIRKA, VYSKA

PRIPONY = {".mp4", ".mov", ".m4v"}
SLOZKA = "B-ROLL"
MIN_S, MAX_S = 1.6, 4.0
ZACATEK_S = 0.4
PRIBLIZENI = 0.04
PROLNUTI_S = 4 / FPS


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
    return {"delka": i["delka_s"], "hdr": bool(i["video"].get("hdr")), "prenos": i["video"].get("prenos", "")}


def _konec_useku(slova, od, max_s):
    """Konec úseku od času od: nejvýš max_s, na hranici slova (konec slova), aspoň MIN_S, když to věta dovolí."""
    konec = od
    for w in slova:
        if w["end"] <= od:
            continue
        if w["end"] - od > max_s and konec - od >= MIN_S:
            break
        konec = w["end"]
    return konec


def naplanuj(vety, soubory, prirazeni=None, jen_hlas=False, delka=None, vyhradit=()):
    """vety: [(id_vety, [slova s start/end v čase reelu])] v pořadí reelu. soubory: [(Path, info)].
    prirazeni: {id_vety: Path} (přání zákaznice). vyhradit: id vět, které zůstávají s tváří (nadpis, výzva).
    Vrátí seznam úseků {"od", "do", "soubor", "zacatek", "hdr", "prenos"} bez překryvu, seřazený."""
    if not soubory or not vety:
        return []
    zbyva = {str(p): inf["delka"] - ZACATEK_S for p, inf in soubory}
    inf_p = {str(p): inf for p, inf in soubory}
    poradi = [str(p) for p, _ in soubory]
    out = []

    def pridej(cesta, od, do):
        k = str(cesta)
        if k not in inf_p:
            return False
        do = min(do, od + max(zbyva[k], 0))
        if do - od < 1.0:
            return False
        zac = inf_p[k]["delka"] - ZACATEK_S - zbyva[k] + ZACATEK_S
        out.append({"od": round(od, 3), "do": round(do, 3), "soubor": k, "zacatek": round(zac, 3),
                    "hdr": inf_p[k]["hdr"], "prenos": inf_p[k]["prenos"]})
        zbyva[k] -= (do - od)
        return True

    if jen_hlas:
        i = 0
        hrany = [s[0]["start"] for _, s in vety if s] + [delka or vety[-1][1][-1]["end"]]
        hrany[0] = 0.0
        for j, (vid, slova) in enumerate(vety):
            od, konec_vety = hrany[j], hrany[j + 1]
            while konec_vety - od > 0.3:
                do = konec_vety if konec_vety - od <= MAX_S + 0.8 else _konec_useku(slova, od, MAX_S)
                if do <= od + 0.3:
                    do = konec_vety
                kand = [c for c in poradi[i:] + poradi[:i] if zbyva[c] >= min(1.0, do - od)]
                cesta = (prirazeni or {}).get(vid) or (kand[0] if kand else poradi[i % len(poradi)])
                if zbyva[str(cesta)] < do - od:      # záběr je kratší, začne znovu od začátku
                    zbyva[str(cesta)] = inf_p[str(cesta)]["delka"] - ZACATEK_S
                pridej(cesta, od, do)
                i = (poradi.index(str(cesta)) + 1) % len(poradi)
                od = do
        return out

    prirazeni = prirazeni or {}
    volne = [(vid, s) for vid, s in vety[1:] if s and vid not in vyhradit]
    if not volne:
        return []
    # přání zákaznice napřed, pak zbylé záběry rovnoměrně po zbylých větách (ne dvě věty za sebou)
    for vid, s in volne:
        if vid in prirazeni:
            pridej(prirazeni[vid], s[0]["start"], _konec_useku(s, s[0]["start"], MAX_S))
    zbyle = [p for p in poradi if p not in {str(v) for v in prirazeni.values()}]
    obsazene = {i for i, (vid, _) in enumerate(volne) if vid in prirazeni}
    kandidati = [i for i in range(len(volne)) if i not in obsazene]
    if zbyle and kandidati:
        n = min(len(zbyle), (len(kandidati) + 1) // 2)
        krok = len(kandidati) / float(n)
        vybrane, posledni = [], -9
        for j in range(n):
            i = kandidati[min(len(kandidati) - 1, int(j * krok + krok / 2))]
            if i - posledni < 2 and i + 1 in kandidati:
                i += 1
            vybrane.append(i)
            posledni = i
        for cesta, i in zip(zbyle, vybrane):
            s = volne[i][1]
            pridej(cesta, s[0]["start"], _konec_useku(s, s[0]["start"], MAX_S))
    out.sort(key=lambda x: x["od"])
    for a, b in zip(out, out[1:]):
        b["od"] = max(b["od"], a["do"])
    return [x for x in out if x["do"] - x["od"] >= 1.0]


def filtr(p, vstup, vystup, base_in, base_out):
    """Řetězec filter_complex: záběr přes celý obraz v čase od..do, s přiblížením a prolnutím."""
    from .kontrola_videa import filtr_hdr
    d = p["do"] - p["od"]
    barvy = (filtr_hdr({"prenos": p.get("prenos")}) + ",") if p.get("hdr") else ""
    z = "%d*(1+%.3f*t/%.3f)" % (SIRKA, PRIBLIZENI, max(d, 0.1))
    return ("[%d:v]%sfps=%d,scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,"
            "scale=w='trunc(%s/2)*2':h=-2:eval=frame:flags=bicubic,crop=%d:%d,setsar=1,trim=duration=%.4f,"
            "format=yuva420p,fade=t=in:st=0:d=%.3f:alpha=1,fade=t=out:st=%.4f:d=%.3f:alpha=1,"
            "setpts=PTS-STARTPTS+%.4f/TB[%s];"
            "[%s][%s]overlay=0:0:eof_action=pass:enable='between(t,%.4f,%.4f)'[%s]") % (
        vstup, barvy, FPS, SIRKA, VYSKA, SIRKA, VYSKA, z, SIRKA, VYSKA, d, PROLNUTI_S,
        max(0.0, d - PROLNUTI_S), PROLNUTI_S, p["od"], vystup + "b", base_in, vystup + "b", p["od"], p["do"], base_out)


def vstupy(prekryvy):
    """Vstupy ffmpeg pro záběry: úsek od zacatek, délka úseku, bez zvuku."""
    out = []
    for p in prekryvy:
        out += ["-ss", "%.4f" % p["zacatek"], "-t", "%.4f" % (p["do"] - p["od"] + 0.2), "-an", "-i", p["soubor"]]
    return out
