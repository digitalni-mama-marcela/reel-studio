"""Kontrola videa (krok 1): formát, otočení, snímkování, HDR, zvuk. Čte jen údaje o souboru (ffprobe), ne snímky.

Výstup: kontrola-videa.json a jedna česká řádka. Když je potřeba, připraví pracovní kopii
(video-pripravene.mp4): stálá snímkovost 30, nejvýš 1080x1920, H.264, zvuk AAC. Originál se nemění.

HDR: tvůj ffmpeg z Homebrew nemá filtr zscale ani libplacebo (OVĚŘENO 14. 10. 2026), takže HDR video
umíme jen poznat, ne převést. Krok skončí červeně a poradí, jak natočit bez HDR. NEOVĚŘENO, zda iPhone
zákaznic HDR posílá (test T6).
"""
import json
import subprocess
import time
from fractions import Fraction
from pathlib import Path

FPS_CIL = 30
SIRKA_CIL, VYSKA_CIL = 1080, 1920
HDR_PRENOSY = {"smpte2084", "arib-std-b67", "smpte428", "bt2020-10", "bt2020-12"}
MIN_DELKA_S = 3.0


def _frac(s):
    try:
        f = Fraction(s)
        return float(f) if f.denominator else 0.0
    except (ValueError, ZeroDivisionError, TypeError):
        return 0.0


