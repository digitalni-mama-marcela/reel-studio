"""Přehled průběhu střihu (D27): jedna místní stránka VYSTUP/prubeh.html, která se sama obnovuje.

Ukazuje kroky (hotovo, běží, čeká, chyba), plán vět (zůstává, vystřiženo a proč, vynechaná slova),
časovou osu reelu jako pruh, délku proti cíli a náhledové obrázky úseků. Obrázky z videa vidí jen
zákaznice v prohlížeči, Claude se na ně nedívá. Nic se neodesílá, stránka je obyčejný soubor.
Napsáno od nuly z popisu Marcely (16. 10. 2026).
"""
import html
import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import hlaseni, projekt

KROKY = ["Založení reelu", "Kopie videa", "Kontrola videa", "Přepis", "Návrh střihu", "Náhled", "Editor přepisu"]
BARVY_KLIPU = ["#6D8AA1", "#B3A49D", "#8aa16d", "#a16d8a"]


def _fmt(s):
    return hlaseni.cas_text(s).replace(".", ",")


def nasbirej(reel):
    """Všechno, co stránka potřebuje, z PRACOVNI."""
    s = projekt.slozky(reel)
    prac = s["pracovni"]
    stav = hlaseni.nacti_stav(prac)
    nast = projekt.nastaveni(reel)
    klipy = projekt.nacti_klipy(reel, s_energii=False)
    navrh = projekt.nacti_json(prac / "navrh-strihu.json", {}) or {}
    vyber_json = projekt.nacti_json(prac / "vyber.json")
    osa = projekt.nacti_json(prac / "casova-osa.json")
    smazane_editor = set()
    for u in prac.glob("upravy-pouzite-*.json"):
        try:
            smazane_editor.update(json.loads(u.read_text(encoding="utf-8")).get("smazane_vety", []))
        except (OSError, ValueError):
            pass
    if vyber_json:
        vyber = [tuple(x) for x in vyber_json["vyber"]]
        vynechat = vyber_json.get("vynechat", {})
    elif navrh.get("vyber"):
        vyber = [tuple(x) for x in navrh["vyber"]]
        vynechat = {}
    else:
        vyber = projekt.vsechny_vety(klipy)
        vynechat = {}
    if osa and osa.get("vynechat"):
        vynechat = osa["vynechat"]
    vybrane = {vid for _, vid in vyber}
    duvody = {}
    for d in navrh.get("dvojice", []):
        if d.get("vyhodit"):
            duvody[d["vyhodit"]] = ("ve druhém pokusu vynechána (před %s)" % d["b"]) if d.get("druh") == "prvni_pokus" else "opakuje se později jako %s" % d["b"]
    radky = []
    for c, k in enumerate(klipy):
        for v in k["vety"]:
            vid = v["id"]
            if vid in vybrane:
                ven = set(vynechat.get(vid, []))
                stavv = "castecne" if ven else "zustava"
                duvod = "vystřižena slova: %s" % ", ".join(w["w"] for i, w in enumerate(v["slova"]) if i in ven) if ven else ""
            else:
                stavv = "vystrizena"
                duvod = "smazáno v editoru" if vid in smazane_editor else duvody.get(vid, "nevybráno")
            radky.append({"id": vid, "klip": c, "start": v["start"], "end": v["end"], "text": v["text"], "stav": stavv,
                          "duvod": duvod, "slova": [w["w"] for w in v["slova"]], "ven": sorted(set(vynechat.get(vid, [])))})
    nahledy = sorted(s["vystup"].glob("nahled-*.mp4"), key=lambda p: p.stat().st_mtime)
    return {"nazev": projekt.nazev_reelu(reel), "slozka": str(reel), "stav": stav, "radky": radky, "osa": osa,
            "klipy": klipy, "cil_s": nast["delka_reelu"]["cil_s"], "nejvic_s": nast["delka_reelu"]["nejvic_s"],
            "nahled": nahledy[-1].name if nahledy else None, "pauzy": navrh.get("pauzy", [])}


def nahledove_obrazky(reel, osa, sirka=240):
    """Jeden obrázek na úsek (první snímek úseku) do PRACOVNI/nahledy. Už hotové se nedělají znovu. Vrátí {index úseku: cesta}."""
    prac = projekt.slozky(reel)["pracovni"] / "nahledy"
    prac.mkdir(parents=True, exist_ok=True)
    out = {}
    for i, u in enumerate(osa.get("useky", [])):
        cil = prac / ("usek-%d-%06d.jpg" % (u["klip"], int(u["od"] * 1000)))
        if not cil.exists():
            try:
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", "%.3f" % (u["od"] + min(0.2, u["delka"] / 2)),
                                "-i", osa["klipy"][u["klip"]], "-frames:v", "1", "-vf", "scale=%d:-2" % sirka, "-q:v", "5", str(cil)],
                               check=True, capture_output=True, timeout=30)
            except (subprocess.SubprocessError, OSError):
                continue
        out[i] = cil
    return out


