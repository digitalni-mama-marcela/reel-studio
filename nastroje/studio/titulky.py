"""Text na video kreslí náš kód. ffmpeg z Homebrew nemá textové filtry (OVĚŘENO 14. 10. 2026), proto se
titulky, nadpis a vsuvky kreslí v Pillow do průhledných snímků 1080x1920 a ffmpeg je jen položí na video.

Vzhled je daný slovníkem STYLY (písma jen s licencí OFL, složka balicek/pisma). Polohy nadpisu a vsuvek
se počítají tak, aby text nezakryl obličej (měření místním programem, viz poloha.py).
Bezpečné pásmo reelu: nic důležitého v horních 220 px a spodních 450 px (Marcela, 18. 10. 2026).
"""
import bisect
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIRKA, VYSKA, FPS = 1080, 1920, 30
HORNI_OKRAJ, DOLNI_OKRAJ, BOK = 220, 450, 70   # zóny podle Marcely 18. 10. 2026 (dřív 270 a 300)
from .cesty import PISMA  # noqa: E402

STYLY = {
    # Vzhled Serif: změřeno na reelu Marcely (screenshoty, odhad), písma Playfair Display a Instrument Serif
    "serif": {
        "titulky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "SemiBold", "velikost": 70, "velka": False,
                    "barva": (255, 255, 255), "ztlumene": 0.40, "spodek": VYSKA - DOLNI_OKRAJ - 20, "max_sirka": 880,
                    "max_slov": 5, "radku": 2, "radek": 1.18, "stin": 150, "obrys": 0, "zvyrazni": None},
        "hook": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 92, "barva": (255, 255, 255),
                 "radek": 1.08, "max_sirka": 900, "stin": 170, "obrys": 0, "podklad": None},
        "vsuvka": {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "velikost": 112,
                   "barva": (255, 255, 255), "akcent": (255, 214, 64), "naklon": 12, "stin": 160, "obrys": 0,
                   "podklad": None},
    },
    # Druhý vzhled na zkoušku: tučné bezpatkové písmo, aktuální slovo žluté, hook na světlém podkladu
    "plny": {
        "titulky": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 58, "velka": True,
                    "barva": (255, 255, 255), "ztlumene": 0.55, "spodek": VYSKA - DOLNI_OKRAJ - 20, "max_sirka": 900,
                    "max_slov": 4, "radku": 2, "radek": 1.22, "stin": 0, "obrys": 7,
                    "zvyrazni": (255, 205, 0)},
        "hook": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 66, "barva": (45, 32, 30),
                 "radek": 1.18, "max_sirka": 860, "stin": 0, "obrys": 0, "podklad": (246, 236, 226, 245)},
        "vsuvka": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 72,
                   "barva": (45, 32, 30), "akcent": (45, 32, 30), "naklon": -4, "stin": 0, "obrys": 0,
                   "podklad": (255, 205, 0, 255)},
    },
    # Vzhled podle webu klickrasy.cz (14. 10. 2026, OVĚŘENO z CSS a vzhledu stránky): písmo webu je Avenir Next
    # (komerční), proto volná náhrada Mulish. Barvy: prachová modrá #6D8AA1 (nadpisy a bannery), béžová #B3A49D,
    # téměř černá #0F0F0F, bílá. Nadpis na modrém podkladu, titulky malé uprostřed, celé věty bez zvýraznění.
    # Vzhled Vogue (Marcela 19. 10.: „ve stylu VOGUE, high-fashion, editorial“): černá a bílá, patkové kapitálky
    # (Playfair Display, blízké didonovým řezům módních časopisů), žádné barevné karty, černé štítky s bílým
    # bezpatkovým textem jako kicker, kurzíva Instrument Serif na vsuvky, obraz lehce odbarvený a kontrastní.
    "vogue": {
        # titulky (zadání 19. 10., oddíl 4): jeden řádek, 2 až 4 slova, ve výšce asi 70 % obrazu, zazněná slova bílá,
        # ostatní ztlumená, pod textem tmavý obdélník 85 % s malým zaoblením
        "titulky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Medium", "velikost": 66, "velka": False,
                    "barva": (255, 255, 255), "ztlumene": 0.40, "spodek": VYSKA - DOLNI_OKRAJ - 20, "stred_y": int(VYSKA * 0.70),
                    "max_sirka": 900, "max_slov": 4, "radku": 1, "radek": 1.14, "stin": 0, "obrys": 0, "zvyrazni": None,
                    "podklad": (10, 10, 10, 217), "podklad_pad": (33, 23), "podklad_radius": 8},
        # hook (oddíl 5): obří patkové verzálky za hlavou, řádek na 75 až 90 % šířky, těsné řádkování
        "hook": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 124, "barva": (255, 255, 255),
                 "radek": 0.92, "max_sirka": 980, "stin": 120, "obrys": 0, "podklad": None, "za_hlavou": True},
        # karty slov (hook po frázích, oddíl 2 a 5): celá obrazovka černá, obří slova za hlavou, každá fráze jiný řez
        "karticky": {"za_hlavou": True},
        "orbit": {"radius": 6, "barva_ramu": (255, 255, 255)},
        "mrizka": {"okraj": (255, 255, 255), "rohy": 0, "ztmaveni": (10, 10, 10), "barva": (255, 255, 255), "varianta": "Medium"},
        "nalepky": {"podklad": (255, 255, 255), "barva": (10, 10, 10), "skrt_barva": (255, 255, 255), "skrt_cara": (255, 255, 255),
                    "skrt_podklad": (10, 10, 10, 230), "rohy": 0},
        "karty_slov": {"barva": (255, 255, 255), "barva_zvyrazneni": (255, 255, 255), "ztmaveni": (10, 10, 10), "ztmavit": 1.0,
                       "stin": 0, "velikost": 190, "min_velikost": 90, "max_sirka": SIRKA - 2 * 60, "radek": 0.92, "za_hlavou": True},
        "mini": {"pismo": "Montserrat-wght.ttf", "varianta": "Medium", "velikost": 38, "barva": (255, 255, 255),
                 "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 1.2, "max_sirka": 780,
                 "podklad": (0, 0, 0, 235), "podklad_pad": (30, 18), "podklad_radius": 0},
        "mini_nahore": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 84, "barva": (255, 255, 255),
                        "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 0.96, "max_sirka": 980,
                        "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.6, "stin_posun": 6, "za_hlavou": True},
        "slovo_velke": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 250, "barva": (255, 255, 255),
                        "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 1.0, "max_sirka": 1040,
                        "podklad": None, "podklad_pad": (20, 10), "stin": 16, "stin_sila": 0.6, "stin_posun": 8, "za_hlavou": True},
        "mini_silny": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 60, "barva": (255, 255, 255),
                       "barva_zvyrazneni": (0, 0, 0), "marker": (255, 255, 255, 235), "radek": 1.18,
                       "max_sirka": 900, "podklad": (0, 0, 0, 240), "podklad_pad": (44, 30), "podklad_radius": 0},
        "vsuvka": {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "velikost": 112,
                   "barva": (255, 255, 255), "akcent": (255, 255, 255), "naklon": 10, "stin": 170, "obrys": 0,
                   "podklad": None},
        # štítky (REEL / CAROUSEL / NEWSLETTER, Marcela 21. 10.): černé pilulky s bílými patkovými verzálkami
        "stitky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 64, "min_velikost": 44, "velka": True,
                   "barva": (255, 255, 255), "podklad": (0, 0, 0), "pad": (40, 18), "mezera": 24, "mezera_svisle": 18,
                   "max_sirka": 900, "stin": 90},
        "vlozka": {"barva_okraje": (255, 255, 255), "radius": 0, "okraj": 4, "stin_barva": (0, 0, 0, 130),
                   "pilulka_podklad": (0, 0, 0, 238), "pilulka_barva": (255, 255, 255), "kapitola_barva": (210, 210, 210),
                   "pilulka_pismo": "Montserrat-wght.ttf", "pilulka_varianta": "Medium", "pilulka_velikost": 32},
        "filtr": None,     # bez barevného filtru (Marcela 19. a 20. 10.: žádné ztmavení ani nádech)
    },
    # Vzhled Marcela: paleta značky Digitální Máma Marcela (krém #FBF6EF, švestková #4A3340, pudrově růžová #D48BA0,
    # blush #F5D6D9, olivová #CED4AC), písma Playfair Display (nadpisy) a Montserrat (text). Ženský, klidný, editoriální.
    "marcela": {
        "titulky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "SemiBold", "velikost": 70, "velka": False,
                    "barva": (255, 255, 255), "ztlumene": 0.40, "spodek": VYSKA - DOLNI_OKRAJ - 20, "max_sirka": 880,
                    "max_slov": 5, "radku": 2, "radek": 1.18, "stin": 150, "obrys": 0, "zvyrazni": None},
        "hook": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 92, "barva": (74, 51, 64),
                 "radek": 1.14, "max_sirka": 880, "stin": 0, "obrys": 0, "podklad": (251, 246, 239, 242),
                 "podklad_pad": (46, 30), "podklad_radius": 38, "marker": (212, 139, 160, 235),
                 "barva_zvyrazneni": (251, 246, 239)},
        "mini": {"pismo": "Montserrat-wght.ttf", "varianta": "Bold", "velikost": 46, "barva": (74, 51, 64),
                 "barva_zvyrazneni": (74, 51, 64), "marker": (245, 214, 217, 240), "radek": 1.22, "max_sirka": 780,
                 "podklad": (251, 246, 239, 240), "podklad_pad": (34, 22), "podklad_radius": 28},
        "orbit": {"radius": 20, "barva_ramu": (251, 246, 239)},
        # nadpis nad hlavou (když se nevejde pod bradu): bílé tučné bezpatkové písmo se stínem, bez karty, na dva řádky
        "mini_nahore": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 64, "barva": (255, 255, 255),
                        "barva_zvyrazneni": (212, 139, 160), "marker": (0, 0, 0, 0), "radek": 1.12, "max_sirka": 940,
                        "podklad": None, "podklad_pad": (16, 10), "stin": 10, "stin_sila": 0.6, "stin_posun": 6},
        # jedno velké slovo (NADPIS) jako titulek z časopisu: patkové kapitálky, bílé, se stínem
        "slovo_velke": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 150, "barva": (255, 255, 255),
                        "barva_zvyrazneni": (212, 139, 160), "marker": (0, 0, 0, 0), "radek": 1.0, "max_sirka": 1000,
                        "podklad": None, "podklad_pad": (20, 10), "stin": 14, "stin_sila": 0.6, "stin_posun": 8},
        "mini_silny": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 62, "barva": (251, 246, 239),
                       "barva_zvyrazneni": (74, 51, 64), "marker": (212, 139, 160, 240), "radek": 1.18,
                       "max_sirka": 880, "podklad": (74, 51, 64, 242), "podklad_pad": (42, 28), "podklad_radius": 34},
        "vsuvka": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 72,
                   "barva": (74, 51, 64), "akcent": (212, 139, 160), "naklon": -3, "stin": 0, "obrys": 0,
                   "podklad": (251, 246, 239, 240)},
        # štítky (REEL / CAROUSEL / NEWSLETTER, Marcela 21. 10.): pilulky v pudrově růžové značky (marker z mini_silny)
        # s bílým tučným bezpatkovým textem (písmo jako mini)
        "stitky": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 64, "min_velikost": 44, "velka": True,
                   "barva": (255, 255, 255), "podklad": (212, 139, 160), "pad": (40, 18), "mezera": 24, "mezera_svisle": 18,
                   "max_sirka": 900, "stin": 90},
        # jemný teplý nádech obrazu (ffmpeg), NÁVRH: teplota 5900 K, sytost 0,95, lehká vinětace
        "filtr": "colortemperature=temperature=5900,eq=contrast=1.03:saturation=0.95,vignette=angle=PI/5",
    },
    "klickrasy": {
        "titulky": {"pismo": "Mulish-wght.ttf", "varianta": "SemiBold", "velikost": 50, "velka": False,
                    "barva": (255, 255, 255), "ztlumene": 1.0, "po_slovech": False, "stred_y": 1090, "max_sirka": 800,
                    "max_slov": 7, "radku": 2, "radek": 1.22, "stin": 190, "obrys": 0, "zvyrazni": None},
        "hook": {"pismo": "Mulish-wght.ttf", "varianta": "ExtraBold", "velikost": 76, "barva": (255, 255, 255),
                 "radek": 1.16, "max_sirka": 860, "stin": 0, "obrys": 0, "podklad": (109, 138, 161, 238),
                 "podklad_pad": (46, 30), "podklad_radius": 38, "marker": (179, 164, 157, 240),
                 "barva_zvyrazneni": (15, 15, 15)},
        # krátké nadpisy v průběhu videa: bílá karta s tmavým textem, nejsilnější místo má styl "mini_silny" (jako nadpis)
        "mini": {"pismo": "Mulish-wght.ttf", "varianta": "Bold", "velikost": 46, "barva": (15, 15, 15),
                 "barva_zvyrazneni": (15, 15, 15), "marker": (179, 164, 157, 235), "radek": 1.22, "max_sirka": 760,
                 "podklad": (255, 255, 255, 244), "podklad_pad": (34, 22), "podklad_radius": 28},
        "mini_silny": {"pismo": "Mulish-wght.ttf", "varianta": "ExtraBold", "velikost": 64, "barva": (255, 255, 255),
                       "barva_zvyrazneni": (15, 15, 15), "marker": (179, 164, 157, 240), "radek": 1.18,
                       "max_sirka": 860, "podklad": (109, 138, 161, 238), "podklad_pad": (40, 26), "podklad_radius": 34},
        "vsuvka": {"pismo": "Mulish-wght.ttf", "varianta": "ExtraBold", "velikost": 64,
                   "barva": (255, 255, 255), "akcent": (255, 255, 255), "naklon": -4, "stin": 0, "obrys": 0,
                   "podklad": (179, 164, 157, 240)},
    },
    # Vzhled Zápisník a čísla (zadání Marcely 29. 10. 2026):
    # titulky po jednom slovu, malé bílé patkové, vedle hlavy na volnější straně; nadpisy a čísla tučné bezpatkové
    # krémové bez karty (druhý řádek kurzívou přes spec["radky_styl"]), zápisník s odškrtáváním, bez filtru
    "zapisnik": {
        "titulky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Regular", "velikost": 58, "velka": False,
                    "barva": (255, 255, 255), "ztlumene": 1.0, "po_slovech": False, "spodek": VYSKA - DOLNI_OKRAJ - 20,
                    "max_sirka": 600, "max_slov": 1, "radku": 1, "radek": 1.1, "stin": 255, "obrys": 0, "zvyrazni": None,
                    "vedle_hlavy": True,
                    "poloha": "hrud"},   # Marcela 29. 10.: doprostřed mezi ruce, ne k pravé liště Instagramu
        "hook": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 84, "barva": (246, 235, 208),
                 "radek": 1.05, "max_sirka": 940, "stin": 120, "obrys": 0, "podklad": None},
        "mini": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 72, "barva": (246, 235, 208),
                 "barva_zvyrazneni": (246, 235, 208), "marker": (0, 0, 0, 0), "radek": 1.08, "max_sirka": 960,
                 "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.95, "stin_posun": 5},
        # nadpisy čísel nad hlavou jako ve vzoru: nahoře, hlava je smí zčásti zakrýt (maska osoby)
        "mini_nahore": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 72, "barva": (246, 235, 208),
                        "barva_zvyrazneni": (246, 235, 208), "marker": (0, 0, 0, 0), "radek": 1.08, "max_sirka": 960,
                        "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.95, "stin_posun": 5,
                        "za_hlavou": True, "stred_nad_hlavou": True},
        # výzva do komentáře bez karty, stejné písmo jako nadpisy
        "mini_silny": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 70, "barva": (246, 235, 208),
                       "barva_zvyrazneni": (246, 235, 208), "marker": (0, 0, 0, 0), "radek": 1.1, "max_sirka": 940,
                       "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.95, "stin_posun": 5},
        "vsuvka": {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "velikost": 70,
                   "barva": (255, 255, 255), "akcent": (246, 235, 208), "naklon": 0, "stin": 120, "obrys": 0,
                   "podklad": None},
        "zapisnik": {"velikost": 50, "sirka": 760, "za_hlavou": True, "y": 256},
        # Marcela 29. 10.: zápisník za hlavou (obličej vždy vpředu), velikost nechat
        # řada náhledů vlastních reelů nahoře za hlavou jako ve vzoru
        "karticky": {"za_hlavou": True},
        # malý řádek nadpisu (obsah „*ČÍSLO* / podpis“ v plánu) kurzívou místo bezpatkového
        "mini_podpis": {"pomer": 0.75, "pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "psani": True},
        "filtr": None,
    },
    # Vzhled Jedno slovo (zadání Marcely 2. 11. 2026):
    # celé video bez nadpisů a karet, jen titulky po jednom slově, velké teplé žluté patkové písmo uprostřed na hrudi
    # (na kolenou), slovo naskočí bez animace; obraz se celé video pomalu přibližuje (najezd, zoom.plan_najezd)
    "jedno_slovo": {
        "titulky": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Medium", "velikost": 150, "velka": False,
                    "puvodni_pismena": True, "barva": (250, 204, 21), "ztlumene": 1.0, "po_slovech": False,
                    "spodek": VYSKA - DOLNI_OKRAJ - 20, "max_sirka": 960, "max_slov": 1, "radku": 1, "radek": 1.1,
                    "stin": 140, "obrys": 0, "zvyrazni": None, "vedle_hlavy": True, "poloha": "hrud"},  # stín: žlutá na bílém svetru bez něj nečitelná (2. 11.)
        # nadpisy nad hlavou (2. 11., Marcela: „nad mojí hlavou je prostor“): bílé patkové verzálky, zvýraznění žluté
        # jako titulky, za hlavou (hlava smí zakrýt spodek písmen), uprostřed mezi horním okrajem a temenem
        "mini_nahore": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Bold", "velikost": 92, "barva": (255, 255, 255),
                        "barva_zvyrazneni": (250, 204, 21), "marker": (0, 0, 0, 0), "radek": 1.0, "max_sirka": 960,
                        "podklad": None, "podklad_pad": (16, 10), "stin": 14, "stin_sila": 0.75, "stin_posun": 5,
                        "za_hlavou": True, "stred_nad_hlavou": True},
        "mini_podpis": {"pomer": 0.85, "pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "psani": True,
                        "barva": (250, 204, 21)},
        "nalepky": {"skrt_velikost": 84, "skrt_podklad": (20, 20, 20, 225), "skrt_barva": (250, 204, 21), "skrt_cara": (230, 57, 43)},
        "najezd": (1.0, 1.12),   # přiblížení od začátku do konce reelu (ve vzoru asi o 10 až 12 %, ODHAD ze snímků)
        "filtr": None,
    },
    # Vzhled Zelený editor (zadání Marcely 3. 11. 2026):
    # tmavě zelená, krémová a bílá. Titulky malé patkové v zeleném obdélníku, 2 až 4 slova, zazněná slova bílá,
    # další ztlumená. Hook po frázích za hlavou na plné zelené ploše, každá fráze jiný řez (karty_slov), velké
    # nadpisy patkovými verzálkami za hlavou, zpráva pro Clauda v bílé kapsli, posuvník před a po (prvek pred_po).
    "zeleny_editor": {
        "titulky": {"pismo": "InstrumentSerif-Regular.ttf", "varianta": None, "velikost": 70, "velka": False,
                    "puvodni_pismena": True, "barva": (255, 255, 255), "ztlumene": 0.45, "spodek": VYSKA - DOLNI_OKRAJ - 20, "stred_y": int(VYSKA * 0.70),
                    "max_sirka": 860, "max_slov": 4, "radku": 1, "radek": 1.12, "stin": 0, "obrys": 0, "zvyrazni": None,
                    "podklad": (22, 48, 38, 226), "podklad_pad": (26, 14), "podklad_radius": 4},
        "hook": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Medium", "velikost": 132, "barva": (243, 235, 221),
                 "radek": 0.92, "max_sirka": 980, "stin": 60, "obrys": 0, "podklad": None, "za_hlavou": True},
        # úvod po frázích: zelená plocha za osobou (ztmavit 1.0 = pozadí celé zelené), patkové / bezpatkové / kurzíva
        "karty_slov": {"barva": (243, 235, 221), "barva_zvyrazneni": (255, 255, 255), "ztmaveni": (22, 48, 38), "ztmavit": 1.0,
                       "stin": 0, "velikost": 200, "min_velikost": 90, "max_sirka": SIRKA - 2 * 60, "radek": 0.92, "za_hlavou": True},
        "karticky": {"za_hlavou": True},
        "mini": {"pismo": "Montserrat-wght.ttf", "varianta": "Medium", "velikost": 38, "barva": (255, 255, 255),
                 "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 1.2, "max_sirka": 780,
                 "podklad": (22, 48, 38, 235), "podklad_pad": (30, 18), "podklad_radius": 6},
        # velké slovo za hlavou (NEVER, CLAUDE), nad ním malý řádek bezpatkovým písmem
        "mini_nahore": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Medium", "velikost": 150, "barva": (243, 235, 221),
                        "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 0.95, "max_sirka": 1000,
                        "podklad": None, "podklad_pad": (16, 10), "stin": 10, "stin_sila": 0.5, "stin_posun": 4,
                        "za_hlavou": True, "stred_nad_hlavou": True},
        "mini_podpis": {"pomer": 0.6, "pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "psani": True,
                        "barva": (243, 235, 221)},
        "slovo_velke": {"pismo": "PlayfairDisplay-wght.ttf", "varianta": "Medium", "velikost": 240, "barva": (243, 235, 221),
                        "barva_zvyrazneni": (255, 255, 255), "marker": (0, 0, 0, 0), "radek": 1.0, "max_sirka": 1040,
                        "podklad": None, "podklad_pad": (20, 10), "stin": 12, "stin_sila": 0.5, "stin_posun": 6, "za_hlavou": True},
        # nadpis v zeleném rámečku (BIGGER / captions.): tučné bezpatkové verzálky, druhý řádek kurzívou (mini_podpis)
        "mini_silny": {"pismo": "Montserrat-wght.ttf", "varianta": "ExtraBold", "velikost": 76, "barva": (255, 255, 255),
                       "barva_zvyrazneni": (243, 235, 221), "marker": (0, 0, 0, 0), "radek": 1.1,
                       "max_sirka": 900, "podklad": (22, 48, 38, 240), "podklad_pad": (34, 20), "podklad_radius": 4},
        "zprava": {"barva": (30, 30, 30), "podklad": (255, 255, 255)},
        "nalepky": {"skrt_podklad": (22, 48, 38, 230), "skrt_barva": (255, 255, 255), "skrt_cara": (230, 57, 43)},
        "vlozka": {"barva_okraje": (243, 235, 221), "radius": 18, "okraj": 3, "stin_barva": (0, 0, 0, 130),
                   "pilulka_podklad": (22, 48, 38, 238), "pilulka_barva": (255, 255, 255), "kapitola_barva": (243, 235, 221),
                   "pilulka_pismo": "InstrumentSerif-Regular.ttf", "pilulka_varianta": None, "pilulka_velikost": 40},
        "orbit": {"radius": 18, "barva_ramu": (243, 235, 221)},
        "mrizka": {"okraj": (243, 235, 221), "ztmaveni": (22, 48, 38)},
        "pred_po": {"podklad": (22, 48, 38, 200)},
        "filtr": None,
    },
}


