"""Krok přepis: z videa udělá přepis s časy slov. Běží celý na počítači, nic se neodesílá.

Zvuk vytáhne náš ffmpeg a přepisovači se předá jako pole vzorků. Vestavěné dekódování
faster-whisper 1.2.1 padá s PyAV 19 (OVĚŘENO 14. 10. 2026), proto se nepoužívá.

Výstup do složky PRACOVNI:
  prepis.json        věty a slova s časy (čte kód)
  prepis-vety.txt    věty s číslem a časem (čte Claude, šetří limity)
"""
import json
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

try:
    import resource          # jen Mac a Linux; Windows ho nemá (měření paměti tam vynecháme)
except ImportError:
    resource = None

VYCHOZI_MODEL = "turbo"  # large-v3 je kvalitnější na jména, ale asi 3x pomalejší (T1, 14. 10. 2026)


def vytahni_zvuk(klip, wav):
    """Zvuk 16 kHz mono do souboru wav. Vrátí délku v sekundách."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(klip), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def nacti_zvuk(wav):
    with wave.open(str(wav), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def prepis_klipu(klip, vystup, model_nazev=VYCHOZI_MODEL, predpona="v", jazyk="cs"):
    """Přepíše klip. Číslo věty je predpona + pořadí (například k1-v03)."""
    from faster_whisper import WhisperModel

    vystup = Path(vystup)
    vystup.mkdir(parents=True, exist_ok=True)
    wav = vystup / "zvuk16k.wav"
    delka = vytahni_zvuk(klip, wav)
    zvuk = nacti_zvuk(wav)

    t = time.time()
    model = WhisperModel(model_nazev, device="cpu", compute_type="int8")
    cas_nacteni = time.time() - t
    t = time.time()
    segmenty, info = model.transcribe(zvuk, language=jazyk, word_timestamps=True, vad_filter=True,
                                      condition_on_previous_text=False, beam_size=5)
    vety = []
    for i, s in enumerate(segmenty, 1):
        slova = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)}
                 for w in (s.words or [])]
        if not slova:
            continue
        vety.append({"id": "%s%02d" % (predpona, i), "start": round(slova[0]["start"], 3),
                     "end": round(slova[-1]["end"], 3), "text": s.text.strip(), "slova": slova})
    cas_prepis = time.time() - t

    metriky = {"klip": Path(klip).name, "model": model_nazev, "delka_s": round(delka, 1),
               "cas_nacteni_modelu_s": round(cas_nacteni, 1), "cas_prepisu_s": round(cas_prepis, 1),
               "nasobek_realneho_casu": round(cas_prepis / delka, 3) if delka else None,
               "pocet_vet": len(vety), "pocet_slov": sum(len(v["slova"]) for v in vety),
               "nejvyssi_pamet_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2) if resource else None,
               "jazyk": info.language, "jistota_jazyka": round(info.language_probability, 3)}
    (vystup / "prepis.json").write_text(json.dumps({"metriky": metriky, "vety": vety}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    uloz_vety(vety, vystup / "prepis-vety.txt")
    return metriky, vety


def cas_text(s):
    m, sec = divmod(s, 60)
    return "%d:%04.1f" % (m, sec)


def uloz_vety(vety, soubor, poznamky=None):
    """Věty po jedné na řádek: číslo, čas, text. Tohle čte Claude místo celého přepisu.
    poznamky: {id věty: text} = co u věty zkontrolovat sluchem (hlídané a nejisté slovo), vypíše se pod větu."""
    radky = []
    for v in vety:
        radky.append("%s [%s-%s] %s" % (v["id"], cas_text(v["start"]), cas_text(v["end"]), v["text"]))
        if poznamky and poznamky.get(v["id"]):
            radky.append("    ⚠️ %s" % poznamky[v["id"]])
    Path(soubor).write_text("\n".join(radky) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Přepis videa (lokálně)")
    p.add_argument("klip")
    p.add_argument("--vystup", required=True)
    p.add_argument("--model", default=VYCHOZI_MODEL)
    p.add_argument("--predpona", default="v")
    a = p.parse_args()
    metriky, _ = prepis_klipu(a.klip, a.vystup, a.model, a.predpona)
    print(json.dumps(metriky, ensure_ascii=False))
    sys.exit(0)
