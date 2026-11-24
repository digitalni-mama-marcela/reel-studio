"""Tichá kontrola při otevření chatu (hook SessionStart přes cink). Jen čte, nic nestahuje, nic nemění.

Marcela 20. 11. 2026 (rozbor druhého kurzu, body E1 a E4): Claude má vědět, co je na počítači zvláštního, dřív než
zákaznice cokoli napíše, a studio musí hlídat, že má zákaznice zapnuté automatické aktualizace.

Co dělá:
  1. zapíše otisk počítače do složky studia (pocitac.txt): systém, čip, paměť, volné místo, verze studia,
     aktualizace zapnuté ano/ne. Když přijde problém, odpověď „co je to za počítač“ už leží tam.
  2. vypíše Claudovi poznámku JEN když je co hlásit: aktualizace vypnuté, nepodporovaný počítač, málo místa,
     složka Reely v cloudu. Normální stav = žádný výstup.
Nikdy nezapisuje cesty k videím, přepisy ani nastavení zákaznice. Domovská složka se v otisku zkracuje na ~.
Jen standardní knihovna, Python 3.9.
"""
import json
import os
import platform
from datetime import datetime
from pathlib import Path

MARKETPLACE = "digitalni-mama-marcela"


def slozka_claude():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def aktualizace_zapnute(claude=None, nazev=MARKETPLACE):
    """True / False, nebo None, když plugin z našeho katalogu v Claude Code není (třeba zkouška ze složky)."""
    claude = Path(claude) if claude else slozka_claude()
    try:
        known = json.loads((claude / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if nazev not in known:
        return None
    if (known.get(nazev) or {}).get("autoUpdate") is True:
        return True
    try:
        nastaveni = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        nastaveni = {}
    return ((nastaveni.get("extraKnownMarketplaces") or {}).get(nazev) or {}).get("autoUpdate") is True


def je_slozka_reely(cesta):
    p = Path(cesta)
    return p.name.lower().startswith("reely") or (p / "NASTAVENI").is_dir() or (p / "SEZNAM.md").is_file()


def zkrat(text):
    domov = str(Path.home())
    return str(text).replace(domov, "~")


def poznamky_a_otisk(cwd, data_slozka, verze=None, claude=None):
    """Vrátí (seznam poznámek pro Clauda, text otisku). Každá kontrola je v try: kontrola nikdy nesmí shodit chat."""
    from . import kontrola_pocitace as kp
    poznamky, otisk = [], ["Otisk počítače pro Reel Studio, %s" % datetime.now().isoformat(timespec="seconds")]
    try:
        pocitac = kp.zjisti_pocitac()
        otisk.append("Systém: %s %s, %s, čip %s, paměť %s GB" % (
            pocitac.get("system"), pocitac.get("verze_systemu") or pocitac.get("verze") or "",
            platform.machine(), pocitac.get("cip") or "?", pocitac.get("pamet_gb") or "?"))
        v = kp.kontrola_pocitace(pocitac)
        if v["stav"] == kp.CHYBA:
            poznamky.append("Počítač: %s %s" % (v["zprava"], v.get("dalsi_krok") or ""))
    except Exception as e:  # noqa: BLE001
        otisk.append("Systém: nepodařilo se zjistit (%s)" % type(e).__name__)
    try:
        m = kp.kontrola_mista(data_slozka)
        otisk.append("Volné místo: %s GB" % m["data"].get("volno_gb"))
        if m["stav"] == kp.CHYBA:
            poznamky.append("Místo na disku: %s" % m["zprava"])
    except Exception:  # noqa: BLE001
        pass
    try:
        if je_slozka_reely(cwd):
            s = kp.kontrola_slozky(cwd)
            otisk.append("Složka Reely v cloudu: %s" % ("ano" if s["stav"] == kp.CHYBA else "ne"))
            if s["stav"] == kp.CHYBA:
                poznamky.append("Složka: %s %s" % (zkrat(s["zprava"]), s.get("dalsi_krok") or ""))
    except Exception:  # noqa: BLE001
        pass
    zapnute = aktualizace_zapnute(claude)
    otisk.append("Verze studia: %s, automatické aktualizace: %s" % (
        verze or "?", {True: "zapnuté", False: "VYPNUTÉ", None: "studio není z katalogu"}[zapnute]))
    if zapnute is False:
        poznamky.append("Automatické aktualizace studia jsou vypnuté, zákaznice by nedostávala opravy ani nové styly. "
                        "Spusť krok STUDIO aktualizace (dovednost instalace, krok 4b) a řekni jí jednou větou: "
                        "„Zapnula jsem ti automatické aktualizace studia.“")
    return poznamky, "\n".join(zkrat(r) for r in otisk) + "\n"


def main(cwd=None, data_slozka=None, verze=None):
    """Vrátí text pro Clauda, nebo None. Otisk zapíše do složky studia."""
    cwd = cwd or os.getcwd()
    data_slozka = Path(data_slozka or os.environ.get("REEL_STUDIO_DATA") or Path.home())
    poznamky, otisk = poznamky_a_otisk(cwd, data_slozka, verze)
    try:
        (data_slozka / "pocitac.txt").write_text(otisk, encoding="utf-8")
    except OSError:
        pass
    if not poznamky:
        return None
    return ("[Reel Studio, kontrola při otevření chatu] Než odpovíš, vyřeš se zákaznicí tohle (jednoduše, česky, "
            "bez odborných slov):\n- " + "\n- ".join(poznamky))
