"""Hlídaná slova v přepisu: vulgární a urážlivá slova, která přepisovač někdy napíše místo neškodného slova
(OVĚŘENO 14. 10. 2026: "pičovat" místo "pečovat"). Nic se neopravuje samo, slovo se jen označí, aby ho
člověk nebo seznam oprav zkontroloval dřív, než se dostane do titulků.

Seznam vzorů je v NASTAVENI/hlidana-slova-cs.json (zákaznice si může přidat vlastní). Jen standardní knihovna.
"""
import json
import re
from pathlib import Path

from .opravy import OKRAJ


def _norm(w):
    return re.sub(r"[%s]" % re.escape(OKRAJ), "", w.lower())


def nacti_vzory(cesta):
    data = json.loads(Path(cesta).read_text(encoding="utf-8"))
    return [re.compile(v) for v in data.get("vzory", [])]


def je_hlidane(slovo, vzory):
    s = _norm(slovo)
    return bool(s) and any(v.search(s) for v in vzory)


def najdi_hlidana(vety, vzory, nejista=None):
    """Vrátí seznam {veta, cas, slovo, jistota, jine}. jine = co napsal druhý model (z nejista.nejista_slova)."""
    jine = {}
    for n in nejista or []:
        jine[(n["veta"], n["cas"])] = n.get("jine")
    out = []
    for v in vety:
        for w in v["slova"]:
            if je_hlidane(w["w"], vzory):
                out.append({"veta": v["id"], "cas": w["start"], "slovo": w["w"], "jistota": w.get("p"),
                            "jine": jine.get((v["id"], w["start"]))})
    return out


def poznamky_k_vetam(hlidana, nejista=None, prah_jistoty=0.6):
    """Poznámka pod větu pro soubor prepis-vety.txt: co zkontrolovat sluchem. Vrátí {id věty: text}."""
    pozn = {}
    for h in hlidana:
        pozn.setdefault(h["veta"], []).append("HLÍDANÉ SLOVO '%s'%s" % (h["slovo"], (" (jinde '%s')" % h["jine"]) if h.get("jine") else ""))
    for n in nejista or []:
        if n["veta"] in pozn and any(n["slovo"] == h["slovo"] for h in hlidana if h["veta"] == n["veta"]):
            continue
        if n.get("jine") or (n.get("jistota") is not None and n["jistota"] < prah_jistoty):
            pozn.setdefault(n["veta"], []).append("nejisté '%s'%s" % (n["slovo"], (" nebo '%s'" % n["jine"]) if n.get("jine") else ""))
    return {k: "; ".join(v) for k, v in pozn.items()}
