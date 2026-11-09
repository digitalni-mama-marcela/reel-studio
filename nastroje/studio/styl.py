"""Kód stylu z knihovny stylů Marcely („Vyber si svůj styl“, https://claude.ai/artifact/7waF2A4cLZ6AqDNKisjyzN)
a obyčejné věty zákaznice, které styl reelu mění.

Kód stylu je jedna věta, kterou stránka dává zákaznici ke zkopírování (verze 16, 3. 11. 2026):
  styl: vogue; nadpisy: Playfair Display, #D48BA0, nahoře; obraz: černobílý; titulky: Montserrat, bílé, na hrudi,
  po jednom slově, 110 %; prvky: Efekt Orbit, Efekt Instagram zeď; zvuky: Klávesnice, Cink (60 %);
  moje obrázky: obalka-1.jpg k větě 3
Starší tvar (verze 14) se čte taky:
  styl: vogue; barva: #D48BA0; obraz: černobílý; písmo nadpisů: Playfair Display; titulky: Montserrat, na hrudi,
  110 %, bílé; prvky: Orbit, Instagram zeď; zvuky: klávesnice, cink (60 %); moje obrázky: obalka-1.jpg k větě 3
Pořadí částí je libovolné, velikost písmen a mezery nevadí, neznámá část se ohlásí a přeskočí.

Co se kam zapisuje:
  <složka reelu>/PRACOVNI/styl.json   rozebraný styl pro tento reel (čte ho krok plan a vzhled)
  <Reely>/NASTAVENI/styl.json         poslední zvolený styl zákaznice (pro další reel bez nového kódu)
  <složka reelu>/PRACOVNI/vzhled.json vzhled a „upravy“ (hodnoty vzhledu jen pro tento reel, titulky.pouzij_upravy)
Názvy presetů, barev, písem, poloh, prvků a zvuků odpovídají konstantám stránky (PRESETY, BARVY, FONTY, POLOHY,
REZIMY_T, NAZEV_EF, ZVUKY), OVĚŘENO ze zdroje dokumenty/knihovna-stylu/vyber-stylu-verze-16.html.
Od verze 20 (3. 11. 2026) stránka nemá hotové styly: „styl“ nese vzhled titulků (vlastní, svestkovy_editor, zeleny_editor,
slovo_a_kurziva) a mikro-nadpisy jsou základ (PRVKY_VZDY). Názvy všech karet hlídá test_styl.TestKnihovnaVerze20.
"""
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import projekt, titulky
from .titulky import CASTI_NADPISU, DOLNI_OKRAJ, VYSKA

# preset stránky -> vzhled studia (titulky.STYLY); „vlastní“ = ruční změny na stránce, základ je vzhled marcela
PRESETY = {"zapisnik": "zapisnik", "vogue": "vogue", "marcela": "marcela", "serif": "serif", "jedno_slovo": "jedno_slovo",
           "plny": "plny", "zeleny_editor": "zeleny_editor", "svestkovy_editor": "svestkovy_editor",
           "slovo_a_kurziva": "slovo_a_kurziva", "vlastni": "marcela"}
# velikost titulků v % u presetu na stránce (PRESETY[k].velikost): 100 % stránky = 58 px, preset má vlastní procenta,
# ve studiu má každý vzhled vlastní výchozí velikost; procenta kódu se proto berou vůči procentům presetu
PRESET_PROCENTA = {"zapisnik": 100, "vogue": 95, "marcela": 100, "serif": 100, "jedno_slovo": 255, "plny": 110, "zeleny_editor": 100,
                   "svestkovy_editor": 100, "slovo_a_kurziva": 152}
NAZVY_PRESETU = {"zapisnik": "Zápisník a čísla", "vogue": "Vogue", "marcela": "Barvy značky", "serif": "Čistý patkový",
                 "jedno_slovo": "Jedno slovo", "plny": "Výrazný",
                 "zeleny_editor": "Zelený editor", "svestkovy_editor": "Švestkový editor",
                 "slovo_a_kurziva": "Slovo a kurzíva", "vlastni": "vlastní (základ Barvy značky)"}
# hodnoty kódu, které preset na stránce posílá jako výchozí (stejné = vzhled studia beze změny)
PRESET_VYCHOZI = {"zeleny_editor": {"barva": "#F3EBDD", "pismo_nadpisu": "Playfair Display", "pismo_titulku": "Instrument Serif"}}
PRESET_VYCHOZI["svestkovy_editor"] = PRESET_VYCHOZI["zeleny_editor"]
PRESET_VYCHOZI["slovo_a_kurziva"] = {"barva": "#F7D254", "pismo_nadpisu": "Inter", "pismo_titulku": "Inter"}
BARVY = {"kremova": "#F6EBD0", "bila": "#FFFFFF", "zluta": "#FFD43B", "oranzova": "#FF8C42", "cervena": "#E5383B",
         "ruzova": "#F28AB2", "fialova": "#A66CFF", "modra": "#4EA8DE", "zelena": "#52B788", "tmave modra": "#1D3557",
         "cerna": "#111111", "barvy znacky marcely": "#D48BA0", "barvy znacky": "#D48BA0"}
# česká slova barev ve větách (kořen bez diakritiky -> barva); zlatá a béžová nejsou na stránce, hodnoty NÁVRH
KORENY_BAREV = [("tmave modr", "#1D3557"), ("cerven", "#E5383B"), ("ruzov", "#F28AB2"), ("modr", "#4EA8DE"),
                ("zelen", "#52B788"), ("zlut", "#FFD43B"), ("oranzov", "#FF8C42"), ("fialov", "#A66CFF"),
                ("cern", "#111111"), ("bil", "#FFFFFF"), ("zlat", "#D4AF37"), ("bezov", "#E8D5B7"), ("kremov", "#F6EBD0")]
