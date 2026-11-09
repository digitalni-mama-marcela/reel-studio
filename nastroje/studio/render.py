"""Vyrenderuje reel z časové osy: obraz ze zdrojových klipů, zvuk srovnaný na stejnou hlasitost, text položený přes overlay.

Postup: zvuk (střih, krátké prolnutí, měření a srovnání hlasitosti) -> obraz (střih, 1080x1920, 30 fps)
a text z našeho kódu přes rouru do ffmpeg. Originální klipy se jen čtou.
"""
import json
import re
import subprocess
from pathlib import Path

from . import zoom as zoom_modul
from .titulky import FPS, SIRKA, STYLY, VYSKA, Kreslic

CIL_LUFS = -16.0     # NÁVRH: cílová hlasitost mluveného reelu
CIL_PEAK = -1.5
PROLNUTI = 0.012     # zvukové prolnutí na každém střihu (s)
# jemný kompresor před srovnáním hlasitosti: tiše dořečený konec věty („…pošlu ti odkaz“, 15 až 20 dB pod řečí,
# OVĚŘENO 19. 10.) se přiblíží zbytku, hlasitá řeč se skoro nemění (NÁVRH hodnot, Marcela posoudí poslechem)
KOMPRESOR = "acompressor=threshold=-28dB:ratio=2.5:attack=8:release=220:makeup=3dB:knee=4"


def _ffmpeg(args, stderr_do=None):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin"] + args, check=True,
                          stderr=stderr_do, capture_output=stderr_do is None)


def zvuk_stridany(osa, wav):
    """Střih zvuku podle úseků. Každý úsek má krátké prolnutí na obou koncích, střihy jsou v tichu."""
    vstupy, filtr, popisky = [], [], []
    for i, u in enumerate(osa["useky"]):
        vstupy += ["-ss", "%.4f" % u["od"], "-t", "%.4f" % u["delka"], "-i", osa["klipy"][u["klip"]]]
        d = u["delka"]
        filtr.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:%.4f,asetpts=PTS-STARTPTS,"
                     "afade=t=in:d=%.3f,afade=t=out:st=%.4f:d=%.3f[a%d]" % (i, d, PROLNUTI, d - PROLNUTI, PROLNUTI, i))
        popisky.append("[a%d]" % i)
    filtr.append("%sconcat=n=%d:v=0:a=1[a]" % ("".join(popisky), len(popisky)))
    _ffmpeg(vstupy + ["-filter_complex", ";".join(filtr), "-map", "[a]", "-c:a", "pcm_s16le", str(wav)])


def zmer_hlasitost(soubor, filtr_pred=""):
    """Změří hlasitost (EBU R128) a vrátí slovník z ffmpeg loudnorm."""
    p = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(soubor), "-af",
                        filtr_pred + "loudnorm=I=%s:TP=%s:LRA=11:print_format=json" % (CIL_LUFS, CIL_PEAK),
                        "-f", "null", "-"], check=True, capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    return json.loads(m.group(0))


def zvuk_srovnany(wav_vstup, wav_vystup):
    """Dvouprůchodové srovnání hlasitosti (přesnější než jednoprůchodové). Vrátí změřené a výsledné hodnoty."""
    m = zmer_hlasitost(wav_vstup, KOMPRESOR + ",")
    af = (KOMPRESOR + ",loudnorm=I=%s:TP=%s:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:"
          "linear=true,aresample=48000" % (CIL_LUFS, CIL_PEAK, m["input_i"], m["input_tp"], m["input_lra"],
                                           m["input_thresh"], m["target_offset"]))
    _ffmpeg(["-i", str(wav_vstup), "-af", af, "-c:a", "pcm_s16le", str(wav_vystup)])
    return m, zmer_hlasitost(wav_vystup)


def potrebuje_masku(osa, styl_nazev):
    """Má reel vrstvy „za hlavou“ (hook, velká slova, prvky s za_hlavou) podle vzhledu nebo spec?"""
    k = Kreslic(osa, styl_nazev)
    h = osa.get("hook")
    if h and k.za_hlavou(("h", 0)):
        return True
    if any(k.za_hlavou(("e", j)) for j in range(len(osa.get("mini", [])))):
        return True
    return any(k.za_hlavou(("p", j)) for j in range(len(osa.get("prvky", []))))


