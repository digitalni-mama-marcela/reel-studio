"""Podklady k efektům z knihovny stylů: co od zákaznice potřebujeme, kam efekt ve videu patří a jak se sestaví.

Zadání Marcely 23. 11. 2026: „Když si studentka vybere styl a má k němu něco dodat, Claude jí to hned řekne
a podklady si vyžádá. Jinak efekt do videa nedá.“ Dřív 22 karet knihovny plán vůbec neuměl (Tlačítko Sledovat,
Komentář jako na Instagramu, Skládaný nadpis…), a když chyběly podklady, efekt potichu vypadl.

Tok:
  1. krok styl (po uložení výběru v knihovně) vypíše seznam_podkladu(): co je vybrané, co už známe, co chybí.
  2. Claude to zákaznici pošle najednou v jedné zprávě, její odpovědi zapíše krokem podklady
     (`podklady --reel X --nastav "ig_komentar.slovo=STUDIO" --profil-jmeno … --profil-fotka …`).
  3. krok plan přidá vybrané efekty do plánu (pridej_do_planu), vzhled --plan je sestaví (sestav_spec).
  4. vzhled hlídá, že ve videu je všechno vybrané (chybejici_ve_videu); jinak skončí červeně.

Profil (jméno účtu, řádek pod ním, profilová fotka) je společný pro všechny reely: NASTAVENI/profil.json,
fotka se zkopíruje do NASTAVENI. Zeptat se jen jednou.
Podklady reelu: PRACOVNI/zadani-efektu.json {"hodnoty": {klíč: {pole: hodnota}}, "vynechat": [klíč, …]}.
Obsah prvků je jen ze slov a souborů zákaznice, nic se nevymýšlí.
"""
import re
import shutil
import unicodedata
from pathlib import Path

from . import projekt

OBRAZKY = (".png", ".jpg", ".jpeg", ".webp")
VIDEA = (".mp4", ".mov", ".m4v")

# Profil zákaznice (společný pro všechny reely).
PROFIL_POLE = {
    "jmeno": "jméno tvého účtu na Instagramu (bez @)",
    "popis": "krátký řádek pod jménem (třeba „AI tipy pro mámy“)",
    "fotka": "profilovou fotku (dej ji do složky PODKLADY-SEM nebo mi ji sem přetáhni)",
}


def P(klic, otazka, druh="text", povinne=True, **x):
    """Jedno pole podkladu. druh: text | slovo | radky (oddělené |) | soubor | soubory | veta | profil."""
    return dict(x, klic=klic, otazka=otazka, druh=druh, povinne=povinne)


VETA = P("veta", "u které věty to má být (číslo věty nebo kus věty)", "veta", povinne=False)

# Karty knihovny, které staví tenhle modul. kde: hook (první věta, místo karty hooku), vyzva (věta s výzvou
# do komentáře, jinak poslední), konec (poslední věta), veta (podle klíčových slov, jinak volná věta), cely (od začátku).
KARTY = {
    # --- nadpisy (patří na první větu místo karty hooku)
    "skladany_nadpis": {"typ": "skladany_nadpis", "kde": "hook", "pole": [
        P("radky", "úvodní větu rozdělenou na 2 až 4 řádky, oddělené svislou čarou | (třeba: naučíme se | jak nechat Clauda | stříhat reely)",
          "radky", povinne=False, vychozi="hook"),
        P("kurziva", "který řádek má být kurzívou (číslo, výchozí každý druhý)", "text", povinne=False)]},
    "hravy_nadpis": {"typ": "hravy_nadpis", "kde": "hook", "pole": [
        P("text", "nadpis na 1 až 3 slova", "text", povinne=False, vychozi="hook_kratky"),
        P("podpis", "menší řádek pod nadpisem (nepovinné)", "text", povinne=False)]},
    "hravy_nadpis_gesta": {"typ": "hravy_nadpis", "kde": "hook", "pole": [
        P("nadpisy", "2 až 3 nadpisy (každý 1 až 3 slova), oddělené |, v pořadí, jak uděláš gesta", "radky")]},
    # --- výzvy a Instagram
    "ig_komentar": {"typ": "ig_komentar", "kde": "vyzva", "pole": [
        P("slovo", "slovo, které mají lidi napsat do komentáře (musí v reelu zaznít)", "slovo", vychozi="slovo_vyzvy"),
        P("odpoved", "tvoji odpověď na komentář (1 krátká věta)", "text"),
        P("jmeno", PROFIL_POLE["jmeno"], "profil"), P("fotka", PROFIL_POLE["fotka"], "profil")]},
    "ig_sledovat": {"typ": "ig_sledovat", "kde": "konec", "pole": [
        P("jmeno", PROFIL_POLE["jmeno"], "profil"), P("popis", PROFIL_POLE["popis"], "profil"),
        P("fotka", PROFIL_POLE["fotka"], "profil")]},
    "sprej": {"typ": "sprej", "kde": "vyzva", "pole": [
        P("text", "slovo do 10 písmen, které se nastříká (třeba slovo pro komentář)", "slovo", vychozi="slovo_vyzvy"),
        P("podpis", "malý řádek pod ním (třeba „napiš do komentáře“, nepovinné)", "text", povinne=False)]},
    "papir_profil": {"typ": "papirova_karta", "kde": "veta", "pevne": {"druh": "profil", "konec": "strih"}, "pole": [
        P("jmeno", PROFIL_POLE["jmeno"], "profil"), P("popis", PROFIL_POLE["popis"], "profil"),
        P("fotka", PROFIL_POLE["fotka"], "profil"),
        P("cisla", "3 čísla z profilu s popiskem, oddělené | (třeba: 145 příspěvků | 20 tis. sledujících | 300 sledovaných)", "radky"),
        P("veta", "u které věty střihneš nůžkami (číslo věty nebo kus věty)", "veta")]},
    "papir_otazka": {"typ": "papirova_karta", "kde": "veta", "pevne": {"druh": "otazka", "konec": "odfouknuti"}, "pole": [
        P("text", "text otázky na nálepce", "text"),
        P("jmeno", PROFIL_POLE["jmeno"], "profil"), P("fotka", PROFIL_POLE["fotka"], "profil", povinne=False),
        P("veta", "u které věty foukneš fénem nebo mávneš (číslo věty nebo kus věty)", "veta")]},
    "papir_komentare": {"typ": "papirova_karta", "kde": "veta", "pevne": {"druh": "komentar", "konec": "dopad"}, "pole": [
        P("texty", "1 až 3 krátké komentáře, oddělené |", "radky"),
        P("jmeno", PROFIL_POLE["jmeno"], "profil"), P("fotka", PROFIL_POLE["fotka"], "profil", povinne=False), VETA]},
    # --- texty
    "rucni_poznamka": {"typ": "rucni_poznamka", "kde": "veta", "pole": [
        P("text", "poznámku na 1 až 2 krátké řádky (druhý řádek odděl |)", "radky"), VETA]},
    "psany_skrt": {"typ": "psany_skrt", "kde": "veta", "pole": [
        P("text", "řádek, který se napíše a přeškrtne (něco, co v reelu řekneš)", "text"), VETA]},
    "obalka_casopisu": {"typ": "obalka_casopisu", "kde": "veta", "pole": [
        P("nazev", "název časopisu (1 slovo, třeba MÁMA)", "text"),
        P("titulky", "1 až 2 krátké titulky obálky, oddělené | (nepovinné)", "radky", povinne=False), VETA]},
    "pocitadlo": {"typ": "pocitadlo", "kde": "veta", "pole": [
        P("kroky", "dva popisky s časem, oddělené | (třeba: SUROVÝ ZÁZNAM 3:52 | HOTOVÝ REEL 1:15); když nic, "
          "vezmu délku tvého natočeného videa a hotového reelu", "radky", povinne=False), VETA]},
    "karta_vzhledu": {"typ": "karta_vzhledu", "kde": "veta", "klicova": r"značk|barv|písm|vzhled|styl", "pole": [VETA]},
    # --- obrázky a videa
    "roj_karet": {"typ": "roj_karet", "kde": "veta", "klicova": r"klip|natoč|video|záběr|spoust", "pole": [
        P("soubory", "4 až 16 obálek reelů, fotek nebo klipů do složky PODKLADY-SEM (když nic, vezmu snímky z tvého videa)",
          "soubory", povinne=False, min=1, max=16), VETA]},
    "slozka": {"typ": "slozka", "kde": "veta", "klicova": r"složk|klip", "pole": [
        P("soubory", "1 až 4 klipy nebo fotky do složky PODKLADY-SEM (když nic, vezmu snímky z tvého videa)",
          "soubory", povinne=False, min=1, max=4),
        P("nazev", "název složky (výchozí „moje videa“)", "text", povinne=False), VETA]},
    "pas_karet": {"typ": "pas_karet", "kde": "veta", "klicova": r"b-roll|broll|obálk|fotk|záběr", "pole": [
        P("soubory", "2 až 8 obálek, fotek nebo krátkých videí do složky PODKLADY-SEM", "soubory", min=2, max=8), VETA]},
    "ikony": {"typ": "ikony", "kde": "veta", "pole": [
        P("soubory", "2 až 5 obrázků ikon aplikací do složky PODKLADY-SEM (stačí snímek plochy telefonu)", "soubory", min=2, max=5),
        P("popisky", "popisky pod ikony v tom pořadí, oddělené | (třeba: Claude | Notion)", "radky", povinne=False), VETA]},
    "videa_okna": {"typ": "videa_okna", "kde": "veta", "klicova": r"natoč|video|záběr|pokus|surov", "pole": [
        P("stitek", "štítek přes okna (třeba NEPOVEDENÝ ZÁBĚR, nepovinné)", "text", povinne=False), VETA]},
    "plakat": {"typ": "vypinac_plakat", "kde": "veta", "pevne": {"vypinac": False}, "pole": [
        P("soubor", "hotový plakát (obrázek 2:3, třeba z Canvy) do složky PODKLADY-SEM", "soubor"),
        P("slovo", "slovo z reelu, u kterého se plakát rozsvítí", "slovo")]},
    "vypinac_plakat": {"typ": "vypinac_plakat", "kde": "cely", "pevne": {"vypinac": True}, "pole": [
        P("soubor", "hotový plakát (obrázek 2:3, třeba z Canvy) do složky PODKLADY-SEM", "soubor")]},
    # --- střih
    "casova_osa": {"typ": "casova_osa", "kde": "veta", "klicova": r"stř[ií]h|program|aplikac|edit", "pole": [VETA]},
    "storyboard": {"typ": "storyboard", "kde": "veta", "klicova": r"storyboard|plán|scén", "pole": [VETA]},
    "pred_po": {"typ": "pred_po", "kde": "veta", "klicova": r"hotov|před|výsled", "pole": [
        P("veta", "větu, u které se má čára rozjet (třeba „a tady je hotové video“)", "veta", povinne=False)]},
}

