"""Pomocník pro zkoušení prvků na umělém videu (barevné pruhy a tón), bez záběrů zákaznice.
Použití ze složky jadro: ../.venv/bin/python -c "from studio.prvky import _ukazka; _ukazka.ukaz([{...spec...}], 'marcela', 'vystup.mp4')"
Vrátí cestu k MP4 a uloží snímky v časech do složky vedle (pro kontrolu okem)."""
import subprocess
from pathlib import Path


def umele_video(cil, delka=8):
    cil = Path(cil)
    if not cil.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=%d" % delka,
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=%d" % delka, "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cil)], check=True)
    return cil


def ukaz(prvky_spec, styl_nazev, vystup, delka=8, casy=(1.0, 3.0, 5.0, 7.0), podklady=None):
    from .. import render, titulky, umisteni
    from . import priprav_vsechny

    vystup = Path(vystup)
    vystup.parent.mkdir(parents=True, exist_ok=True)
    video = umele_video(vystup.parent / "umele-video.mp4", delka)
    osa = {"verze": 1, "fps": 30, "sirka": 1080, "vyska": 1920, "klipy": [str(video)],
           "useky": [{"klip": 0, "od": 0.0, "do": float(delka), "vystup_od": 0.0, "delka": float(delka), "vety": ["v1"],
                      "jisty_vstup": True, "jisty_vystup": True}],
           "slova": [{"w": "zkouška", "start": 0.5, "end": 1.0, "veta": "v1"}, {"w": "prvku", "start": 1.0, "end": 1.5, "veta": "v1"}],
           "delka": float(delka), "vynechat": {}, "hook": None, "mini": [], "vsuvky": [], "prvky": prvky_spec}
    styl = titulky.STYLY[styl_nazev]
    priprav_vsechny(osa, styl, [], podklady)
    kreslic = titulky.Kreslic(osa, styl_nazev)
    problemy, kontrol = umisteni.kontrola(osa, kreslic, [])
    render.vyrenderuj(osa, styl_nazev, vystup, vystup.parent / "prac", preset="ultrafast")
    snimky = vystup.parent / "snimky"
    snimky.mkdir(exist_ok=True)
    for c in casy:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % c, "-i", str(vystup), "-frames:v", "1", "-vf", "scale=360:-2",
                        str(snimky / ("%05.2fs.jpg" % c))], check=True)
    return vystup, problemy, snimky
