"""Výplňová slova a zvuky v mezerách mezi slovy: "ee", "mm", nádech, mlasknutí.

Přepisovač je do textu většinou nezapíše, ale v mluveném reelu zpomalují. Hledají se v mezerách mezi slovy
(podle časů slov) podle hlasitosti a znělosti zvuku. Co se najde, může střih vystříhnout. Co se nenajde
v tichém místě, kde jde střih udělat čistě, se nechá být.
"""
import wave

import numpy as np

HOP = 0.01
OKNO = 0.025


def nacti(wav_cesta):
    with wave.open(str(wav_cesta), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        return x, w.getframerate()


def znelost(x, sr, t0, t1):
    """Pro každý snímek (10 ms) v <t0, t1>: (energie, znělost 0..1). Znělost je normalizovaná autokorelace v pásmu 80 až 400 Hz."""
    delka = int(OKNO * sr)
    lag_min, lag_max = int(sr / 400), int(sr / 80)
    vys = []
    i = int(t0 / HOP)
    while (i * HOP + OKNO) <= t1 + 1e-9 or not vys:
        a = int(i * HOP * sr)
        f = x[a:a + delka]
        if len(f) < delka:
            break
        e = float(np.sqrt(np.mean(f * f)))
        f = f - f.mean()
        r0 = float(np.dot(f, f)) + 1e-12
        r = max(float(np.dot(f[:-l], f[l:])) for l in range(lag_min, lag_max, 2)) / r0
        vys.append((e, max(0.0, r)))
        i += 1
    return np.array(vys) if vys else np.zeros((0, 2))


def najdi_vypln(slova, x, sr, en, min_delka=0.10, okraj=0.03):
    """Vrátí události v mezerách mezi slovy.

    Každá událost: od, do, typ ('hlas' = znělý zvuk jako "ee", 'dech' = šum), mezera (číslo slova před, -1 na začátku),
    dalsi (číslo slova za, None na konci) a odstranit. Odstranit je pravda jen u zvuku, který před sebou i za sebou
    má ticho (čistý začátek a čistý konec). Zvuk, který navazuje plynule na slovo (dozvuk, protažené "ee" přímo
    před slovem), nejde vystřihnout čistě a nechá se, protože střih by byl uprostřed znělého zvuku.
    slova: seznam slov klipu v pořadí. en: hlasitost po 10 ms (strih.energie).
    """
    if not slova:
        return []
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    prah = noise + 0.20 * (p90 - noise)
    out = []
    hranice = [(-1, 0, 0.0, slova[0]["start"])]
    for i, (a, b) in enumerate(zip(slova, slova[1:])):
        hranice.append((i, i + 1, a["end"], b["start"]))
    hranice.append((len(slova) - 1, None, slova[-1]["end"], len(x) / sr))
    for pred, dalsi, g0, g1 in hranice:
        t0, t1 = g0 + okraj, g1 - okraj
        if t1 - t0 < min_delka:
            continue
        zn = znelost(x, sr, t0, t1)
        if not len(zn):
            continue
        hlasite = zn[:, 0] > prah
        i = 0
        while i < len(hlasite):
            if not hlasite[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(hlasite) and (hlasite[j + 1] or (j + 3 < len(hlasite) and hlasite[j + 3])):
                j += 1
            delka = (j - i + 1) * HOP
            if delka >= min_delka:
                usek = zn[i:j + 1]
                podil_znely = float((usek[:, 1] > 0.45).mean())
                out.append({"od": round(t0 + i * HOP, 3), "do": round(t0 + (j + 1) * HOP + (OKNO - HOP), 3),
                            "typ": "hlas" if podil_znely >= 0.5 else "dech",
                            "znely_podil": round(podil_znely, 2), "max_energie": round(float(usek[:, 0].max()), 4),
                            "mezera": pred, "dalsi": dalsi, "cisty_zacatek": i > 0, "cisty_konec": j < len(hlasite) - 1,
                            "odstranit": i > 0 and j < len(hlasite) - 1})
            i = j + 1
    return out