# Karty, které plán uměl už dřív. Tady jen co od zákaznice potřebují (kontrola podkladů), staví je planer a vzhled.
DRIVE = {
    "vyzva": [P("slovo", "slovo pro komentář (třeba REEL); musí v reelu zaznít", "slovo", vychozi="slovo_vyzvy")],
    "vlozka": [P("obrazky", "obrázek PNG, JPG nebo WEBP do složky PODKLADY-SEM", "pocet", min=1)],
    "karticky": [P("obrazky", "3 až 5 screenshotů nebo fotek do složky PODKLADY-SEM", "pocet", min=3)],
    "mrizka": [P("obrazky", "5 až 9 obálek reelů (9:16) do složky PODKLADY-SEM", "pocet", min=5)],
    "orbit": [P("obrazky", "4 až 8 obálek reelů (9:16) do složky PODKLADY-SEM", "pocet", min=4)],
    "zed": [P("obrazky", "4 až 12 obálek reelů do složky PODKLADY-SEM", "pocet", min=4)],
    # Marcela 24. 11. 2026: i tyhle karty plán dřív jen „smí navrhnout“ a když je nenavrhl, potichu vypadly
    "zapisnik": [P("polozky", "1 až 6 krátkých bodů do zápisníku, oddělené | (každý se odškrtne, když ho v reelu řekneš, "
                              "tak je piš svými slovy z videa)", "radky"),
                 P("nadpis", "nadpis zápisníku (nepovinné, třeba „Co potřebuješ“)", "text", povinne=False), VETA],
    "karty_slov": [P("slova", "úvodní větu rozdělenou na 2 až 4 kousky, oddělené | (výchozí: tvoje první věta)", "radky",
                     povinne=False, vychozi="hook")],
    "velke_slovo": [P("slovo", "jedno slovo, které v reelu řekneš a má vyskočit přes celou obrazovku", "slovo")],
    "nalepky": [P("slova", "1 až 3 slova, která v reelu řekneš a na obrazovce se přeškrtnou (oddělené čárkou)", "text"), VETA],
    "zprava": [P("text", "zprávu pro Clauda, jak ji v reelu píšeš nebo říkáš (1 až 2 krátké věty)", "text"), VETA],
    "vsuvka": [P("text", "slovo nebo dvě z věty, které mají naskočit na kartičce (barevná část mezi hvězdičkami, třeba *10* minut)", "text"), VETA],
    "casomira": [],      # tikající čas pod nadpisem: nic dodávat nemusí
}
# karty z DRIVE, které dostanou řádek plánu s obsahem z podkladů (karty_slov je nadpis, casomira jen příznak u nadpisu)
DRIVE_TEXTOVE = ("zapisnik", "velke_slovo", "nalepky", "zprava", "vsuvka")
NADPISY = {k for k, d in KARTY.items() if d["kde"] == "hook"}


# ---------------------------------------------------------------------------------------------------------------
# soubory s podklady
# ---------------------------------------------------------------------------------------------------------------