STYL = """
:root{--pozadi:#faf7f2;--text:#2b2522;--slabe:#8a7f78;--ramecek:#e4ddd4;--zelena:#2f7d4f;--cervena:#b23a3a;--oranzova:#c07a1a;--seda:#cfc8c0;--modra:#6D8AA1}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;background:var(--pozadi);color:var(--text)}
main{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}.pod{color:var(--slabe);font-size:13px;margin-bottom:16px}
.kroky{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:10px 0 18px}
.krok{display:flex;align-items:center;gap:6px;font-size:13px;padding:6px 10px;border:1px solid var(--ramecek);border-radius:20px;background:#fff}
.tecka{width:12px;height:12px;border-radius:50%;background:var(--seda);flex:none}
.zelena .tecka{background:var(--zelena)}.cervena .tecka{background:var(--cervena)}.bezi .tecka{background:var(--oranzova);animation:pulz 1s infinite}
@keyframes pulz{0%{opacity:1}50%{opacity:.3}100%{opacity:1}}
.hlaska{background:#fff;border:1px solid var(--ramecek);border-radius:8px;padding:10px 12px;font-size:15px;margin-bottom:16px}
.hlaska.cervena{border-color:var(--cervena)}.hlaska.zelena{border-color:var(--zelena)}
h2{font-size:14px;color:var(--slabe);margin:18px 0 8px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.osa{position:relative;height:34px;border-radius:6px;overflow:hidden;background:var(--seda);display:flex}
.usek{height:100%;border-right:2px solid #fff;font-size:11px;color:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;white-space:nowrap}
.delka{font-size:15px;margin:8px 0}.delka.pres-cil{color:var(--oranzova)}.delka.pres-max{color:var(--cervena);font-weight:600}
.nahledy{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px}.nahledy img{height:150px;border-radius:6px;flex:none}
table{width:100%;border-collapse:collapse;font-size:15px}td{padding:7px 6px;border-bottom:1px solid var(--ramecek);vertical-align:top}
td.cas{color:var(--slabe);font-size:12px;white-space:nowrap}td.id{color:var(--slabe);font-size:12px;white-space:nowrap}
tr.vystrizena td.text{color:var(--slabe);text-decoration:line-through}tr.castecne .ven{color:var(--cervena);text-decoration:line-through}
.duvod{font-size:12px;color:var(--oranzova);display:block;text-decoration:none}
.legenda{font-size:12px;color:var(--slabe);margin-top:6px}
"""


