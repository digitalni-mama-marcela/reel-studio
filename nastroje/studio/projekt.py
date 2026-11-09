"""Jeden reel ve složce: kde co je, nastavení zákaznice, načtení klipů s přepisy, opravami a úpravami z editoru.

Soubory v PRACOVNI (dohoda mezi kroky, Notion 01):
  stav.json             stav každého kroku
  kopie.json            co se zkopírovalo (otisky)
  klipy.json            seznam klipů: originál, soubor k použití (připravená kopie), délka
  klip-<n>/             kontrola-videa.json, video-pripravene.mp4, zvuk16k.wav, prepis.json, prepis-vety.txt, opravy.json
  navrh-strihu.json/.txt  zdvojené věty, pauzy, navržený výběr
  vyber.json            platný výběr vět a vynechaných slov (po úpravách)
  upravy.json           čerstvé úpravy z editoru (po použití se přejmenuje na upravy-pouzite-<čas>.json)
  casova-osa.json       výsledná osa (zdroj pravdy pro MP4 i CapCut)
"""
import json
import os
import time
from pathlib import Path

from . import hlidana_slova, opravy, strih

from .cesty import BALICEK  # noqa: E402


def slozky(reel):
    reel = Path(reel)
    return {"reel": reel, "podklady": reel / "PODKLADY-SEM", "vystup": reel / "VYSTUP", "pracovni": reel / "PRACOVNI",
            "reely": reel.parent}


def _nastaveni_soubor(reel, jmeno):
    """Soubor z NASTAVENI zákaznice (vedle složek reelů), jinak výchozí z balíčku."""
    vlastni = Path(reel).parent / "NASTAVENI" / jmeno
    return vlastni if vlastni.exists() else BALICEK / "NASTAVENI" / jmeno


def nastaveni(reel):
    cesta = _nastaveni_soubor(reel, "nastaveni.json")
    data = json.loads(cesta.read_text(encoding="utf-8"))
    vychozi = json.loads((BALICEK / "NASTAVENI" / "nastaveni.json").read_text(encoding="utf-8"))
    for k, v in vychozi.items():
        data.setdefault(k, v)
    data["_soubor"] = str(cesta)
    data["_opravy"] = str(_nastaveni_soubor(reel, "opravy-slov-cs.json"))
    data["_hlidana"] = str(_nastaveni_soubor(reel, "hlidana-slova-cs.json"))
    return data


def vzhled_upravy(reel):
    """Stálé úpravy vzhledů zákaznice (NASTAVENI/vzhled-upravy.json, co řekla „vždycky“): {vzhled: {část: {klíč: hodnota}}}."""
    cesta = _nastaveni_soubor(reel, "vzhled-upravy.json")
    try:
        return json.loads(cesta.read_text(encoding="utf-8")).get("upravy", {}) or {}
    except (OSError, ValueError):
        return {}


def zapis_vzhled_upravu(reel, vzhled, cast, klic, hodnota, poznamka=None):
    """Zapíše stálou úpravu („vždycky“) do NASTAVENI zákaznice a větu do poznamky-zakaznice.md. Vrátí cestu souboru."""
    slozka = Path(reel).parent / "NASTAVENI"
    slozka.mkdir(exist_ok=True)
    cesta = slozka / "vzhled-upravy.json"
    if cesta.exists():
        data = json.loads(cesta.read_text(encoding="utf-8"))
    else:
        data = json.loads((BALICEK / "NASTAVENI" / "vzhled-upravy.json").read_text(encoding="utf-8"))
    data.setdefault("upravy", {}).setdefault(vzhled, {}).setdefault(cast, {})[klic] = hodnota
    cesta.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if poznamka:
        md = slozka / "poznamky-zakaznice.md"
        if not md.exists():
            md.write_text((BALICEK / "NASTAVENI" / "poznamky-zakaznice.md").read_text(encoding="utf-8"), encoding="utf-8")
        with md.open("a", encoding="utf-8") as f:
            f.write("- %s (%s: %s.%s = %s)\n" % (poznamka, vzhled, cast, klic, json.dumps(hodnota, ensure_ascii=False)))
    return cesta


def seznam_oprav(reel):
    """Opravy slov: výchozí z balíčku plus vlastní zákaznice (její položky mají přednost). Nová výchozí slova
    po aktualizaci studia tak platí i bez přepsání jejího souboru (D18)."""
    vychozi = opravy.nacti_opravy(BALICEK / "NASTAVENI" / "opravy-slov-cs.json")
    vlastni_soubor = Path(nastaveni(reel)["_opravy"])
    if vlastni_soubor.resolve() != (BALICEK / "NASTAVENI" / "opravy-slov-cs.json").resolve():
        vychozi.update(opravy.nacti_opravy(vlastni_soubor))
    return vychozi


def nacti_json(cesta, vychozi=None):
    cesta = Path(cesta)
    if not cesta.exists():
        return vychozi
    return json.loads(cesta.read_text(encoding="utf-8"))


