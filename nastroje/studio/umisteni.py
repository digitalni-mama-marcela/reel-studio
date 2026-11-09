"""Umístění nadpisu (hooku) a vsuvek tak, aby nezakryly obličej, a kontrola celé obrazovky.

Nadpis je nejdřív na hranici bezpečného pásma (270 px). Kdyby tam zasahoval do obličeje, posune se pod
bradu. Když se tam nevejde, zmenší se písmo. Když se nevejde ani tak, výsledek je červený.
"""
from . import poloha, titulky
from .titulky import BOK, DOLNI_OKRAJ, HORNI_OKRAJ, SIRKA, VYSKA

MEZERA = 40


def horni_okraj_titulku(styl):
    """Kde nahoře začíná blok titulků (dvouřádkový) ve zvoleném vzhledu."""
    st = styl["titulky"]
    vyska = st["radku"] * int(st["velikost"] * st["radek"] * 1.2)
    if st.get("stred_y"):
        return st["stred_y"] - vyska / 2
    return st["spodek"] - vyska


def titulky_mimo_oblicej(osa, styl_nazev, obliceje, min_velikost=50):
    """Když by titulky zakrývaly obličej (velká hlava nízko v záběru), posune je k spodnímu bezpečnému okraji
    a případně zmenší písmo. Vrátí název vzhledu k použití (odvozený '<vzhled>#reel'), původní vzhled se nemění."""
    import copy

    styl = titulky.STYLY[styl_nazev]
    st = styl["titulky"]
    if st.get("vedle_hlavy"):
        # stránky, které se vedle hlavy nevejdou, stojí na výchozím místě: to se dál posune mimo obličej jako dřív
        titulky_vedle_hlavy(osa, st, obliceje)
    if st.get("stred_y"):
        return styl_nazev
    okno = poloha.sjednoceni(obliceje, 0, osa["delka"], 0.0)
    if not okno:
        return styl_nazev
    kandidati = [(st["spodek"], st["velikost"], st["radku"]), (VYSKA - DOLNI_OKRAJ, st["velikost"], st["radku"])]
    for v in range(st["velikost"] - 6, min_velikost - 1, -6):
        kandidati.append((VYSKA - DOLNI_OKRAJ, v, st["radku"]))
    if st["radku"] > 1:
        for v in range(st["velikost"], min_velikost - 1, -6):          # jeden řádek, méně slov na stránku
            kandidati.append((VYSKA - DOLNI_OKRAJ, v, 1))
    for spodek, velikost, radku in kandidati:
        vyska = radku * int(velikost * st["radek"] * 1.2)
        obd = (BOK, spodek - vyska, SIRKA - BOK, spodek)
        if not poloha.protina(obd, okno):
            if (spodek, velikost, radku) == (st["spodek"], st["velikost"], st["radku"]):
                return styl_nazev
            novy = copy.deepcopy(styl)
            novy["titulky"].update({"spodek": spodek, "velikost": velikost, "radku": radku,
                                    "max_slov": min(st["max_slov"], 4) if radku == 1 else st["max_slov"]})
            nazev = styl_nazev + "#reel"
            titulky.STYLY[nazev] = novy
            osa["titulky_uprava"] = {"spodek": spodek, "velikost": velikost, "radku": radku, "puvodne": [st["spodek"], st["velikost"]]}
            return nazev
    return styl_nazev


