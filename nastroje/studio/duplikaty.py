"""Zdvojené věty a znovu začaté věty (krok návrh střihu). Pracuje jen s textem přepisu, nic nestříhá.

Pravidlo z briefu: když je věta řečená dvakrát, zůstane ta poslední. Surová natáčení Marcely (18. 10. 2026,
OVĚŘENO) ukázala, že přepisovač rozdělí stejný text pokaždé jinak, proto se neporovnávají celé věty,
ale slova: kolik slov věty se v pořadí objeví i v některé pozdější větě (nebo dvou po sobě).
  pokrytí >= PRAH_STEJNA: věta se později opakuje (další pokus), navrhuje se vystřihnout.
  pokrytí >= PRAH_PODOBNA: možná totéž jinými slovy, jen se označí, rozhoduje člověk.
Počítají se jen shodné bloky aspoň dvou slov, aby náhodná slova („a“, „je“, „to“) nic nespojila.
Znovu začatá věta uvnitř věty („A co je super? A co je super? Video…“): první pokus se vynechá po slovech.
Prahy jsou NÁVRH, změřené na natáčení Marcely 18. 10. 2026.
"""
import difflib
import re
import unicodedata

from .opravy import OKRAJ

PRAH_STEJNA = 0.55
PRAH_PODOBNA = 0.35
MIN_SLOV = 3
MIN_BLOK = 2
MAX_RESTART = 12


def _norm(w):
    """Malá písmena, bez interpunkce na okrajích a bez diakritiky (přepisovač ji u komolených slov mění)."""
    s = re.sub(r"[%s]" % re.escape(OKRAJ), "", w.lower())
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slova_vety(v):
    return [_norm(w["w"]) for w in v["slova"] if _norm(w["w"])]


def pokryti(a, b, min_blok=MIN_BLOK):
    """Podíl slov věty a, které leží ve shodných blocích (aspoň min_blok slov po sobě) s b. 0 až 1."""
    if not a or not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    shoda = sum(bl.size for bl in sm.get_matching_blocks() if bl.size >= min_blok)
    return shoda / len(a)


