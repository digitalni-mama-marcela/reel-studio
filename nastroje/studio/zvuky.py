"""Vlastní krátké zvukové efekty (syntéza numpy, žádný cizí soubor, žádná licence) a jejich přimíchání
do zvuku reelu. NÁVRH 19. 10. 2026 (Marcela: zvukový efekt u velkého slova).

osa["zvuky"] = [{"typ": "whoosh" | "klik" | "trpyt" | "vystrel" | "pink" | "pusa" | "cvak" | "bzuk", "cas": sekundy ve výstupu, "db": -18 (volitelně)}]
trpyt, vystrel, pink a pusa: hravý nadpis (29. 10. 2026), rozepsání rukama, hod nad hlavu, cvrnknutí prstem, pusa.
cvak a bzuk: vypínač a plakát (29. 10. 2026), přepnutí vypínače a rozsvícení plakátu jako zářivky.
stopky: rychlé tikání běžícího počítadla času, délka přes "param": {"delka": s} (3. 11. 2026).
"""
import wave

import numpy as np

SR = 48000


def whoosh(delka=0.38, sr=SR):
    """Šum, který projede zdola nahoru (filtr s rostoucí propustí) s obálkou rychlý náběh, delší dozvuk."""
    n = int(delka * sr)
    rng = np.random.default_rng(7)
    sum_ = rng.standard_normal(n)
    # jednopólová dolní propust s mezní frekvencí rostoucí 250 Hz → 3200 Hz
    out = np.zeros(n)
    y = 0.0
    fc = np.geomspace(250.0, 3200.0, n)
    a = np.exp(-2 * np.pi * fc / sr)
    for i in range(n):
        y = a[i] * y + (1 - a[i]) * sum_[i]
        out[i] = y
    t = np.linspace(0, 1, n)
    obalka = np.minimum(t / 0.18, 1.0) * np.exp(-3.2 * np.maximum(t - 0.18, 0.0))
    out *= obalka
    return out / (np.max(np.abs(out)) + 1e-9)


def klik(delka=0.12, sr=SR):
    """Měkké ťuknutí: krátký tón, který klesá, s rychlým dozněním."""
    n = int(delka * sr)
    t = np.arange(n) / sr
    f = np.geomspace(900.0, 320.0, n)
    faze = np.cumsum(2 * np.pi * f / sr)
    out = np.sin(faze) * np.exp(-28 * t)
    return out / (np.max(np.abs(out)) + 1e-9)


def trpyt(delka=0.9, sr=SR):
    """Třpyt k rozepsání nadpisu: 9 krátkých cinknutí stoupajících 1100 → 3300 Hz po 0,07 s a tichý šum pod nimi."""
    n = int(delka * sr)
    out = np.zeros(n)
    for j, f in enumerate(np.geomspace(1100.0, 3300.0, 9)):
        i0 = int(j * 0.07 * sr)
        t = np.arange(n - i0) / sr
        out[i0:] += (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-22 * t) * (0.6 + 0.05 * j)
    rng = np.random.default_rng(11)
    t = np.linspace(0, 1, n)
    out += 0.08 * rng.standard_normal(n) * np.minimum(t / 0.3, 1.0) * np.exp(-3 * t)
    return out / (np.max(np.abs(out)) + 1e-9)


def vystrel(delka=0.55, sr=SR):
    """Výstřel nahoru: šum zrychlující 300 → 5000 Hz se sílící hlasitostí, na konci krátké „puf“ (nízký úder)."""
    n = int(delka * sr)
    rng = np.random.default_rng(5)
    sum_ = rng.standard_normal(n)
    fc = np.geomspace(300.0, 5000.0, n)
    a = np.exp(-2 * np.pi * fc / sr)
    out, y = np.zeros(n), 0.0
    for i in range(n):
        y = a[i] * y + (1 - a[i]) * sum_[i]
        out[i] = y
    t = np.linspace(0, 1, n)
    out *= np.minimum(t / 0.75, 1.0) ** 2 * np.where(t > 0.8, np.exp(-25 * (t - 0.8)), 1.0)
    out /= np.max(np.abs(out)) + 1e-9
    i0 = int(0.78 * n)
    tt = np.arange(n - i0) / sr
    out[i0:] += 0.9 * np.sin(2 * np.pi * np.geomspace(180.0, 70.0, n - i0) * tt) * np.exp(-30 * tt)
    return out / (np.max(np.abs(out)) + 1e-9)


def pink(delka=0.22, sr=SR):
    """Cvrnknutí: krátký jasný tón, který vyskočí 1400 → 2600 Hz, s vyšší harmonickou a rychlým doznívaním."""
    n = int(delka * sr)
    t = np.arange(n) / sr
    f = 1400.0 + 1200.0 * np.minimum(t / 0.03, 1.0)
    faze = np.cumsum(2 * np.pi * f / sr)
    out = (np.sin(faze) + 0.35 * np.sin(2.01 * faze)) * np.exp(-30 * t)
    out[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr))
    return out / (np.max(np.abs(out)) + 1e-9)


