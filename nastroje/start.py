"""Spouštěč studia. Jen standardní knihovna, běží na Pythonu 3.9 i novějším, na Macu i Windows.

Co dělá:
  1. najde (nebo založí) prostředí studia MIMO složku Reely a mimo iCloud a OneDrive:
       Mac:     ~/Library/Application Support/ClaudeReelStudio
       Windows: %LOCALAPPDATA%\\ClaudeReelStudio
     V něm je Python 3.12 a knihovny (uv venv + uv pip install podle pozadavky.txt) a modely přepisu (HF_HOME).
  2. spustí krok studia: python -m studio <krok> ...  (kód je vedle tohoto souboru ve složce studio/)

Použití: python3 start.py <krok> [parametry]       (stejné kroky jako python -m studio)
         python3 start.py priprava                  (jen připraví prostředí a vypíše zelenou/červenou)
         python3 start.py kde                       (vypíše cesty)
Proměnná REEL_STUDIO_DATA přepíše složku s prostředím (pro zkoušky).
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

TADY = Path(__file__).resolve().parent
POZADAVKY = TADY / "pozadavky.txt"
PYTHON_VERZE = "3.12"


def slozka_dat():
    env = os.environ.get("REEL_STUDIO_DATA")
    if env:
        return Path(env)
    if platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ClaudeReelStudio"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ClaudeReelStudio"
    return Path.home() / ".claude-reel-studio"


def python_ve_venv(venv):
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def najdi_uv():
    cesta = shutil.which("uv")
    if cesta:
        return cesta
    for p in (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv",
              Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv"),
              Path.home() / ".local" / "bin" / "uv.exe"):
        if p.exists():
            return str(p)
    return None


def otisk_pozadavku():
    import hashlib
    return hashlib.sha256(POZADAVKY.read_bytes()).hexdigest()[:16]


def priprav(tise=False):
    """Založí prostředí, když chybí nebo se změnily požadavky. Vrátí (python, zpráva, ok)."""
    data = slozka_dat()
    venv = data / "venv"
    znacka = data / "venv-pozadavky.txt"
    py = python_ve_venv(venv)
    if py.exists() and znacka.exists() and znacka.read_text(encoding="utf-8").strip() == otisk_pozadavku():
        return py, "Prostředí studia je připravené (%s)." % data, True
    uv = najdi_uv()
    if not uv:
        return None, "Chybí nástroj uv, který stahuje Python a knihovny.", False
    data.mkdir(parents=True, exist_ok=True)
    if not tise:
        print("⏳ Připravuju prostředí studia do %s (poprvé to trvá pár minut, stahuje se Python a knihovny)." % data, flush=True)
    kroky = [[uv, "venv", "--python", PYTHON_VERZE, "--allow-existing", str(venv)],
             [uv, "pip", "install", "--python", str(py), "-r", str(POZADAVKY)]]
    for cmd in kroky:
        v = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if v.returncode != 0:
            return None, "Příprava prostředí selhala: %s" % (v.stderr.strip().splitlines() or ["bez hlášky"])[-1][:300], False
    znacka.write_text(otisk_pozadavku(), encoding="utf-8")
    return py, "Prostředí studia je připravené (%s)." % data, True


def prostredi():
    env = dict(os.environ)
    data = slozka_dat()
    env.setdefault("HF_HOME", str(data / "modely"))           # modely přepisu mimo Reely (D3)
    env["PYTHONPATH"] = str(TADY) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["REEL_STUDIO_DATA"] = str(data)
    return env


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "kde":
        print("Nástroje: %s\nProstředí a modely: %s\nuv: %s" % (TADY, slozka_dat(), najdi_uv() or "nenalezeno"))
        return 0
    py, zprava, ok = priprav()
    if argv[0] == "priprava":
        print(("✅ Příprava prostředí: " if ok else "🔴 Příprava prostředí: ") + zprava +
              ("" if ok else " Udělej: spusť instalaci znovu (dovednost instalace), nebo mi pošli tenhle řádek."))
        return 0 if ok else 1
    if not ok:
        print("🔴 Studio nejde spustit: " + zprava + " Udělej: spusť nejdřív instalaci.")
        return 1
    cmd = [str(py), "-m", "studio"] + argv
    return subprocess.call(cmd, env=prostredi())   # pracovní složka zůstává, relativní cesty zákaznice platí


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
