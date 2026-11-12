"""Spouštěč studia. Jen standardní knihovna, běží na Pythonu 3.9 i novějším, na Macu i Windows.

Zákaznice ho nespouští napřímo. Claude volá spouštěč pro její systém. Ten si sám stáhne uv a Python 3.12
a pak spustí tenhle soubor:
  Mac:     sh "<plugin>/nastroje/spust.sh" <krok> ...
  Windows: powershell -NoProfile -ExecutionPolicy Bypass -File "<plugin>/nastroje/spust.ps1" <krok> ...

Co dělá:
  1. najde (nebo založí) prostředí studia MIMO složku Reely a mimo iCloud a OneDrive:
       Mac:     ~/Library/Application Support/ClaudeReelStudio
       Windows: %LOCALAPPDATA%\\ClaudeReelStudio
     V něm je uv, Python 3.12, knihovny (venv podle pozadavky.txt), ffmpeg a modely přepisu (HF_HOME).
     Nic se neinstaluje do systému a nechce to heslo ani práva správce.
  2. spustí krok studia: python -m studio <krok> ...  (kód je vedle tohoto souboru ve složce studio/)

Kroky navíc (běží bez prostředí studia):
  priprava     připraví prostředí a ffmpeg, vyzkouší knihovny, vypíše zelenou nebo červenou
  kontrola     kontrola počítače (stejné parametry jako studio/kontrola_pocitace.py)
  aktualizace  zapne automatické aktualizace pluginu (aktualizace.py)
  cink         zvuk (studio/cink.py)
  model        stáhne model přepisu (asi 1,6 GB). --na-pozadi: stahuje dál sám, Claude hned pokračuje.
               --stav: jen řekne, jestli je stažený, nebo se stahuje.
  kde          vypíše cesty
Proměnná REEL_STUDIO_DATA přepíše složku s prostředím (pro zkoušky).
"""
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

TADY = Path(__file__).resolve().parent
POZADAVKY = TADY / "pozadavky.txt"
JE_WINDOWS = platform.system() == "Windows"
JE_MAC = platform.system() == "Darwin"
# Na Windows vždycky x64: přepis (ctranslate2) a maska (ai-edge-litert) nemají sestavení pro Windows na ARM.
PYTHON_VERZE = os.environ.get("REEL_STUDIO_PYTHON") or ("cpython-3.12-windows-x86_64-none" if JE_WINDOWS else "3.12")
HLAVICKA = {"User-Agent": "ReelStudio-DigitalniMamaMarcela/1.0"}

# Vlastní ffmpeg studia: pevné verze, kontrolní součty SHA-256 (OVĚŘENO 11. 11. 2026 ze zdrojů níž).
# Mac: sestavení Martina Riedla (odkaz z ffmpeg.org/download), podepsané a notarizované, s libx264 a HEVC.
# Windows: sestavení gyan.dev „essentials“ (odkaz z ffmpeg.org/download), zrcadlo na GitHubu GyanD/codexffmpeg.
FFMPEG_VERZE = "9.0.2"
_RIEDL = "https://ffmpeg.martin-riedl.de/download/macos/"
FFMPEG_ZDROJE = {
    "mac-arm64": [
        (_RIEDL + "arm64/1789931890_9.0.2/ffmpeg.zip",
         "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924", {"ffmpeg": "ffmpeg"}),
        (_RIEDL + "arm64/1789931890_9.0.2/ffprobe.zip",
         "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6", {"ffprobe": "ffprobe"}),
    ],
    "mac-x86_64": [
        (_RIEDL + "amd64/1789931006_9.0.2/ffmpeg.zip",
         "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4", {"ffmpeg": "ffmpeg"}),
        (_RIEDL + "amd64/1789931006_9.0.2/ffprobe.zip",
         "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd", {"ffprobe": "ffprobe"}),
    ],
    "windows-x64": [
        ("https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
         "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
         {"bin/ffmpeg.exe": "ffmpeg.exe", "bin/ffprobe.exe": "ffprobe.exe"}),
    ],
}
VELIKOST_FFMPEG = {"mac-arm64": "asi 55 MB", "mac-x86_64": "asi 60 MB", "windows-x64": "asi 115 MB"}

# Knihovny, které musí jít načíst, jinak studio nepoběží (maska je volitelná, viz pozadavky.txt).
ZKOUSKA_KNIHOVEN = "import numpy, PIL, cv2, av, ctranslate2, faster_whisper; print('ok')"

