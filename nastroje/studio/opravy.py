"""Opravy slov v přepisu podle seznamu. Čas slov se nemění, jen jejich text.

Seznam je soubor NASTAVENI/opravy-slov-cs.json (v balíčku výchozí, zákaznice do něj přidává
větou "přidej opravu"). Hledá se bez ohledu na velikost písmen a bez interpunkce na okrajích.
Řekne se, co se opravilo, aby šlo zkontrolovat.
"""
import json
import re
from pathlib import Path

OKRAJ = ".,;:!?\"'()[]„“”…-–—"


def nacti_opravy(cesta):
    data = json.loads(Path(cesta).read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in data.get("opravy", {}).items()}


def oprav_slovo(slovo, opravy):
    """Vrátí (nové slovo, opraveno?). Interpunkce na okrajích se zachová."""
    m = re.match(r"^([%s]*)(.*?)([%s]*)$" % (re.escape(OKRAJ), re.escape(OKRAJ)), slovo)
    pred, jadro, po = m.group(1), m.group(2), m.group(3)
    nove = opravy.get(jadro.lower())
    if nove is None:
        return slovo, False
    if jadro[:1].isupper() and nove[:1].islower():
        nove = nove[:1].upper() + nove[1:]
    return pred + nove + po, True


def oprav_vety(vety, opravy):
    """Opraví slova ve větách a přepíše text věty ze slov. Vrátí seznam toho, co se změnilo."""
    zaznam = []
    for v in vety:
        zmena = False
        for s in v["slova"]:
            nove, ok = oprav_slovo(s["w"], opravy)
            if ok:
                zaznam.append({"vet": v["id"], "cas": s["start"], "bylo": s["w"], "je": nove})
                s["w"] = nove
                zmena = True
        if zmena:
            v["text"] = " ".join(s["w"] for s in v["slova"])
    return zaznam


def slij_cisla(vety):
    """Přepisovač občas rozdělí slovo s pomlčkou na dvě ('3' a '-5', 'SPF' a '-ko'). Spojí je zpět, čas se zachová."""
    zmen = 0
    for v in vety:
        nova = []
        for s in v["slova"]:
            if nova and re.match(r"^-\w", s["w"]):
                nova[-1]["w"] += s["w"]
                nova[-1]["end"] = s["end"]
                nova[-1]["p"] = min(nova[-1].get("p", 1), s.get("p", 1))
                zmen += 1
            else:
                nova.append(s)
        v["slova"] = nova
        v["text"] = " ".join(x["w"] for x in nova)
    return zmen
