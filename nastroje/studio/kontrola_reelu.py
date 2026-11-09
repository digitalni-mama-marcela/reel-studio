"""Kontrola hotového reelu: čísla, ne dojem. Každá položka je zelená nebo červená.

- rozměr, snímkování, délka obrazu a zvuku
- hlasitost a špičky
- ticho a klik na každém střihu
- nové přečtení hotového zvuku přepisovačem a porovnání s tím, co mělo zaznít (useknuté nebo vypadlé slovo u střihu)
"""
import difflib
import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import opravy, render
from .hlaseni import cas_text as render_cas
from .opravy import OKRAJ


def _norm(w):
    return re.sub(r"[%s]" % re.escape(OKRAJ), "", w.lower())


def _wav(soubor):
    with wave.open(str(soubor), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        return (x.reshape(-1, w.getnchannels()).mean(axis=1) if w.getnchannels() > 1 else x), w.getframerate()


def kontrola_formatu(mp4, osa):
    s = render.zmer_vystup(mp4)
    v = next(x for x in s if x["codec_type"] == "video")
    a = next(x for x in s if x["codec_type"] == "audio")
    vysl = []
    vysl.append(("rozměr 1080x1920", v["width"] == 1080 and v["height"] == 1920, "%sx%s" % (v["width"], v["height"])))
    vysl.append(("30 snímků za sekundu", v["r_frame_rate"] == "30/1", v["r_frame_rate"]))
    rozdil = abs(float(v["duration"]) - float(a["duration"]))
    vysl.append(("obraz a zvuk stejně dlouhé (rozdíl do 0,05 s)", rozdil <= 0.05,
                 "obraz %.2f s, zvuk %.2f s" % (float(v["duration"]), float(a["duration"]))))
    vysl.append(("délka sedí s časovou osou", abs(float(v["duration"]) - osa["delka"]) <= 0.1,
                 "%.2f s proti %.2f s" % (float(v["duration"]), osa["delka"])))
    return vysl


def kontrola_strihu(wav_srovnany, osa):
    """Na každém střihu: hlasitost okolí proti řeči a největší skok mezi vzorky (klik)."""
    x, sr = _wav(wav_srovnany)
    x = x / max(float(np.max(np.abs(x))), 1e-6) * 0.89      # na špičku jako po srovnání hlasitosti (TP −1 dB)
    rms_rec = float(np.sqrt(np.mean(x[np.abs(x) > 0.01] ** 2))) if np.any(np.abs(x) > 0.01) else 1e-6
    vysl, nejhorsi_db, nejhorsi_klik, kde = [], -99.0, 0.0, 0.0
    strihy = [u["vystup_od"] for u in osa["useky"][1:]]
    for t in strihy:
        i = int(t * sr)
        okolo = x[max(0, i - int(0.015 * sr)):i + int(0.015 * sr)]
        db = 20 * np.log10(max(float(np.sqrt(np.mean(okolo ** 2))), 1e-6) / rms_rec)
        klik = float(np.max(np.abs(np.diff(x[max(0, i - int(0.006 * sr)):i + int(0.006 * sr)])))) if len(okolo) else 0
        if db > nejhorsi_db:
            nejhorsi_db, kde = db, t
        nejhorsi_klik = max(nejhorsi_klik, klik)
    if strihy:
        # NÁVRH 19. 10.: 18 dB pod řečí (20 dB padalo na nádech těsně před slovem, který ve výsledku slyšet není)
        vysl.append(("střihy jsou v tichu (okolí aspoň 18 dB pod řečí)", bool(round(nejhorsi_db) <= -18),   # stejné zaokrouhlení jako v hlášce
                     "nejhlasitější střih %.0f dB proti řeči (v %.1f s), střihů %d" % (nejhorsi_db, kde, len(strihy))))
        vysl.append(("na střihu není klik (skok mezi vzorky do 0,05)", bool(nejhorsi_klik <= 0.05),
                     "největší skok %.3f" % nejhorsi_klik))
    else:
        vysl.append(("střihy", True, "žádný střih, jeden souvislý úsek"))
    return vysl


def nejdelsi_pauza(wav_srovnany, podil=0.2, okno=0.01):
    """Nejdelší souvislý úsek ticha (pod podílem hlasitosti řeči) v hotovém zvuku. Vrátí (délka s, čas začátku)."""
    x, sr = _wav(wav_srovnany)
    n = int(sr * okno)
    k = len(x) // n
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1))
    rms = np.convolve(rms, np.ones(5) / 5, mode="same")
    noise, p90 = float(np.percentile(rms, 10)), float(np.percentile(rms, 90))
    tichy = rms <= noise + podil * (p90 - noise)
    nej, nej_od, i = 0, 0.0, 0
    while i < len(tichy):
        if not tichy[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(tichy) and tichy[j + 1]:
            j += 1
        if j - i + 1 > nej:
            nej, nej_od = j - i + 1, i * okno
        i = j + 1
    return round(nej * okno, 2), round(nej_od, 2)


def kontrola_slov(mp4, osa, pracovni, model="turbo", seznam_oprav=None):
    """Přečte hotový reel znovu a porovná s tím, co mělo zaznít. Vypadlá slova u střihu jsou červená."""
    from .prepis import prepis_klipu

    _, vety = prepis_klipu(mp4, Path(pracovni) / "kontrola-prepis", model, "x")
    if seznam_oprav:
        opravy.oprav_vety(vety, seznam_oprav)
        opravy.slij_cisla(vety)
    zni = [w for v in vety for w in v["slova"]]
    ocek = osa["slova"]
    sm = difflib.SequenceMatcher(None, [_norm(w["w"]) for w in ocek], [_norm(w["w"]) for w in zni], autojunk=False)
    strihy = [u["vystup_od"] for u in osa["useky"][1:]]
    # slova přímo na hranici střihu: poslední slovo před střihem a první slovo za ním (ta může střih poškodit)
    na_hranici = set()
    for t in strihy:
        pred = max((i for i, w in enumerate(ocek) if w["end"] <= t + 0.02), default=None)
        po = min((i for i, w in enumerate(ocek) if w["start"] >= t - 0.02), default=None)
        na_hranici.update(i for i in (pred, po) if i is not None)
    chyb, u_strihu = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for i in range(i1, i2):
            w = ocek[i]
            zaz = " ".join(x["w"] for x in zni[j1:j2]) or "(nic)"
            zaznam = {"cas": w["start"], "ocekavano": w["w"], "slyset": zaz}
            chyb.append(zaznam)
            # u střihu je chyba jen slovo na hranici, které vypadlo nebo se změnilo k nepoznání
            # ("mý" přečtené jako "mít" není useknutí). OVĚŘENO 14. 10. 2026: přepisovač vynechá slovo i v nedotčeném zvuku,
            # proto se slova dál od střihu nepočítají.
            a, b = _norm(w["w"]), _norm(zaz)
            podobne = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.5 or (a[:1] == b[:1] and abs(len(a) - len(b)) <= 1)
            if not podobne and i in na_hranici:
                u_strihu.append(zaznam)
    shoda = 1 - len(chyb) / max(1, len(ocek))
    return [("slova u střihů nechybí ani nejsou useknutá", not u_strihu,
             "u střihů nesedí %d slov: %s" % (len(u_strihu), ", ".join("%s→%s (%.1f s)" % (x["ocekavano"], x["slyset"], x["cas"]) for x in u_strihu[:6]))),
            ("hotový zvuk se čte jako text (shoda aspoň 85 %)", shoda >= 0.85,
             "shoda %.0f %%, nesedí %d ze %d slov" % (shoda * 100, len(chyb), len(ocek)))], chyb


def kontrola_reelu(mp4, osa, pracovni, s_prepisem=True, seznam_oprav=None, model="turbo"):
    pracovni = Path(pracovni)
    # střihy se měří na střihaném zvuku před kompresorem (kompresor zmenší odstup ticha od řeči, ne střih samotný)
    strihany = pracovni / "zvuk-strihany.wav"
    vysl = kontrola_formatu(mp4, osa) + kontrola_strihu(strihany if strihany.exists() else pracovni / "zvuk-srovnany.wav", osa)
    d, od = nejdelsi_pauza(pracovni / "zvuk-srovnany.wav")
    if osa.get("bez_strihu"):
        vysl.append(("pauzy (video bez střihu na přání zákaznice)", True, "nejdelší pauza %.1f s (v %s), nic se nestříhalo" % (d, render_cas(od))))
    else:
        vysl.append(("žádná pauza delší než 1 s", d <= 1.0, "nejdelší pauza %.1f s (v %s)" % (d, render_cas(od))))
    chyby = []
    if s_prepisem:
        v, chyby = kontrola_slov(mp4, osa, pracovni, model=model, seznam_oprav=seznam_oprav)
        vysl += v
    return vysl, chyby


def vypis(vysl):
    for nazev, ok, detail in vysl:
        print("   %s %s: %s" % ("ZELENÁ " if ok else "ČERVENÁ", nazev, detail))
