"""Krok střih: z vybraných vět (a slov) udělá časovou osu (casova-osa.json), jediný zdroj pravdy pro MP4 i CapCut.

Střih se nedělá podle časů z přepisu (jsou přibližné: slovo "a" má v přepisu často 0,9 s, protože zahrnuje
ticho za sebou, OVĚŘENO 14. 10. 2026), ale přichytí se k nejtišší chvíli v signálu zvuku. Ticho do MAX_PAUZA
zůstane celé, delší ticho se zkrátí střihem: po řeči zůstane PO, před řečí PRED. Vynechaná věta, vynechaná slova
uvnitř věty a výplňové zvuky ("ee", mlasknutí) se vystřihnou tvrdým střihem v tichu.
Čas v časové ose je zaokrouhlený na snímky (30 fps), aby obraz a zvuk seděly.

Výběr: seznam (číslo klipu, id věty) v pořadí ve videu. Vynechat: {id věty: [pořadí slov od 0]} = slova,
která se z věty vystřihnou (fráze uvnitř věty, přeřeknutí). Střih uvnitř věty bez pauzy je označený jako
nejistý (jisty_vstup / jisty_vystup = false) a kontrola hotového souboru ho pak přečte znovu.

Sloučeno 14. 10. 2026 ze dvou relací: vynechání slov a úpravy z editoru (Fable) a zkracování pauz podle
skutečného ticha s výplňovými zvuky (reel klickrasy, testy/spike/klickrasy).
"""
import json
import wave
from pathlib import Path

import numpy as np

from . import vypln as _vypln

FPS = 30
OKNO = 0.01          # energie zvuku po 10 ms
PRED = 0.07          # kolik ticha nechat před řečí po střihu
PO = 0.12            # kolik ticha nechat za řečí před střihem
MAX_PAUZA = 0.30     # ticho do této délky se nechá celé, delší se zkrátí střihem (měřeno na klipu klientky)
KONEC_REELU = 0.30   # dozvuk za poslední větou
MIN_OKNO = 0.03      # kratší mezera mezi slovy se nehledá, střih jde přesně na hranici slova
MIN_CAST = 0.25      # kratší kus úseku se při zkracování ticha nevytváří
PODIL_TICHA = 0.20   # co je pod touhle částí hlasitosti řeči, je ticho (dech, šum)
PRESAH_PRED = 0.15   # o kolik smí okno střihu sahat přes konec sousedního slova (jeho čas bývá moc dlouhý)
MIN_ZBYTEK = 0.5     # kratší zbytek věty vedle vystřižené fráze se vystřihne taky (osamocené slůvko se ztrácí)
PRESAH_DO = 0.02     # o kolik smí střih sahat do začátku vlastního slova (čas začátku bývá o něco pozdě)
PODIL_RECI = 0.45    # co je pod touhle částí hlasitosti řeči mezi dvěma slovy, není řeč (dech, šustění)


def nacti_prepis(slozka):
    return json.loads((Path(slozka) / "prepis.json").read_text(encoding="utf-8"))["vety"]


def energie(wav_cesta):
    """Hlasitost (RMS) po 10 ms, mírně vyhlazená, aby krátké zavření hlásky uvnitř slova nebylo 'ticho'."""
    with wave.open(str(wav_cesta), "rb") as w:
        vz = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        sr = w.getframerate()
    n = int(sr * OKNO)
    k = len(vz) // n
    rms = np.sqrt((vz[:k * n].reshape(k, n) ** 2).mean(axis=1))
    return np.convolve(rms, np.ones(3) / 3, mode="same")


