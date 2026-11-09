"""Hlášení kroků: každý krok skončí zeleně nebo červeně, česky, a zapíše se do stav.json.

Vzor (Notion 01): ✅ Přepis hotový: 2:46 videa, 486 slov. Další krok: kontrola slov.
                  🔴 Přepis se nezdařil: důvod. Udělej: jedna věta.
Jen standardní knihovna, Python 3.9.
"""
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

ZELENA, CERVENA, INFO, BEZI = "zelena", "cervena", "info", "bezi"
ZNACKY = {ZELENA: "✅", CERVENA: "🔴", INFO: "ℹ️", BEZI: "⏳"}
VERZE_STUDIA = "0.2"


def _utf8():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cas_text(s):
    """Sekundy jako m:ss,d (0:53,8)."""
    m, sec = divmod(float(s), 60)
    return "%d:%04.1f" % (m, sec)


def zprava(stav, krok, text, dalsi=None, udelej=None):
    """Složí jednu řádku hlášení."""
    radek = "%s %s %s" % (ZNACKY[stav], krok, text)
    if stav == ZELENA and dalsi:
        radek += " Další krok: %s" % dalsi
    if stav == CERVENA and udelej:
        radek += " Udělej: %s" % udelej
    return radek


class Krok:
    """Jeden krok studia. Měří čas, hlásí česky a zapisuje do stav.json ve složce PRACOVNI."""

    def __init__(self, nazev, pracovni=None, tise=False):
        self.nazev = nazev
        self.pracovni = Path(pracovni) if pracovni else None
        self.tise = tise
        self.zacatek = time.time()
        self.vysledek = None
        if self.pracovni:
            # krok právě běží: přehled průběhu to ukáže jako "běží"
            zapis_stav(self.pracovni, {"krok": nazev, "stav": BEZI, "zprava": "běží", "dalsi_krok": None, "udelej": None,
                                       "trvani_s": 0, "kdy": datetime.now().isoformat(timespec="seconds"), "data": {}})

    def _hotovo(self, stav, text, dalsi=None, udelej=None, data=None):
        _utf8()
        radek = zprava(stav, self.nazev + ":", text, dalsi, udelej)
        if not self.tise:
            print(radek)
            sys.stdout.flush()
        self.vysledek = {"krok": self.nazev, "stav": stav, "zprava": text, "dalsi_krok": dalsi, "udelej": udelej,
                         "trvani_s": round(time.time() - self.zacatek, 1),
                         "kdy": datetime.now().isoformat(timespec="seconds"), "data": data or {}}
        if self.pracovni:
            zapis_stav(self.pracovni, self.vysledek)
        return self.vysledek

    def zelena(self, text, dalsi=None, data=None):
        return self._hotovo(ZELENA, text, dalsi=dalsi, data=data)

    def cervena(self, text, udelej, data=None):
        return self._hotovo(CERVENA, text, udelej=udelej, data=data)

    def info(self, text):
        _utf8()
        if not self.tise:
            print("   %s %s" % (ZNACKY[INFO], text))
            sys.stdout.flush()

    def kod(self):
        """Návratový kód pro příkazovou řádku: 0 zelená, 1 červená."""
        return 0 if self.vysledek and self.vysledek["stav"] == ZELENA else 1


def nacti_stav(pracovni):
    soubor = Path(pracovni) / "stav.json"
    if not soubor.exists():
        return {"verze_studia": VERZE_STUDIA, "system": platform.system(), "kroky": {}, "poradi": []}
    try:
        return json.loads(soubor.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verze_studia": VERZE_STUDIA, "system": platform.system(), "kroky": {}, "poradi": []}


def zapis_stav(pracovni, vysledek):
    """Přidá nebo přepíše záznam o kroku. Starší záznam stejného kroku se uloží do historie."""
    pracovni = Path(pracovni)
    pracovni.mkdir(parents=True, exist_ok=True)
    stav = nacti_stav(pracovni)
    krok = vysledek["krok"]
    stary = stav["kroky"].get(krok)
    if stary and stary.get("stav") != BEZI:
        stav.setdefault("historie", []).append(stary)
    stav["kroky"][krok] = vysledek
    if krok not in stav["poradi"]:
        stav["poradi"].append(krok)
    stav["posledni_krok"] = krok
    stav["posledni_zmena"] = vysledek["kdy"]
    (pracovni / "stav.json").write_text(json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8")
    return stav