def vyrenderuj(osa, styl_nazev, vystup, pracovni, log=None, bez_textu=False, preset="medium", maska=None):
    """Celý render. Vrátí slovník s měřením (hlasitost, délka, počet snímků).

    bez_textu=True: hrubý střih k náhledu (jen obraz a srovnaný zvuk, žádný hook ani titulky), rychlejší.
    maska=True: text za hlavou. Nejdřív se vyrenderuje základ bez textu (zaklad.mp4), z něj maska osoby
    (studio.maska, LiteRT), pak se na základ položí text, kde vrstvy „za hlavou“ osoba překrývá.
    """
    pracovni = Path(pracovni)
    pracovni.mkdir(parents=True, exist_ok=True)
    prechody = [p for p in osa.get("prechody", []) if p.get("typ") == "prulet"]
    z_videa = [p for p in osa.get("prvky", []) if p.get("typ") == "hravy_nadpis"
               and (p.get("pohyb") in ("ruka", "obrazovka") or p.get("nastup") == "ruce")]
    pred_po = [p for p in osa.get("prvky", []) if p.get("typ") == "pred_po"]
    if (maska or prechody or z_videa or pred_po) and not bez_textu:
        from . import maska as maska_modul
        zaklad = pracovni / "zaklad.mp4"
        m1 = _render(osa, styl_nazev, zaklad, pracovni, log, bez_textu=False, preset="fast", jen_zaklad=True)
        mk = None
        if maska or maska_modul.k_dispozici():
            # průlet masku jen využije (hledá tmavé místo na osobě), bez ní si poradí
            mk = maska_modul.Maska(str(zaklad), str(pracovni / "maska.npy"), fps=FPS)
            mk.spocitej(log)
        _dopocitej_prvky(osa, zaklad, mk)
        kreslic = Kreslic(osa, styl_nazev)
        kreslic.maska = mk if maska else None
        if prechody:
            zaklad = _pruletove_prechody(osa, prechody, zaklad, pracovni, mk, log)
        if pred_po:
            zaklad = _pred_po_zaklad(pred_po, zaklad, pracovni)
        out = _poloz_text_na_zaklad(osa, zaklad, _zvuk_se_zvuky(osa, pracovni), kreslic, vystup, pracovni, preset, m1)
        out["maska"] = bool(maska)
        if prechody:
            out["prechody"] = [p.get("vysledek") for p in prechody]
        return out
    return _render(osa, styl_nazev, vystup, pracovni, log, bez_textu, preset)


def _dopocitej_prvky(osa, zaklad, mk):
    """Prvky, které potřebují hotový obraz: hravý nadpis s rukou (maska osoby) nebo v tabletu (tmavá obrazovka),
    vypínač a plakát (vrchol skoku z masky)."""
    from .prvky import hravy_nadpis, vypinac_plakat
    for spec in osa.get("prvky", []):
        if spec.get("typ") == "hravy_nadpis":
            hravy_nadpis.dopocitej(spec, zaklad, mk)
        elif spec.get("typ") == "vypinac_plakat":
            # čas přepnutí z vrcholu skoku, pak zvuk cvaknutí přesně v tu chvíli
            vypinac_plakat.dopocitej(spec, zaklad, mk)
            zdroj = "vypinac_plakat@%.2f" % spec["od"]
            osa["zvuky"] = [z for z in osa.get("zvuky", []) if z.get("zdroj") != zdroj]
            osa["zvuky"] += [dict(z, zdroj=zdroj) for z in vypinac_plakat.zvuky(spec)]


def _pruletove_prechody(osa, prechody, zaklad, pracovni, mk, log):
    """Průlet střihem (prechody.prulet): na základu bez textu se kolem každého střihu přepočítá 18 snímků.
    Každý průlet zapíše nový základ zaklad-prulet-N.mp4; vrací cestu k poslednímu."""
    from . import prechody as prechody_modul
    zdroj = Path(zaklad)
    for j, p in enumerate(sorted(prechody, key=lambda x: x["cas"]), 1):
        cil = Path(pracovni) / ("zaklad-prulet-%d.mp4" % j)
        strih = int(round(float(p["cas"]) * FPS))
        p["vysledek"] = prechody_modul.prulet(str(zdroj), str(cil), strih, maska=mk, hlaseni=log,
                                              **{k: v for k, v in p.items() if k in ("pul", "hloubka", "strmost", "naklon")})
        p["vysledek"]["snimek_strihu"] = strih
        zdroj = cil
    return zdroj


