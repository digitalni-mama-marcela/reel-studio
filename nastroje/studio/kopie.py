"""Kopie originálního videa do složky reelu. Originál se jen čte, nikdy se nepřesouvá ani nemaže.

Po zkopírování se spočítá otisk (SHA-256) originálu i kopie a musí se shodovat. Když se neshoduje,
kopie se přejmenuje na *.nepovedena-kopie a krok skončí červeně. Nic se nemaže.
Jen standardní knihovna, Python 3.9.
"""
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from . import reel

REZERVA_B = 500 * 1024 ** 2   # kolik místa musí zbýt navíc po kopii


def otisk(cesta, blok=4 * 1024 ** 2):
    h = hashlib.sha256()
    with open(str(cesta), "rb") as f:
        while True:
            data = f.read(blok)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def volne_misto(slozka):
    p = Path(slozka)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(str(p)).free


def zkontroluj_zdroj(zdroj):
    """Vrátí (v pořádku, zpráva, co udělat)."""
    z = Path(zdroj)
    if z.name.startswith(".") and z.name.endswith(".icloud"):
        return False, "Video %s je jen v iCloudu, v počítači není stažené." % z.name[1:-7], \
            "Ve Finderu klikni na mráček u souboru, počkej na stažení a spusť krok znovu."
    if not z.exists():
        return False, "Video %s neexistuje." % z, "Zkontroluj cestu nebo přetáhni soubor do složky PODKLADY-SEM."
    if not z.is_file():
        return False, "%s není soubor." % z, "Vyber soubor s videem (MP4 nebo MOV)."
    if not reel.je_video(z):
        return False, "%s nevypadá jako video (přípona %s)." % (z.name, z.suffix or "žádná"), \
            "Použij MP4 nebo MOV z telefonu."
    if z.stat().st_size == 0:
        return False, "Video %s má velikost 0 B (nejspíš se ještě stahuje z cloudu)." % z.name, \
            "Počkej na stažení a spusť krok znovu."
    return True, "", ""


def cilovy_nazev(cil_slozka, jmeno, otisk_zdroje):
    """Stejné jméno jako originál. Když už tam soubor s tím jménem je a je to jiný soubor, přidá -2, -3."""
    cil = Path(cil_slozka) / jmeno
    n = 2
    while cil.exists():
        if otisk(cil) == otisk_zdroje:
            return cil, True
        cil = Path(cil_slozka) / ("%s-%d%s" % (Path(jmeno).stem, n, Path(jmeno).suffix))
        n += 1
    return cil, False


def zkopiruj(zdroj, cil_slozka, zaznam_soubor=None):
    """Zkopíruje video. Vrátí slovník s výsledkem: ok, cil, zprava, udelej, otisk, velikost, trvalo."""
    zdroj, cil_slozka = Path(zdroj), Path(cil_slozka)
    ok, zprava, udelej = zkontroluj_zdroj(zdroj)
    if not ok:
        return {"ok": False, "zprava": zprava, "udelej": udelej, "zdroj": str(zdroj)}
    velikost = zdroj.stat().st_size
    cil_slozka.mkdir(parents=True, exist_ok=True)
    try:
        if zdroj.resolve().parent == cil_slozka.resolve():
            o = otisk(zdroj)
            vysledek = {"ok": True, "uz_tam_byl": True, "zdroj": str(zdroj), "cil": str(zdroj), "otisk": o,
                        "velikost": velikost, "zprava": "Video %s už je ve složce reelu, nekopíruje se." % zdroj.name}
            _zapis(zaznam_soubor, vysledek)
            return vysledek
    except OSError:
        pass
    volno = volne_misto(cil_slozka)
    if volno < velikost + REZERVA_B:
        return {"ok": False, "zdroj": str(zdroj),
                "zprava": "Na disku je %.1f GB, video má %.1f GB a kopie potřebuje aspoň %.1f GB." %
                          (volno / 1e9, velikost / 1e9, (velikost + REZERVA_B) / 1e9),
                "udelej": "Uvolni místo na disku a spusť krok znovu."}
    zacatek = datetime.now()
    o = otisk(zdroj)
    drive = _uz_zkopirovano(zaznam_soubor, o)
    if drive:
        return {"ok": True, "uz_tam_byl": True, "zdroj": str(zdroj), "cil": drive, "otisk": o, "velikost": velikost,
                "zprava": "Video %s má stejný obsah jako už zkopírované %s, bere se jen jednou." % (zdroj.name, Path(drive).name)}
    cil, stejny = cilovy_nazev(cil_slozka, zdroj.name, o)
    if stejny:
        vysledek = {"ok": True, "uz_tam_byl": True, "zdroj": str(zdroj), "cil": str(cil), "otisk": o, "velikost": velikost,
                    "zprava": "Video %s už bylo zkopírované dřív (stejný obsah), nekopíruje se znovu." % zdroj.name}
        _zapis(zaznam_soubor, vysledek)
        return vysledek
    shutil.copy2(str(zdroj), str(cil))
    o2 = otisk(cil)
    trvalo = (datetime.now() - zacatek).total_seconds()
    if o2 != o:
        spatna = cil.with_name(cil.name + ".nepovedena-kopie")
        cil.rename(spatna)
        return {"ok": False, "zdroj": str(zdroj), "cil": str(spatna),
                "zprava": "Kopie videa %s se neshoduje s originálem (poškozený zápis)." % zdroj.name,
                "udelej": "Zkontroluj disk a spusť krok znovu. Originál je v pořádku, nedotkli jsme se ho."}
    vysledek = {"ok": True, "uz_tam_byl": False, "zdroj": str(zdroj), "cil": str(cil), "otisk": o, "velikost": velikost,
                "trvalo_s": round(trvalo, 1), "kdy": zacatek.isoformat(timespec="seconds"),
                "zprava": "Video %s zkopírováno (%.0f MB za %.0f s), otisk souhlasí. Originál zůstal na místě." %
                          (zdroj.name, velikost / 1e6, trvalo)}
    _zapis(zaznam_soubor, vysledek)
    return vysledek


def _uz_zkopirovano(zaznam_soubor, o):
    """Cesta k dřív zkopírovanému souboru se stejným otiskem (podle kopie.json), jinak None."""
    if not zaznam_soubor or not Path(zaznam_soubor).exists():
        return None
    try:
        for z in json.loads(Path(zaznam_soubor).read_text(encoding="utf-8")):
            if z.get("otisk") == o and z.get("cil") and Path(z["cil"]).exists():
                return z["cil"]
    except (OSError, ValueError):
        pass
    return None


def _zapis(soubor, vysledek):
    """Přidá záznam o kopii do kopie.json (seznam)."""
    if not soubor:
        return
    soubor = Path(soubor)
    soubor.parent.mkdir(parents=True, exist_ok=True)
    seznam = []
    if soubor.exists():
        try:
            seznam = json.loads(soubor.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            seznam = []
    z = {k: v for k, v in vysledek.items() if k != "zprava"}
    if not any(x.get("otisk") == z.get("otisk") and x.get("cil") == z.get("cil") for x in seznam):
        seznam.append(z)
    soubor.write_text(json.dumps(seznam, ensure_ascii=False, indent=1), encoding="utf-8")
