"""Příkazy studia (etapa A). Spuštění ze složky jadro: STUDIO <krok> ...

  zaloz           založí složku reelu
  kopie           zkopíruje video do PODKLADY-SEM (originál zůstane)
  kontrola-videa  zkontroluje každé video a připraví pracovní kopii, když je třeba
  prepis          přepis s časy slov, opravy slov, hlídaná a nejistá slova
  navrh           zdvojené věty, pauzy, návrh výběru vět
  nahled          hrubý střih jako MP4 k náhledu (bez textu) a kontrola souboru
  editor          editor přepisu v prohlížeči, uloží PRACOVNI/upravy.json
  plan-reelu      stránka Plán reelu: scény jako karty, vlastní média, věty s prvky
  oprava-titulku  Claude opraví chyby přepisu v titulcích před náhledem (video se nestříhá)
  zabery          záběry pro b-roll pod hlasem: kvalita, nejlepší chvilky, náhledy pro Clauda, katalog
  styl            kód stylu z knihovny stylů nebo věta zákaznice (písmo větší…), zapíše PRACOVNI/styl.json a vzhled.json
  stav            co je hotové

Každý krok skončí jednou českou řádkou (✅ nebo 🔴) a zapíše se do PRACOVNI/stav.json.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import duplikaty, hlaseni, hlidana_slova, kopie, kontrola_videa, opravy, otisk, projekt, reel, strih
from .hlaseni import Krok, cas_text

# prvky, které smí běžet souběžně s dalšími (pozadí za osobou, karty IG nahoře a dole): nezkracují se kvůli dalšímu textu
PRVKY_BEZ_ZKRACENI = {"vypinac_plakat", "pred_po", "obalka_casopisu", "ig_sledovat", "ig_komentar"}
PRVKY_POZADI = {"vypinac_plakat", "pred_po", "obalka_casopisu"}      # ani nezkracují ostatní (běží za osobou)


def _prubeh(r):
    """Po každém kroku obnoví přehled průběhu (VYSTUP/prubeh.html). Chyba přehledu nikdy neshodí krok."""
    try:
        from . import prubeh
        return prubeh.zapis(r)
    except Exception as e:  # noqa: BLE001
        print("   ℹ️ Přehled průběhu se nepodařilo obnovit: %s" % str(e)[:120])
        return None


def krok_prubeh(a):
    import webbrowser

    from . import prubeh

    r = _reel(a.reel)
    k = Krok("Přehled průběhu")   # bez zápisu do stav.json, ať se na stránce neukazuje sám sobě jako "běží"
    cil = prubeh.zapis(r)
    if not a.neotvirat:
        webbrowser.open(cil.as_uri())
    k.zelena("stránka je v %s a sama se obnovuje." % cil, "nech ji otevřenou vedle a sleduj, co studio dělá.")
    return k.kod()


def _reel(cesta):
    r = Path(cesta).expanduser().resolve()
    if not (r / "PRACOVNI").is_dir():
        raise SystemExit("🔴 Složka %s není složka reelu (chybí PRACOVNI). Udělej: STUDIO zaloz --reely ... --nazev ..." % r)
    return r


def krok_zaloz(a):
    koren = Path(a.reely).expanduser().resolve()
    k = Krok("Založení reelu")
    nast = koren / "NASTAVENI"
    if not nast.exists():
        shutil.copytree(projekt.BALICEK / "NASTAVENI", nast)
        k.info("Složka NASTAVENI ještě nebyla, založil jsem ji s výchozím nastavením.")
    slozka = reel.zaloz_reel(koren, a.nazev)
    k.pracovni = slozka / "PRACOVNI"
    k.zelena("složka %s je připravená." % slozka, "nahraj video do %s a spusť kopii (STUDIO kopie --reel \"%s\" <video>)."
             % (slozka / "PODKLADY-SEM", slozka), {"slozka": str(slozka)})
    print(slozka)
    return k.kod()


def krok_kopie(a):
    r = _reel(a.reel)
    s = projekt.slozky(r)
    if getattr(a, "nahravka", False):
        return _kopie_nahravek(a, r, s)
    k = Krok("Kopie videa", s["pracovni"])
    zdroje = [Path(v).expanduser() for v in a.video] if a.video else reel.najdi_videa(s["podklady"])
    icloud = reel.zastupne_icloud(s["podklady"])
    if icloud:
        k.info("Soubory jen v iCloudu (nestažené): %s" % ", ".join(icloud))
    if not zdroje:
        return k.cervena("ve složce PODKLADY-SEM není žádné video.",
                         "přetáhni natočené video do %s a spusť krok znovu." % s["podklady"]).and_kod() if False else \
            (k.cervena("ve složce PODKLADY-SEM není žádné video.", "přetáhni natočené video do %s a spusť krok znovu." % s["podklady"]), k.kod())[1]
    hotove, chyby = [], []
    for z in zdroje:
        v = kopie.zkopiruj(z, s["podklady"], s["pracovni"] / "kopie.json")
        if v["ok"]:
            hotove.append(v)
            k.info(v["zprava"])
        else:
            chyby.append(v)
    if chyby:
        k.cervena("%d z %d videí se nepodařilo zkopírovat: %s" % (len(chyby), len(zdroje), " ".join(c["zprava"] for c in chyby)),
                  " ".join(c["udelej"] for c in chyby if c.get("udelej")))
    else:
        k.zelena("%d video je ve složce reelu, otisky souhlasí, originály zůstaly na místě." % len(hotove) if len(hotove) == 1 else
                 "%d videa jsou ve složce reelu, otisky souhlasí, originály zůstaly na místě." % len(hotove),
                 "kontrola videa (STUDIO kontrola-videa --reel \"%s\")." % r, {"videa": [h["cil"] for h in hotove]})
    reel.pripis_do_seznamu(s["reely"], r.name, projekt.nazev_reelu(r), "video zkopírováno")
    _prubeh(r)
    return k.kod()


def _kopie_nahravek(a, r, s):
    """Nahrávky obrazovky do PODKLADY-SEM/NAHRAVKY-OBRAZOVKY. Nejsou to klipy jejího mluvení: nepřepisují se,
    plán je dá do vložky (video v rámečku). Originál zůstává na místě."""
    k = Krok("Kopie nahrávky obrazovky", s["pracovni"])
    cil = s["podklady"] / reel.NAHRAVKY
    if not a.video:
        k.cervena("nevím, kterou nahrávku zkopírovat.", "zadej cestu k nahrávce obrazovky (MP4 nebo MOV).")
        return k.kod()
    hotove, chyby = [], []
    for z in [Path(v).expanduser() for v in a.video]:
        if z.suffix.lower() not in reel.NAHRAVKY_PRIPONY:
            chyby.append({"zprava": "%s: nahrávku obrazovky umí studio jen jako MP4 nebo MOV." % z.name,
                          "udelej": "Ulož nahrávku jako MP4 nebo MOV (iPhone, Mac i Windows to dělají samy)."})
            continue
        v = kopie.zkopiruj(z, cil, s["pracovni"] / "kopie-nahravek.json")
        (hotove if v["ok"] else chyby).append(v)
        if v["ok"]:
            k.info(v["zprava"].replace("Video ", "Nahrávka ", 1))
    if chyby:
        k.cervena("%d z %d nahrávek se nepodařilo zkopírovat: %s" % (len(chyby), len(a.video), " ".join(c["zprava"] for c in chyby)),
                  " ".join(c["udelej"] for c in chyby if c.get("udelej")))
    else:
        k.zelena("Nahrávky obrazovky jsou ve složce %s/%s: %s. Plán reelu je dá do rámečku k větám o obrazovce "
                 "(z každé nahrávky nejvýš 8 s od začátku)." % (s["podklady"].name, reel.NAHRAVKY,
                                                                ", ".join(Path(h["cil"]).name for h in hotove)),
                 "plán obrazovky (STUDIO plan --reel \"%s\"), když už je náhled." % r,
                 {"nahravky": [h["cil"] for h in hotove]})
    return k.kod()


def krok_kontrola_videa(a):
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Kontrola videa", s["pracovni"])
    videa = reel.najdi_videa(s["podklady"])
    if not videa:
        k.cervena("ve složce PODKLADY-SEM není žádné video.", "nejdřív spusť kopii videa.")
        return k.kod()
    # pořadí klipů podle času natočení z metadat (poslední pokus má vyhrát), jinak podle názvu
    videa = sorted(videa, key=lambda v: (kontrola_videa.cas_vzniku(v), v.name.lower()))
    klipy, chyby = [], []
    for n, v in enumerate(videa, 1):
        slozka = s["pracovni"] / ("klip-%d" % n)
        t = time.time()
        ok, zprava, udelej, info = kontrola_videa.kontrola(v, slozka)
        k.info("Klip %d (%s): %s%s" % (n, v.name, zprava, "" if ok else " 🔴 " + (udelej or "")))
        if ok:
            klipy.append({"n": n, "original": str(v), "pouzit": info["pouzit"], "delka_s": info["delka_s"], "natoceno": kontrola_videa.cas_vzniku(v),
                          "pripravena_kopie": bool(info.get("pripravena_kopie")), "kontrola_s": round(time.time() - t, 1)})
        else:
            chyby.append((v.name, zprava, udelej))
    projekt.uloz_json(s["pracovni"] / "klipy.json", klipy)
    if chyby:
        k.cervena("%d z %d videí neprošlo: %s" % (len(chyby), len(videa), " ".join(z for _, z, _ in chyby)),
                  " ".join(dict.fromkeys(u for _, _, u in chyby if u)))
    else:
        celkem = sum(x["delka_s"] for x in klipy)
        k.zelena("%d klip%s, celkem %s videa, všechno v pořádku." % (len(klipy), "" if len(klipy) == 1 else "y", cas_text(celkem)),
                 "přepis (STUDIO prepis --reel \"%s\")." % r, {"klipy": klipy})
    _prubeh(r)
    return k.kod()


def krok_prepis(a):
    from . import nejista, prepis

    r = _reel(a.reel)
    s = projekt.slozky(r)
    nast = projekt.nastaveni(r)
    k = Krok("Přepis", s["pracovni"])
    klipy = projekt.klipy_seznam(r)
    if not klipy:
        k.cervena("chybí seznam klipů.", "nejdřív spusť kontrolu videa.")
        return k.kod()
    # jazyk (Marcela 25. 11. 2026): auto = studio pozná z hlasu češtinu, nebo slovenčinu; --jazyk ho určí napevno
    from . import jazyk as _jazyk
    pozadany = a.jazyk or nast.get("jazyk_reci") or "auto"
    jazyk_reelu, seznam_oprav, vzory = None, None, None
    slov, delka, oprav, hlidanych, nejistych, cas = 0, 0.0, 0, [], 0, 0.0
    for kl in klipy:
        slozka = s["pracovni"] / ("klip-%d" % kl["n"])
        t = time.time()
        metriky, vety = prepis.prepis_klipu(kl["pouzit"], slozka, a.model, "k%d-v" % kl["n"], jazyk_reelu or pozadany)
        if jazyk_reelu is None:
            jazyk_reelu = _jazyk.platny(metriky.get("jazyk"))
            projekt.uloz_json(s["pracovni"] / "jazyk.json", {"jazyk": jazyk_reelu, "zdroj": "hlas" if pozadany == "auto" else "zadano",
                                                             "rozpoznani": metriky.get("jazyk_poznany_z_hlasu")})
            seznam_oprav = projekt.seznam_oprav(r, jazyk_reelu)
            vzory = projekt.vzory_hlidanych(r, jazyk_reelu)
            rp = metriky.get("jazyk_poznany_z_hlasu") or {}
            k.info("Jazyk: %s%s." % (_jazyk.nazev(jazyk_reelu), (" (poznal jsem z hlasu, jistota %d %%)" % round(100 * rp.get(jazyk_reelu, 0)))
                                     if rp else " (zadaný napevno)"))
            if rp and rp.get("nejpravdepodobnejsi") not in _jazyk.JAZYKY:
                k.info("⚠️ Hlas zní spíš jako jiný jazyk (%s). Studio umí češtinu a slovenčinu, přepsal jsem ho jako %s." %
                       (rp.get("nejpravdepodobnejsi"), _jazyk.nazev(jazyk_reelu)))
        zaznam = opravy.oprav_vety(vety, seznam_oprav)
        opravy.slij_cisla(vety)
        nej = []
        if a.porovnat:
            druhy = "turbo" if a.model != "turbo" else "large-v3"
            _, vety_b = prepis.prepis_klipu(kl["pouzit"], slozka / "porovnani", druhy, "k%d-v" % kl["n"], jazyk_reelu)
            opravy.oprav_vety(vety_b, seznam_oprav)
            nej = nejista.nejista_slova(vety, vety_b)
        else:
            nej = [{"veta": v["id"], "cas": w["start"], "slovo": w["w"], "jine": None, "jistota": w.get("p")}
                   for v in vety for w in v["slova"] if w.get("p", 1) < 0.5]
        hl = hlidana_slova.najdi_hlidana(vety, vzory, nej)
        prepis.uloz_vety(vety, slozka / "prepis-vety.txt", hlidana_slova.poznamky_k_vetam(hl, nej))
        projekt.uloz_json(slozka / "opravy.json", {"opravy_slov": zaznam, "hlidana_slova": hl, "nejista_slova": nej})
        cas += time.time() - t
        slov += metriky["pocet_slov"]
        delka += metriky["delka_s"]
        oprav += len(zaznam)
        hlidanych += [(h["veta"], h["slovo"]) for h in hl]
        nejistych += len(nej)
        k.info("Klip %d: %d vět, %d slov, přepis %.0f s (%.2fx délky), model %s." %
               (kl["n"], metriky["pocet_vet"], metriky["pocet_slov"], metriky["cas_prepisu_s"], metriky["nasobek_realneho_casu"] or 0, a.model))
    zprava = "%d klip%s, %s videa, %d slov za %.0f s. Opravy slov: %d. Nejistá slova: %d." % (
        len(klipy), "" if len(klipy) == 1 else "y", cas_text(delka), slov, cas, oprav, nejistych)
    if hlidanych:
        zprava += " ⚠️ Hlídaná slova ke kontrole sluchem: %s." % ", ".join("%s '%s'" % h for h in hlidanych)
    else:
        zprava += " Hlídaná slova: žádná."
    k.zelena(zprava, "návrh střihu (STUDIO navrh --reel \"%s\"). Věty jsou v PRACOVNI/klip-*/prepis-vety.txt." % r,
             {"slov": slov, "delka_s": round(delka, 1), "cas_s": round(cas, 1), "model": a.model, "hlidana": hlidanych})
    reel.pripis_do_seznamu(s["reely"], r.name, projekt.nazev_reelu(r), "přepis hotový")
    _prubeh(r)
    return k.kod()


def krok_navrh(a):
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Návrh střihu", s["pracovni"])
    klipy = projekt.nacti_klipy(r, s_energii=False)
    if not klipy:
        k.cervena("chybí přepis.", "nejdřív spusť přepis.")
        return k.kod()
    klipy_vety = [kl["vety"] for kl in klipy]
    dvojice = duplikaty.cele_pokusy(klipy_vety, duplikaty.najdi_opakovani(klipy_vety))
    pauzy = duplikaty.dlouhe_pauzy(klipy_vety)
    vyber = duplikaty.navrh_vyberu(klipy_vety, dvojice)
    vybrane = {v for _, v in vyber}
    vynechat = {k: v for k, v in duplikaty.restarty(klipy_vety).items() if k in vybrane}
    text = duplikaty.text_navrhu(klipy_vety, dvojice, pauzy, vyber, vynechat)
    projekt.uloz_json(s["pracovni"] / "navrh-strihu.json", {"vyber": [[c, v] for c, v in vyber], "vynechat": vynechat,
                                                           "dvojice": dvojice, "pauzy": pauzy})
    (s["pracovni"] / "navrh-strihu.txt").write_text(text, encoding="utf-8")
    if (s["pracovni"] / "vyber.json").exists() and not a.znovu:
        k.info("Platný výběr už existuje (vyber.json), návrh ho nepřepisuje. Chceš začít znovu: --znovu.")
    elif a.znovu and (s["pracovni"] / "vyber.json").exists():
        (s["pracovni"] / "vyber.json").rename(s["pracovni"] / ("vyber-stary-%d.json" % int(time.time())))
    print(text)
    stejne = sum(1 for d in dvojice if d["druh"] in ("stejna", "znovu_zacata"))
    pokusy = sum(1 for d in dvojice if d["druh"] == "prvni_pokus")
    k.zelena("%d vět, opakovaných %d (vyhazuju první pokus), vynechaných ve druhém pokusu %d, znovu začatých uvnitř věty %d, podobných %d, dlouhých pauz %d. Zůstává %d vět. Návrh je v PRACOVNI/navrh-strihu.txt." %
             (sum(len(v) for v in klipy_vety), stejne, pokusy, len(vynechat), len(dvojice) - stejne - pokusy, len(pauzy), len(vyber)),
             "náhled (STUDIO nahled --reel \"%s\"), nebo uprav výběr: --vyber k1-v01,k1-v02 --vynechat k1-v05:1,2" % r)
    _prubeh(r)
    return k.kod()


def _rozeber_vynechat(text):
    out = {}
    for cast in (text or "").split(";"):
        cast = cast.strip()
        if not cast:
            continue
        vid, _, idx = cast.partition(":")
        out[vid.strip()] = sorted({int(x) for x in idx.split(",") if x.strip().isdigit()})
    return out


def _rozeber_rezy(text):
    """„k1:10.92-11.13;k3:21.8-22.1“ -> {0: [(10.92, 11.13)], 2: [(21.8, 22.1)]} (čísla klipů od 1, časy v originálu)."""
    out = {}
    for cast in (text or "").split(";"):
        cast = cast.strip()
        if not cast:
            continue
        klip, _, cas = cast.partition(":")
        od, _, do = cas.partition("-")
        c = int(klip.strip().lstrip("kK")) - 1
        od, do = float(od.replace(",", ".")), float(do.replace(",", "."))
        if do <= od:
            raise ValueError("úsek %s končí dřív, než začne" % cast)
        out.setdefault(c, []).append((od, do))
    return out


def krok_nahled(a):
    from . import kontrola_reelu, render

    r = _reel(a.reel)
    s = projekt.slozky(r)
    nast = projekt.nastaveni(r)
    k = Krok("Náhled", s["pracovni"])
    klipy = projekt.nacti_klipy(r)
    if not klipy:
        k.cervena("chybí přepis.", "nejdřív spusť přepis a návrh střihu.")
        return k.kod()
    vyber, vynechat, texty, upravy = projekt.pouzij_upravy(r, klipy)
    if upravy:
        k.info("Použil jsem úpravy z editoru: smazané věty %d, vystřižená slova %d, upravené texty %d." %
               (len(upravy.get("smazane_vety", [])), sum(len(v) for v in upravy.get("smazana_slova", {}).values()), len(upravy.get("texty", {}))))
        if texty:
            strih.pouzij_texty(klipy, texty)
    if a.vyber:
        index = {v["id"]: c for c, kl in enumerate(klipy) for v in kl["vety"]}
        chybi = [x.strip() for x in a.vyber.split(",") if x.strip() and x.strip() not in index]
        if chybi:
            k.cervena("neznámé věty ve výběru: %s." % ", ".join(chybi), "použij čísla vět z PRACOVNI/klip-*/prepis-vety.txt.")
            return k.kod()
        vyber = [(index[x.strip()], x.strip()) for x in a.vyber.split(",") if x.strip()]
    if a.vynechat:
        for vid, idx in _rozeber_vynechat(a.vynechat).items():
            vynechat[vid] = sorted(set(vynechat.get(vid, [])) | set(idx))
    if not vyber:
        k.cervena("výběr vět je prázdný.", "vrať aspoň jednu větu (editor) nebo zadej --vyber.")
        return k.kod()
    projekt.uloz_vyber(r, vyber, vynechat, texty)
    # ruční úseky k vystřižení se pamatují v PRACOVNI/vystrihnout.json; nové --vystrihnout je nahradí celé („“ = žádné)
    cesta_rezu = s["pracovni"] / "vystrihnout.json"
    if a.vystrihnout is not None:
        try:
            rezy = _rozeber_rezy(a.vystrihnout)
        except ValueError as e:
            k.cervena("úseky k vystřižení nejdou přečíst: %s." % e, "zadej je jako k1:10.92-11.13;k3:21.8-22.1 (klip:od-do v sekundách originálu).")
            return k.kod()
        projekt.uloz_json(cesta_rezu, {str(c): v for c, v in rezy.items()})
    else:
        rezy = {int(c): [tuple(x) for x in v] for c, v in (json.loads(cesta_rezu.read_text()) if cesta_rezu.exists() else {}).items()}
    if rezy:
        k.info("Ručně vystřižené úseky: %s." % ", ".join("klip %d %.2f až %.2f s" % (c + 1, od, do) for c, v in sorted(rezy.items()) for od, do in v))
    t = time.time()
    if a.cele:
        vyber = [(c, v["id"]) for c, kl in enumerate(klipy) for v in kl["vety"]]
        vynechat = {}
    vynechat_ticho, hlaseni = strih.rozsir_vynechat_do_ticha(klipy, vyber, vynechat)
    for h in hlaseni:
        k.info(h)
    # tempo (Marcela 24. 11. 2026): úderně / běžně / procítěně, pamatuje se v PRACOVNI/tempo.json
    cesta_tempa = s["pracovni"] / "tempo.json"
    tempo = a.tempo or (projekt.nacti_json(cesta_tempa, {}) or {}).get("tempo") or "bezne"
    if a.tempo:
        projekt.uloz_json(cesta_tempa, {"tempo": tempo})
    if tempo != "bezne":
        k.info({"uderne": "Tempo úderné: i kratší pauzy se zkracují, b-roll se střídá rychleji.",
                "procitene": "Tempo procítěné: mezi myšlenkami zůstává chvilka ticha, b-roll déle a s prolnutím."}[tempo])
    osa = strih.osa_cela(klipy, vyber) if a.cele else strih.sestav_osu(klipy, vyber, vynechat=vynechat_ticho or vynechat, rezy=rezy, tempo=tempo)
    osa["tempo"] = tempo
    osa["jazyk"] = projekt.jazyk_reelu(r)
    if a.cele:
        k.info("Bez střihu: video celé, %s, nic se nezkracuje." % cas_text(osa["delka"]))
    osa["vynechat_zadano"] = {kk: v for kk, v in vynechat.items() if v}
    n = projekt.dalsi_cislo(s["vystup"], "nahled", ".mp4")
    mp4 = s["vystup"] / ("nahled-%d.mp4" % n)
    prac = s["pracovni"] / ("nahled-%d" % n)
    s["vystup"].mkdir(exist_ok=True)
    otisk_vstupu = otisk.spocitej(r, plan=False, vzhled=False)     # stav, ze kterého náhled vzniká (stránka Plán reelu)
    try:
        if a.bez_titulku:
            m = render.vyrenderuj(osa, nast.get("vzhled", "serif"), mp4, prac, bez_textu=True, preset=a.preset)
        else:
            # Marcela 10. 11. 2026: náhled po střihu má titulky (jednoduché bílé), ať zákaznice vidí text a může
            # napsat opravu. Bez nadpisu, efektů a zvuků: ty přijdou až podle jejího výběru v knihovně stylů.
            osa_nahled = {kk: v for kk, v in osa.items()
                          if kk not in ("hook", "mini", "prvky", "vsuvky", "prechody", "zvuky", "titulky_polohy", "filtr_od")}
            m = render.vyrenderuj(osa_nahled, "serif", mp4, prac, preset=a.preset)
            k.info("Náhled má jednoduché bílé titulky, ať je vidět text. Vzhled přijde podle výběru stylu.")
    except RuntimeError as e:
        k.cervena("render se nezdařil: %s" % e, "spusť krok znovu; když to nepomůže, pošli mi PRACOVNI/nahled-%d/ffmpeg-chyby.log." % n)
        return k.kod()
    strih.uloz_osu(osa, s["pracovni"] / "casova-osa.json")
    strih.uloz_osu(osa, prac / "casova-osa.json")
    otisk.uloz(otisk_vstupu, prac)
    seznam_oprav = projekt.seznam_oprav(r)
    vysl, chyby = kontrola_reelu.kontrola_reelu(mp4, osa, prac, s_prepisem=a.kontrola_slov, seznam_oprav=seznam_oprav, model=a.model)
    cervene = [v for v in vysl if not v[1]]
    for nazev, ok, detail in vysl:
        k.info("%s %s: %s" % ("ZELENÁ" if ok else "ČERVENÁ", nazev, detail))
    nejiste = strih.nejiste_strihy(osa)
    projekt.uloz_json(prac / "mereni.json", {"render": m, "kontrola": vysl, "slova_nesedi": chyby, "nejiste_strihy": nejiste,
                                              "trvani_s": round(time.time() - t, 1)})
    cil, nejvic = nast["delka_reelu"]["cil_s"], nast["delka_reelu"]["nejvic_s"]
    delka_text = "%s (cíl %s, nejvíc %s)" % (cas_text(osa["delka"]), cas_text(cil), cas_text(nejvic))
    if osa["delka"] > nejvic:
        delka_text += " 🔴 nad limitem"
    elif osa["delka"] > cil:
        delka_text += " ⚠️ nad cílem"
    zprava = "náhled %d: délka %s, %d vět, %d střihů, hotovo za %.0f s. Kontrola souboru %d z %d zelená. Soubor: %s." % (
        n, delka_text, len({v for u in osa["useky"] for v in u["vety"]}), max(0, len(osa["useky"]) - 1), time.time() - t,
        len(vysl) - len(cervene), len(vysl), mp4)
    if hlaseni:
        zprava += " " + " ".join(hlaseni) + " Když to nechceš, vrať slova v editoru."
    if nejiste:
        zprava += " Střihy uvnitř věty bez pauzy (zkontroluj poslechem): %s." % ", ".join("%s v %s" % (x["veta"], cas_text(x["cas"])) for x in nejiste)
    # Editor přepisu (náhled s titulky a větami) má zákaznici vyskočit po KAŽDÉM náhledu (Marcela 23. 11. 2026,
    # „must have“). Krok náhledu už na editor nečeká: příkaz by běžel až 30 minut a Claudovi by vypršel čas.
    # Claude editor spustí hned potom na pozadí a otevře ho vedle chatu (stejně jako knihovnu stylů).
    otevrit_editor = a.editor or (nast.get("editor_po_nahledu", True) and not a.bez_editoru)
    pokyn_editor = ("HNED, bez ptaní, otevři zákaznici editor přepisu: spusť NA POZADÍ STUDIO editor --reel \"%s\" --neotvirat, "
                    "adresu z řádku STATUS editor READY otevři vedle chatu (vestavěný prohlížeč; když ho nemáš, spusť editor "
                    "bez --neotvirat) a počkej, až klikne na Odeslat úpravy." % r)
    if cervene:
        k.cervena(zprava, "poslechni si místa z kontroly; když je to špatně, uprav výběr v editoru a udělej náhled znovu."
                  + (" " + pokyn_editor if otevrit_editor else ""))
    else:
        k.zelena(zprava, pokyn_editor if otevrit_editor else
                 "podívej se na náhled. Řekni 'jo', nebo otevři editor (STUDIO editor --reel \"%s\")." % r,
                 {"nahled": str(mp4), "delka_s": osa["delka"], "otevrit_editor": bool(otevrit_editor)})
    reel.pripis_do_seznamu(s["reely"], r.name, projekt.nazev_reelu(r), "náhled %d" % n)
    _prubeh(r)
    return k.kod()


def _poloha_klipu(klip, slozka):
    """Poloha obličeje v klipu (místní program OpenCV), uložená v klip-n/poloha.json. Claude snímky nevidí."""
    from . import poloha

    soubor = Path(slozka) / "poloha.json"
    data = projekt.nacti_json(soubor)
    if data is None:
        shrnuti, vzorky = poloha.zmer_polohu(klip["cesta"])
        data = {"shrnuti": shrnuti, "vzorky": vzorky}
        projekt.uloz_json(soubor, data)
    return data


def _hook_opakuje_vetu(text, slova):
    """Říká nadpis totéž co věta (je v ní celý, bez interpunkce a velikosti písmen)? Pak by titulky byly dvakrát."""
    def norm(t):
        return " ".join(re.sub(r"[^\w\s]", " ", t.lower()).split())
    nadpis = norm(text or "")
    return bool(nadpis) and nadpis in norm(" ".join(w["w"] for w in slova))


def _vychozi_hook(text, max_slov=10):
    """Výchozí hook bez zadání: první věta reelu po první tečku, otazník nebo vykřičník, nejvýš max_slov slov."""
    import re as _re

    prvni = _re.split(r"(?<=[.?!])\s", text.strip(), maxsplit=1)[0] if text else ""
    slova = prvni.split()
    if len(slova) > max_slov:
        prvni = " ".join(slova[:max_slov])
    return prvni.rstrip(".,;:")


def _auto_mini(osa, vety_text, veta_slova, hook_veta, cta_veta, nejvic=3):
    """Mikro-nadpisy z vlastních slov zákaznice: krátké údernější věty (3 až 6 slov) nebo věty s číslem. NÁVRH."""
    out = []
    # krátká první věta (1,8 s, OVĚŘENO 25. 11. 2026): hook drží aspoň 2,6 s, mini nesmí naskočit pod ním
    konec_hooku = float((osa.get("hook") or {}).get("do") or 0.0)
    for u in osa["useky"]:
        for vid in u.get("vety", []):
            if vid in (hook_veta, cta_veta) or vid not in veta_slova:
                continue
            if veta_slova[vid][0]["start"] < konec_hooku + 0.2:
                continue
            txt = vety_text.get(vid, "").strip()
            slova = txt.rstrip(".!?").split()
            if (3 <= len(slova) <= 6) or (any(ch.isdigit() for ch in txt) and len(slova) <= 9):
                od = veta_slova[vid][0]["start"]
                out.append({"text": " ".join(slova), "styl": "mini", "efekt": "zleva", "od": round(od, 2),
                            "do": round(max(veta_slova[vid][-1]["end"] + 0.4, od + 2.2), 2), "veta": vid, "y": 0})
            if len(out) >= nejvic:
                return out
    return out


def krok_vzhled(a):
    """Hotový reel s textem: hook (nadpis), titulky po slovech, mikro-nadpisy, vsuvky, zoom, barevný filtr.
    Nastavení vzhledu reelu se ukládá do PRACOVNI/vzhled.json: další verze mění jen to, co zákaznice řekne."""
    import shutil
    from . import kontrola_reelu, poloha, render, titulky, umisteni, zoom

    r = _reel(a.reel)
    s = projekt.slozky(r)
    nast = projekt.nastaveni(r)
    k = Krok("Vzhled", s["pracovni"])
    plan_vsuvky = []                  # vsuvky z plánu (efekt Vsuvka z knihovny stylů)
    osa_soubor = s["pracovni"] / "casova-osa.json"
    if not osa_soubor.exists():
        k.cervena("ještě není náhled.", "nejdřív udělej náhled (STUDIO nahled --reel \"%s\")." % r)
        return k.kod()
    ulozeno = projekt.nacti_json(s["pracovni"] / "vzhled.json", {}) or {}
    zmen = titulky.pouzij_upravy(projekt.vzhled_upravy(r))
    if zmen:
        k.info("Stálé úpravy zákaznice („vždycky“): %d." % zmen)
    zmen_reel = titulky.pouzij_upravy(ulozeno.get("upravy"))      # úpravy jen pro tento reel (vzhled.json „upravy“)
    if zmen_reel:
        k.info("Úpravy vzhledu jen pro tento reel: %d." % zmen_reel)
    from . import styl as _styl
    styl_reelu = _styl.nacti(r)                                     # kód stylu z knihovny (krok styl); {} = jako dřív
    if styl_reelu.get("kod"):
        k.info("Styl z knihovny: %s." % styl_reelu["kod"][:100])
    styl = a.vzhled or ulozeno.get("vzhled") or nast.get("vzhled", "serif")
    titulky_z = a.titulky or ulozeno.get("titulky_z") or nast.get("titulky_z")
    for jm in (styl, titulky_z):
        if jm and jm not in titulky.STYLY:
            k.cervena("vzhled '%s' neznám." % jm, "použij jeden z: %s." % ", ".join(x for x in titulky.STYLY if "+" not in x))
            return k.kod()
    styl = titulky.kombinace(styl, titulky_z)
    t = time.time()
    osa = strih.nacti_osu(osa_soubor)
    klipy = projekt.nacti_klipy(r, s_energii=False)
    vety_text = {v["id"]: v["text"] for kl in klipy for v in kl["vety"]}
    veta_slova = {}
    for w in osa["slova"]:
        # velké písmeno uprostřed věty = vlastní jméno (Marcela, Claude, Canva): titulky ho nezmenší (Marcela 24. 11. 2026)
        if w["veta"] in veta_slova and re.match(r"^[\"„(]*[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]", w["w"]):
            w["jmeno"] = True
        veta_slova.setdefault(w["veta"], []).append(w)
    prvni = next((u["vety"][0] for u in osa["useky"] if u.get("vety")), None)
    # hook: zadaný, uložený, nebo první věta
    hook_text = a.hook or ulozeno.get("hook", {}).get("text") or (_vychozi_hook(vety_text.get(prvni, "")) if prvni else "")
    zvyraznit = a.zvyraznit or ulozeno.get("hook", {}).get("zvyraznit") or (max(hook_text.split(), key=len) if hook_text else None)
    if hook_text and not a.bez_hooku:
        h = veta_slova.get(prvni, [{"end": 2.6}])
        osa["hook"] = {"text": hook_text, "od": 0.1, "do": round(min(max(h[-1]["end"] + 0.4, 2.6), 5.0), 2)}
        if _hook_opakuje_vetu(hook_text, veta_slova.get(prvni, [])):
            osa["hook"]["skryt_titulky"] = True     # hook říká totéž co první věta, titulky by byly dvakrát
        if titulky.STYLY[styl]["hook"].get("podklad"):
            osa["hook"].update({"efekt": "pop", "zvyraznit": [zvyraznit] if zvyraznit else [], "marker_od": 0.35,
                                "velikost": titulky.STYLY[styl]["hook"]["velikost"]})
    else:
        osa["hook"] = None
    # mikro-nadpisy: uložené + nově zadané; poprvé automaticky z krátkých vět
    cta_veta = next((vid for u in osa["useky"] for vid in u.get("vety", []) if "komentá" in vety_text.get(vid, "").lower()), None)
    mini = [m for m in ulozeno.get("mini", []) if m.get("veta") in veta_slova or m.get("od") is not None]
    if (not ulozeno or ulozeno.get("jen_styl")) and not a.bez_mini and "mini" in titulky.STYLY[styl]:
        mini = _auto_mini(osa, vety_text, veta_slova, prvni, cta_veta)   # jen_styl: vzhled.json zatím zapsal jen krok styl
    for m in a.mini or []:
        text, _, vid = m.rpartition("@")
        if not text or vid not in veta_slova:
            k.cervena("mini nadpis '%s' nemá tvar text@číslo-věty, nebo věta není v reelu." % m, "zapiš třeba --mini \"Žádné nahrávání ven@k1-v05\".")
            return k.kod()
        od = veta_slova[vid][0]["start"]
        mini.append({"text": text.replace("\\n", "\n"), "styl": "mini", "efekt": "zleva", "od": round(od, 2),
                     "do": round(max(veta_slova[vid][-1]["end"] + 0.4, od + 2.2), 2), "veta": vid, "y": 0})
    for smaz in a.smaz_mini or []:
        mini = [m for m in mini if smaz.lower() not in m["text"].lower()]
    for m in mini:
        m.setdefault("velikost", titulky.STYLY[styl].get(m.get("styl", "mini"), {}).get("velikost", 46))
        if m.get("veta") in veta_slova:     # časy podle aktuální osy
            m["od"] = round(veta_slova[m["veta"]][0]["start"], 2)
            m["do"] = round(max(veta_slova[m["veta"]][-1]["end"] + 0.4, m["od"] + 2.2), 2)
    osa["mini"] = [m for m in mini if m.get("styl") != "mini_silny"]
    # výzva na konci: věta s „komentář“ jako tmavá karta místo titulků
    if cta_veta and "mini_silny" in titulky.STYLY[styl] and not a.bez_vyzvy:
        txt = vety_text[cta_veta].rstrip(".").split()
        pul = (len(txt) + 1) // 2
        text = (" ".join(txt[:pul]) + "\n" + " ".join(txt[pul:])) if len(txt) > 5 else " ".join(txt)
        slovo = next((w for w in txt if w.isupper() and len(w) > 2), None)
        osa["mini"].append({"text": text, "styl": "mini_silny", "efekt": "pop", "od": round(veta_slova[cta_veta][0]["start"], 2),
                            "do": round(min(osa["delka"], veta_slova[cta_veta][-1]["end"] + 1.2), 2), "veta": cta_veta,
                            "velikost": titulky.STYLY[styl]["mini_silny"]["velikost"], "y": 0, "skryt_titulky": True, "vyzva": True,
                            "zvyraznit": [slovo] if slovo else [], "marker_od": 0.5})
    osa["prvky"] = []
    osa["zvuky"] = []
    osa["prechody"] = []
    plan = projekt.nacti_json(s["pracovni"] / "plan-strihu.json") if a.plan else None
    if plan:
        from . import prvky as _prvky
        dostupne = set(_prvky.nacti_vsechny())
        osa["mini"] = []
        from . import zadani as _zadani
        # plán mohl vzniknout před výběrem stylu: efekty ze stylu, které v něm chybí, se doplní (nic se nepřepisuje)
        vety_planu = [{"id": vid_, "text": vety_text.get(vid_, ""), "od": veta_slova[vid_][0]["start"], "do": veta_slova[vid_][-1]["end"]}
                      for vid_ in dict.fromkeys(v_ for u in osa["useky"] for v_ in u.get("vety", [])) if vid_ in veta_slova]
        for zprava in _zadani.pridej_do_planu(r, plan["radky"], styl_reelu, vety_planu):
            k.info("Plán byl starší než styl, doplňuji: " + zprava)
        prvni_veta = next((rr["veta"] for rr in plan["radky"] if rr["veta"] in veta_slova), None)
        hook_radky = [rr for rr in plan["radky"] if rr["veta"] == prvni_veta and (rr["prvek"] in ("hook", "karty_slov") or rr["prvek"] in _zadani.NADPISY)]
        if a.bez_hooku:
            # zákaznice nadpis nechce: řádek nadpisu u první věty se vynechá
            plan["radky"] = [rr for rr in plan["radky"] if rr not in hook_radky]
            hook_radky = []
        elif a.hook:
            # text nadpisu potvrzený zákaznicí (krok 7c) má přednost před návrhem plánu
            slova_karet = (_zadani.nacti(r)["hodnoty"].get("karty_slov") or {}).get("slova")
            for rr in hook_radky:
                if rr["prvek"] == "karty_slov" and slova_karet:
                    continue            # karty slov rozdělené zákaznicí (krok podklady) se nepřepisují
                rr["obsah"] = " | ".join(a.hook.split()) if rr["prvek"] == "karty_slov" else a.hook
            if not hook_radky and prvni_veta:
                hr = {"veta": prvni_veta, "prvek": "hook", "obsah": a.hook, "duvod": "nadpis zákaznice"}
                plan["radky"].insert(0, hr)
                hook_radky = [hr]
        if not any(r["prvek"] in ("hook", "karty_slov") for r in plan["radky"]):
            osa["hook"] = None            # plán je závazný: bez řádku hook žádná karta hooku
        hook_efektu = a.hook or next((rr.get("obsah", "").replace(" | ", " ") for rr in hook_radky if rr.get("obsah")), None)
        kontext_efektu = {"vety": [{"id": vid_, "text": vety_text.get(vid_, ""), "od": veta_slova[vid_][0]["start"], "do": veta_slova[vid_][-1]["end"]}
                                   for vid_ in dict.fromkeys(v_ for u in osa["useky"] for v_ in u.get("vety", [])) if vid_ in veta_slova],
                          "delka_reelu": osa["delka"], "delka_videa": sum(float(kl.get("delka") or 0) for kl in klipy),
                          "klipy": klipy, "hook_text": hook_efektu, "styl_vzhledu": titulky.STYLY[styl], "radky": plan["radky"]}
        nesestavene = []
        k.info("Stavím podle plánu střihu (%d řádků)." % len(plan["radky"]))
        for rad in plan["radky"]:
            if rad.get("zkontrolovat"):
                k.info("⚠️ Věta %s: %s (dřív „%s“, teď „%s“). Prvek %s zůstal u ní, zkontroluj ho." % (
                    rad["veta"], rad["zkontrolovat"], rad.get("text_drive", ""), rad["text"], rad["prvek"]))
        for rad in plan.get("bez_vety", []):
            k.info("⚠️ Prvek %s (%s) nemá větu, do videa nejde. Přiřaď ho jiné větě, nebo odlož." % (rad["prvek"], rad.get("obsah", "")))
        for rad in plan["radky"]:
            vid, prvek, obsah = rad["veta"], rad["prvek"], rad.get("obsah", "")
            if vid not in veta_slova:
                continue
            od_v, do_v = veta_slova[vid][0]["start"], veta_slova[vid][-1]["end"]
            # volitelně v řádku plánu: "slovo": prvek začne 0,3 s před tím slovem věty; "trvani": délka v sekundách
            if rad.get("slovo"):
                cil = str(rad["slovo"]).lower().strip(".,!?")
                w = next((x for x in veta_slova[vid] if x["w"].lower().strip(".,!?") == cil), None)
                if w:
                    od_v = max(0.1, w["start"] - 0.3)
            if rad.get("cas") is not None:
                od_v = float(rad["cas"])      # přesný začátek v sekundách reelu (třeba když zvedne prst)
            if rad.get("trvani"):
                do_v = od_v + float(rad["trvani"]) - 0.3
            n_mini0, n_prv0 = len(osa["mini"]), len(osa["prvky"])
            if prvek in _zadani.KARTY:
                # efekt z knihovny stylů (Marcela 23. 11. 2026): podklady od zákaznice, sestavení v zadani.py
                kontext_efektu["slova_vety"] = veta_slova[vid]
                spec_e, duvod_e = _zadani.sestav_spec(r, prvek, rad, od_v, do_v, kontext_efektu)
                if spec_e is None:
                    nesestavene.append("%s u věty %s: %s" % (_styl.PRVKY_TEXT.get(prvek, prvek), vid, duvod_e))
                else:
                    osa["prvky"].extend(spec_e if isinstance(spec_e, list) else [spec_e])
                continue
            if prvek == "karty_slov" and "karty_slov" in dostupne:
                karty = [c.strip() for c in obsah.split("|") if c.strip()]
                osa["hook"] = None
                osa["prvky"].append({"typ": "karty_slov", "od": max(0.1, od_v), "do": round(min(od_v + max(1.0, 1.0 * len(karty)), do_v + 0.3), 2),
                                     "karty": karty, "skryt_titulky": True})
            elif prvek == "hook" and titulky.STYLY[styl].get("karty_slov", {}).get("za_hlavou") and "karty_slov" in dostupne:
                # vzhled s hookem po frázích přes celou obrazovku (vogue): hook se rozdělí podle interpunkce,
                # poslední fráze po slovech, ať má každá karta jiný řez
                import re as _re
                fraze = [f.strip() for f in _re.split(r"[.!?,]+", obsah) if f.strip()]
                if len(fraze) <= 2 and fraze:
                    fraze = fraze[:-1] + fraze[-1].split()
                osa["hook"] = None
                osa["prvky"].append({"typ": "karty_slov", "od": max(0.1, od_v), "do": round(min(od_v + max(1.2, 0.9 * len(fraze)), do_v + 0.3), 2),
                                     "karty": fraze, "skryt_titulky": True, "casomira": True})
            elif prvek == "hook":
                # titulky schovat, jen když nadpis říká totéž co věta (24. 11. 2026: vlastní nadpis Marcely
                # „Přesně ten produkt…“ nad jinou první větou schoval titulky na prvních 5 s)
                osa["hook"] = {"text": obsah, "od": 0.1, "do": round(min(max(do_v + 0.4, 2.6), 5.0), 2),
                               "skryt_titulky": _hook_opakuje_vetu(obsah, veta_slova[vid])}
                if titulky.STYLY[styl]["hook"].get("podklad"):
                    osa["hook"].update({"efekt": "pop", "zvyraznit": [max(obsah.split(), key=len)], "marker_od": 0.35,
                                        "velikost": titulky.STYLY[styl]["hook"]["velikost"]})
            elif prvek == "mini" and ("/" in obsah or (len(obsah) > 2 and obsah.startswith("*") and obsah.endswith("*"))):
                # i jeden řádek mezi hvězdičkami (*MÁLO ČASU*) je velký nadpis nad hlavou, hvězdičky se nekreslí
                # řádky oddělené lomítkem; řádek mezi hvězdičkami je velký, ostatní malé (Marcela 20. 10.)
                radky_o = [x.strip() for x in obsah.split("/") if x.strip()]
                rs, cisty = [], []
                for radek_t in radky_o:
                    velky = radek_t.startswith("*") and radek_t.endswith("*") and len(radek_t) > 2
                    cisty.append(radek_t.strip("*").strip())
                    maly = titulky.STYLY[styl].get("mini_podpis") or {"pomer": 0.45, "pismo": "Montserrat-wght.ttf", "varianta": "Medium"}
                    rs.append({"pomer": 1.0} if velky else dict(maly))
                st_n = "mini_nahore" if "mini_nahore" in titulky.STYLY[styl] else "mini"
                zakl = titulky.STYLY[styl].get(st_n, {}).get("velikost", 64)
                vel = str(rad.get("velikost", "")).strip()        # „130%“ = o 30 % větší, „96“ = px (Marcela 20. 10.)
                velikost_n = int(round(zakl * float(vel[:-1]) / 100)) if vel.endswith("%") else (int(vel) if vel.isdigit() else zakl)
                osa["mini"].append({"text": "\n".join(cisty), "radky_styl": rs, "styl": st_n, "efekt": "zleva", "od": round(od_v, 2),
                                    "do": round(max(do_v + 0.4, od_v + 2.2), 2), "veta": vid, "velikost": velikost_n,
                                    "velikost_zadana": velikost_n, "y": 0, "nahore": bool(rad.get("nahore"))})
                if rad.get("postupne"):
                    # řádky naskakují postupně, každý když zazní jeho první slovo, pak zůstanou všechny spolu
                    # (Marcela 24. 11. 2026: „Captions, CapCut, Canva postupně, pak všechno najednou“)
                    def _koren(t):
                        return re.sub(r"[^\w]", "", t.lower())[:4]
                    zp, hledej_od = [], 0
                    for i_r, radek_t in enumerate(cisty):
                        cil = _koren(radek_t.split()[0]) if radek_t.split() else ""
                        sl_v = [w for w in osa["slova"] if w["start"] >= od_v - 0.05]   # i slova dalších vět
                        j = next((j for j in range(hledej_od, len(sl_v)) if cil and _koren(sl_v[j]["w"]) == cil), None)
                        if j is None:
                            zp.append(round((zp[-1] if zp else 0.0) + 0.5, 2) if zp else 0.0)
                        else:
                            zp.append(round(max(zp[-1] if zp else 0.0, sl_v[j]["start"] - od_v), 2))
                            hledej_od = j + 1
                    if len(cisty) == 1:
                        # jeden řádek: naskakují slova (bez oddělovačů), řádek stojí na místě
                        slova_r = [x for x in cisty[0].split() if x.strip("·•|–-")]
                        zp, hledej_od = [], 0
                        for slovo_r in slova_r:
                            cil = _koren(slovo_r)
                            j = next((j for j in range(hledej_od, len(sl_v)) if cil and _koren(sl_v[j]["w"]) == cil), None)
                            if j is None:
                                zp.append(round((zp[-1] + 0.5) if zp else 0.0, 2))
                            else:
                                zp.append(round(max(zp[-1] if zp else 0.0, sl_v[j]["start"] - od_v), 2))
                                hledej_od = j + 1
                        osa["mini"][-1]["radky_styl"][0]["slova_od"] = zp
                    else:
                        osa["mini"][-1]["zpozdeni_radku"] = zp
                    osa["mini"][-1]["do"] = round(max(osa["mini"][-1]["do"], od_v + zp[-1] + 1.5), 2)
                if any(r.get("psani") for r in rs):
                    # řádek psaný po písmenech začne, až velký řádek dojede (Marcela 29. 10., vzor se zvukem klávesnice)
                    osa["mini"][-1]["zpozdeni_radku"] = [0.35 if r.get("psani") else 0.0 for r in rs]
            elif prvek == "mini":
                slova_o = obsah.rstrip(".").split()
                text = (" ".join(slova_o[:(len(slova_o) + 1) // 2]) + "\n" + " ".join(slova_o[(len(slova_o) + 1) // 2:])) if len(slova_o) > 4 else obsah
                osa["mini"].append({"text": text, "styl": "mini", "efekt": "zleva", "od": round(od_v, 2), "do": round(max(do_v + 0.4, od_v + 2.2), 2),
                                    "veta": vid, "velikost": titulky.STYLY[styl].get("mini", {}).get("velikost", 46), "y": 0})
            elif prvek == "wow":
                slova_w = obsah.rstrip(".").split()
                if len(slova_w) > 3 and "\n" not in obsah:
                    pul = (len(slova_w) + 1) // 2
                    obsah = " ".join(slova_w[:pul]) + "\n" + " ".join(slova_w[pul:])
                osa["mini"].append({"text": obsah, "styl": "mini_silny", "efekt": "pop", "od": round(od_v, 2), "do": round(do_v + 1.5, 2), "veta": vid,
                                    "velikost": titulky.STYLY[styl].get("mini_silny", {}).get("velikost", 62), "y": 0, "skryt_titulky": True,
                                    "zvyraznit": [max(obsah.split(), key=len)], "marker_od": 0.4})
            elif prvek == "vyzva" and "/" in obsah:
                # řádky oddělené lomítkem, řádek mezi hvězdičkami je slovo pro komentář: větší (Marcela 29. 10.:
                # „REEL na druhý řádek a větší“, jinak sahá k pravé liště Instagramu)
                radky_v = [x.strip() for x in obsah.split("/") if x.strip()]
                velke = [r.startswith("*") and r.endswith("*") and len(r) > 2 for r in radky_v]
                cisty_v = [r.strip("*").strip() for r in radky_v]
                slovo = next((c for c, v in zip(cisty_v, velke) if v), None)
                osa["mini"].append({"text": "\n".join(cisty_v), "radky_styl": [{"pomer": 1.6} if v else {"pomer": 1.0} for v in velke],
                                    "styl": "mini_silny", "efekt": "pop", "od": round(od_v, 2), "do": round(min(osa["delka"], do_v + 1.2), 2),
                                    "veta": vid, "velikost": titulky.STYLY[styl].get("mini_silny", {}).get("velikost", 62), "y": 0,
                                    "skryt_titulky": True, "zvyraznit": [slovo] if slovo else [], "marker_od": 0.5})
            elif prvek == "vyzva":
                txt = obsah.rstrip(".").split()
                pul = (len(txt) + 1) // 2
                slovo = next((w.strip(".,!") for w in txt if w.strip(".,!").isupper() and len(w) > 2), None)
                osa["mini"].append({"text": (" ".join(txt[:pul]) + "\n" + " ".join(txt[pul:])) if len(txt) > 5 else " ".join(txt), "styl": "mini_silny",
                                    "efekt": "pop", "od": round(od_v, 2), "do": round(min(osa["delka"], do_v + 1.2), 2), "veta": vid,
                                    "velikost": titulky.STYLY[styl].get("mini_silny", {}).get("velikost", 62), "y": 0, "skryt_titulky": True,
                                    "vyzva": True, "zvyraznit": [slovo] if slovo else [], "marker_od": 0.5})
            elif prvek == "vsuvka" and obsah:
                plan_vsuvky.append("%s@%s" % (obsah, vid))
            elif prvek == "zprava" and "zprava" in dostupne:
                osa["prvky"].append({"typ": "zprava", "od": round(od_v, 2), "do": round(max(do_v + 0.8, od_v + 3.5), 2), "text": obsah, "komu": "PRO CLAUDA"})
            elif prvek == "vlozka" and "vlozka" in dostupne and obsah:
                # obsah: „soubor | štítek | vyrez=stred“ (štítek i výřez nepovinné; výřez nahore / stred / dole)
                dily = [x.strip() for x in obsah.split("|")]
                soubor, zbytek = dily[0], dily[1:]
                # nahrávka obrazovky smí zůstat déle (vložka z videa bere nejvýš 8 s), obrázek nejvýš 5 s
                nejdel = 8.0 if soubor.lower().endswith((".mp4", ".mov")) else 5.0
                pv = {"typ": "vlozka", "od": round(od_v, 2), "do": round(min(max(do_v + 0.4, od_v + 2.5), od_v + nejdel), 2),
                      "soubor": soubor, "efekt": "pop"}
                for d_ in zbytek:
                    if d_.lower().startswith("vyrez="):
                        pv["vyrez"] = d_.split("=", 1)[1].strip().lower()
                    elif d_:
                        pv["nazev"] = d_
                if rad.get("do_konce"):
                    # obrázek zůstane až do konce reelu (Marcela 24. 11. 2026: screenshot profilu do úplného konce)
                    pv["do"], pv["do_konce"] = round(osa["delka"], 2), True
                osa["prvky"].append(pv)
            elif prvek == "velke_slovo" and obsah:
                # jedno velké slovo ve chvíli, kdy ho řekne (Marcela 19. 10.: „nadpis“ jako z časopisu)
                cil = obsah.split()[0].lower().strip(".,!?")
                w = next((x for x in veta_slova[vid] if x["w"].lower().strip(".,!?") == cil), None)
                od_s = w["start"] if w else od_v
                osa.setdefault("zvuky", []).append({"typ": "whoosh", "cas": round(max(0.0, od_s - 0.05), 2), "db": -17})
                osa["mini"].append({"text": obsah.upper(), "styl": "slovo_velke", "efekt": "pop", "od": round(od_s, 2),
                                    "do": round(min(osa["delka"], od_s + 1.8), 2), "veta": vid,
                                    "velikost": titulky.STYLY[styl].get("slovo_velke", {}).get("velikost", 150), "y": 0,
                                    "skryt_titulky": False})
            elif prvek == "karticky" and "karticky" in dostupne and obsah:
                soubory = [x.strip() for x in obsah.split("|") if x.strip() and not x.strip().lower().startswith("vyrez=")]
                pv = {"typ": "karticky", "od": round(od_v, 2), "do": round(min(max(do_v + 0.4, od_v + 2.5), od_v + 5.0), 2), "soubory": soubory}
                vyrez = next((x.strip().split("=", 1)[1] for x in obsah.split("|") if x.strip().lower().startswith("vyrez=")), None)
                if vyrez:
                    pv["vyrez"] = vyrez
                osa["prvky"].append(pv)
            elif prvek == "orbit" and "orbit" in dostupne and obsah:
                # obálky reelů krouží kolem osoby (hook); obsah: „soubor | soubor | …“ nebo „*“ = všechny obálky z podkladů
                if obsah.strip() == "*":
                    podkl = Path(plan.get("podklady", ""))
                    soubory = sorted(str(x) for x in podkl.glob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))[:8]
                else:
                    soubory = [x.strip() for x in obsah.split("|") if x.strip()][:8]
                if len(soubory) >= 4:
                    # titulky se po dobu prstenu schovají (prsten jede ve výšce hrudi, kde jsou titulky)
                    osa["prvky"].append({"typ": "orbit", "od": round(max(0.1, od_v), 2), "do": round(min(od_v + 4.5, do_v + 0.3), 2), "soubory": soubory,
                                         "skryt_titulky": True})
                else:
                    k.info("Orbit u věty %s vynechán: potřebuje aspoň 4 obálky, v plánu jsou %d." % (vid, len(soubory)))
            elif prvek == "zed" and "zed" in dostupne and obsah:
                # Instagram zeď: mřížka obálek za osobou; obsah „*“ = všechny obrázky z podkladů, nebo seznam souborů
                if obsah.strip() == "*":
                    podkl = Path(plan.get("podklady", ""))
                    soubory = sorted(str(x) for x in podkl.glob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))[:12]
                else:
                    soubory = [x.strip() for x in obsah.split("|") if x.strip()][:12]
                if len(soubory) >= 4:
                    od_z, do_z = round(max(0.1, od_v), 2), round(min(osa["delka"], do_v + 0.3, od_v + 6.0), 2)
                    osa["prvky"].append({"typ": "zed", "od": od_z, "do": do_z, "soubory": soubory,
                                         "pozadi": True})     # pozadí za osobou: titulky a jiné texty přes ně smějí
                    # zvuk: svist při vyjetí mřížky, ťuknutí při dopadu zpět (Marcela 20. 10.)
                    osa.setdefault("zvuky", []).append({"typ": "whoosh", "cas": od_z, "db": -17})
                    osa["zvuky"].append({"typ": "klik", "cas": round(max(od_z, do_z - 0.1), 2), "db": -20})
                else:
                    k.info("Instagram zeď u věty %s vynechána: potřebuje aspoň 4 obálky, v plánu jsou %d." % (vid, len(soubory)))
            elif prvek == "stitky" and "stitky" in dostupne and obsah:
                # štítky: 2 až 5 pilulek naskočí po sobě (Marcela 21. 10.: REEL / CAROUSEL / NEWSLETTER); každá u svého slova věty, jinak po 0,35 s
                texty = [x.strip() for x in obsah.replace("/", "|").split("|") if x.strip()][:5]
                if len(texty) >= 2:
                    casy, dalsi = [], od_v
                    for txt in texty:
                        w = next((x for x in veta_slova[vid] if x["w"].lower().strip(".,!?") == txt.lower()), None)
                        c = max(od_v, w["start"] - 0.1) if w else dalsi
                        c = max(c, casy[-1] + 0.2) if casy else c
                        casy.append(round(c, 2))
                        dalsi = c + 0.35
                    pv = {"typ": "stitky", "od": round(max(0.1, casy[0]), 2), "do": round(min(osa["delka"], max(do_v + 0.4, casy[-1] + 1.2)), 2),
                          "texty": texty, "casy": casy}
                    if rad.get("y") is not None:
                        pv["y"] = int(rad["y"])
                    osa["prvky"].append(pv)
                    for c in casy:
                        osa.setdefault("zvuky", []).append({"typ": "klik", "cas": c, "db": -20})
                else:
                    k.info("Štítky u věty %s vynechány: potřebují aspoň 2 texty." % vid)
            elif prvek == "prulet":
                # průlet střihem: věta musí začínat tvrdým střihem (hranice úseku); kamera se ponoří do osoby a vynoří v dalším záběru
                hranice = [round(float(u.get("vystup_od", 0.0)), 3) for u in osa["useky"][1:]]
                blizko = [h for h in hranice if abs(h - od_v) <= 0.45]
                if blizko:
                    cas = min(blizko, key=lambda h: abs(h - od_v))
                    pv = {"typ": "prulet", "cas": cas, "veta": vid}
                    for klic in ("hloubka", "strmost", "naklon", "pul"):
                        if rad.get(klic) is not None:
                            pv[klic] = float(rad[klic]) if klic != "pul" else int(rad[klic])
                    osa.setdefault("prechody", []).append(pv)
                    # svist začíná těsně před střihem, vrchol síly na střihu
                    osa.setdefault("zvuky", []).append({"typ": "whoosh", "cas": round(max(0.0, cas - 0.2), 2), "db": -15})
                else:
                    k.info("Průlet u věty %s vynechán: věta nezačíná střihem (nejbližší střih je dál než 0,45 s)." % vid)
            elif prvek == "mrizka" and "mrizka" in dostupne:
                podkl = Path(plan.get("podklady", ""))
                soubory = sorted(str(x) for x in podkl.glob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))[:9]
                if len(soubory) >= 5:
                    osa["prvky"].append({"typ": "mrizka", "od": round(od_v, 2), "do": round(max(do_v + 0.3, od_v + 2.5), 2), "soubory": soubory, "sloupce": 3})
            elif prvek == "zapisnik" and "zapisnik" in dostupne and obsah:
                # „Nadpis: položka | položka | položka“ (nadpis volitelný); položka se odškrtne, když zazní její
                # první slovo (stejný začátek slova, hledá se po dobu karty, i v dalších větách, Marcela 29. 10.);
                # položka, která nezazní, se odškrtne 0,7 s po předchozí
                prvni = obsah.split("|")[0]
                nadpis_z, zbytek = (prvni.split(":", 1)[0].strip(), obsah.split(":", 1)[1]) if ":" in prvni else ("", obsah)
                polozky_z = [x.strip() for x in zbytek.split("|") if x.strip()]

                def _koren(s):
                    return s.lower().strip(".,!?;:„“\"")[:4]

                slova_z = [w for w in osa["slova"] if od_v - 0.05 <= w["start"] <= do_v]
                casy_z, j = [], 0
                for pol in polozky_z:
                    cil = _koren(pol.split()[0])
                    w = next((i for i in range(j, len(slova_z)) if _koren(slova_z[i]["w"]) == cil), None)
                    if w is None:
                        casy_z.append(round((casy_z[-1] if casy_z else od_v + 0.1) + 0.7, 2))
                    else:
                        casy_z.append(round(slova_z[w]["start"], 2))
                        j = w + 1
                do_z = max(do_v + 0.6, casy_z[-1] + 1.2)
                # nadpis u stejné věty má přednost: karta vyjede až po něm (obojí nahoře by se překrylo)
                od_z = max([max(0.1, od_v - 0.2)] + [m["do"] + 0.1 for m in osa["mini"] if m.get("veta") == vid])
                spec_z = {"typ": "zapisnik", "od": round(od_z, 2), "do": round(min(osa["delka"], do_z), 2),
                          "nadpis": nadpis_z, "polozky": polozky_z}
                if casy_z:
                    spec_z["casy"] = casy_z
                osa["prvky"].append(spec_z)
            elif prvek == "nalepky" and "nalepky" in dostupne:
                slova_p = [x.strip() for x in obsah.split(",") if x.strip()]
                # štítky nesou slova samy, titulky se po tu dobu schovají (jinak se s nimi ve spodní části potkají)
                osa["prvky"].append({"typ": "nalepky", "od": round(od_v, 2), "do": round(max(do_v + 0.4, od_v + 2.2), 2), "preskrtnout": slova_p, "stitky": [],
                                     "skryt_titulky": True})
            # volitelné doplňky řádku (2. 11.): "x"/"y" = pevná poloha nadpisu (střed x, horní okraj y, třeba nad prstem),
            # "efekt" = nástup nadpisu, "zvuk" = zvuk na začátku prvku (typ ze zvuky.ZVUKY, "zvuk_db"),
            # "skoky" = rychlé přiblížení na slovech: [["slovo", násobek], ...] na 0,3 s (jako střihy na detail)
            for m in osa["mini"][n_mini0:]:
                if rad.get("x") is not None:
                    m["x"] = int(rad["x"])
                if rad.get("y") is not None:
                    m["pevne_y"] = int(rad["y"])
                if rad.get("efekt"):
                    m["efekt"] = rad["efekt"]
                if rad.get("barva"):
                    m["radky_styl"] = [dict(r, barva=tuple(rad["barva"])) for r in (m.get("radky_styl") or [{"pomer": 1.0}])]
            for pv in osa["prvky"][n_prv0:]:
                if rad.get("oblast"):
                    pv["oblast"] = [int(v) for v in rad["oblast"]]      # kam prvek patří, třeba pás nad hlavou
                    pv["pevna_oblast"] = bool(rad.get("pevna_oblast"))
            novy = (osa["mini"][n_mini0:] + osa["prvky"][n_prv0:])
            if rad.get("zvuk"):
                cas_z = novy[0]["od"] if novy else od_v
                osa.setdefault("zvuky", []).append({"typ": rad["zvuk"], "cas": round(max(0.0, cas_z), 2), "db": float(rad.get("zvuk_db", -16))})
            for slovo_s, nas in rad.get("skoky") or []:
                w = next((x for x in veta_slova[vid] if x["w"].lower().strip(".,!?").startswith(str(slovo_s).lower())), None)
                if w:
                    osa.setdefault("skoky_zoom", []).append({"od": round(w["start"], 2), "do": round(w["start"] + float(rad.get("skok_s", 0.3)), 2),
                                                             "nasobek": float(nas)})
                    if rad.get("zvuk_skoku"):
                        osa.setdefault("zvuky", []).append({"typ": rad["zvuk_skoku"], "cas": round(w["start"], 2), "db": -14})
        # prvek u první věty (vedle hooku) začne až 0,2 s po konci hooku nebo karet slov
        nadpisove_typy = {"karty_slov", "skladany_nadpis", "hravy_nadpis"}
        hook_do = max([x["do"] for x in osa["prvky"] if x["typ"] in nadpisove_typy and x["od"] < 1.0] + ([osa["hook"]["do"]] if osa.get("hook") else [0.0]))
        for x in osa["prvky"]:
            if x["typ"] not in nadpisove_typy and x["typ"] not in PRVKY_POZADI and x["od"] < hook_do:
                trv = x["do"] - x["od"]
                x["od"] = round(hook_do + 0.2, 2)
                x["do"] = round(min(osa["delka"], x["od"] + max(2.5, trv)), 2)
        # nadpis u věty, kde zároveň běží obrázkový prvek (mřížka, kartičky, vložka), počká, až prvek skončí;
        # když by pak trval pod 1 s, vynechá se (dvě těžké grafiky najednou ne, zadání 19. 10. oddíl 3)
        obrazkove = [x for x in osa["prvky"] if x["typ"] in ("mrizka", "karticky", "vlozka")]
        zbyle = []
        for m in osa["mini"]:
            kol = [x for x in obrazkove if x["od"] < m["do"] and x["do"] > m["od"] and x["od"] <= m["od"] + 0.3]
            if kol:
                nove_od = round(max(x["do"] for x in kol) + 0.1, 2)
                if m["do"] - nove_od < 1.0 and m.get("styl") != "mini_silny":
                    continue
                m["od"], m["do"] = nove_od, round(max(m["do"], nove_od + 1.8), 2)
            zbyle.append(m)
        osa["mini"] = zbyle
        # dva texty se v čase nepřekrývají: nadpis končí 0,1 s před dalším prvkem nebo nadpisem
        zacatky = sorted(x["od"] for x in osa["mini"] + osa["prvky"] if x.get("typ") not in PRVKY_POZADI)
        for m in osa["mini"] + [x for x in osa["prvky"] if x["typ"] not in PRVKY_BEZ_ZKRACENI and not x.get("do_konce")]:
            dalsi = next((z for z in zacatky if z > m["od"] + 0.5), None)
            if dalsi is not None and m["do"] > dalsi - 0.1:
                m["do"] = round(max(m["od"] + 1.0, dalsi - 0.1), 2)
        # Tlačítko Sledovat leží na hrudi jako karta výzvy: naskočí až po ní (konec reelu), výzva se případně zkrátí
        for sl in [x for x in osa["prvky"] if x["typ"] == "ig_sledovat"]:
            vyzvy = [m for m in osa["mini"] if (m.get("vyzva") or m.get("styl") == "mini_silny") and m["od"] < sl["do"] and m["do"] > sl["od"]]
            if vyzvy:
                start = min(max(m["do"] for m in vyzvy) + 0.1, osa["delka"] - 2.6)
                for m in vyzvy:
                    m["do"] = round(max(m["od"] + 1.0, min(m["do"], start - 0.1)), 2)
                sl["od"], sl["do"] = round(max(sl["od"], start), 2), round(osa["delka"], 2)
        if "casomira" in (styl_reelu.get("prvky") or []) and "casomira" not in _zadani.nacti(r)["vynechat"]:
            # tikající čas pod nadpisem (knihovna: „Tikající čas pod hookem“), u karty hooku i u nadpisových efektů
            nadpis_c = next((x for x in osa["prvky"] if x["typ"] in ("karty_slov", "skladany_nadpis", "hravy_nadpis")), None)
            if nadpis_c is not None:
                nadpis_c["casomira"] = True
            elif osa.get("hook"):
                osa["hook"]["casomira"] = True
        if osa.get("hook") and any(x["typ"] == "vypinac_plakat" and x.get("vypinac") and x["od"] < 1.0 for x in osa["prvky"]):
            # úvod se zdí a vypínačem: plakát je nadpis, karta nadpisu by se s vypínačem překryla
            osa["hook"] = None
            k.info("Úvod je vypínač s plakátem: plakát je nadpis, kartu nadpisu nedávám.")
        karty_hook = [x for x in osa["prvky"] if x["typ"] == "karty_slov"]
        hook_text = osa["hook"]["text"] if osa.get("hook") else (" | ".join(karty_hook[0]["karty"]) if karty_hook else "")
        nadpis_efekt = next((x for x in osa["prvky"] if x["typ"] in ("skladany_nadpis", "hravy_nadpis")), None)
        if not hook_text and nadpis_efekt:
            hook_text = " ".join(rr["text"] for rr in nadpis_efekt.get("radky", [])) or nadpis_efekt.get("text", "")
        if plan.get("filtr_od_vety") in veta_slova:
            osa["filtr_od"] = round(veta_slova[plan["filtr_od_vety"]][0]["start"], 2)
            k.info("Barevný filtr od věty %s (%.1f s)." % (plan["filtr_od_vety"], osa["filtr_od"]))
    osa["vsuvky"] = []
    for vs in (a.vsuvka or []) + ulozeno.get("vsuvky", []) + plan_vsuvky:
        text, _, vid = vs.rpartition("@")
        if not text or vid not in veta_slova:
            k.cervena("vsuvka '%s' nemá tvar text@číslo-věty, nebo věta není v reelu." % vs, "zapiš třeba --vsuvka \"SPF *30*@k1-v05\".")
            return k.kod()
        od = veta_slova[vid][0]["start"]
        osa["vsuvky"].append({"text": text, "od": round(od, 2), "do": round(min(od + 2.4, veta_slova[vid][-1]["end"] + 0.6), 2)})
    # b-roll pod hlasem (prekryvy.py, zabery.py): chvilky ze záběrů v PODKLADY-SEM/B-ROLL (a stálé knihovny MOJE-ZABERY
    # podle přiřazení) přes celý obraz, hlas běží dál
    from . import prekryvy as _pk
    osa["prekryvy"] = []
    ulozene_prani = [] if a.zrus_broll else ulozeno.get("broll", [])
    broll_prani = list(dict.fromkeys((a.broll or []) + ulozene_prani))
    jen_hlas = bool(a.jen_hlas or (ulozeno.get("jen_hlas") and not a.s_tvari)) and not a.bez_brollu
    bez_zvuku_zaberu = bool(a.bez_zvuku_zaberu or (ulozeno.get("bez_zvuku_zaberu") and not a.se_zvukem_zaberu))
    if not a.bez_brollu:
        chvilky, popsane = _chvilky_reelu(r, a, k, s["pracovni"] / "zabery")
        poradi_vet = list(dict.fromkeys(vid for u in osa["useky"] for vid in u.get("vety", []) if vid in veta_slova))
        prirazeni = {}
        for b_ in broll_prani:
            jm, _, kde = b_.rpartition("@")
            jm, vid = jm.strip(), kde.strip()
            cil = next((c["id"] for c in chvilky if c["id"].lower() == jm.lower()), None) or \
                next((c["soubor"] for c in chvilky if Path(c["soubor"]).name.lower() == jm.lower()), None)
            if vid.isdigit() and 0 < int(vid) <= len(poradi_vet):
                vid = poradi_vet[int(vid) - 1]
            if cil is None or vid not in veta_slova:
                k.cervena("b-roll '%s' neznám: chvilka nebo záběr musí být v katalogu (B-ROLL nebo MOJE-ZABERY) a věta v reelu." % b_,
                          "zapiš třeba --broll \"kavarna-kava@4\" (název chvilky nebo souboru @ číslo věty), názvy vypíše STUDIO zabery.")
                return k.kod()
            prirazeni[vid] = cil
        auto = [c for c in chvilky if not c.get("jen_prirazeni")]
        if auto or prirazeni:
            vyhradit = {cta_veta} | {m.get("veta") for m in osa.get("mini", []) if m.get("vyzva")}
            osa["prekryvy"] = _pk.naplanuj([(vid, veta_slova[vid]) for vid in poradi_vet], chvilky, prirazeni,
                                           jen_hlas, osa["delka"], vyhradit, osa.get("tempo", "bezne"))
            osa["zvuk_zaberu"] = not bez_zvuku_zaberu
            if osa["prekryvy"]:
                stabu = sum(1 for x in osa["prekryvy"] if x["pohyb"].startswith("stab"))
                drzene = [x for x in osa["prekryvy"] if not x["pohyb"].startswith("stab")]
                n_ = len(drzene)
                k.info("B-roll pod hlasem: %d %s, celkem %.1f s%s%s%s (%s)." % (
                    n_, "záběr" if n_ == 1 else "záběry" if 2 <= n_ <= 4 else "záběrů", sum(x["do"] - x["od"] for x in osa["prekryvy"]),
                    ", celý reel jen hlas" if jen_hlas else "",
                    (", rychlý začátek %d střihů" % stabu) if stabu else "",
                    "" if bez_zvuku_zaberu else ", zvuk záběrů tiše pod hlasem",
                    ", ".join("%s %.1f–%.1f s" % (x["chvilka"], x["od"], x["do"]) for x in drzene)))
                if chvilky and not popsane:
                    k.info("Chvilky zatím nemají popis, rozmístil jsem je podle kvality. Podle smyslu vět je přiřadíš po "
                           "STUDIO zabery (náhledy v PRACOVNI/zabery).")
            else:
                k.info("Záběry v B-ROLL jsou, ale v reelu pro ně není volná věta (první věta a výzva zůstávají s tváří).")
        elif jen_hlas:
            k.cervena("režim jen hlas potřebuje použitelné záběry ve složce PODKLADY-SEM/B-ROLL (nebo přiřazené z MOJE-ZABERY).",
                      "řekni zákaznici, ať do té složky dá aspoň dva záběry, a spusť vzhled znovu.")
            return k.kod()
    # poloha obličeje v každém klipu (místní měření, s uložením)
    vzorky = []
    for kl in klipy:
        data = _poloha_klipu(kl, kl["slozka"])
        vzorky.append(poloha.pevne(data["vzorky"]))
    pouzit_zoom = a.zoom or ulozeno.get("zoom", False)
    if pouzit_zoom:
        rozmery = [poloha.rozmer_klipu(kl["cesta"])[:2] for kl in klipy]
        zoom.plan_zoomu(osa, rozmery, vzorky)
        # při vložce a mřížce obraz žije prvkem, ne přibližováním (kniha střihu, část 8): zoom zpět na 1,0
        # totéž u nadpisů nad hlavou a velkých slov: přiblížený záběr by jim sebral místo nad hlavou
        s_prvkem = [pv for pv in osa.get("prvky", []) if pv["typ"] in ("vlozka", "mrizka", "zed", "orbit")] + list(osa.get("mini", []))
        for c in osa.get("casti", []):
            if any(c["vystup_od"] < pv["do"] and c["vystup_od"] + c["delka"] > pv["od"] for pv in s_prvkem):
                c["zoom"], c["posun_x"], c["posun_y"] = 1.0, 0.0, 0.0
    elif titulky.STYLY[styl].get("najezd"):
        # vzhled se souvislým pomalým přiblížením přes celý reel (jedno_slovo)
        zoom.plan_najezd(osa, *titulky.STYLY[styl]["najezd"])
        k.info("Pomalé přiblížení přes celý reel: %.2f → %.2f." % tuple(titulky.STYLY[styl]["najezd"]))
    obl = poloha.obliceje_ve_vystupu(osa, vzorky)
    styl_pouzity = umisteni.titulky_mimo_oblicej(osa, styl, obl)
    if osa.get("titulky_uprava"):
        u = osa["titulky_uprava"]
        k.info("Titulky by zakrývaly obličej, posouvám je ke spodnímu okraji%s." % (
            "" if u["velikost"] == u["puvodne"][1] else " a zmenšuju písmo (%d místo %d)" % (u["velikost"], u["puvodne"][1])))
    varovani = umisteni.umisti(osa, styl_pouzity, obl)
    if osa.get("prvky"):
        from . import prvky as _prvky
        try:
            varovani += _prvky.priprav_vsechny(osa, titulky.STYLY[styl_pouzity], obl, _podklady_reelu(r, a))
        except FileNotFoundError as e:
            k.cervena("prvek potřebuje obrázek, který chybí: %s" % e, "nahraj obrázek do složky podkladů a spusť vzhled znovu.")
            return k.kod()
    if titulky.STYLY[styl_pouzity]["titulky"].get("vedle_hlavy"):
        # titulky vedle hlavy znovu, teď už se známými nadpisy a prvky, ať se s nimi nepotkají
        from . import efekty as _efekty, prvky as _prvky
        stp = titulky.STYLY[styl_pouzity]
        prekazky = [(pv["od"], pv["do"], _prvky.modul(pv["typ"]).obdelnik(pv, stp.get(pv["typ"], {}))) for pv in osa.get("prvky", [])]
        prekazky += [(m["od"], m["do"], _efekty.obdelnik(m, stp[m.get("styl", "mini")])) for m in osa.get("mini", [])]
        umisteni.titulky_vedle_hlavy(osa, stp["titulky"], obl, prekazky=prekazky)
    # zvuky k psaní a fajfkám až teď, když jsou časy nadpisů a prvků konečné (umístění je mohlo posunout)
    from . import efekty as _ef
    for m in osa.get("mini", []):
        for i, od_r, n in _ef.casy_psani(m):
            znaky = _ef.radky(m)[i]
            osa.setdefault("zvuky", []).extend(
                {"typ": "klavesa", "cas": round(m["od"] + od_r + j * _ef.PISMENO_S, 3), "db": -14, "param": {"seed": j}}
                for j, ch in enumerate(znaky) if not ch.isspace())
    for pv in osa.get("prvky", []):
        if pv["typ"] == "zapisnik" and pv.get("casy_rel"):
            from .prvky import zapisnik as _zap
            osa.setdefault("zvuky", []).extend({"typ": "cink", "cas": round(pv["od"] + c + _zap.FAJFKA_OD_S, 3), "db": -10}
                                               for c in pv["casy_rel"])
    if styl_reelu.get("zvuky_nastaveni"):
        # výběr zvuků z knihovny a hlasitost (render je přimíchá přes zvuky.podle_nastaveni)
        osa["zvuky_nastaveni"] = styl_reelu["zvuky_nastaveni"]
        zn = styl_reelu["zvuky_nastaveni"]
        k.info("Zvuky podle stylu: %s%s." % ("žádné" if zn.get("bez") else (", ".join(zn["povolene"]) if zn.get("povolene") else "všechny od prvků"),
                                             (", hlasitost %d %%" % zn["hlasitost"]) if zn.get("hlasitost") is not None and not zn.get("bez") else ""))
    kreslic = titulky.Kreslic(osa, styl_pouzity)
    problemy, kontrol = umisteni.kontrola(osa, kreslic, obl)
    for v in varovani:
        k.info("Upozornění: %s" % v)
    # nastavení vzhledu reelu pro další verze (mění se jen to, co zákaznice řekne)
    projekt.uloz_json(s["pracovni"] / "vzhled.json", {
        "vzhled": styl.split("+")[0], "titulky_z": titulky_z, "hook": {"text": hook_text, "zvyraznit": zvyraznit, "vypnuto": bool(a.bez_hooku)},
        "mini": [{kk: vv for kk, vv in m.items() if kk in ("text", "styl", "efekt", "veta", "od", "do")} for m in osa["mini"] if m.get("styl") != "mini_silny"],
        "vsuvky": (a.vsuvka or []) + ulozeno.get("vsuvky", []), "zoom": bool(pouzit_zoom), "vyzva": not a.bez_vyzvy,
        "broll": broll_prani, "jen_hlas": jen_hlas, "bez_zvuku_zaberu": bez_zvuku_zaberu,
        "upravy": ulozeno.get("upravy") or {}})
    # Pojistka (Marcela 23. 11. 2026): nic, co si zákaznice vybrala, nesmí z videa potichu vypadnout.
    from . import zadani as _zadani
    chybi_ve_videu = []
    if plan:
        chybi_ve_videu += nesestavene
        chybi_ve_videu += ["%s: ve videu není (žádná věta, kam by patřil, nebo chybí podklady)" % _styl.PRVKY_TEXT.get(x, x)
                           for x in _zadani.chybejici_ve_videu(styl_reelu, osa, _zadani.nacti(r))
                           if not any(n_.startswith(_styl.PRVKY_TEXT.get(x, x)) for n_ in nesestavene)]
    nadpisove = {"karty_slov", "skladany_nadpis", "hravy_nadpis"}
    if not a.bez_hooku and not osa.get("hook") and not any(x["typ"] in nadpisove or (x["typ"] == "vypinac_plakat" and x.get("vypinac"))
                                                          for x in osa.get("prvky", [])):
        chybi_ve_videu.append("nadpis: ve videu žádný není")
    if chybi_ve_videu:
        k.cervena("video jsem nestavěla, chybělo by v něm, co si zákaznice vybrala: " + "; ".join(chybi_ve_videu) + ".",
                  "zjisti, co chybí: STUDIO podklady --reel \"%s\". Zeptej se zákaznice najednou na všechno, co chybí, "
                  "zapiš to krokem podklady, pak znovu plan a vzhled --plan. Když něco nechce, zapiš podklady --vynechat <efekt>; "
                  "když nechce nadpis, spusť vzhled s --bez-hooku." % r)
        return k.kod()
    n = projekt.dalsi_cislo(s["vystup"], "reel", ".mp4")
    mp4 = s["vystup"] / ("reel-%d.mp4" % n)
    prac = s["pracovni"] / ("reel-%d" % n)
    otisk_vstupu = otisk.spocitej(r, plan=bool(a.plan))           # stav, ze kterého reel vzniká (stránka Plán reelu)
    try:
        pouzit_masku = False
        if render.potrebuje_masku(osa, styl_pouzity) and not a.bez_masky:
            try:
                from . import maska as _maska
                pouzit_masku = _maska.k_dispozici()
            except Exception:
                pouzit_masku = False
            k.info("Text za hlavou: %s." % ("ano, počítám masku osoby (chvíli to trvá)" if pouzit_masku else
                                            "ne (chybí balíček ai-edge-litert nebo model), text půjde před osobu"))
        m = render.vyrenderuj(osa, styl_pouzity, mp4, prac, preset=a.preset, maska=pouzit_masku, log=k.info)
    except RuntimeError as e:
        k.cervena("render se nezdařil: %s" % e, "spusť krok znovu; když to nepomůže, pošli mi PRACOVNI/reel-%d/ffmpeg-chyby.log." % n)
        return k.kod()
    strih.uloz_osu(osa, prac / "casova-osa.json")
    strih.uloz_osu(osa, s["pracovni"] / "casova-osa-vzhled.json")
    otisk.uloz(otisk_vstupu, prac)
    # menší verze pro telefon a snímky hotového videa ke kontrole (D29: Marcela je smí vidět, Claude taky)
    telefon = s["vystup"] / ("reel-%d-telefon.mp4" % n)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(mp4), "-vf", "scale=540:960", "-c:v", "libx264",
                    "-preset", "fast", "-crf", "27", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(telefon)], check=False)
    snimky = prac / "snimky"
    snimky.mkdir(exist_ok=True)
    casy = [0.8] + [round(x["od"] + 0.6, 2) for x in osa["mini"]] + [round(osa["delka"] * f, 2) for f in (0.25, 0.5, 0.75)]
    for i, c in enumerate(sorted(set(min(max(0.1, x), osa["delka"] - 0.2) for x in casy))):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", "%.2f" % c, "-i", str(mp4), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(snimky / ("%02d-%05.1fs.jpg" % (i, c)))], check=False)
    vysl, chyby = kontrola_reelu.kontrola_reelu(mp4, osa, prac, s_prepisem=False)
    for nazev, ok, detail in vysl:
        k.info("%s %s: %s" % ("ZELENÁ" if ok else "ČERVENÁ", nazev, detail))
    cervene = [v for v in vysl if not v[1]]
    projekt.uloz_json(prac / "mereni.json", {"render": m, "kontrola": vysl, "text_problemy": problemy, "text_kontrol": kontrol,
                                              "varovani": varovani, "trvani_s": round(time.time() - t, 1)})
    zprava = "reel %d ve vzhledu %s: délka %s, hook „%s“, %d stránek titulků, %d mikro-nadpisů, %d prvků (%s), %d vsuvek, zoom %s, text proti obličeji a okrajům %s (%d kontrol), hotovo za %.0f s. Soubor: %s (pro telefon %s). Snímky ke kontrole: %s." % (
        n, styl, cas_text(osa["delka"]), hook_text[:60] if hook_text else "bez hooku", len(kreslic.stranky), len(osa["mini"]),
        len(osa.get("prvky", [])), ", ".join(x["typ"] for x in osa.get("prvky", [])) or "žádné", len(osa["vsuvky"]),
        "ano" if pouzit_zoom else "ne", "v pořádku" if not problemy else "🔴 " + "; ".join(problemy[:3]), kontrol, time.time() - t, mp4, telefon.name, snimky)
    if cervene or problemy:
        k.cervena(zprava, "podívej se na místa z kontroly; řekni, co posunout (hook níž, titulky menší), a udělám reel znovu.")
    else:
        k.zelena(zprava, "podívej se na reel. Řekni 'jo', nebo co změnit (hook, titulky, mikro-nadpisy, vsuvky, vzhled).", {"reel": str(mp4)})
    reel.pripis_do_seznamu(s["reely"], r.name, projekt.nazev_reelu(r), "reel %d" % n)
    _prubeh(r)
    return k.kod()


def _podklady_reelu(r, a):
    """Složka s obrázky k reelu: --podklady, jinak PODKLADY-SEM reelu."""
    return Path(a.podklady).expanduser() if getattr(a, "podklady", None) else projekt.slozky(r)["podklady"]


def _chvilky_reelu(r, a, k, nahledy):
    """Chvilky ze záběrů reelu (B-ROLL, studio je rozmisťuje samo) a ze stálé knihovny MOJE-ZABERY (jen podle přiřazení).
    Nové a změněné záběry změří a zapíše do katalogu. Vrátí (chvilky, jestli mají popis)."""
    from . import zabery
    out, popsane = [], False
    zdroje = [(_pk_slozka(r, a), False, False), (zabery.knihovna(r), True, True)]
    for slozka, rekurz, jen_prir in zdroje:
        if not zabery.najdi(slozka, rekurz) and not (slozka / zabery.KATALOG).exists():
            continue
        kat, nove = zabery.aktualizuj(slozka, nahledy, rekurz, hlaseni=None)
        for jm in nove:
            z = kat["zabery"][jm]
            if z.get("vyrazeno"):
                k.info("Záběr %s nepoužiju: %s." % (jm, z["vyrazeno"]))
        for c in zabery.chvilky(slozka, kat):
            c["jen_prirazeni"] = jen_prir
            out.append(c)
            popsane = popsane or bool(c.get("popis"))
    return out, popsane


def _pk_slozka(r, a):
    from . import prekryvy
    return prekryvy.slozka(_podklady_reelu(r, a))


def krok_zabery(a):
    """Záběry pro b-roll pod hlasem: změří nové záběry (kvalita, nejlepší chvilky), připraví náhledy pro Clauda,
    vypíše katalog a věty reelu (k přiřazení podle smyslu). S --popis zapíše, co na záběrech je."""
    from . import zabery
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Záběry", s["pracovni"])
    nahledy = s["pracovni"] / "zabery"
    zdroje = [("B-ROLL", _pk_slozka(r, a), False), ("MOJE-ZABERY", zabery.knihovna(r), True)]
    if a.popis:
        try:
            popis = json.loads(Path(a.popis).expanduser().read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            k.cervena("popis záběrů nejde přečíst: %s." % e, "zapiš JSON {\"soubor.mov\": {\"popis\": …, \"chvilky\": [{\"c\": 1, \"nazev\": …}]}}.")
            return k.kod()
        zbyva = dict(popis)
        for _, slozka, _ in zdroje:
            if (slozka / zabery.KATALOG).exists():
                kat, neznam = zabery.zapis_popis(slozka, {j: p for j, p in zbyva.items()})
                zbyva = {j: zbyva[j] for j in neznam}
        if zbyva:
            k.info("Tyhle záběry v katalogu nejsou: %s." % ", ".join(zbyva))
    radky, bez_popisu, nahl = [], [], []
    for jmeno, slozka, rekurz in zdroje:
        if not zabery.najdi(slozka, rekurz) and not (slozka / zabery.KATALOG).exists():
            continue
        kat, nove = zabery.aktualizuj(slozka, nahledy, rekurz, hlaseni=None)
        radky.append("%s (%s): %d záběrů%s" % (jmeno, slozka, len(kat["zabery"]), (", nově prohlédnuté: %s" % ", ".join(nove)) if nove else ""))
        for jm, z in sorted(kat["zabery"].items()):
            if z.get("vyrazeno"):
                radky.append("  %s: nepoužitelný, %s" % (jm, z["vyrazeno"]))
                continue
            for c in z["chvilky"]:
                radky.append("  %s  [%s %s–%s, %s%s]%s%s" % (
                    zabery.id_chvilky(jm, c), jm, zabery.cas(c["od"]), zabery.cas(c["do"]), c["energie"],
                    (", " + c["nalada"]) if c.get("nalada") else "", ("  " + c["popis"]) if c.get("popis") else "",
                    "  (vyřazená)" if c.get("vyradit") else ""))
            if not z.get("popis") or any(not c.get("popis") for c in z["chvilky"]):
                bez_popisu.append(jm)
            for konc in (".jpg", "-chvilky.jpg"):
                p_ = nahledy / (zabery._bezpecne(jm) + konc)
                if p_.exists() and jm in bez_popisu:
                    nahl.append(str(p_))
    if not radky:
        k.cervena("žádné záběry pro b-roll.", "řekni zákaznici, ať dá záběry do PODKLADY-SEM/B-ROLL v reelu "
                  "(nebo stálé do složky %s) a spusť zabery znovu." % zabery.knihovna(r))
        return k.kod()
    for x in radky:
        k.info(x)
    osa_soubor = s["pracovni"] / "casova-osa.json"
    if osa_soubor.exists():
        osa = strih.nacti_osu(osa_soubor)
        poradi = list(dict.fromkeys(v for u in osa["useky"] for v in u.get("vety", [])))
        texty = {}
        for kl in projekt.nacti_klipy(r):
            for v in kl["vety"]:
                texty[v["id"]] = " ".join(w["w"] for w in v["slova"]).strip()
        k.info("Věty reelu (číslo pro --broll \"chvilka@číslo\"):\n" + "\n".join(
            "  %d. %s" % (i + 1, texty.get(v, v)) for i, v in enumerate(poradi)))
    if bez_popisu:
        k.info("Bez popisu: %s. Prohlédni náhledy a zapiš popis (--popis soubor.json): %s" % (", ".join(bez_popisu), " ".join(nahl)))
    k.zelena("katalog záběrů je aktuální (%s)." % ", ".join(str(sl / zabery.KATALOG_TXT) for _, sl, _ in zdroje if (sl / zabery.KATALOG_TXT).exists()))
    return k.kod()


def krok_vzdy(a):
    """Poznámka zákaznice se slovem „vždycky“: zapíše stálou úpravu vzhledu (NASTAVENI/vzhled-upravy.json)
    a větu do poznamky-zakaznice.md. Příklad: vzdy --reel X --nastav "vogue.mini_nahore.velikost=109" --poznamka "nadpis nad hlavou větší"."""
    from . import titulky
    r = _reel(a.reel)
    k = Krok("Vždycky", projekt.slozky(r)["pracovni"])
    if not a.nastav and not a.poznamka:
        k.cervena("nemám co zapsat.", "zadej --nastav \"vzhled.cast.klic=hodnota\" nebo --poznamka \"věta\".")
        return k.kod()
    cesty = []
    for polozka in a.nastav or []:
        try:
            cesta, hodnota = polozka.split("=", 1)
            vzhled, cast, klic = cesta.strip().split(".")
        except ValueError:
            k.cervena("úprava '%s' nemá tvar vzhled.cast.klic=hodnota." % polozka, "zapiš třeba vogue.mini_nahore.velikost=109.")
            return k.kod()
        if vzhled not in titulky.STYLY:
            k.cervena("vzhled '%s' neznám." % vzhled, "použij jeden z: %s." % ", ".join(x for x in titulky.STYLY if "+" not in x))
            return k.kod()
        hodnota = hodnota.strip()
        try:
            hodnota = json.loads(hodnota)
        except ValueError:
            pass
        cesty.append(projekt.zapis_vzhled_upravu(r, vzhled, cast, klic, hodnota, a.poznamka))
    if a.poznamka and not a.nastav:
        slozka = r.parent / "NASTAVENI"
        slozka.mkdir(exist_ok=True)
        md = slozka / "poznamky-zakaznice.md"
        if not md.exists():
            md.write_text((projekt.BALICEK / "NASTAVENI" / "poznamky-zakaznice.md").read_text(encoding="utf-8"), encoding="utf-8")
        with md.open("a", encoding="utf-8") as f:
            f.write("- %s\n" % a.poznamka)
        cesty.append(md)
    k.zelena("zapsáno: %d úprav, poznámka %s. Soubor: %s." % (len(a.nastav or []), "ano" if a.poznamka else "ne", cesty[-1]),
             "platí pro každý další reel; spusť vzhled znovu, ať se to projeví i na tomhle.")
    return k.kod()


def krok_oprava_titulku(a):
    """Marcela 11. 11. 2026: chyby přepisu („Cloud“ místo „Claude“, „týděn“) opraví Claude sám ještě před náhledem.
    Mění jen text titulků, video se nestříhá. S --naucit si studio dvojici zapamatuje pro další reely
    (NASTAVENI/opravy-slov-cs.json zákaznice)."""
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Oprava titulků", s["pracovni"])
    klipy = projekt.nacti_klipy(r)
    if not klipy:
        k.cervena("chybí přepis.", "nejdřív spusť přepis.")
        return k.kod()
    vety = {v["id"]: v for kl in klipy for v in kl["vety"]}
    vyber, vynechat, texty = projekt.aktualni_vyber(r, klipy)
    texty = dict(texty)
    zaznam = []
    for o in a.oprava or []:
        vid, _, novy = o.partition("=")
        vid, novy = vid.strip(), " ".join(novy.split())
        if vid not in vety or not novy:
            k.cervena("neznám větu „%s“ nebo chybí nový text." % vid, "použij tvar k1-v03=celý opravený text věty (čísla z prepis-vety.txt).")
            return k.kod()
        bylo = " ".join(w["w"] for w in vety[vid]["slova"])
        cist = lambda t: [w.strip(".,;:!?\"'()[]„“”…-–—").lower() for w in t.split()]
        if len(novy.split()) < len(bylo.split()) and all(w in cist(bylo) for w in cist(novy)):
            k.cervena("věta %s by jen ztratila slova. Oprava titulků nic nestříhá." % vid,
                      "slova k vystřižení jdou přes editor nebo nahled --vynechat.")
            return k.kod()
        if novy != bylo:
            texty[vid] = novy
            zaznam.append({"veta": vid, "bylo": bylo, "je": novy})
            k.info("%s: „%s“ → „%s“" % (vid, bylo, novy))
    nauceno = []
    if a.naucit:
        slozka = Path(r).parent / "NASTAVENI"
        slozka.mkdir(exist_ok=True)
        j_ = projekt.jazyk_reelu(r)
        soubor = slozka / ("opravy-slov-%s.json" % j_)
        data = projekt.nacti_json(soubor) or {"jazyk": j_, "verze": 1, "opravy": {}}
        data.setdefault("opravy", {})
        for dv in a.naucit:
            spatne, _, dobre = dv.partition("=")
            spatne, dobre = spatne.strip(), dobre.strip()
            if not spatne or not dobre or " " in spatne:
                k.cervena("„%s“ není dvojice jedno_slovo=oprava." % dv, "použij tvar týděn=týden.")
                return k.kod()
            data["opravy"][spatne.lower()] = dobre
            nauceno.append("%s → %s" % (spatne, dobre))
        projekt.uloz_json(soubor, data)
    projekt.uloz_vyber(r, vyber, vynechat, texty)
    hist = projekt.nacti_json(s["pracovni"] / "opravy-claude.json") or []
    hist.append({"cas": time.strftime("%Y-%m-%d %H:%M"), "opravy": zaznam, "nauceno": nauceno})
    projekt.uloz_json(s["pracovni"] / "opravy-claude.json", hist)
    k.zelena("opraveno vět %d%s. Video se nestříhá, mění se jen titulky." % (
        len(zaznam), (", zapamatováno pro další reely: " + ", ".join(nauceno)) if nauceno else ""),
        "náhled: STUDIO nahled --reel \"%s\"." % r)
    return k.kod()


def krok_styl(a):
    """Kód stylu z knihovny stylů („styl: vogue; nadpisy: …“) nebo obyčejná věta zákaznice („písmo větší“).
    Nic nerenderuje: zapíše PRACOVNI/styl.json, NASTAVENI/styl.json a PRACOVNI/vzhled.json (vzhled + úpravy jen pro
    tento reel) a vypíše řádek po řádku, co pochopil. Další vzhled --plan to použije."""
    from . import styl as _styl, titulky
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Styl", s["pracovni"])
    kod = (a.kod or "").strip()
    veta = (a.veta or "").strip()
    if a.z_knihovny:
        # Marcela 10. 11. 2026: výběr z knihovny stylů bez kopírování. Zákaznice klikne na „Uložit výběr pro tenhle
        # reel“, knihovna uloží záznam pro-reel ({kod, ulozeno, ...}), Claude ho stáhne do souboru a předá sem.
        try:
            zaznam = json.loads(Path(a.z_knihovny).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            k.cervena("uložený výběr nejde přečíst (%s)." % e, "požádej zákaznici, ať v knihovně stylů klikne znovu na Uložit výběr pro tenhle reel.")
            return k.kod()
        if isinstance(zaznam, dict) and isinstance(zaznam.get("data"), dict):
            zaznam = zaznam["data"]
        kod = str((zaznam or {}).get("kod") or "").strip() if isinstance(zaznam, dict) else ""
        if not kod:
            k.cervena("v uloženém výběru chybí kód stylu.", "požádej zákaznici, ať v knihovně stylů klikne na Uložit výběr pro tenhle reel.")
            return k.kod()
        k.info("Výběr z knihovny stylů, uložený %s." % (zaznam.get("ulozeno") or "bez času"))
    if not kod and not veta:
        posledni = _styl.nacti_posledni(r)
        if posledni.get("kod"):
            kod = posledni["kod"]
            k.info("Bez kódu i věty: beru poslední styl zákaznice z NASTAVENI/styl.json.")
        else:
            k.cervena("nemám kód stylu ani větu.", "zadej --kod \"<věta z knihovny stylů>\" nebo --veta \"písmo větší\".")
            return k.kod()
    if kod:
        st, hlasky = _styl.rozeber_kod(kod)
        for uroven, text in hlasky:
            k.info(("⚠️ " if uroven == "pozor" else "") + text)
        zachovat = bool(_styl.nacti(r).get("zachovat_pismo") or _styl.nacti_posledni(r).get("zachovat_pismo"))
        upravy, popis = _styl.upravy_ze_stylu(st, zachovat_pismo=zachovat)
        for text in popis:
            k.info(text)
        if zachovat:
            st["zachovat_pismo"] = True
        from . import zadani as _zadani_m
        neznam_prvky = [p for p in (st.get("prvky") or []) if p not in _styl.PRVKY_PLANU and p not in ("vsuvka", "za_hlavou", "casomira", "titulky", "zoom")
                        and p not in _zadani_m.KARTY]
        if neznam_prvky:
            k.info("ℹ️ Prvky %s plán sám nenavrhuje; zákaznice je dá do řádku plánu (viz dovednost novy-reel)." % ", ".join(_styl.PRVKY_TEXT.get(p, p) for p in neznam_prvky))
        cesty = _styl.zapis_styl(r, st, upravy, popis, kod=kod)
        from . import zadani as _zadani
        seznam, chybi_podklady = _zadani.seznam_podkladu(r, st)
        if seznam:
            print("PODKLADY K VYBRANÝM EFEKTŮM (řekni zákaznici hned, najednou, v jedné zprávě):")
            for radek in seznam:
                print(radek)
        pozor = sum(1 for u, _ in hlasky if u == "pozor")
        k.zelena("vzhled %s, %d úprav vzhledu, prvků %s, zvuky %s, obrázků k větám %d%s. Zapsáno: %s, %s, %s." % (
            st["vzhled"], sum(len(v) for v in upravy.get(st["vzhled"], {}).values() if isinstance(v, dict)),
            "všechny" if st.get("prvky") is None else len(st["prvky"]),
            "podle vzhledu" if st.get("zvuky") is None else (", ".join(st["zvuky"]) or "žádné"), len(st.get("obrazky") or []),
            (", %d částí jsem nepochopil (viz ⚠️ výš)" % pozor) if pozor else "", cesty[0], cesty[1], cesty[2]),
            (("HNED zákaznici napiš jednou zprávou, co si vybrala a co od ní ke každému efektu s ❌ potřebuješ (seznam výš). "
              "Neptej se po jednom. Odpovědi zapiš: STUDIO podklady --reel \"%s\" --nastav \"efekt.pole=hodnota\" (profil: --profil-jmeno, "
              "--profil-popis, --profil-fotka). Co nechce, zapiš --vynechat <efekt>. Teprve když podklady hlásí zelenou: " % r)
             if chybi_podklady else "") +
            "plán a vzhled: STUDIO plan --reel \"%s\" a pak vzhled --reel \"%s\" --plan --zoom." % (r, r))
        return k.kod()
    # obyčejná věta zákaznice pro tento reel (a s --vzdy i trvale)
    ulozeno = projekt.nacti_json(s["pracovni"] / "vzhled.json", {}) or {}
    styl_reelu = _styl.nacti(r)
    vzhled = ulozeno.get("vzhled") or styl_reelu.get("vzhled") or projekt.nastaveni(r).get("vzhled", "serif")
    if vzhled not in titulky.STYLY:
        k.cervena("vzhled '%s' neznám." % vzhled, "použij jeden z: %s." % ", ".join(x for x in titulky.STYLY if "+" not in x))
        return k.kod()
    trvale = projekt.vzhled_upravy(r).get(vzhled, {})
    reelove = (ulozeno.get("upravy") or {}).get(vzhled, {})

    def aktualni(cast, klic):
        if cast == "_styl":
            zn = styl_reelu.get("zvuky_nastaveni") or {}
            return zn.get(klic)
        for zdroj in (reelove, trvale):
            if klic in (zdroj.get(cast) or {}):
                return zdroj[cast][klic]
        return titulky.ZAKLAD.get(vzhled, {}).get(cast, {}).get(klic)

    akce, nepochopeno = _styl.rozeber_vetu(veta, vzhled, aktualni)
    if not akce:
        k.cervena("větě „%s“ nerozumím." % veta, "umím: %s." % "; ".join(_styl.UMIM))
        return k.kod()
    for kus in nepochopeno:
        k.info("⚠️ Části „%s“ nerozumím, přeskakuju ji." % kus)
    upravy = ulozeno.get("upravy") or {}
    upravy.setdefault(vzhled, {})
    zmena_stylu = False
    vypsano = set()
    for x in akce:
        if x["popis"] not in vypsano:       # stejná změna pro víc částí vzhledu jen jednou
            k.info(x["popis"] + ".")
            vypsano.add(x["popis"])
        if x["co"] == "uprava":
            upravy[vzhled].setdefault(x["cast"], {})[x["klic"]] = x["hodnota"]
        else:
            zmena_stylu = True
            if x["klic"] == "zvuky":
                styl_reelu["zvuky"] = x["hodnota"]
                if x["hodnota"] is None:
                    styl_reelu.pop("hlasitost", None)
            elif x["klic"] == "hlasitost":
                styl_reelu["hlasitost"] = x["hodnota"]
                if styl_reelu.get("zvuky") == []:
                    styl_reelu["zvuky"] = None
            else:
                styl_reelu[x["klic"]] = x["hodnota"]
    if zmena_stylu or styl_reelu:
        styl_reelu.setdefault("vzhled", vzhled)
        styl_reelu["zvuky_nastaveni"] = _styl.zvuky_nastaveni(styl_reelu)
        styl_reelu.setdefault("vety", []).append(veta)
        projekt.uloz_json(_styl.soubor_reelu(r), styl_reelu)
    ulozeno["vzhled"] = vzhled
    ulozeno["upravy"] = upravy
    if "hook" not in ulozeno:
        ulozeno["jen_styl"] = True
    projekt.uloz_json(s["pracovni"] / "vzhled.json", ulozeno)
    cesty = [s["pracovni"] / "vzhled.json"]
    if a.vzdy:
        prvni = True
        for x in akce:
            if x["co"] == "uprava":
                cesty.append(projekt.zapis_vzhled_upravu(r, vzhled, x["cast"], x["klic"], x["hodnota"], veta if prvni else None))
                prvni = False
        posledni = _styl.nacti_posledni(r)
        for x in akce:
            if x["co"] == "styl":
                posledni[x["klic"]] = x["hodnota"]
        if any(x["co"] == "styl" for x in akce):
            posledni["zvuky_nastaveni"] = _styl.zvuky_nastaveni(posledni)
            projekt.uloz_json(_styl.soubor_nastaveni(r), posledni)
            cesty.append(_styl.soubor_nastaveni(r))
    k.zelena("„%s“: %d změn pro vzhled %s%s. Zapsáno: %s." % (veta, len(akce), vzhled, " (i trvale, „vždycky“)" if a.vzdy else "",
                                                             ", ".join(str(c) for c in cesty)),
             "spusť vzhled znovu: STUDIO vzhled --reel \"%s\" --plan --zoom." % r)
    return k.kod()


def krok_broll(a):
    """B-roll (Marcela 22. 10.): video bez řeči, vybraný úsek, nadpis přes obraz, volitelně štítky. Zvuk původní (ztišený) nebo ticho."""
    from . import efekty, poloha, render, titulky, umisteni
    from .titulky import FPS, VYSKA

    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("B-roll", s["pracovni"])
    seznam = projekt.klipy_seznam(r)
    if not seznam:
        k.cervena("chybí zkontrolované video.", "nejdřív spusť kopie a kontrola-videa.")
        return k.kod()
    kl = seznam[max(0, min(len(seznam) - 1, (a.klip or 1) - 1))]
    delka_klipu = float(kl["delka_s"])
    od = max(0.0, float(a.od or 0.0))
    delka = min(float(a.delka or 10.0), delka_klipu - od) if not a.cele else delka_klipu - od
    if delka < 1.0:
        k.cervena("úsek je kratší než 1 s (klip má %.1f s).", "zadej --od a --delka uvnitř klipu." % delka_klipu)
        return k.kod()
    delka = round(round(delka * FPS) / FPS, 4)
    klip = {"cesta": kl["pouzit"], "vety": [], "delka": delka_klipu, "n": kl["n"], "slozka": str(s["pracovni"] / ("klip-%d" % kl["n"]))}
    osa = {"verze": 1, "fps": FPS, "sirka": 1080, "vyska": 1920, "klipy": [klip["cesta"]],
           "useky": [{"klip": 0, "od": od, "do": round(od + delka, 4), "vystup_od": 0.0, "delka": delka, "vety": [],
                      "cele_vety": True, "cast": 1, "casti": 1, "jisty_vstup": True, "jisty_vystup": True}],
           "slova": [], "delka": delka, "hook": None, "vsuvky": [], "vyber": [], "vynechat": {}, "bez_strihu": True,
           "mini": [], "prvky": [], "zvuky": [], "zvuk": "ticho" if a.zvuk == "ticho" else "puvodni", "broll": True}
    styl = a.vzhled or projekt.nacti_json(s["pracovni"] / "vzhled.json", {}).get("vzhled") or "vogue"
    if styl not in titulky.STYLY:
        k.cervena("neznámý vzhled %s." % styl, "použij jeden z: %s." % ", ".join(sorted(titulky.STYLY)))
        return k.kod()
    titulky.pouzij_upravy(projekt.vzhled_upravy(r))
    titulky.pouzij_upravy((projekt.nacti_json(s["pracovni"] / "vzhled.json", {}) or {}).get("upravy"))   # úpravy jen pro tento reel
    nadpisy = [n for n in (a.nadpis or []) if n and n.strip()]
    if nadpisy:
        # víc nadpisů za sebou (Marcela 22. 10.: tři hooky, každý statický, poslední do konce); časy --nadpis-casy
        # „0 | 3.2 | 5.8“, jinak podle počtu slov (0,35 s na slovo + 0,9 s, nejméně 2,2 s)
        if a.nadpis_casy:
            casy_n = [float(x.strip().replace(",", ".")) for x in a.nadpis_casy.split("|") if x.strip()]
        else:
            casy_n, t0 = [], 0.0
            for n in nadpisy:
                casy_n.append(round(t0, 2))
                t0 += max(2.2, 0.35 * len(n.replace("/", " ").split()) + 0.9)
        while len(casy_n) < len(nadpisy):
            casy_n.append(round(casy_n[-1] + 2.5, 2))
        st_n = "mini_nahore" if "mini_nahore" in titulky.STYLY[styl] else "mini"
        zakl = titulky.STYLY[styl].get(st_n, {}).get("velikost", 64)
        vel = str(a.velikost or "").strip()
        velikost_n = int(round(zakl * float(vel[:-1]) / 100)) if vel.endswith("%") else (int(vel) if vel.isdigit() else zakl)
        for i, nadpis in enumerate(nadpisy):
            # řádky lomítkem, jinak rozdělit po 3 až 4 slovech, všechny řádky velké (Playfair)
            # emoji na konci nadpisu se kreslí jako obrázek za posledním řádkem (Marcela 22. 10.)
            nadpis_t, emoji = nadpis.strip(), None
            if nadpis_t and ord(nadpis_t[-1]) >= 0x2600:
                emoji, nadpis_t = nadpis_t[-1], nadpis_t[:-1].rstrip()
            if "/" in nadpis_t:
                radky = [x.strip() for x in nadpis_t.split("/") if x.strip()]
            else:
                slova = nadpis_t.split()
                n_r = max(1, min(5, (len(slova) + 2) // 3))
                na_radek = -(-len(slova) // n_r)
                radky = [" ".join(slova[j:j + na_radek]) for j in range(0, len(slova), na_radek)]
            od_n = max(0.0, casy_n[i])
            do_n = round(delka, 2) if i == len(nadpisy) - 1 else round(min(delka, casy_n[i + 1]), 2)
            m = {"text": "\n".join(radky), "styl": st_n, "efekt": "zleva", "od": round(od_n + (0.3 if (i == 0 and not a.staticky) else 0.0), 2),
                 "do": do_n, "veta": None, "velikost": velikost_n, "velikost_zadana": velikost_n, "y": 0, "za_hlavou": False}
            if emoji:
                m["emoji"] = emoji
            if a.staticky or i > 0:
                m.update({"efekt": "zadny", "staticky": True})      # hned, bez nástupu; další nadpis tvrdě vystřídá předchozí
            if a.zvyraznit:
                zv = [x.strip() for x in a.zvyraznit.replace("|", " ").split() if x.strip()]
                if any(z.lower().strip(".,!?") in nadpis_t.lower() for z in zv):
                    m["zvyraznit"] = zv
                    m["marker_od"], m["marker_delka"] = 0.0, 0.01
            osa["mini"].append(m)
    if a.stitky:
        texty = [x.strip() for x in a.stitky.replace("/", "|").split("|") if x.strip()][:5]
        if len(texty) >= 2:
            casy = [round(1.0 + 0.35 * i, 2) for i in range(len(texty))]
            osa["prvky"].append({"typ": "stitky", "od": 1.0, "do": round(delka, 2), "texty": texty, "casy": casy})
            osa["zvuky"] += [{"typ": "klik", "cas": c, "db": -20} for c in casy]
    if a.ikony:
        # „ikona-claude.jpg:Claude | ikona-notion.jpg:Notion“ (obrázky ve složce podkladů)
        soubory, popisky = [], []
        for kus in a.ikony.split("|"):
            soubor, _, popisek = kus.strip().partition(":")
            if soubor.strip():
                soubory.append(soubor.strip())
                popisky.append(popisek.strip() or Path(soubor.strip()).stem.replace("ikona-", "").capitalize())
        if soubory:
            casy = [round(1.0 + 0.35 * i, 2) for i in range(len(soubory))]
            osa["prvky"].append({"typ": "ikony", "od": 1.0, "do": round(delka, 2), "soubory": soubory, "popisky": popisky, "casy": casy,
                                 "sipka": bool(a.sipka)})
            osa["zvuky"] += [{"typ": "klik", "cas": c, "db": -22} for c in casy]
    # obličej (když ve videu je) a umístění
    data = _poloha_klipu(klip, klip["slozka"])
    obl = poloha.obliceje_ve_vystupu(osa, [poloha.pevne(data["vzorky"])])
    varovani = umisteni.umisti(osa, styl, obl)
    if len(osa["mini"]) > 1:
        # víc nadpisů za sebou: stejná velikost písma pro všechny (nejmenší, která se vešla)
        nejmensi = min(int(m["velikost"]) for m in osa["mini"])
        for m in osa["mini"]:
            m["velikost"] = m["velikost_zadana"] = nejmensi
    for m in osa["mini"]:
        if a.y is not None:
            m["y"] = int(a.y)
        elif not obl:
            # bez obličeje: nadpis v horní třetině, štítky pod ním
            _, vb = efekty.velikost_bloku(m, titulky.STYLY[styl][m["styl"]])
            m["y"] = int(VYSKA * 0.40 - vb / 2)
    if osa["prvky"]:
        from . import prvky as _prvky
        if a.y_stitky is not None:
            for p in osa["prvky"]:
                p["y"] = int(a.y_stitky)
        elif osa["mini"] and not any(p.get("y") for p in osa["prvky"]):
            m = osa["mini"][0]
            _, vb = efekty.velikost_bloku(m, titulky.STYLY[styl][m["styl"]])
            for p in osa["prvky"]:
                p["y"] = int(m["y"] + vb + 150)
        varovani += _prvky.priprav_vsechny(osa, titulky.STYLY[styl], obl, _podklady_reelu(r, a))
    for v in varovani:
        k.info("Upozornění: %s" % v)
    strih.uloz_osu(osa, s["pracovni"] / "casova-osa-broll.json")
    n = projekt.dalsi_cislo(s["vystup"], "reel", ".mp4")
    mp4 = s["vystup"] / ("reel-%d.mp4" % n)
    prac = s["pracovni"] / ("reel-%d" % n)
    try:
        m = render.vyrenderuj(osa, styl, mp4, prac, preset=a.preset, maska=False, log=k.info)
    except RuntimeError as e:
        k.cervena("render selhal: %s" % e, "pošli mi soubor PRACOVNI/reel-%d/ffmpeg-chyby.log." % n)
        return k.kod()
    projekt.uloz_json(prac / "mereni.json", {"render": m, "osa": "casova-osa-broll.json", "od": od, "delka": delka, "varovani": varovani})
    k.zelena("b-roll reel %d: úsek %.1f až %.1f s klipu (%.1f s), nadpis %s, štítky %s, vzhled %s, zvuk %s. Soubor: %s"
             % (n, od, od + delka, delka, "ano" if osa["mini"] else "ne", ", ".join(x["typ"] + " " + " / ".join(x.get("texty") or x.get("popisky") or []) for x in osa["prvky"]) or "ne",
                styl, osa["zvuk"], mp4), "podívej se na snímky a řekni, jiný úsek nebo jiný text.")
    return k.kod()


def krok_vzor(a):
    """Ulož schválený reel jako vzor (šablonu): vzhled, titulky, velikosti a vzor plánu (typ věty → prvek).
    Vzor se ukládá do Reely/VZORY/<slug>.json a .md; krok plan --vzor <slug> ho použije na další reel."""
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Vzor", s["pracovni"])
    plan = projekt.nacti_json(s["pracovni"] / "plan-strihu.json")
    ulozeno = projekt.nacti_json(s["pracovni"] / "vzhled.json", {}) or {}
    if not plan:
        k.cervena("reel nemá plán obrazovky.", "nejdřív udělej plan a vzhled --plan, pak ulož vzor.")
        return k.kod()
    slug = reel.slug(a.nazev)
    slozka = s["reely"] / "VZORY"
    slozka.mkdir(exist_ok=True)
    radky = []
    n = len(plan["radky"])
    for i, rad in enumerate(plan["radky"]):
        radky.append({"poradi": "prvni" if i == 0 else ("posledni" if i == n - 1 else "stred"), "typ": rad.get("typ"),
                      "prvek": rad["prvek"], "obsah": rad.get("obsah", "") if rad["prvek"] in ("mini", "velke_slovo") else "",
                      "velikost": rad.get("velikost")})
    vzor = {"nazev": a.nazev, "slug": slug, "kdy": time.strftime("%Y-%m-%d"), "z_reelu": r.name,
            "vzhled": a.vzhled or ulozeno.get("vzhled"), "titulky_z": ulozeno.get("titulky_z"), "zoom": ulozeno.get("zoom"),
            "radky": radky, "filtr_od_vety": plan.get("filtr_od_vety")}
    (slozka / (slug + ".json")).write_text(json.dumps(vzor, ensure_ascii=False, indent=1), encoding="utf-8")
    prvky = {}
    for rad in radky:
        prvky[rad["prvek"]] = prvky.get(rad["prvek"], 0) + 1
    md = ["# Vzor: %s" % a.nazev, "", "Uložen %s z reelu %s. Vzhled: %s%s." % (vzor["kdy"], r.name, vzor["vzhled"] or "výchozí",
          (", titulky %s" % vzor["titulky_z"]) if vzor.get("titulky_z") else ""), "",
          "Prvky: " + ", ".join("%s %d×" % kv for kv in prvky.items()) + ".", "",
          "| pořadí | typ věty | prvek |", "|---|---|---|"] + ["| %s | %s | %s |" % (x["poradi"], x["typ"], x["prvek"]) for x in radky]
    (slozka / (slug + ".md")).write_text("\n".join(md) + "\n", encoding="utf-8")
    k.zelena("vzor „%s“ uložen (%d řádků, vzhled %s). Soubor: %s." % (a.nazev, len(radky), vzor["vzhled"], slozka / (slug + ".json")),
             "další reel stejného typu: plan --vzor %s, pak vzhled --plan --vzhled %s." % (slug, vzor["vzhled"] or "serif"))
    return k.kod()


def krok_podklady(a):
    """Podklady k efektům z knihovny stylů (Marcela 23. 11. 2026): zapíše, co zákaznice dodala, a vypíše, co ještě chybí.
    Bez voleb jen vypíše stav. Profil (jméno účtu, řádek pod ním, fotka) se ukládá jednou pro všechny reely."""
    from . import styl as _styl, zadani as _zadani
    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Podklady", s["pracovni"])
    chyby = []
    if a.profil_jmeno is not None or a.profil_popis is not None or a.profil_fotka is not None:
        _, ch = _zadani.nastav_profil(r, a.profil_jmeno, a.profil_popis, a.profil_fotka)
        chyby += ch
    if a.nastav or a.vynechat or a.vratit:
        _, ch = _zadani.nastav(r, a.nastav, a.vynechat, a.vratit)
        chyby += ch
    styl_reelu = _styl.nacti(r)
    vybrane = _zadani.vybrane(styl_reelu)
    if not vybrane:
        k.zelena("v tomhle reelu nejsou vybrané efekty, které by potřebovaly podklady.", "pokračuj plánem (STUDIO plan --reel \"%s\")." % r)
        return k.kod()
    data, profil = _zadani.nacti(r), _zadani.nacti_profil(r)
    vety = _zadani._vety_reelu(r)
    chybi = 0
    for z in _zadani.kontrola(r, styl_reelu):
        print("%s %s%s" % ("–" if z["vynechano"] else ("❌" if z["chybi"] else "✅"), z["nazev"], " (vynechat)" if z["vynechano"] else ""))
        if z["vynechano"]:
            continue
        chybi += 1 if z["chybi"] else 0
        for pole in (_zadani.KARTY.get(z["karta"], {}).get("pole") or _zadani.DRIVE.get(z["karta"]) or []):
            if pole["druh"] == "pocet":
                print("     obrázky v PODKLADY-SEM: %s" % pole["otazka"])
                continue
            v = _zadani.hodnota(r, z["karta"], pole["klic"], data, profil, vety)
            zapis = ("--profil-%s" % pole["klic"]) if pole["druh"] == "profil" else ("--nastav \"%s.%s=…\"" % (z["karta"], pole["klic"]))
            print("     %s %s: %s  [%s]" % ("✓" if v else ("✗" if pole["povinne"] else "·"), pole["klic"],
                                          (Path(v).name if pole["klic"] == "fotka" else v) if v else pole["otazka"], zapis))
    for ch in chyby:
        k.info("⚠️ " + ch)
    if chyby or chybi:
        k.cervena("chybí podklady u %d efektů%s." % (chybi, (" a %d zápisů se nepovedlo" % len(chyby)) if chyby else ""),
                  "napiš zákaznici JEDNOU zprávou, co ke kterému efektu potřebuješ (✗ výš, svými slovy, bez názvů polí); "
                  "soubory ať dá do složky PODKLADY-SEM. Odpovědi zapiš krokem podklady. Co nechce, --vynechat <efekt>.")
    else:
        k.zelena("podklady ke všem vybraným efektům mám.", "STUDIO plan --reel \"%s\", pak vzhled --reel \"%s\" --plan --zoom." % (r, r))
    return k.kod()


def krok_plan(a):
    """Plán obrazovky věta po větě podle knihy střihu. Zákaznice ho schválí nebo upraví, pak se staví vzhled."""
    from . import planer

    r = _reel(a.reel)
    s = projekt.slozky(r)
    k = Krok("Plán střihu", s["pracovni"])
    osa_soubor = s["pracovni"] / "casova-osa.json"
    if not osa_soubor.exists():
        k.cervena("ještě není náhled.", "nejdřív udělej náhled (STUDIO nahled --reel \"%s\")." % r)
        return k.kod()
    osa = strih.nacti_osu(osa_soubor)
    klipy = projekt.nacti_klipy(r, s_energii=False)
    vety_text = {v["id"]: v["text"] for kl in klipy for v in kl["vety"]}
    veta_slova = {}
    for w in osa["slova"]:
        veta_slova.setdefault(w["veta"], []).append(w)
    vety = []
    for u in osa["useky"]:
        for vid in u.get("vety", []):
            if vid in veta_slova and not any(x["id"] == vid for x in vety):
                vety.append({"id": vid, "text": vety_text.get(vid, ""), "od": veta_slova[vid][0]["start"], "do": veta_slova[vid][-1]["end"]})
    podklady = _podklady_reelu(r, a)
    nadpisy, wow = planer.nacti_mikro_nadpisy(podklady / "mikro-nadpisy.txt")
    obrazky = sorted(p.name for p in podklady.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")) if podklady.exists() else []
    # nahrávky obrazovky první: ukazují věc na obrazovce líp než screenshot (planer je bere v tomhle pořadí)
    obrazky = [p.name for p in reel.najdi_nahravky(podklady)] + obrazky
    radky = planer.sestav_plan(vety, nadpisy, wow, obrazky)
    if a.vzor:
        vz_cesta = s["reely"] / "VZORY" / (a.vzor + ".json")
        vz = projekt.nacti_json(vz_cesta)
        if not vz:
            k.cervena("vzor '%s' nenalezen (%s)." % (a.vzor, vz_cesta), "ulož vzor krokem vzor, nebo zkontroluj název.")
            return k.kod()
        pouzito = 0
        for i, rad in enumerate(radky):
            poradi = "prvni" if i == 0 else ("posledni" if i == len(radky) - 1 else "stred")
            kand = [x for x in vz["radky"] if x["poradi"] == poradi and (poradi != "stred" or x["typ"] == rad.get("typ"))]
            if kand and rad["prvek"] in ("zoom", "chybi_obrazek") and kand[0]["prvek"] not in ("zoom", "chybi_obrazek", "vlozka", "karticky", "mrizka"):
                rad["prvek"], rad["duvod"] = kand[0]["prvek"], "podle vzoru „%s“" % vz["nazev"]
                if kand[0].get("velikost"):
                    rad["velikost"] = kand[0]["velikost"]
                pouzito += 1
        k.info("Vzor „%s“: upraveno %d řádků." % (vz["nazev"], pouzito))
    from . import styl as _styl
    styl_reelu = _styl.nacti(r)                 # kód stylu z knihovny: povolené prvky a obrázky k větám; {} = jako dřív
    for zprava in _styl.pouzij_na_plan(radky, styl_reelu, vety, obrazky):
        k.info(zprava)
    from . import zadani as _zadani
    for zprava in _zadani.pridej_do_planu(r, radky, styl_reelu, vety):
        k.info(zprava)
    for kk, vv in _styl.PRVKY_TEXT.items():
        planer.JMENA_PRVKU.setdefault(kk, vv)
    seznam, chybi_podklady = _zadani.seznam_podkladu(r, styl_reelu)
    if chybi_podklady:
        k.info("⚠️ Podklady k vybraným efektům (chybí u %d):" % chybi_podklady)
        for radek in seznam:
            print(radek)
    plan, souhrn = planer.sloucit_plan(projekt.nacti_json(s["pracovni"] / "plan-strihu.json"), radky)
    plan.update({"podklady": str(podklady), "schvaleno": False})
    radky = plan["radky"]
    projekt.uloz_json(s["pracovni"] / "plan-strihu.json", plan)
    if souhrn["zachovano"]:
        k.info("Ruční úpravy zůstaly: %d scén. Studio navrhuje něco jiného u %d, věta se změnila u %d, bez věty %d. Nic jsem nepřepsal, rozhodne zákaznice." % (
            souhrn["zachovano"], souhrn["konflikty"], souhrn["zkontrolovat"], souhrn["bez_vety"]))
    text = planer.tabulka(radky, projekt.nazev_reelu(r), plan["bez_vety"])
    (s["pracovni"] / "plan-strihu.md").write_text(text, encoding="utf-8")
    print(text)
    chybi = [x for x in radky if x["prvek"] == "chybi_obrazek"]
    k.zelena("%d vět, %d prvků s textem, nadpisů od zákaznice %d, WOW %s, chybí obrázky u %d vět. Plán je v PRACOVNI/plan-strihu.md." % (
        len(radky), sum(1 for x in radky if x["prvek"] not in ("zoom", "chybi_obrazek")), sum(1 for x in radky if x["zdroj"] == "nadpis zákaznice"),
        "ano" if wow else "ne", len(chybi)),
        ("NEJDŘÍV si od zákaznice najednou vyžádej chybějící podklady (seznam ❌ výš) a zapiš je krokem podklady, pak plan znovu. "
         if chybi_podklady else "") +
        "ukaž plán zákaznici; po „jo“ (nebo úpravách v plan-strihu.json) spusť vzhled s plánem: STUDIO vzhled --reel \"%s\" --plan" % r)
    _prubeh(r)
    return k.kod()


def krok_editor(a):
    from . import editor

    r = _reel(a.reel)
    s = projekt.slozky(r)
    nast = projekt.nastaveni(r)
    k = Krok("Editor přepisu", s["pracovni"])
    osa_soubor = s["pracovni"] / "casova-osa.json"
    if not osa_soubor.exists():
        k.cervena("ještě není náhled.", "nejdřív udělej náhled (STUDIO nahled --reel \"%s\")." % r)
        return k.kod()
    osa = strih.nacti_osu(osa_soubor)
    klipy = projekt.nacti_klipy(r, s_energii=False)
    nahledy = sorted(list(s["vystup"].glob("nahled-*.mp4")) + list(s["vystup"].glob("reel-*.mp4")), key=lambda p: p.stat().st_mtime)
    video = nahledy[-1] if nahledy else None
    data = editor.data_editoru(osa, [kl["vety"] for kl in klipy], projekt.nazev_reelu(r),
                               nast["delka_reelu"]["cil_s"], nast["delka_reelu"]["nejvic_s"])
    html = editor.stranka(data, "/video")
    (s["pracovni"] / "editor.html").write_text(editor.stranka(data, "../VYSTUP/%s" % video.name if video else ""), encoding="utf-8")

    def ohlas(adresa):
        print("STATUS editor READY %s" % adresa, flush=True)
        k.info("Editor běží na %s (jen na tomhle počítači). Až zákaznice klikne na Odeslat úpravy, příkaz skončí sám." % adresa)

    u = editor.spust(html, video, s["pracovni"] / "upravy.json", otevrit=not a.neotvirat, cekat_s=a.cekat, port=a.port, po_startu=ohlas)
    if u is None:
        k.cervena("nic se neuložilo (okno zavřené bez uložení, nebo vypršel čas %d s)." % a.cekat,
                  "spusť editor znovu a klikni na Odeslat úpravy. Nebo řekni, co změnit, slovy.")
    else:
        k.zelena("úpravy uložené: %s" % editor.shrnuti_uprav(u), "nový náhled (STUDIO nahled --reel \"%s\")." % r,
                 {"upravy": {kk: v for kk, v in u.items() if kk != "texty"}})
    _prubeh(r)
    return k.kod()


def krok_plan_reelu(a):
    """Stránka Plán reelu: karty scén, knihovna vlastních médií, věty s prvky. Mění jen plán, úpravy textu a podklady."""
    from . import plan_reelu

    r = _reel(a.reel)
    s = projekt.slozky(r)
    nast = projekt.nastaveni(r)
    k = Krok("Plán reelu", s["pracovni"])
    osa_soubor, soubor_planu = s["pracovni"] / "casova-osa.json", s["pracovni"] / "plan-strihu.json"
    if not osa_soubor.exists():
        k.cervena("ještě není náhled.", "nejdřív udělej náhled (STUDIO nahled --reel \"%s\")." % r)
        return k.kod()
    if not soubor_planu.exists():
        k.cervena("reel ještě nemá plán obrazovky.", "nejdřív spusť plan (STUDIO plan --reel \"%s\")." % r)
        return k.kod()
    osa = strih.nacti_osu(osa_soubor)
    klipy = projekt.nacti_klipy(r, s_energii=False)
    videa = sorted(list(s["vystup"].glob("nahled-*.mp4")) + [p for p in s["vystup"].glob("reel-*.mp4") if not p.stem.endswith("-telefon")],
                   key=lambda p: p.stat().st_mtime)
    video = videa[-1] if videa else None
    podklady = Path((projekt.nacti_json(soubor_planu) or {}).get("podklady") or s["podklady"])
    zname = {w["veta"] for w in osa["slova"]}

    def data():
        return plan_reelu.data_stranky(r, osa, [kl["vety"] for kl in klipy], projekt.nazev_reelu(r), nast["delka_reelu"]["cil_s"],
                                       nast["delka_reelu"]["nejvic_s"], projekt.nacti_json(soubor_planu) or {"radky": []}, soubor_planu, podklady, video)

    server = plan_reelu.Server(r, data, video, soubor_planu, s["pracovni"] / "upravy.json", podklady, zname, port=a.port)

    def ohlas(adresa):
        k.info("Plán reelu běží na %s (jen na tomhle počítači). Otevírám prohlížeč. Až bude hotová, klikne na Hotovo." % adresa)

    zmeny = plan_reelu.spust(server, otevrit=not a.neotvirat, cekat_s=a.cekat, po_startu=ohlas)
    stav_nahledu = otisk.porovnej(r, video)
    if not zmeny:
        k.zelena("stránka zavřená bez změn.", "nic, nebo se zeptej, jestli chce něco změnit slovy.")
    else:
        dalsi = "nový náhled (nahled) a pak vzhled --plan" if "text" in zmeny else "vzhled --plan (nové video podle plánu)"
        k.zelena("uloženo: %s. Náhled teď %s." % (", ".join(sorted(zmeny)), "odpovídá" if stav_nahledu["stav"] == "aktualni" else "neobsahuje poslední úpravy"),
                 "%s, až řekne „vytvoř reel“." % dalsi, {"zmeny": sorted(zmeny), "nahled": stav_nahledu})
    _prubeh(r)
    return k.kod()


def krok_stav(a):
    r = _reel(a.reel)
    stav = hlaseni.nacti_stav(r / "PRACOVNI")
    print("Reel: %s (%s)" % (stav.get("nazev", r.name), r))
    for krok in stav.get("poradi", []):
        v = stav["kroky"][krok]
        print(" %s %s: %s (%s, %.0f s)" % (hlaseni.ZNACKY[v["stav"]], krok, v["zprava"], v["kdy"][:16].replace("T", " "), v["trvani_s"]))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["knihovna"]:          # knihovna stylů v počítači (studio/knihovna.py), vlastní parametry
        from . import knihovna
        return knihovna.main(argv[1:])
    p = argparse.ArgumentParser(prog="STUDIO", description="Claude Reel Studio: kroky etapy A")
    sub = p.add_subparsers(dest="krok", required=True)
    z = sub.add_parser("zaloz", help="založit složku reelu")
    z.add_argument("--reely", required=True, help="složka Reely (kořen, mimo iCloud a OneDrive)")
    z.add_argument("--nazev", required=True)
    z.set_defaults(f=krok_zaloz)
    c = sub.add_parser("kopie", help="zkopírovat video do složky reelu")
    c.add_argument("--reel", required=True)
    c.add_argument("video", nargs="*", help="cesty k videím (když nic, vezmou se videa už v PODKLADY-SEM)")
    c.add_argument("--nahravka", action="store_true",
                   help="videa jsou nahrávky obrazovky: do PODKLADY-SEM/NAHRAVKY-OBRAZOVKY, do reelu jako video v rámečku")
    c.set_defaults(f=krok_kopie)
    kv = sub.add_parser("kontrola-videa", help="formát, otočení, snímkování, HDR, zvuk")
    kv.add_argument("--reel", required=True)
    kv.set_defaults(f=krok_kontrola_videa)
    pr = sub.add_parser("prepis", help="přepis s časy slov")
    pr.add_argument("--reel", required=True)
    pr.add_argument("--model", default="turbo", help="turbo (rychlejší) nebo large-v3 (přesnější na jména)")
    pr.add_argument("--porovnat", action="store_true", help="přepsat i druhým modelem a označit nejistá slova")
    pr.add_argument("--jazyk", choices=("auto", "cs", "sk"), help="jazyk řeči: auto (pozná z hlasu, výchozí), cs, sk")
    pr.set_defaults(f=krok_prepis)
    nv = sub.add_parser("navrh", help="zdvojené věty a návrh výběru")
    nv.add_argument("--reel", required=True)
    nv.add_argument("--znovu", action="store_true", help="zahodit platný výběr a začít od návrhu")
    nv.set_defaults(f=krok_navrh)
    nh = sub.add_parser("nahled", help="hrubý střih jako MP4")
    nh.add_argument("--reel", required=True)
    nh.add_argument("--vyber", help="věty v pořadí, oddělené čárkou (k1-v01,k1-v02)")
    nh.add_argument("--vynechat", help="slova k vystřižení: k1-v05:1,2;k1-v07:0 (pořadí slov od 0)")
    nh.add_argument("--kontrola-slov", action="store_true", help="přečíst hotový zvuk přepisovačem a porovnat (pomalejší)")
    nh.add_argument("--model", default="turbo")
    nh.add_argument("--preset", default="fast", help="rychlost kódování ffmpeg (fast pro náhled, medium pro finál)")
    nh.add_argument("--editor", action="store_true", help="po náhledu připomenout otevření editoru, i když ho má nastavení vypnutý")
    nh.add_argument("--bez-editoru", action="store_true", help="neotvírat editor, i když to má nastavení zapnuté")
    nh.add_argument("--vystrihnout", help="úseky k vystřižení podle času originálu: k1:10.92-11.13;k3:21.8-22.1 (přeřek, „mmm“); \"\" = žádné")
    nh.add_argument("--cele", action="store_true", help="bez střihu: celé video tak, jak je natočené (žádné pauzy ani věty pryč)")
    nh.add_argument("--bez-titulku", action="store_true", help="náhled bez titulků (rychlejší, jako dřív)")
    nh.add_argument("--tempo", choices=("uderne", "bezne", "procitene"), help="úderně (kratší pauzy, rychlejší b-roll), procítěně (pauzy mezi myšlenkami, delší b-roll s prolnutím); pamatuje se")
    nh.set_defaults(f=krok_nahled)
    vz = sub.add_parser("vzhled", help="hotový reel s hookem, titulky a vsuvkami z poslední časové osy")
    vz.add_argument("--reel", required=True)
    vz.add_argument("--hook", help="text hooku (výchozí: první věta reelu)")
    vz.add_argument("--vsuvka", action="append", help="vsuvka jako text@číslo-věty, část mezi hvězdičkami je zvýrazněná; lze víckrát")
    vz.add_argument("--vzhled", help="serif, plny nebo klickrasy (výchozí z nastavení)")
    vz.add_argument("--zoom", action="store_true", help="střídat přiblížení záběru na střizích")
    vz.add_argument("--zvyraznit", help="slovo hooku, které dostane zvýrazňovač (výchozí nejdelší slovo)")
    vz.add_argument("--mini", action="append", help="krátký nadpis v průběhu videa: text@číslo-věty (\\n = nový řádek); lze víckrát")
    vz.add_argument("--bez-vyzvy", action="store_true", help="nedělat kartu z věty s výzvou do komentáře")
    vz.add_argument("--bez-hooku", action="store_true", help="bez karty hooku")
    vz.add_argument("--bez-mini", action="store_true", help="poprvé nenavrhovat mikro-nadpisy automaticky")
    vz.add_argument("--smaz-mini", action="append", help="smazat mikro-nadpis, který obsahuje tenhle text; lze víckrát")
    vz.add_argument("--plan", action="store_true", help="stavět podle PRACOVNI/plan-strihu.json (krok plan)")
    vd = sub.add_parser("vzdy", help="poznámka zákaznice „vždycky“: stálá úprava vzhledu nebo poznámka pro studio")
    vd.add_argument("--reel", required=True)
    vd.add_argument("--nastav", action="append", help="vzhled.cast.klic=hodnota, třeba vogue.mini_nahore.velikost=109; lze víckrát")
    vd.add_argument("--poznamka", help="věta zákaznice, zapíše se do NASTAVENI/poznamky-zakaznice.md")
    ot = sub.add_parser("oprava-titulku", help="Claude opraví chyby přepisu v titulcích (video se nestříhá)")
    ot.add_argument("--reel", required=True)
    ot.add_argument("--oprava", action="append", help="k1-v03=celý opravený text věty; lze víckrát")
    ot.add_argument("--naucit", action="append", help="špatně=správně (jedno slovo), studio si to zapamatuje pro další reely")
    ot.set_defaults(f=krok_oprava_titulku)
    sy = sub.add_parser("styl", help="kód stylu z knihovny stylů („styl: vogue; nadpisy: …“) nebo věta zákaznice („písmo větší“)")
    sy.add_argument("--reel", required=True)
    sy.add_argument("--kod", help="věta z knihovny stylů (Zkopírovat kód); bez --kod i --veta se vezme poslední styl z NASTAVENI/styl.json")
    sy.add_argument("--veta", help="obyčejná věta: písmo větší, písmo červeně, dej červené pozadí, titulky po slovech, titulky nahoru, hook nahoru ale jemně, zachovej moje písmo, bez zvuků, hlasitěji")
    sy.add_argument("--vzdy", action="store_true", help="větu zapsat i trvale („vždycky“) do NASTAVENI")
    sy.add_argument("--z-knihovny", help="soubor JSON s uloženým výběrem z knihovny stylů (záznam pro-reel s polem kod)")
    sy.set_defaults(f=krok_styl)
    vd.set_defaults(f=krok_vzdy)
    br = sub.add_parser("broll", help="b-roll: video bez řeči s nadpisem přes obraz (zvuk původní ztišený, hudbu přidá zákaznice v Instagramu)")
    br.add_argument("--reel", required=True)
    br.add_argument("--klip", type=int, help="pořadí klipu ve složce reelu (výchozí 1)")
    br.add_argument("--od", type=float, help="začátek úseku v klipu (s), výchozí 0")
    br.add_argument("--delka", type=float, help="délka úseku (s), výchozí 10")
    br.add_argument("--cele", action="store_true", help="celý klip od --od do konce")
    br.add_argument("--nadpis", action="append", help="text přes obraz; řádky lomítkem; víc nadpisů za sebou = parametr vícekrát")
    br.add_argument("--nadpis-casy", dest="nadpis_casy", help="začátky nadpisů v sekundách: „0 | 3.2 | 5.8“ (jinak podle délky textu)")
    br.add_argument("--velikost", help="velikost nadpisu: „120%%“ nebo px")
    br.add_argument("--y", type=int, help="horní okraj nadpisu v px (výchozí: horní třetina)")
    br.add_argument("--stitky", help="štítky pod nadpisem: „Claude | Notion“")
    br.add_argument("--ikony", help="ikony aplikací z podkladů s popiskem: „ikona-claude.jpg:Claude | ikona-notion.jpg:Notion“")
    br.add_argument("--staticky", action="store_true", help="nadpis hned od začátku a bez nástupu")
    br.add_argument("--sipka", action="store_true", help="šipka propojení mezi ikonami")
    br.add_argument("--zvyraznit", help="slova nadpisu ke zvýraznění: „content manažera“")
    br.add_argument("--y-stitky", dest="y_stitky", type=int, help="střed štítků v px (výchozí: pod nadpisem)")
    br.add_argument("--vzhled", help="vzhled (výchozí z nastavení, jinak vogue)")
    br.add_argument("--zvuk", choices=["puvodni", "ticho"], default="puvodni")
    br.add_argument("--podklady", help="složka s obrázky pro prvky")
    br.add_argument("--preset", default="medium")
    br.set_defaults(f=krok_broll)
    vo = sub.add_parser("vzor", help="uložit schválený reel jako vzor (šablonu) pro další reely")
    vo.add_argument("--reel", required=True)
    vo.add_argument("--nazev", required=True, help="název vzoru, třeba „Mluvící návod vogue“")
    vo.add_argument("--vzhled", help="vzhled vzoru, když poslední vykreslení bylo jiné (výchozí z PRACOVNI/vzhled.json)")
    vo.set_defaults(f=krok_vzor)
    vz.add_argument("--titulky", help="titulky z jiného vzhledu (třeba --vzhled vogue --titulky marcela)")
    vz.add_argument("--bez-masky", action="store_true", help="text vždy před osobu (bez masky osoby)")
    vz.add_argument("--podklady", help="složka s obrázky k vložkám a mřížce (výchozí PODKLADY-SEM reelu)")
    vz.add_argument("--broll", action="append", help="záběr z PODKLADY-SEM/B-ROLL k větě: soubor@číslo-věty; lze víckrát (jinak studio rozmístí samo)")
    vz.add_argument("--jen-hlas", dest="jen_hlas", action="store_true", help="celý reel ze záběrů v B-ROLL, z videa jen hlas")
    vz.add_argument("--bez-brollu", dest="bez_brollu", action="store_true", help="záběry z B-ROLL do reelu nedávat")
    vz.add_argument("--s-tvari", dest="s_tvari", action="store_true", help="zpátky z režimu jen hlas: tvář a záběry jen u některých vět")
    vz.add_argument("--zrus-broll", dest="zrus_broll", action="store_true", help="zapomenout dřívější přiřazení záběrů k větám (--broll)")
    vz.add_argument("--bez-zvuku-zaberu", dest="bez_zvuku_zaberu", action="store_true", help="zvuk záběrů (voda, kroky) pod hlas nedávat; pamatuje se")
    vz.add_argument("--se-zvukem-zaberu", dest="se_zvukem_zaberu", action="store_true", help="zvuk záběrů zase zapnout")
    vz.add_argument("--preset", default="medium")
    vz.set_defaults(f=krok_vzhled)
    zb = sub.add_parser("zabery", help="záběry pro b-roll: kvalita, nejlepší chvilky, náhledy, katalog a věty reelu")
    zb.add_argument("--reel", required=True)
    zb.add_argument("--podklady", help="složka podkladů (výchozí PODKLADY-SEM reelu)")
    zb.add_argument("--popis", help="JSON s popisem záběrů a chvilek od Clauda (názvy, popis, nálada, vyřazení)")
    zb.set_defaults(f=krok_zabery)
    pd = sub.add_parser("podklady", help="podklady k efektům z knihovny stylů: zapsat, co zákaznice dodala, a vypsat, co chybí")
    pd.add_argument("--reel", required=True)
    pd.add_argument("--nastav", action="append", help="efekt.pole=hodnota (třeba ig_komentar.slovo=STUDIO); lze víckrát")
    pd.add_argument("--profil-jmeno", help="jméno účtu na Instagramu (pro všechny reely)")
    pd.add_argument("--profil-popis", help="řádek pod jménem účtu (pro všechny reely)")
    pd.add_argument("--profil-fotka", help="profilová fotka (soubor v PODKLADY-SEM nebo celá cesta); zkopíruje se do NASTAVENI")
    pd.add_argument("--vynechat", action="append", help="efekt, který zákaznice v tomhle reelu nechce (klíč, třeba sprej)")
    pd.add_argument("--vratit", action="append", help="vrátit dřív vynechaný efekt")
    pd.set_defaults(f=krok_podklady)
    ed = sub.add_parser("editor", help="editor přepisu v prohlížeči")
    ed.add_argument("--reel", required=True)
    ed.add_argument("--neotvirat", action="store_true", help="neotvírat prohlížeč sám")
    ed.add_argument("--cekat", type=int, default=1800, help="kolik sekund čekat na uložení")
    ed.add_argument("--port", type=int, default=0, help="port serveru (0 = náhodný volný)")
    ed.set_defaults(f=krok_editor)
    pb = sub.add_parser("prubeh", help="přehled průběhu střihu v prohlížeči")
    pb.add_argument("--reel", required=True)
    pb.add_argument("--neotvirat", action="store_true")
    pb.set_defaults(f=krok_prubeh)
    pl = sub.add_parser("plan", help="plán obrazovky věta po větě (ke schválení)")
    pl.add_argument("--reel", required=True)
    pl.add_argument("--podklady", help="složka se skript.txt, mikro-nadpisy.txt a obrázky (výchozí PODKLADY-SEM reelu)")
    pl.add_argument("--vzor", help="použít uložený vzor z Reely/VZORY (slug)")
    pl.set_defaults(f=krok_plan)
    pr2 = sub.add_parser("plan-reelu", help="stránka Plán reelu: scény jako karty, vlastní média, věty s prvky")
    pr2.add_argument("--reel", required=True)
    pr2.add_argument("--neotvirat", action="store_true", help="neotvírat prohlížeč (adresa se vypíše)")
    pr2.add_argument("--cekat", type=int, default=7200, help="jak dlouho stránka běží, v sekundách")
    pr2.add_argument("--port", type=int, default=0)
    pr2.set_defaults(f=krok_plan_reelu)
    st = sub.add_parser("stav", help="co je hotové")
    st.add_argument("--reel", required=True)
    st.set_defaults(f=krok_stav)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