def _soubor_reelu(reel):
    return projekt.slozky(reel)["pracovni"] / "zadani-efektu.json"


def _slozka_nastaveni(reel):
    return Path(reel).parent / "NASTAVENI"


def nacti_profil(reel):
    return projekt.nacti_json(_slozka_nastaveni(reel) / "profil.json", {}) or {}


def nacti(reel):
    d = projekt.nacti_json(_soubor_reelu(reel), {}) or {}
    d.setdefault("hodnoty", {})
    d.setdefault("vynechat", [])
    return d


def uloz(reel, data):
    projekt.uloz_json(_soubor_reelu(reel), data)


def najdi_soubor(reel, nazev):
    """Soubor zákaznice: absolutní cesta, nebo jméno v PODKLADY-SEM (i bez ohledu na velikost písmen). None = není."""
    nazev = str(nazev or "").strip().strip("„“\"'")
    if not nazev:
        return None
    p = Path(nazev).expanduser()
    if p.is_absolute():
        return p if p.exists() else None
    podklady = projekt.slozky(reel)["podklady"]
    if (podklady / nazev).exists():
        return podklady / nazev
    if podklady.exists():
        for x in podklady.rglob("*"):
            if x.name.lower() == nazev.lower():
                return x
    return None


def soubory_podkladu(reel, pripony=OBRAZKY + VIDEA):
    podklady = projekt.slozky(reel)["podklady"]
    if not podklady.exists():
        return []
    return sorted(p for p in podklady.iterdir() if p.is_file() and p.suffix.lower() in pripony and not p.name.startswith("."))


def nastav_profil(reel, jmeno=None, popis=None, fotka=None):
    """Zapíše profil do NASTAVENI/profil.json, fotku zkopíruje do NASTAVENI. Vrátí (profil, chyby)."""
    profil, chyby = nacti_profil(reel), []
    if jmeno is not None:
        profil["jmeno"] = jmeno.strip().lstrip("@")
    if popis is not None:
        profil["popis"] = popis.strip()
    if fotka is not None:
        zdroj = najdi_soubor(reel, fotka)
        if not zdroj or zdroj.suffix.lower() not in OBRAZKY:
            chyby.append("profilovou fotku %s nenacházím (má být obrázek PNG, JPG nebo WEBP v PODKLADY-SEM)." % fotka)
        else:
            cil = _slozka_nastaveni(reel) / ("profilova-fotka" + zdroj.suffix.lower())
            cil.parent.mkdir(parents=True, exist_ok=True)
            for stara in cil.parent.glob("profilova-fotka.*"):
                if stara != zdroj:
                    stara.unlink()          # jen naše vlastní kopie fotky, nikdy soubor zákaznice
            if zdroj.resolve() != cil.resolve():
                shutil.copy2(zdroj, cil)
            profil["fotka"] = str(cil)
    projekt.uloz_json(_slozka_nastaveni(reel) / "profil.json", profil)
    return profil, chyby


def nastav(reel, prirazeni, vynechat=(), vratit=()):
    """prirazeni: ["ig_komentar.slovo=STUDIO", …]. Vrátí (data, chyby)."""
    data, chyby = nacti(reel), []
    for x in prirazeni or []:
        klic, sep, hodnota = str(x).partition("=")
        karta, _, pole = klic.strip().partition(".")
        if not sep or not pole:
            chyby.append("„%s“ nemá tvar efekt.pole=hodnota." % x)
            continue
        definice = KARTY.get(karta, {}).get("pole") or DRIVE.get(karta)
        if not definice or pole not in {p["klic"] for p in definice}:
            chyby.append("efekt %s nemá pole %s." % (karta, pole))
            continue
        druh = next(p["druh"] for p in definice if p["klic"] == pole)
        if druh == "profil":
            nastav_profil(reel, **{pole: hodnota})
            continue
        data["hodnoty"].setdefault(karta, {})[pole] = hodnota.strip()
    for karta in vynechat or []:
        if karta not in data["vynechat"]:
            data["vynechat"].append(karta)
    for karta in vratit or []:
        if karta in data["vynechat"]:
            data["vynechat"].remove(karta)
    uloz(reel, data)
    return data, chyby


# ---------------------------------------------------------------------------------------------------------------
# co je vybrané a co chybí
# ---------------------------------------------------------------------------------------------------------------

def vybrane(styl_reelu):
    """Karty knihovny, které zákaznice v tomhle reelu vybrala a které potřebují podklady nebo stavbu (pořadí výběru)."""
    prvky = styl_reelu.get("prvky") if styl_reelu else None
    if not isinstance(prvky, list):
        return []
    return [p for p in prvky if p in KARTY or p in DRIVE]


def _vety_reelu(reel):
    """Věty reelu v pořadí časové osy: [{id, text, od, do}] (prázdné, když ještě není náhled)."""
    from . import strih
    s = projekt.slozky(reel)
    osa_soubor = s["pracovni"] / "casova-osa.json"
    if not osa_soubor.exists():
        return []
    osa = strih.nacti_osu(osa_soubor)
    texty = {v["id"]: v["text"] for kl in projekt.nacti_klipy(reel, s_energii=False) for v in kl["vety"]}
    slova = {}
    for w in osa["slova"]:
        slova.setdefault(w["veta"], []).append(w)
    out = []
    for u in osa["useky"]:
        for vid in u.get("vety", []):
            if vid in slova and not any(x["id"] == vid for x in out):
                out.append({"id": vid, "text": texty.get(vid, ""), "od": slova[vid][0]["start"], "do": slova[vid][-1]["end"]})
    return out


def slovo_vyzvy(vety):
    """Slovo pro komentář z věty s výzvou: slovo velkými písmeny, jinak slovo za „napiš (mi) (do komentáře)“
    (slovensky „napíš (mi) do komentára“)."""
    from .jazyk import NE_SLOVO, SLOVO_VYZVY
    for v in reversed(vety or []):
        t = v["text"]
        if "komentá" not in t.lower() and not re.search(r"nap[ií]š", t, re.I):
            continue
        velke = [w.strip(".,!?„“\"") for w in t.split() if w.strip(".,!?„“\"").isupper() and len(w.strip(".,!?„“\"")) > 2]
        if velke:
            return velke[0]
        m = SLOVO_VYZVY.search(t)
        if m and m.group(1).lower() not in NE_SLOVO:
            return m.group(1).upper()
    return None


def _vychozi(vychozi, vety, hook_text=None):
    if vychozi == "slovo_vyzvy":
        return slovo_vyzvy(vety)
    if vychozi in ("hook", "hook_kratky"):
        text = hook_text or (vety[0]["text"] if vety else None)
        if text and vychozi == "hook_kratky":
            text = " ".join(re.split(r"[,.!?]", text)[0].split()[:3])
        return text
    return None