def ffprobe(cesta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,"
                          "pix_fmt,color_transfer,color_primaries,color_space,bit_rate,sample_rate,channels,duration:"
                          "stream_side_data=rotation:stream_tags=rotate:format=duration,size,bit_rate",
                          "-of", "json", str(cesta)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def cas_vzniku(cesta):
    """Čas natočení z metadat souboru (creation_time), prázdný řetězec když chybí. NEOVĚŘENO, že telefon vždy zapíše čas natočení."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "default=nw=1:nk=1",
                              str(cesta)], check=True, capture_output=True, text=True).stdout.strip()
        return out
    except (subprocess.CalledProcessError, OSError):
        return ""


def precti(cesta):
    """Údaje o videu, srozumitelně pojmenované. Vrátí slovník (video=None, když soubor video nemá)."""
    d = ffprobe(cesta)
    fmt = d.get("format", {})
    video = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    zvuk = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    info = {"soubor": str(cesta), "velikost_b": int(fmt.get("size", 0) or 0),
            "delka_s": round(float(fmt.get("duration", 0) or 0), 3), "video": None, "zvuk": None}
    if video:
        w, h = int(video.get("width", 0)), int(video.get("height", 0))
        rot = 0
        for sd in video.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        if not rot and video.get("tags", {}).get("rotate"):
            try:
                rot = int(video["tags"]["rotate"])
            except ValueError:
                rot = 0
        if abs(rot) % 180 == 90:
            w, h = h, w
        r, avg = _frac(video.get("r_frame_rate")), _frac(video.get("avg_frame_rate"))
        prenos = video.get("color_transfer", "") or ""
        primarky = video.get("color_primaries", "") or ""
        pix = video.get("pix_fmt", "") or ""
        hdr = prenos in HDR_PRENOSY or (primarky == "bt2020" and ("10" in pix or "12" in pix))
        info["video"] = {"kodek": video.get("codec_name"), "sirka": w, "vyska": h, "otoceni": rot,
                         "na_vysku": h > w, "fps": round(r, 3), "fps_prumer": round(avg, 3),
                         "promenna_snimkovost": bool(r and avg and abs(r - avg) > 0.05),
                         "pix_fmt": pix, "prenos": prenos, "primarky": primarky, "hdr": bool(hdr),
                         "datovy_tok": int(video.get("bit_rate") or fmt.get("bit_rate") or 0),
                         "snimku": int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None}
    if zvuk:
        info["zvuk"] = {"kodek": zvuk.get("codec_name"), "vzorkovani": int(zvuk.get("sample_rate", 0) or 0),
                        "kanaly": int(zvuk.get("channels", 0) or 0)}
    return info


def posud(info):
    """Vyhodnotí údaje. Vrátí (zelená?, seznam zpráv (stav, text), potřeba_pripravit, co udělat při červené)."""
    v = info["video"]
    zpravy = []
    if not v:
        return False, [("cervena", "Soubor neobsahuje video.")], False, "Nahraj video z telefonu (MP4 nebo MOV)."
    if info["delka_s"] < MIN_DELKA_S:
        return False, [("cervena", "Video je kratší než %d s (%.1f s)." % (MIN_DELKA_S, info["delka_s"]))], False, \
            "Nahraj celé natočené video."
    if not info["zvuk"]:
        return False, [("cervena", "Video nemá zvukovou stopu, není co přepsat.")], False, \
            "Zkontroluj, že je v telefonu zapnutý mikrofon, a natoč znovu."
    if v["hdr"]:
        return False, [("cervena", "Video je HDR (%s). Po střihu by měly barvy vybledlé." % (v["prenos"] or v["pix_fmt"]))], \
            False, ("Převod HDR zatím neumíme. V iPhonu vypni Nastavení > Kamera > Nahrát video > HDR video "
                    "a natoč znovu, nebo video exportuj z Fotek jako 'Nejkompatibilnější'.")
    pripravit = False
    zpravy.append(("ok", "%s, %dx%d, %.2f snímků/s, %s, zvuk %s %d Hz." % (
        v["kodek"].upper(), v["sirka"], v["vyska"], v["fps_prumer"] or v["fps"], "na výšku" if v["na_vysku"] else "NA ŠÍŘKU",
        info["zvuk"]["kodek"], info["zvuk"]["vzorkovani"])))
    if not v["na_vysku"]:
        zpravy.append(("info", "Video je na šířku. Reel bude 1080x1920, okraje se oříznou (osoba uprostřed)."))
    if v["promenna_snimkovost"]:
        zpravy.append(("info", "Snímkování je proměnné (%.2f až %.2f). Připravím kopii se stálými 30 snímky, "
                               "aby zvuk a obraz držely spolu." % (min(v["fps"], v["fps_prumer"]), max(v["fps"], v["fps_prumer"]))))
        pripravit = True
    elif abs((v["fps_prumer"] or v["fps"]) - FPS_CIL) > 0.6:
        zpravy.append(("info", "Snímkování %.0f se převede na 30." % (v["fps_prumer"] or v["fps"])))
        pripravit = True
    if v["vyska"] > VYSKA_CIL or v["sirka"] > SIRKA_CIL:
        zpravy.append(("info", "Video je větší než 1080x1920, zmenší se (střih pak běží rychleji)."))
        pripravit = True
    return True, zpravy, pripravit, None


def priprav_kopii(zdroj, cil, info, log=None):
    """Udělá pracovní kopii: 30 snímků/s stálých, nejvýš 1080x1920, H.264 (crf 16), zvuk AAC 256 kb/s."""
    v = info["video"]
    filtry = ["fps=%d" % FPS_CIL]
    if v["vyska"] > VYSKA_CIL and v["na_vysku"]:
        filtry.append("scale=-2:%d" % VYSKA_CIL)
    elif v["sirka"] > SIRKA_CIL and not v["na_vysku"]:
        filtry.append("scale=%d:-2" % SIRKA_CIL)
    elif v["sirka"] > SIRKA_CIL:
        filtry.append("scale=%d:-2" % SIRKA_CIL)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(zdroj), "-vf", ",".join(filtry),
           "-fps_mode", "cfr", "-r", str(FPS_CIL), "-c:v", "libx264", "-preset", "fast", "-crf", "16",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", str(cil)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not Path(cil).exists():
        return False, (p.stderr or "").strip()[-400:]
    return True, ""


def kontrola(cesta, pracovni=None, pripravit_kdyz_treba=True):
    """Celý krok. Vrátí (zelená?, zpráva, co udělat, slovník s údaji včetně cesty k videu pro další kroky)."""
    cesta = Path(cesta)
    try:
        info = precti(cesta)
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        return False, "Video %s nejde přečíst." % cesta.name, \
            "Zkontroluj, že je soubor celý stažený, a zkus to znovu. (%s)" % str(e)[:120], {}
    ok, zpravy, pripravit, udelej = posud(info)
    info["hodnoceni"] = [{"stav": s, "text": t} for s, t in zpravy]
    info["pouzit"] = str(cesta)
    info["pripravena_kopie"] = None
    if pracovni:
        Path(pracovni).mkdir(parents=True, exist_ok=True)
    texty = [t for _, t in zpravy]
    zprava = " ".join(texty)
    if ok and pripravit and pripravit_kdyz_treba and pracovni:
        cil = Path(pracovni) / "video-pripravene.mp4"
        zacatek = time.time()
        hotovo, chyba = priprav_kopii(cesta, cil, info)
        if hotovo:
            po = precti(cil)
            info["pripravena_kopie"] = {"soubor": str(cil), "video": po["video"], "delka_s": po["delka_s"],
                                        "velikost_b": po["velikost_b"], "trvalo_s": round(time.time() - zacatek, 1)}
            info["pouzit"] = str(cil)
            zprava += " Pracovní kopie je hotová (%dx%d, 30 snímků/s, %.0f s)." % (
                po["video"]["sirka"], po["video"]["vyska"], time.time() - zacatek)
        else:
            ok, udelej = False, "Spusť krok znovu. Když to nepomůže, pošli mi soubor PRACOVNI/stav.json."
            zprava = "Příprava pracovní kopie videa %s se nezdařila (%s)." % (cesta.name, chyba or "ffmpeg bez hlášky")
            info["hodnoceni"].append({"stav": "cervena", "text": zprava})
    if pracovni:
        (Path(pracovni) / "kontrola-videa.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return ok, zprava, udelej, info