MODEL_PREPISU = "turbo"            # stejný jako studio/prepis.py VYCHOZI_MODEL
# Stáhne model do HF_HOME (prostředí studia). Stejnou cestou si ho pak najde přepis, takže se nestahuje dvakrát.
# Když se stahování přeruší, další spuštění naváže (huggingface_hub si drží rozpracované soubory).
STAHNI_MODEL = ("import sys; from faster_whisper.utils import download_model; "
                "download_model(sys.argv[1]); print('MODEL OK')")
JE_MODEL = ("import os, sys; from faster_whisper.utils import download_model; "
            "p = download_model(sys.argv[1], local_files_only=True); "
            "sys.exit(0 if os.path.isfile(os.path.join(p, 'model.bin')) else 1)")


def slozka_dat():
    env = os.environ.get("REEL_STUDIO_DATA")
    if env:
        return Path(env)
    if JE_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ClaudeReelStudio"
    if JE_MAC:
        return Path.home() / "Library" / "Application Support" / "ClaudeReelStudio"
    return Path.home() / ".claude-reel-studio"


def exe(nazev):
    return nazev + ".exe" if JE_WINDOWS else nazev


def python_ve_venv(venv):
    if JE_WINDOWS:
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def najdi_uv():
    """Nejdřív vlastní uv studia (ze spouštěče), pak uv v počítači."""
    kandidati = [os.environ.get("REEL_STUDIO_UV"), str(slozka_dat() / "uv" / exe("uv")), shutil.which("uv")]
    kandidati += [str(p) for p in (Path.home() / ".local" / "bin" / exe("uv"), Path("/opt/homebrew/bin/uv"),
                                   Path("/usr/local/bin/uv"))]
    for k in kandidati:
        if k and Path(k).is_file():
            return k
    return None


def uv_prostredi():
    """uv drží Python i mezipaměť ve složce studia a bere jen Python, který si stáhl sám."""
    env = dict(os.environ)
    data = slozka_dat()
    env.setdefault("UV_PYTHON_INSTALL_DIR", str(data / "python"))
    env.setdefault("UV_CACHE_DIR", str(data / "uv-cache"))
    env.setdefault("UV_PYTHON_PREFERENCE", "only-managed")
    env.setdefault("UV_NO_CONFIG", "1")
    return env


def otisk_pozadavku():
    return hashlib.sha256(POZADAVKY.read_bytes()).hexdigest()[:16]


def spust_tiche(cmd, env=None, limit=None):
    try:
        v = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                           timeout=limit)
        return v.returncode, (v.stdout or "") + (v.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)


def posledni_radek(text):
    radky = [r for r in (text or "").strip().splitlines() if r.strip()]
    return (radky[-1] if radky else "bez hlášky")[:300]


def priprav_venv(tise=False):
    """Založí prostředí, když chybí nebo se změnily požadavky. Vrátí (python, zpráva, ok)."""
    data = slozka_dat()
    venv = data / "venv"
    znacka = data / "venv-pozadavky.txt"
    py = python_ve_venv(venv)
    if py.exists() and znacka.exists() and znacka.read_text(encoding="utf-8").strip() == otisk_pozadavku():
        return py, "Prostředí studia je připravené (%s)." % data, True
    uv = najdi_uv()
    if not uv:
        return None, "Chybí nástroj uv. Spouštěč (spust.sh nebo spust.ps1) si ho stáhne sám.", False
    data.mkdir(parents=True, exist_ok=True)
    if not tise:
        print("⏳ Připravuju prostředí studia do %s (poprvé pár minut, stahují se knihovny)." % data, flush=True)
    env = uv_prostredi()
    kroky = [[uv, "venv", "--clear", "--python", PYTHON_VERZE, str(venv)],
             [uv, "pip", "install", "--python", str(py), "-r", str(POZADAVKY)]]
    for cmd in kroky:
        kod, vystup = spust_tiche(cmd, env=env)
        if kod != 0:
            return None, "Příprava prostředí selhala: %s" % posledni_radek(vystup), False
    znacka.write_text(otisk_pozadavku(), encoding="utf-8")
    return py, "Prostředí studia je připravené (%s)." % data, True


# ---------------------------------------------------------------- ffmpeg

