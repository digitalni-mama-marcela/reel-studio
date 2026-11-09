"""Otisk vstupů hotového videa (Marcela 29. 10. 2026): poznat, jestli náhled obsahuje poslední změny.

Nespoléhá na čas změny souboru. Při vytvoření videa se spočítá otisk (SHA-256) všeho, z čeho video vzniká,
a uloží se k němu (PRACOVNI/<nahled|reel>-N/otisk.json). Stránka Plán reelu spočítá otisk teď a porovná po částech:
přepis a střih, plán scén, vzhled, podklady (obsah použitých obrázků). Zvlášť hlásí úpravy z editoru, které ještě
nejsou ve střihu (PRACOVNI/upravy.json). Jen standardní knihovna.
"""
import hashlib
import json
from pathlib import Path

from . import projekt

CASTI = {"strih": "přepis a střih", "plan": "scény", "vzhled": "vzhled", "podklady": "nahrané podklady"}
# klíče řádku plánu, které render nečte (značky, popisky, časy pro tabulku)
PLAN_BEZ = {"text", "text_vety", "text_drive", "od", "do", "duvod", "zdroj", "typ", "rucne", "odmitnuto", "navrh", "odmitnuty_navrh", "zkontrolovat"}
OBRAZKY = (".png", ".jpg", ".jpeg", ".webp")


def _h(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _soubor(p):
    p = Path(p)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for kus in iter(lambda: f.read(1 << 20), b""):
            h.update(kus)
    return h.hexdigest()[:16]


def _json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def soubory_planu(plan, podklady):
    """Cesty k obrázkům, na které plán odkazuje (obsah řádků: „soubor | štítek“, „a.jpg / b.jpg“, „*“)."""
    podklady = Path(podklady) if podklady else None
    out = set()
    for rad in (plan or {}).get("radky", []):
        obsah = str(rad.get("obsah") or "")
        if obsah.strip() == "*" and podklady and podklady.is_dir():
            out |= {p for p in podklady.iterdir() if p.suffix.lower() in OBRAZKY}
            continue
        for kus in obsah.replace("|", "\n").replace(" / ", "\n").splitlines():
            kus = kus.strip()
            if not kus.lower().endswith(OBRAZKY):
                continue
            p = Path(kus)
            if not p.is_absolute() and podklady:
                p = podklady / kus
            out.add(p)
    return sorted(out)


def spocitej(reel, plan=True, vzhled=True):
    """Otisk po částech pro aktuální stav reelu. Náhled střihu: plan=False, vzhled=False. Vzhled bez plánu: plan=False."""
    s = projekt.slozky(reel)
    prac = s["pracovni"]
    strih = {"vyber": _json(prac / "vyber.json"), "navrh": _json(prac / "navrh-strihu.json"),
             "prepisy": {p.parent.name: _soubor(p) for p in sorted(prac.glob("klip-*/prepis.json"))},
             "opravy": projekt.seznam_oprav(reel)}
    out = {"strih": _h(strih)}
    if vzhled:
        out["vzhled"] = _h({"vzhled": _json(prac / "vzhled.json"), "stale": projekt.vzhled_upravy(reel)})
    if plan:
        p = _json(prac / "plan-strihu.json") or {}
        radky = [{k: v for k, v in r.items() if k not in PLAN_BEZ} for r in p.get("radky", [])]
        out["plan"] = _h({"radky": radky, "filtr_od_vety": p.get("filtr_od_vety")})
        out["podklady"] = _h({str(x): _soubor(x) for x in soubory_planu(p, p.get("podklady") or s["podklady"])})
    return out


def uloz(otisk, slozka_renderu):
    Path(slozka_renderu).mkdir(parents=True, exist_ok=True)
    (Path(slozka_renderu) / "otisk.json").write_text(json.dumps(otisk, ensure_ascii=False, indent=1), encoding="utf-8")


def porovnej(reel, video):
    """Stav náhledu pro stránku: {"stav": "aktualni" | "zastaraly" | "nevim" | "zadne", "zmeny": [...], "cekaji_upravy": bool}."""
    s = projekt.slozky(reel)
    cekaji = (s["pracovni"] / "upravy.json").exists()
    if not video:
        return {"stav": "zadne", "zmeny": [], "cekaji_upravy": cekaji}
    ulozeny = _json(s["pracovni"] / Path(video).stem / "otisk.json")
    if not ulozeny:
        return {"stav": "nevim", "zmeny": [], "cekaji_upravy": cekaji}
    ted = spocitej(reel, plan="plan" in ulozeny, vzhled="vzhled" in ulozeny)
    zmeny = [CASTI[k] for k in CASTI if k in ulozeny and ulozeny[k] != ted.get(k)]
    return {"stav": "zastaraly" if zmeny or cekaji else "aktualni", "zmeny": zmeny, "cekaji_upravy": cekaji}
