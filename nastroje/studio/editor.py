"""Editor přepisu k MP4 náhledu (D20): místní stránka editor.html a malý místní server (jen standardní knihovna).

Stránka ukazuje náhled a věty pod sebou. U každé věty: přehrát od ní, smazat nebo vrátit, upravit text,
kliknutím na slovo ho vynechat. Dole celková délka proti cílové. Tlačítko Uložit pošle úpravy serveru,
který poslouchá jen na tomhle počítači (127.0.0.1) a zapíše PRACOVNI/upravy.json. Záloha: stažení souboru.
Nic se neodesílá mimo počítač. Claude úpravy nečte, čte jen krátké shrnutí.
"""
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STRANKA = r"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Editor přepisu: __NAZEV__</title>
<style>
  :root { --pozadi:#faf7f2; --text:#2b2522; --slabe:#8a7f78; --ramecek:#e4ddd4; --zelena:#2f7d4f; --cervena:#b23a3a; --oranzova:#c07a1a; --zvyrazneni:#fff0c2; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; background:var(--pozadi); color:var(--text); }
  header { position: sticky; top:0; background:var(--pozadi); border-bottom:1px solid var(--ramecek); padding:12px 16px; z-index:2; }
  .radek { display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap; }
  video { width: 200px; max-height: 356px; background:#000; border-radius:8px; }
  h1 { font-size:18px; margin:0 0 6px; }
  .delka { font-size:16px; margin:6px 0; }
  .delka.pres-cil { color:var(--oranzova); }
  .delka.pres-max { color:var(--cervena); font-weight:600; }
  .pocitadlo { font-size:14px; color:var(--slabe); margin-bottom:6px; }
  button { font: inherit; padding:6px 10px; border:1px solid var(--ramecek); background:#fff; border-radius:6px; cursor:pointer; }
  button.hlavni { background:var(--zelena); color:#fff; border-color:var(--zelena); font-weight:600; padding:10px 16px; }
  button:disabled { opacity:.5; cursor:default; }
  main { padding: 8px 16px 120px; max-width: 900px; }
  .veta { display:grid; grid-template-columns: 40px 60px 1fr; gap:8px; align-items:start; padding:10px 0; border-bottom:1px solid var(--ramecek); }
  .veta.smazana .text { text-decoration: line-through; color:var(--slabe); }
  .veta.vystrizena .text { color:var(--slabe); font-style: italic; }
  .cas { color:var(--slabe); font-size:13px; padding-top:6px; }
  .id { color:var(--slabe); font-size:12px; }
  .text { font-size:17px; line-height:1.5; }
  .slovo { cursor:pointer; padding:0 1px; border-radius:3px; }
  .slovo:hover { background:var(--zvyrazneni); }
  .slovo.ven { text-decoration: line-through; color:var(--cervena); }
  .slovo.hraje { background:var(--zvyrazneni); }
  .nastroje { margin-top:6px; display:flex; gap:6px; flex-wrap:wrap; }
  .nastroje button { font-size:13px; padding:4px 8px; }
  .pozn { font-size:13px; color:var(--oranzova); margin-top:4px; }
  .upravit { width:100%; font: inherit; font-size:17px; padding:6px; border:1px solid var(--ramecek); border-radius:6px; }
  footer { position: fixed; bottom:0; left:0; right:0; background:#fff; border-top:1px solid var(--ramecek); padding:12px 16px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .stav { font-size:15px; }
  .stav.ok { color:var(--zelena); font-weight:600; }
  .stav.chyba { color:var(--cervena); }
  h2 { font-size:15px; color:var(--slabe); margin:18px 0 6px; font-weight:600; }
  .napoveda { font-size:13px; color:var(--slabe); margin:4px 0 10px; }
</style>
</head>
<body>
<header>
  <div class="radek">
    <video id="video" controls preload="metadata" src="__VIDEO__"></video>
    <div>
      <h1>__NAZEV__</h1>
      <div class="delka" id="delka"></div>
      <div class="pocitadlo" id="pocitadlo"></div>
      <div class="napoveda">Klikni na ▶ u věty a přehraje se od ní. Klikni na slovo a vystřihne se (znovu kliknout = vrátit).<br>
      Smazaná věta se z videa vystřihne. Když v textu slovo smažeš, vystřihne se taky. Když ho přepíšeš, změní se jen titulek. Poznámka je vzkaz pro mě.</div>
    </div>
  </div>
</header>
<main>
  <div id="vety"></div>
  <h2 id="nadpis-vystrizene" style="display:none">Věty vystřižené dřív (jdou vrátit)</h2>
  <div id="vystrizene"></div>
</main>
<footer>
  <button class="hlavni" id="ulozit">Odeslat úpravy</button>
  <button id="stahnout">Stáhnout soubor úprav</button>
  <span class="stav" id="stav"></span>
</footer>
<script>
const DATA = __DATA__;
const stav = { smazane: new Set(), vracene: new Set(), ven: {}, texty: {}, poznamky: {} };
for (const v of DATA.vety) { stav.ven[v.id] = new Set(v.slova.filter(s => s.vynechano).map(s => s.i)); }
const video = document.getElementById('video');

function fmt(s) { s = Math.max(0, s); const m = Math.floor(s / 60); return m + ':' + (s - m * 60).toFixed(1).padStart(4, '0'); }

function delkaCelkem() {
  let d = 0;
  for (const v of DATA.vety) {
    if (stav.smazane.has(v.id)) continue;
    for (const s of v.slova) { if (!stav.ven[v.id].has(s.i)) d += (s.do - s.od); }
    d += 0.25;
  }
  for (const v of DATA.vystrizene) { if (stav.vracene.has(v.id)) d += v.delka; }
  return d;
}

function ukazDelku() {
  const d = delkaCelkem();
  const el = document.getElementById('delka');
  el.className = 'delka' + (d > DATA.nejvic_s ? ' pres-max' : (d > DATA.cil_s ? ' pres-cil' : ''));
  let t = 'Délka asi ' + fmt(d) + ' (cíl ' + fmt(DATA.cil_s) + ', nejvíc ' + fmt(DATA.nejvic_s) + ')';
  if (d > DATA.nejvic_s) t += ' – nad limitem, vystřihni víc';
  else if (d > DATA.cil_s) t += ' – nad cílem';
  el.textContent = t;
  const zustava = DATA.vety.filter(v => !stav.smazane.has(v.id)).length + stav.vracene.size;
  const ven = stav.smazane.size + (DATA.vystrizene.length - stav.vracene.size);
  const slov = Object.values(stav.ven).reduce((s, x) => s + x.size, 0);
  const pozn = Object.values(stav.poznamky).filter(x => x && x.trim()).length;
  document.getElementById('pocitadlo').innerHTML = '<b>' + zustava + '</b> zůstává · <b>' + ven + '</b> vystřiženo · <b>' + slov + '</b> slov ven · <b>' + pozn + '</b> poznámek';
}

function vykresli() {
  const kont = document.getElementById('vety');
  kont.innerHTML = '';
  for (const v of DATA.vety) {
    const div = document.createElement('div');
    div.className = 'veta' + (stav.smazane.has(v.id) ? ' smazana' : '');
    div.dataset.id = v.id;
    const play = document.createElement('button'); play.textContent = '▶'; play.title = 'Přehrát od téhle věty';
    play.onclick = () => { video.currentTime = v.od; video.play(); };
    const cas = document.createElement('div'); cas.className = 'cas'; cas.innerHTML = fmt(v.od) + '<br><span class="id">' + v.id + '</span><br><span class="id">' + (v.delka || 0).toFixed(1) + ' s</span>';
    const text = document.createElement('div');
    const t = document.createElement('div'); t.className = 'text';
    if (stav.texty[v.id] !== undefined) {
      t.textContent = stav.texty[v.id];
    } else {
      v.slova.forEach((s, n) => {
        const sp = document.createElement('span'); sp.className = 'slovo' + (stav.ven[v.id].has(s.i) ? ' ven' : '');
        sp.textContent = s.w; sp.dataset.od = s.od; sp.dataset.do = s.do;
        sp.onclick = () => { if (stav.ven[v.id].has(s.i)) stav.ven[v.id].delete(s.i); else stav.ven[v.id].add(s.i); vykresli(); };
        t.appendChild(sp); if (n < v.slova.length - 1) t.appendChild(document.createTextNode(' '));
      });
    }
    text.appendChild(t);
    const n = document.createElement('div'); n.className = 'nastroje';
    const smaz = document.createElement('button');
    smaz.textContent = stav.smazane.has(v.id) ? '↩ Vrátit větu' : '🗑 Smazat větu';
    smaz.onclick = () => { if (stav.smazane.has(v.id)) stav.smazane.delete(v.id); else stav.smazane.add(v.id); vykresli(); };
    n.appendChild(smaz);
    const uprav = document.createElement('button'); uprav.textContent = '✎ Upravit text';
    uprav.onclick = () => {
      const inp = document.createElement('input'); inp.className = 'upravit';
      inp.value = stav.texty[v.id] !== undefined ? stav.texty[v.id] : v.slova.map(s => s.w).join(' ');
      const hotovo = document.createElement('button'); hotovo.textContent = 'Hotovo';
      hotovo.onclick = () => {
        const nov = inp.value.trim().replace(/\s+/g, ' ');
        const norm = w => w.toLowerCase().replace(/^[„“”"'(\[]+|[„“”"')\].,;:!?…-]+$/g, '');
        const stara = v.slova.map(s => s.w), nova = nov ? nov.split(' ') : [];
        // jen smazaná slova (nic přidaného ani přepsaného): vystřihnout z videa, titulek se nemění
        let i = 0, ven = [];
        for (let j = 0; j < stara.length; j++) { if (i < nova.length && norm(nova[i]) === norm(stara[j])) i++; else ven.push(j); }
        if (nova.length && i === nova.length && ven.length) {
          delete stav.texty[v.id]; ven.forEach(j => stav.ven[v.id].add(j));
        } else if (nov === stara.join(' ')) delete stav.texty[v.id]; else stav.texty[v.id] = nov;
        vykresli();
      };
      text.innerHTML = ''; text.appendChild(inp); text.appendChild(hotovo); inp.focus();
    };
    n.appendChild(uprav);
    const pozn = document.createElement('button'); pozn.textContent = (stav.poznamky[v.id] ? '💬 Poznámka ✓' : '💬 Poznámka');
    pozn.title = 'Napiš mi k téhle větě, co s ní (třeba: tady dej hook, oprav slovo, zkrať)';
    pozn.onclick = () => {
      const ta = document.createElement('textarea'); ta.className = 'upravit'; ta.rows = 2; ta.placeholder = 'Co s touhle větou? (čtu to já, ne přepisovač)';
      ta.value = stav.poznamky[v.id] || '';
      const hotovo = document.createElement('button'); hotovo.textContent = 'Hotovo';
      hotovo.onclick = () => { const x = ta.value.trim(); if (x) stav.poznamky[v.id] = x; else delete stav.poznamky[v.id]; vykresli(); };
      text.appendChild(ta); text.appendChild(hotovo); ta.focus();
    };
    n.appendChild(pozn);
    text.appendChild(n);
    if (stav.poznamky[v.id]) {
      const p = document.createElement('div'); p.className = 'pozn'; p.textContent = '💬 ' + stav.poznamky[v.id];
      text.appendChild(p);
    }
    if (stav.texty[v.id] !== undefined) {
      const p = document.createElement('div'); p.className = 'pozn';
      const a = v.slova.map(s => s.w).join(' ').split(' ').length, b = stav.texty[v.id].split(' ').length;
      p.textContent = 'Text přepsaný: změní se jen titulek, zvuk zůstává (jiná slova ti nevyrobím).' + (a !== b ? ' Počet slov se liší od řeči (' + a + ' → ' + b + '), časování titulku bude přibližné.' : '') + ' Chceš slovo vystřihnout? Vrať text a klikni na slovo, nebo ho v textu jen smaž.';
      text.appendChild(p);
    }
    if (stav.ven[v.id].size) {
      const p = document.createElement('div'); p.className = 'pozn';
      p.textContent = 'Vystřihne se ' + stav.ven[v.id].size + ' slov' + (stav.ven[v.id].size === 1 ? 'o' : (stav.ven[v.id].size < 5 ? 'a' : '')) + ' uvnitř věty.';
      text.appendChild(p);
    }
    div.appendChild(play); div.appendChild(cas); div.appendChild(text);
    kont.appendChild(div);
  }
  const vk = document.getElementById('vystrizene'); vk.innerHTML = '';
  document.getElementById('nadpis-vystrizene').style.display = DATA.vystrizene.length ? '' : 'none';
  for (const v of DATA.vystrizene) {
    const div = document.createElement('div'); div.className = 'veta' + (stav.vracene.has(v.id) ? '' : ' vystrizena');
    const b = document.createElement('button'); b.textContent = stav.vracene.has(v.id) ? '🗑' : '↩'; b.title = 'Vrátit do videa';
    b.onclick = () => { if (stav.vracene.has(v.id)) stav.vracene.delete(v.id); else stav.vracene.add(v.id); vykresli(); };
    const cas = document.createElement('div'); cas.className = 'cas'; cas.innerHTML = fmt(v.delka) + '<br><span class="id">' + v.id + '</span>';
    const t = document.createElement('div'); t.className = 'text'; t.textContent = v.text + (stav.vracene.has(v.id) ? '  (vrátí se)' : '');
    div.appendChild(b); div.appendChild(cas); div.appendChild(t); vk.appendChild(div);
  }
  ukazDelku();
}

function upravy() {
  const ven = {}, vracena = {};
  for (const v of DATA.vety) {
    const puv = new Set(v.slova.filter(s => s.vynechano).map(s => s.i));
    const ted = stav.ven[v.id];
    const nove = [...ted].filter(i => !puv.has(i)).sort((a, b) => a - b);
    const zpet = [...puv].filter(i => !ted.has(i)).sort((a, b) => a - b);
    if (nove.length) ven[v.id] = nove;
    if (zpet.length) vracena[v.id] = zpet;
  }
  return { verze: 1, kdy: new Date().toISOString(), delka_odhad_s: Math.round(delkaCelkem() * 10) / 10,
           smazane_vety: [...stav.smazane], vracene_vety: [...stav.vracene], smazana_slova: ven, vracena_slova: vracena, texty: stav.texty,
           poznamky: stav.poznamky };
}

document.getElementById('ulozit').onclick = async () => {
  const el = document.getElementById('stav');
  el.className = 'stav'; el.textContent = 'Ukládám…';
  try {
    const r = await fetch('/uloz', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(upravy()) });
    if (!r.ok) throw new Error('server ' + r.status);
    el.className = 'stav ok'; el.textContent = '✅ Odesláno. Zavři tohle okno, studio pokračuje.';
  } catch (e) {
    el.className = 'stav chyba'; el.textContent = 'Uložení přes server nešlo (' + e.message + '). Použij Stáhnout soubor úprav a soubor dej do složky PRACOVNI.';
  }
};
document.getElementById('stahnout').onclick = () => {
  const a = document.createElement('a');
  a.href = 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(upravy(), null, 1));
  a.download = 'upravy.json'; a.click();
};
video.addEventListener('timeupdate', () => {
  const t = video.currentTime;
  document.querySelectorAll('.slovo').forEach(s => { s.classList.toggle('hraje', t >= +s.dataset.od && t < +s.dataset.do); });
});
vykresli();
</script>
</body>
</html>
"""


def data_editoru(osa, klipy_vety, nazev, cil_s, nejvic_s):
    """Z časové osy a přepisů složí data pro stránku: věty v pořadí videa, slova s časy ve videu, věty vystřižené dřív."""
    index = {}
    for c, vety in enumerate(klipy_vety):
        for v in vety:
            index[v["id"]] = (c, v)
    podle_vety = {}
    for w in osa["slova"]:
        podle_vety.setdefault(w["veta"], []).append(w)
    poradi = []
    for u in osa["useky"]:
        for vid in u["vety"]:
            if vid not in poradi:
                poradi.append(vid)
    vynechat = {k: set(v) for k, v in osa.get("vynechat", {}).items()}
    vety_out = []
    for vid in poradi:
        c, v = index[vid]
        zni = podle_vety.get(vid, [])
        slova, n = [], 0
        for i, s in enumerate(v["slova"]):
            if i in vynechat.get(vid, set()):
                od = zni[n - 1]["end"] if n > 0 and zni else (zni[0]["start"] if zni else 0)
                slova.append({"i": i, "w": s["w"], "od": od, "do": od, "vynechano": True})
            else:
                z = zni[n] if n < len(zni) else {"start": 0, "end": 0}
                slova.append({"i": i, "w": s["w"], "od": z["start"], "do": z["end"], "vynechano": False})
                n += 1
        vety_out.append({"id": vid, "klip": c, "od": zni[0]["start"] if zni else 0, "do": zni[-1]["end"] if zni else 0,
                         "delka": round((zni[-1]["end"] - zni[0]["start"]) if zni else 0, 1), "text": v["text"], "slova": slova})
    vystrizene = [{"id": v["id"], "klip": c, "text": v["text"], "delka": round(v["end"] - v["start"], 2)}
                  for c, vety in enumerate(klipy_vety) for v in vety if v["id"] not in podle_vety]
    return {"nazev": nazev, "cil_s": cil_s, "nejvic_s": nejvic_s, "delka_s": osa["delka"], "vety": vety_out,
            "vystrizene": vystrizene}


def stranka(data, video_src):
    return (STRANKA.replace("__NAZEV__", data["nazev"].replace("<", "&lt;")).replace("__VIDEO__", video_src)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))


def zkontroluj_upravy(u):
    """Ověří tvar úprav z prohlížeče. Vrátí očištěný slovník, nebo vyhodí ValueError."""
    if not isinstance(u, dict):
        raise ValueError("úpravy nejsou slovník")
    out = {"verze": 1, "kdy": str(u.get("kdy", "")), "delka_odhad_s": float(u.get("delka_odhad_s", 0) or 0)}
    for k in ("smazane_vety", "vracene_vety"):
        seznam = u.get(k, [])
        if not isinstance(seznam, list) or not all(isinstance(x, str) for x in seznam):
            raise ValueError("%s musí být seznam id vět" % k)
        out[k] = seznam
    for k in ("smazana_slova", "vracena_slova"):
        d = u.get(k, {})
        if not isinstance(d, dict) or not all(isinstance(v, list) and all(isinstance(i, int) for i in v) for v in d.values()):
            raise ValueError("%s musí být {id věty: [pořadí slov]}" % k)
        out[k] = {str(a): sorted(set(b)) for a, b in d.items()}
    t = u.get("texty", {})
    if not isinstance(t, dict) or not all(isinstance(v, str) for v in t.values()):
        raise ValueError("texty musí být {id věty: text}")
    out["texty"] = {str(a): b for a, b in t.items()}
    pz = u.get("poznamky", {})
    if not isinstance(pz, dict) or not all(isinstance(v, str) for v in pz.values()):
        raise ValueError("poznámky musí být {id věty: text}")
    out["poznamky"] = {str(a): b.strip() for a, b in pz.items() if b.strip()}
    return out


def shrnuti_uprav(u):
    """Jedna česká věta o úpravách (tohle čte Claude místo souboru)."""
    n_slov = sum(len(v) for v in u.get("smazana_slova", {}).values())
    casti = ["smazané věty %d" % len(u.get("smazane_vety", [])), "vrácené věty %d" % len(u.get("vracene_vety", [])),
             "vystřižená slova %d" % n_slov, "upravené texty %d" % len(u.get("texty", {}))]
    s = ", ".join(casti) + "."
    if u.get("delka_odhad_s"):
        s += " Odhad délky %.1f s." % u["delka_odhad_s"]
    if u.get("poznamky"):
        s += " Poznámky: " + " ".join("%s: „%s“" % (k, v) for k, v in u["poznamky"].items())
    return s


class _Handler(BaseHTTPRequestHandler):
    server_version = "ReelStudioEditor/1"

    def log_message(self, fmt, *args):
        pass

    def _posli(self, kod, telo, typ="application/json; charset=utf-8", hlavicky=None):
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (hlavicky or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(telo)

    def do_GET(self):
        s = self.server
        if self.path in ("/", "/editor.html"):
            self._posli(200, s.html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/stav":
            self._posli(200, json.dumps({"ulozeno": s.ulozeno is not None}).encode("utf-8"))
        elif self.path == "/video" and s.video:
            self._video()
        else:
            self._posli(404, b'{"chyba":"neni"}')

    def _video(self):
        cesta = Path(self.server.video)
        velikost = cesta.stat().st_size
        od, do = 0, velikost - 1
        rozsah = self.headers.get("Range")
        if rozsah and rozsah.startswith("bytes="):
            a, _, b = rozsah[6:].partition("-")
            od = int(a) if a else max(0, velikost - int(b))
            do = int(b) if (b and a) else velikost - 1
            do = min(do, velikost - 1)
            if od > do:
                self._posli(416, b"", "text/plain", {"Content-Range": "bytes */%d" % velikost})
                return
        delka = do - od + 1
        self.send_response(206 if rozsah else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(delka))
        if rozsah:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (od, do, velikost))
        self.end_headers()
        try:
            with open(str(cesta), "rb") as f:
                f.seek(od)
                zbyva = delka
                while zbyva > 0:
                    blok = f.read(min(1024 * 256, zbyva))
                    if not blok:
                        break
                    self.wfile.write(blok)
                    zbyva -= len(blok)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        s = self.server
        delka = int(self.headers.get("Content-Length", 0) or 0)
        telo = self.rfile.read(delka) if delka else b""
        if self.path == "/uloz":
            try:
                u = zkontroluj_upravy(json.loads(telo.decode("utf-8")))
            except (ValueError, UnicodeDecodeError) as e:
                self._posli(400, json.dumps({"chyba": str(e)}, ensure_ascii=False).encode("utf-8"))
                return
            uloz_upravy(s.soubor_uprav, u)
            s.ulozeno = u
            self._posli(200, b'{"ok":true}')
        elif self.path == "/konec":
            s.konec = True
            self._posli(200, b'{"ok":true}')
        else:
            self._posli(404, b'{"chyba":"neni"}')


def uloz_upravy(soubor, u):
    """Zapíše upravy.json bezpečně (nejdřív do dočasného souboru, pak přejmenování). Starší verze zůstane jako upravy-<čas>.json."""
    soubor = Path(soubor)
    soubor.parent.mkdir(parents=True, exist_ok=True)
    if soubor.exists():
        zaloha = soubor.with_name("upravy-%d.json" % int(time.time()))
        if not zaloha.exists():
            os.replace(str(soubor), str(zaloha))
    tmp = soubor.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(u, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(soubor))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, html, video, soubor_uprav, port=0):
        super().__init__(("127.0.0.1", port), _Handler)
        self.html, self.video, self.soubor_uprav = html, str(video) if video else None, soubor_uprav
        self.ulozeno, self.konec = None, False

    @property
    def adresa(self):
        return "http://127.0.0.1:%d/" % self.server_address[1]


def spust(html, video, soubor_uprav, otevrit=True, cekat_s=1800, port=0, po_startu=None):
    """Spustí server, otevře prohlížeč a čeká na uložení (nebo na vypršení času). Vrátí uložené úpravy, nebo None."""
    server = Server(html, video, soubor_uprav, port)
    vlakno = threading.Thread(target=server.serve_forever, daemon=True)
    vlakno.start()
    try:
        if po_startu:
            po_startu(server.adresa)
        if otevrit:
            webbrowser.open(server.adresa)
        konec = time.time() + cekat_s
        while time.time() < konec and server.ulozeno is None and not server.konec:
            time.sleep(0.3)
        return server.ulozeno
    finally:
        server.shutdown()
        server.server_close()