def hodnota(reel, karta, pole, data=None, profil=None, vety=None, hook_text=None):
    """Hodnota pole: od zákaznice, z profilu, nebo výchozí z reelu. None = chybí."""
    data = data if data is not None else nacti(reel)
    profil = profil if profil is not None else nacti_profil(reel)
    definice = (KARTY.get(karta, {}).get("pole") or DRIVE.get(karta) or [])
    p = next((x for x in definice if x["klic"] == pole), None)
    if p is None:
        return None
    if p["druh"] == "profil":
        return profil.get(pole) or None
    v = (data["hodnoty"].get(karta) or {}).get(pole)
    if v:
        return v
    return _vychozi(p.get("vychozi"), vety or [], hook_text)


def kontrola(reel, styl_reelu=None):
    """Projde vybrané karty. Vrátí seznam {karta, nazev, chybi: [otázky], mame: [popisy], vynechano}."""
    from . import styl as _styl
    styl_reelu = styl_reelu if styl_reelu is not None else _styl.nacti(reel)
    data, profil, vety = nacti(reel), nacti_profil(reel), _vety_reelu(reel)
    obrazky = soubory_podkladu(reel)
    out = []
    for karta in vybrane(styl_reelu):
        zaznam = {"karta": karta, "nazev": _styl.PRVKY_TEXT.get(karta, karta), "chybi": [], "mame": [],
                  "vynechano": karta in data["vynechat"]}
        definice = KARTY.get(karta, {}).get("pole") or DRIVE.get(karta) or []
        for p in definice:
            if p["druh"] == "pocet":
                if len(obrazky) < p.get("min", 1):
                    zaznam["chybi"].append(p["otazka"] + " (teď jich tam je %d)" % len(obrazky))
                else:
                    zaznam["mame"].append("obrázky v PODKLADY-SEM: %d" % len(obrazky))
                continue
            v = hodnota(reel, karta, p["klic"], data, profil, vety)
            if p["druh"] in ("soubor", "soubory") and v:
                nalezene = _soubory(reel, v)
                if p["druh"] == "soubor" and not nalezene:
                    zaznam["chybi"].append(p["otazka"] + " (soubor %s ve složce nevidím)" % v)
                    continue
                if p["druh"] == "soubory" and len(nalezene) < p.get("min", 1):
                    zaznam["chybi"].append(p["otazka"] + " (našla jsem %d)" % len(nalezene))
                    continue
            if p["druh"] == "profil" and p["klic"] == "fotka" and v and not Path(v).exists():
                v = None
            if v:
                zaznam["mame"].append("%s: %s" % (p["klic"], Path(v).name if p["klic"] == "fotka" else v))
            elif p["povinne"]:
                zaznam["chybi"].append(p["otazka"])
        out.append(zaznam)
    return out


def seznam_podkladu(reel, styl_reelu=None):
    """Text pro Clauda: co zákaznici říct a na co se zeptat. Vrátí (řádky, počet karet s chybějícími podklady)."""
    zaznamy = kontrola(reel, styl_reelu)
    if not zaznamy:
        return [], 0
    radky, chybi = [], 0
    for z in zaznamy:
        if z["vynechano"]:
            radky.append("   – %s: vynechat (řekla zákaznice)" % z["nazev"])
        elif z["chybi"]:
            chybi += 1
            radky.append("   ❌ %s: potřebuju %s" % (z["nazev"], "; ".join(z["chybi"])))
        else:
            radky.append("   ✅ %s: mám všechno%s" % (z["nazev"], (" (" + ", ".join(z["mame"]) + ")") if z["mame"] else ""))
    return radky, chybi


# ---------------------------------------------------------------------------------------------------------------
# plán: kam efekt patří
# ---------------------------------------------------------------------------------------------------------------

def _bez_diakritiky(t):
    return "".join(c for c in unicodedata.normalize("NFKD", str(t).lower()) if not unicodedata.combining(c))


