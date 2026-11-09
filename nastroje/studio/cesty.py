"""Kde je složka balíčku (NASTAVENI, pisma). Funguje ve stavbě (jadro/studio -> ../balicek) i v pluginu (nastroje/studio -> ..)."""
from pathlib import Path


def koren_balicku():
    zde = Path(__file__).resolve().parents[1]          # jadro (stavba) nebo nastroje (plugin)
    for k in (zde.parent / "balicek", zde.parent):
        if (k / "NASTAVENI").is_dir() and (k / "pisma").is_dir():
            return k
    return zde.parent / "balicek"


BALICEK = koren_balicku()
PISMA = BALICEK / "pisma"