def podobnost(a, b):
    """Podobnost dvou seznamů slov 0 až 1 (zachováno pro starší volání)."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def restart_uvnitr_vety(slova_norm, max_delka=MAX_RESTART):
    """Pořadí slov, která jsou první pokus znovu začaté věty uvnitř věty: blok slov se hned za sebou opakuje
    (A co je super A co je super video...). Vrátí seznam pořadí slov k vynechání."""
    ven = set()
    n = len(slova_norm)
    i = 0
    while i < n:
        nalezeno = False
        for d in range(min(max_delka, (n - i) // 2), 1, -1):      # delší blok má přednost
            if slova_norm[i:i + d] == slova_norm[i + d:i + 2 * d]:
                ven.update(range(i, i + d))
                i += d
                nalezeno = True
                break
        if not nalezeno:
            i += 1
    return sorted(ven)


def najdi_opakovani(klipy_vety, prah_stejna=PRAH_STEJNA, prah_podobna=PRAH_PODOBNA):
    """klipy_vety: seznam (po klipech) seznamů vět v pořadí natočení. Vrátí seznam:
    {a, b, klip_a, klip_b, podobnost (pokrytí), druh ('stejna' | 'podobna' | 'znovu_zacata'), nechat, vyhodit}
    a je dřív, b později. U 'stejna' a 'znovu_zacata' je vyhodit = a (zůstává poslední pokus)."""
    vse = []
    for c, vety in enumerate(klipy_vety):
        for i, v in enumerate(vety):
            vse.append((c, i, v, slova_vety(v)))
    out = []
    for x in range(len(vse)):
        ca, ia, va, sa = vse[x]
        if not sa:
            continue
        nej, nej_y = 0.0, None
        for y in range(x + 1, len(vse)):
            cb, ib, vb, sb = vse[y]
            kandidati = [(sb, y)]
            if y + 1 < len(vse) and vse[y + 1][0] == cb:
                # dvě věty po sobě (jiné rozdělení přepisu); přiřadí se té z nich, která sama kryje víc
                dalsi = vse[y + 1][3]
                komu = y if pokryti(sa, sb) >= pokryti(sa, dalsi) else y + 1
                kandidati.append((sb + dalsi, komu))
            if ca == cb and ib == ia + 1 and len(sa) < MIN_SLOV and len(sb) >= len(sa):
                # krátký útržek ("Dneska vám") a hned za ním věta se stejným začátkem
                if sb[:len(sa)] == sa:
                    out.append({"a": va["id"], "b": vb["id"], "klip_a": ca, "klip_b": cb, "podobnost": 1.0,
                                "druh": "znovu_zacata", "nechat": vb["id"], "vyhodit": va["id"]})
                    nej = None
                    break
            for k, komu in kandidati:
                p = pokryti(sa, k) if len(sa) >= MIN_SLOV else (1.0 if " ".join(sa) in " ".join(k) and ca == cb and ib - ia <= 3 else 0.0)
                if p > nej:
                    nej, nej_y = p, komu
        if nej is None or nej_y is None:
            continue
        cb, ib, vb, sb = vse[nej_y]
        if nej >= prah_stejna:
            out.append({"a": va["id"], "b": vb["id"], "klip_a": ca, "klip_b": cb, "podobnost": round(nej, 2),
                        "druh": "stejna", "nechat": vb["id"], "vyhodit": va["id"]})
        elif nej >= prah_podobna and len(sa) >= MIN_SLOV:
            out.append({"a": va["id"], "b": vb["id"], "klip_a": ca, "klip_b": cb, "podobnost": round(nej, 2),
                        "druh": "podobna", "nechat": vb["id"], "vyhodit": None})
    return out


PRAH_POKUSU = 0.6


def cele_pokusy(klipy_vety, dvojice, prah=PRAH_POKUSU):
    """Doplní dvojice o věty, které zůstaly trčet uvnitř prvního pokusu (ve druhém pokusu je mluvčí vynechala).

    Uvnitř klipu: když se před prvním opakováním (nejbližší "později jako" ve stejném klipu) opakuje aspoň prah
    vět, je celý začátek klipu první pokus a vyhodí se i jeho neopakované věty.
    Mezi klipy: když se aspoň prah vět klipu opakuje v pozdějších klipech, je celý klip dřívější pokus.
    Vrátí nové dvojice (druh 'prvni_pokus')."""
    index = {}
    for c, vety in enumerate(klipy_vety):
        for i, v in enumerate(vety):
            index[v["id"]] = (c, i)
    vyhozene = {d["vyhodit"] for d in dvojice if d["vyhodit"]}
    nove = []
    for c, vety in enumerate(klipy_vety):
        ids = [v["id"] for v in vety]
        if len(ids) < 3:
            continue
        # uvnitř klipu
        r_kandidati = [index[d["b"]][1] for d in dvojice if d["vyhodit"] and index[d["a"]][0] == c and index[d["b"]][0] == c]
        if r_kandidati:
            r = min(r_kandidati)
            pred = ids[:r]
            if pred and sum(1 for x in pred if x in vyhozene) / len(pred) >= prah:
                for x in pred:
                    if x not in vyhozene:
                        vyhozene.add(x)
                        nove.append({"a": x, "b": ids[r], "klip_a": c, "klip_b": c, "podobnost": 0.0, "druh": "prvni_pokus",
                                     "nechat": ids[r], "vyhodit": x})
        # celý klip jako dřívější pokus
        pozdeji = [d for d in dvojice if d["vyhodit"] and index[d["a"]][0] == c and index[d["b"]][0] > c]
        if pozdeji and len({d["a"] for d in pozdeji}) / len(ids) >= prah:
            cil = max(pozdeji, key=lambda d: index[d["b"]][0])["b"]
            for x in ids:
                if x not in vyhozene:
                    vyhozene.add(x)
                    nove.append({"a": x, "b": cil, "klip_a": c, "klip_b": index[cil][0], "podobnost": 0.0, "druh": "prvni_pokus",
                                 "nechat": cil, "vyhodit": x})
    return dvojice + nove


def restarty(klipy_vety):
    """Znovu začaté věty uvnitř vět: {id věty: [pořadí slov k vynechání]}."""
    out = {}
    for vety in klipy_vety:
        for v in vety:
            norm = [_norm(w["w"]) for w in v["slova"]]
            ven = restart_uvnitr_vety(norm)
            if ven:
                out[v["id"]] = ven
    return out


def navrh_vyberu(klipy_vety, dvojice):
    """Výchozí výběr: všechny věty v pořadí klipů, bez těch, které se navrhují vyhodit."""
    ven = {d["vyhodit"] for d in dvojice if d["vyhodit"]}
    return [(c, v["id"]) for c, vety in enumerate(klipy_vety) for v in vety if v["id"] not in ven]


def dlouhe_pauzy(klipy_vety, min_pauza=1.5):
    """Mezery mezi větami delší než min_pauza (střih je vystřihne sám, tohle je jen přehled)."""
    out = []
    for c, vety in enumerate(klipy_vety):
        for a, b in zip(vety, vety[1:]):
            d = b["start"] - a["end"]
            if d >= min_pauza:
                out.append({"klip": c, "po_vete": a["id"], "pred_vetou": b["id"], "pauza_s": round(d, 2)})
    return out


def text_navrhu(klipy_vety, dvojice, pauzy, vyber, vynechat=None):
    """Krátký český text pro Clauda a zákaznici: co studio našlo a co navrhuje. Čte se místo celého přepisu."""
    texty = {v["id"]: v["text"] for vety in klipy_vety for v in vety}
    slova = {v["id"]: [w["w"] for w in v["slova"]] for vety in klipy_vety for v in vety}
    radky = []
    stejne = [d for d in dvojice if d["druh"] in ("stejna", "znovu_zacata")]
    podobne = [d for d in dvojice if d["druh"] == "podobna"]
    if not dvojice and not pauzy and not vynechat:
        radky.append("Žádná zdvojená věta ani dlouhá pauza. Navrhuju nechat všechny věty.")
    if stejne:
        radky.append("Věty, které se později opakují (zůstává poslední pokus), vyhazuju: %s." % ", ".join(d["a"] for d in stejne))
        for d in stejne:
            radky.append("   %s: %s  → později jako %s: %s" % (d["a"], texty[d["a"]], d["b"], texty[d["b"]][:90]))
    pokusy = [d for d in dvojice if d["druh"] == "prvni_pokus"]
    if pokusy:
        radky.append("Věty z prvního pokusu, které jsi ve druhém pokusu vynechala, vyhazuju taky (v editoru je můžeš vrátit): %s." %
                     ", ".join(d["a"] for d in pokusy))
        for d in pokusy:
            radky.append("   %s: %s" % (d["a"], texty[d["a"]]))
    for vid, idx in (vynechat or {}).items():
        radky.append("Ve větě %s je znovu začatý úsek, vynechávám první pokus: „%s“." % (vid, " ".join(slova[vid][i] for i in idx)))
    for d in podobne:
        radky.append("Věty %s a %s jsou podobné (%d %%), možná totéž jinými slovy. Nechávám obě, rozhodni." %
                     (d["a"], d["b"], d["podobnost"] * 100))
        radky.append("   %s: %s" % (d["a"], texty[d["a"]]))
        radky.append("   %s: %s" % (d["b"], texty[d["b"]]))
    for p in pauzy:
        radky.append("Pauza %.1f s mezi %s a %s (vystřihne se sama)." % (p["pauza_s"], p["po_vete"], p["pred_vetou"]))
    radky.append("Výběr k náhledu (%d vět): %s" % (len(vyber), ", ".join(v for _, v in vyber)))
    return "\n".join(radky) + "\n"
