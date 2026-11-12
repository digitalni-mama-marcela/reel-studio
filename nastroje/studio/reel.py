"""Složka reelu a seznam reelů (SEZNAM.md). Jen standardní knihovna, Python 3.9.

Strom (Notion 01):
  Reely/2026-10-14_nazev-reelu/
      PODKLADY-SEM/   video, screenshoty (sem zákaznice nahrává, studio sem kopíruje originál)
          NAHRAVKY-OBRAZOVKY/  nahrávky obrazovky (telefon, počítač): do reelu jdou jako video v rámečku,
                               ne jako její mluvení
      VYSTUP/         MP4, projekt pro CapCut, obálka
      PRACOVNI/       přepis, časová osa, stav.json (zákaznice nemusí otevírat)
Názvy složek jsou bez diakritiky a bez mezer, název reelu s diakritikou zůstává ve stav.json a v SEZNAM.md.
"""
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from .hlaseni import VERZE_STUDIA

PODSLOZKY = ("PODKLADY-SEM", "VYSTUP", "PRACOVNI")
VIDEO_PRIPONY = {".mp4", ".mov", ".m4v", ".mts", ".avi", ".mkv", ".webm", ".3gp"}
NAHRAVKY = "NAHRAVKY-OBRAZOVKY"          # podsložka PODKLADY-SEM; videa v ní nejsou klipy jejího mluvení
NAHRAVKY_PRIPONY = {".mp4", ".mov"}      # co umí vložka (prvky/vlozka.py)


def slug(nazev, max_delka=40):
    """Název bez diakritiky, malými písmeny, mezery a zvláštní znaky jako pomlčka."""
    bez = unicodedata.normalize("NFKD", nazev)
    bez = "".join(c for c in bez if not unicodedata.combining(c))
    bez = re.sub(r"[^A-Za-z0-9]+", "-", bez).strip("-").lower()
    bez = bez[:max_delka].strip("-")
    return bez or "reel"


def nazev_slozky(nazev, kdy=None):
    kdy = kdy or date.today()
    return "%s_%s" % (kdy.strftime("%Y-%m-%d"), slug(nazev))


def zaloz_reel(koren, nazev, kdy=None):
    """Založí složku reelu s podsložkami. Existující složku nikdy nepřepíše, přidá -2, -3. Vrátí cestu."""
    koren = Path(koren)
    koren.mkdir(parents=True, exist_ok=True)
    zaklad = nazev_slozky(nazev, kdy)
    cil, n = koren / zaklad, 2
    while cil.exists():
        cil = koren / ("%s-%d" % (zaklad, n))
        n += 1
    for p in PODSLOZKY:
        (cil / p).mkdir(parents=True)
    (cil / "PODKLADY-SEM" / NAHRAVKY).mkdir()
    stav = {"verze_studia": VERZE_STUDIA, "nazev": nazev, "slozka": cil.name,
            "zalozeno": datetime.now().isoformat(timespec="seconds"), "kroky": {}, "poradi": []}
    (cil / "PRACOVNI" / "stav.json").write_text(json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8")
    (cil / "PODKLADY-SEM" / "SEM-NAHRAJ-VIDEO.txt").write_text(
        "Sem nahraj natočené video (jedno nebo dvě se stejným obsahem) a případné screenshoty.\n"
        "Nahrávky obrazovky (z telefonu nebo počítače) dej do složky NAHRAVKY-OBRAZOVKY.\n"
        "Studio je vloží do reelu jako video v rámečku.\n"
        "Originál zůstane tam, kde je. Studio si ho jen zkopíruje.\n", encoding="utf-8")
    pripis_do_seznamu(koren, cil.name, nazev, "založeno")
    return cil


def pripis_do_seznamu(koren, slozka, nazev, stav):
    """Jeden řádek na reel v SEZNAM.md. Řádek stejné složky se nahradí, nic jiného se nemění."""
    soubor = Path(koren) / "SEZNAM.md"
    radek = "| %s | %s | %s | %s |" % (slozka, nazev, stav, datetime.now().strftime("%-d. %-m. %Y %H:%M"))
    if soubor.exists():
        radky = soubor.read_text(encoding="utf-8").splitlines()
    else:
        radky = ["# Seznam reelů", "", "| Složka | Název | Stav | Poslední změna |", "|---|---|---|---|"]
    nove, nahrazeno = [], False
    for r in radky:
        if r.startswith("| %s |" % slozka):
            nove.append(radek)
            nahrazeno = True
        else:
            nove.append(r)
    if not nahrazeno:
        nove.append(radek)
    soubor.write_text("\n".join(nove) + "\n", encoding="utf-8")


def je_video(cesta):
    p = Path(cesta)
    return p.is_file() and p.suffix.lower() in VIDEO_PRIPONY and not p.name.startswith(".")


def najdi_videa(slozka):
    """Videa ve složce (bez skrytých souborů a bez zástupných souborů iCloudu), podle názvu."""
    slozka = Path(slozka)
    if not slozka.is_dir():
        return []
    return sorted((p for p in slozka.iterdir() if je_video(p)), key=lambda p: p.name.lower())


def najdi_nahravky(podklady):
    """Nahrávky obrazovky v PODKLADY-SEM/NAHRAVKY-OBRAZOVKY (MP4, MOV), podle názvu. Vrátí cesty."""
    slozka = Path(podklady) / NAHRAVKY
    if not slozka.is_dir():
        return []
    return sorted((p for p in slozka.iterdir() if p.is_file() and not p.name.startswith(".")
                   and p.suffix.lower() in NAHRAVKY_PRIPONY), key=lambda p: p.name.lower())


def zastupne_icloud(slozka):
    """Soubory, které jsou jen v iCloudu (.nazev.icloud) a v počítači nejsou stažené."""
    slozka = Path(slozka)
    if not slozka.is_dir():
        return []
    return sorted(p.name[1:-7] for p in slozka.iterdir() if p.name.startswith(".") and p.name.endswith(".icloud"))


def slozky_reelu(koren):
    """Složky reelů v kořenu Reely (začínají datem)."""
    koren = Path(koren)
    if not koren.is_dir():
        return []
    return sorted(p for p in koren.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}_", p.name))
