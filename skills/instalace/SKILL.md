---
name: instalace
description: Jednorázová příprava počítače pro Claude Reel Studio (složka Reely mimo iCloud a OneDrive, ffmpeg, uv, Python a knihovny, model přepisu). Použij při prvním spuštění, při „nainstaluj studio“, „připrav mi to“ nebo když spouštěč hlásí, že má běžet instalace.
---

# Instalace studia (jen jednou)

Zákaznice nikdy neotevřela terminál. Mluv s ní česky, tykej, krátké věty. Ptej se po jedné otázce a nabídni
volby. Před každým krokem, který může chtít heslo nebo potvrzení v počítači, jí to řekni předem.
NÁVRH (16. 10. 2026): zkouší se na čistém Macu a na Windows v týdnu od 20. 10., kroky se podle toho upřesní.

## 1. Kontrola počítače (nic neinstaluje)
```
python3 "${CLAUDE_PLUGIN_ROOT}/nastroje/studio/kontrola_pocitace.py" --slozka "<Reely>"
```
Běží na jakémkoli Pythonu 3.9 a novějším. Na Windows použij `python` místo `python3`, když `python3` není.
Výstup je česky: ✅ nebo 🔴 u každé položky a u červené věta „Co dál“. Předej zákaznici jen červené položky.

## 2. Složka Reely
Zeptej se: „Kam mám dát složku Reely? Nabízím domovskou složku (doporučeno), nebo mi řekni jinou.“
Nikdy Plocha, Dokumenty, iCloud, OneDrive, Dropbox (kontrola počítače to pozná a řekne). Založ ji a zkopíruj
do ní výchozí nastavení: `<Reely>/NASTAVENI` z `${CLAUDE_PLUGIN_ROOT}/NASTAVENI`.

## 3. Nástroje, které plugin neumí nést
- **Mac:** Homebrew (když chybí, řekni předem: „Teď se tě počítač zeptá na heslo, to je v pořádku.“), pak
  `brew install ffmpeg uv`.
- **Windows:** `winget install Gyan.FFmpeg` a `winget install astral-sh.uv`. Git for Windows je potřeba pro
  plugin samotný. NEOVĚŘENO, zkouší se 20. 10.
Po instalaci spusť znovu kontrolu počítače. Pokračuj, až je ffmpeg i uv zelené.

## 4. Prostředí studia a model přepisu
```
python3 "${CLAUDE_PLUGIN_ROOT}/nastroje/start.py" priprava
```
Stáhne Python 3.12 a knihovny do složky aplikace (ne do Reely). Poprvé pár minut, řekni to předem.
Model přepisu se stáhne při prvním přepisu (asi 1,6 GB u modelu turbo), taky to řekni předem.
Model pro text za hlavou (selfie_segmenter.tflite, 250 kB, Apache 2.0) má být v `${CLAUDE_PLUGIN_ROOT}/modely/`;
když chybí, stáhni ho podle adresy v `modely/LICENCE-selfie_segmenter.txt` (NÁVRH, čeká na souhlas Marcely, bod 47).
Bez něj studio text kreslí před osobu a řekne to.

## 4b. Automatické aktualizace studia
Claude Code u pluginů od jiných autorů aktualizace samo nezapíná. Zapni je za zákaznici, ať jí nové styly,
písma a efekty chodí samy:
```
python3 "${CLAUDE_PLUGIN_ROOT}/nastroje/aktualizace.py"
```
Řekni jí jednou větou: „Automatické aktualizace jsou zapnuté, nové styly ti budou chodit samy.“
Když krok skončí 🔴, řekni jí větu za „Udělej:“.

## 5. Zkouška
Řekni: „Hotovo. Chceš to hned vyzkoušet na svém videu?“ a předej dovednosti `novy-reel`.

## 6. Chrome rozšíření Claude (volitelné, jen pro reely z Instagramu)
Když zákaznice pošle odkaz na cizí reel („udělej to podle tohohle“), nejdřív ho otevři vestavěným prohlížečem
aplikace Claude: veřejný reel jde bez přihlášení (OVĚŘENO 3. 11. 2026 na Macu Marcely; u cookies zvol „Odmítnout
volitelné“). Když Instagram chce přihlášení, nebo je reel soukromý, nabídni zálohu: rozšíření Claude pro Chrome
(odkaz dá Marcela v lekci; v obchodě Chrome má být vydavatel Anthropic) a přihlášení na Instagram v jejím Chromu.
Nikdy nechtěj heslo a nikdy se nepřihlašuj za ni. Třetí možnost: pošle snímky obrazovky reelu.
Claude Code jen v Terminálu bez aplikace vestavěný prohlížeč nemá (NEOVĚŘENO): tam rovnou rozšíření nebo snímky.
