"""Kontrola počítače (krok 0).

Zjistí systém, čip, volné místo, nástroje a to, zda je složka v cloudu.
CapCut a písma v systému se nekontrolují: kurz CapCut nepoužívá a studio kreslí text vlastními písmy
(složka pisma pluginu). kontrola_capcutu a kontrola_pisem zůstávají jen pro volitelný projekt do CapCutu.
Používá jen standardní knihovnu Pythonu a běží i na Pythonu 3.9, aby šla spustit dřív,
než se cokoli doinstaluje.

Windows: větev je napsaná, ale na Windows ještě NEBYLA vyzkoušena (test T10).
Spouští se přes spouštěč: `spust.sh kontrola ...` (Mac) nebo `spust.ps1 kontrola ...` (Windows).
"""
import argparse
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OK = "ok"
CHYBA = "chyba"
INFO = "info"
ZNACKY = {OK: "✅", CHYBA: "🔴", INFO: "ℹ️"}

# Model přepisu turbo (výchozí): 1,5 GB na disku (OVĚŘENO měřením na Macu 12. 11. 2026, du).
VELIKOST_MODELU_GB = 1.6
# Celé studio s modelem: uv, Python, knihovny, ffmpeg asi 0,9 GB + model 1,6 GB (OVĚŘENO 12. 11. 2026).
# Kopie videí a hotové reely chtějí další místo, proto aspoň 5 GB volných (stejně jako popis instalace).
POTREBNE_MISTO_GB = 5.0

# Písma podle vzhledu. Hledáme podle názvu souboru bez mezer, pomlček a velikosti písmen.
PISMA_VZHLEDU = {
    "serif": [("Playfair Display", "playfairdisplay"), ("Instrument Serif", "instrumentserif")],
}

TESTOVACI_VETA = "Příliš žluťoučký kůň úpěl ďábelské ódy. ě š č ř ž ý á í é ú ů ď ť ň"

# Co od ffmpeg potřebujeme (filtry, dekodér, kodér). Textové filtry nepotřebujeme,
# texty kreslí náš kód.
POTREBNE_FILTRY = ["overlay", "loudnorm"]
KODERY_H264 = ["libx264", "h264_videotoolbox", "h264_nvenc", "h264_mf"]
TEXTOVE_FILTRY = ["drawtext", "subtitles", "ass"]


def spust(prikaz, limit=20):
    """Spustí příkaz a vrátí (návratový kód, výstup). Když příkaz nejde spustit, vrátí (None, "")."""
    try:
        v = subprocess.run(prikaz, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           encoding="utf-8", errors="replace", timeout=limit)
        return v.returncode, v.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def vysledek(klic, stav, zprava, dalsi=None, data=None):
    return {"klic": klic, "stav": stav, "zprava": zprava, "dalsi_krok": dalsi, "data": data or {}}


def ma_polozku(vystup, nazev):
    """Je v seznamu filtrů, kodérů nebo dekodérů z ffmpeg položka s tímto názvem?"""
    return re.search(r"^\s*\S+\s+%s\s" % re.escape(nazev), vystup, re.M) is not None


def je_uvnitr(cesta, koren):
    try:
        Path(cesta).resolve().relative_to(Path(koren).resolve())
        return True
    except (ValueError, OSError):
        return False


