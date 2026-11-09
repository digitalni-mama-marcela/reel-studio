"""Nejistá slova v přepisu: tam, kde se dva přepisovací modely liší, nebo kde si model sám není jistý.

Nic se tu neopravuje. Seznam slouží ke kontrole (člověk, nebo seznam oprav slov), protože správné
znění zná jen mluvčí. Porovnání dvou modelů je levné: druhý model běží asi 20 s na minutu videa.
"""
import difflib
import re

from .opravy import OKRAJ


def _norm(w):
    return re.sub(r"[%s]" % re.escape(OKRAJ), "", w.lower())


def nejista_slova(vety_a, vety_b, prah_jistoty=0.5):
    """Vrátí seznam {veta, cas, slovo, jine, jistota}. A je hlavní přepis, B porovnávací."""
    a = [(v["id"], w) for v in vety_a for w in v["slova"]]
    b = [w for v in vety_b for w in v["slova"]]
    sm = difflib.SequenceMatcher(None, [_norm(w["w"]) for _, w in a], [_norm(w["w"]) for w in b], autojunk=False)
    jine = {}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("replace", "delete"):
            for i in range(i1, i2):
                jine[i] = " ".join(w["w"] for w in b[j1:j2])
    out = []
    for i, (vid, w) in enumerate(a):
        if i in jine or w.get("p", 1) < prah_jistoty:
            out.append({"veta": vid, "cas": w["start"], "slovo": w["w"], "jine": jine.get(i), "jistota": w.get("p")})
    return out
