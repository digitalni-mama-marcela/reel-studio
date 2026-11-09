"""Přechod „Průlet“: tvrdý střih mezi dvěma záběry se promění v jeden pohyb kamery.

Nápad Marcely (20. 10. 2026), parametry jsou náš NÁVRH:
- posledních `pul` snímků záběru A: kamera se přibližuje do bodu na osobě (tmavé hladké místo na trupu,
  ne kůže ani ruce), čím rychleji, tím víc radiálního pohybového rozmazání (průměr několika mezipoloh
  zoomu, „závěrka“), na konci se obraz rozplyne do barvy toho bodu;
- prvních `pul` snímků záběru B: otevře se ze stejného bodu (začíná velmi přiblížený, zabrzdí na 1,0×),
  kolem malého obrazu B měkký kruhový „portál“, mimo něj tma, do které zhasínají okrajové barvy B
  (roztažení posledních pixelů podél paprsků od bodu, ne zrcadlení);
- lehký náklon kamery přes celý pohyb (A: 0 → +naklon, B: −naklon → 0, tedy pořád stejným směrem),
  jemný barevný lem při nejvyšší rychlosti (červená o chlup větší, modrá menší).
Celkem 2·pul snímků kolem střihu, mimo ně je obraz nedotčený. Zvuk se tu neřeší, dělá ho hlavní program.

Použití: prulet(zaklad, vystup, strih) pro jeden střih, prulety(zaklad, vystup, [strihy]) pro všechny střihy
reelu najednou (video se překóduje jen jednou). Vstup je základ bez textu (render.py, zaklad.mp4), výstup
má stejný počet snímků a žádný zvuk; text a zvuk na něj položí hlavní program.
Všechno počítá numpy a OpenCV (warpAffine, remap, bilineárně), světlo se míchá v lineárním prostoru
(gamma 2,2). Video se čte i zapisuje přes ffmpeg, nikam se neposílá.
Potřebuje: numpy, opencv-python-headless, ffmpeg a ffprobe v PATH.
"""
import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

SIRKA, VYSKA, FPS = 1080, 1920, 30
GAMMA = 2.2
OKNO_BODU = 48            # okno (px) pro hledání hladké plochy
OKNO_BARVY = 20           # okno (px) pro průměrnou barvu bodu A
ZMENSENI = 4              # hledání bodu běží na 270x480
ZAVERKA = 1.0             # jak velkou část snímku (v čase) závěrka „vidí“ (1,0 = celý krok mezi snímky, 360°)
MEZIPOLOH_MIN, MEZIPOLOH_MAX = 2, 24
RYCHLOST_PLNA = 0.5       # ln(zoom) na snímek, při které je barevný lem nejsilnější
PX_NA_MEZIPOLOHU = 4.0    # jedna mezipoloha na tolik px posunu nejvzdálenějšího rohu během závěrky
ZOOM_ROZPLYNUTI = 1.5     # od tohoto zoomu se A lineárně (v ln zoomu) rozplývá do barvy bodu a B se z tmy vynořuje
LEM_MAX = 0.004           # barevný lem: červená ×(1+LEM), modrá ×(1−LEM) při plné rychlosti
TMA = 0.05                # spodní jas tmy mimo portál (v obrazovém prostoru, 0..1)
TMA_PODIL = 0.35          # tma = tolik z barvy bodu (lineárně) + spodní jas; konec A ztmavne na stejnou úroveň
OKRAJ_DOLE = 160          # bod nesmí být blíž než tolik px ke spodnímu okraji (ať je kolem něj obraz)
OKRAJ_STRANY = 120        # a ke stranám
PORTAL_R0 = 90.0          # poloměr portálu na prvním snímku B (px)
PORTAL_OKRAJ = 0.30       # měkký okraj portálu = PORTAL_OKRAJ · r + 30 px
PORTAL_STRMOST = 1.0      # otevírání portálu: t^PORTAL_STRMOST (víc než 1 = na začátku pomaleji)
PRESET_X264 = "fast"


# ---------------------------------------------------------------------------- pomocné