def pusa(delka=0.22, sr=SR):
    """Pusa (mlasknutí). Verze 2 (29. 10. 2026, Marcela: první nezněla jako pusa).

    Skutečné mlasknutí = rty se přisají a odlepí: krátké nasátí, jehož výška rychle stoupá (350 → 2400 Hz za 45 ms,
    s vlhkým šumem), na konci ostrý „pop“ (2 ms, pásmo 1 až 5 kHz) a pod tím krátký vzdušný dozvuk.
    """
    n = int(delka * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(3)
    out = np.zeros(n)
    k = int(0.045 * sr)                                        # nasátí
    tk = t[:k]
    f = np.geomspace(350.0, 2400.0, k)
    obalka = np.sin(np.pi * np.minimum(tk / 0.045, 1.0)) ** 0.6
    out[:k] += 0.55 * np.sin(np.cumsum(2 * np.pi * f / sr)) * obalka
    vlhky = rng.standard_normal(k) * obalka
    out[:k] += 0.25 * (vlhky - np.convolve(vlhky, np.ones(6) / 6, mode="same"))   # jen vyšší složky šumu
    i0 = k                                                     # pop při odlepení rtů
    pk = int(0.002 * sr)
    pop = rng.standard_normal(pk)
    pop = pop - np.convolve(pop, np.ones(4) / 4, mode="same")
    out[i0:i0 + pk] += 1.0 * pop * np.linspace(1, 0, pk)
    m = n - i0                                                 # vzdušný dozvuk
    vzduch = rng.standard_normal(m)
    vzduch = np.convolve(vzduch, np.ones(12) / 12, mode="same")
    out[i0:] += 0.35 * vzduch * np.exp(-40 * t[:m])
    out[: int(0.003 * sr)] *= np.linspace(0, 1, int(0.003 * sr))
    return out / (np.max(np.abs(out)) + 1e-9)


def klavesa(delka=0.05, sr=SR, seed=0):
    """Úhoz klávesy k psaní po písmenech (Marcela 29. 10.): ostré cvaknutí (šum nad 2 kHz, 4 ms) a krátké tupé
    ťuknutí (190 až 260 Hz); každý úhoz trochu jiný (seed), ať to nezní jako kulomet."""
    n = int(delka * sr)
    rng = np.random.default_rng(100 + int(seed))
    t = np.arange(n) / sr
    sum_ = rng.standard_normal(n)
    vysoky = sum_ - np.convolve(sum_, np.ones(8) / 8, mode="same")
    out = vysoky * np.exp(-t / 0.004) * (0.8 + 0.4 * rng.random())
    f = 190.0 + 70.0 * rng.random()
    out += 0.5 * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012)
    out[: int(0.0005 * sr)] *= np.linspace(0, 1, int(0.0005 * sr))
    return out / (np.max(np.abs(out)) + 1e-9) * (0.75 + 0.25 * rng.random())


def cink(delka=0.45, sr=SR):
    """Krátké „hotovo“ k fajfce v zápisníku (Marcela 29. 10.): dva jasné tóny po sobě (G6 a C7, 60 ms) s dozvukem."""
    n = int(delka * sr)
    out = np.zeros(n)
    for zpozdeni, f, sila in ((0.0, 1568.0, 0.8), (0.06, 2093.0, 1.0)):
        i0 = int(zpozdeni * sr)
        t = np.arange(n - i0) / sr
        ton = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2.0 * f * t) + 0.1 * np.sin(2 * np.pi * 3.0 * f * t)
        out[i0:] += sila * ton * np.exp(-t / 0.09)
    out[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr))
    return out / (np.max(np.abs(out)) + 1e-9)


def cvak(delka=0.12, sr=SR):
    """Vypínač (vypínač a plakát, 29. 10.): dvě ostrá cvaknutí 25 ms po sobě (stisk a dosednutí) s tupým ťuknutím."""
    n = int(delka * sr)
    rng = np.random.default_rng(31)
    out = np.zeros(n)
    for zpozdeni, sila in ((0.0, 1.0), (0.025, 0.6)):
        i0 = int(zpozdeni * sr)
        t = np.arange(n - i0) / sr
        sum_ = rng.standard_normal(n - i0)
        vysoky = sum_ - np.convolve(sum_, np.ones(6) / 6, mode="same")
        out[i0:] += sila * (vysoky * np.exp(-t / 0.003) + 0.6 * np.sin(2 * np.pi * 140.0 * t) * np.exp(-t / 0.015))
    return out / (np.max(np.abs(out)) + 1e-9)