def najdi_vetu(vety, udaj):
    """Věta podle čísla (1 = první věta reelu) nebo kusu textu. Vrátí index nebo None."""
    udaj = str(udaj or "").strip().strip("„“\"'")
    if not udaj:
        return None
    if udaj.isdigit():
        i = int(udaj) - 1
        return i if 0 <= i < len(vety) else None
    for i, v in enumerate(vety):
        if v["id"] == udaj:
            return i
    cil = set(w for w in re.findall(r"\w+", _bez_diakritiky(udaj)) if len(w) > 2)
    nej, nej_i = 0, None
    for i, v in enumerate(vety):
        s = len(cil & set(re.findall(r"\w+", _bez_diakritiky(v["text"]))))
        if s > nej:
            nej, nej_i = s, i
    return nej_i if nej and nej >= max(1, len(cil) // 2) else None


def _veta_vyzvy(vety):
    for i in range(len(vety) - 1, -1, -1):
        t = vety[i]["text"].lower()
        if "komentá" in t or re.search(r"nap[ií]š", t) or "sleduj" in t or "follow" in t:
            return i
    return len(vety) - 1 if vety else None


def _veta_slova(vety, slovo):
    s = _bez_diakritiky(slovo).strip(".,!?")
    for i, v in enumerate(vety):
        if any(_bez_diakritiky(w).strip(".,!?„“\"") == s for w in v["text"].split()):
            return i
    return None


def misto(karta, vety, radky, data, profil=None):
    """Index věty, kam karta patří (podle zadání, klíčových slov, nebo první volné věty). None = nikam."""
    d = KARTY[karta]
    zadana = (data["hodnoty"].get(karta) or {}).get("veta")
    if zadana:
        i = najdi_vetu(vety, zadana)
        if i is not None:
            return i
    if not vety:
        return None
    if d["kde"] in ("hook", "cely"):
        return 0
    if d["kde"] == "konec":
        return len(vety) - 1
    if d["kde"] == "vyzva":
        return _veta_vyzvy(vety)
    if karta == "plakat":
        slovo = (data["hodnoty"].get(karta) or {}).get("slovo")
        i = _veta_slova(vety, slovo) if slovo else None
        if i is not None:
            return i
    if karta == "psany_skrt":
        i = najdi_vetu(vety, (data["hodnoty"].get(karta) or {}).get("text"))
        if i is not None:
            return i
    return misto_volne(vety, radky, d.get("klicova"))


def _pridej_drive(reel, radky, styl_reelu, vety, data, hlasky):
    """Karty, které plán uměl už dřív, ale sám je nenavrhne (orbit, zeď, kartičky, mřížka, obrázek, výzva):
    když je zákaznice vybrala a v plánu nejsou, přidá je k vhodné větě."""
    obrazky = [p.name for p in soubory_podkladu(reel, OBRAZKY)]
    for karta in vybrane(styl_reelu):
        if karta not in DRIVE or karta in data["vynechat"]:
            continue
        if karta in DRIVE_TEXTOVE or karta == "karty_slov":
            _pridej_textovou(reel, radky, styl_reelu, vety, data, hlasky, karta)
            continue
        if karta == "casomira" or any(r["prvek"] == karta for r in radky):
            continue
        if karta == "vyzva":
            i, obsah = _veta_vyzvy(vety), None
            obsah = vety[i]["text"].rstrip(".") if i is not None else ""
            slovo = (data["hodnoty"].get("vyzva") or {}).get("slovo") or slovo_vyzvy(vety)
            if slovo and obsah:
                # slovo pro komentář velkými písmeny: karta výzvy ho zvýrazní
                obsah = re.sub(r"(?i)(?<!\w)%s(?!\w)" % re.escape(slovo), slovo.upper(), obsah)
        elif karta == "orbit":
            i, obsah = 0, "*"
        elif karta == "zed":
            i, obsah = misto_volne(vety, radky, r"instagram|profil|reel|sleduj"), "*"
        elif karta == "mrizka":
            i, obsah = misto_volne(vety, radky, r"reel|všechn|spoust|týden"), "obálky reelů z podkladů"
        elif karta == "karticky":
            i, obsah = misto_volne(vety, radky, r"ukáž|ukazuj|vidíš|screenshot|aplikac"), " | ".join(obrazky[:5])
        else:   # vlozka
            i, obsah = misto_volne(vety, radky, r"ukáž|ukazuj|vidíš|tady|obrazovk"), (obrazky[0] if obrazky else "")
        if i is None or (karta in ("karticky", "vlozka") and not obsah):
            continue
        v = vety[i]
        if karta == "vyzva":
            for r in [r for r in radky if r["veta"] == v["id"] and r["prvek"] in ("zoom", "mini")]:
                radky.remove(r)
        poz = max((j for j, r in enumerate(radky) if r["veta"] == v["id"]), default=len(radky) - 1) + 1
        radky.insert(poz, {"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                           "prvek": karta, "obsah": obsah, "duvod": "efekt ze stylu, u věty %d" % (i + 1), "zdroj": "styl", "typ": "styl"})
        hlasky.append("Efekt %s jde k větě %d („%s“)." % (karta, i + 1, v["text"][:60]))


KLICOVA_TEXTOVYCH = {"zapisnik": r"krok|tip|potřeb|seznam|za prvé|první|druh|třetí",
                     "nalepky": r"nechci|nemusíš|bez |žádn|zapomeň|už ne",
                     "zprava": r"claud|napíš|napsal|řekn|prompt|zadá|chat",
                     "vsuvka": None}


def _pridej_textovou(reel, radky, styl_reelu, vety, data, hlasky, karta):
    """Karty, které potřebují text od zákaznice (zápisník, nálepky, zpráva, obří slovo, vsuvka, karty slov):
    řádek plánu s obsahem z podkladů. Řádek, který navrhl plán sám, dostane slova zákaznice (ruční se nemění)."""
    h = data["hodnoty"].get(karta) or {}
    zadana = najdi_vetu(vety, h.get("veta")) if h.get("veta") else None
    if karta == "karty_slov":
        # nadpis z karet slov: jen když nadpis neurčuje jiná karta (skládaný, hravý)
        if any(k in NADPISY for k in vybrane(styl_reelu) if k not in data["vynechat"]):
            hlasky.append("⚠️ Vybrané jsou karty slov i jiný nadpis, karty slov vynechávám.")
            return
        v = vety[0]
        slova = h.get("slova")
        hook_radek = next((r for r in radky if r["veta"] == v["id"] and r["prvek"] in ("hook", "karty_slov", "zoom")), None)
        if hook_radek and hook_radek["prvek"] == "karty_slov" and (hook_radek.get("zdroj") == "rucne" or not slova):
            return
        text = slova or (hook_radek.get("obsah", "") if hook_radek and hook_radek["prvek"] == "hook" else "") or v["text"]
        obsah = text if "|" in text else " | ".join(re.split(r"[,.!?]", text)[0].split()[:4])
        if hook_radek:
            radky.remove(hook_radek)
        radky.insert(0, {"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                         "prvek": "karty_slov", "obsah": obsah, "duvod": "nadpis ze stylu (karty slov)", "zdroj": "styl", "typ": "hook"})
        hlasky.append("Nadpis jako karty slov: %s." % obsah)
        return
    if karta == "zapisnik":
        polozky = _radky(h.get("polozky"))
        obsah = ((h.get("nadpis").strip() + ": ") if h.get("nadpis") else "") + " | ".join(polozky) if polozky else ""
        i = zadana if zadana is not None else najdi_vetu(vety, polozky[0]) if polozky else None
    elif karta == "velke_slovo":
        obsah = (h.get("slovo") or "").strip().strip(".,!?„“\"")
        i = zadana if zadana is not None else (_veta_slova(vety, obsah) if obsah else None)
        if obsah and i is None:
            hlasky.append("⚠️ Obří slovo „%s“ v reelu nezazní. Zeptej se zákaznice na slovo, které opravdu řekne." % obsah)
            return
    else:
        obsah = (h.get("slova") if karta == "nalepky" else h.get("text")) or ""
        i = zadana if zadana is not None else (najdi_vetu(vety, obsah) if obsah and karta != "zprava" else None)
    if not obsah:
        return                          # chybí podklady: kontrola to zákaznici řekne, pojistka video nepustí
    existujici = [r for r in radky if r["prvek"] == karta]
    if existujici:
        for r in existujici:
            if r.get("zdroj") != "rucne":
                r["obsah"] = obsah
        return
    if i is None:
        i = misto_volne(vety, radky, KLICOVA_TEXTOVYCH.get(karta))
    if i is None:
        return
    v = vety[i]
    poz = max((j for j, r in enumerate(radky) if r["veta"] == v["id"]), default=len(radky) - 1) + 1
    radky.insert(poz, {"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                       "prvek": karta, "obsah": obsah, "duvod": "efekt ze stylu, u věty %d" % (i + 1), "zdroj": "styl", "typ": "styl"})
    hlasky.append("Efekt %s jde k větě %d („%s“)." % (karta, i + 1, v["text"][:60]))



def misto_volne(vety, radky, klicova=None):
    """Věta podle klíčových slov (uprostřed reelu), jinak první volná věta uprostřed."""
    if not vety:
        return None
    stred = list(enumerate(vety))[1:-1] or list(enumerate(vety))
    if klicova:
        for i, v in stred:
            if re.search(klicova, v["text"].lower()):
                return i
    # věta s nejmenším počtem prvků (víc efektů než vět: rozloží se rovnoměrně, ne všechny na jednu větu)
    pocet = {}
    for r in radky:
        if r["prvek"] not in ("zoom", "chybi_obrazek"):
            pocet[r["veta"]] = pocet.get(r["veta"], 0) + 1
    return min(stred, key=lambda iv: (pocet.get(iv[1]["id"], 0), iv[0]))[0]


def pridej_do_planu(reel, radky, styl_reelu, vety):
    """Přidá vybrané karty do řádků plánu (úprava na místě). Vrátí hlášky pro Clauda."""
    hlasky = []
    data, profil = nacti(reel), nacti_profil(reel)
    karty = [k for k in vybrane(styl_reelu) if k in KARTY and k not in data["vynechat"]]
    if not vety:
        return hlasky
    _pridej_drive(reel, radky, styl_reelu, vety, data, hlasky)
    # nadpis: první vybraný nadpis nahradí kartu hooku / karty slov u první věty
    nadpis = next((k for k in karty if k in NADPISY), None)
    for karta in karty:
        if karta in NADPISY and karta != nadpis:
            hlasky.append("⚠️ Vybrané jsou dva nadpisy, použiju %s; %s vynechávám." % (KARTY[nadpis]["typ"], karta))
            continue
        if any(r["prvek"] == karta for r in radky):
            continue                    # už v plánu je (třeba ručně přesunutý k jiné větě)
        i = misto(karta, vety, radky, data, profil)
        if i is None:
            hlasky.append("⚠️ %s: nenašla jsem větu, kam patří. Zeptej se zákaznice, u které věty to chce." % karta)
            continue
        v = vety[i]
        if KARTY[karta]["kde"] == "hook":
            hook_radek = next((r for r in radky if r["veta"] == v["id"] and r["prvek"] in ("hook", "karty_slov", "zoom")), None)
            text = hook_radek.get("obsah", "").replace(" | ", " ") if hook_radek and hook_radek["prvek"] != "zoom" else ""
            if hook_radek:
                radky.remove(hook_radek)
            radky.insert(0, {"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                             "prvek": karta, "obsah": text, "duvod": "nadpis ze stylu (%s)" % karta, "zdroj": "styl", "typ": "hook"})
            continue
        if any(r["veta"] == v["id"] and r["prvek"] == karta for r in radky):
            continue
        poz = max((j for j, r in enumerate(radky) if r["veta"] == v["id"]), default=len(radky) - 1) + 1
        radky.insert(poz, {"veta": v["id"], "text": v["text"], "text_vety": v["text"], "od": round(v["od"], 2), "do": round(v["do"], 2),
                           "prvek": karta, "obsah": "", "duvod": "efekt ze stylu, u věty %d" % (i + 1), "zdroj": "styl", "typ": "styl"})
        hlasky.append("Efekt %s jde k větě %d („%s“)." % (karta, i + 1, v["text"][:60]))
    return hlasky


# ---------------------------------------------------------------------------------------------------------------
# vzhled: sestavení specifikace prvku z řádku plánu
# ---------------------------------------------------------------------------------------------------------------

def _soubory(reel, hodnota_):
    """„a.jpg | b.png“, „a.jpg, b.png“ nebo „*“ (všechno v PODKLADY-SEM). Vrátí seznam existujících cest."""
    if not hodnota_:
        return []
    if str(hodnota_).strip() == "*":
        return [str(p) for p in soubory_podkladu(reel)]
    out = []
    for kus in re.split(r"\s*[|,;]\s*", str(hodnota_)):
        p = najdi_soubor(reel, kus)
        if p:
            out.append(str(p))
    return out


def _radky(t):
    return [x.strip() for x in re.split(r"\s*\|\s*|\n", str(t or "")) if x.strip()]


def _cas_textem(s):
    s = max(0, int(round(s)))
    return "%d:%02d" % (s // 60, s % 60)


def _snimky_z_videa(reel, pocet, kontext):
    """Snímky z natočených klipů zákaznice (místní ffmpeg, jen čtení originálu). Vrátí cesty k JPG v PRACOVNI."""
    import subprocess
    pracovni = projekt.slozky(reel)["pracovni"] / "efekty"
    pracovni.mkdir(parents=True, exist_ok=True)
    klipy = kontext.get("klipy") or []
    out = []
    for i in range(pocet):
        if not klipy:
            break
        kl = klipy[i % len(klipy)]
        delka = float(kl.get("delka") or 10)
        cas = max(0.2, delka * ((i // len(klipy)) + 1) / (pocet // len(klipy) + 2))
        cil = pracovni / ("snimek-%d-%02d.jpg" % (kl.get("n", 0), i))
        if not cil.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", "%.2f" % cas, "-i", str(kl["cesta"]),
                            "-frames:v", "1", "-vf", "scale=360:-2", str(cil)], check=False)
        if cil.exists():
            out.append(str(cil))
    return out


def _vlna(kontext, hodnot=120):
    """Hlasitost řeči 0..1 z prvního klipu (zvuk16k.wav), jinak rovná čára."""
    import wave
    import numpy as np
    for kl in kontext.get("klipy") or []:
        wav = Path(kl.get("slozka") or "") / "zvuk16k.wav"
        if not wav.exists():
            continue
        try:
            with wave.open(str(wav)) as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
        except (OSError, wave.Error):
            continue
        if data.size < hodnot:
            continue
        kusy = np.array_split(np.abs(data), hodnot)
        h = np.array([k.mean() for k in kusy])
        return [round(float(x), 3) for x in (h / (h.max() or 1.0))]
    return [0.4] * hodnot


# prvky, které podle zadání Marcely jdou za osobu (maska), i když modul nemá ZA_HLAVOU (kontrola je pak neposuzuje proti obličeji)
SCHOVAT_TITULKY = {"ig_sledovat", "sprej", "papir_profil", "papir_otazka", "papir_komentare"}
ZA_OSOBU = {"obalka_casopisu", "casova_osa", "storyboard", "pocitadlo", "psany_skrt", "videa_okna"}


def sestav_spec(reel, karta, rad, od_v, do_v, kontext):
    """Sestaví spec (viz _sestav_spec) a prvkům za osobou doplní za_hlavou."""
    spec, duvod = _sestav_spec(reel, karta, rad, od_v, do_v, kontext)
    for s in (spec if isinstance(spec, list) else [spec] if spec else []):
        if karta in SCHOVAT_TITULKY:
            s.setdefault("skryt_titulky", True)      # karta na hrudi: titulky by byly pod ní (23. 11. 2026)
        if s["typ"] in ZA_OSOBU:
            s.setdefault("za_hlavou", True)
            s.setdefault("vzdy_za_hlavou", True)
    return spec, duvod


def _sestav_spec(reel, karta, rad, od_v, do_v, kontext):
    """Spec prvku pro osa["prvky"] (nebo seznam specs) z řádku plánu. kontext: {vety, delka_reelu, delka_videa,
    klipy, hook_text, slova_vety, vsechna_slova, styl_vzhledu, radky}. Vrátí (spec | [spec] | None, důvod když None)."""
    d = KARTY[karta]
    data, profil = nacti(reel), nacti_profil(reel)
    vety = kontext.get("vety") or []

    def h(pole):
        return hodnota(reel, karta, pole, data, profil, vety, kontext.get("hook_text"))

    delka = float(kontext.get("delka_reelu") or do_v + 3)
    spec = dict(d.get("pevne", {}), typ=d["typ"], od=round(max(0.1, od_v), 2), do=round(min(delka, max(do_v + 0.5, od_v + 2.8)), 2))
    hook = (rad.get("obsah") or kontext.get("hook_text") or (vety[0]["text"] if vety else "")).replace(" | ", " ").strip()

    if karta == "skladany_nadpis":
        casti = _radky(h("radky")) if (data["hodnoty"].get(karta) or {}).get("radky") else []
        if not casti:
            casti = [c.strip() for c in re.split(r"[,.!?]+", hook) if c.strip()]
            if len(casti) < 2:
                slova = hook.split()
                n = 3 if len(slova) >= 6 else 2
                krok = max(1, -(-len(slova) // n))
                casti = [" ".join(slova[j:j + krok]) for j in range(0, len(slova), krok)]
        casti = casti[:4]
        if not casti:
            return None, "chybí text nadpisu"
        kurz = (data["hodnoty"].get(karta) or {}).get("kurziva")
        krok_s = max(0.5, (do_v - od_v) / max(1, len(casti)))
        spec["radky"] = [dict({"text": c, "cas": round(spec["od"] + j * krok_s, 2)},
                              **({"kurziva": str(j + 1) == str(kurz).strip()} if kurz else {})) for j, c in enumerate(casti)]
        spec["do"] = round(min(delka, max(do_v + 0.6, spec["od"] + 0.6 * len(casti) + 1.2)), 2)
        return spec, None
    if karta == "hravy_nadpis":
        text = (data["hodnoty"].get(karta) or {}).get("text") or " ".join(hook.split()[:3])
        if not text:
            return None, "chybí text nadpisu"
        spec.update({"text": text, "nastup": "psani", "za_hlavou": True, "od": 0.1})
        if h("podpis"):
            spec["podpis"] = h("podpis")
        return spec, None
    if karta == "hravy_nadpis_gesta":
        nadpisy = _radky(h("nadpisy"))[:3]
        if not nadpisy:
            return None, "chybí nadpisy"
        krok_s = max(1.2, (do_v - 0.1) / len(nadpisy))
        return [{"typ": "hravy_nadpis", "od": round(0.1 + j * krok_s, 2), "do": round(min(delka, 0.1 + (j + 1) * krok_s), 2),
                 "text": t, "nastup": "psani", "za_hlavou": True} for j, t in enumerate(nadpisy)], None
    if karta == "ig_komentar":
        slovo, odpoved, jmeno = h("slovo"), h("odpoved"), h("jmeno")
        if not (slovo and odpoved and jmeno):
            return None, "chybí slovo pro komentář, odpověď nebo jméno účtu"
        from . import jazyk as _jazyk, projekt as _projekt
        spec.update({"vyzva": "%s\n%s" % (_jazyk.text("napis_do_komentare", _projekt.jazyk_reelu(reel)), slovo.upper()), "slovo": slovo.upper(), "kdo": "tvuj_ucet",
                     "autorka": jmeno, "odpoved": odpoved, "fotka": h("fotka") or ""})
        spec["do"] = round(min(delka, max(do_v + 0.5, od_v + 3.3)), 2)
        return spec, None
    if karta == "ig_sledovat":
        jmeno = h("jmeno")
        if not jmeno:
            return None, "chybí jméno účtu"
        od = max(0.1, min(od_v, delka - 3.3))
        spec.update({"od": round(od, 2), "do": round(min(delka, od + 3.3), 2), "jmeno": jmeno, "popis": h("popis") or "",
                     "fotka": h("fotka") or "", "tuk": 1.3})
        return spec, None
    if karta == "sprej":
        text = (h("text") or "").upper()[:10]
        if not text:
            return None, "chybí slovo"
        spec["text"] = text
        if h("podpis"):
            spec["podpis"] = h("podpis")
        return spec, None
    if karta == "papir_profil":
        jmeno = h("jmeno")
        cisla = [re.match(r"^\s*(\S+)\s*(.*)$", c).groups() for c in _radky(h("cisla"))][:3]
        if not jmeno or len(cisla) < 3:
            return None, "chybí jméno účtu nebo 3 čísla z profilu"
        spec.update({"jmeno": jmeno, "popis": h("popis") or "", "cisla": [list(c) for c in cisla], "foto": h("fotka") or ""})
        return spec, None
    if karta == "papir_otazka":
        if not h("text"):
            return None, "chybí text otázky"
        spec["text"] = h("text")
        spec.update({"jmeno": h("jmeno") or "", "foto": h("fotka") or ""})
        return spec, None
    if karta == "papir_komentare":
        texty = _radky(h("texty"))[:3]
        if not texty:
            return None, "chybí komentáře"
        spec.update({"texty": texty, "casy": [round(spec["od"] + 0.4 * j, 2) for j in range(len(texty))],
                     "jmeno": h("jmeno") or "", "foto": h("fotka") or ""})
        spec["do"] = round(min(delka, max(spec["do"], od_v + 1.0 + 0.4 * len(texty) + 1.5)), 2)
        return spec, None
    if karta == "rucni_poznamka":
        r_ = _radky(h("text"))[:2]
        if not r_:
            return None, "chybí text poznámky"
        spec.update({"text": "\n".join(r_), "sipka": "vpravo"})
        return spec, None
    if karta == "psany_skrt":
        if not h("text"):
            return None, "chybí řádek textu"
        spec["text"] = h("text")
        return spec, None
    if karta == "obalka_casopisu":
        if not h("nazev"):
            return None, "chybí název časopisu"
        t = _radky(h("titulky"))
        spec.update({"nazev": h("nazev").upper()})
        if t:
            spec["titulek"] = "\n".join(t[:2])
        spec["do"] = round(min(delka, max(spec["do"], od_v + 3.0)), 2)
        return spec, None
    if karta == "pocitadlo":
        kroky = []
        for kus in _radky(h("kroky"))[:2]:
            m = re.match(r"^(.*?)\s*(\d{1,2}:\d{2})\s*$", kus)
            if m:
                kroky.append((m.group(1).strip().upper() or "ČAS", m.group(2)))
        if len(kroky) < 2:
            kroky = [("SUROVÝ ZÁZNAM", _cas_textem(kontext.get("delka_videa") or delka)), ("HOTOVÝ REEL", _cas_textem(delka))]
        spec["do"] = round(min(delka, max(do_v + 0.4, od_v + 2.6)), 2)
        pul = round(spec["od"] + (spec["do"] - spec["od"]) * 0.6, 2)
        spec["kroky"] = [{"cas": spec["od"], "popisek": kroky[0][0], "hodnota": kroky[0][1]},
                         {"cas": pul, "popisek": kroky[1][0], "hodnota": kroky[1][1]}]
        return spec, None
    if karta == "karta_vzhledu":
        sv = kontext.get("styl_vzhledu") or {}
        pismo = (sv.get("hook") or {}).get("pismo") or "PlayfairDisplay-wght.ttf"
        barvy = []
        for cast in ("hook", "mini", "titulky", "vsuvka"):
            for kl in ("barva", "marker", "barva_zvyrazneni", "podklad"):
                b = (sv.get(cast) or {}).get(kl)
                if isinstance(b, (list, tuple)) and len(b) >= 3:
                    hx = "#%02X%02X%02X" % tuple(int(x) for x in b[:3])
                    if hx not in barvy:
                        barvy.append(hx)
        barvy = (barvy + ["#FFFFFF", "#1F2A44", "#E9C46A", "#F4A261", "#2A9D8F"])[:5]
        spec.update({"nadpis": "tvůj vzhled", "podpis": "na míru tobě", "meritko": 1.3, "varianty": [
            {"cas": spec["od"], "pismo": pismo, "nazev": Path(pismo).stem.split("-")[0], "barvy": barvy}]})
        return spec, None
    if karta in ("roj_karet", "slozka", "pas_karet"):
        maximum = {"roj_karet": 16, "slozka": 4, "pas_karet": 8}[karta]
        soubory = _soubory(reel, h("soubory"))[:maximum]
        if not soubory and karta != "pas_karet":
            soubory = _snimky_z_videa(reel, maximum if karta == "slozka" else 8, kontext)
        if len(soubory) < (2 if karta == "pas_karet" else 1):
            return None, "chybí obrázky nebo klipy v PODKLADY-SEM"
        spec["soubory"] = soubory
        if karta == "slozka":
            spec["nazev"] = h("nazev") or "moje videa"
        if karta == "roj_karet":
            spec["do"] = round(min(delka, max(do_v, od_v + 1.4)), 2)
        return spec, None
    if karta == "ikony":
        soubory = _soubory(reel, h("soubory"))[:5]
        if len(soubory) < 2:
            return None, "chybí 2 až 5 obrázků ikon v PODKLADY-SEM"
        popisky = _radky(h("popisky"))
        spec.update({"soubory": soubory, "popisky": (popisky + [Path(x).stem for x in soubory])[:len(soubory)] if popisky else
                     [Path(x).stem.replace("ikona-", "").capitalize() for x in soubory]})
        spec["do"] = round(min(delka, max(do_v + 0.5, od_v + 3.0)), 2)
        return spec, None
    if karta == "videa_okna":
        videa = []
        for kl in (kontext.get("klipy") or [])[:4]:
            dl = float(kl.get("delka") or 6)
            videa.append({"soubor": str(kl["cesta"]), "od": round(min(2.0, max(0.0, dl - 3.0)), 2), "delka": 2.5})
        if not videa:
            return None, "nemám natočené klipy"
        spec["videa"] = videa
        if h("stitek"):
            spec["stitek"] = h("stitek").upper()
        return spec, None
    if karta in ("plakat", "vypinac_plakat"):
        soubor = _soubory(reel, h("soubor"))
        if not soubor:
            return None, "chybí hotový plakát v PODKLADY-SEM"
        spec["soubor"] = soubor[0]
        if karta == "vypinac_plakat":
            spec.update({"od": 0.0, "do": round(min(delka, 9.1), 2), "cas_zapnuti": "auto"})
        else:
            slovo = h("slovo")
            w = next((x for x in kontext.get("slova_vety") or [] if slovo and _bez_diakritiky(x["w"]).strip(".,!?") == _bez_diakritiky(slovo).strip(".,!?")), None)
            spec["cas_zapnuti"] = round(w["start"], 2) if w else spec["od"]
            spec["od"] = round(max(0.0, spec["cas_zapnuti"] - 0.1), 2)
            spec["do"] = round(delka, 2)
        return spec, None
    if karta == "casova_osa":
        nahledy = _snimky_z_videa(reel, 6, kontext)
        if not nahledy:
            return None, "nemám snímky z videa"
        spec.update({"nahledy": nahledy, "vlna": _vlna(kontext), "nazev": "Časová osa"})
        spec["do"] = round(min(delka, max(do_v + 0.4, od_v + 2.5)), 2)
        return spec, None
    if karta == "storyboard":
        zaznamy = []
        for r in kontext.get("radky") or []:
            if r.get("veta") is None or r["prvek"] == "storyboard":
                continue
            jmeno = KARTY.get(r["prvek"], {}).get("typ") or r["prvek"]
            from .styl import PRVKY_TEXT
            zaznamy.append({"cas": "%s–%s" % (_cas_textem(r["od"]), _cas_textem(r["do"])), "delka": ("%.1f s" % (r["do"] - r["od"])).replace(".", ","),
                            "typ": "Mluvící záběr", "citat": r.get("text", "")[:80],
                            "body": [PRVKY_TEXT.get(r["prvek"], jmeno) if r["prvek"] != "zoom" else "přiblížení"]})
        if not zaznamy:
            return None, "plán je prázdný"
        spec.update({"zaznamy": zaznamy[:25], "hlavicka": "storyboard", "vpravo": "%d záběrů" % len(zaznamy)})
        spec["do"] = round(min(delka, max(do_v + 0.4, od_v + 4.0)), 2)
        return spec, None
    if karta == "pred_po":
        spec.update({"rezim": "posuvnik", "popisky": ["PŘED", "PO"]})
        spec["do"] = round(min(delka, max(do_v, od_v + 2.2)), 2)
        return spec, None
    return None, "efekt %s studio neumí sestavit" % karta


def typy_karty(karta):
    """Typ(y) prvku v osa["prvky"], podle kterých se pozná, že karta ve videu je."""
    if karta in KARTY:
        return {KARTY[karta]["typ"]}
    return {"vyzva": {"vyzva"}, "vlozka": {"vlozka"}, "karticky": {"karticky"}, "mrizka": {"mrizka"},
            "orbit": {"orbit"}, "zed": {"zed"}, "zapisnik": {"zapisnik"}, "nalepky": {"nalepky"}, "zprava": {"zprava"},
            "karty_slov": {"karty_slov"}}.get(karta, set())


def chybejici_ve_videu(styl_reelu, osa, data):
    """Vybrané karty, které ve výsledné časové ose nejsou (a zákaznice je nechtěla vynechat). Vrátí [klíč]."""
    typy = {p.get("typ") for p in osa.get("prvky", [])}
    out = []
    for karta in vybrane(styl_reelu):
        if karta in data.get("vynechat", []):
            continue
        if karta == "vyzva":
            # karta výzvy je v osa["mini"] (mini_silny s „vyzva“), výzvu umí nést i komentář na IG nebo sprej
            if not any(m.get("vyzva") or m.get("styl") == "mini_silny" for m in osa.get("mini", [])) \
                    and not ({"ig_komentar", "sprej"} & typy):
                out.append(karta)
            continue
        if karta == "velke_slovo":
            if not any(m.get("styl") == "slovo_velke" for m in osa.get("mini", [])):
                out.append(karta)
            continue
        if karta == "vsuvka":
            if not osa.get("vsuvky"):
                out.append(karta)
            continue
        if karta == "casomira":
            if not ((osa.get("hook") or {}).get("casomira") or any(x.get("casomira") for x in osa.get("prvky", []))):
                out.append(karta)
            continue
        t = typy_karty(karta)
        if t and not (t & typy):
            out.append(karta)
    return out
