"""Plán střihu (krok 8 briefu, kniha střihu část 3): věta po větě, jaký prvek se objeví a proč.

Vstup: věty reelu v pořadí časové osy (text, časy), podklady zákaznice (skript.txt, mikro-nadpisy.txt: řádky
„Moment<tab>TEXT“, řádek „WOW moment: TEXT u věty „…““), seznam obrázků v podkladech.
Výstup: seznam řádků plánu {veta, text, od, do, prvek, obsah, duvod, zdroj} a tabulka v Markdownu pro zákaznici.
Pravidla jsou z dokumenty/KNIHA-STRIHU.md (NÁVRH, dokud je Marcela neschválí). Nic se nevymýšlí: obsah prvků je
jen z vět zákaznice a z jejích nadpisů.
"""
import re
import unicodedata
from pathlib import Path

PRVKY_KARTY = {"hook", "karty_slov", "mini", "mini_silny", "wow", "vyzva"}
MIN_ODSTUP_S = 3.0        # dva prvky s textem ne blíž než 3 s (H5 a rytmus)
MAX_KLID_S = 5.0          # nejvíc 5 s bez změny (H4)


def _cele(w):
    """Slovo malými písmeny bez diakritiky a interpunkce (celé, pro hledání kmene uvnitř slova)."""
    s = re.sub(r"[^\w]", "", w.lower())
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm(w):
    return _cele(w)[:5]


def _slova(text):
    return [_norm(w) for w in text.split() if _norm(w)]


def nacti_mikro_nadpisy(cesta):
    """Z mikro-nadpisy.txt: seznam {moment, text} a WOW moment {text, veta_text} (nebo None)."""
    cesta = Path(cesta)
    out, wow = [], None
    if not cesta.exists():
        return out, wow
    for radek in cesta.read_text(encoding="utf-8").splitlines():
        r = radek.strip()
        if not r:
            continue
        if r.lower().startswith("wow moment"):
            m = re.search(r"wow moment:\s*(.+?)\s+u v[eě]ty\s*[„\"]?(.+?)[“\"]?(?:\s+na\s|\.|$)", r, re.I)
            if m:
                wow = {"text": m.group(1).strip().rstrip("."), "veta_text": m.group(2).strip()}
            continue
        if "\t" in r:
            moment, text = r.split("\t", 1)
        elif "  " in r:
            moment, text = re.split(r"\s{2,}", r, 1)
        else:
            continue
        out.append({"moment": moment.strip(), "text": text.strip()})
    return out, wow


def prirad_nadpisy(vety, nadpisy):
    """Každý nadpis zákaznice k větě podle popisu momentu (překryv slov), 'Úvodní hook' k první větě. Vrátí {id věty: text}."""
    prirazeno = {}
    for n in nadpisy:
        popis = n["moment"].lower()
        if "hook" in popis or "úvod" in popis:
            if vety:
                prirazeno[vety[0]["id"]] = n["text"]
            continue
        klice = [k for k in _slova(popis) if len(k) >= 4 and k not in ("kdyz", "mluvi", "videu", "vysve", "rikas")]
        kmeny = set(klice)      # kontrole ~ zkontroluji ~ kontrola: kmen (5 písmen) kdekoli uvnitř slova
        nej, nej_s = 0, None
        for v in vety:
            if v["id"] in prirazeno:
                continue
            slova_v = _slova(v["text"])
            cela = [_cele(w) for w in v["text"].split()]
            s = len(set(klice) & set(slova_v)) + 0.5 * sum(1 for w in cela if len(w) >= 4 and any(k in w for k in kmeny))
            s += 0.5 * len(set(_slova(n["text"])) & set(slova_v))      # slova nadpisu ve větě (JÁ ROZHODUJU ~ „já zkontroluji“)
            if s > nej:
                nej, nej_s = s, v["id"]
        if nej_s is None:
            # popis nesedí na žádnou větu: nadpisy jdou v pořadí reelu, vezmi další větu za posledním přiřazeným
            ids = [v["id"] for v in vety]
            posledni = max((ids.index(i) for i in prirazeno if i in ids), default=0)
            nej_s = next((v["id"] for v in vety[posledni + 1:] if v["id"] not in prirazeno and len(v["text"].split()) >= 4), None)
        if nej_s:
            prirazeno[nej_s] = n["text"]
    return prirazeno


