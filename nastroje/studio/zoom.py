"""Střídání velikosti záběru (přiblížení a oddálení), aby nebylo pořád stejné video.

Záběr se mění na každém střihu a v dlouhých úsecích na začátku věty (po MAX_CAST s). Obličej zůstává
na místě: zvětšuje se kolem svého středu, takže text umístěný mimo obličej zůstane mimo obličej.
Zdroj má jen 576x1024, proto jsou úrovně mírné (větší přiblížení zvětšuje měkkost).
Obraz se dělí na části (osa["casti"]), zvuk zůstává podle úseků, protože zvuk uvnitř úseku je souvislý.
"""
import numpy as np

from .titulky import FPS, SIRKA, VYSKA

UROVNE = [1.0, 1.18, 1.06, 1.28]   # dynamičtější střídání (Marcela 18. 10.)
MAX_CAST = 3.5     # delší část se rozdělí na začátku nejbližší věty (dřív 6,0)
MIN_CAST = 2.5
MISTO_POD_OBLICEJEM = VYSKA - 450 - 230   # pod obličejem musí zůstat místo na dva řádky titulků nad spodní zónou


def plan_zoomu(osa, rozmery, vzorky_klipu, urovne=UROVNE, max_cast=MAX_CAST):
    """Doplní osa["casti"]. rozmery: [(šířka, výška)] po otočení pro každý klip. vzorky_klipu: obličeje po klipech."""
    # začátky vět ve výstupním čase
    zacatky = {}
    for w in osa["slova"]:
        zacatky.setdefault(w["veta"], w["start"])
    casti, pocitadlo, posledni_zmena = [], 0, -10 ** 9
    # hranice částí: začátky úseků (střihy) a v dlouhých úsecích začátky vět
    kandidati = []
    for ui, u in enumerate(osa["useky"]):
        kandidati.append(round(u["vystup_od"] * FPS))
    for v, t0 in zacatky.items():
        kandidati.append(round((t0 - 0.05) * FPS))
    konec = round(osa["delka"] * FPS)
    meze = [0]
    for f in sorted(set(kandidati)):
        if f - meze[-1] >= max(MIN_CAST * FPS, 0) and konec - f >= MIN_CAST * FPS * 0.7 and \
                (f - meze[-1] >= max_cast * FPS or any(round(u["vystup_od"] * FPS) == f for u in osa["useky"])):
            meze.append(f)
    meze.append(konec)
    for a, b in zip(meze, meze[1:]):
        # část může překročit hranici úseku: rozděl ji na kousky podle úseků (zdroj je jiný)
        hranice = [a] + [round(u["vystup_od"] * FPS) for u in osa["useky"] if a < round(u["vystup_od"] * FPS) < b] + [b]
        z = urovne[pocitadlo % len(urovne)] if pocitadlo else 1.0
        pocitadlo += 1
        for fa, fb in zip(hranice, hranice[1:]):
            ui = max(i for i, u in enumerate(osa["useky"]) if round(u["vystup_od"] * FPS) <= fa)
            u = osa["useky"][ui]
            f0 = round(u["vystup_od"] * FPS)
            od = u["od"] + (fa - f0) / FPS
            delka = (fb - fa) / FPS
            c = {"usek": ui, "klip": u["klip"], "od": round(od, 4), "delka": round(delka, 4),
                 "vystup_od": round(fa / FPS, 4), "zoom": z, "posun_x": 0.0, "posun_y": 0.0, "snimku": fb - fa}
            if z != 1.0:
                v = [x for x in vzorky_klipu[u["klip"]] if od - 0.25 <= x["t"] <= od + delka + 0.25]
                if v:
                    cx = float(np.median([x["x"] + x["w"] / 2 for x in v]))
                    cy = float(np.median([x["y"] + x["h"] / 2 for x in v]))
                    # přiblížení jen tak, aby pod obličejem (i s bradou a krkem) zůstalo místo pro titulky:
                    # spodek rozšířeného obdélníku obličeje nesmí jít pod hranici MISTO_POD_OBLICEJEM
                    spodek = float(np.max([x["y"] + 1.25 * x["h"] for x in v]))
                    while z > 1.0 and VYSKA / 2 + (spodek - VYSKA / 2) * z + float(np.clip((VYSKA / 2 - cy) * (z - 1), -(z - 1) * VYSKA / 2, (z - 1) * VYSKA / 2)) > MISTO_POD_OBLICEJEM:
                        z = round(z - 0.03, 2)
                    if z < 1.04:
                        z = 1.0
                    c["zoom"] = z
                    c["posun_x"] = round(float(np.clip((SIRKA / 2 - cx) * (z - 1), -(z - 1) * SIRKA / 2, (z - 1) * SIRKA / 2)), 1)
                    c["posun_y"] = round(float(np.clip((VYSKA / 2 - cy) * (z - 1), -(z - 1) * VYSKA / 2, (z - 1) * VYSKA / 2)), 1)
            casti.append(c)
    osa["casti"] = casti
    osa["rozmery_klipu"] = [list(r) for r in rozmery]
    return casti