def druh_pocitace():
    if JE_WINDOWS:
        return "windows-x64"
    if JE_MAC:
        arm = platform.machine().lower() in ("arm64", "aarch64")
        if not arm:   # Python pod Rosettou hlásí x86_64, čip je ale Apple
            arm = spust_tiche(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"])[1].strip() == "1"
        return "mac-arm64" if arm else "mac-x86_64"
    return None


def slozka_ffmpeg():
    return slozka_dat() / "ffmpeg"


def vlastni_ffmpeg():
    d = slozka_ffmpeg()
    return d / exe("ffmpeg"), d / exe("ffprobe")


def ffmpeg_jede(ffmpeg, ffprobe):
    """Spustí se oba programy? (Filtry a kodéry posuzuje ffmpeg_umi a kontrola počítače.)"""
    for p in (ffmpeg, ffprobe):
        if not p or not Path(p).is_file():
            return False
        kod, _ = spust_tiche([str(p), "-hide_banner", "-version"], limit=30)
        if kod != 0:
            return False
    return True


def ffmpeg_umi(ffmpeg):
    """Má tenhle ffmpeg všechno, co studio potřebuje? Stejná pravidla jako kontrola počítače."""
    if str(TADY) not in sys.path:
        sys.path.insert(0, str(TADY))
    try:
        from studio import kontrola_pocitace as k
    except Exception:  # noqa: BLE001
        return False
    filtry = spust_tiche([ffmpeg, "-hide_banner", "-filters"], limit=30)[1]
    dekodery = spust_tiche([ffmpeg, "-hide_banner", "-decoders"], limit=30)[1]
    kodery = spust_tiche([ffmpeg, "-hide_banner", "-encoders"], limit=30)[1]
    return (all(k.ma_polozku(filtry, f) for f in k.POTREBNE_FILTRY) and k.ma_polozku(dekodery, "hevc")
            and any(k.ma_polozku(kodery, x) for x in k.KODERY_H264))


def stahni(url, cil, pokusu=3):
    """Stáhne soubor. Nejdřív Python, když to nejde (třeba certifikáty), systémový curl. Vrátí True/False."""
    for pokus in range(1, pokusu + 1):
        try:
            pozadavek = urllib.request.Request(url, headers=HLAVICKA)
            with urllib.request.urlopen(pozadavek, timeout=60) as r, open(cil, "wb") as f:
                shutil.copyfileobj(r, f, 1024 * 1024)
            return True
        except Exception:  # noqa: BLE001
            curl = shutil.which("curl")
            if curl:
                kod, _ = spust_tiche([curl, "-fsSL", "--connect-timeout", "20", "--speed-limit", "1024",
                                      "--speed-time", "45", "-A", HLAVICKA["User-Agent"], "-o", str(cil), url])
                if kod == 0:
                    return True
        if pokus < pokusu:
            print("⏳ Stahování se nedokončilo, zkouším znovu (%d. pokus ze %d)." % (pokus + 1, pokusu), flush=True)
            time.sleep(3)
    return False


def sha256(soubor):
    h = hashlib.sha256()
    with open(soubor, "rb") as f:
        for kus in iter(lambda: f.read(1024 * 1024), b""):
            h.update(kus)
    return h.hexdigest()


def stahni_ffmpeg(druh):
    """Stáhne vlastní ffmpeg a ffprobe do složky studia. Vrátí (ok, zpráva)."""
    cil = slozka_ffmpeg()
    docasna = slozka_dat() / "ffmpeg.stahovani"
    shutil.rmtree(docasna, ignore_errors=True)
    docasna.mkdir(parents=True, exist_ok=True)
    try:
        for i, (url, soucet, soubory) in enumerate(FFMPEG_ZDROJE[druh]):
            archiv = docasna / ("balik-%d.zip" % i)
            if not stahni(url, archiv):
                return False, "ffmpeg se nepodařilo stáhnout (internet nebo server nedostupný)."
            if sha256(archiv) != soucet:
                return False, "Stažený ffmpeg neprošel kontrolním součtem, nepoužila jsem ho."
            with zipfile.ZipFile(archiv) as z:
                for clen in z.namelist():
                    for konec, jmeno in soubory.items():
                        if clen == konec or clen.endswith("/" + konec):
                            with z.open(clen) as zdroj, open(docasna / jmeno, "wb") as vystup:
                                shutil.copyfileobj(zdroj, vystup, 1024 * 1024)
            archiv.unlink()
        cil.mkdir(parents=True, exist_ok=True)
        for jmeno in (exe("ffmpeg"), exe("ffprobe")):
            zdroj = docasna / jmeno
            if not zdroj.exists():
                return False, "Ve staženém balíku chybí %s." % jmeno
            if not JE_WINDOWS:
                zdroj.chmod(zdroj.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            os.replace(str(zdroj), str(cil / jmeno))
    finally:
        shutil.rmtree(docasna, ignore_errors=True)
    if not ffmpeg_jede(*vlastni_ffmpeg()):
        return False, ("Stažený ffmpeg nejde spustit. Na Windows ho mohl zablokovat antivirus nebo "
                       "Smart App Control.")
    return True, "ffmpeg %s je připravený (vlastní kopie studia)." % FFMPEG_VERZE


def priprav_ffmpeg(tise=False):
    """Vlastní kopie studia, nebo ffmpeg z počítače, když umí všechno potřebné, jinak ho stáhne.
    Vrátí (ok, zpráva)."""
    if ffmpeg_jede(*vlastni_ffmpeg()):
        return True, "ffmpeg je připravený (vlastní kopie studia)."
    systemovy, systemovy_probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_jede(systemovy, systemovy_probe) and ffmpeg_umi(systemovy):
        return True, "ffmpeg je připravený (%s)." % systemovy
    druh = druh_pocitace()
    if druh not in FFMPEG_ZDROJE:
        return False, "Pro tenhle systém studio ffmpeg stáhnout neumí."
    if not tise:
        print("⏳ Stahuju ffmpeg, program na práci s videem (%s, jednou)." % VELIKOST_FFMPEG[druh], flush=True)
    return stahni_ffmpeg(druh)


def prostredi():
    env = dict(os.environ)
    data = slozka_dat()
    env.setdefault("HF_HOME", str(data / "modely"))           # modely přepisu mimo Reely (D3)
    env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")           # stahování modelu nic dalšího neposílá
    env["PYTHONPATH"] = str(TADY) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["REEL_STUDIO_DATA"] = str(data)
    if vlastni_ffmpeg()[0].exists():                          # vlastní ffmpeg má přednost před systémovým
        env["PATH"] = str(slozka_ffmpeg()) + os.pathsep + env.get("PATH", "")
    return env


def zkus_knihovny(py):
    """Jdou knihovny opravdu načíst? Na Windows tady vyjde najevo chybějící knihovna Visual C++."""
    kod, vystup = spust_tiche([str(py), "-c", ZKOUSKA_KNIHOVEN], env=prostredi(), limit=300)
    if kod == 0:
        return True, "Knihovny studia jdou načíst."
    rada = ""
    if JE_WINDOWS and "dll" in vystup.lower():
        rada = (" Udělej: v PowerShellu spusť `winget install --id Microsoft.VCRedist.2015+.x64 -e`, "
                "pak Claude úplně zavři, znovu otevři a spusť přípravu znovu.")
    return False, "Knihovny studia nejdou načíst: %s.%s" % (posledni_radek(vystup), rada)


def priprav(tise=False):
    """Prostředí + ffmpeg. Vrátí (python nebo None, [(ok, zpráva)], ok)."""
    py, zprava, ok = priprav_venv(tise)
    zpravy = [(ok, zprava)]
    if not ok:
        return None, zpravy, False
    ff_ok, ff_zprava = priprav_ffmpeg(tise)
    zpravy.append((ff_ok, ff_zprava))
    return (py if ff_ok else None), zpravy, ff_ok


def model_stav(py, nazev):
    """'hotovo', 'stahuje' (běží stahování na pozadí) nebo 'chybi'."""
    zamek = slozka_dat() / "modely" / "stahovani.pid"
    try:
        if bezi(int(zamek.read_text().strip())):
            return "stahuje"
    except (OSError, ValueError):
        pass
    kod, _ = spust_tiche([str(py), "-c", JE_MODEL, nazev], env=prostredi(), limit=120)
    return "hotovo" if kod == 0 else "chybi"


def bezi(pid):
    if JE_WINDOWS:
        kod, vystup = spust_tiche(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], limit=30)
        return kod == 0 and str(pid) in vystup
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def model(py, argv):
    """Krok model: stáhne model přepisu dopředu, aby první přepis nečekal."""
    nazev = MODEL_PREPISU
    if "--model" in argv and argv.index("--model") + 1 < len(argv):
        nazev = argv[argv.index("--model") + 1]
    stav = model_stav(py, nazev)
    print("STATUS model %s: %s" % (nazev, stav), flush=True)
    if stav == "hotovo":
        print("✅ Model přepisu je stažený.")
        return 0
    if stav == "stahuje":
        print("⏳ Model přepisu se pořád stahuje na pozadí. Přepis na něj případně počká.")
        return 0
    if "--stav" in argv:
        print("ℹ️ Model přepisu zatím stažený není. Stáhne se při prvním přepisu (asi 1,6 GB).")
        return 0
    slozka = slozka_dat() / "modely"
    slozka.mkdir(parents=True, exist_ok=True)
    if "--na-pozadi" in argv:
        log = open(slozka / "stahovani.log", "w", encoding="utf-8")
        volby = {}
        if JE_WINDOWS:   # bez okna a nezávisle na Claudovi, aby stahování běželo dál
            volby["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED, NEW_GROUP, NO_WINDOW
        else:
            volby["start_new_session"] = True
        proc = subprocess.Popen([str(py), "-c", STAHNI_MODEL, nazev], env=prostredi(), stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, close_fds=True, **volby)
        (slozka / "stahovani.pid").write_text(str(proc.pid))
        print("⏳ Model přepisu (asi 1,6 GB) se stahuje na pozadí. Můžeš normálně pokračovat.")
        return 0
    print("⏳ Stahuju model přepisu (asi 1,6 GB, jednou). Podle internetu to trvá pár minut.", flush=True)
    kod = subprocess.call([str(py), "-c", STAHNI_MODEL, nazev], env=prostredi())
    if kod == 0:
        print("✅ Model přepisu je stažený.")
        return 0
    print("🔴 Model přepisu se nestáhl. Udělej: zkontroluj internet a spusť krok znovu, co už se stáhlo, zůstává.")
    return 1


def spust_modul(nazev, argv):
    """Spustí skript, který běží jen na standardní knihovně, v tomhle Pythonu (kontrola, aktualizace, cink)."""
    os.environ.update({k: v for k, v in prostredi().items() if k in ("PATH", "REEL_STUDIO_DATA", "HF_HOME")})
    uv = najdi_uv()
    if uv:   # kontrola počítače hledá uv v PATH
        os.environ["PATH"] = str(Path(uv).parent) + os.pathsep + os.environ.get("PATH", "")
    if str(TADY) not in sys.path:
        sys.path.insert(0, str(TADY))
    if nazev == "aktualizace":
        import aktualizace as modul
    elif nazev == "kontrola":
        from studio import kontrola_pocitace as modul
    else:
        from studio import cink as modul
    return modul.main(argv)


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "kde":
        ff = vlastni_ffmpeg()[0]
        print("Nástroje: %s\nProstředí a modely: %s\nuv: %s\nffmpeg: %s" % (
            TADY, slozka_dat(), najdi_uv() or "nenalezeno",
            ff if ff.exists() else (shutil.which("ffmpeg") or "nenalezeno")))
        return 0
    if argv[0] in ("kontrola", "aktualizace", "cink"):
        return spust_modul(argv[0], argv[1:])
    py, zpravy, ok = priprav()
    if argv[0] == "priprava":
        for dilci_ok, zprava in zpravy:
            print(("✅ " if dilci_ok else "🔴 ") + zprava)
        if ok:
            ok, zprava = zkus_knihovny(py)
            print(("✅ " if ok else "🔴 ") + zprava)
            zpravy.append((ok, zprava))
        if ok:
            print("✅ Příprava prostředí: hotovo.")
        elif not any("Udělej:" in z for _, z in zpravy):
            print("🔴 Příprava prostředí se nepovedla. Udělej: spusť přípravu znovu. Když to skončí stejně, "
                  "pošli Marcele tenhle výpis.")
        return 0 if ok else 1
    if not ok:
        print("🔴 Studio nejde spustit: " + " ".join(z for o, z in zpravy if not o) +
              " Udělej: spusť nejdřív instalaci.")
        return 1
    if argv[0] == "model":
        return model(py, argv[1:])
    cmd = [str(py), "-m", "studio"] + argv
    return subprocess.call(cmd, env=prostredi())   # pracovní složka zůstává, relativní cesty zákaznice platí


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