def najdi_vetu(vety, text):
    """Věta, která se nejvíc kryje s textem (pro WOW moment). Vrátí id nebo None."""
    cil = set(_slova(text))
    nej, nej_id = 0, None
    for v in vety:
        s = len(cil & set(_slova(v["text"])))
        if s > nej:
            nej, nej_id = s, v["id"]
    return nej_id if nej >= 3 else None


def _typ_vety(text, je_prvni, je_posledni):
    t = text.lower()
    if je_prvni:
        return "hook"
    if "komentá" in t or "follow" in t or (je_posledni and ("napiš" in t or "sleduj" in t)):
        return "vyzva"
    if re.search(r"[„\"“][^“”\"]{3,}[“”\"]", text) or re.search(r"\b(řeknu|napíšu|zeptám)\b", t):
        return "zprava"
    if re.search(r"\b(ukážu|ukazuju|vidíš|vidím|složk|přepis|plán|storyboard|kliknu|nahraju|dám mu)", t):
        return "vlozka"
    if re.search(r"\b(nejlepší záběry|celý týden|spousta|skoro u každ|každý reel|všechny)", t):
        return "mrizka"
    if re.search(r"\bžádn[ýáé]\b.*\bžádn[ýáé]\b", t) or re.search(r"\bžádn[ýáé]\b.*\b(nic|jen)\b", t):
        return "nalepky"
    if re.search(r"\d", t) or re.search(r"\b(hodin|minut|za pár|hotovo|ušetří|zpátky)", t):
        return "mini"
    if t.rstrip().endswith("?") and len(t.split()) <= 8:
        return "otazka"
    if re.search(r"\b(nevím skoro|nechtělo se mi|upřímně|nehrnula|nejsem)", t):
        return "priznani"
    if re.match(r"^(a teď|sleduj|a nejlepší|a víš|a co je)", t):
        return "most"
    return "ostatni"


def _preskrtnuta(text):
    """Slova X, Y z věty 'žádný X, žádný Y' (velká písmena uprostřed věty)."""
    out = []
    for m in re.finditer(r"žádn[ýáé]\s+([A-ZÁ-Ž][\w-]*)", text):
        out.append(m.group(1))
    return out


def _uvozovky(text):
    m = re.search(r"[„\"“]([^“”\"]{3,})[“”\"]", text)
    return m.group(1).strip() if m else None