def pamet_windows():
    import ctypes

    class Stav(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    s = Stav()
    s.dwLength = ctypes.sizeof(Stav)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return round(s.ullTotalPhys / 1024 ** 3)
    except (AttributeError, OSError):
        pass
    return None


def zjisti_pocitac():
    system = platform.system()
    pocitac = {"system": system, "architektura": platform.machine().lower(), "verze": "",
               "cip": "", "pamet_gb": None, "apple_silicon": False}
    if system == "Darwin":
        pocitac["verze"] = platform.mac_ver()[0]
        pocitac["cip"] = spust(["sysctl", "-n", "machdep.cpu.brand_string"])[1].strip()
        pamet = spust(["sysctl", "-n", "hw.memsize"])[1].strip()
        if pamet.isdigit():
            pocitac["pamet_gb"] = round(int(pamet) / 1024 ** 3)
        arm = spust(["sysctl", "-n", "hw.optional.arm64"])[1].strip() == "1"
        pocitac["apple_silicon"] = arm or pocitac["cip"].startswith("Apple")
    elif system == "Windows":
        pocitac["verze"] = platform.version()
        pocitac["cip"] = platform.processor()
        pocitac["pamet_gb"] = pamet_windows()
        pocitac["architektura"] = (os.environ.get("PROCESSOR_ARCHITEW6432")
                                   or os.environ.get("PROCESSOR_ARCHITECTURE")
                                   or pocitac["architektura"]).lower()
    return pocitac


def posud_podporu(pocitac):
    """Verze 1 oficiálně: Mac s čipem M a Windows s procesorem x64 (návrh D17)."""
    if pocitac["system"] == "Darwin":
        return "podporovano" if pocitac["apple_silicon"] else "bez_zaruky"
    if pocitac["system"] == "Windows":
        return "podporovano" if pocitac["architektura"] in ("amd64", "x86_64") else "bez_zaruky"
    return "nepodporovano"


def kontrola_pocitace(pocitac):
    system = pocitac["system"]
    pamet = ("%d GB paměti" % pocitac["pamet_gb"]) if pocitac["pamet_gb"] else "paměť nezjištěna"
    if system == "Darwin":
        nazev = "macOS %s" % pocitac["verze"]
        # Knihovna na čtení videa (av 19) má pro čip M sestavení až od macOS 14, pro Intel od macOS 11;
        # obrazová knihovna (opencv 4.11) od macOS 13 (PyPI, ověřeno 11. 11. 2026).
        minimum = 14 if pocitac["apple_silicon"] else 13
        try:
            stary = int(pocitac["verze"].split(".")[0]) < minimum
        except ValueError:
            stary = False
        if stary:
            return vysledek("pocitac", CHYBA, "%s je moc starý." % nazev,
                            "Potřebuješ macOS %d nebo novější. Aktualizuj systém (Nastavení systému → Obecné → "
                            "Aktualizace softwaru)." % minimum, pocitac)
    elif system == "Windows":
        nazev = "Windows %s" % pocitac["verze"]
        try:
            stary = int(pocitac["verze"].split(".")[2]) < 17763
        except (ValueError, IndexError):
            stary = False
        if stary:
            return vysledek("pocitac", CHYBA, "%s je moc starý." % nazev,
                            "Potřebuješ Windows 10 verze 1809 nebo novější. Aktualizuj systém.", pocitac)
    else:
        return vysledek("pocitac", CHYBA, "Systém %s zatím nepodporujeme." % system,
                        "Použij Mac s čipem M nebo Windows počítač.", pocitac)
    zprava = "%s, %s, %s." % (nazev, pocitac["cip"] or pocitac["architektura"], pamet)
    if posud_podporu(pocitac) != "podporovano":
        zprava += " Bez záruky: oficiálně podporujeme Mac s čipem M a Windows s procesorem x64."
    return vysledek("pocitac", OK, zprava, None, pocitac)


def nejblizsi_existujici(cesta):
    p = Path(cesta)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def kontrola_mista(cesta):
    volno_gb = shutil.disk_usage(str(nejblizsi_existujici(cesta))).free / 1e9
    data = {"volno_gb": round(volno_gb, 1), "model_gb": VELIKOST_MODELU_GB, "potreba_gb": POTREBNE_MISTO_GB}
    if volno_gb < POTREBNE_MISTO_GB:
        return vysledek("misto", CHYBA,
                        "Volné místo je %.1f GB. Studio potřebuje aspoň %.0f GB (samo zabere asi 2,5 GB, zbytek je "
                        "pro videa)." % (volno_gb, POTREBNE_MISTO_GB),
                        "Uvolni místo na disku (smaž nebo přesuň staré soubory) a spusť kontrolu znovu.", data)
    return vysledek("misto", OK,
                    "Volné místo je %.1f GB. Studio samo zabere asi 2,5 GB." % volno_gb, None, data)


def icloud_zapnuto(klic):
    if platform.system() != "Darwin":
        return False
    kod, vystup = spust(["defaults", "read", "com.apple.finder", klic])
    return kod == 0 and vystup.strip() == "1"


def zjisti_cloud(cesta, system, home, icloud_plocha=False, icloud_dokumenty=False, env=None):
    """Vrátí seznam důvodů, proč složka patří do cloudu. Čistá funkce kvůli testům."""
    s = str(cesta)
    duvody = []
    if system == "Darwin":
        if "com~apple~CloudDocs" in s or "/Mobile Documents/" in s:
            duvody.append("iCloud Drive")
        if icloud_plocha and je_uvnitr(cesta, Path(home) / "Desktop"):
            duvody.append("Plocha se synchronizuje s iCloudem")
        if icloud_dokumenty and je_uvnitr(cesta, Path(home) / "Documents"):
            duvody.append("Dokumenty se synchronizují s iCloudem")
    if system == "Windows":
        env = env or {}
        for promenna in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            koren = env.get(promenna)
            if koren and je_uvnitr(cesta, koren) and "OneDrive" not in duvody:
                duvody.append("OneDrive")
        if "onedrive" in s.lower() and "OneDrive" not in duvody:
            duvody.append("OneDrive")
    male = s.lower()
    if "dropbox" in male:
        duvody.append("Dropbox")
    if "google drive" in male or "googledrive" in male:
        duvody.append("Google Drive")
    return duvody


def kontrola_slozky(cesta):
    real = Path(cesta).expanduser().resolve()
    system = platform.system()
    duvody = zjisti_cloud(real, system, Path.home(), icloud_zapnuto("FXICloudDriveDesktop"),
                          icloud_zapnuto("FXICloudDriveDocuments"), dict(os.environ))
    data = {"cesta": str(real), "cloud": duvody}
    if duvody:
        return vysledek("slozka", CHYBA, "Složka %s je v cloudu: %s." % (real, ", ".join(duvody)),
                        "Velká videa se odkládají do cloudu a pak nejdou přečíst. Přesuň složku Reely do "
                        "domovské složky, mimo Plochu, Dokumenty a cloudové složky.", data)
    return vysledek("slozka", OK, "Složka %s není v cloudu." % real, None, data)


def kontrola_cesty(cesta):
    s = str(Path(cesta).expanduser().resolve())
    zvlastnosti = []
    if not s.isascii():
        zvlastnosti.append("diakritiku")
    if " " in s:
        zvlastnosti.append("mezery")
    if zvlastnosti:
        return vysledek("cesta", INFO, "Cesta obsahuje %s. Nástroje to musí zvládnout (test T10)." %
                        " a ".join(zvlastnosti), None, {"cesta": s})
    return vysledek("cesta", OK, "Cesta nemá diakritiku ani mezery.", None, {"cesta": s})


def nastroj(prikaz, argumenty):
    cesta = shutil.which(prikaz)
    if not cesta:
        return None, ""
    kod, vystup = spust([cesta] + argumenty)
    radky = vystup.strip().splitlines()
    return cesta, (radky[0] if radky else "")


# uv a ffmpeg si studio stahuje samo do své složky (spouštěč spust.sh / spust.ps1 a krok priprava).
# Zákaznice nic neinstaluje, nepotřebuje Homebrew, winget ani heslo.
POUZIJ_SPOUSTEC = ("Spusť kontrolu přes spouštěč studia (Mac: spust.sh, Windows: spust.ps1), ten si uv "
                   "stáhne sám.")


def kontrola_uv(system):
    cesta, verze = nastroj("uv", ["--version"])
    if not cesta:
        return vysledek("uv", CHYBA, "uv chybí.", POUZIJ_SPOUSTEC)
    return vysledek("uv", OK, verze + ".", None, {"cesta": cesta, "verze": verze})


def kontrola_ffmpeg(system):
    cesta, verze = nastroj("ffmpeg", ["-hide_banner", "-version"])
    ffprobe = shutil.which("ffprobe")
    nastroj_instalace = "Smaž složku ffmpeg ve složce prostředí studia a spusť krok priprava znovu."
    if not cesta or not ffprobe:
        return vysledek("ffmpeg", INFO, "ffmpeg zatím není. Studio si ho stáhne samo v kroku Příprava, "
                        "bez hesla.", None)
    filtry = spust([cesta, "-hide_banner", "-filters"])[1]
    dekodery = spust([cesta, "-hide_banner", "-decoders"])[1]
    kodery = spust([cesta, "-hide_banner", "-encoders"])[1]
    chybi = ["filtr " + f for f in POTREBNE_FILTRY if not ma_polozku(filtry, f)]
    if not ma_polozku(dekodery, "hevc"):
        chybi.append("dekodér hevc (video z iPhonu)")
    h264 = [k for k in KODERY_H264 if ma_polozku(kodery, k)]
    if not h264:
        chybi.append("kodér H.264")
    textove = [f for f in TEXTOVE_FILTRY if ma_polozku(filtry, f)]
    data = {"cesta": cesta, "verze": verze, "kodery_h264": h264, "textove_filtry": textove}
    if chybi:
        return vysledek("ffmpeg", CHYBA, "%s. Chybí: %s." % (verze, ", ".join(chybi)),
                        nastroj_instalace, data)
    zprava = "%s. Umí přečíst video z iPhonu (HEVC) a položit text na video." % verze
    if not textove:
        zprava += " Textové filtry nemá. Nevadí, texty kreslí náš kód."
    return vysledek("ffmpeg", OK, zprava, None, data)


def kontrola_capcutu(system):
    verze = None
    nalezen = False
    if system == "Darwin":
        for koren in (Path("/Applications"), Path.home() / "Applications"):
            plist = koren / "CapCut.app" / "Contents" / "Info.plist"
            if plist.exists():
                nalezen = True
                try:
                    with open(str(plist), "rb") as f:
                        verze = plistlib.load(f).get("CFBundleShortVersionString")
                except (OSError, plistlib.InvalidFileException):
                    pass
                break
    elif system == "Windows":
        # Rozložení složek CapCutu na Windows NEBYLO ověřeno. Hledáme jen podsložky s číslem verze.
        koren = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps"
        if koren.exists():
            nalezen = True
            verze_slozky = sorted(p.name for p in koren.iterdir() if re.match(r"^\d+(\.\d+)+$", p.name))
            verze = verze_slozky[-1] if verze_slozky else None
    if not nalezen:
        return vysledek("capcut", CHYBA, "CapCut není nainstalovaný.",
                        "Stáhni CapCut z capcut.com (verze zdarma stačí) a jednou ho otevři. MP4 půjde i bez něj, "
                        "projekt pro CapCut ne.")
    return vysledek("capcut", OK, "CapCut %s je nainstalovaný." % (verze or "(verze nezjištěna)"),
                    None, {"verze": verze})


def slozky_s_pismy(system):
    if system == "Darwin":
        return [Path.home() / "Library" / "Fonts", Path("/Library/Fonts")]
    if system == "Windows":
        return [Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
    return []


def najdi_pismo(system, token):
    nalezene = []
    for slozka in slozky_s_pismy(system):
        try:
            for p in slozka.iterdir():
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    if re.sub(r"[^a-z]", "", p.stem.lower()).startswith(token):
                        nalezene.append(p.name)
        except OSError:
            continue
    return sorted(nalezene)


def kontrola_pisem(system, vzhled):
    pisma = PISMA_VZHLEDU.get(vzhled, [])
    chybi, mam = [], {}
    for nazev, token in pisma:
        soubory = najdi_pismo(system, token)
        if soubory:
            mam[nazev] = soubory
        else:
            chybi.append(nazev)
    if chybi:
        return vysledek("pisma", CHYBA, "Chybí písma pro vzhled %s: %s." % (vzhled, ", ".join(chybi)),
                        "Písma s volnou licencí se nainstalují z Google Fonts. CapCut je nabídne, až budou "
                        "nainstalovaná v počítači.", {"vzhled": vzhled, "nalezena": mam, "chybi": chybi})
    return vysledek("pisma", OK, "Písma pro vzhled %s jsou nainstalovaná: %s." % (vzhled, ", ".join(mam)),
                    None, {"vzhled": vzhled, "nalezena": mam})


def kontrola_diakritiky():
    with tempfile.TemporaryDirectory() as d:
        soubor = Path(d) / "test.txt"
        soubor.write_text(TESTOVACI_VETA, encoding="utf-8")
        shoda = soubor.read_text(encoding="utf-8") == TESTOVACI_VETA
    if not shoda:
        return vysledek("diakritika", CHYBA, "Diakritika se při uložení do souboru pokazila.",
                        "Nahlas to: je to chyba v nastavení znakové sady počítače.")
    return vysledek("diakritika", OK, "Diakritika se uloží i přečte správně. Vidíš všechna písmena? %s" %
                    TESTOVACI_VETA, None)


def spust_kontroly(slozka, vzhled):
    pocitac = zjisti_pocitac()
    system = pocitac["system"]
    return [
        kontrola_pocitace(pocitac),
        kontrola_mista(slozka),
        kontrola_slozky(slozka),
        kontrola_cesty(slozka),
        kontrola_uv(system),
        kontrola_ffmpeg(system),
        kontrola_diakritiky(),
    ], pocitac


def vypis(vysledky):
    print("Kontrola počítače")
    for v in vysledky:
        print("%s %s" % (ZNACKY[v["stav"]], v["zprava"]))
        if v["stav"] == CHYBA and v["dalsi_krok"]:
            print("   Co dál: %s" % v["dalsi_krok"])
    zelene = sum(1 for v in vysledky if v["stav"] == OK)
    cervene = [v for v in vysledky if v["stav"] == CHYBA]
    if cervene:
        print("\n🔴 Kontrola skončila červeně: %d v pořádku, %d k opravě. Začni tím, co je nahoře." %
              (zelene, len(cervene)))
    else:
        print("\n✅ Kontrola skončila zeleně: %d v pořádku. Můžeš pokračovat." % zelene)
    return len(cervene)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Kontrola počítače pro Claude Reel Studio")
    parser.add_argument("--slozka", default=os.getcwd(), help="složka Reely (výchozí: aktuální složka)")
    parser.add_argument("--vzhled", default="serif", help="vzhled, podle kterého se kontrolují písma")
    parser.add_argument("--json", help="kam uložit výsledek jako JSON")
    args = parser.parse_args(argv)
    vysledky, pocitac = spust_kontroly(args.slozka, args.vzhled)
    cervene = vypis(vysledky)
    if args.json:
        Path(args.json).write_text(json.dumps({"pocitac": pocitac, "podpora": posud_podporu(pocitac),
                                               "vysledky": vysledky}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return 1 if cervene else 0


if __name__ == "__main__":
    sys.exit(main())