def uloz_json(cesta, data):
    cesta = Path(cesta)
    cesta.parent.mkdir(parents=True, exist_ok=True)
    cesta.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def nazev_reelu(reel):
    stav = nacti_json(Path(reel) / "PRACOVNI" / "stav.json", {})
    return stav.get("nazev") or Path(reel).name


def klipy_seznam(reel):
    return nacti_json(slozky(reel)["pracovni"] / "klipy.json", [])


def nacti_klipy(reel, s_energii=True):
    """Klipy s přepisy po opravách slov a po úpravách textů z editoru. Vrátí seznam pro strih.sestav_osu."""
    s = slozky(reel)
    nast = nastaveni(reel)
    seznam = seznam_oprav(reel)
    vyber = nacti_json(s["pracovni"] / "vyber.json", {})
    out = []
    for k in klipy_seznam(reel):
        slozka = s["pracovni"] / ("klip-%d" % k["n"])
        prepis = nacti_json(slozka / "prepis.json")
        if not prepis:
            continue
        vety = prepis["vety"]
        opravy.oprav_vety(vety, seznam)
        opravy.slij_cisla(vety)
        if s_energii:
            klip = strih.priprav_klip(k["pouzit"], vety, slozka / "zvuk16k.wav", k["delka_s"])
        else:
            klip = {"cesta": k["pouzit"], "vety": vety, "delka": k["delka_s"]}
        klip.update({"n": k["n"], "slozka": str(slozka)})
        out.append(klip)
    if vyber.get("texty"):
        strih.pouzij_texty(out, vyber["texty"])
    return out


def vsechny_vety(klipy):
    return [(c, v["id"]) for c, k in enumerate(klipy) for v in k["vety"]]


def aktualni_vyber(reel, klipy):
    """Platný výběr: vyber.json, jinak návrh střihu, jinak všechny věty. Vrátí (vyber, vynechat, texty)."""
    s = slozky(reel)
    v = nacti_json(s["pracovni"] / "vyber.json")
    if v:
        return [tuple(x) for x in v["vyber"]], v.get("vynechat", {}), v.get("texty", {})
    n = nacti_json(s["pracovni"] / "navrh-strihu.json")
    if n:
        return [tuple(x) for x in n["vyber"]], n.get("vynechat", {}), {}
    return vsechny_vety(klipy), {}, {}


def pouzij_upravy(reel, klipy):
    """Když existuje upravy.json z editoru, zapracuje ho do vyber.json a přejmenuje na upravy-pouzite-<čas>.json.
    Vrátí (vyber, vynechat, texty, úpravy nebo None)."""
    s = slozky(reel)
    vyber, vynechat, texty = aktualni_vyber(reel, klipy)
    u = nacti_json(s["pracovni"] / "upravy.json")
    if not u:
        return vyber, vynechat, texty, None
    # smazaná slova v upraveném textu = vystřihnout z videa, ne jen změnit titulek
    ven_z_textu, u["texty"] = strih.texty_na_vynechani(klipy, u.get("texty", {}))
    for vid, idx in ven_z_textu.items():
        u.setdefault("smazana_slova", {}).setdefault(vid, [])
        u["smazana_slova"][vid] = sorted(set(u["smazana_slova"][vid]) | set(idx))
    vyber, vynechat, nove_texty = strih.vyber_po_upravach(klipy, vyber, vynechat, u)
    texty = dict(texty)
    texty.update(nove_texty)
    uloz_vyber(reel, vyber, vynechat, texty)
    os.replace(str(s["pracovni"] / "upravy.json"), str(s["pracovni"] / ("upravy-pouzite-%d.json" % int(time.time()))))
    return vyber, vynechat, texty, u


def uloz_vyber(reel, vyber, vynechat, texty):
    uloz_json(slozky(reel)["pracovni"] / "vyber.json",
              {"vyber": [[c, v] for c, v in vyber], "vynechat": vynechat, "texty": texty})


def dalsi_cislo(slozka, predpona, pripona):
    """Číslo další verze souboru predpona-<n>.pripona ve složce (1, 2, 3 ...)."""
    slozka = Path(slozka)
    n = 0
    if slozka.exists():
        for p in slozka.glob("%s-*%s" % (predpona, pripona)):
            cast = p.name[len(predpona) + 1:-len(pripona)] if pripona else p.name[len(predpona) + 1:]
            if cast.isdigit():
                n = max(n, int(cast))
    return n + 1


def vzory_hlidanych(reel):
    """Hlídaná slova: výchozí z balíčku plus vlastní zákaznice."""
    vzory = hlidana_slova.nacti_vzory(BALICEK / "NASTAVENI" / "hlidana-slova-cs.json")
    vlastni = Path(nastaveni(reel)["_hlidana"])
    if vlastni.resolve() != (BALICEK / "NASTAVENI" / "hlidana-slova-cs.json").resolve():
        patterns = {v.pattern for v in vzory}
        vzory += [v for v in hlidana_slova.nacti_vzory(vlastni) if v.pattern not in patterns]
    return vzory