def plan_najezd(osa, od=1.0, do=1.12):
    """Pomalé souvislé přiblížení přes celý reel (vzhled jedno_slovo): každý úsek dostane zoom_od a zoom_do podle
    výstupního času, takže na střihu přiblížení plynule pokračuje. zoom (pro kontrolu textu proti obličeji) je
    hodnota na konci úseku, kde je obličej největší."""
    delka = max(float(osa["delka"]), 0.1)
    # skoky: [{"od", "do", "nasobek"}] = tvrdé přiblížení na chvíli (jako střih na detail), osa["skoky_zoom"]
    skoky = sorted(osa.get("skoky_zoom") or [], key=lambda s: s["od"])
    meze = sorted({round(x * FPS) for s in skoky for x in (s["od"], s["do"])})

    def nasobek(t):
        return next((s["nasobek"] for s in skoky if s["od"] <= t + 1e-6 < s["do"]), 1.0)

    casti = []
    for ui, u in enumerate(osa["useky"]):
        t0u = float(u.get("vystup_od", 0.0))
        f0, f1 = round(t0u * FPS), round((t0u + u["delka"]) * FPS)
        body = [f0] + [f for f in meze if f0 < f < f1] + [f1]
        for fa, fb in zip(body, body[1:]):
            t0, t1 = fa / FPS, fb / FPS
            k = nasobek(t0)
            z0 = (od + (do - od) * t0 / delka) * k
            z1 = (od + (do - od) * min(1.0, t1 / delka)) * k
            casti.append({"usek": ui, "klip": u["klip"], "od": round(u["od"] + (t0 - t0u), 4), "delka": round(t1 - t0, 4),
                          "vystup_od": round(t0, 4), "zoom": round(z1, 4), "zoom_od": round(z0, 5), "zoom_do": round(z1, 5),
                          "posun_x": 0.0, "posun_y": 0.0, "snimku": fb - fa})
    osa["casti"] = casti
    return casti


def filtr_casti(cast, w, h):
    """ffmpeg řetězec pro jednu část: zvětšení zdroje na (1080x1920 krát zoom) a ořez s posunem."""
    if "zoom_do" in cast:
        # souvislé přiblížení: velikost se počítá pro každý snímek (scale eval=frame), ořez vždy na střed
        s0 = max(SIRKA / w, VYSKA / h)
        z0, dz, d = cast["zoom_od"], cast["zoom_do"] - cast["zoom_od"], max(cast["delka"], 0.01)
        zt = "(%.5f+%.6f*t/%.4f)" % (z0, dz, d)
        return ("scale=w='2*ceil(%d*%.6f*%s/2)':h='2*ceil(%d*%.6f*%s/2)':eval=frame:flags=lanczos,"
                "crop=%d:%d:'(iw-ow)/2':'(ih-oh)/2'" % (w, s0, zt, h, s0, zt, SIRKA, VYSKA))
    z = cast["zoom"]
    s = max(SIRKA / w, VYSKA / h) * z
    W, H = int(np.ceil(w * s / 2) * 2), int(np.ceil(h * s / 2) * 2)
    x = int(np.clip((W - SIRKA) / 2 - cast["posun_x"], 0, W - SIRKA))
    y = int(np.clip((H - VYSKA) / 2 - cast["posun_y"], 0, H - VYSKA))
    return "scale=%d:%d:flags=lanczos,crop=%d:%d:%d:%d" % (W, H, SIRKA, VYSKA, x, y)


def transformuj(obdelnik, cast):
    """Obdélník v záběru bez zoomu přepočítá do záběru se zoomem a posunem (střed obrazu je pevný bod zvětšení)."""
    z, sx, sy = cast["zoom"], cast["posun_x"], cast["posun_y"]
    x0, y0, x1, y1 = obdelnik
    return (SIRKA / 2 + (x0 - SIRKA / 2) * z + sx, VYSKA / 2 + (y0 - VYSKA / 2) * z + sy,
            SIRKA / 2 + (x1 - SIRKA / 2) * z + sx, VYSKA / 2 + (y1 - VYSKA / 2) * z + sy)