def _ffprobe_video(video):
    """Počet snímků, snímkovost, rozměr a barevné značky videa (nic se nedekóduje)."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
           "stream=nb_frames,nb_read_packets,width,height,r_frame_rate,color_range,color_space,pix_fmt",
           "-of", "json", str(video)]
    try:
        p = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("Nenašel jsem ffprobe, nainstaluj ffmpeg (na Macu brew install ffmpeg).")
    except subprocess.CalledProcessError:
        raise RuntimeError("Video %s se nepodařilo přečíst (ffprobe)." % video)
    s = json.loads(p.stdout)["streams"][0]
    snimku = None
    for k in ("nb_frames", "nb_read_packets"):
        if str(s.get(k, "")).isdigit():
            snimku = int(s[k])
            break
    cit, _, jm = str(s.get("r_frame_rate", "30/1")).partition("/")
    fps = float(cit) / float(jm or 1)
    rozsah = s.get("color_range") or ("pc" if str(s.get("pix_fmt", "")).startswith("yuvj") else "tv")
    matice = s.get("color_space") if s.get("color_space") not in (None, "unknown", "unspecified") else "bt709"
    return {"snimku": snimku, "fps": fps, "sirka": int(s.get("width", 0)), "vyska": int(s.get("height", 0)),
            "rozsah": rozsah, "matice": matice}


def _filtr_cteni(info):
    return "scale=in_color_matrix=%s:in_range=%s:flags=accurate_rnd+full_chroma_int" % (info["matice"], info["rozsah"])


def _filtr_zapisu(info):
    return "scale=out_color_matrix=%s:out_range=%s:flags=accurate_rnd+full_chroma_int,format=yuv420p" % (
        info["matice"], info["rozsah"])


def precti_snimky(video, od, pocet, info=None):
    """Přečte `pocet` snímků od indexu `od` jako uint8 (pocet, VYSKA, SIRKA, 3) RGB.

    Seek -ss před -i jde na klíčový snímek a dekóduje jen odtud (OVĚŘENO 20. 10.: shoda se select=n),
    zbytek videa se nedekóduje. -fps_mode passthrough, jinak by cfr zdvojil první snímek.
    """
    info = info or _ffprobe_video(video)
    t = max(0.0, (od - 0.5) / info["fps"])
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.6f" % t, "-i", str(video), "-frames:v", str(pocet),
           "-fps_mode", "passthrough", "-vf", _filtr_cteni(info), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    try:
        p = subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise RuntimeError("Nenašel jsem ffmpeg, nainstaluj ho (na Macu brew install ffmpeg).")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("ffmpeg nedokázal přečíst snímky %d..%d z %s: %s" % (
            od, od + pocet - 1, Path(video).name, e.stderr.decode("utf-8", "replace")[:200]))
    n = len(p.stdout) // (VYSKA * SIRKA * 3)
    if n < pocet:
        raise RuntimeError("Z videa %s jsem přečetl jen %d z %d snímků (od snímku %d)." % (Path(video).name, n, pocet, od))
    return np.frombuffer(p.stdout, np.uint8)[: pocet * VYSKA * SIRKA * 3].reshape(pocet, VYSKA, SIRKA, 3)


_LUT_LIN = (np.arange(256, dtype=np.float32) / 255.0) ** GAMMA


def do_linearu(snimek_uint8):
    """uint8 RGB -> float32 lineární světlo 0..1."""
    return _LUT_LIN[snimek_uint8]


def z_linearu(lin):
    """float32 lineární světlo -> uint8 RGB (gamma 2,2)."""
    return (np.power(np.clip(lin, 0.0, 1.0), 1.0 / GAMMA) * 255.0 + 0.5).astype(np.uint8)


def _maska_snimku(maska, i):
    """Maska pro snímek i: objekt s [i] (studio.maska.Maska), 2D pole pro všechny snímky, nebo None."""
    if maska is None:
        return None
    if isinstance(maska, np.ndarray) and maska.ndim == 2:
        return maska
    m = maska[i]
    return None if m is None else np.asarray(m)


# ---------------------------------------------------------------------------- bod


def najdi_bod(snimek_rgb, maska=None):
    """Bod pro průlet: nejtmavší hladká plocha uvnitř masky osoby, v dolních 60 % masky, s tmavým okolím.

    Hladkost = nízký rozptyl jasu v okně 48x48 px; kůže (YCrCb) se trestá, aby to nebyl obličej ani ruce.
    Bez masky vrátí střed dolní poloviny obrazu. Vrátí (x, y) v celých px.
    """
    import cv2
    if maska is None:
        return (SIRKA // 2, VYSKA // 2 + VYSKA // 4)
    z = ZMENSENI
    okno = max(3, OKNO_BODU // z)
    okoli = okno * 3
    w, h = SIRKA // z, VYSKA // z
    mal = cv2.resize(np.ascontiguousarray(snimek_rgb), (w, h), interpolation=cv2.INTER_AREA)
    m = cv2.resize(np.ascontiguousarray(maska), (w, h), interpolation=cv2.INTER_AREA) >= 128
    radky = np.where(m.any(axis=1))[0]
    if len(radky) < okno:
        return (SIRKA // 2, VYSKA // 2 + VYSKA // 4)
    ycc = cv2.cvtColor(mal, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    jas, cr, cb = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    kuze = ((cr >= 133) & (cr <= 175) & (cb >= 80) & (cb <= 130) & (jas > 60)).astype(np.float32)
    prumer = cv2.blur(jas, (okno, okno))
    prumer2 = cv2.blur(jas * jas, (okno, okno))
    rozptyl = np.sqrt(np.maximum(prumer2 - prumer * prumer, 0.0))
    okoli_jas = cv2.blur(jas, (okoli, okoli))
    kuze_podil = cv2.blur(kuze, (okno, okno))
    # celé okno musí být uvnitř masky: eroze maskou okna
    uvnitr = cv2.erode(m.astype(np.uint8), np.ones((okno, okno), np.uint8)) > 0
    # dolních 60 % masky (trup, klín)
    horni, dolni = int(radky[0]), int(radky[-1])
    od_radku = horni + int(round(0.4 * (dolni - horni)))
    uvnitr[:od_radku] = False
    # nic u okraje obrazu (ať má zoom i portál kolem bodu kam sahat)
    uvnitr[: okno // 2 + 1] = False
    uvnitr[h - OKRAJ_DOLE // z:] = False
    uvnitr[:, : OKRAJ_STRANY // z] = False
    uvnitr[:, w - OKRAJ_STRANY // z:] = False
    if not uvnitr.any():
        # maska je malá: aspoň střed její dolní části
        sloupce = np.where(m[od_radku:].any(axis=0))[0]
        x = int(np.median(sloupce)) if len(sloupce) else w // 2
        y = min((od_radku + dolni) // 2, h - OKRAJ_DOLE // z)
        x = min(max(x, OKRAJ_STRANY // z), w - OKRAJ_STRANY // z)
        return (int(x * z + z // 2), int(y * z + z // 2))
    # při shodě vyhrává místo blíž středu povolené plochy (ať bod nesedí v rohu trupu)
    yy, xx = np.nonzero(uvnitr)
    stred_x, stred_y = float(np.median(xx)), float(np.median(yy))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    vzdalenost = np.hypot(xs - stred_x, ys - stred_y)
    skore = prumer + 1.5 * rozptyl + 0.5 * okoli_jas + 400.0 * kuze_podil + 0.02 * vzdalenost
    skore[~uvnitr] = np.inf
    y, x = np.unravel_index(int(np.argmin(skore)), skore.shape)
    return (int(x * z + z // 2), int(y * z + z // 2))


def prumerna_barva(snimek_rgb, bod, okno=OKNO_BARVY):
    """Průměrná barva (lineární float32 RGB) v okně kolem bodu."""
    x, y = bod
    r = okno // 2
    vyrez = snimek_rgb[max(0, y - r): y + r, max(0, x - r): x + r]
    return do_linearu(np.ascontiguousarray(vyrez)).reshape(-1, 3).mean(axis=0).astype(np.float32)


# ---------------------------------------------------------------------------- křivky


class _Krivka:
    """Zoom, náklon a rychlost v průběhu průletu. `p` = 0 (bez zoomu) .. 1 (nejvíc přiblíženo)."""

    def __init__(self, hloubka, strmost, naklon, pul):
        self.ln_max = 0.5 * math.log(hloubka)      # zoom na střihu = sqrt(hloubka)
        self.strmost = float(strmost)
        self.naklon = float(naklon)
        self.pul = int(pul)

    def _e(self, p):
        p = min(max(p, 0.0), 1.0)
        return p ** self.strmost                    # pomalu, pak rychle skrz střih

    def zoom(self, p):
        return math.exp(self.ln_max * self._e(p))

    def uhel(self, p):
        return self.naklon * self._e(p)

    def rychlost(self, p):
        """|Δ ln zoom| za jeden snímek kolem polohy p."""
        d = 0.5 / self.pul
        return abs(self.ln_max * (self._e(p + d) - self._e(p - d)))

    def mezipoloh(self, v, roh_px):
        """Počet mezipoloh podle toho, o kolik px se během závěrky posune nejvzdálenější roh."""
        posun = roh_px * abs(1.0 - math.exp(-v * ZAVERKA))
        return int(min(MEZIPOLOH_MAX, max(MEZIPOLOH_MIN, round(posun / PX_NA_MEZIPOLOHU))))

    def lem(self, v):
        return LEM_MAX * min(1.0, v / RYCHLOST_PLNA) ** 2


def _matice(bod, zoom, uhel_deg):
    import cv2
    return cv2.getRotationMatrix2D((float(bod[0]), float(bod[1])), float(uhel_deg), float(zoom))


def _warp(lin, M):
    import cv2
    return cv2.warpAffine(lin, M, (SIRKA, VYSKA), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _nejdalsi_roh(bod):
    return max(math.hypot(bod[0] - x, bod[1] - y) for x in (0, SIRKA) for y in (0, VYSKA))


def _rozmazany(lin, bod, krivka, p, znamenko_uhlu):
    """Průměr mezipoloh zoomu (radiální pohybové rozmazání) kolem polohy p. Vrátí (obraz lin, rychlost, mezipoloh)."""
    v = krivka.rychlost(p)
    n = krivka.mezipoloh(v, _nejdalsi_roh(bod))
    acc = np.zeros_like(lin)
    for i in range(n):
        pi = p + ZAVERKA * (i / (n - 1) - 0.5) / krivka.pul
        pi = min(max(pi, 0.0), 1.0)
        acc += _warp(lin, _matice(bod, krivka.zoom(pi), znamenko_uhlu * krivka.uhel(pi)))
    acc *= 1.0 / n
    return acc, v, n


def barva_tmy(barva_bodu):
    """Tma za portálem a na konci A: část barvy bodu (lineárně) plus spodní jas TMA."""
    return (TMA_PODIL * np.asarray(barva_bodu, np.float32) + np.float32(TMA ** GAMMA)).astype(np.float32)


def _barevny_lem(lin, bod, k):
    """Červená o chlup větší, modrá menší (kolem bodu)."""
    if k <= 0:
        return lin
    out = lin.copy()
    out[..., 0] = _warp(np.ascontiguousarray(lin[..., 0]), _matice(bod, 1.0 + k, 0.0))
    out[..., 2] = _warp(np.ascontiguousarray(lin[..., 2]), _matice(bod, 1.0 - k, 0.0))
    return out


class _Portal:
    """Kruhový portál kolem bodu B: uvnitř obraz, za okrajem roztažené okrajové pixely zhasínající do tmy."""

    def __init__(self, bod, barva):
        ys, xs = np.mgrid[0:VYSKA, 0:SIRKA].astype(np.float32)
        self.bod = bod
        self.dx, self.dy = xs - bod[0], ys - bod[1]
        self.d = np.sqrt(self.dx * self.dx + self.dy * self.dy) + 1e-3
        self.r_max = _nejdalsi_roh(bod) * 1.02
        self.tma = barva_tmy(barva)

    def polomer(self, t):
        """t = 0 (nejvíc přiblíženo) .. 1 (zoom 1): poloměr od PORTAL_R0 po celý obraz i s měkkým okrajem."""
        r_plny = (self.r_max + 30.0) / (1.0 - PORTAL_OKRAJ)      # při t = 1 je i měkký okraj za rohy
        return PORTAL_R0 + (r_plny - PORTAL_R0) * min(max(t, 0.0), 1.0) ** PORTAL_STRMOST

    def poloz(self, lin, r):
        import cv2
        okraj = PORTAL_OKRAJ * r + 30.0
        if r >= self.r_max:
            return lin
        s = np.minimum(1.0, r / self.d).astype(np.float32)
        mapx = (self.bod[0] + self.dx * s).astype(np.float32)
        mapy = (self.bod[1] + self.dy * s).astype(np.float32)
        natazeny = cv2.remap(lin, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        vzd = np.maximum(self.d - r, 0.0) / okraj
        f = np.exp(-(vzd * vzd))[..., None].astype(np.float32)
        return natazeny * f + self.tma * (1.0 - f)


# ---------------------------------------------------------------------------- průlet


def spocitej_prechod(snimky_a, snimky_b, bod_a, bod_b, hloubka=80.0, strmost=2.4, naklon=4.0, hlaseni=None):
    """Spočítá 2·pul snímků přechodu z posledních pul snímků A a prvních pul snímků B (uint8 RGB).

    snimky_a: (pul, VYSKA, SIRKA, 3) poslední snímky A v pořadí; snimky_b: (pul, ...) první snímky B.
    Vrátí seznam uint8 snímků.
    """
    pul = len(snimky_a)
    if len(snimky_b) != pul:
        raise ValueError("Záběr A má %d snímků, B %d; musí jich být stejně." % (pul, len(snimky_b)))
    krivka = _Krivka(hloubka, strmost, naklon, pul)
    barva_a = prumerna_barva(snimky_a[-1], bod_a)
    barva_b = prumerna_barva(snimky_b[0], bod_b)
    tma_a = barva_tmy(barva_a)
    ln_roz = math.log(ZOOM_ROZPLYNUTI)
    vysledek = []
    # --- A: zoom 1 -> sqrt(hloubka), náklon 0 -> +naklon
    for j in range(pul):
        p = (j + 1) / pul
        lin, v, n = _rozmazany(do_linearu(snimky_a[j]), bod_a, krivka, p, +1.0)
        lin = _barevny_lem(lin, bod_a, krivka.lem(v))
        ln_z = math.log(krivka.zoom(p))
        d = min(1.0, max(0.0, (ln_z - ln_roz) / max(krivka.ln_max - ln_roz, 1e-6)))
        if d > 0:
            # rozplynutí do barvy bodu a zároveň ztmavnutí na úroveň tmy za portálem B (ať střih nesvítí)
            lin = lin * (1.0 - d) + (barva_a * (1.0 - d) + tma_a * d) * d
        vysledek.append(z_linearu(lin))
        if hlaseni:
            hlaseni("Průlet: snímek %d z %d (A, zoom %.2fx, mezipoloh %d)" % (j + 1, 2 * pul, krivka.zoom(p), n))
    # --- B: zoom sqrt(hloubka) -> 1, náklon -naklon -> 0, portál se otevírá
    portal = _Portal(bod_b, barva_b)
    for j in range(pul):
        p = 1.0 - j / pul
        lin, v, n = _rozmazany(do_linearu(snimky_b[j]), bod_b, krivka, p, -1.0)
        lin = _barevny_lem(lin, bod_b, krivka.lem(v))
        ln_z = math.log(krivka.zoom(p))
        t = 1.0 - ln_z / krivka.ln_max
        lin = portal.poloz(lin, portal.polomer(t))
        # zrcadlově k A: první snímky B se z tmy teprve vynořují (jinak by skok ze tmy do světla byl moc prudký)
        d = min(1.0, max(0.0, (ln_z - ln_roz) / max(krivka.ln_max - ln_roz, 1e-6)))
        if d > 0:
            lin = lin * (1.0 - d) + portal.tma * d
        vysledek.append(z_linearu(lin))
        if hlaseni:
            hlaseni("Průlet: snímek %d z %d (B, zoom %.2fx, portál %d px)" % (
                pul + j + 1, 2 * pul, krivka.zoom(p), int(portal.polomer(t))))
    return vysledek


def _sloz_video(zaklad, vystup, useky, info, preset=PRESET_X264):
    """vystup = základ s vyměněnými úseky. useky: [(od, pocet, vzor_png)] seřazené, bez překryvu.

    Stejné parametry jako základ (libx264 crf 14, yuv420p, bt709, stejná snímkovost), bez zvuku.
    PNG se převádí stejnou maticí a rozsahem, jakými se snímky četly, ať barvy navazují.
    """
    vstupy = ["-i", str(zaklad)]
    filtr = ["[0:v]split=%d%s" % (len(useky) + 1, "".join("[s%d]" % i for i in range(len(useky) + 1)))]
    poradi = []
    zacatek = 0
    for i, (od, pocet, vzor) in enumerate(useky):
        vstupy += ["-framerate", "%g" % info["fps"], "-i", str(vzor)]
        filtr.append("[s%d]trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS[z%d]" % (i, zacatek, od, i))
        filtr.append("[%d:v]%s[p%d]" % (i + 1, _filtr_zapisu(info), i))
        poradi += ["[z%d]" % i, "[p%d]" % i]
        zacatek = od + pocet
    filtr.append("[s%d]trim=start_frame=%d,setpts=PTS-STARTPTS[z%d]" % (len(useky), zacatek, len(useky)))
    poradi.append("[z%d]" % len(useky))
    filtr.append("%sconcat=n=%d:v=1:a=0[v]" % ("".join(poradi), len(poradi)))
    cmd = (["ffmpeg", "-y", "-v", "error", "-nostdin"] + vstupy + ["-filter_complex", ";".join(filtr), "-map", "[v]",
           "-c:v", "libx264", "-preset", preset, "-crf", "14", "-pix_fmt", "yuv420p", "-r", "%g" % info["fps"],
           "-colorspace", info["matice"], "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", info["rozsah"], "-an", "-movflags", "+faststart", str(vystup)])
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg nedokázal složit video s průletem: %s" % p.stderr.decode("utf-8", "replace")[:300])


def _rozvrhni_pul(strihy, n, pul, hlaseni=None):
    """Kolik snímků na každé straně má každý střih: pul, u kraje videa nebo u sousedního střihu méně, nejméně 4."""
    puly = []
    for strih in strihy:
        nejvic = min(strih - 2, n - strih - 2)
        if nejvic < 4:
            raise ValueError("Střih na snímku %d je moc blízko začátku nebo konce videa (%d snímků); "
                             "průlet potřebuje aspoň 6 snímků na každé straně." % (strih, n))
        puly.append(min(pul, nejvic))
    # sousední střihy: přechody se nesmí překrývat ani dotýkat (mezi nimi aspoň 1 nedotčený snímek)
    for i in range(len(strihy) - 1):
        while strihy[i] + puly[i] >= strihy[i + 1] - puly[i + 1]:
            j = i if puly[i] >= puly[i + 1] else i + 1
            puly[j] -= 1
            if puly[j] < 4:
                raise ValueError("Střihy na snímcích %d a %d jsou moc blízko u sebe (%d snímků); průlet potřebuje "
                                 "mezi nimi aspoň 9 snímků." % (strihy[i], strihy[i + 1], strihy[i + 1] - strihy[i]))
    for strih, p in zip(strihy, puly):
        if p < pul and hlaseni:
            hlaseni("Průlet: střih na snímku %d je blízko okraje videa nebo jiného střihu, zkracuji na %d snímků na každé straně." % (strih, p))
    return puly


def prulety(zaklad_mp4, vystup_mp4, strihy, maska=None, body=None, pul=9, hloubka=80.0, strmost=2.4, naklon=4.0,
            hlaseni=None, slozka_snimku=None):
    """Vloží průlet kolem každého střihu ze seznamu `strihy` (čísla prvních snímků záběrů B) a složí video jednou.

    body: volitelný seznam (bod_a, bod_b) ke každému střihu, None = najít. Ostatní jako prulet().
    Vrátí {"snimku", "prechody": [{"strih", "bod_a", "bod_b", "pul"}], "cas_s", "soubor"}.
    """
    import cv2
    zacatek = time.time()
    zaklad, vystup = Path(zaklad_mp4), Path(vystup_mp4)
    if not zaklad.is_file():
        raise FileNotFoundError("Video %s neexistuje." % zaklad)
    info = _ffprobe_video(zaklad)
    if (info["sirka"], info["vyska"]) != (SIRKA, VYSKA):
        raise ValueError("Video %s má %dx%d, průlet čeká %dx%d." % (zaklad.name, info["sirka"], info["vyska"], SIRKA, VYSKA))
    n = info["snimku"]
    if not n:
        raise RuntimeError("Nezjistil jsem počet snímků videa %s." % zaklad.name)
    strihy = [int(s) for s in strihy]
    if strihy != sorted(strihy) or len(set(strihy)) != len(strihy):
        raise ValueError("Střihy musí být seřazené od začátku a každý jen jednou: %s" % strihy)
    if not strihy:
        raise ValueError("Nedostal jsem žádný střih, kam průlet vložit.")
    puly = _rozvrhni_pul(strihy, n, int(pul), hlaseni)
    body = list(body or [None] * len(strihy))
    docasna = None
    if slozka_snimku is None:
        docasna = tempfile.mkdtemp(prefix="prulet-")
        slozka = Path(docasna)
    else:
        slozka = Path(slozka_snimku)
        slozka.mkdir(parents=True, exist_ok=True)
    useky, prechody = [], []
    try:
        for k, (strih, p) in enumerate(zip(strihy, puly)):
            od = strih - p
            snimky = precti_snimky(zaklad, od, 2 * p, info)
            snimky_a, snimky_b = snimky[:p], snimky[p:]
            bod_a, bod_b = body[k] if body[k] else (None, None)
            if bod_a is None:
                bod_a = najdi_bod(snimky_a[-1], _maska_snimku(maska, strih - 1))
            if bod_b is None:
                bod_b = najdi_bod(snimky_b[0], _maska_snimku(maska, strih))
            bod_a, bod_b = (int(bod_a[0]), int(bod_a[1])), (int(bod_b[0]), int(bod_b[1]))
            if hlaseni:
                hlaseni("Průlet %d z %d: střih na snímku %d, bod A %s, bod B %s, %d snímků přechodu." % (
                    k + 1, len(strihy), strih, bod_a, bod_b, 2 * p))
            prechod = spocitej_prechod(snimky_a, snimky_b, bod_a, bod_b, hloubka, strmost, naklon, hlaseni)
            vzor = "prulet-%d-%%03d.png" % strih
            for j, sn in enumerate(prechod):
                cv2.imwrite(str(slozka / (vzor % j)), cv2.cvtColor(sn, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 1])
            useky.append((od, 2 * p, slozka / vzor))
            prechody.append({"strih": strih, "bod_a": bod_a, "bod_b": bod_b, "pul": p})
        vystup.parent.mkdir(parents=True, exist_ok=True)
        _sloz_video(zaklad, vystup, useky, info)
    finally:
        if docasna:
            shutil.rmtree(docasna, ignore_errors=True)
    n_out = _ffprobe_video(vystup)["snimku"]
    if n_out != n:
        raise RuntimeError("Video s průletem má %d snímků, základ %d; něco se pokazilo při skládání." % (n_out, n))
    cas = time.time() - zacatek
    if hlaseni:
        hlaseni("Průlet hotový: %s, %d snímků, %d přechodů, %.1f s." % (vystup.name, n_out, len(prechody), cas))
    return {"snimku": n_out, "prechody": prechody, "cas_s": round(cas, 2), "soubor": str(vystup)}


def prulet(zaklad_mp4, vystup_mp4, strih_snimek, maska=None, bod_a=None, bod_b=None, pul=9,
           hloubka=80.0, strmost=2.4, naklon=4.0, hlaseni=None, slozka_snimku=None):
    """Vloží průlet kolem jednoho střihu na snímku `strih_snimek` (první snímek záběru B) a složí nové video.

    zaklad_mp4: základ reelu bez textu (1080x1920, 30 fps). vystup_mp4: nové video se stejným počtem snímků,
    bez zvuku. maska: studio.maska.Maska (nebo 2D pole), pro hledání bodu. bod_a/bod_b: (x, y), když None,
    najdou se na posledním snímku A a prvním snímku B. slozka_snimku: kam uložit PNG přechodu (jinak dočasná).
    Víc střihů najednou (jedno překódování): prulety(). Vrátí {"snimku", "bod_a", "bod_b", "cas_s", "pul", "soubor"}.
    """
    v = prulety(zaklad_mp4, vystup_mp4, [int(strih_snimek)], maska=maska, body=[(bod_a, bod_b)], pul=pul,
                hloubka=hloubka, strmost=strmost, naklon=naklon, hlaseni=hlaseni, slozka_snimku=slozka_snimku)
    p = v["prechody"][0]
    return {"snimku": v["snimku"], "bod_a": p["bod_a"], "bod_b": p["bod_b"], "cas_s": v["cas_s"], "pul": p["pul"],
            "soubor": v["soubor"]}


def kontaktni_list(snimky, cesta, sloupcu=6, sirka=180):
    """Uloží snímky (uint8 RGB) jako jeden obrázek v mřížce (pro kontrolu okem)."""
    import cv2
    vyska = int(sirka * VYSKA / SIRKA)
    radku = (len(snimky) + sloupcu - 1) // sloupcu
    list_ = np.zeros((radku * vyska, sloupcu * sirka, 3), np.uint8)
    for j, sn in enumerate(snimky):
        r, c = divmod(j, sloupcu)
        list_[r * vyska:(r + 1) * vyska, c * sirka:(c + 1) * sirka] = cv2.resize(sn, (sirka, vyska), interpolation=cv2.INTER_AREA)
    Path(cesta).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(cesta), cv2.cvtColor(list_, cv2.COLOR_RGB2BGR))
    return str(cesta)
