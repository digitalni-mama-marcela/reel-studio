"""Prvky na obrazovce (karty slov, zpráva pro Clauda, vložky v rámečku, mřížka, nálepky…).

Každý prvek je samostatný modul v této složce s těmito funkcemi (všechny povinné):

  pripravit(spec, styl, kontext) -> None
      Doplní do spec rozměry a polohu (spec["y"], spec["x"], spec["sirka"], spec["vyska"]) tak, aby prvek
      nezakrýval obličej. kontext = {"okno": obdélník obličeje po dobu prvku nebo None, "osa": osa,
      "podklady": Path složky s obrázky zákaznice, "sirka": 1080, "vyska": 1920, "horni": 220, "dolni": 450}.
  stav(spec, t) -> hashovatelný klíč, nebo None, když prvek v čase t (sekundy od začátku reelu) není vidět.
      Stejný klíč = stejný snímek (kvůli rychlosti se snímky ukládají). Animace vrací číslo snímku.
  vykresli(spec, styl, klic) -> (RGBA obrázek, (x, y))   obrázek se položí na plátno 1080x1920 na (x, y)
  obdelnik(spec, styl) -> (x0, y0, x1, y1)   plocha prvku po animaci (kontrola proti obličeji a okrajům)

Spec je slovník v osa["prvky"]: {"typ": "<název modulu>", "od": s, "do": s, ...vlastní klíče}.
Styl prvku je styl[typ] ze slovníku vzhledu (titulky.STYLY), když chybí, modul použije vlastní výchozí hodnoty
(VYCHOZI_STYL v modulu). Barvy vzhledu Marcela: krém (251,246,239), švestková (74,51,64), růžová (212,139,160),
blush (245,214,217), olivová (206,212,172). Písma: balicek/pisma (PlayfairDisplay-wght.ttf, Montserrat-wght.ttf,
InstrumentSerif-Italic.ttf, Mulish-wght.ttf), načítání přes titulky.pismo(soubor, velikost, varianta).
Bezpečné pásmo: nic důležitého v horních 220 px a spodních 450 px. Nic se nekreslí přes obličej (kontext["okno"]).
"""
import importlib
import pkgutil

REGISTR = {}


def nacti_vsechny():
    """Načte všechny moduly prvků v této složce do REGISTR (typ = název souboru)."""
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        if m.name not in REGISTR:
            REGISTR[m.name] = importlib.import_module("%s.%s" % (__name__, m.name))
    return REGISTR


def modul(typ):
    if typ not in REGISTR:
        nacti_vsechny()
    if typ not in REGISTR:
        raise KeyError("Prvek '%s' neexistuje (složka jadro/studio/prvky)." % typ)
    return REGISTR[typ]


def kontext_prvku(osa, obliceje, spec, podklady=None):
    """Kontext pro pripravit(): okno obličeje po dobu prvku a společné rozměry."""
    from .. import poloha
    from ..titulky import DOLNI_OKRAJ, HORNI_OKRAJ, SIRKA, VYSKA

    return {"okno": poloha.sjednoceni(obliceje, spec["od"], spec["do"]), "osa": osa, "podklady": podklady,
            "sirka": SIRKA, "vyska": VYSKA, "horni": HORNI_OKRAJ, "dolni": DOLNI_OKRAJ}


def priprav_vsechny(osa, styl, obliceje, podklady=None):
    """Zavolá pripravit() na každý prvek v osa["prvky"]. Vrátí seznam varování (česky), prázdný = v pořádku."""
    varovani = []
    for spec in osa.get("prvky", []):
        st = styl.get(spec["typ"], {})
        kontext = kontext_prvku(osa, obliceje, spec, podklady)
        if spec.get("za_hlavou", st.get("za_hlavou", getattr(modul(spec["typ"]), "ZA_HLAVOU", None))):
            okno = kontext.get("okno")
            # prvky z 3. 11. (ZA_HLAVOU v modulu) a prvky se spec["vzdy_za_hlavou"] zůstávají za osobou i u vysoké hlavy
            # (pravidlo Marcely 3. 11. 2026: efekty nikdy přes hlavu); vepředu by šly přes obličej (OVĚŘENO 3. 11., roj karet)
            vzdy = spec.get("vzdy_za_hlavou") or getattr(modul(spec["typ"]), "ZA_HLAVOU", False)
            if okno and okno[1] < kontext["horni"] + 180 and not vzdy:
                # hlava sahá až k hornímu okraji (OVĚŘENO 19. 10., reel 3): za hlavou by prvek nebyl vidět,
                # jde dopředu a modul ho položí pod bradu; u karet slov zůstává pozadí za osobou a text jde dopředu
                spec.pop("pres_oblicej", None)
                if spec["typ"] == "karty_slov":
                    spec["za_hlavou"], spec["text_vpredu"] = True, True
                else:
                    spec["za_hlavou"] = False
            else:
                # prvek jde za osobu (maska): umisťuje se bez ohledu na obličej, hlava smí zakrývat spodek písmen
                kontext["okno"] = None
                spec["pres_oblicej"] = True
        modul(spec["typ"]).pripravit(spec, st, kontext)
        if spec.get("varovani"):
            varovani.append("%s (%s): %s" % (spec["typ"], spec.get("od"), spec["varovani"]))
    return varovani