POLOHY = {"na hrudi": "hrud", "hrud": "hrud", "vedle hlavy": "vedle", "vedle": "vedle", "dole": "dole"}
POLOHY_TEXT = {"hrud": "na hrudi", "vedle": "vedle hlavy", "dole": "dole"}
REZIMY = {"po jednom slove": "slovo", "po slovech": "slovo", "jedno slovo": "slovo", "cele vety": "veta", "vety": "veta",
          "cele vety, zvyraznene slovo": "veta_zvyr", "zvyraznene slovo": "veta_zvyr", "vety se zvyraznenym slovem": "veta_zvyr"}
REZIMY_TEXT = {"slovo": "po jednom slově", "veta": "celé věty", "veta_zvyr": "celé věty se zvýrazněným slovem"}
ZVUKY = {"klavesnice": "klavesa", "klavesa": "klavesa", "cink": "cink", "svih": "whoosh", "whoosh": "whoosh", "klik": "klik"}
ZVUKY_TEXT = {"klavesa": "klávesnice", "cink": "cink", "whoosh": "švih", "klik": "klik"}
ZVUKY_KNIHOVNY = set(ZVUKY_TEXT)
# názvy karet prvků na stránce (NAZEV_EF) -> klíč prvku; klíč se bere i přímo (orbit, zed, …)
PRVKY = {"karta hooku": "hook", "hook": "hook", "titulky po slovech": "titulky", "titulky": "titulky",
         "mikro-nadpis": "mini", "mikro nadpis": "mini", "mini": "mini", "karta vyzvy": "vyzva", "vyzva": "vyzva",
         "vsuvka": "vsuvka", "priblizeni (zoom)": "zoom", "priblizeni": "zoom", "zoom": "zoom", "karty slov": "karty_slov",
         "zprava pro clauda": "zprava", "zprava": "zprava", "obrazek v ramecku": "vlozka", "vlozka": "vlozka",
         "mrizka reelu": "mrizka", "mrizka": "mrizka", "nalepky s preskrtnutim": "nalepky", "nalepky": "nalepky",
         "text za hlavou": "za_hlavou", "za hlavou": "za_hlavou", "karticky s printscreeny": "karticky", "karticky": "karticky",
         "obri slovo": "velke_slovo", "velke slovo": "velke_slovo", "tikajici cas pod hookem": "casomira", "casomira": "casomira",
         "efekt orbit": "orbit", "orbit": "orbit", "efekt instagram zed": "zed", "instagram zed": "zed", "zed": "zed",
         "hravy nadpis": "hravy_nadpis", "hravy nadpis s gesty": "hravy_nadpis_gesta",
         "zapisnik s odskrtavanim": "zapisnik", "zapisnik": "zapisnik", "papirove karty a sprej": "papirove_karty",
         "papirove karty": "papirove_karty", "vypinac a plakat": "vypinac_plakat", "vypinac": "vypinac_plakat",
         "pred a po": "pred_po", "posuvnik pred a po": "pred_po", "pred_po": "pred_po",
         "skladany nadpis": "skladany_nadpis", "skladany_nadpis": "skladany_nadpis", "rucni poznamka": "rucni_poznamka",
         "rucni poznamka se sipkou": "rucni_poznamka", "rucni_poznamka": "rucni_poznamka", "roj karet": "roj_karet",
         "roj_karet": "roj_karet", "slozka s klipy": "slozka", "slozka": "slozka", "pas karet": "pas_karet",
         "pas_karet": "pas_karet", "karta vzhledu": "karta_vzhledu", "karta_vzhledu": "karta_vzhledu",
         "casova osa": "casova_osa", "casova_osa": "casova_osa",
         # verze 20 knihovny (3. 11. 2026): smíchané karty rozdělené, nové karty z hotových reelů Marcely
         "plakat za tebou": "plakat", "plakat": "plakat", "profil s nuzkami": "papir_profil", "papir_profil": "papir_profil",
         "nalepka s otazkou": "papir_otazka", "papir_otazka": "papir_otazka", "padajici komentare": "papir_komentare",
         "papir_komentare": "papir_komentare", "napis sprejem": "sprej", "sprej": "sprej",
         "komentar jako na instagramu": "ig_komentar", "ig_komentar": "ig_komentar", "tlacitko sledovat": "ig_sledovat",
         "ig_sledovat": "ig_sledovat", "preklapeci casovac": "pocitadlo", "pocitadlo": "pocitadlo",
         "obalka casopisu": "obalka_casopisu", "obalka_casopisu": "obalka_casopisu", "ikony aplikaci": "ikony", "ikony": "ikony",
         "casova osa strihu": "casova_osa", "okna se surovymi videi": "videa_okna", "videa_okna": "videa_okna",
         "storyboard": "storyboard", "napsano a preskrtnuto": "psany_skrt", "psany_skrt": "psany_skrt"}
PRVKY_TEXT = {"hook": "karta hooku", "titulky": "titulky", "mini": "mikro-nadpis", "vyzva": "karta výzvy", "vsuvka": "vsuvka",
              "zoom": "přiblížení", "karty_slov": "karty slov", "zprava": "zpráva pro Clauda", "vlozka": "obrázek v rámečku",
              "mrizka": "mřížka reelů", "nalepky": "nálepky s přeškrtnutím", "za_hlavou": "text za hlavou",
              "karticky": "kartičky s printscreeny", "velke_slovo": "obří slovo", "casomira": "tikající čas pod hookem",
              "orbit": "orbit", "zed": "Instagram zeď", "hravy_nadpis": "hravý nadpis", "hravy_nadpis_gesta": "hravý nadpis s gesty",
              "zapisnik": "zápisník", "papirove_karty": "papírové karty a sprej", "vypinac_plakat": "vypínač a plakát",
              "pred_po": "před a po", "skladany_nadpis": "skládaný nadpis", "rucni_poznamka": "ruční poznámka se šipkou",
              "roj_karet": "roj karet", "slozka": "složka s klipy", "pas_karet": "pás karet", "karta_vzhledu": "karta vzhledu",
              "casova_osa": "časová osa střihu", "plakat": "plakát za tebou", "papir_profil": "profil s nůžkami",
              "papir_otazka": "nálepka s otázkou", "papir_komentare": "padající komentáře", "sprej": "nápis sprejem",
              "ig_komentar": "komentář jako na Instagramu", "ig_sledovat": "tlačítko Sledovat", "pocitadlo": "překlápěcí časovač",
              "obalka_casopisu": "obálka časopisu", "ikony": "ikony aplikací", "videa_okna": "okna se surovými videi",
              "storyboard": "storyboard", "psany_skrt": "napsáno a přeškrtnuto"}