def zarovnej_slova_na_signal(vety, en, min_posun=0.15):
    """Přisune časy slov z přepisu ke skutečné řeči v signálu. OVĚŘENO 18. 10. 2026 na natáčení Marcely: začátek
    slova bývá v přepisu až o 1 s dřív, než řeč opravdu začne, a konec slova zahrnuje ticho za ním.
    Začátek slova ležící v tichu delším než min_posun se posune na první zvuk, konec v tichu zpět na poslední zvuk.
    Vrátí počet posunutých časů."""
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    hladke = np.convolve(en, np.ones(5) / 5, mode="same")
    tichy = hladke <= noise + PODIL_TICHA * (p90 - noise)
    rec = hladke > noise + PODIL_RECI * (p90 - noise)
    n = len(tichy)
    slova = [w for v in vety for w in v["slova"]]
    posunuto = 0
    for i, w in enumerate(slova):
        dalsi = slova[i + 1]["start"] if i + 1 < len(slova) else len(en) * OKNO
        a = int(w["start"] / OKNO)
        if 0 <= a < n and tichy[a]:
            b = a
            while b < n and tichy[b] and b * OKNO < dalsi - 0.05:
                b += 1
            if (b - a) * OKNO >= min_posun and b * OKNO < w["end"]:
                w["start"] = round(b * OKNO, 3)
                posunuto += 1
        e = int(w["end"] / OKNO) - 1
        if 0 <= e < n and tichy[e]:
            b = e
            while b > 0 and tichy[b] and b * OKNO > w["start"] + 0.05:
                b -= 1
            if (e - b) * OKNO >= min_posun:
                w["end"] = round((b + 1) * OKNO, 3)
                posunuto += 1
        elif 0 <= e < n:
            # přepis ukončil slovo dřív, než dozní (OVĚŘENO 19. 10.: „odkaz“ končilo v přepisu 0,45 s před koncem
            # zvuku a reel ho usekl): když do 0,15 s za koncem začíná řeč (hlasitost nad PODIL_RECI), konec jde
            # dopředu na konec té řeči, nejvýš 0,6 s a ne přes další slovo
            strop = min(n, int((dalsi - 0.03) / OKNO), int((w["end"] + 0.6) / OKNO))
            j = e + 1
            while j < min(strop, e + 1 + int(0.15 / OKNO)) and not rec[j]:
                j += 1
            if j < strop and rec[j]:
                b = j
                while b + 1 < strop and rec[b + 1]:
                    b += 1
                if (b + 1) * OKNO >= w["end"] + min_posun:
                    w["end"] = round((b + 1) * OKNO, 3)
                    posunuto += 1
    # krátké první slovo věty ("A", "Jo") přilepené přepisem k předchozí větě: když za ním je dlouhé ticho a druhé
    # slovo začíná až po něm, patří první slovo těsně před druhé (OVĚŘENO: "A díky za follow. | A ... nakonec")
    for v in vety:
        s = v["slova"]
        if len(s) >= 2 and len(_norm_slovo(s[0]["w"])) <= 3 and s[1]["start"] - s[0]["end"] >= 1.0:
            b = int(s[1]["start"] / OKNO) - 1
            while b > 0 and not tichy[b] and b * OKNO > s[0]["end"]:
                b -= 1
            zac = (b + 1) * OKNO
            if s[0]["end"] < zac < s[1]["start"] - 0.03:
                s[0]["start"], s[0]["end"] = round(zac, 3), round(s[1]["start"], 3)
                posunuto += 1
            elif s[0]["end"] < s[1]["start"]:
                # první slovo splývá s druhým v jednom zvuku: dej mu prvních 80 ms toho zvuku
                s[0]["start"], s[0]["end"] = round(s[1]["start"], 3), round(s[1]["start"] + 0.08, 3)
                s[1]["start"] = round(s[1]["start"] + 0.08, 3)
                posunuto += 1
    for v in vety:
        if v["slova"]:
            v["start"], v["end"] = v["slova"][0]["start"], v["slova"][-1]["end"]
    return posunuto


def _norm_slovo(w):
    import re as _re
    return _re.sub(r"[^\wáčďéěíňóřšťúůýž]", "", w.lower())


def priprav_klip(cesta, vety, wav_cesta, delka, odstran_vypln=True):
    """Klip pro střih: energie zvuku, časy slov přisunuté k řeči a výplňové zvuky mezi slovy (vypln.py). Id vět se nemění."""
    en = energie(wav_cesta)
    zarovnej_slova_na_signal(vety, en)
    slova = [w for v in vety for w in v["slova"]]
    vypl = []
    if odstran_vypln and slova:
        x, sr = _vypln.nacti(wav_cesta)
        vypl = _vypln.najdi_vypln(slova, x, sr, en)
    return {"cesta": str(cesta), "vety": vety, "en": en, "delka": delka, "vypln": vypl}


def za_doznenim(hladke, noise, p90, t, strop):
    """Konec řeči i s tichým dozněním: poslední zvuk nad 6 % hlasitosti řeči v okně <t, strop> (nejvýš 0,5 s), + 60 ms.
    Tiché doznění posledního slova („Claude?“, „-ství“, „-mi“) je mezi 10 a 40 % hlasitosti řeči, tedy pod prahem
    řeči i ticha, a střih ho usekával (OVĚŘENO 29. 10. 2026, Marcela: „chybí poslední slova vět“, 6 z 18 střihů).
    Doznění může mít krátký propad, proto poslední zvuk v okně, ne první ticho. Vrátí nový čas (nikdy dřív než t)."""
    b = int(t / OKNO)
    e = min(len(hladke), int(min(strop, t + 0.5) / OKNO))
    if b >= e:
        return t
    # Když za slovem zbývá aspoň 0,3 s místa (konec části nebo dlouhá pauza), práh 1,5 %: koncová souhláska
    # „Claude“ doznívala 32 dB pod řečí a střih ji usekl (OVĚŘENO 2. 11. 2026, kontrola slov četla „klo“)
    podil = 0.015 if strop - t >= 0.3 else 0.06
    zvuk = np.where(hladke[b:e] > noise + podil * (p90 - noise))[0]
    if not len(zvuk):
        return t
    return max(t, min((b + int(zvuk[-1]) + 1) * OKNO + 0.06, strop))


def tiche_misto(en, od, do, cil):
    """Čas nejtišší části okna <od, do>, nejblíž času cil. Vrátí (čas, jistota). Bez okna vrátí cil (v mezích) bez jistoty.

    Hledá nejdřív co nejtišší místo (4, 8, pak 15 % rozsahu) a chce ticho i 20 ms kolem střihu.
    """
    cil = min(max(cil, od), max(od, do))
    i0 = max(0, int(od / OKNO))
    i1 = max(i0 + 1, int(do / OKNO))
    ok = en[i0:i1]
    if len(ok) < 3:
        return cil, False
    mn = float(ok.min())
    p90 = float(np.percentile(en, 90))
    kand, jiste = np.array([], dtype=int), False
    for faktor in (0.04, 0.08, 0.15):
        maska = ok <= mn + faktor * (p90 - mn)
        stabilni = np.convolve(maska.astype(int), np.ones(5, dtype=int), mode="same") == 5
        kand = np.where(stabilni)[0] if stabilni.any() else np.where(maska)[0]
        if stabilni.any():
            jiste = True
            break
    # ticho musí být opravdu tiché: aspoň 20 dB pod hlasitou řečí (stejná mez jako kontrola hotového reelu;
    # 12 dB pouštělo střih do nádechu, OVĚŘENO 19. 10. reel 3)
    if jiste and ok[kand].min() > p90 * 0.1:
        jiste = False
    i = kand[np.argmin(np.abs((i0 + kand) * OKNO + OKNO / 2 - cil))]
    return (i0 + i) * OKNO + OKNO / 2, jiste