# Vzhled Slovo a kurzíva (zadání Marcely 3. 11. 2026):
# titulky po jednom slově bílým bezpatkovým písmem uprostřed na hrudi, důležitá slova (konec věty) větší žlutou patkovou
# kurzívou. Hook se skládá po řádcích za hlavou (skladany_nadpis), nadpisy nahoře bílé, zvýraznění žlutou kurzívou.
# Ostatní prvky (roj karet, složka, pás karet, ruční poznámka, karta vzhledu) za osobou.
_ZLUTA = (247, 210, 84)   # sytější než ve vzhledu: na světlé zdi bledá žlutá zanikala (zkouška 3. 11.)
STYLY["slovo_a_kurziva"] = {
    "titulky": {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 88, "velka": False,
                "puvodni_pismena": True, "barva": (255, 255, 255), "ztlumene": 1.0, "po_slovech": False,
                "spodek": VYSKA - DOLNI_OKRAJ - 20, "max_sirka": 900, "max_slov": 1, "radku": 1, "radek": 1.1,
                "stin": 150, "obrys": 0, "zvyrazni": None, "vedle_hlavy": True, "poloha": "hrud",
                "klicove": {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "barva": _ZLUTA, "pomer": 1.35, "auto": True,
                            "stin": 230}},
    "hook": {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 92, "barva": (255, 255, 255),
             "radek": 1.02, "max_sirka": 960, "stin": 110, "obrys": 0, "podklad": None, "za_hlavou": True},
    "skladany_nadpis": {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 118, "stin": 170, "barva": (255, 255, 255),
                        "pismo_kurziva": "InstrumentSerif-Italic.ttf", "barva_kurziva": _ZLUTA, "pomer_kurziva": 1.22},
    "mini": {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 54, "barva": (255, 255, 255),
             "barva_zvyrazneni": _ZLUTA, "marker": (0, 0, 0, 0), "radek": 1.1, "max_sirka": 900,
             "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.8, "stin_posun": 4},
    "mini_nahore": {"pismo": "Inter-wght.ttf", "varianta": "SemiBold", "velikost": 88, "barva": (255, 255, 255),
                    "barva_zvyrazneni": _ZLUTA, "marker": (0, 0, 0, 0), "radek": 1.02, "max_sirka": 960,
                    "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.8, "stin_posun": 4,
                    "za_hlavou": True, "stred_nad_hlavou": True},
    "mini_podpis": {"pomer": 1.2, "pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "psani": False, "barva": _ZLUTA},
    "mini_silny": {"pismo": "Inter-wght.ttf", "varianta": "Bold", "velikost": 70, "barva": (255, 255, 255),
                   "barva_zvyrazneni": _ZLUTA, "marker": (0, 0, 0, 0), "radek": 1.1, "max_sirka": 940,
                   "podklad": None, "podklad_pad": (16, 10), "stin": 12, "stin_sila": 0.9, "stin_posun": 5},
    "vsuvka": {"pismo": "InstrumentSerif-Italic.ttf", "varianta": None, "velikost": 70,
               "barva": (255, 255, 255), "akcent": _ZLUTA, "naklon": 0, "stin": 120, "obrys": 0, "podklad": None},
    "karticky": {"za_hlavou": True},
    "zprava": {"barva": (30, 30, 30), "podklad": (255, 255, 255)},
    "filtr": None,
}


def _prebarvi(hodnota, z, na):
    """Kopie části vzhledu, kde barva z (RGB, i s průhledností) je nahrazená barvou na."""
    if isinstance(hodnota, dict):
        return {k: _prebarvi(v, z, na) for k, v in hodnota.items()}
    if isinstance(hodnota, tuple) and len(hodnota) in (3, 4) and tuple(hodnota[:3]) == z:
        return tuple(na) + tuple(hodnota[3:])
    return hodnota


# Švestkový editor (Marcela 3. 11. 2026): Zelený editor v barvě její značky, švestková #4A3340 místo tmavě zelené
STYLY["svestkovy_editor"] = _prebarvi(STYLY["zeleny_editor"], (22, 48, 38), (74, 51, 64))
# běžící čas pod úvodem jako ve vzhledu (3. 11. 2026): psací písmo, tlumené nuly, sekundy jasné, snímky zlatavé
STYLY["svestkovy_editor"]["casomira"] = {"pismo": "CourierPrime-Regular.ttf", "varianta": None, "velikost": 58, "alfa": 240, "alfa_nul": 120,
                                         "barva": (251, 246, 239), "barva_snimku": (233, 200, 130), "zarovnani": "stred",
                                         "mezera": 24}

# Starší vzhledy (serif, plny, klickrasy) nemají všechny části (mikro-nadpis, karta výzvy, velké slovo, nadpis nad
# hlavou, karty slov): chybějící část se vezme ze vzhledu „marcela“, ať jde každý vzhled použít na celý reel.
for _nazev, _st in STYLY.items():
    if _nazev != "marcela":
        for _k, _v in STYLY["marcela"].items():
            if _k not in _st:
                _st[_k] = _v
            elif isinstance(_v, dict) and isinstance(_st[_k], dict):
                for _kk, _vv in _v.items():            # i klíče uvnitř části (marker, barva_zvyrazneni, podklad_pad…)
                    _st[_k].setdefault(_kk, _vv)

import copy as _copy  # noqa: E402
ZAKLAD = _copy.deepcopy(STYLY)     # vzhledy, jak je studio dodává (před pouzij_upravy); čte je styl.py pro „o 15 % větší“ a procenta


def pouzij_upravy(upravy):
    """Stálé úpravy zákaznice přes vzhledy: {vzhled: {část: {klíč: hodnota}}}. Seznamy z JSON se berou jako n-tice
    (barvy). Část, která ve vzhledu není, se založí z kopie části vzhledu marcela. Vrátí počet změn."""
    n = 0
    for vzhled, casti in (upravy or {}).items():
        if vzhled not in STYLY:
            continue
        for cast, hodnoty in (casti or {}).items():
            if cast == "filtr":
                STYLY[vzhled]["filtr"] = hodnoty or None
                n += 1
                continue
            if cast not in STYLY[vzhled]:
                STYLY[vzhled][cast] = dict(STYLY["marcela"].get(cast, {}))
            for k, v in (hodnoty or {}).items():
                STYLY[vzhled][cast][k] = tuple(v) if isinstance(v, list) else v
                n += 1
    return n


def kombinace(vzhled, titulky_z=None):
    """Vzhled s titulky z jiného vzhledu (volba studentky na stránce stylů). Zaregistruje a vrátí název."""
    if not titulky_z or titulky_z == vzhled:
        return vzhled
    nazev = "%s+titulky:%s" % (vzhled, titulky_z)
    if nazev not in STYLY:
        STYLY[nazev] = dict(STYLY[vzhled], titulky=STYLY[titulky_z]["titulky"])
    return nazev


@lru_cache(maxsize=None)
def pismo(soubor, velikost, varianta=None):
    f = ImageFont.truetype(str(PISMA / soubor), velikost)
    if varianta:
        f.set_variation_by_name(varianta)
    return f


# Písma na výběr na stránce stylů (všechna OFL 1.1, staženo z github.com/google/fonts 2. 11. 2026, čeština ověřená).
# Název ze stránky -> (soubor, varianta) pro nadpisy a pro titulky.
PISMA_NA_VYBER = {
    "Montserrat": {"nadpis": ("Montserrat-wght.ttf", "ExtraBold"), "titulky": ("Montserrat-wght.ttf", "Medium")},
    "Playfair Display": {"nadpis": ("PlayfairDisplay-wght.ttf", "Bold"), "titulky": ("PlayfairDisplay-wght.ttf", "Medium")},
    "Instrument Serif": {"nadpis": ("InstrumentSerif-Italic.ttf", None), "titulky": ("InstrumentSerif-Italic.ttf", None)},
    "Mulish": {"nadpis": ("Mulish-wght.ttf", "ExtraBold"), "titulky": ("Mulish-wght.ttf", "Medium")},
    "Bodoni Moda": {"nadpis": ("BodoniModa-wght.ttf", "Bold"), "titulky": ("BodoniModa-wght.ttf", "Medium")},
    "DM Serif Display": {"nadpis": ("DMSerifDisplay-Regular.ttf", None), "titulky": ("DMSerifDisplay-Regular.ttf", None)},
    "Fraunces": {"nadpis": ("Fraunces-wght.ttf", "Bold"), "titulky": ("Fraunces-wght.ttf", "Regular")},
    "Inter": {"nadpis": ("Inter-wght.ttf", "ExtraBold"), "titulky": ("Inter-wght.ttf", "Medium")},
    "DM Sans": {"nadpis": ("DMSans-wght.ttf", "ExtraBold"), "titulky": ("DMSans-wght.ttf", "Medium")},
    "Courier Prime": {"nadpis": ("CourierPrime-Bold.ttf", None), "titulky": ("CourierPrime-Regular.ttf", None)},
}
CASTI_NADPISU = ("hook", "mini", "mini_nahore", "mini_silny", "slovo_velke", "stitky")


def upravy_pisma(vzhled, nadpis=None, titulky=None):
    """Volba písma ze stránky stylů jako úpravy pro pouzij_upravy: {vzhled: {část: {pismo, varianta}}}."""
    casti = {}
    for nazev, kam in ((nadpis, CASTI_NADPISU), (titulky, ("titulky",))):
        if not nazev:
            continue
        if nazev not in PISMA_NA_VYBER:
            raise ValueError("Písmo %s ve studiu není. Na výběr: %s." % (nazev, ", ".join(PISMA_NA_VYBER)))
        soubor, varianta = PISMA_NA_VYBER[nazev]["titulky" if kam == ("titulky",) else "nadpis"]
        for cast in kam:
            if cast in STYLY.get(vzhled, {}):
                casti[cast] = {"pismo": soubor, "varianta": varianta}
    return {vzhled: casti}


def zobraz(w, styl):
    """Text slova na obrazovce: bez interpunkce na okrajích (kromě ? a !), velikost podle stylu."""
    t = re.sub(r"^[\"„“”'(\[]+|[\"„“”')\]]+$", "", w.strip())
    t = re.sub(r"[.,;:…]+$", "", t)
    t = re.sub(r"(?<=\d)-(?=\d)", "–", t)
    if styl["velka"]:
        return t.upper()
    if styl.get("puvodni_pismena"):      # jak zaznělo v přepisu (Claude, CapCutu), vzhled jedno_slovo
        return t
    return t if re.match(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,}", t) else t.lower()


def rozdel(sirky, mezera, max_sirka):
    """Rozdělí slova na řádky. Vrátí počty slov na řádku, nejdřív zkusí co nejvyváženější dva řádky."""
    n = len(sirky)

    def delka(a, b):
        return sum(sirky[a:b]) + mezera * (b - a - 1)

    if delka(0, n) <= max_sirka:
        return [n]
    nej = None
    for k in range(1, n):
        m = max(delka(0, k), delka(k, n))
        if m <= max_sirka and (nej is None or m < nej[0]):
            nej = (m, k)
    if nej:
        return [nej[1], n - nej[1]]
    radky, i = [], 0
    while i < n:
        j = i + 1
        while j < n and delka(i, j + 1) <= max_sirka:
            j += 1
        radky.append(j - i)
        i = j
    return radky


def barva_stinu(barva, styl=None):
    """Tmavé písmo (černá, tmavě modrá) dostane světlou záři místo černého stínu, jinak by nebylo čitelné."""
    if styl and styl.get("stin_barva"):
        return tuple(styl["stin_barva"][:3])
    if barva and 0.2126 * barva[0] + 0.7152 * barva[1] + 0.0722 * barva[2] < 90:
        return (255, 255, 255)
    return (0, 0, 0)


def _vrstva_s_textem(velikost_plochy, polozky, styl, font, alfa=1.0):
    """polozky: (x, y, text, barva RGB, průhlednost 0..1). Vrátí RGBA obrázek se stínem a obrysem."""
    w, h = velikost_plochy
    text = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(text)
    stin = Image.new("L", (w, h), 0)
    ds = ImageDraw.Draw(stin)
    for x, y, t, barva, pr in polozky:
        a = int(255 * pr * alfa)
        if styl.get("obrys"):
            d.text((x, y), t, font=font, fill=barva + (a,), stroke_width=styl["obrys"], stroke_fill=(15, 12, 12, a))
        else:
            d.text((x, y), t, font=font, fill=barva + (a,))
        if styl.get("stin"):
            ds.text((x + 2, y + 5), t, font=font, fill=int(styl["stin"] * pr * alfa))
    if styl.get("stin"):
        stin = stin.filter(ImageFilter.GaussianBlur(7))
        podklad = Image.new("RGBA", (w, h), barva_stinu(polozky[0][3] if polozky else None, styl) + (0,))
        podklad.putalpha(stin)
        podklad.alpha_composite(text)
        return podklad
    return text


def blok_textu(slova, font, styl, max_sirka):
    """Rozloží slova do řádků. Vrátí (řádky se slovy a šířkami, šířky, mezera, šířka bloku, výška bloku, výška řádku)."""
    sirky = [font.getlength(s) for s in slova]
    mezera = font.getlength(" ")
    radky_n = rozdel(sirky, mezera, max_sirka)
    asc, desc = font.getmetrics()
    vyska_radku = int((asc + desc) * styl.get("radek", 1.1))
    radky, i = [], 0
    for n in radky_n:
        idx = list(range(i, i + n))
        radky.append({"idx": idx, "sirka": sum(sirky[j] for j in idx) + mezera * (n - 1)})
        i += n
    return radky, sirky, mezera, max(r["sirka"] for r in radky), vyska_radku * len(radky), vyska_radku


def je_klicove(w, styl):
    """Důležité slovo: v plánu označené (slovo["klic"]), jinak podle vzhledu poslední slovo věty (tečka, vykřičník)
    s aspoň 4 písmeny. Ve slovech s otazníkem zůstává bílé."""
    if not isinstance(w, dict):
        return False
    if "klic" in w:
        return bool(w["klic"])
    k = styl.get("klicove") or {}
    hole = re.sub(r"[^\w]", "", w["w"])
    return bool(k.get("auto", True) and re.search(r"[.!]$", w["w"]) and len(hole) >= 4)


def vykresli_titulky(slova_strany, k_zni, styl, stred=None):
    """Jedna stránka titulků. k_zni = kolik slov už zaznělo (včetně právě znějícího). Vrátí (obrázek, (x, y), obdélník textu).
    stred = (x, y) středu textu, když stránka nestojí uprostřed šířky (titulky vedle hlavy, umisteni.titulky_vedle_hlavy)."""
    if styl.get("klicove") and slova_strany and all(je_klicove(w, styl) for w in slova_strany):
        # vzhled Slovo a kurzíva (3. 11. 2026): důležité slovo jiným písmem a barvou (patková kurzíva, žlutá)
        k = styl["klicove"]
        styl = dict(styl, pismo=k["pismo"], varianta=k.get("varianta"), barva=tuple(k["barva"]),
                    velikost=int(styl["velikost"] * k.get("pomer", 1.3)), max_sirka=int(styl["max_sirka"] * k.get("pomer", 1.3)),
                    stin=k.get("stin", styl.get("stin")))
    font = pismo(styl["pismo"], styl["velikost"], styl["varianta"])
    texty = [zobraz(w["w"] if isinstance(w, dict) else w, styl) for w in slova_strany]
    radky, sirky, mezera, sb, vb, vr = blok_textu(texty, font, styl, styl["max_sirka"])
    pad = 40
    plocha = (int(sb) + 2 * pad, int(vb) + 2 * pad)
    polozky = []
    y = pad
    for r in radky:
        x = pad + (sb - r["sirka"]) / 2
        for j in r["idx"]:
            if j < k_zni - 1 or (j == k_zni - 1 and not styl["zvyrazni"]):
                barva, pr = styl["barva"], 1.0
            elif j == k_zni - 1:
                barva, pr = styl["zvyrazni"], 1.0
            else:
                barva, pr = styl["barva"], styl["ztlumene"]
            polozky.append((x, y, texty[j], barva, pr))
            x += sirky[j] + mezera
        y += vr
    img = _vrstva_s_textem(plocha, polozky, styl, font)
    if styl.get("podklad"):
        # pilulka pod titulky (vzhled Marcela): zaoblený obdélník kolem bloku textu
        px, py = styl.get("podklad_pad", (34, 18))
        p = Image.new("RGBA", plocha, (0, 0, 0, 0))
        ImageDraw.Draw(p).rounded_rectangle((pad - px, pad - py, pad + sb + px, pad + vb + py),
                                            radius=styl.get("podklad_radius", 30), fill=styl["podklad"])
        p.alpha_composite(img)
        img = p
    x0 = int((SIRKA - plocha[0]) / 2)
    if stred:
        x0, y0 = int(stred[0] - plocha[0] / 2), int(stred[1] - vb / 2 - pad)
    elif styl.get("stred_y"):
        y0 = int(styl["stred_y"] - vb / 2 - pad)
    else:
        y0 = int(styl["spodek"] - vb - pad)
    return img, (x0, y0), (x0 + pad, y0 + pad, x0 + pad + int(sb), y0 + pad + int(vb))


def vykresli_casomiru(spec, styl, snimek):
    """Drobný tikající údaj pod hookem ve tvaru 00:00:01:10 (hodiny:minuty:sekundy:snímky), zarovnaný doleva
    na 20 % šířky (zadání Marcely 19. 10., oddíl 5). Vrátí (obrázek, (x, y), obdélník).
    Volitelně ve stylu: "zarovnani": "stred"; "barva_snimku": barva posledních dvou číslic; "alfa_nul": průhlednost
    úvodních nul (3. 11. 2026, reel „ani sekundu“: nuly tlumené, sekundy jasné, snímky barevné)."""
    s = snimek // FPS
    text = "%02d:%02d:%02d:%02d" % (s // 3600, (s // 60) % 60, s % 60, snimek % FPS)
    font = pismo(styl.get("pismo", "Montserrat-wght.ttf"), styl.get("velikost", 30), styl.get("varianta", "Medium"))
    alfa = styl.get("alfa", 170)
    barva = tuple(styl.get("barva", (255, 255, 255)))
    w = int(font.getlength("00:00:00:00")) + 8
    h = styl.get("velikost", 30) + 14
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if styl.get("alfa_nul") is None and not styl.get("barva_snimku"):
        d.text((4, 4), text, font=font, fill=barva + (alfa,))
    else:
        x = 4
        tlumene = len(text) - 5 if s < 60 else len(text) - 8
        for i, z in enumerate(text):
            if i >= len(text) - 2 and styl.get("barva_snimku"):
                f = tuple(styl["barva_snimku"]) + (alfa,)
            elif i < tlumene:
                f = barva + (int(styl.get("alfa_nul", alfa)),)
            else:
                f = barva + (alfa,)
            d.text((x, 4), z, font=font, fill=f)
            x += font.getlength(z)
    from . import prvky
    ob = prvky.modul(spec["typ"]).obdelnik(spec, {})
    x = int((SIRKA - w) / 2) if styl.get("zarovnani") == "stred" else int(SIRKA * 0.20)
    y = int(min(VYSKA - DOLNI_OKRAJ - h, (ob[3] if ob else VYSKA * 0.45) + styl.get("mezera", 36)))
    if spec.get("casomira_y"):
        y = int(spec["casomira_y"])
    return img, (x, y), (x, y, x + w, y + h)


def radky_nadpisu(text, styl, velikost):
    """Řádky nadpisu. Ručně zadané zalomení (\\n) se dodrží, jinak se zalomí podle šířky. Vrátí (řádky, šířky, výška řádku)."""
    font = pismo(styl["pismo"], velikost, styl["varianta"])
    if "\n" in text:
        radky = [r.strip() for r in text.split("\n") if r.strip()]
    else:
        slova = text.split()
        b, sirky, mezera, _, _, _ = blok_textu(slova, font, dict(styl, velikost=velikost), styl["max_sirka"])
        radky = [" ".join(slova[j] for j in r["idx"]) for r in b]
    asc, desc = font.getmetrics()
    return radky, [font.getlength(r) for r in radky], int((asc + desc) * styl.get("radek", 1.1))


def velikost_hooku(text, styl, velikost):
    """Velikost viditelného bloku nadpisu (i s podkladem): (šířka, výška, velikost)."""
    radky, sirky, vr = radky_nadpisu(text, styl, velikost)
    px, py = styl.get("podklad_pad", (30, 18)) if styl.get("podklad") else (0, 0)
    return int(max(sirky) + 2 * px), int(vr * len(radky) + 2 * py), velikost


def vykresli_hook(hook, styl, alfa=1.0):
    """hook: {text, velikost, y}. y je horní okraj viditelného bloku (podkladu, nebo textu). Vrátí (obrázek, (x, y), obdélník)."""
    velikost = hook["velikost"]
    radky, sirky, vr = radky_nadpisu(hook["text"], styl, velikost)
    font = pismo(styl["pismo"], velikost, styl["varianta"])
    px, py = styl.get("podklad_pad", (30, 18)) if styl.get("podklad") else (0, 0)
    sb = max(sirky)
    pad = 56
    blok_w, blok_h = int(sb + 2 * px), int(vr * len(radky) + 2 * py)
    plocha = (blok_w + 2 * pad, blok_h + 2 * pad)
    polozky = []
    for i, (r, w) in enumerate(zip(radky, sirky)):
        polozky.append((pad + px + (sb - w) / 2, pad + py + i * vr, r, styl["barva"], 1.0))
    img = _vrstva_s_textem(plocha, polozky, styl, font, alfa)
    if styl.get("podklad"):
        p = Image.new("RGBA", plocha, (0, 0, 0, 0))
        ImageDraw.Draw(p).rounded_rectangle((pad, pad, pad + blok_w, pad + blok_h), radius=styl.get("podklad_radius", 30),
                                            fill=styl["podklad"][:3] + (int(styl["podklad"][3] * alfa),))
        p.alpha_composite(img)
        img = p
    x0 = int((SIRKA - blok_w) / 2) - pad
    y0 = int(hook["y"]) - pad
    return img, (x0, y0), (x0 + pad, y0 + pad, x0 + pad + blok_w, y0 + pad + blok_h)


def vykresli_vsuvku(vs, styl, alfa=1.0):
    """vs: {text, y, x}. Část textu mezi hvězdičkami je ve zvýrazněné barvě. Obrázek se nakloní."""
    velikost = vs.get("velikost", styl["velikost"])
    font = pismo(styl["pismo"], velikost, styl["varianta"])
    casti = [(c, i % 2 == 1) for i, c in enumerate(vs["text"].split("*")) if c]
    sirka = sum(font.getlength(c) for c, _ in casti)
    asc, desc = font.getmetrics()
    pad = 70
    plocha = (int(sirka) + 2 * pad, asc + desc + 2 * pad)
    polozky, x = [], pad
    for c, akcent in casti:
        polozky.append((x, pad, c, styl["akcent"] if akcent else styl["barva"], 1.0))
        x += font.getlength(c)
    img = _vrstva_s_textem(plocha, polozky, styl, font, alfa)
    if styl.get("podklad"):
        p = Image.new("RGBA", plocha, (0, 0, 0, 0))
        ImageDraw.Draw(p).rounded_rectangle((pad - 26, pad - 6, pad + sirka + 26, pad + asc + desc + 6), radius=24,
                                            fill=styl["podklad"][:3] + (int(styl["podklad"][3] * alfa),))
        p.alpha_composite(img)
        img = p
    img = img.rotate(styl["naklon"], resample=Image.BICUBIC, expand=True)
    x0, y0 = int(vs["x"]), int(vs["y"])
    return img, (x0, y0), (x0, y0, x0 + img.width, y0 + img.height)


def vypln_stranky(slova, styl):
    """Rozdělí slova reelu na stránky titulků: kratší stránky, zlom na konci věty a při pauze."""
    font = pismo(styl["pismo"], styl["velikost"], styl["varianta"])
    mezera = font.getlength(" ")
    stranky, aktualni = [], []

    def vejde(sl):
        sirky = [font.getlength(zobraz(w["w"], styl)) for w in sl]
        return len(rozdel(sirky, mezera, styl["max_sirka"])) <= styl["radku"]

    for i, w in enumerate(slova):
        if aktualni:
            pred = aktualni[-1]
            zlom = (len(aktualni) >= styl["max_slov"] or not vejde(aktualni + [w])
                    or re.search(r"[.?!]$", pred["w"]) or w["start"] - pred["end"] > 0.45
                    or (re.search(r"[,;:]$", pred["w"]) and len(aktualni) >= 3))
            if zlom:
                stranky.append(aktualni)
                aktualni = []
        aktualni.append(w)
    if aktualni:
        stranky.append(aktualni)
    # osamocené jedno slovo (ne konec věty), které se vejde k předchozí stránce, se k ní přilepí
    slite = []
    for s in stranky:
        if slite and styl["max_slov"] > 1 and len(s) == 1 and not re.search(r"[.?!]$", slite[-1][-1]["w"]) and len(slite[-1]) < styl["max_slov"] + 1 \
                and vejde(slite[-1] + s) and s[0]["start"] - slite[-1][-1]["end"] <= 0.45:
            slite[-1] = slite[-1] + s
        else:
            slite.append(s)
    return slite


OKRAJ_MASKY = (150, 2.2)   # střed a strmost okraje masky osoby pro vrstvy za osobou (snimek)


class Kreslic:
    """Zná všechno, co je na obrazovce, v každém snímku. Snímky se ukládají, opakující se se nekreslí znovu."""

    def __init__(self, osa, styl_nazev):
        self.osa = osa
        self.styl = STYLY[styl_nazev]
        self.n = int(round(osa["delka"] * FPS))
        self.stranky = vypln_stranky(osa["slova"], self.styl["titulky"])
        self.po_slovech = self.styl["titulky"].get("po_slovech", True)
        self.starty = [s[0]["start"] for s in self.stranky]
        self.konce = []
        for i, s in enumerate(self.stranky):
            dalsi = self.stranky[i + 1][0]["start"] if i + 1 < len(self.stranky) else 1e9
            self.konce.append(min(dalsi, s[-1]["end"] + 0.30))
        self.polohy = osa.get("titulky_polohy") or []   # střed každé stránky [x, y] nebo None (titulky vedle hlavy)
        self._obr = {}
        self._snimky = {}
        self.maska = None          # maska osoby (studio.maska.Maska): vrstvy „za hlavou“ osoba překrývá

    def za_hlavou(self, polozka):
        """Vrstva jde za osobu. Pravidlo Marcely (3. 11. 2026): efekty nikdy přes hlavu, vždycky za osobou.
        Proto prvky, hook a nadpisy jdou za osobu, i když to vzhled neříká; vypnout jde jen výslovně
        (za_hlavou: false ve spec nebo ve vzhledu). Titulky a karta výzvy (na hrudi) zůstávají vpředu."""
        if polozka[0] == "pt":
            return False
        if polozka[0] == "c":
            return True                      # běžící čas pod úvodem leží u hlavy, jde za osobu jako ostatní efekty
        if polozka[0] == "p":
            spec = self.osa["prvky"][polozka[1]]
            return bool(spec.get("za_hlavou", self.styl.get(spec["typ"], {}).get("za_hlavou", True)))
        if polozka[0] in ("e", "h"):
            spec = self.osa["hook"] if (polozka[0] == "h" or polozka[1] == -1) else self.osa["mini"][polozka[1]]
            nazev = "hook" if (polozka[0] == "h" or polozka[1] == -1) else spec.get("styl", "mini")
            styl_bloku = self.styl[nazev]
            # karta výzvy: studio ji kreslí stylem mini_silny na hrudi (bez titulků, ne nad obličejem)
            if spec.get("vyzva") or (nazev == "mini_silny" and spec.get("skryt_titulky") and not spec.get("nad_oblicejem")):
                return bool(spec.get("za_hlavou", False))
            return bool(spec.get("za_hlavou", styl_bloku.get("za_hlavou", nazev != "vyzva")))
        return False

    def alfa(self, t, od, do, nabeh=0.25, dobeh=0.2):
        return max(0.0, min(1.0, (t - od) / nabeh, (do - t) / dobeh))

    def stav(self, t):
        """Klíč toho, co je vidět v čase t. Stejný klíč = stejný snímek."""
        klic = []
        h = self.osa.get("hook")
        nadpis = bool(h and h["od"] <= t < h["do"])
        i = bisect.bisect_right(self.starty, t + 0.03) - 1
        mini_schovava = any(m.get("skryt_titulky") and m["od"] <= t < m["do"] for m in self.osa.get("mini", []) + self.osa.get("prvky", []))
        if i >= 0 and t < self.konce[i] and not (nadpis and h.get("skryt_titulky")) and not mini_schovava:
            k = sum(1 for w in self.stranky[i] if w["start"] <= t + 0.03) if self.po_slovech else len(self.stranky[i])
            krok_vetsi = self._krok_vetsich(t)
            klic.append(("t", i, max(1, k)) + ((krok_vetsi,) if krok_vetsi else ()))
        from . import efekty
        if nadpis and h.get("efekt"):
            klic.append(("e", -1, efekty.krok(h, t - h["od"], h["do"] - t)))
        elif nadpis:
            klic.append(("h", round(self.alfa(t, h["od"], h["do"]) * 6)))
        for j, pv in enumerate(self.osa.get("prvky", [])):
            if pv["od"] <= t < pv["do"]:
                from . import prvky
                kk = prvky.modul(pv["typ"]).stav(pv, t)
                if kk is not None:
                    klic.append(("p", j, kk))
                    if pv.get("text_vpredu"):
                        klic.append(("pt", j, kk))
                    if pv.get("casomira"):
                        klic.append(("c", j, int(round((t - pv["od"]) * FPS))))
        for j, m in enumerate(self.osa.get("mini", [])):
            if m["od"] <= t < m["do"]:
                klic.append(("e", j, efekty.krok(m, t - m["od"], m["do"] - t)))
        for j, v in enumerate(self.osa.get("vsuvky", [])):
            if v["od"] <= t < v["do"]:
                klic.append(("v", j, round(self.alfa(t, v["od"], v["do"], 0.15, 0.15) * 6)))
        return tuple(klic)

    def _vrstva(self, polozka):
        if polozka in self._obr:
            return self._obr[polozka]
        if polozka[0] in ("p", "pt"):
            from . import prvky
            spec = self.osa["prvky"][polozka[1]]
            if spec.get("text_vpredu"):
                spec = dict(spec, cast="text" if polozka[0] == "pt" else "pozadi")
            img, poz = prvky.modul(spec["typ"]).vykresli(spec, self.styl.get(spec["typ"], {}), polozka[2])
            r = (img, poz, prvky.modul(spec["typ"]).obdelnik(spec, self.styl.get(spec["typ"], {})))
        elif polozka[0] == "t":
            st = self.styl["titulky"]
            if len(polozka) > 3:
                m = polozka[3] / 100.0
                st = dict(st, velikost=int(round(st["velikost"] * m)), max_sirka=int(min(SIRKA - 60, st["max_sirka"] * m)))
            r = vykresli_titulky(self.stranky[polozka[1]], polozka[2], st, self._stred(polozka[1]))
        elif polozka[0] == "e":
            from . import efekty
            spec = self.osa["hook"] if polozka[1] == -1 else self.osa["mini"][polozka[1]]
            styl_bloku = self.styl["hook"] if polozka[1] == -1 else self.styl[spec.get("styl", "mini")]
            r = efekty.vykresli(spec, styl_bloku, polozka[2])
        elif polozka[0] == "h":
            r = vykresli_hook(self.osa["hook"], self.styl["hook"], polozka[1] / 6)
        elif polozka[0] == "c":
            r = vykresli_casomiru(self.osa["prvky"][polozka[1]], self.styl.get("casomira", {}), polozka[2])
        else:
            r = vykresli_vsuvku(self.osa["vsuvky"][polozka[1]], self.styl["vsuvka"], polozka[2] / 6)
        self._obr[polozka] = r
        return r

    def _krok_vetsich(self, t):
        """Větší titulky (osa["titulky_vetsi"] = [{"od", "do", "meritko": 1.5}], 3. 11. 2026, „větší titulky?“):
        titulky naskočí s pružným zvětšením za 0,2 s, drží a za 0,15 s se vrátí. Vrátí měřítko v procentech, nebo 0."""
        for v in self.osa.get("titulky_vetsi") or []:
            if v["od"] <= t < v["do"]:
                cil = float(v.get("meritko", 1.5))
                a, z = t - v["od"], v["do"] - t
                if a < 0.2:
                    p = a / 0.2
                    m = 1 + (cil - 1) * (p * (1 + 0.35 * (1 - p) * 3))
                elif z < 0.15:
                    m = 1 + (cil - 1) * (z / 0.15)
                else:
                    m = cil
                return int(round(m * 100 / 2.0)) * 2
        return 0

    def _stred(self, i):
        return self.polohy[i] if i < len(self.polohy) else None

    def _plat(self, klic):
        """Složené vrstvy klíče na průhledné plátno (s mezipamětí)."""
        if klic in self._snimky:
            return self._snimky[klic]
        plat = Image.new("RGBA", (SIRKA, VYSKA), (0, 0, 0, 0))
        for p in klic:
            img, (x, y), _ = self._vrstva(p)
            plat.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
        if len(self._snimky) > 120:
            self._snimky.clear()
        if len(self._obr) > 600:
            self._obr.clear()
        self._snimky[klic] = plat
        return plat

    def snimek(self, klic, i=None):
        """Snímek pro klíč. S maskou osoby jdou vrstvy „za hlavou“ pod osobu: jejich průhlednost se vynásobí (1 − maska)."""
        zadni = tuple(p for p in klic if self.za_hlavou(p))
        if not zadni or self.maska is None or i is None:
            return self._plat(klic).tobytes()
        import numpy as np
        predni = tuple(p for p in klic if p not in zadni)
        z = np.array(self._plat(zadni), dtype=np.uint8).copy()
        m = self.maska[i]                                   # (VYSKA, SIRKA) uint8, 255 = osoba
        # užší okraj osoby: měkký přechod masky nechával kolem osoby světlý lem původního pozadí (hlavně na plné
        # barevné ploše za osobou, 3. 11. 2026); přechod se zúží a posune o 1 až 2 px dovnitř osoby (NÁVRH hodnot)
        stred, strmost = OKRAJ_MASKY
        m = np.clip((m.astype(np.float32) - stred) * strmost + 128, 0, 255).astype(np.uint8)
        z[:, :, 3] = (z[:, :, 3].astype(np.uint16) * (255 - m.astype(np.uint16)) // 255).astype(np.uint8)
        out = Image.fromarray(z, "RGBA")
        if predni:
            out.alpha_composite(self._plat(predni))
        return out.tobytes()

    def snimky(self):
        """Generátor všech snímků reelu jako surové RGBA bajty."""
        pred, data = None, None
        for i in range(self.n):
            klic = self.stav(i / FPS)
            za = self.maska is not None and any(self.za_hlavou(p) for p in klic)
            if klic != pred or za:
                data = self.snimek(klic, i if za else None)
                pred = klic
            yield data

    def obdelniky(self):
        """Všechny texty, jak se objeví: typ, čas od a do, obdélník. Pro automatickou kontrolu."""
        out = []
        h = self.osa.get("hook")
        for i, s in enumerate(self.stranky):
            _, _, ob = vykresli_titulky(s, len(s), self.styl["titulky"], self._stred(i))
            od, do = s[0]["start"], self.konce[i]
            if any(m.get("skryt_titulky") and od < m["do"] and do > m["od"] for m in self.osa.get("mini", []) + self.osa.get("prvky", [])):
                continue   # za dobu karty, která titulky schovává, se titulky nezobrazují
            if h and h.get("skryt_titulky") and od < h["do"] and do > h["od"]:   # za dobu nadpisu se titulky nezobrazují
                od = max(od, h["do"])
                if od >= do:
                    continue
            out.append({"typ": "titulky", "od": od, "do": do, "obdelnik": ob})
        if h:
            from . import efekty
            ob = efekty.obdelnik(h, self.styl["hook"]) if h.get("efekt") else vykresli_hook(h, self.styl["hook"])[2]
            out.append({"typ": "hook", "od": h["od"], "do": h["do"], "obdelnik": ob,
                        "vlasy_podil": 0.55 if (h.get("za_hlavou") or self.styl["hook"].get("za_hlavou")) else None})
        for m in self.osa.get("mini", []):
            from . import efekty
            out.append({"typ": "mini", "od": m["od"], "do": m["do"], "obdelnik": efekty.obdelnik(m, self.styl[m.get("styl", "mini")]),
                        "nad_oblicejem": bool(m.get("nad_oblicejem")), "vlasy_podil": m.get("vlasy_podil"),
                        "pres_oblicej": bool(m.get("pres_oblicej"))})
        for pv in self.osa.get("prvky", []):
            from . import prvky
            out.append({"typ": pv["typ"], "od": pv["od"], "do": pv["do"], "pres_oblicej": bool(pv.get("pres_oblicej")), "pozadi": bool(pv.get("pozadi")),
                        "nad_oblicejem": bool(pv.get("nad_oblicejem")),
                        "obdelnik": prvky.modul(pv["typ"]).obdelnik(pv, self.styl.get(pv["typ"], {}))})
        for v in self.osa.get("vsuvky", []):
            out.append({"typ": "vsuvka", "od": v["od"], "do": v["do"],
                        "obdelnik": vykresli_vsuvku(v, self.styl["vsuvka"])[2]})
        return out


def text_po_radcich(slova, styl, velikost=None, max_sirka=None):
    """Text rozdělený na řádky stejně jako při kreslení (pro CapCut, kde se zlom řádku píše do textu)."""
    font = pismo(styl["pismo"], velikost or styl["velikost"], styl["varianta"])
    s = dict(styl, velikost=velikost or styl["velikost"])
    radky, _, _, _, _, _ = blok_textu(slova, font, s, max_sirka or styl["max_sirka"])
    return "\n".join(" ".join(slova[j] for j in r["idx"]) for r in radky)
