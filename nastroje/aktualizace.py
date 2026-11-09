"""Zapne automatické aktualizace pluginu studia u zákaznice. Jen standardní knihovna, Python 3.9.

Claude Code u pluginů od jiných autorů aktualizace samo nezapíná. Podle dokumentace (code.claude.com,
plugins/loading, ověřeno 9. 11. 2026) rozhoduje nejdřív `autoUpdate` u marketplace v `extraKnownMarketplaces`
v souboru nastavení. Tenhle krok ho zapíše do ~/.claude/settings.json (zdroj vezme z known_marketplaces.json,
kam ho zapsala instalace pluginu). Před změnou udělá zálohu settings.json.zaloha-studio. Nic jiného nemění.
Zda Claude Code `autoUpdate` v uživatelském nastavení opravdu použije: NEOVĚŘENO, zkouší se s GitHubem.

Spuštění: python3 aktualizace.py [--marketplace digitalni-mama-marcela]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

MARKETPLACE = "digitalni-mama-marcela"


def zdroj_z_known(known, nazev):
    """Zdroj marketplace ve tvaru pro settings.json, nebo None."""
    zaznam = known.get(nazev)
    if not isinstance(zaznam, dict) or not isinstance(zaznam.get("source"), dict):
        return None
    return dict(zaznam["source"])


def zapni(settings, nazev, zdroj):
    """Vrátí nové nastavení s autoUpdate u marketplace. Ostatní klíče nechá, jak jsou."""
    nove = dict(settings)
    trhy = dict(nove.get("extraKnownMarketplaces") or {})
    zaznam = dict(trhy.get(nazev) or {})
    if "source" not in zaznam:
        zaznam["source"] = zdroj
    zaznam["autoUpdate"] = True
    trhy[nazev] = zaznam
    nove["extraKnownMarketplaces"] = trhy
    return nove


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketplace", default=MARKETPLACE)
    ap.add_argument("--domov", default=str(Path.home()), help="jen pro zkoušky")
    a = ap.parse_args(argv)
    claude = Path(a.domov) / ".claude"
    known_soubor = claude / "plugins" / "known_marketplaces.json"
    settings_soubor = claude / "settings.json"
    try:
        known = json.loads(known_soubor.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("🔴 Nenašla jsem seznam nainstalovaných pluginů. Udělej: nejdřív nainstaluj plugin studia.")
        return 1
    zdroj = zdroj_z_known(known, a.marketplace)
    if zdroj is None:
        print("🔴 Plugin studia (%s) v Claude Code není. Udělej: nejdřív nainstaluj plugin studia." % a.marketplace)
        return 1
    settings = {}
    if settings_soubor.exists():
        try:
            settings = json.loads(settings_soubor.read_text(encoding="utf-8"))
        except ValueError:
            print("🔴 Soubor nastavení Claude Code nejde přečíst, nic neměním. Udělej: napiš Marcele.")
            return 1
        shutil.copy2(settings_soubor, settings_soubor.with_name("settings.json.zaloha-studio"))
    if (settings.get("extraKnownMarketplaces") or {}).get(a.marketplace, {}).get("autoUpdate") is True:
        print("✅ Automatické aktualizace studia už jsou zapnuté.")
        return 0
    claude.mkdir(parents=True, exist_ok=True)
    settings_soubor.write_text(json.dumps(zapni(settings, a.marketplace, zdroj), ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print("✅ Automatické aktualizace studia jsou zapnuté. Nová verze se stáhne sama, projeví se v příští konverzaci.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