def sestav_plan(vety, nadpisy=None, wow=None, obrazky=None):
    """vety: seznam {id, text, od, do} v pořadí reelu (časy ve výstupu). Vrátí seznam řádků plánu."""
    nadpisy = nadpisy or []
    obrazky = list(obrazky or [])
    prirazeno = prirad_nadpisy(vety, nadpisy)
    wow_veta = najdi_vetu(vety, wow["veta_text"]) if wow else None
    # obrázek pojmenovaný číslem věty („06-editor.png“, „veta-6.jpg“) patří k té větě; ostatní jdou po pořadí
    k_vete = {}
    for o in list(obrazky):
        m = re.match(r"^(?:veta-?)?0*(\d{1,2})\b", Path(o).name.lower())
        if m and 1 <= int(m.group(1)) <= len(vety):
            k_vete.setdefault(int(m.group(1)) - 1, []).append(o)
            obrazky.remove(o)
    radky = []
    posledni_karta_do = -99.0
    for i, v in enumerate(vety):
        typ = _typ_vety(v["text"], i == 0, i == len(vety) - 1)
        prvek, obsah, duvod, zdroj = None, "", "", ""
        if i == 0:
            hook = prirazeno.get(v["id"]) or " ".join(v["text"].split(". ")[0].split()[:10]).rstrip(".,")
            casti = [c.strip() for c in re.split(r"[.!?]", hook) if c.strip()]
            if 1 < len(casti) <= 4 or (len(hook.split()) <= 4):
                prvek, obsah = "karty_slov", " | ".join(casti if len(casti) > 1 else hook.split())
                duvod = "hook jako karty slov (kniha střihu, typ Hook)"
            else:
                prvek, obsah, duvod = "hook", hook, "hook jako karta (víc než 4 slova)"
            zdroj = "nadpis zákaznice" if v["id"] in prirazeno else "první věta"
        elif v["id"] == wow_veta:
            prvek, obsah, duvod, zdroj = "wow", wow["text"], "WOW moment označený zákaznicí", "WOW moment"
        elif typ == "vyzva":
            slovo = next((w.strip(".,!") for w in v["text"].split() if w.strip(".,!").isupper() and len(w) > 2), None)
            prvek, obsah, duvod = "vyzva", v["text"].rstrip("."), "výzva do komentáře" + (", slovo %s" % slovo if slovo else "")
        elif v["id"] in prirazeno:
            prvek, obsah, duvod, zdroj = "mini", prirazeno[v["id"]], "nadpis od zákaznice má přednost", "nadpis zákaznice"
        elif typ == "zprava":
            citace = _uvozovky(v["text"])
            if citace:
                prvek, obsah, duvod = "zprava", citace, "věta „řeknu Claudovi“ s textem v uvozovkách"
            else:
                typ = "ostatni"
        elif i in k_vete:
            prvek, obsah, duvod = "vlozka", k_vete[i][0], "obrázek pojmenovaný číslem věty"
            if v["id"] in prirazeno:
                obsah += " | " + prirazeno[v["id"]]
                duvod += "; nadpis zákaznice jako štítek pod obrázkem"
        elif typ == "vlozka":
            if obrazky:
                prvek, obsah, duvod = "vlozka", obrazky.pop(0), "věta ukazuje věc na obrazovce, screenshot z podkladů"
            else:
                prvek, obsah, duvod = "chybi_obrazek", "", "věta by chtěla screenshot, v podkladech žádný není (záložní: jen přiblížení)"
        elif typ == "mrizka":
            prvek, obsah, duvod = ("mrizka", "obálky reelů z podkladů", "věta o množství: mřížka reelů") if len(obrazky) >= 5 \
                else ("chybi_obrazek", "", "věta o množství by chtěla mřížku (5 obálek reelů), v podkladech nejsou")
        elif typ == "nalepky":
            slova = _preskrtnuta(v["text"])
            prvek, obsah, duvod = "nalepky", ", ".join(slova) if slova else v["text"], "zápor s výčtem: přeškrtnutí"
        elif typ == "mini" and any(r["prvek"] == "mini" and r["zdroj"] == "nadpis zákaznice" and v["od"] - r["do"] < 6 for r in radky[-2:]):
            prvek, obsah, duvod = "zoom", "podle pořadí úrovní", "bez nadpisu: nadpis zákaznice byl před chvílí"
        elif typ == "mini":
            prvek, obsah, duvod = "mini", " ".join(v["text"].rstrip(".").split()[:4]).upper(), "věta s číslem nebo výsledkem (z věty, označit „z věty“)"
            zdroj = "z věty"
        elif typ == "otazka":
            prvek, obsah, duvod = "mini", " ".join(v["text"].split()[:5]), "otázka divákovi"
            zdroj = "z věty"
        elif typ == "priznani":
            prvek, obsah, duvod = "zoom", "přiblížení 1,18", "přiznání: jen přiblížení"
        elif typ == "most":
            prvek, obsah, duvod = "zoom", "oddálení 1,0", "spojka: nádech před dalším prvkem"
        else:
            prvek, obsah, duvod = "zoom", "podle pořadí úrovní", "bez zvláštního prvku"
        # H5: dvě textové karty ne hned za sebou (výjimka hook a WOW)
        if prvek in ("mini", "mini_silny") and v["od"] - posledni_karta_do < MIN_ODSTUP_S and zdroj != "nadpis zákaznice":
            prvek, obsah, duvod = "zoom", "podle pořadí úrovní", "nadpis vynechán: předchozí karta skončila před méně než 3 s"
        if prvek in PRVKY_KARTY or prvek in ("zprava", "vlozka", "mrizka", "nalepky"):
            posledni_karta_do = v["do"]
        radky.append({"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                      "prvek": prvek, "obsah": obsah, "duvod": duvod, "zdroj": zdroj, "typ": typ})
    # H4: víc než 5 s klidu → poznámka (přiblížení se v render řeší samo)
    for r in radky:
        if r["do"] - r["od"] > MAX_KLID_S and r["prvek"] == "zoom":
            r["duvod"] += "; věta delší než 5 s, přiblížení se změní uprostřed"
    return radky


JMENA_PRVKU = {"karty_slov": "karty slov", "hook": "karta hooku", "mini": "mikro-nadpis", "wow": "WOW: velké slovo",
               "vyzva": "karta výzvy", "zprava": "zpráva pro Clauda", "vlozka": "vložka (obrázek)", "mrizka": "mřížka reelů",
               "nalepky": "nálepky / přeškrtnutí", "zoom": "jen přiblížení", "chybi_obrazek": "⚠️ chybí obrázek",
               "velke_slovo": "velké slovo", "karticky": "kartičky s printscreeny", "orbit": "orbit (obálky v prstenu)", "zed": "Instagram zeď (mřížka obálek za osobou)",
               "prulet": "průlet střihem (kamera skrz osobu do dalšího záběru)",
               "stitky": "štítky (pilulky naskakují po sobě)", "zapisnik": "zápisník (fajfka u položky)"}


def tabulka(radky, nazev, bez_vety=None):
    out = ["# Plán obrazovky: %s" % nazev, "",
           "Každý řádek: věta, co se objeví, proč. Změň obsah, smaž řádek, nebo napiš „jo“.", "",
           "| č. | od | věta | prvek | obsah | důvod |", "|---|---|---|---|---|---|"]
    jmena = JMENA_PRVKU
    for i, r in enumerate(radky, 1):
        znacka = ""
        if r.get("zkontrolovat"):
            znacka += "⚠️ %s (dřív: %s). " % (r["zkontrolovat"], r.get("text_drive", "").replace("|", "/"))
        if r.get("navrh"):
            znacka += "⚠️ studio teď navrhuje: %s %s. " % (jmena.get(r["navrh"]["prvek"], r["navrh"]["prvek"]), (r["navrh"]["obsah"] or "").replace("|", "/"))
        if r.get("odmitnuto"):
            znacka += "✋ návrh odmítnutý. "
        elif r.get("rucne"):
            znacka += "✋ ruční úprava. "
        out.append("| %d | %s | %s | %s | %s | %s |" % (i, _cas(r.get("od", 0)), r.get("text", "").replace("|", "/"), jmena.get(r["prvek"], r["prvek"]),
                                                      (r.get("obsah") or "").replace("|", "/"), znacka + r.get("duvod", "")))
    pocty = {}
    for r in radky:
        pocty[r["prvek"]] = pocty.get(r["prvek"], 0) + 1
    if bez_vety:
        out += ["", "## Bez věty (věta už v reelu není, nic se nepřesunulo samo)", ""]
        out += ["- %s: %s (dřív u věty „%s“)" % (jmena.get(r["prvek"], r["prvek"]), (r.get("obsah") or "").replace("|", "/"), r.get("text", "")) for r in bez_vety]
    out += ["", "Prvků: " + ", ".join("%s %d" % (jmena.get(k, k), n) for k, n in pocty.items() if k != "zoom") + "."]
    return "\n".join(out) + "\n"


def _cas(s):
    m, sec = divmod(float(s), 60)
    return "%d:%04.1f" % (m, sec)


# Ochrana ručních úprav (Marcela 29. 10. 2026): nový plán nikdy nepřepíše, co zákaznice změnila nebo odmítla.
PLAN_VERZE = 2
ZAKLADNI_KLICE = {"veta", "text", "od", "do", "prvek", "obsah", "duvod", "zdroj", "typ"}
ZNACKY = {"rucne", "odmitnuto", "navrh", "odmitnuty_navrh", "zkontrolovat", "text_drive", "text_vety"}


def _lisi(a, b):
    """Liší se řádek a od návrhu b obsahem? (prvek, obsah, nebo ruční doplňky jako velikost, slovo, trvání)."""
    if a["prvek"] != b["prvek"] or (a.get("obsah") or "").strip() != (b.get("obsah") or "").strip():
        return True
    return any(k not in ZAKLADNI_KLICE and k not in ZNACKY and a.get(k) != b.get(k) for k in set(a) | set(b))


def _odmitnuty_navrh(o, n):
    """Zákaznice u řádku o už jednou řekla „Nechat moje“ právě tomuhle návrhu n."""
    x = o.get("odmitnuty_navrh") or {}
    return x.get("prvek") == n["prvek"] and (x.get("obsah") or "").strip() == (n.get("obsah") or "").strip()


def _vyznamny(r):
    """Řádek, o který by šlo přijít: něco ukazuje (obrázek, text), ne jen přiblížení."""
    return r["prvek"] not in ("zoom", "chybi_obrazek")


def _stejna_veta(stary_radek, text):
    """Je to pořád stejná věta? S uloženým textem z přepisu (text_vety) se porovná přímo. Starší řádky mají jen
    text bez vystřižených slov: stačí, když jsou jeho slova po pořadí v nové větě a je jich aspoň polovina."""
    b = _slova(text)
    if stary_radek.get("text_vety") is not None:
        return _slova(stary_radek["text_vety"]) == b
    a = _slova(stary_radek["text"])
    it = iter(b)
    return len(a) * 2 >= len(b) and all(w in it for w in a)


def sloucit_plan(stary, novy):
    """Sloučí dosavadní plán (dict ze souboru, nebo None) s novým návrhem (seznam řádků, jeden na větu).

    Chráněný řádek (rucne, odmitnuto) zůstane, jak je. Když návrh pro tu větu říká něco jiného, uloží se vedle
    jako „navrh“ a zákaznice rozhodne. Když se text věty změnil, řádek dostane „zkontrolovat“ a nikam se nepřesune.
    Chráněný řádek věty, která už v reelu není, jde do „bez_vety“. Jedna věta může mít víc řádků (víc prvků).
    Starý plán bez značek (verze 1, často psaný ručně): každý rozdíl proti návrhu je ruční úprava a věta bez řádku
    mohla být smazaná schválně, takže návrh pro ni jen čeká na rozhodnutí. Vrátí (plán, souhrn)."""
    souhrn = {"zachovano": 0, "konflikty": 0, "zkontrolovat": 0, "bez_vety": 0, "nove": 0}
    if not stary or not stary.get("radky"):
        return {"verze": PLAN_VERZE, "radky": list(novy), "bez_vety": []}, souhrn
    stara_verze = stary.get("verze", 1) < PLAN_VERZE
    podle_vety = {}
    for o in stary["radky"]:
        podle_vety.setdefault(o["veta"], []).append(o)
    radky = []
    for n in novy:
        stare = podle_vety.get(n["veta"], [])
        if not stare:
            souhrn["nove"] += 1
            if stara_verze and _vyznamny(n):
                radky.append(dict(n, prvek="zoom", obsah="", duvod="věta neměla řádek, návrh čeká na rozhodnutí", rucne=True,
                                  navrh={"prvek": n["prvek"], "obsah": n["obsah"], "duvod": n["duvod"]}))
                souhrn["konflikty"] += 1
            else:
                radky.append(n)
            continue
        chraneny = any(o.get("rucne") or o.get("odmitnuto") for o in stare)
        if not chraneny and stara_verze and (len(stare) > 1 or _lisi(stare[0], n)):
            chraneny = True
        if not chraneny:
            radky.append(n)
            continue
        shoda = not _vyznamny(n) or any(not _lisi(o, n) or (o.get("odmitnuto") and n["prvek"] == o["odmitnuto"]) or _odmitnuty_navrh(o, n)
                                        for o in stare)
        for j, o in enumerate(stare):
            r = dict(o)
            r.pop("navrh", None)
            if not r.get("odmitnuto"):
                r["rucne"] = True
            r["od"], r["do"] = n["od"], n["do"]          # časy jdou s větou (render bere časy ze slov věty)
            if not _stejna_veta(o, n["text"]):
                r.setdefault("text_drive", o.get("text_vety", o["text"]))
                r["zkontrolovat"] = "věta se změnila"
            r["text"] = n["text"]
            r["text_vety"] = n["text"]
            if r.get("zkontrolovat"):
                souhrn["zkontrolovat"] += 1
            if j == 0 and not shoda:
                r["navrh"] = {"prvek": n["prvek"], "obsah": n["obsah"], "duvod": n["duvod"]}
                souhrn["konflikty"] += 1
            souhrn["zachovano"] += 1
            radky.append(r)
    ve_novem = {n["veta"] for n in novy}
    bez_vety = list(stary.get("bez_vety", []))
    for o in stary["radky"]:
        if o["veta"] in ve_novem:
            continue
        if o.get("rucne") or (stara_verze and _vyznamny(o)):
            bez_vety.append(dict(o, rucne=True, zkontrolovat="věta už v reelu není"))
    souhrn["bez_vety"] = len(bez_vety)
    plan = {k: v for k, v in stary.items() if k not in ("radky", "bez_vety", "verze")}
    plan.update({"verze": PLAN_VERZE, "radky": radky, "bez_vety": bez_vety})
    return plan, souhrn
