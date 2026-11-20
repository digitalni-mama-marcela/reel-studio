"""Zvuková upozornění: "hotovo" a "potřebuju tě".

Příkazy:
  hotovo         zahraje zvuk, že je práce hotová
  potrebuji-te   zahraje zvuk, že studio čeká na zákaznici (povolení, otázka)
  zacatek        zapíše čas, kdy zákaznice zadala úkol; když se studio aktualizovalo, vypíše pro Clauda hlášku
  konec          zahraje "hotovo" jen když od zápisu uplynulo víc než LIMIT_SEKUND
  zkouska        zahraje oba zvuky za sebou
  start          tichá kontrola při otevření chatu (studio/start_relace.py), vypíše jen to, co je potřeba řešit

Mac: systémové zvuky z /System/Library/Sounds (OVĚŘENO, že existují).
Windows: větev je napsaná, ale NEBYLA vyzkoušena (test T10). Když zvuk nejde, ozve se aspoň pípnutí terminálu.
Jen standardní knihovna, Python 3.9.
"""
import json
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


# ---- Hláška o nové verzi (Marcela 20. 11. 2026: zákaznice musí vědět, že se nic neztratilo a co má udělat) ----
# Claude Code stáhne novou verzi pluginu sám (automatické aktualizace), ale načte ji až v novém chatu. Tenhle chat
# běží dál ve staré. Hook „zacatek“ to pozná a vypíše pokyn pro Clauda (výstup UserPromptSubmit dostane Claude):
#   a) ve složce pluginů už je novější verze, než ta, ve které běží tenhle chat -> „otevři nový chat“ (jednou),
#   b) první zpráva v nové verzi -> co je nového (NOVINKY.json v kořeni pluginu), jednou.
# Při úplně první instalaci se nic nevypisuje. Stav je ve složce studia (verze-stav.json), ne v pluginu.

def verze_klic(text):
    try:
        return tuple(int(x) for x in str(text).split("."))
    except ValueError:
        return ()


def koren_pluginu():
    koren = Path(__file__).resolve().parents[2]
    return koren if (koren / ".claude-plugin" / "plugin.json").is_file() else None


def bezici_verze(koren):
    try:
        return json.loads((koren / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def nejnovejsi_stazena(koren):
    """Složky verzí vedle té, ve které běžíme (…/cache/<marketplace>/reel-studio/<verze>)."""
    verze = [p.name for p in koren.parent.iterdir() if p.is_dir() and verze_klic(p.name)] if koren.parent.is_dir() else []
    return max(verze, key=verze_klic) if verze else None


def novinky_od(koren, od_verze):
    try:
        vse = json.loads((koren / "NOVINKY.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [vse[v] for v in sorted(vse, key=verze_klic) if verze_klic(v) > verze_klic(od_verze or "0")]


def hlaska_o_verzi(koren=None, stav_soubor=None):
    """Vrátí text pro Clauda, nebo None. Zapíše si, co už oznámil, aby se nic neopakovalo."""
    koren = koren or koren_pluginu()
    if koren is None:
        return None
    if stav_soubor is None:
        data = os.environ.get("REEL_STUDIO_DATA")
        if not data:
            return None
        stav_soubor = Path(data) / "verze-stav.json"
    try:
        stav = json.loads(Path(stav_soubor).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stav = {}
    bezi = bezici_verze(koren)
    if not bezi:
        return None
    text = None
    posledni = stav.get("posledni_bezici")
    if posledni is None:
        stav["posledni_bezici"] = bezi                    # první instalace: nic neoznamovat
    elif verze_klic(bezi) > verze_klic(posledni):
        nove = novinky_od(koren, posledni)
        stav["posledni_bezici"] = bezi
        if nove:
            text = ("[Reel Studio] Studio teď běží v nové verzi %s. Na začátku odpovědi řekni zákaznici jednou "
                    "krátkou větou, co je nového: %s Dodej, že její reely, videa i nastavení zůstaly, jak byly. "
                    "Neopakuj to." % (bezi, " ".join(nove)))
    stazena = nejnovejsi_stazena(koren)
    if text is None and stazena and verze_klic(stazena) > verze_klic(bezi) and stav.get("oznamena_stazena") != stazena:
        stav["oznamena_stazena"] = stazena
        text = ("[Reel Studio] Do počítače se právě stáhla nová verze studia (%s), tenhle chat ale běží ve starší %s. "
                "Na začátku odpovědi řekni zákaznici: „Stáhla se nová verze studia. Tvoje reely, videa i nastavení "
                "zůstávají, nic se neztratí. Až dokončíme, co právě děláme, zavři tenhle chat a otevři nový ve složce "
                "Reely, ať se nová verze načte.“ Rozdělanou práci dokonči normálně, stará verze funguje. Neopakuj to."
                % (stazena, bezi))
    try:
        Path(stav_soubor).parent.mkdir(parents=True, exist_ok=True)
        Path(stav_soubor).write_text(json.dumps(stav, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return text


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
        try:
            text = hlaska_o_verzi()
        except Exception:           # hláška nikdy nesmí shodit hook
            text = None
        if text:
            print(text)
    elif prikaz == "konec":
        konec()
    elif prikaz == "start":
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from studio import start_relace
            koren = koren_pluginu()
            text = start_relace.main(verze=bezici_verze(koren) if koren else None)
        except Exception:           # kontrola nikdy nesmí shodit otevření chatu
            text = None
        if text:
            print(text)
    elif prikaz == "zkouska":
        prehraj("potrebuji-te")
        time.sleep(1)
        prehraj("hotovo")
    else:
        sys.stderr.write("Použití: cink.py hotovo | potrebuji-te | zacatek | konec | start | zkouska\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
