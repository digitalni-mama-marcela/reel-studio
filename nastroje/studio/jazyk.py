"""Jazyk reelu (Marcela 25. 11. 2026): čeština a slovenčina.

Jazyk pozná přepis sám z hlasu (prepis.rozpoznej_jazyk), uloží se do PRACOVNI/jazyk.json a jde do časové osy
(osa["jazyk"]). Podle něj se berou opravy slov (NASTAVENI/opravy-slov-<jazyk>.json), hlídaná slova
(hlidana-slova-<jazyk>.json) a pevné texty ve videu (tlačítko Sledovat, pole komentáře…). Titulky jsou z jejích
slov, takže jsou v jejím jazyce samy. Stránky v prohlížeči (knihovna stylů, editor, plán) zůstávají česky.
"""
import re

JAZYKY = {"cs": "čeština", "sk": "slovenčina"}
VYCHOZI = "cs"

# pevné texty, které studio kreslí do videu (napodobují Instagram a aplikace v jazyce zákaznice)
TEXTY = {
    "napis_do_komentare": {"cs": "Napiš do komentáře", "sk": "Napíš do komentára"},
    "pridej_komentar": {"cs": "Přidej komentář…", "sk": "Pridaj komentár…"},
    "sledovat": {"cs": "Sledovat", "sk": "Sledovať"},
    "sledovano": {"cs": "Sledováno", "sk": "Sledujete"},
    "odpovedet": {"cs": "Odpovědět", "sk": "Odpovedať"},
    "napis_odpoved": {"cs": "Napiš odpověď", "sk": "Napíš odpoveď"},
    "odeslano": {"cs": "Odesláno", "sk": "Odoslané"},
    "casova_osa": {"cs": "Časová osa", "sk": "Časová os"},
    "prispevku": {"cs": "příspěvků", "sk": "príspevkov"},
    "sledujicich": {"cs": "sledujících", "sk": "sledujúcich"},
    "sleduji": {"cs": "sleduji", "sk": "sledované"},
    "ted": {"cs": "teď", "sk": "teraz"},
    "tvuj_vzhled": {"cs": "tvůj vzhled", "sk": "tvoj vzhľad"},
    "pismo_nadpisu": {"cs": "písmo nadpisů", "sk": "písmo nadpisov"},
    "na_miru": {"cs": "na míru tobě", "sk": "na mieru tebe"},
}


def platny(kod):
    kod = (kod or "").lower().split("-")[0]
    return kod if kod in JAZYKY else VYCHOZI


def text(klic, jazyk_nebo_spec=None):
    """Pevný text v jazyce reelu. Druhý argument je kód jazyka, nebo spec prvku / osa s klíčem „jazyk“."""
    j = jazyk_nebo_spec.get("jazyk") if isinstance(jazyk_nebo_spec, dict) else jazyk_nebo_spec
    return TEXTY[klic].get(platny(j), TEXTY[klic][VYCHOZI])


def nazev(kod):
    return JAZYKY.get(platny(kod))


# výzva do komentáře v obou jazycích: „napiš / napíš (mi) do komentáře / komentára“, „sleduj“, „follow“
VYZVA = re.compile(r"koment[aá]|nap[ií]š|sleduj|follow|zanechaj", re.I)
SLOVO_VYZVY = re.compile(r"nap[ií]š(?:\s+mi)?(?:\s+do\s+koment[aá][rř][ae]?)?\s+(?:slovo\s+)?[„\"]?(\w{3,})", re.I)
NE_SLOVO = {"komentáře", "komentář", "komentára", "komentár", "mi", "do", "slovo"}


def je_vyzva(text_vety):
    return bool(VYZVA.search(text_vety or ""))
