"""Poloha osoby v záběru. Měří místní program (OpenCV, Haar), Claude se na snímky nedívá.

Používá se na to, aby text nikdy nezakryl obličej. Výsledek je v pixelech hotového reelu 1080x1920.
Kaskáda hledá obličej zepředu. Když ho v části záběrů nenajde (otočená hlava, ruka přes obličej),
bere se poslední známá poloha a výsledek se označí jako méně jistý.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

SIRKA, VYSKA = 1080, 1920


def rozmer_klipu(klip):
    """Rozměr po otočení (telefon ukládá otočení zvlášť). Vrátí (šířka, výška, délka v s)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation:format=duration", "-of", "json", str(klip)],
                         check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    rot = 0
    for sd in s.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return w, h, float(d["format"]["duration"])


def snimky_sedive(klip, fps=2.0, sirka=480):
    """Vrátí (pole snímků v odstínech šedi, šířka, výška). ffmpeg otáčí podle metadat sám."""
    w, h, _ = rozmer_klipu(klip)
    vyska = int(round(sirka * h / w / 2)) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(klip), "-vf", "fps=%s,scale=%d:%d" % (fps, sirka, vyska),
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
    pole = np.frombuffer(raw, dtype=np.uint8).reshape(-1, vyska, sirka)
    return pole, sirka, vyska


def zmer_polohu(klip, fps=2.0):
    """Najde obličej v řídce vybraných snímcích. Souřadnice jsou přepočtené na 1080x1920."""
    import cv2

    kaskada = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    snimky, sirka, vyska = snimky_sedive(klip, fps)
    mierka = SIRKA / sirka
    vzorky = []
    for i, s in enumerate(snimky):
        n = kaskada.detectMultiScale(s, scaleFactor=1.1, minNeighbors=6, minSize=(int(sirka * 0.12),) * 2)
        if len(n):
            x, y, w, h = max(n, key=lambda b: b[2] * b[3])
            vzorky.append({"t": round(i / fps, 2), "x": int(x * mierka), "y": int(y * mierka),
                           "w": int(w * mierka), "h": int(h * mierka)})
    vse = len(snimky)
    shrnuti = {"snimku": vse, "nalezeno": len(vzorky), "podil": round(len(vzorky) / vse, 2) if vse else 0}
    if vzorky:
        shrnuti.update({"horni_okraj": min(v["y"] for v in vzorky),
                        "dolni_okraj": max(v["y"] + v["h"] for v in vzorky),
                        "levy_okraj": min(v["x"] for v in vzorky),
                        "pravy_okraj": max(v["x"] + v["w"] for v in vzorky),
                        "median_y": int(np.median([v["y"] for v in vzorky])),
                        "median_vyska": int(np.median([v["h"] for v in vzorky]))})
    return shrnuti, vzorky


def pevne(vzorky):
    """Vyřadí zjevné omyly detekce (obličej mimo, jiná velikost než obvykle)."""
    if len(vzorky) < 5:
        return list(vzorky)
    my = float(np.median([v["y"] for v in vzorky]))
    mh = float(np.median([v["h"] for v in vzorky]))
    mx = float(np.median([v["x"] for v in vzorky]))
    return [v for v in vzorky if abs(v["y"] - my) <= 0.9 * mh and 0.65 * mh <= v["h"] <= 1.5 * mh
            and abs(v["x"] - mx) <= 1.2 * mh]


def rozsireny(v):
    """Obdélník, který text nesmí zakrýt: obličej s vlasy nad čelem a bradou s krkem."""
    return (v["x"] - 0.20 * v["w"], v["y"] - 0.45 * v["h"], v["x"] + 1.20 * v["w"], v["y"] + 1.25 * v["h"])


def obliceje_ve_vystupu(osa, vzorky_klipu):
    """Obličeje v čase hotového reelu: seznam (čas, obdélník). Střih posune čas, zoom změní velikost a polohu."""
    from .zoom import transformuj

    casti = osa.get("casti") or [{"klip": u["klip"], "od": u["od"], "delka": u["delka"], "vystup_od": u["vystup_od"],
                                  "zoom": 1.0, "posun_x": 0.0, "posun_y": 0.0} for u in osa["useky"]]
    out = []
    for c in casti:
        for v in vzorky_klipu[c["klip"]]:
            if c["od"] - 0.25 <= v["t"] <= c["od"] + c["delka"] + 0.25:
                out.append((c["vystup_od"] + v["t"] - c["od"], transformuj(rozsireny(v), c)))
    return out


def sjednoceni(obliceje, t0, t1, rezerva=0.6):
    """Obdélník, který pokryje obličej ve všech vzorcích v okně <t0, t1>. Bez vzorků v okně bere vzorky do 1,5 s
    kolem okna (měří se 2x za sekundu, krátké slovo u střihu jinak žádný vzorek nemá, 29. 10. 2026), pak celý reel."""
    vyber = ([b for t, b in obliceje if t0 - rezerva <= t <= t1 + rezerva]
             or [b for t, b in obliceje if t0 - 1.5 <= t <= t1 + 1.5] or [b for _, b in obliceje])
    if not vyber:
        return None
    return (min(b[0] for b in vyber), min(b[1] for b in vyber), max(b[2] for b in vyber), max(b[3] for b in vyber))


def protina(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


if __name__ == "__main__":
    import sys

    for k in sys.argv[1:]:
        s, _ = zmer_polohu(k)
        print(Path(k).name, json.dumps(s, ensure_ascii=False))