def sestav(data, obrazky=None):
    """HTML stránky z nasbíraných dat. obrazky: {index úseku: cesta relativní k VYSTUP}."""
    e = html.escape
    stav = data["stav"]
    kroky_html = []
    for k in KROKY:
        z = stav.get("kroky", {}).get(k)
        trida = z["stav"] if z else "ceka"
        popis = {"zelena": "hotovo", "cervena": "chyba", "bezi": "běží", "ceka": "čeká"}.get(trida, trida)
        kroky_html.append('<div class="krok %s"><span class="tecka"></span>%s <span style="color:var(--slabe)">%s</span></div>' % (trida, e(k), popis))
    posledni = stav.get("kroky", {}).get(stav.get("posledni_krok", ""), {})
    hlaska = ""
    if posledni:
        txt = hlaseni.zprava(posledni["stav"] if posledni["stav"] in hlaseni.ZNACKY else "info", posledni["krok"] + ":",
                             posledni["zprava"], posledni.get("dalsi_krok"), posledni.get("udelej"))
        hlaska = '<div class="hlaska %s">%s</div>' % (posledni["stav"], e(txt))
    osa = data["osa"]
    osa_html = ""
    if osa and osa.get("useky"):
        celk = osa["delka"] or 1
        casti = []
        for i, u in enumerate(osa["useky"]):
            sirka = max(0.5, 100 * u["delka"] / celk)
            barva = BARVY_KLIPU[u["klip"] % len(BARVY_KLIPU)]
            popisek = ", ".join(u.get("vety") or []) if sirka > 8 else ""
            casti.append('<div class="usek" style="width:%.2f%%;background:%s" title="klip %d, %s až %s">%s</div>' % (
                sirka, barva, u["klip"] + 1, _fmt(u["od"]), _fmt(u["do"]), e(popisek)))
        d = osa["delka"]
        trida = "pres-max" if d > data["nejvic_s"] else ("pres-cil" if d > data["cil_s"] else "")
        delka = '<div class="delka %s">Délka %s (cíl %s, nejvíc %s)%s</div>' % (
            trida, _fmt(d), _fmt(data["cil_s"]), _fmt(data["nejvic_s"]),
            " 🔴 nad limitem" if d > data["nejvic_s"] else (" ⚠️ nad cílem" if d > data["cil_s"] else ""))
        osa_html = '<h2>Časová osa reelu (%d úseků, %d střihů)</h2><div class="osa">%s</div>%s' % (
            len(osa["useky"]), max(0, len(osa["useky"]) - 1), "".join(casti), delka)
        if obrazky:
            osa_html += '<div class="nahledy">%s</div>' % "".join(
                '<img src="%s" alt="úsek %d" title="úsek %d, %s">' % (e(str(obrazky[i])), i + 1, i + 1, _fmt(osa["useky"][i]["vystup_od"]))
                for i in sorted(obrazky))
        if data.get("nahled"):
            osa_html += '<div class="legenda">Poslední náhled: %s (ve složce VYSTUP).</div>' % e(data["nahled"])
    radky = []
    for r in data["radky"]:
        if r["stav"] == "castecne":
            text = " ".join('<span class="ven">%s</span>' % e(w) if i in r["ven"] else e(w) for i, w in enumerate(r["slova"]))
        else:
            text = e(r["text"])
        duvod = '<span class="duvod">%s</span>' % e(r["duvod"]) if r["duvod"] else ""
        znak = {"zustava": "✅", "castecne": "✂️", "vystrizena": "⬜"}[r["stav"]]
        radky.append('<tr class="%s"><td>%s</td><td class="id">%s<br>klip %d</td><td class="cas">%s</td><td class="text">%s%s</td></tr>' % (
            r["stav"], znak, e(r["id"]), r["klip"] + 1, _fmt(r["start"]), text, duvod))
    zustava = sum(1 for r in data["radky"] if r["stav"] != "vystrizena")
    plan_html = ""
    if data["radky"]:
        plan_html = ('<h2>Plán vět (%d z %d zůstává)</h2><table>%s</table>'
                     '<div class="legenda">✅ zůstává · ✂️ zůstává bez některých slov · ⬜ vystřiženo (důvod pod větou). Změny děláš v editoru přepisu.</div>'
                     % (zustava, len(data["radky"]), "".join(radky)))
    else:
        plan_html = '<h2>Plán vět</h2><div class="legenda">Čeká na přepis.</div>'
    pauzy = ""
    if data.get("pauzy"):
        pauzy = '<div class="legenda">Dlouhé pauzy, které se zkrátí samy: %s</div>' % e(", ".join(
            "%.1f s mezi %s a %s" % (p["pauza_s"], p["po_vete"], p["pred_vetou"]) for p in data["pauzy"]))
    _t = datetime.now()     # ne strftime("%-d"): Windows ho nezná
    ted = "%d. %d. %d %s" % (_t.day, _t.month, _t.year, _t.strftime("%H:%M:%S"))
    return """<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3"><title>Průběh střihu: %s</title><style>%s</style></head><body><main>
<h1>%s</h1><div class="pod">Přehled průběhu střihu. Obnovuje se sám každé 3 sekundy. Naposledy %s. Složka: %s</div>
<div class="kroky">%s</div>%s%s%s%s
</main></body></html>""" % (e(data["nazev"]), STYL, e(data["nazev"]), ted, e(data["slozka"]), "".join(kroky_html), hlaska, osa_html, plan_html, pauzy)


def zapis(reel, s_obrazky=True):
    """Vygeneruje VYSTUP/prubeh.html (a náhledové obrázky). Vrátí cestu. Nikdy nesmí shodit krok, který ji volá."""
    s = projekt.slozky(reel)
    data = nasbirej(reel)
    obrazky = {}
    if s_obrazky and data["osa"]:
        cesty = nahledove_obrazky(reel, data["osa"])
        obrazky = {i: Path("..") / "PRACOVNI" / "nahledy" / c.name for i, c in cesty.items()}
    s["vystup"].mkdir(parents=True, exist_ok=True)
    cil = s["vystup"] / "prubeh.html"
    cil.write_text(sestav(data, obrazky), encoding="utf-8")
    return cil
