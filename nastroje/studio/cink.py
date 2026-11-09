"""Zvuková upozornění: "hotovo" a "potřebuju tě".

Příkazy:
  hotovo         zahraje zvuk, že je práce hotová
  potrebuji-te   zahraje zvuk, že studio čeká na zákaznici (povolení, otázka)
  zacatek        zapíše čas, kdy zákaznice zadala úkol
  konec          zahraje "hotovo" jen když od zápisu uplynulo víc než LIMIT_SEKUND
  zkouska        zahraje oba zvuky za sebou

Mac: systémové zvuky z /System/Library/Sounds (OVĚŘENO, že existují).
Windows: větev je napsaná, ale NEBYLA vyzkoušena (test T10). Když zvuk nejde, ozve se aspoň pípnutí terminálu.
Jen standardní knihovna, Python 3.9.
"""
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LIMIT_SEKUND = 60
ZVUKY_MAC = {"hotovo": "Glass", "potrebuji-te": "Funk"}
ZVUKY_WINDOWS = {"hotovo": "Asterisk", "potrebuji-te": "Exclamation"}
SOUBOR_ZACATKU = Path(tempfile.gettempdir()) / "claude-reel-studio-zacatek.txt"


def uplynulo_dost(zacatek, ted, limit=LIMIT_SEKUND):
    """Je rozdíl mezi dvěma časy větší než limit? Čistá funkce kvůli testům."""
    return zacatek is not None and (ted - zacatek) > limit


def pipnuti():
    sys.stdout.write("\a")
    sys.stdout.flush()


def prehraj(druh):
    """Zahraje zvuk. Vrací True, když zazněl systémový zvuk, jinak se ozve aspoň pípnutí."""
    system = platform.system()
    try:
        if system == "Darwin":
            nazev = os.environ.get("REEL_ZVUK_" + druh.upper().replace("-", "_"), ZVUKY_MAC[druh])
            soubor = Path("/System/Library/Sounds") / (nazev + ".aiff")
            if soubor.exists():
                subprocess.run(["afplay", str(soubor)], timeout=10)
                return True
        elif system == "Windows":
            prikaz = "[System.Media.SystemSounds]::%s.Play(); Start-Sleep -Milliseconds 800" % ZVUKY_WINDOWS[druh]
            subprocess.run(["powershell", "-NoProfile", "-Command", prikaz], timeout=10)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    pipnuti()
    return False


def zapis_zacatek():
    SOUBOR_ZACATKU.write_text(str(time.time()), encoding="utf-8")


def precti_zacatek():
    try:
        return float(SOUBOR_ZACATKU.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def konec():
    zacatek = precti_zacatek()
    try:
        SOUBOR_ZACATKU.unlink()
    except OSError:
        pass
    if uplynulo_dost(zacatek, time.time()):
        prehraj("hotovo")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    prikaz = argv[0] if argv else ""
    # Hooky Claude Code posílají na vstup JSON. Musí se přečíst, aby na druhé straně nevznikla chyba.
    # Čte se jen, když na vstupu něco je (hook pošle JSON a zavře). Jinak by příkaz z terminálu bez vstupu čekal navěky.
    try:
        if not sys.stdin.isatty():
            import select
            if select.select([sys.stdin], [], [], 0.5)[0]:
                sys.stdin.read()
    except (OSError, ValueError, ImportError):
        pass
    if prikaz in ("hotovo", "potrebuji-te"):
        prehraj(prikaz)
    elif prikaz == "zacatek":
        zapis_zacatek()
    elif prikaz == "konec":
        konec()
    elif prikaz == "zkouska":
        prehraj("potrebuji-te")
        time.sleep(1)
        prehraj("hotovo")
    else:
        sys.stderr.write("Použití: cink.py hotovo | potrebuji-te | zacatek | konec | zkouska\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