def bzuk(delka=0.4, sr=SR):
    """Rozsvícení zářivky (nástup „blik“): bzučení 100 Hz s vyššími tóny, přerušované v rytmu blikání."""
    n = int(delka * sr)
    t = np.arange(n) / sr
    out = sum(np.sin(2 * np.pi * 100.0 * k * t) / k for k in (1, 2, 3, 5))
    rytmus = np.where(((t * 30).astype(int) % 2 == 1) & (t < 0.14), 0.25, 1.0)
    out = out * rytmus * np.minimum(t / 0.01, 1.0) * np.exp(-3.5 * t)
    return out / (np.max(np.abs(out)) + 1e-9)


def nuzky(delka=0.16, sr=SR):
    """Střih nůžkami (2. 11., „nechci se učit stříhat videa“): dvě kovová cvaknutí 60 ms po sobě, šum nad 3 kHz
    s krátkým zvoněním 4,2 kHz, druhé tišší."""
    n = int(delka * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)
    out = np.zeros(n)
    for zac, sila in ((0.0, 1.0), (0.06, 0.7)):
        tt = t - zac
        m = tt >= 0
        sum_ = rng.standard_normal(n)
        sum_ = np.diff(np.concatenate([[0.0], sum_]))          # výšky (jednoduchý horní propust)
        obal = np.where(m, np.exp(-np.clip(tt, 0, None) / 0.008), 0.0)
        zvon = np.where(m, np.sin(2 * np.pi * 4200 * np.clip(tt, 0, None)) * np.exp(-np.clip(tt, 0, None) / 0.02), 0.0)
        out += sila * (0.8 * sum_ * obal + 0.5 * zvon)
    return out / (np.max(np.abs(out)) + 1e-9)


def stopky(delka=2.6, sr=SR, krok=0.04):
    """Běžící stopky k počítadlu času (Marcela 3. 11., úvod „ani sekundu“): rychlé jemné tikání po 40 ms jako
    přeskakující setiny, každé ťuknutí trochu jiné, na konci tišší dojezd a jedno pevnější zastavení."""
    n = int(delka * sr)
    out = np.zeros(n + int(0.05 * sr))
    t = np.arange(int(0.012 * sr)) / sr
    rng = np.random.default_rng(23)
    for i, zac in enumerate(np.arange(0.0, delka - 0.05, krok)):
        f = 2600.0 + 500.0 * rng.random()
        tik = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.0025) * (0.55 + 0.25 * rng.random())
        i0 = int(zac * sr)
        out[i0:i0 + len(tik)] += tik
    stop = cvak(0.05, sr)
    i0 = int((delka - 0.03) * sr)
    out[i0:i0 + len(stop)] += 0.9 * stop[: len(out) - i0]
    return out / (np.max(np.abs(out)) + 1e-9)


ZVUKY = {"stopky": stopky, "nuzky": nuzky, "whoosh": whoosh, "klik": klik, "trpyt": trpyt, "vystrel": vystrel, "pink": pink, "pusa": pusa,
         "klavesa": klavesa, "cink": cink, "cvak": cvak, "bzuk": bzuk}


ZVUKY_KNIHOVNY = ("klavesa", "cink", "whoosh", "klik")   # zvuky, které si zákaznice vybírá v knihovně stylů


def podle_nastaveni(osa):
    """Zvuky osy podle osa["zvuky_nastaveni"] (krok styl): {"povolene": [typy z knihovny] nebo None, "bez": True = žádné,
    "db_posun": dB}. Bez nastavení vrátí zvuky beze změny (reely bez stylu se nemění). Zvuky, které v knihovně nejsou
    (třpyt, cvak…), patří k prvku a zůstávají, jen se ztiší nebo zesílí."""
    n = osa.get("zvuky_nastaveni")
    zv = osa.get("zvuky") or []
    if not n:
        return zv
    if n.get("bez"):
        return []
    povolene = n.get("povolene")
    posun = float(n.get("db_posun") or 0.0)
    out = []
    for z in zv:
        if povolene is not None and z.get("typ") in ZVUKY_KNIHOVNY and z.get("typ") not in povolene:
            continue
        out.append(dict(z, db=float(z.get("db", -18)) + posun) if posun else z)
    return out


def primichej(wav_vstup, wav_vystup, zvuky):
    """Přimíchá zvuky do stereo WAV (48 kHz, 16 bit). Hlasitost: db pod plným rozsahem (výchozí −18 dB)."""
    with wave.open(str(wav_vstup), "rb") as w:
        sr, kanaly, n = w.getframerate(), w.getnchannels(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32).reshape(-1, kanaly) / 32768.0
    for z in zvuky:
        gen = ZVUKY.get(z.get("typ"))
        if gen is None:
            continue
        sig = gen(sr=sr, **(z.get("param") or {})) * (10 ** (float(z.get("db", -18)) / 20))
        i0 = int(float(z["cas"]) * sr)
        if i0 >= len(data):
            continue
        kus = sig[: len(data) - i0]
        data[i0:i0 + len(kus)] += kus[:, None]
    data = np.clip(data, -0.999, 0.999)
    with wave.open(str(wav_vystup), "wb") as w:
        w.setnchannels(kanaly)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((data * 32767).astype(np.int16).tobytes())
    return len(zvuky)