def titulky_vedle_hlavy(osa, st, obliceje, odstup=36, prekazky=None):
    """Titulky po jednom slovu stojí vedle hlavy na straně, kde je víc místa (rozbor reelu 29. 10. 2026), nebo při
    st["poloha"] == "hrud" uprostřed šířky ve výšce hrudi,
    ve výšce tváře. Když vedle hlavy místo není, zkusí se pod bradou, pak u spodního bezpečného okraje a pak
    výchozí místo vzhledu. Zkouší se se skutečným obdélníkem textu a stejným oknem obličeje jako v kontrole.
    prekazky = [(od, do, obdélník)] nadpisů a prvků, kterým se titulky vyhnou (volá se znovu po přípravě prvků).
    Zapíše osa["titulky_polohy"]: střed [x, y] každé stránky, nebo None (výchozí místo). Vrátí počet stránek mimo výchozí."""
    font = titulky.pismo(st["pismo"], st["velikost"], st["varianta"])
    vyska_textu = st["velikost"] * st["radek"]
    polohy, n = [], 0
    stranky = titulky.vypln_stranky(osa["slova"], st)
    for i, s in enumerate(stranky):
        # konec stránky jako v titulky.Kreslic (do dalšího slova, nejvýš 0,3 s po konci); obě okna sjednocená,
        # protože kratší okno bez vzorku sáhne po vzorcích z delšího okolí
        konec = min(stranky[i + 1][0]["start"] if i + 1 < len(stranky) else 1e9, s[-1]["end"] + 0.30)
        okna = [poloha.sjednoceni(obliceje, s[0]["start"], t1, 0.3) for t1 in (konec, s[-1]["end"] + 0.30)] if obliceje else []
        okna = [o for o in okna if o]
        okno = (min(o[0] for o in okna), min(o[1] for o in okna), max(o[2] for o in okna), max(o[3] for o in okna)) if okna else None
        if not okno:
            polohy.append(None)
            continue
        w = font.getlength(" ".join(titulky.zobraz(x["w"], st) for x in s))
        cy_tvar = max(HORNI_OKRAJ + 80, min(VYSKA - DOLNI_OKRAJ - 80, okno[1] + 0.55 * (okno[3] - okno[1])))
        vlevo, vpravo = okno[0] - odstup - BOK, SIRKA - BOK - odstup - okno[2]
        strany = [(okno[0] - odstup - w / 2, cy_tvar), (okno[2] + odstup + w / 2, cy_tvar)]
        if vpravo > vlevo:
            strany.reverse()
        # u spodního okraje: střed tak, aby spodek textu seděl přesně na hranici pásma
        _, _, ob = titulky.vykresli_titulky(s, len(s), st, [SIRKA // 2, 1000])
        dole = (SIRKA / 2, 1000 + (VYSKA - DOLNI_OKRAJ - 1) - ob[3])
        kandidati = strany + [((okno[0] + okno[2]) / 2, okno[3] + odstup + vyska_textu / 2), dole, None]
        if st.get("poloha") == "hrud":
            # Marcela 29. 10.: vpravo je na Instagramu lišta (srdce, komentáře), titulky proto doprostřed šířky
            # do výšky hrudi mezi ruce: pod okno obličeje o čtvrtinu jeho výšky, nejníž nad spodní bezpečné pásmo
            cy_hrud = min(VYSKA - DOLNI_OKRAJ - 60, okno[3] + 0.22 * (okno[3] - okno[1]))
            kandidati = [(SIRKA / 2, cy_hrud), dole, None]
        v_case = [r for od, do, r in (prekazky or []) if od < konec and do > s[0]["start"]]
        volba = None
        for k in kandidati:
            if k is not None:
                cx = max(BOK + w / 2, min(SIRKA - BOK - w / 2, k[0]))
                k = [int(round(cx)), int(round(k[1]))]
            _, _, ob = titulky.vykresli_titulky(s, len(s), st, k)
            if ob[1] >= HORNI_OKRAJ and ob[3] <= VYSKA - DOLNI_OKRAJ and not poloha.protina(ob, okno) \
                    and not any(poloha.protina(ob, r) for r in v_case):
                volba = k
                break
        polohy.append(volba)
        n += volba is not None
    osa["titulky_polohy"] = polohy
    return n


def okno_pro_nadpis(okno, podil=0.28):
    """Pro nadpis nevadí překrytí vlasů: horních 28 % rozšířeného obdélníku obličeje (vlasy nad čelem) se nepočítá.
    Text nad hlavou bez karty smí až 40 % (vlasy a čelo, jako v oblíbených reelech Marcely, 19. 10.)."""
    if not okno:
        return okno
    return (okno[0], okno[1] + podil * (okno[3] - okno[1]), okno[2], okno[3])


def umisti(osa, styl_nazev, obliceje):
    """Doplní do osy y (a velikost) nadpisu a vsuvek. Vrátí seznam varování, prázdný = zelená."""
    styl = titulky.STYLY[styl_nazev]
    varovani = []
    horni_titulky = horni_okraj_titulku(styl)
    h = osa.get("hook")
    if h:
        za = bool(h.get("za_hlavou") or styl["hook"].get("za_hlavou"))
        okno = okno_pro_nadpis(poloha.sjednoceni(obliceje, h["od"], h["do"]), 0.55 if za else 0.28)
        velikost = styl["hook"]["velikost"]
        h["y"], ok = None, False
        if h.get("efekt") and "text_puvodni" not in h:
            h["text_puvodni"] = h["text"]
        while velikost >= 52 and not ok:
            if h.get("efekt"):
                from . import efekty
                # karta se sama nezalamuje: řádky podle šířky vzhledu (ruční zalomení \n se dodrží)
                if "\n" not in h["text_puvodni"]:
                    rad, _, _ = titulky.radky_nadpisu(h["text_puvodni"], styl["hook"], velikost)
                    h["text"] = "\n".join(rad)
                sb, vb = efekty.velikost_bloku(dict(h, velikost=velikost), styl["hook"])
            else:
                sb, vb, _ = titulky.velikost_hooku(h["text"], styl["hook"], velikost)
            if sb <= SIRKA - 2 * BOK:
                # kam zkusit nadpis: horní okraj pásma, pod bradu, nad obličej (když je obličej nízko), dole nad titulky
                mista = [HORNI_OKRAJ, int(okno[3]) + MEZERA if okno else HORNI_OKRAJ]
                if okno:
                    mista.append(int(okno[1]) - MEZERA - vb)
                # nadpis je nadpis: nahoře, pod bradou nebo nad obličejem, nikdy dole jako titulek (Marcela 18. 10.)
                for y in mista:
                    if y < HORNI_OKRAJ:
                        continue
                    obd = ((SIRKA - sb) / 2, y, (SIRKA + sb) / 2, y + vb)
                    misto_pod_titulky = h.get("skryt_titulky") or y + vb <= horni_titulky - MEZERA
                    if (not okno or not poloha.protina(obd, okno)) and misto_pod_titulky and y + vb <= VYSKA - DOLNI_OKRAJ:
                        h["y"], h["velikost"], ok = y, velikost, True
                        break
            velikost -= 4
        if not ok:
            h["y"], h["velikost"] = HORNI_OKRAJ, styl["hook"]["velikost"]
            varovani.append("Nadpis se nevejde mimo obličej.")
        if styl["hook"].get("posun_y"):
            # věta zákaznice „hook nahoru / dolů“ (krok styl --veta): posun v px, horní bezpečné pásmo se nepouští
            h["y"] = int(max(HORNI_OKRAJ, min(VYSKA - DOLNI_OKRAJ - 80, h["y"] + int(styl["hook"]["posun_y"]))))
    for m in osa.get("mini", []):
        from . import efekty
        if m.get("styl_puvodni"):
            m["styl"], m["text"] = m["styl_puvodni"], m.get("text_puvodni", m["text"])
        st = styl[m.get("styl", "mini")]
        okno = poloha.sjednoceni(obliceje, m["od"], m["do"])
        velikost = m.get("velikost_zadana", st["velikost"])
        m["velikost_zadana"] = velikost
        if m.get("pevne_y") is not None:
            # poloha zadaná v plánu (nad prstem, který na slovo ukazuje): neposouvat, jen nepustit do horního pásma
            m["y"], m["velikost"], m["nad_oblicejem"] = max(HORNI_OKRAJ, int(m["pevne_y"])), velikost, True
            continue
        ok = False
        dole = m.get("pozice") == "dole"      # pod titulky, mezi titulky a spodním bezpečným okrajem (a před tlačítky vpravo)
        nejmensi = 90 if m.get("styl") == "slovo_velke" else 34
        while velikost >= nejmensi and not ok:
            sb, vb = efekty.velikost_bloku(dict(m, velikost=velikost), st)
            if m.get("skryt_titulky"):
                y = int(VYSKA - DOLNI_OKRAJ - vb)
                vejde = sb <= SIRKA - 2 * BOK and (not okno or not poloha.protina(((SIRKA - sb) / 2, y, (SIRKA + sb) / 2, y + vb), okno))
            elif dole:
                tt = styl["titulky"]
                konec_titulku = (tt["stred_y"] + tt["radku"] * int(tt["velikost"] * tt["radek"] * 1.2) / 2) if tt.get("stred_y") else tt["spodek"]
                y = int(konec_titulku) + 34
                vejde = sb <= 800 and y + vb <= VYSKA - DOLNI_OKRAJ - 10
            else:
                # pod bradou; když tam není místo (přiblížený záběr), nad obličejem jako v oblíbených reelech (vlasy nevadí)
                y = int(okno[3]) + MEZERA if okno else 700
                vejde = sb <= SIRKA - 2 * BOK and y + vb <= horni_titulky - 24
                # nadpis ve stylu „za hlavou“ pod bradou by schovalo tělo (Marcela 21. 10., hook zmizel za svetrem):
                # zkusit nejdřív nad hlavu; když to nejde, až dole pod bradou jako štítek vpředu
                if vejde and okno and styl.get(m.get("styl", "mini"), {}).get("za_hlavou") and not m.get("za_hlavou_pod_bradou"):
                    vejde = False
                hlava_u_okraje = bool(okno) and okno[1] < HORNI_OKRAJ + 180
                if not vejde and okno and sb <= SIRKA - 2 * BOK and not hlava_u_okraje:
                    bez_karty = m.get("styl") in ("mini_nahore", "slovo_velke") or (m.get("styl", "mini") == "mini" and "mini_nahore" in styl)
                    za = bool(m.get("za_hlavou") or styl.get("mini_nahore" if bez_karty and m.get("styl") != "slovo_velke" else m.get("styl", "mini"), {}).get("za_hlavou"))
                    # za hlavou: aspoň 70 % písmen vidět; jedno obří slovo smí hlouběji (Marcela 19. 10.: NADPIS větší)
                    m["vlasy_podil"] = (0.5 if m.get("styl") == "slovo_velke" else 0.35) if za else (0.40 if bez_karty else 0.28)
                    on = okno_pro_nadpis(okno, m["vlasy_podil"])
                    if m.get("styl", "mini") == "mini" and "mini_nahore" in styl:
                        # nad hlavou vypadá karta jako nalepená z mobilu (Marcela 19. 10.): bez karty, větší, na dva řádky
                        m["styl_puvodni"], m["text_puvodni"] = m["styl"], m["text"]
                        m["styl"], st = "mini_nahore", styl["mini_nahore"]
                        slova_t = m["text"].replace("\n", " ").split()
                        if len(slova_t) >= 3 and "\n" not in m["text"]:
                            pul = (len(slova_t) + 1) // 2
                            m["text"] = " ".join(slova_t[:pul]) + "\n" + " ".join(slova_t[pul:])
                        velikost = m["velikost_zadana"] = st["velikost"]
                        sb, vb = efekty.velikost_bloku(dict(m, velikost=velikost), st)
                    # za hlavou: nejdřív úplně nahoře (hlava smí zakrýt jen spodek písmen), jinak těsně nad vlasy
                    for y2 in ((HORNI_OKRAJ, int(on[1]) - MEZERA - vb) if za else (int(on[1]) - MEZERA - vb, HORNI_OKRAJ)):
                        if y2 >= HORNI_OKRAJ and not poloha.protina(((SIRKA - sb) / 2, y2, (SIRKA + sb) / 2, y2 + vb), on):
                            y, vejde, m["nad_oblicejem"] = y2, True, True
                            break
            if vejde:
                m["y"], m["velikost"], ok = y, velikost, True
            velikost -= 4
        if not ok and okno and m.get("styl") in ("mini_nahore", "mini") and "podklad" in styl.get("mini", {}):
            # hlava sahá až k hornímu okraji (text za hlavou by nebyl čitelný): nadpis jde pod bradu jako štítek
            # místo titulků (titulky se po tu dobu schovají), zadání 19. 10., oddíl 5 „dvouřádkový nápis v obdélnících“
            if m.get("styl_puvodni"):
                m["styl"], m["text"] = m["styl_puvodni"], m.get("text_puvodni", m["text"])
            m.pop("nad_oblicejem", None)
            m["za_hlavou"] = False
            st = styl[m.get("styl", "mini")]
            slova_t = m["text"].replace("\n", " ").split()
            if len(slova_t) >= 3 and "\n" not in m["text"]:
                pul = (len(slova_t) + 1) // 2
                m["text"] = " ".join(slova_t[:pul]) + "\n" + " ".join(slova_t[pul:])
            velikost = st["velikost"]
            sb, vb = efekty.velikost_bloku(dict(m, velikost=velikost), st)
            y = min(int(okno[3]) + MEZERA, VYSKA - DOLNI_OKRAJ - vb - 10)
            if y >= int(okno[3]) + 10 and sb <= SIRKA - 2 * BOK:
                m["y"], m["velikost"], m["skryt_titulky"], ok = y, velikost, True, True
        if not ok and okno and m.get("skryt_titulky") and m.get("styl") == "mini_silny":
            # karta přes celou šířku (WOW, výzva) při obličeji nízko v záběru: dole místo titulků, smí sáhnout na bradu
            # (záměr, jako mřížka), kontrola to nehlásí
            velikost = m["velikost_zadana"]
            sb, vb = efekty.velikost_bloku(dict(m, velikost=velikost), st)
            m["y"], m["velikost"], m["pres_oblicej"], ok = int(VYSKA - DOLNI_OKRAJ - vb), velikost, True, True
        if not ok and okno and st.get("za_hlavou") and m.get("styl") == "mini_nahore":
            # vzhled s nadpisy za hlavou (zapisnik): nahoru za hlavu, hlava smí zakrýt spodek písmen (maska osoby)
            m["y"], m["velikost"], m["za_hlavou"], m["nad_oblicejem"], m["vlasy_podil"] = HORNI_OKRAJ, st["velikost"], True, True, 0.5
            ok = True
        if ok and okno and m.get("nad_oblicejem") and st.get("stred_nad_hlavou"):
            # nadpis uprostřed mezi horním bezpečným okrajem a temenem hlavy (Marcela 29. 10.: „moc nahoře“)
            _, vb = efekty.velikost_bloku(dict(m, velikost=m["velikost"]), st)
            m["y"] = max(HORNI_OKRAJ, int((HORNI_OKRAJ + okno[1]) / 2 - vb / 2))
        if not ok:
            m["y"], m["velikost"] = 700, st["velikost"]
            varovani.append("Mini nadpis '%s' se nevejde mimo obličej a titulky." % m["text"].replace("\n", " "))
    for v in osa.get("vsuvky", []):
        okno = poloha.sjednoceni(obliceje, v["od"], v["do"])
        v["velikost"] = styl["vsuvka"]["velikost"]
        while True:
            _, _, ob = titulky.vykresli_vsuvku(dict(v, x=BOK, y=0), styl["vsuvka"])
            if ob[2] - ob[0] <= SIRKA - 2 * BOK or v["velikost"] <= 56:
                break
            v["velikost"] -= 8
        vyska = ob[3] - ob[1]
        y = int(okno[3]) + MEZERA if okno else 760
        v["x"] = BOK
        v["y"] = min(y, horni_titulky - vyska - MEZERA)
        if v["y"] < y - 1:
            varovani.append("Vsuvka '%s' je blíž k obličeji než obvykle." % v["text"])
    return varovani


def kontrola(osa, kreslic, obliceje):
    """Zkontroluje každý text proti obličeji, bezpečným okrajům a ostatním textům. Vrátí (problémy, počet kontrol)."""
    problemy, kontrol = [], 0
    obd = kreslic.obdelniky()
    for o in obd:
        x0, y0, x1, y1 = o["obdelnik"]
        okno = poloha.sjednoceni(obliceje, o["od"], o["do"], 0.3)
        if o["typ"] == "hook" or o.get("nad_oblicejem") or o.get("pres_oblicej"):
            okno = okno_pro_nadpis(okno, o.get("vlasy_podil") or 0.28)   # nad obličejem nevadí vlasy; mřížka přes obličej je záměr
        if o.get("pres_oblicej"):
            kontrol += 1
            continue
        kontrol += 1
        if okno and poloha.protina(o["obdelnik"], okno):
            problemy.append("%s v čase %.1f s zakrývá obličej" % (o["typ"], o["od"]))
        if x0 < BOK - 10 or x1 > SIRKA - BOK + 10:
            problemy.append("%s v čase %.1f s je moc u kraje (%d až %d px)" % (o["typ"], o["od"], x0, x1))
        if y0 < HORNI_OKRAJ - 5:
            problemy.append("%s v čase %.1f s zasahuje do horních %d px" % (o["typ"], o["od"], HORNI_OKRAJ))
        if y1 > VYSKA - DOLNI_OKRAJ:
            problemy.append("%s v čase %.1f s zasahuje do spodních %d px" % (o["typ"], o["od"], DOLNI_OKRAJ))
    for i, a in enumerate(obd):
        for b in obd[i + 1:]:
            if a.get("pozadi") or b.get("pozadi"):
                continue        # prvek pozadí (Instagram zeď) smí být pod texty
            if a["typ"] != b["typ"] and a["od"] < b["do"] and b["od"] < a["do"] and poloha.protina(a["obdelnik"], b["obdelnik"]):
                problemy.append("%s a %s se v čase %.1f s překrývají" % (a["typ"], b["typ"], max(a["od"], b["od"])))
                kontrol += 1
    return problemy, kontrol
