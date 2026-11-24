"""Zkouška na GitHubu (jen větve zkouska-*): každý efekt a každý styl z knihovny jeden po druhém do hotového videa.

Spuštění: <python studia> vsechny_efekty.py "<složka reelu>" "<výstupní složka>" <příkaz STUDIO...>
Pro každou položku: styl --kod, podklady, plan, vzhled. Ověří, že video vzniklo a že efekt je v časové ose,
a uloží snímek z místa efektu (vystup/<název>.jpg), ať se dá prohlédnout. Na konci tabulka a návratový kód 1,
když něco selhalo. Do ZIPu pro zákaznice nejde (.github se nebalí).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

R, OUT, STUDIO = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")      # konzole na Windows neumí ✓ a ✗
NASTROJE = Path(__file__).resolve().parents[2] / "nastroje"
sys.path.insert(0, str(NASTROJE))
from PIL import Image, ImageDraw  # noqa: E402
from studio import zadani  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
t = (NASTROJE / "knihovna" / "index.html").read_text(encoding="utf-8")
EF = json.loads(re.search(r"const EFEKTY = (\[.*?\]);\n", t, re.S).group(1))
NAZEV = {e["k"]: e["nazev"] for e in EF}

vety = (R / "PRACOVNI" / "klip-1" / "prepis-vety.txt").read_text(encoding="utf-8")
slova = [w for w in re.findall(r"[^\W\d_]{4,}", vety.split("]", 1)[-1])]
SLOVO = max(slova, key=len) if slova else "video"     # slovo, které ve videu opravdu zazní

HODNOTY = ["skladany_nadpis.radky=naučíme se | jak nechat Clauda | stříhat reely", "hravy_nadpis.text=5 tipů",
           "hravy_nadpis_gesta.nadpisy=NATOČÍM | CLAUDE | stříhá", "ig_komentar.slovo=" + SLOVO,
           "ig_komentar.odpoved=Posílám odkaz.", "sprej.text=reel",
           "papir_profil.cisla=145 příspěvků | 20 tis. sledujících | 300 sledovaných",
           "papir_otazka.text=Kolik hodin stříháš?", "papir_otazka.veta=2", "papir_profil.veta=2", "papir_komentare.texty=Konečně | Chci taky",
           "rucni_poznamka.text=tohle jsem já | bez stříhání", "psany_skrt.text=hodiny stříhání",
           "obalka_casopisu.nazev=máma", "obalka_casopisu.titulky=Celé video | sestříhané",
           "pocitadlo.kroky=SUROVÝ ZÁZNAM 3:52 | HOTOVÝ REEL 0:45",
           "pas_karet.soubory=obalka-0.jpg | obalka-1.jpg | obalka-2.jpg", "ikony.soubory=ikona-claude.png, ikona-notion.png",
           "plakat.soubor=plakat.png", "plakat.slovo=tvořit", "vypinac_plakat.soubor=plakat.png", "roj_karet.soubory=*",
           "slozka.soubory=*", "videa_okna.soubory=*", "storyboard.soubory=*", "pred_po.pred=obalka-0.jpg",
           "pred_po.po=obalka-1.jpg", "zapisnik.polozky=natočit video | nahrát | hotový reel", "zapisnik.nadpis=Co chci",
           "velke_slovo.slovo=" + SLOVO, "nalepky.slova=CapCut, titulky, přechody",
           "zprava.text=Sestříhej mi tohle video do reelu", "vsuvka.text=bez *CapCutu*", "vyzva.slovo=" + SLOVO]


def kod(efs, pol="hrud", pN="nahore", rez="slovo", vz="vlastní", fN="Montserrat", fT="Playfair Display"):
    POL = {"hrud": "na hrudi", "vedle": "vedle hlavy", "dole": "dole"}
    REZ = {"slovo": "po jednom slově", "veta": "celé věty", "veta_zvyr": "celé věty, zvýrazněné slovo"}
    e = [NAZEV[k] for k in efs if k in NAZEV]
    return "styl: %s; nadpisy: %s, #FFD43B, %s; titulky: %s, bílé, %s, %s, 100 %%; prvky: %s; zvuky: Cink (70 %%)" % (
        vz, fN, "uprostřed" if pN == "stred" else "nahoře", fT, POL[pol], REZ[rez], ", ".join(e) if e else "jen základ")


def beh(*argv):
    p = subprocess.run(STUDIO + list(argv), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def ve_videu(k, osa):
    typy = {x.get("typ") for x in osa.get("prvky", [])}
    if k == "vyzva":
        return any(m.get("vyzva") or m.get("styl") == "mini_silny" for m in osa.get("mini", []))
    if k == "vsuvka":
        return bool(osa.get("vsuvky"))
    if k == "hook":
        return bool(osa.get("hook")) or bool(typy & {"karty_slov", "skladany_nadpis", "hravy_nadpis"})
    if k == "broll":      # krátké zkušební video (3 věty): první věta zůstává s tváří, záběr se vejde jeden
        return len(osa.get("prekryvy") or []) >= 1
    if k == "jen-hlas":   # celý reel ze záběrů, bez mezery
        pk = osa.get("prekryvy") or []
        return len(pk) >= 2 and pk[0]["od"] == 0 and abs(pk[-1]["do"] - osa["delka"]) < 0.05
    if k == "velke_slovo":
        return any(m.get("styl") == "slovo_velke" for m in osa.get("mini", []))
    if k == "casomira":
        return any(x.get("casomira") for x in osa.get("prvky", [])) or bool((osa.get("hook") or {}).get("casomira"))
    if k in zadani.KARTY or k in zadani.DRIVE:
        return bool(zadani.typy_karty(k) & typy) or k in typy
    return k in typy


def cas_efektu(k, osa):
    kand = [x for x in osa.get("prvky", []) if k and (x.get("typ") == k or
            ((k in zadani.KARTY or k in zadani.DRIVE) and x.get("typ") in zadani.typy_karty(k)))]
    if k == "velke_slovo":
        kand = [m for m in osa.get("mini", []) if m.get("styl") == "slovo_velke"]
    if k == "vyzva":
        kand = [m for m in osa.get("mini", []) if m.get("vyzva") or m.get("styl") == "mini_silny"]
    if k == "vsuvka":
        kand = osa.get("vsuvky", [])
    if k in ("broll", "jen-hlas"):
        kand = osa.get("prekryvy", [])
    if kand and "od" in kand[0]:
        x = kand[0]
        return x["od"] + min(1.2, (x.get("do", x["od"] + 1) - x["od"]) * 0.6)
    return 1.5


p = R / "PODKLADY-SEM"
p.mkdir(exist_ok=True)
for i in range(6):
    im = Image.new("RGB", (540, 960), (40 * i + 30, 120, 160))
    ImageDraw.Draw(im).text((200, 450), "OBR %d" % i, fill="white")
    im.save(p / ("obalka-%d.jpg" % i))
for n in ("claude", "notion"):
    Image.new("RGB", (300, 300), (220, 120, 80)).save(p / ("ikona-%s.png" % n))
Image.new("RGB", (800, 1200), (30, 60, 90)).save(p / "plakat.png")
Image.new("RGB", (300, 300), (200, 120, 140)).save(p / "ja.jpg")

ulohy = [([k], k, {}) for k in NAZEV]
for vz, fN, fT in (("svestkovy_editor", "Bodoni Moda", "Inter"), ("zeleny_editor", "Fraunces", "DM Sans"),
                   ("slovo_a_kurziva", "Courier Prime", "Instrument Serif"), ("vlastní", "DM Serif Display", "Mulish")):
    ulohy.append(([], "vzhled-%s" % vz.replace("í", "i"), {"vz": vz, "fN": fN, "fT": fT}))
for pol in ("hrud", "vedle", "dole"):
    for rez in ("slovo", "veta", "veta_zvyr"):
        ulohy.append(([], "titulky-%s-%s" % (pol, rez), {"pol": pol, "rez": rez}))
ulohy.append(([], "nadpis-uprostred", {"pN": "stred"}))
# b-roll pod hlasem (prekryvy.py): dva záběry v PODKLADY-SEM/B-ROLL, jeden na šířku, jeden HDR jako z iPhonu
ulohy += [(["broll"], "broll", {}), (["jen-hlas"], "jen-hlas", {})]
import os  # noqa: E402
if os.environ.get("JEN"):        # jen vybrané položky (čárkami), pro ladění
    ulohy = [u for u in ulohy if u[1] in os.environ["JEN"].split(",")]

ff = None
kde = beh("kde")[1]
for radek in kde.splitlines():
    if radek.startswith("ffmpeg:"):
        ff = radek.split(":", 1)[1].strip()

b = p / "B-ROLL"
b.mkdir(exist_ok=True)
subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "mandelbrot=size=1920x1080:rate=25", "-t", "6",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(b / "na-sirku.mp4")], check=True)
subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-t", "6", "-vf",
                "format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,"
                "zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt2020:t=arib-std-b67:m=bt2020nc:r=tv,format=yuv420p10le",
                "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1", "-color_primaries", "bt2020",
                "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", str(b / "hdr-iphone.mov")], check=True)
vysledky, chyby = [], 0
for efs, nazev, kw in ulohy:
    for f in (R / "VYSTUP").glob("reel-*"):
        f.unlink()
    log = ""
    kroky = [("styl", "--reel", str(R), "--kod", kod(efs, **kw)),
             ["podklady", "--reel", str(R), "--profil-jmeno", "moje_jmeno", "--profil-popis", "AI tipy",
              "--profil-fotka", str(p / "ja.jpg")] + sum((["--nastav", h] for h in HODNOTY
                                                          if h.split(".")[0] in efs), []),
             ("plan", "--reel", str(R)),
             ("vzhled", "--reel", str(R), "--plan", "--zoom", "--hook", "Já už se nechci učit CapCut")
             + (() if efs in (["broll"], ["jen-hlas"]) else ("--bez-brollu",)) + (("--jen-hlas",) if efs == ["jen-hlas"] else ())]
    kody = []
    for k in kroky:
        kod_, out = beh(*k)
        kody.append(kod_)
        log += out
    mp4 = [m for m in sorted((R / "VYSTUP").glob("reel-*.mp4")) if "telefon" not in m.name]
    stav = "✓"
    if not mp4:
        stav = "✗ VIDEO NEPOSTAVENO"
        cerv = [l for l in log.splitlines() if "🔴" in l or "nestavěla" in l]
        poz = (cerv[-1] if cerv else log.strip().splitlines()[-1] if log.strip() else "")[:200]
    else:
        osa = json.loads((R / "PRACOVNI" / "casova-osa-vzhled.json").read_text(encoding="utf-8"))
        k = efs[0] if efs else None
        if k and not ve_videu(k, osa):
            stav = "✗ EFEKT CHYBÍ VE VIDEU"
        poz = ""
        c = cas_efektu(k, osa)
        subprocess.run([ff, "-y", "-v", "error", "-ss", "%.2f" % c, "-i", str(mp4[-1]), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(OUT / (nazev + ".jpg"))])
        if kody[-1] != 0:      # video vzniklo, ale kontrola hotového videa něco hlásí (třeba text u obličeje)
            stav = "✓" if stav == "✓" else stav
            poz = "kontrola: " + " ".join(re.findall(r"🔴 ([^🔴]{0,90})", log.split("🔴 Vzhled")[-1]))[:160]
        else:
            varovani = [l.strip() for l in log.splitlines() if "⚠️" in l]
            if varovani:
                poz = varovani[-1][:160]
    (OUT / (nazev + ".log")).write_text(log, encoding="utf-8")
    chyby += stav != "✓"
    radek = "%-24s %s %s" % (nazev, stav, poz)
    vysledky.append(radek)
    print(radek, flush=True)

(OUT / "souhrn.txt").write_text("\n".join(vysledky) + "\n", encoding="utf-8")
print("\nCelkem %d, selhalo %d." % (len(vysledky), chyby))
sys.exit(1 if chyby else 0)