# klíč karty -> typ prvku v osa["prvky"] a hodnoty, které karta určuje (ostatní doplní Claude podle věty, viz docstring prvku)
PRVEK_KARTY = {"plakat": ("vypinac_plakat", {"vypinac": False}), "papir_profil": ("papirova_karta", {"druh": "profil", "konec": "strih"}),
               "papir_otazka": ("papirova_karta", {"druh": "otazka", "konec": "odfouknuti"}),
               "papir_komentare": ("papirova_karta", {"druh": "komentar", "konec": "dopad"}),
               "papirove_karty": ("papirova_karta", {}), "vypinac_plakat": ("vypinac_plakat", {"vypinac": True})}
# prvky, které plán smí navrhnout vždy (bez nich reel nejde) a prvek, který zákaznice označila sama (WOW moment)
# mikro-nadpisy jsou od verze 20 knihovny základ jako titulky (Marcela 3. 11.: nejdřív nadpis a titulky, pak efekty)
PRVKY_VZDY = {"zoom", "chybi_obrazek", "wow", "titulky", "mini"}
# prvky plánu (krok plan) a jejich klíč z knihovny: plán zná jen tyhle, ostatní karty knihovny vkládá zákaznice ručně
PRVKY_PLANU = {"hook", "karty_slov", "mini", "vyzva", "zprava", "vlozka", "mrizka", "nalepky", "karticky", "velke_slovo",
               "orbit", "zed", "stitky", "zapisnik", "prulet", "wow"}
CB_FILTR = "hue=s=0,eq=contrast=1.06"     # černobílý obraz (ffmpeg hue a eq OVĚŘENO v ffmpeg z Homebrew 3. 11. 2026), NÁVRH kontrast
ZMENA_VELIKOSTI = 1.15                     # „písmo větší / menší“ = o 15 %
POSUN_HOOKU = {"jemne": 50, "normalne": 120}