def vnitrni_ticha(en, od, do, min_delka=MAX_PAUZA):
    """Úseky skutečného ticha uvnitř <od, do> dlouhé aspoň min_delka (podle hlasitosti, ne podle časů slov).
    Vrátí seznam (začátek, konec) v sekundách."""
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    # Dech a šum mezi slovy (OVĚŘENO 18. 10. 2026 na natáčení Marcely: 14 až 28 % hlasitosti řeči) je pauza,
    # ne řeč. Hranice 20 % s vyhlazením 50 ms; uvnitř slov to nic nového nenajde (ověřeno na obou klipech).
    prah = noise + PODIL_TICHA * (p90 - noise)
    hladke = np.convolve(en, np.ones(5) / 5, mode="same")
    i0, i1 = int(od / OKNO), int(do / OKNO)
    tichy = hladke[i0:i1] <= prah
    out, i = [], 0
    while i < len(tichy):
        if not tichy[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(tichy) and tichy[j + 1]:
            j += 1
        if (j - i + 1) * OKNO >= min_delka:
            out.append(((i0 + i) * OKNO, (i0 + j + 1) * OKNO))
        i = j + 1
    return out


def mezery_mezi_slovy(en, slova, od, do):
    """Pauzy mezi sousedními slovy delší než MAX_PAUZA, měřené od skutečného konce řeči za slovem po skutečný začátek
    řeči před dalším slovem (hlasitost pod PODIL_RECI není řeč). OVĚŘENO 19. 10. 2026: mezi „video,“ a „klidně“
    zůstalo 1,4 s dechu a šustění, které práh ticha PODIL_TICHA nepoznal. Vrátí seznam (začátek, konec) pauz."""
    if len(slova) < 2:
        return []
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    hladke = np.convolve(en, np.ones(5) / 5, mode="same")
    rec = hladke > noise + PODIL_RECI * (p90 - noise)
    n = len(rec)
    out = []
    for a, b in zip(slova, slova[1:]):
        if b["start"] - a["end"] <= MAX_PAUZA or a["end"] < od or b["start"] > do:
            continue
        lo, hi = max(0, int((a["end"] - 0.3) / OKNO)), min(n, int((a["end"] + 0.35) / OKNO))
        hl = np.where(rec[lo:hi])[0]
        konec_a = (lo + hl[-1] + 1) * OKNO if len(hl) else a["end"]
        lo, hi = max(0, int((b["start"] - 0.35) / OKNO)), min(n, int((b["start"] + 0.1) / OKNO))
        hl = np.where(rec[lo:hi])[0]
        zacatek_b = (lo + hl[0]) * OKNO if len(hl) else b["start"]
        if zacatek_b - konec_a > MAX_PAUZA:
            # body střihu v opravdovém tichu (OVĚŘENO 19. 10.: střih hned za hlasitou částí sekl do dozvuku „vypadat“)
            x, jx = tiche_misto(en, konec_a, min(zacatek_b, konec_a + 0.4), konec_a + PO)
            x = za_doznenim(hladke, noise, p90, x, zacatek_b - PRED - 0.05)
            y, jy = tiche_misto(en, max(konec_a, zacatek_b - 0.4), zacatek_b, zacatek_b - PRED)
            if not jy:
                # před slovem je nádech: pauza skončí v posledním opravdu tichém místě před ním, nádech zůstane
                i_x, i_b = int(x / OKNO), int(zacatek_b / OKNO)
                tiche = np.where(hladke[i_x:i_b] <= noise + 0.1 * (p90 - noise))[0]
                if len(tiche):
                    y, jy = (i_x + tiche[-1]) * OKNO, True
            # jen když jsou oba body v jistém tichu (OVĚŘENO 19. 10., reel 3: časy slov z přepisu byly posunuté
            # a střih by šel doprostřed slova)
            if jx and jy and y - x > MAX_PAUZA:
                out.append((float(max(od, x)), float(min(do, y))))
    return [(round(x, 3), round(y, 3)) for x, y in out if y - x > 0.05]


def rozdel_na_ticha(en, od, do, slova=None):
    """Rozdělí úsek <od, do> na části bez dlouhého ticha. Po řeči zůstane PO, před řečí PRED ticha.
    slova: slova úseku (zdrojové časy); pauzy mezi nimi se zkrátí i s tichými zvuky uvnitř (mezery_mezi_slovy)."""
    casti, zacatek = [], od
    # okraje pauzy do opravdového ticha (20 dB pod řečí, stejná mez jako kontrola): střih po PO za řečí a PRED před ní
    # nesmí sedět v dozvuku nebo nádechu (OVĚŘENO 19. 10. reel 3, střih −16 dB)
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    hladke = np.convolve(en, np.ones(5) / 5, mode="same")
    tiche20 = hladke <= noise + 0.1 * (p90 - noise)
    pauzy = []
    for a, b in vnitrni_ticha(en, od, do):
        i0, i1 = int((a + PO) / OKNO), int((b - PRED) / OKNO)
        idx = np.where(tiche20[i0:i1])[0]
        if len(idx):
            konec_reci = za_doznenim(hladke, noise, p90, (i0 + idx[0]) * OKNO, (i0 + idx[-1] + 1) * OKNO - 0.05)
            pauzy.append((konec_reci, (i0 + idx[-1] + 1) * OKNO))
    for x, y in mezery_mezi_slovy(en, slova or [], od, do):
        pauzy = [(a, b) for a, b in pauzy if not (a >= x - 0.02 and b <= y + 0.02)]   # tichá místa uvnitř pauzy
        pauzy.append((x, y))
    pauzy.sort()
    for konec_casti, nova_zacatek in pauzy:
        if konec_casti >= nova_zacatek - 0.02 or konec_casti - zacatek < MIN_CAST or do - nova_zacatek < MIN_CAST:
            continue
        if konec_casti < zacatek:      # překryv s předchozí pauzou
            continue
        casti.append((zacatek, konec_casti))
        zacatek = nova_zacatek
    casti.append((zacatek, do))
    return casti


def _globalni_indexy(vety):
    """{(index věty, pořadí slova): pořadí slova v celém klipu} (tak čísluje slova vypln.najdi_vypln)."""
    g, out = 0, {}
    for i, v in enumerate(vety):
        for j in range(len(v["slova"])):
            out[(i, j)] = g
            g += 1
    return out


def _vypln_k_odstraneni(klip):
    """Výplňové zvuky k vystřižení, jen ty, které časově opravdu leží mezi slovy, na která ukazují.
    OVĚŘENO 19. 10. (reel 3): po přisunutí časů slov k signálu ukazoval dech z 39,6 s na slova ve 41 s
    a střih rozdělil větu uprostřed řeči."""
    slova = [w for v in klip.get("vety", []) for w in v["slova"]]
    out = []
    for e in klip.get("vypln", []):
        if not e.get("odstranit"):
            continue
        m, d = e.get("mezera"), e.get("dalsi")
        if m is not None and 0 <= m < len(slova) and e["od"] < slova[m]["end"] - 0.3:
            continue
        if d is not None and 0 <= d < len(slova) and e["do"] > slova[d]["start"] + 0.3:
            continue
        out.append(e)
    return out


def hranice_slov(vety, idx, j, k, en, delka_klipu, vypln=None, gidx=None):
    """Nejlepší místo střihu před slovem j a za slovem k-1 věty idx. Vrátí (vstup, výstup, jistota_vstupu, jistota_výstupu).

    Okno se hledá mezi koncem předchozího slova (nebo věty) a začátkem prvního slova úseku. Když mezi slovy
    není žádná mezera, střih jde přesně na hranici slova a je označený jako nejistý. Výplňový zvuk k odstranění
    těsně před prvním slovem nebo těsně za posledním slovem střih vyhne (začne až za ním, skončí před ním).
    """
    v = vety[idx]
    slova = v["slova"]
    prev_end = slova[j - 1]["end"] if j > 0 else (vety[idx - 1]["end"] if idx > 0 else 0.0)
    next_start = slova[k]["start"] if k < len(slova) else (vety[idx + 1]["start"] if idx + 1 < len(vety) else delka_klipu)
    s, e = slova[j]["start"], slova[k - 1]["end"]
    g_prvni = gidx[(idx, j)] if gidx else None
    g_posledni = gidx[(idx, k - 1)] if gidx else None
    pred = [x for x in (vypln or []) if x["dalsi"] == g_prvni]
    po = [x for x in (vypln or []) if x["mezera"] == g_posledni]
    # Časy slov z přepisu jsou přibližné (OVĚŘENO: slovo může ve zvuku začít o 0,3 s dřív, konec často zahrnuje ticho).
    # Proto se okno pro střih přesahuje přes hranice slov a o tichu rozhoduje signál (stabilní ticho 50 ms).
    od, do = max(0.0, prev_end - PRESAH_PRED, s - 0.40), s + PRESAH_DO
    if j == 0 and idx == 0:
        od = max(0.0, s - 0.40)
    if pred:
        posledni = max(pred, key=lambda x: x["do"])
        if posledni["do"] >= s - 0.05:
            vst, j1 = max(posledni["do"] - 0.01, 0.0), True
            od = do    # okno se nehledá
        else:
            od = max(od, posledni["do"])
    if od < do - MIN_OKNO:
        vst, j1 = tiche_misto(en, od, do, s - PRED)
    elif not pred:
        vst, j1 = s, False
    vst = min(max(vst, 0.0), s + PRESAH_DO)
    od, do = max(e - PRESAH_DO, 0.0), min(next_start + PRESAH_PRED, e + 0.45, delka_klipu)
    if po:
        prvni = min(po, key=lambda x: x["od"])
        do = min(do, prvni["od"] - 0.005)
    # OVĚŘENO 19. 10. (Marcela: „a nakonec“ dvakrát): za posledním slovem klipu začala další věta („A nakonec“),
    # kterou přepis nezachytil, a kousek z ní („A“) zůstal v reelu. Když se za slovem po mezeře aspoň 80 ms ozve
    # další řeč ještě před koncem okna, okno střihu končí v té mezeře.
    noise = float(np.percentile(en, 10))
    p90 = float(np.percentile(en, 90))
    hladke = np.convolve(en, np.ones(5) / 5, mode="same")
    rec = hladke > noise + PODIL_RECI * (p90 - noise)
    i_do = min(len(rec), int(do / OKNO))
    stred = min(len(rec) - 1, int((slova[k - 1]["start"] + e) / 2 / OKNO))
    kb = stred
    while kb + 1 < i_do and rec[kb + 1]:
        kb += 1                                              # konec souvislé řeči těla slova
    j = kb + 1
    while j < i_do and not rec[j]:
        j += 1                                               # první hlasitý vzorek po mezeře
    cil = min(e + PO, do)
    spodni = e - PRESAH_DO                   # pod tohle střih nejde (konec slova z přepisu)
    telo_konec = (kb + 1) * OKNO
    if j < i_do and (j - kb - 1) * OKNO >= 0.08:
        do = min(do, telo_konec + (j - kb - 1) * OKNO * 0.9)
        od = min(od, max(0.0, telo_konec - PRESAH_DO))
    # Přepis natáhl konec slova přes mezeru a tichý zbytek rozjeté další věty („nadpis. | a“, OVĚŘENO 19. 10.).
    # Pozor na tiché koncovky („-s“) a tiše dořečená slova („odkaz“): ty nejsou nad prahem řeči, ale nejsou ani
    # ticho. Proto se hledá skutečné ticho (pod PODIL_TICHA) aspoň 80 ms za tělem slova a po něm další zvuk
    # (nad PODIL_TICHA) ještě před koncem z přepisu; střih pak jde do nejtiššího místa té mezery.
    tichy = hladke <= noise + PODIL_TICHA * (p90 - noise)
    if e - telo_konec > 0.15:
        g0 = kb + 1
        while g0 < i_do and not tichy[g0]:
            g0 += 1                                          # konec koncovky slova (první tichý vzorek)
        g1 = g0
        while g1 < i_do and tichy[g1]:
            g1 += 1                                          # konec mezery (první další zvuk)
        if g1 < min(i_do, int(e / OKNO) + 3) and (g1 - g0) * OKNO >= 0.08:
            od = min(od, max(0.0, g0 * OKNO - PRESAH_DO))
            do = min(do, g1 * OKNO - 0.02)
            cil = (g0 + g1) / 2 * OKNO
            spodni = g0 * OKNO - PRESAH_DO
    if do - od >= MIN_OKNO:
        vyst, j2 = tiche_misto(en, od, do, min(cil, do))
    else:
        vyst, j2 = e, False
    vyst = max(min(vyst, do if do > spodni else e), spodni)
    # tiché doznění posledního slova zůstane (za_doznenim), nejblíž 0,05 s před další slovo
    po_dozneni = za_doznenim(hladke, noise, p90, vyst, min(next_start - 0.05, delka_klipu))
    if po_dozneni > vyst:
        vyst, j2 = po_dozneni, True
    return vst, vyst, j1, j2


def hranice_vety(vety, idx, en, delka_klipu):
    """Nejlepší místo střihu před a za celou větou číslo idx (zachováno kvůli starším voláním)."""
    return hranice_slov(vety, idx, 0, len(vety[idx]["slova"]), en, delka_klipu)


def na_snimky(d):
    return max(1, round(d * FPS)) / FPS


def delka_na_snimky(d, vstup, en):
    """Délka úseku zaokrouhlená na celé snímky. Ze dvou možností (dolů a nahoru) vybere tu, kde je střih tišší."""
    dolu, nahoru = max(1, int(d * FPS)) / FPS, max(1, int(d * FPS) + 1) / FPS

    def hlasitost(x):
        i = min(len(en) - 1, int((vstup + x) / OKNO))
        return float(en[max(0, i - 1):i + 2].mean())

    return dolu if hlasitost(dolu) <= hlasitost(nahoru) else nahoru


def bloky_slov(klipy, vyber, vynechat=None):
    """Výběr vět na bloky souvislých slov: (klip, index věty, od slova, do slova).
    Vynechaná slova blok rozdělí. Výplňový zvuk k odstranění mezi dvěma slovy věty blok taky rozdělí (vystřihne se)."""
    vynechat = vynechat or {}
    index = [{v["id"]: i for i, v in enumerate(k["vety"])} for k in klipy]
    gidx = [_globalni_indexy(k["vety"]) for k in klipy]
    rezy = [set() for _ in klipy]
    for c, k in enumerate(klipy):
        for e in _vypln_k_odstraneni(k):
            if e["dalsi"] is not None and e["mezera"] is not None and e["dalsi"] == e["mezera"] + 1:
                rezy[c].add(e["dalsi"])
    bloky = []
    for c, vid in vyber:
        i = index[c][vid]
        n = len(klipy[c]["vety"][i]["slova"])
        ven = set(vynechat.get(vid, ()))
        j = 0
        while j < n:
            if j in ven:
                j += 1
                continue
            k = j + 1
            while k < n and k not in ven and gidx[c][(i, k)] not in rezy[c]:
                k += 1
            bloky.append((c, i, j, k))
            j = k
    return bloky


def skupiny_bloku(klipy, bloky):
    """Spojí bloky, které na sebe v klipu přímo navazují (celá věta za větou, bez výplně mezi nimi) do jednoho úseku.
    Dlouhé ticho mezi nimi se zkrátí až při skládání osy (rozdel_na_ticha)."""
    gidx = [_globalni_indexy(k["vety"]) for k in klipy]
    skupiny = []
    for b in bloky:
        c, i, j, k = b
        if skupiny:
            pc, pi, pj, pk = skupiny[-1][-1]
            vety = klipy[c]["vety"]
            if pc == c and i == pi + 1 and pk == len(vety[pi]["slova"]) and j == 0:
                g_pred, g_po = gidx[c][(pi, pk - 1)], gidx[c][(i, 0)]
                bez_vypln = not any(e["mezera"] == g_pred and e["dalsi"] == g_po for e in _vypln_k_odstraneni(klipy[c]))
                if bez_vypln:
                    skupiny[-1].append(b)
                    continue
        skupiny.append([b])
    return skupiny


def slij_kratke_mezery(casti, min_mezera=0.12):
    """Části jednoho úseku, mezi kterými by se vystřihlo méně než min_mezera s, se spojí. Tak krátké ticho
    divák nepozná, ale střih v něm ukousl začátek další hlásky („Studio“ bez „S“, OVĚŘENO 2. 11. 2026)."""
    vysl = []
    for ca, cb in casti:
        if vysl and ca - vysl[-1][1] < min_mezera:
            vysl[-1] = (vysl[-1][0], cb)
        else:
            vysl.append((ca, cb))
    return vysl


def sestav_osu(klipy, vyber, hook=None, vsuvky=None, vynechat=None):
    """klipy: seznam slovníků {cesta, vety, en, delka, vypln (volitelně)}. vyber: seznam (číslo klipu, id věty) v pořadí ve videu.
    vynechat: {id věty: [pořadí slov]} slova, která se vystřihnou.

    Vrátí časovou osu. Souvislé věty z jednoho klipu tvoří jeden úsek; dlouhé ticho uvnitř úseku se zkrátí
    (úsek se rozdělí na části, každá část je samostatný úsek osy).
    """
    gidx = [_globalni_indexy(k["vety"]) for k in klipy]
    skupiny = skupiny_bloku(klipy, bloky_slov(klipy, vyber, vynechat))
    useky, slova, vystup_od = [], [], 0.0
    for g in skupiny:
        c = g[0][0]
        k = klipy[c]
        vyp = _vypln_k_odstraneni(k)
        _, i0, j0, k0 = g[0]
        _, i1, j1_, k1 = g[-1]
        vst, _, jist1, _ = hranice_slov(k["vety"], i0, j0, k0, k["en"], k["delka"], vyp, gidx[c])
        _, vyst, _, jist2 = hranice_slov(k["vety"], i1, j1_, k1, k["en"], k["delka"], vyp, gidx[c])
        if g is skupiny[-1]:
            vyst = max(vyst, k["vety"][i1]["slova"][k1 - 1]["end"] + KONEC_REELU)
        vst = max(0.0, vst)
        vyst = min(k["delka"], vyst)
        ids = []
        for _, i, _, _ in g:
            if k["vety"][i]["id"] not in ids:
                ids.append(k["vety"][i]["id"])
        cele = all(j == 0 and kk == len(k["vety"][i]["slova"]) for _, i, j, kk in g)
        veta_slova = [(k["vety"][i]["id"], w) for _, i, j, kk in g for w in k["vety"][i]["slova"][j:kk]]
        casti = slij_kratke_mezery(rozdel_na_ticha(k["en"], vst, vyst, [w for _, w in veta_slova]))
        for n, (ca, cb) in enumerate(casti):
            d = delka_na_snimky(cb - ca, ca, k["en"])
            u = {"klip": c, "od": round(ca, 3), "do": round(ca + d, 3), "vystup_od": round(vystup_od, 3),
                 "delka": round(d, 4), "vety": ids if n == 0 else [], "cele_vety": cele, "cast": n + 1, "casti": len(casti),
                 "jisty_vstup": bool(jist1) if n == 0 else True, "jisty_vystup": bool(jist2) if n == len(casti) - 1 else True}
            useky.append(u)
            dalsi_od = casti[n + 1][0] if n + 1 < len(casti) else None
            for vid, w in veta_slova:
                if ca - 0.05 <= w["start"] < (cb + 0.01 if dalsi_od is None else dalsi_od - 0.05):
                    slova.append({"w": w["w"], "start": round(vystup_od + max(0.0, w["start"] - ca), 3),
                                  "end": round(vystup_od + min(d, w["end"] - ca), 3), "veta": vid, "p": w.get("p")})
            vystup_od += d
    return {"verze": 1, "fps": FPS, "sirka": 1080, "vyska": 1920,
            "klipy": [k["cesta"] for k in klipy], "useky": useky, "slova": slova,
            "delka": round(vystup_od, 3), "hook": hook, "vsuvky": vsuvky or [],
            "vyber": [[c, vid] for c, vid in vyber], "vynechat": {k: sorted(v) for k, v in (vynechat or {}).items() if v}}


def osa_cela(klipy, vyber=None):
    """Osa bez jakéhokoli střihu: každý klip celý od začátku do konce, slova všech vět (Marcela 20. 10.:
    „použij původní verzi a nijak to nezkracuj“). vyber jen určuje pořadí klipů (klip se bere celý, jednou)."""
    poradi = []
    for c, _ in (vyber or [(i, None) for i in range(len(klipy))]):
        if c not in poradi:
            poradi.append(c)
    useky, slova, vystup_od = [], [], 0.0
    for c in poradi:
        k = klipy[c]
        d = round(round(k["delka"] * FPS) / FPS, 4)
        useky.append({"klip": c, "od": 0.0, "do": d, "vystup_od": round(vystup_od, 3), "delka": d,
                      "vety": [v["id"] for v in k["vety"]], "cele_vety": True, "cast": 1, "casti": 1, "jisty_vstup": True, "jisty_vystup": True})
        for v in k["vety"]:
            for w in v["slova"]:
                slova.append({"w": w["w"], "start": round(vystup_od + w["start"], 3), "end": round(vystup_od + min(d, w["end"]), 3),
                              "veta": v["id"], "p": w.get("p")})
        vystup_od += d
    return {"verze": 1, "fps": FPS, "sirka": 1080, "vyska": 1920, "klipy": [k["cesta"] for k in klipy], "useky": useky, "slova": slova,
            "delka": round(vystup_od, 3), "hook": None, "vsuvky": [], "vyber": [[c, v["id"]] for c in poradi for v in klipy[c]["vety"]], "vynechat": {},
            "bez_strihu": True}


def rozsir_vynechat_do_ticha(klipy, vyber, vynechat, max_slov=2):
    """Střih jen v tichu: když vystřižená fráze uvnitř věty nemá na kraji pauzu, vystřihne se i sousední slovo
    (nejvýš max_slov na každé straně), dokud střih nepadne do ticha. Vrátí (nové vynechat, seznam hlášení)."""
    if not vynechat:
        return {}, []
    index = {v["id"]: (c, i) for c, k in enumerate(klipy) for i, v in enumerate(k["vety"])}
    nove, hlaseni = {}, []
    for vid, idx in vynechat.items():
        if vid not in index or not idx:
            continue
        c, i = index[vid]
        k = klipy[c]
        slova = k["vety"][i]["slova"]
        gidx = _globalni_indexy(k["vety"])
        vyp = _vypln_k_odstraneni(k)
        ven = set(x for x in idx if 0 <= x < len(slova))
        pridano = []
        for smer in (-1, 1):
            for _ in range(max_slov):
                # hranice vystřižených slov na této straně
                if smer < 0:
                    prvni = min(ven)
                    if prvni == 0:
                        break
                    # konec bloku před frází: slovo prvni-1 končí, fráze začíná. Je tam ticho?
                    _, vyst, _, jiste = hranice_slov(k["vety"], i, 0, prvni, k["en"], k["delka"], vyp, gidx)
                    if jiste:
                        break
                    ven.add(prvni - 1)
                    pridano.append(slova[prvni - 1]["w"])
                else:
                    posledni = max(ven)
                    if posledni >= len(slova) - 1:
                        break
                    vst, _, jiste, _ = hranice_slov(k["vety"], i, posledni + 1, len(slova), k["en"], k["delka"], vyp, gidx)
                    if jiste:
                        break
                    ven.add(posledni + 1)
                    pridano.append(slova[posledni + 1]["w"])
        if pridano:
            hlaseni.append("Ve větě %s není kolem vystřižené fráze ticho, vystřihl jsem i: %s." % (vid, ", ".join("'%s'" % x for x in pridano)))
        # zbytek věty kratší než MIN_ZBYTEK (osamocené slůvko jako "Ta") by zůstal sám mezi dvěma střihy: vystřihne se taky
        for strana in ("pred", "za"):
            zbytek = [x for x in range(0, min(ven)) if x not in ven] if strana == "pred" else [x for x in range(max(ven) + 1, len(slova))]
            if zbytek and (slova[zbytek[-1]]["end"] - slova[zbytek[0]]["start"]) < MIN_ZBYTEK:
                ven.update(zbytek)
                hlaseni.append("Ve větě %s by zůstalo samotné '%s' (%.1f s), vystřihl jsem ho taky." % (
                    vid, " ".join(slova[x]["w"] for x in zbytek), slova[zbytek[-1]]["end"] - slova[zbytek[0]]["start"]))
        nove[vid] = sorted(ven)
    return nove, hlaseni


def nejiste_strihy(osa):
    """Střihy, které nejsou v pauze (uvnitř věty bez mezery). Kontrola hotového souboru je pak přečte znovu."""
    out = []
    useky = osa["useky"]
    for i, u in enumerate(useky):
        if i > 0 and not u["jisty_vstup"]:
            out.append({"cas": u["vystup_od"], "veta": (u["vety"] or [None])[0], "kde": "začátek"})
        if i + 1 < len(useky) and not u["jisty_vystup"]:
            vety = u["vety"] or next((x["vety"] for x in reversed(useky[:i + 1]) if x["vety"]), [None])
            out.append({"cas": round(u["vystup_od"] + u["delka"], 3), "veta": vety[-1], "kde": "konec"})
    return out


def vyber_po_upravach(klipy, vyber, vynechat, upravy):
    """Použije úpravy z editoru přepisu (upravy.json) na výběr. Vrátí (nový výběr, nové vynechat, nové texty slov).

    upravy: {smazane_vety: [id], vracene_vety: [id], smazana_slova: {id: [pořadí]}, vracena_slova: {id: [pořadí]},
             texty: {id: "nový text věty"}}
    Smazané věty se vyhodí, vrácené se zařadí na své přirozené místo (podle klipu a pořadí v klipu).
    """
    index = {}
    for c, k in enumerate(klipy):
        for i, v in enumerate(k["vety"]):
            index[v["id"]] = (c, i)
    smazane = set(upravy.get("smazane_vety", []))
    vracene = [v for v in upravy.get("vracene_vety", []) if v in index and v not in smazane]
    novy = [(c, vid) for c, vid in vyber if vid not in smazane]
    for vid in vracene:
        if any(x == vid for _, x in novy):
            continue
        c, i = index[vid]
        poz = len(novy)
        for p, (pc, pvid) in enumerate(novy):
            if index[pvid] > (c, i):
                poz = p
                break
        novy.insert(poz, (c, vid))
    nove_vynechat = {k: set(v) for k, v in (vynechat or {}).items()}
    for vid, idx in upravy.get("smazana_slova", {}).items():
        nove_vynechat.setdefault(vid, set()).update(idx)
    for vid, idx in upravy.get("vracena_slova", {}).items():
        if vid in nove_vynechat:
            nove_vynechat[vid] -= set(idx)
    nove_vynechat = {k: sorted(v) for k, v in nove_vynechat.items() if v}
    return novy, nove_vynechat, upravy.get("texty", {})


def texty_na_vynechani(klipy, texty):
    """Upravený text věty, ve kterém jsou jen smazaná slova (nic přidaného ani přepsaného), znamená vystřihnout ta
    slova z videa (Marcela, 18. 10. 2026). Vrátí ({id věty: [pořadí smazaných slov]}, texty, které zůstávají jako úprava titulku)."""
    import difflib

    def norm(w):
        return w.strip().lower().strip(".,;:!?\"'()[]„“”…-–—")

    vynechat, zbytek = {}, {}
    slova_vet = {v["id"]: [w["w"] for w in v["slova"]] for k in klipy for v in k["vety"]}
    for vid, novy in texty.items():
        stara = slova_vet.get(vid)
        if stara is None:
            continue
        nova = novy.split()
        sm = difflib.SequenceMatcher(None, [norm(w) for w in stara], [norm(w) for w in nova], autojunk=False)
        ops = sm.get_opcodes()
        if nova and len(nova) < len(stara) and all(op in ("equal", "delete") for op, *_ in ops):
            vynechat[vid] = sorted(i for op, i1, i2, _, _ in ops if op == "delete" for i in range(i1, i2))
        else:
            zbytek[vid] = novy
    return vynechat, zbytek


def pouzij_texty(klipy, texty):
    """Upravený text věty z editoru: mění jen slova (titulky), časy zůstávají. Vrátí seznam vět, kde se počet slov liší."""
    import difflib

    rozdilne = []
    for k in klipy:
        for v in k["vety"]:
            novy = texty.get(v["id"])
            if novy is None:
                continue
            nova = novy.split()
            stara = [w["w"] for w in v["slova"]]
            if len(nova) == len(stara):
                for w, t in zip(v["slova"], nova):
                    w["w"] = t
            else:
                rozdilne.append(v["id"])
                sm = difflib.SequenceMatcher(None, stara, nova, autojunk=False)
                for op, i1, i2, j1, j2 in sm.get_opcodes():
                    if op == "equal":
                        continue
                    if op == "insert":
                        # vložené slovo se přilepí k sousednímu slovu (čas zůstává jeho)
                        if i1 == 0:
                            v["slova"][0]["w"] = " ".join(nova[j1:j2]) + " " + v["slova"][0]["w"]
                        else:
                            v["slova"][i1 - 1]["w"] += " " + " ".join(nova[j1:j2])
                        continue
                    nove_slova = nova[j1:j2]
                    cile = list(range(i1, i2))
                    for n, i in enumerate(cile):
                        if n < len(cile) - 1:
                            v["slova"][i]["w"] = nove_slova[n] if n < len(nove_slova) else ""
                        else:
                            v["slova"][i]["w"] = " ".join(nove_slova[n:])
                    if op == "replace" and nove_slova:
                        # přepsaná slova se sloučí („po každý“ → „pokaždé“), nevystřihnou: čas prázdného slova
                        # dostane poslední neprázdné slovo téže změny, zvuk zůstává celý (Marcela 11. 11. 2026)
                        posledni = None
                        for i in cile:
                            if v["slova"][i]["w"]:
                                posledni = v["slova"][i]
                            elif posledni is not None:
                                posledni["end"] = max(posledni["end"], v["slova"][i]["end"])
                v["slova"] = [w for w in v["slova"] if w["w"]]
            v["text"] = " ".join(w["w"] for w in v["slova"])
    return rozdilne


def uloz_osu(osa, soubor):
    Path(soubor).write_text(json.dumps(osa, ensure_ascii=False, indent=1), encoding="utf-8")


def nacti_osu(soubor):
    return json.loads(Path(soubor).read_text(encoding="utf-8"))