def _pred_po_zaklad(prvky_pred_po, zaklad, pracovni):
    """Před a po (prvky.pred_po): na základu bez textu se v čase prvku smíchá obraz s jeho kopií v jiné barvě
    (ffmpeg blend, výraz podle polohy čáry nebo záclony). Mimo čas prvku zůstává základ beze změny, zvuk se kopíruje.
    Zapíše zaklad-pred-po.mp4 a vrátí cestu k němu."""
    from .prvky import pred_po
    filtr, vstup = [], "0:v"
    for j, spec in enumerate(sorted(prvky_pred_po, key=lambda p: float(p["od"]))):
        filtr.append("[%s]split[a%d][b%d]" % (vstup, j, j))
        filtr.append("[b%d]%s,format=yuv420p[g%d]" % (j, pred_po.BARVY[pred_po.barva(spec)], j))
        filtr.append("[a%d][g%d]blend=all_expr='%s':enable='between(t,%.4f,%.4f)'[v%d]" % (
            j, j, pred_po.vyraz_ffmpeg(spec), float(spec["od"]), pred_po.drzet_do(spec), j))
        vstup = "v%d" % j
    cil = Path(pracovni) / "zaklad-pred-po.mp4"
    _ffmpeg(["-i", str(zaklad), "-filter_complex", ";".join(filtr), "-map", "[%s]" % vstup, "-map", "0:a?",
             "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "copy", str(cil)])
    return cil


def _zvuk_se_zvuky(osa, pracovni):
    """Zvuk reelu pro render: srovnaný zvuk, a když osa má zvukové efekty, přimíchané (zvuk-s-efekty.wav)."""
    zvuk_nrm = Path(pracovni) / "zvuk-srovnany.wav"
    if osa.get("zvuky"):
        from . import zvuky
        k_mixu = zvuky.podle_nastaveni(osa)      # styl zákaznice (krok styl): výběr zvuků a hlasitost; bez stylu beze změny
        if not k_mixu:
            return zvuk_nrm
        fx = Path(pracovni) / "zvuk-s-efekty.wav"
        zvuky.primichej(zvuk_nrm, fx, k_mixu)
        return fx
    return zvuk_nrm


def _poloz_text_na_zaklad(osa, zaklad, zvuk_nrm, kreslic, vystup, pracovni, preset, mereni_zakladu):
    """Druhý průchod: hotový základ (obraz i zvuk už srovnané) + text z Kreslic (RGBA přes rouru)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(zaklad), "-i", str(zvuk_nrm),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (SIRKA, VYSKA), "-r", str(FPS), "-i", "-",
           "-filter_complex", "[0:v][2:v]overlay=0:0:format=auto[o];[o]format=yuv420p[vout]",
           "-map", "[vout]", "-map", "1:a", "-c:v", "libx264", "-preset", preset, "-crf", "18", "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:a", "aac", "-b:a", "192k", "-t", "%.4f" % osa["delka"], "-movflags", "+faststart", str(vystup)]
    chyby = open(pracovni / "ffmpeg-chyby.log", "wb")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=chyby)
    snimku = 0
    try:
        for data in kreslic.snimky():
            proc.stdin.write(data)
            snimku += 1
        proc.stdin.close()
    except BrokenPipeError:
        pass
    proc.wait()
    chyby.close()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg skončil chybou, viz %s" % (pracovni / "ffmpeg-chyby.log"))
    out = dict(mereni_zakladu)
    out.update({"snimku_overlay": snimku, "soubor": str(vystup), "maska": True})
    return out


def _render(osa, styl_nazev, vystup, pracovni, log=None, bez_textu=False, preset="medium", jen_zaklad=False):
    zvuk = pracovni / "zvuk-strihany.wav"
    zvuk_nrm = pracovni / "zvuk-srovnany.wav"
    zvuk_stridany(osa, zvuk)
    if osa.get("zvuk") in ("puvodni", "ticho"):
        # b-roll (Marcela 22. 10.): okolní zvuk se nezesiluje na řečovou hlasitost, hudbu přidá v Instagramu
        af = "volume=0" if osa["zvuk"] == "ticho" else "volume=-6dB,aresample=48000"
        _ffmpeg(["-i", str(zvuk), "-af", af, "-c:a", "pcm_s16le", str(zvuk_nrm)])
        pred = po = {"input_i": "-", "input_tp": "-", "input_lra": "-"}
    else:
        pred, po = zvuk_srovnany(zvuk, zvuk_nrm)

    kreslic = None if (bez_textu or jen_zaklad) else Kreslic(osa, styl_nazev)
    # obraz po částech: část = kus úseku se svým zoomem (zoom.py). Bez částí je část = úsek bez zoomu.
    casti = osa.get("casti") or [dict(klip=u["klip"], od=u["od"], delka=u["delka"], vystup_od=u.get("vystup_od", 0.0),
                                      zoom=1.0, posun_x=0.0, posun_y=0.0) for u in osa["useky"]]
    rozmery = osa.get("rozmery_klipu")
    n = len(casti)
    vstupy, filtr = [], []
    for i, c in enumerate(casti):
        vstupy += ["-ss", "%.4f" % c["od"], "-t", "%.4f" % c["delka"], "-i", osa["klipy"][c["klip"]]]
        if rozmery:
            zoom = zoom_modul.filtr_casti(c, *rozmery[c["klip"]])
        else:
            zoom = "scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d" % (SIRKA, VYSKA, SIRKA, VYSKA)
        # barevný filtr až od osa["filtr_od"] (Marcela 19. 10.: ne hned od začátku, až v průběhu videa)
        s_filtrem = not bez_textu and STYLY.get(styl_nazev, {}).get("filtr") and c["vystup_od"] + 0.01 >= float(osa.get("filtr_od") or 0.0)
        barevny = ("," + STYLY[styl_nazev]["filtr"]) if s_filtrem else ""
        filtr.append("[%d:v]fps=%d,%s%s,setsar=1,trim=duration=%.4f,setpts=PTS-STARTPTS[v%d]" % (i, FPS, zoom, barevny, c["delka"], i))
    filtr.append("%sconcat=n=%d:v=1:a=0[base]" % ("".join("[v%d]" % i for i in range(n)), n))
    if bez_textu or jen_zaklad:
        filtr.append("[base]format=yuv420p[vout]")
        vstup_textu = []
    else:
        filtr.append("[base][%d:v]overlay=0:0:format=auto[o];[o]format=yuv420p[vout]" % (n + 1))
        vstup_textu = ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (SIRKA, VYSKA), "-r", str(FPS), "-i", "-"]
    zvuk_render = zvuk_nrm if (bez_textu or jen_zaklad) else _zvuk_se_zvuky(osa, pracovni)
    cmd = (["ffmpeg", "-y", "-v", "error", "-nostdin"] + vstupy + ["-i", str(zvuk_render)] + vstup_textu +
           ["-filter_complex", ";".join(filtr), "-map", "[vout]", "-map", "%d:a" % n,
            "-c:v", "libx264", "-preset", preset, "-crf", "14" if jen_zaklad else "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-t", "%.4f" % osa["delka"], "-movflags", "+faststart", str(vystup)])
    chyby = open(pracovni / "ffmpeg-chyby.log", "wb")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if kreslic else subprocess.DEVNULL, stderr=chyby)
    snimku = 0
    if kreslic:
        try:
            for data in kreslic.snimky():
                proc.stdin.write(data)
                snimku += 1
            proc.stdin.close()
        except BrokenPipeError:
            pass
    proc.wait()
    chyby.close()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg skončil chybou, viz %s" % (pracovni / "ffmpeg-chyby.log"))
    return {"hlasitost_pred": {"LUFS": pred["input_i"], "peak_dB": pred["input_tp"]},
            "hlasitost_po": {"LUFS": po["input_i"], "peak_dB": po["input_tp"], "LRA": po["input_lra"]},
            "snimku_overlay": snimku, "delka_s": osa["delka"], "soubor": str(vystup)}


def zmer_vystup(soubor):
    """Co je v hotovém souboru: rozměr, snímkování, délka obrazu a zvuku."""
    d = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                   "stream=codec_type,codec_name,width,height,r_frame_rate,duration,pix_fmt,sample_rate",
                                   "-of", "json", str(soubor)], check=True, capture_output=True, text=True).stdout)
    return d["streams"]