def _norm(text):
    """Malá písmena bez diakritiky, jedna mezera."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", t).strip()


def hex_na_rgb(h):
    h = str(h).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError("barva %r není ve tvaru #RRGGBB" % h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_na_hex(rgb):
    return "#%02X%02X%02X" % tuple(rgb[:3])


def _hex_v_textu(text):
    m = re.search(r"#?\b([0-9a-fA-F]{6})\b", text)
    return ("#" + m.group(1).upper()) if m and ("#" in text or not text.strip().isalpha()) else None


def _pismo(text):
    """Název písma ze stránky (FONTY), tolerantně k velikosti písmen a diakritice."""
    n = _norm(text)
    for nazev in titulky.PISMA_NA_VYBER:
        if _norm(nazev) == n:
            return nazev
    return None


def _procenta(text):
    m = re.search(r"(\d{2,3})\s*%", text)
    return int(m.group(1)) if m else None


def _tmava(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] < 110


# ---------------------------------------------------------------------------------------------------------------
# 1. rozbor kódu stylu
# ---------------------------------------------------------------------------------------------------------------

def vychozi_styl():
    return {"preset": None, "vzhled": None, "barva": None, "cernobily": False, "pismo_nadpisu": None, "pismo_titulku": None,
            "poloha_nadpisu": None, "barva_titulku": None, "poloha_titulku": None, "rezim_titulku": None,
            "velikost_titulku": None, "prvky": None, "zvuky": None, "hlasitost": None, "obrazky": [], "kod": None}


def rozeber_kod(kod):
    """Rozebere větu z knihovny stylů. Vrátí (styl, hlášky), hlášky = [(úroveň, text)], úroveň „ok“ nebo „pozor“.
    Nikdy nevyhodí výjimku kvůli neznámé části: ta se ohlásí a přeskočí."""
    s = vychozi_styl()
    s["kod"] = kod.strip()
    hlasky = []
    casti = [c.strip() for c in re.split(r"\s*;\s*", kod.strip()) if c.strip()]
    for cast in casti:
        if ":" not in cast:
            hlasky.append(("pozor", "Části „%s“ nerozumím (chybí dvojtečka), přeskakuju ji." % cast))
            continue
        klic, hodnota = cast.split(":", 1)
        klic, hodnota = _norm(klic), hodnota.strip()
        hn = _norm(hodnota)
        if klic == "styl":
            p = hn.replace(" ", "_").replace("-", "_")
            if p in PRESETY:
                s["preset"], s["vzhled"] = p, PRESETY[p]
                hlasky.append(("ok", "Styl: %s → vzhled %s." % (NAZVY_PRESETU[p], s["vzhled"])))
            elif hn in titulky.STYLY:
                s["preset"], s["vzhled"] = hn, hn
                hlasky.append(("ok", "Styl: vzhled studia %s." % hn))
            else:
                s["preset"], s["vzhled"] = "vlastni", PRESETY["vlastni"]
                hlasky.append(("pozor", "Styl „%s“ neznám, beru základ Barvy značky (marcela). Znám: %s." % (
                    hodnota, ", ".join(NAZVY_PRESETU[k] for k in PRESET_PROCENTA))))
        elif klic == "barva":
            h = _hex_v_textu(hodnota) or BARVY.get(hn)
            if h:
                s["barva"] = h.upper()
                hlasky.append(("ok", "Barva nadpisů a zvýraznění: %s." % s["barva"]))
            else:
                hlasky.append(("pozor", "Barvě „%s“ nerozumím (čekám #RRGGBB nebo název ze stránky)." % hodnota))
        elif klic == "nadpisy":
            for dil in [d.strip() for d in hodnota.split(",") if d.strip()]:
                dn = _norm(dil)
                if _pismo(dil):
                    s["pismo_nadpisu"] = _pismo(dil)
                elif _hex_v_textu(dil):
                    s["barva"] = _hex_v_textu(dil).upper()
                elif dn in ("nahore", "uprostred", "uprostred videa"):
                    s["poloha_nadpisu"] = "stred" if dn.startswith("uprostred") else "nahore"
                elif dn in BARVY:
                    s["barva"] = BARVY[dn]
                else:
                    hlasky.append(("pozor", "U nadpisů nerozumím části „%s“." % dil))
            hlasky.append(("ok", "Nadpisy: písmo %s, barva %s, %s." % (
                s["pismo_nadpisu"] or "podle vzhledu", s["barva"] or "podle vzhledu",
                "uprostřed videa" if s["poloha_nadpisu"] == "stred" else "nahoře")))
        elif klic == "obraz":
            s["cernobily"] = "cernobil" in hn
            hlasky.append(("ok", "Obraz: %s." % ("černobílý" if s["cernobily"] else "barevný (%s)" % hodnota)))
        elif klic in ("pismo nadpisu", "pismo nadpisů", "pismo"):
            p = _pismo(hodnota)
            if p:
                s["pismo_nadpisu"] = p
                hlasky.append(("ok", "Písmo nadpisů: %s." % p))
            else:
                hlasky.append(("pozor", "Písmo „%s“ ve studiu není. Na výběr: %s." % (hodnota, ", ".join(titulky.PISMA_NA_VYBER))))
        elif klic == "titulky":
            for dil in [d.strip() for d in hodnota.split(",") if d.strip()]:
                dn = _norm(dil)
                if _pismo(dil):
                    s["pismo_titulku"] = _pismo(dil)
                elif dn in POLOHY:
                    s["poloha_titulku"] = POLOHY[dn]
                elif _procenta(dil) is not None:
                    s["velikost_titulku"] = _procenta(dil)
                elif dn in ("bile", "bila"):
                    s["barva_titulku"] = "#FFFFFF"
                elif dn in ("cerne", "cerna"):
                    s["barva_titulku"] = "#111111"
                elif dn in ("barva jako nadpisy", "jako nadpisy", "v barve nadpisu"):
                    s["barva_titulku"] = "nadpis"
                elif _hex_v_textu(dil):
                    s["barva_titulku"] = _hex_v_textu(dil).upper()
                elif dn in REZIMY:
                    s["rezim_titulku"] = REZIMY[dn]
                elif dn == "cele vety" or dn == "zvyraznene slovo":
                    s["rezim_titulku"] = REZIMY[dn]
                else:
                    hlasky.append(("pozor", "U titulků nerozumím části „%s“." % dil))
            # „celé věty, zvýrazněné slovo“ přijde jako dvě části za čárkou
            if s["rezim_titulku"] == "veta" and "zvyraznen" in hn:
                s["rezim_titulku"] = "veta_zvyr"
            hlasky.append(("ok", "Titulky: písmo %s, barva %s, %s, %s, velikost %s." % (
                s["pismo_titulku"] or "podle vzhledu",
                "jako nadpisy" if s["barva_titulku"] == "nadpis" else (s["barva_titulku"] or "podle vzhledu"),
                POLOHY_TEXT.get(s["poloha_titulku"], "podle vzhledu"), REZIMY_TEXT.get(s["rezim_titulku"], "podle vzhledu"),
                ("%d %%" % s["velikost_titulku"]) if s["velikost_titulku"] else "podle vzhledu")))
        elif klic == "prvky":
            s["prvky"] = []
            if hn in ("jen zaklad", "zaklad", "zadne", ""):
                hlasky.append(("ok", "Prvky: jen základ (titulky a přiblížení)."))
                continue
            for dil in [d.strip() for d in hodnota.split(",") if d.strip()]:
                dn = _norm(dil)
                p = PRVKY.get(dn) or PRVKY.get(dn.replace("efekt ", "")) or (dn.replace(" ", "_") if dn.replace(" ", "_") in PRVKY_TEXT else None)
                if p:
                    if p not in s["prvky"]:
                        s["prvky"].append(p)
                else:
                    hlasky.append(("pozor", "Prvek „%s“ neznám, vynechávám ho. Znám: %s." % (dil, ", ".join(PRVKY_TEXT.values()))))
            hlasky.append(("ok", "Prvky (%d): %s." % (len(s["prvky"]), ", ".join(PRVKY_TEXT[p] for p in s["prvky"]) or "žádné")))
        elif klic == "zvuky":
            s["zvuky"] = []
            s["hlasitost"] = _procenta(hodnota)
            bez_procent = re.sub(r"\(.*?\)", "", hodnota)
            if _norm(bez_procent) in ("bez zvuku", "zadne", "bez"):
                hlasky.append(("ok", "Zvuky: žádné."))
                continue
            for dil in [d.strip() for d in bez_procent.split(",") if d.strip()]:
                z = ZVUKY.get(_norm(dil))
                if z:
                    if z not in s["zvuky"]:
                        s["zvuky"].append(z)
                else:
                    hlasky.append(("pozor", "Zvuk „%s“ neznám, vynechávám ho. Znám: %s." % (dil, ", ".join(ZVUKY_TEXT.values()))))
            hlasky.append(("ok", "Zvuky: %s%s." % (", ".join(ZVUKY_TEXT[z] for z in s["zvuky"]) or "žádné",
                                                  (" (hlasitost %d %%)" % s["hlasitost"]) if s["hlasitost"] is not None else "")))
        elif klic in ("moje obrazky", "obrazky", "fotky", "moje fotky"):
            for dil in [d.strip() for d in hodnota.split(",") if d.strip()]:
                m = re.match(r"^(.+?)\s+k\s+vet[eě]\s+(\d+)\s*$", dil, flags=re.IGNORECASE) or \
                    re.match(r"^(.+?)\s+k\s+v\S*\s+(\d+)\s*$", _norm(dil))
                if m:
                    s["obrazky"].append({"soubor": m.group(1).strip(), "veta": int(m.group(2))})
                else:
                    hlasky.append(("pozor", "Obrázku „%s“ nerozumím (čekám „soubor k větě 3“)." % dil))
            hlasky.append(("ok", "Moje obrázky: %s." % (", ".join("%s k větě %d" % (o["soubor"], o["veta"]) for o in s["obrazky"]) or "žádné")))
        else:
            hlasky.append(("pozor", "Část „%s“ neznám, přeskakuju ji. Znám: styl, nadpisy, barva, obraz, písmo nadpisů, titulky, prvky, zvuky, moje obrázky." % klic))
    if not s["vzhled"]:
        s["preset"], s["vzhled"] = "vlastni", PRESETY["vlastni"]
        hlasky.append(("pozor", "V kódu chybí „styl“, beru základ Barvy značky (marcela)."))
    if s["barva_titulku"] == "nadpis":
        s["barva_titulku"] = s["barva"] or "#FFFFFF"
    return s, hlasky


# ---------------------------------------------------------------------------------------------------------------
# 2. styl -> úpravy vzhledu (titulky.pouzij_upravy) a nastavení zvuků
# ---------------------------------------------------------------------------------------------------------------

def _zaklad(vzhled, cast):
    """Původní hodnoty části vzhledu (před úpravami zákaznice)."""
    return titulky.ZAKLAD.get(vzhled, {}).get(cast, {})


def upravy_titulku_rezim(vzhled, rezim, barva_nadpisu=None):
    """Hodnoty titulků pro režim ze stránky: po jednom slově / celé věty / celé věty se zvýrazněným slovem."""
    z = _zaklad(vzhled, "titulky")
    if rezim == "slovo":
        return {"max_slov": 1, "radku": 1, "ztlumene": 1.0, "po_slovech": False, "zvyrazni": None, "max_sirka": max(600, z.get("max_sirka", 600))}
    u = {"max_slov": z.get("max_slov", 5) if z.get("max_slov", 5) > 1 else 5, "radku": 2 if z.get("radku", 2) >= 2 or z.get("max_slov", 5) <= 1 else z["radku"],
         "ztlumene": z.get("ztlumene", 0.4) if z.get("ztlumene", 1.0) < 1.0 else 0.40, "po_slovech": True,
         "max_sirka": max(880, z.get("max_sirka", 880))}
    u["zvyrazni"] = hex_na_rgb(barva_nadpisu) if (rezim == "veta_zvyr" and barva_nadpisu) else None
    return u


def upravy_titulku_poloha(poloha):
    if poloha == "dole":
        return {"vedle_hlavy": False, "stred_y": None, "spodek": VYSKA - DOLNI_OKRAJ - 20}
    return {"vedle_hlavy": True, "poloha": poloha}


def upravy_ze_stylu(s, zachovat_pismo=False):
    """Z rozebraného stylu udělá úpravy vzhledu {vzhled: {část: {klíč: hodnota}}} (hodnoty čitelné pro JSON,
    barvy jako seznamy) a vrátí (úpravy, hlášky)."""
    vzhled = s["vzhled"]
    casti = {}
    hlasky = []
    # stránka posílá barvu a písma vždycky; když jsou stejné jako výchozí u presetu, vzhled se nemění
    # (Zelený editor: zelené rámečky nadpisů a titulky Instrument Serif rovné, ne kurzíva)
    vychozi = PRESET_VYCHOZI.get(s.get("preset"), {})
    if vychozi:
        s = dict(s)
        for k, v in vychozi.items():
            if s.get(k) and str(s[k]).lower() == str(v).lower():
                s[k] = None

    def nastav(cast, **hod):
        casti.setdefault(cast, {}).update({k: (list(v) if isinstance(v, tuple) else v) for k, v in hod.items()})

    if s["barva"]:
        rgb = hex_na_rgb(s["barva"])
        for cast in CASTI_NADPISU:
            z = _zaklad(vzhled, cast)
            if not z:
                continue
            if cast == "stitky":
                nastav(cast, podklad=rgb, barva=(17, 17, 17) if not _tmava(rgb) else (255, 255, 255))
            else:
                # jako na stránce: nadpis v barvě bez karty, s měkkým stínem (tmavá barva dostane světlou záři)
                nastav(cast, barva=rgb, barva_zvyrazneni=rgb)
                if z.get("podklad"):
                    nastav(cast, podklad=None, stin=max(10, int(z.get("stin") or 0)), stin_sila=0.6, stin_posun=6)
        if "orbit" in titulky.ZAKLAD.get(vzhled, {}):
            nastav("orbit", barva_ramu=rgb)
        hlasky.append("Nadpisy v barvě %s (bez karty, se stínem)." % s["barva"])
    if s["cernobily"]:
        casti["filtr"] = CB_FILTR
        hlasky.append("Obraz černobílý (filtr %s)." % CB_FILTR)
    if (s["pismo_nadpisu"] or s["pismo_titulku"]) and zachovat_pismo:
        hlasky.append("Písmo z kódu nepoužívám: zákaznice chce zachovat svoje („zachovej moje písmo“).")
    elif s["pismo_nadpisu"] or s["pismo_titulku"]:
        p = titulky.upravy_pisma(vzhled, nadpis=s["pismo_nadpisu"], titulky=s["pismo_titulku"])[vzhled]
        for cast, hod in p.items():
            nastav(cast, **hod)
        if s["pismo_nadpisu"] and "mini_podpis" in titulky.ZAKLAD.get(vzhled, {}):
            pass    # podpis (kurzíva) zůstává, je to záměr vzhledu
        hlasky.append("Písmo: nadpisy %s, titulky %s." % (s["pismo_nadpisu"] or "podle vzhledu", s["pismo_titulku"] or "podle vzhledu"))
    if s["barva_titulku"]:
        rgb = hex_na_rgb(s["barva_titulku"])
        nastav("titulky", barva=rgb)
        if _tmava(rgb):
            nastav("titulky", stin=max(140, int(_zaklad(vzhled, "titulky").get("stin") or 0)))
        hlasky.append("Titulky v barvě %s." % s["barva_titulku"])
    if s["rezim_titulku"]:
        nastav("titulky", **upravy_titulku_rezim(vzhled, s["rezim_titulku"], s["barva"]))
        hlasky.append("Titulky %s." % REZIMY_TEXT[s["rezim_titulku"]])
    if s["poloha_titulku"]:
        nastav("titulky", **upravy_titulku_poloha(s["poloha_titulku"]))
        hlasky.append("Titulky %s." % POLOHY_TEXT[s["poloha_titulku"]])
    if s["velikost_titulku"]:
        zakl = _zaklad(vzhled, "titulky").get("velikost", 58)
        pct = PRESET_PROCENTA.get(s["preset"], 100) if s["preset"] in PRESET_PROCENTA else 100
        vel = int(round(zakl * s["velikost_titulku"] / pct))
        nastav("titulky", velikost=max(30, min(260, vel)))
        hlasky.append("Velikost titulků %d %% (%d px, výchozí vzhledu %d px)." % (s["velikost_titulku"], casti["titulky"]["velikost"], zakl))
    if s["poloha_nadpisu"] == "stred":
        hlasky.append("⚠️ Nadpisy uprostřed videa studio zatím neumí (NEOVĚŘENO), dám je nahoru nad hlavu.")
    return {vzhled: casti}, hlasky


def zvuky_nastaveni(s):
    """Nastavení zvuků pro render (zvuky.podle_nastaveni): které z knihovny smí znít a posun hlasitosti v dB."""
    if s.get("zvuky") is None and s.get("hlasitost") is None:
        return None
    n = {"povolene": s.get("zvuky"), "bez": s.get("zvuky") == [], "db_posun": 0.0}
    if s.get("hlasitost") is not None:
        n["hlasitost"] = int(s["hlasitost"])
        n["db_posun"] = db_posun(int(s["hlasitost"]))
    return n


def db_posun(hlasitost):
    """Hlasitost ze stránky v % (100 % = jak studio zvuky míchá): posun v dB, nejmíň −40 dB."""
    import math
    h = max(1, min(200, int(hlasitost)))
    return round(max(-40.0, 20 * math.log10(h / 100.0)), 2)


# ---------------------------------------------------------------------------------------------------------------
# 3. soubory
# ---------------------------------------------------------------------------------------------------------------

def soubor_reelu(reel):
    return projekt.slozky(reel)["pracovni"] / "styl.json"


def soubor_nastaveni(reel):
    return Path(reel).parent / "NASTAVENI" / "styl.json"


def nacti(reel):
    """Styl tohoto reelu (PRACOVNI/styl.json), {} když žádný není. Reely bez stylu se chovají jako dřív."""
    return projekt.nacti_json(soubor_reelu(reel), {}) or {}


def nacti_posledni(reel):
    """Poslední styl zákaznice (NASTAVENI/styl.json), {} když žádný."""
    return projekt.nacti_json(soubor_nastaveni(reel), {}) or {}


def zapis_styl(reel, s, upravy, hlasky_upravy, kod=None):
    """Zapíše PRACOVNI/styl.json, NASTAVENI/styl.json a PRACOVNI/vzhled.json. Vrátí cesty."""
    s = dict(s)
    s["kdy"] = datetime.now().isoformat(timespec="seconds")
    s["zvuky_nastaveni"] = zvuky_nastaveni(s)
    s["upravy"] = upravy
    s["upravy_popis"] = hlasky_upravy
    if kod:
        s["kod"] = kod
    stary = nacti(reel)
    for k in ("zachovat_pismo",):
        if stary.get(k) is not None:
            s.setdefault(k, stary[k])
    projekt.uloz_json(soubor_reelu(reel), s)
    posledni = {k: v for k, v in s.items() if k != "obrazky"}
    posledni["obrazky"] = []        # obrázky k větám patří jen k tomuhle reelu
    posledni["reel"] = str(Path(reel).name)
    projekt.uloz_json(soubor_nastaveni(reel), posledni)
    vz = projekt.nacti_json(projekt.slozky(reel)["pracovni"] / "vzhled.json", {}) or {}
    novy = not vz
    vz["vzhled"] = s["vzhled"]
    vz["titulky_z"] = None
    vz["upravy"] = upravy
    if novy or vz.get("jen_styl"):
        vz["jen_styl"] = True       # krok vzhled: první vykreslení smí ještě navrhnout mikro-nadpisy
    projekt.uloz_json(projekt.slozky(reel)["pracovni"] / "vzhled.json", vz)
    return soubor_reelu(reel), soubor_nastaveni(reel), projekt.slozky(reel)["pracovni"] / "vzhled.json"


# ---------------------------------------------------------------------------------------------------------------
# 4. plán: povolené prvky a obrázky k větám
# ---------------------------------------------------------------------------------------------------------------

def pouzij_na_plan(radky, s, vety, obrazky=None):
    """Upraví řádky plánu podle stylu reelu: prvek mimo povolené -> jen přiblížení, obrázky ze stylu -> vložka
    (víc obrázků k jedné větě -> kartičky). Vrátí hlášky (česky). Bez stylu nic nemění."""
    hlasky = []
    if not s:
        return hlasky
    povolene = s.get("prvky")
    if isinstance(povolene, list):
        p = set(povolene) | PRVKY_VZDY
        for r in radky:
            if r["prvek"] in p:
                continue
            if r["prvek"] == "karty_slov" and "hook" in p:
                r["prvek"], r["obsah"] = "hook", " ".join(x.strip() for x in r["obsah"].split("|"))
                r["duvod"] = "hook jako karta (karty slov nejsou ve zvoleném stylu)"
            elif r["prvek"] == "hook" and "karty_slov" in p:
                r["prvek"], r["obsah"] = "karty_slov", " | ".join(r["obsah"].split())
                r["duvod"] = "hook jako karty slov (karta hooku není ve zvoleném stylu)"
            else:
                hlasky.append("Věta %s: prvek %s vynechán, není ve zvoleném stylu." % (r["veta"], PRVKY_TEXT.get(r["prvek"], r["prvek"])))
                r["prvek"], r["obsah"], r["duvod"] = "zoom", "podle pořadí úrovní", "bez prvku: %s není ve zvoleném stylu" % PRVKY_TEXT.get(r["prvek"], r["prvek"])
    podle_vety = {}
    for o in s.get("obrazky") or []:
        podle_vety.setdefault(int(o["veta"]), []).append(o["soubor"])
    jmena = {Path(x).name for x in (obrazky or [])}
    for cislo, soubory in sorted(podle_vety.items()):
        if not (1 <= cislo <= len(vety)):
            hlasky.append("⚠️ Obrázek %s k větě %d: reel má jen %d vět, vynechávám." % (", ".join(soubory), cislo, len(vety)))
            continue
        vid = vety[cislo - 1]["id"]
        rad = next((r for r in radky if r["veta"] == vid), None)
        if rad is None:
            continue
        chybi = [x for x in soubory if Path(x).name not in jmena]
        if chybi:
            rad.update({"prvek": "chybi_obrazek", "obsah": " | ".join(soubory), "zdroj": "styl", "rucne": True,
                        "duvod": "obrázek ze stylu k větě %d, v podkladech chybí: %s" % (cislo, ", ".join(chybi))})
            hlasky.append("⚠️ Obrázek %s k větě %d není ve složce podkladů (PODKLADY-SEM reelu, nebo --podklady). Nahraj ho tam a spusť plan znovu." % (", ".join(chybi), cislo))
            continue
        if len(soubory) == 1:
            rad.update({"prvek": "vlozka", "obsah": soubory[0], "duvod": "obrázek ze stylu k větě %d" % cislo, "zdroj": "styl", "rucne": True})
        else:
            rad.update({"prvek": "karticky", "obsah": " | ".join(soubory), "duvod": "obrázky ze stylu k větě %d" % cislo, "zdroj": "styl", "rucne": True})
        hlasky.append("Věta %d (%s): %s %s." % (cislo, vid, "obrázek" if len(soubory) == 1 else "kartičky", ", ".join(soubory)))
    return hlasky


# ---------------------------------------------------------------------------------------------------------------
# 5. obyčejné věty zákaznice
# ---------------------------------------------------------------------------------------------------------------

UMIM = ["písmo větší / menší (o 15 %)", "nadpisy větší / menší", "písmo červeně (barvy: červená, modrá, zelená, žlutá, růžová, "
        "oranžová, fialová, černá, bílá, zlatá, béžová, krémová, nebo #RRGGBB)", "nadpisy červeně", "dej červené pozadí (podklad nadpisů)",
        "titulky po slovech / celé věty", "titulky nahoru (vedle hlavy) / dolů / na hruď", "hook nahoru / dolů, ale jemně",
        "zachovej moje písmo", "bez zvuků / zvuky zpátky", "hlasitěji / tišeji"]


def _barva_ve_vete(n):
    h = re.search(r"#([0-9a-f]{6})\b", n)
    if h:
        return "#" + h.group(1).upper()
    for koren, hexa in KORENY_BAREV:
        if koren in n:
            return hexa
    return None


def rozeber_vetu(veta, vzhled, aktualni):
    """Obyčejná věta zákaznice -> seznam akcí. aktualni(cast, klic) vrací platnou hodnotu části vzhledu.
    Akce: {"co": "uprava", "cast", "klic", "hodnota", "popis"} nebo {"co": "styl", "klic", "hodnota", "popis"}.
    Vrátí (akce, nepochopené kusy věty)."""
    akce, nepochopeno = [], []
    kusy = []
    for k in re.split(r"[,;]|\s+a\s+(?=\w)", veta):
        k = k.strip()
        if not k:
            continue
        if kusy and re.match(r"^(ale|jen|jenom|trochu|radši|radeji|raději)\b", _norm(k)):
            kusy[-1] += ", " + k        # „hook nahoru, ale jemně“ je jeden pokyn
        else:
            kusy.append(k)
    for kus in kusy:
        n = _norm(kus)
        pred = len(akce)
        o_nadpisech = any(w in n for w in ("nadpis", "hook", "titul nadpis"))
        o_hooku = "hook" in n
        o_titulcich = "titulk" in n
        barva = _barva_ve_vete(n)
        # hook / titulky nahoru, dolů, na hruď
        if o_hooku and any(w in n for w in ("nahoru", "nahore", "vys", "dolu", "dole", "niz")):
            smer = -1 if any(w in n for w in ("nahoru", "nahore", "vys")) else 1
            jemne = any(w in n for w in ("jemne", "trochu", "kousek", "malinko", "lehce", "o kousek"))
            posun = smer * POSUN_HOOKU["jemne" if jemne else "normalne"]
            akce.append({"co": "uprava", "cast": "hook", "klic": "posun_y", "hodnota": int(aktualni("hook", "posun_y") or 0) + posun,
                         "popis": "hook %s o %d px%s" % ("výš" if smer < 0 else "níž", abs(posun), " (jemně)" if jemne else "")})
        elif o_titulcich and any(w in n for w in ("nahoru", "nahore", "vys", "vedle hlavy")):
            for k, v in upravy_titulku_poloha("vedle").items():
                akce.append({"co": "uprava", "cast": "titulky", "klic": k, "hodnota": v, "popis": "titulky vedle hlavy"})
        elif o_titulcich and any(w in n for w in ("dolu", "dole", "niz")):
            for k, v in upravy_titulku_poloha("dole").items():
                akce.append({"co": "uprava", "cast": "titulky", "klic": k, "hodnota": v, "popis": "titulky dole"})
        elif any(w in n for w in ("na hrud", "mezi ruce", "na hrudi")):
            for k, v in upravy_titulku_poloha("hrud").items():
                akce.append({"co": "uprava", "cast": "titulky", "klic": k, "hodnota": v, "popis": "titulky na hrudi"})
        # po slovech / celé věty
        if any(w in n for w in ("po slovech", "po jednom slove", "jedno slovo", "slovo po slovu")):
            for k, v in upravy_titulku_rezim(vzhled, "slovo").items():
                akce.append({"co": "uprava", "cast": "titulky", "klic": k, "hodnota": v, "popis": "titulky po jednom slově"})
        elif any(w in n for w in ("cele vety", "celou vetu", "po vetach", "celych vet")):
            for k, v in upravy_titulku_rezim(vzhled, "veta").items():
                akce.append({"co": "uprava", "cast": "titulky", "klic": k, "hodnota": v, "popis": "titulky po celých větách"})
        # větší / menší
        if any(w in n for w in ("vetsi", "zvetsi", "vetsi pismo")) or any(w in n for w in ("mensi", "zmensi")):
            nasobek = ZMENA_VELIKOSTI if any(w in n for w in ("vetsi", "zvetsi")) else 1 / ZMENA_VELIKOSTI
            casti = [c for c in CASTI_NADPISU if _zaklad(vzhled, c)] if o_nadpisech else ["titulky"]
            for c in casti:
                z = aktualni(c, "velikost") or _zaklad(vzhled, c).get("velikost", 58)
                akce.append({"co": "uprava", "cast": c, "klic": "velikost", "hodnota": int(round(z * nasobek)),
                             "popis": "%s %s (%d → %d px)" % ("nadpis" if c != "titulky" else "titulky", "větší" if nasobek > 1 else "menší", z, int(round(z * nasobek)))})
        # barva: pozadí nadpisů, nadpisy, nebo titulky
        if barva and any(w in n for w in ("pozadi", "podklad", "karta", "kartu")):
            rgb = hex_na_rgb(barva)
            for c in [c for c in ("hook", "mini", "mini_silny") if _zaklad(vzhled, c)]:
                akce.append({"co": "uprava", "cast": c, "klic": "podklad", "hodnota": list(rgb) + [240], "popis": "podklad nadpisů %s" % barva})
                akce.append({"co": "uprava", "cast": c, "klic": "barva", "hodnota": [255, 255, 255] if _tmava(rgb) else [17, 17, 17],
                             "popis": "text nadpisů %s na podkladu" % ("bílý" if _tmava(rgb) else "tmavý")})
                akce.append({"co": "uprava", "cast": c, "klic": "stin", "hodnota": 0, "popis": "bez stínu (je podklad)"})
        elif barva and o_nadpisech:
            rgb = hex_na_rgb(barva)
            for c in [c for c in CASTI_NADPISU if _zaklad(vzhled, c) and c != "stitky"]:
                akce.append({"co": "uprava", "cast": c, "klic": "barva", "hodnota": list(rgb), "popis": "nadpisy %s" % barva})
                akce.append({"co": "uprava", "cast": c, "klic": "barva_zvyrazneni", "hodnota": list(rgb), "popis": "zvýraznění %s" % barva})
        elif barva and (o_titulcich or any(w in n for w in ("pismo", "text", "titulk")) or len(n.split()) <= 2):
            rgb = hex_na_rgb(barva)
            akce.append({"co": "uprava", "cast": "titulky", "klic": "barva", "hodnota": list(rgb), "popis": "titulky %s" % barva})
            if _tmava(rgb):
                akce.append({"co": "uprava", "cast": "titulky", "klic": "stin", "hodnota": 140, "popis": "světlá záře pod tmavým písmem"})
        # zvuky
        if any(w in n for w in ("bez zvuk", "zadne zvuky", "zadny zvuk", "vypni zvuk", "zvuky pryc", "zvuky vypnout")):
            akce.append({"co": "styl", "klic": "zvuky", "hodnota": [], "popis": "bez zvukových efektů"})
        elif any(w in n for w in ("zvuky zpatky", "zvuky zpet", "se zvuky", "zapni zvuk", "zvuky zapnout")):
            akce.append({"co": "styl", "klic": "zvuky", "hodnota": None, "popis": "zvuky zpátky (všechny, které prvky dávají)"})
        elif any(w in n for w in ("hlasitej", "nahlas", "silnej", "hlasiteji")):
            h = int(aktualni("_styl", "hlasitost") or 100)
            akce.append({"co": "styl", "klic": "hlasitost", "hodnota": min(200, h + 20), "popis": "zvuky hlasitěji (%d → %d %%)" % (h, min(200, h + 20))})
        elif any(w in n for w in ("tiseji", "tisej", "potichu", "slabsi", "ztlum")):
            h = int(aktualni("_styl", "hlasitost") or 100)
            akce.append({"co": "styl", "klic": "hlasitost", "hodnota": max(10, h - 20), "popis": "zvuky tišeji (%d → %d %%)" % (h, max(10, h - 20))})
        # písmo
        if "pismo" in n and any(w in n for w in ("zachovej", "zachovat", "nech", "moje", "me pismo", "neprepisuj")):
            akce.append({"co": "styl", "klic": "zachovat_pismo", "hodnota": True, "popis": "písmo zákaznice zůstává, kód stylu ho nepřepíše"})
        if len(akce) == pred:
            nepochopeno.append(kus)
    return akce, nepochopeno
