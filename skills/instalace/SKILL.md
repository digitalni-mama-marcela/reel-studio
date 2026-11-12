---
name: instalace
description: Jednorázová příprava počítače pro Claude Reel Studio na Macu i Windows (složka Reely mimo iCloud a OneDrive, vlastní uv, Python, knihovny a ffmpeg studia, model přepisu). Použij při prvním spuštění, při „nainstaluj studio“, „připrav mi to“ nebo když spouštěč hlásí, že má běžet instalace.
---

# Instalace studia (jen jednou)

Zákaznice nikdy neotevřela terminál. Mluv s ní česky, tykej, krátké věty. Ptej se po jedné otázce a nabídni
volby. Odborná slova (Python, uv, ffmpeg) jí neříkej, řekni „nástroje pro střih“.

Zákaznice nic neinstaluje sama. Studio si všechno, co potřebuje, stáhne samo do své složky prostředí
(Mac: `~/Library/Application Support/ClaudeReelStudio`, Windows: `%LOCALAPPDATA%\ClaudeReelStudio`).
Nechce to heslo, práva správce, Homebrew ani winget a nic se neinstaluje do systému.

## 0. Který počítač (nejdřív, jednou)
Zjisti systém z prostředí Claude Code (platforma darwin = Mac, win32 = Windows). Podle toho celou dobu používej
jeden z těchto spouštěčů. Dál v dovednostech mu říkáme `STUDIO`:

- **Mac:**
  ```
  sh "${CLAUDE_PLUGIN_ROOT}/nastroje/spust.sh" <krok> ...
  ```
- **Windows:**
  ```
  powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/nastroje/spust.ps1" <krok> ...
  ```

Nikdy nespouštěj `python3`, `python` ani `py` napřímo. Na Macu bez vývojářských nástrojů Applu otevře `python3`
okno „nainstalovat nástroje pro vývojáře“, na Windows je `python3` jen odkaz do Microsoft Storu.

Pravidla pro příkazy, aby fungovaly v zsh na Macu i v Git Bash a PowerShellu na Windows:
- cesty celé, v dvojitých uvozovkách a s lomítky `/` (i na Windows: `"C:/Users/jana/Reely"`);
- jeden příkaz na jedno volání, bez `&&`, bez `cd`, bez `~` uvnitř uvozovek;
- když tvůj nástroj na Windows běží v PowerShellu (ne v Git Bash), napiš před cestu v uvozovkách `&`:
  `& powershell -NoProfile -ExecutionPolicy Bypass -File "…/spust.ps1" priprava`;
- v textu pro parametry (`--veta`, `--hook`, `--kod` …) nepoužívej rovné uvozovky `"`. Na Windows je PowerShell
  5.1 rozbije. Místo nich piš české „ “.

Spouštěč vypisuje anglické řádky `STATUS …` (ty jsou pro tebe) a pak české řádky ✅ nebo 🔴 (ty jsou pro
zákaznici). Řádek `STATUS … MISSING (…)` a na konci `NOT READY` znamená, že krok nejde dokončit. Důvod je
v závorce.

## 1. Kontrola počítače (stáhne jen uv a Python, asi 40 MB)
```
STUDIO kontrola --slozka "<Reely nebo domovská složka>"
```
Poprvé si spouštěč stáhne uv a Python 3.12 (asi 40 MB, asi minutu). Řekni to předem jednou větou:
„Teď si studio stáhne první nástroje, asi minutu.“
Výstup je česky: ✅, ℹ️ nebo 🔴 u každé položky a u červené věta „Co dál“. Předej zákaznici jen červené
položky. Že ffmpeg zatím chybí (ℹ️), je v pořádku, stáhne se v kroku 4.

## 2. Složka Reely
Zeptej se: „Kam mám dát složku Reely? Nabízím domovskou složku (doporučeno), nebo mi řekni jinou.“
Nikdy Plocha, Dokumenty, iCloud, OneDrive, Dropbox (kontrola počítače to pozná a řekne). Na Windows bývají
Plocha a Dokumenty v OneDrivu, takže tam vždycky domovská složka (`C:/Users/<jméno>/Reely`).
Založ ji a zkopíruj do ní výchozí nastavení: `<Reely>/NASTAVENI` z `${CLAUDE_PLUGIN_ROOT}/NASTAVENI`.

## 3. (dřív Homebrew a winget) Už není potřeba
Studio si nástroje pro střih stáhne samo v kroku 4. Nic neinstaluj přes Homebrew ani winget, ani když to
někde v počítači najdeš. Jediná výjimka je krok 4, když tam 🔴 výslovně řekne „Udělej: winget …“.

## 4. Prostředí studia a nástroje pro střih
```
STUDIO priprava
```
Stáhne do složky prostředí knihovny studia (asi 250 MB) a ffmpeg, program na práci s videem
(Mac asi 55 MB, Windows asi 115 MB). Pak vyzkouší, že všechno jde načíst. Poprvé to trvá pár minut podle
internetu, řekni to předem.
Pokračuj, až poslední řádek je „✅ Příprava prostředí: hotovo.“ Při 🔴 jí řekni větu za „Udělej:“, a když tam
není, spusť krok jednou znovu. Když skončí stejně, pošli Marcele celý výpis.
Hned po zelené přípravě pusť stahování modelu přepisu na pozadí, ať první střih nečeká:
```
STUDIO model --na-pozadi
```
Krok se vrátí hned a model (asi 1,6 GB) se stahuje sám dál, i když zákaznice pokračuje dalšími kroky.
Řekni jí jednou větou: „Na pozadí se teď stahuje nástroj na přepis řeči, asi 1,6 GB. Můžeme pokračovat.“
Ať do konce stahování nezavírá počítač víkem. Kdyby se stahování přerušilo, přepis si model dotáhne sám
(co už se stáhlo, zůstává). Jak je to daleko: `STUDIO model --stav`.
Model pro text za hlavou (selfie_segmenter.tflite, 250 kB, Apache 2.0) je v `${CLAUDE_PLUGIN_ROOT}/modely/`.
Na Macu s procesorem Intel ho studio použít neumí (knihovna pro něj neexistuje): text kreslí před osobu a řekne to.

Co dělat, když něco selže:
- **Windows, „Knihovny studia nejdou načíst“ a chyba s DLL:** chybí knihovna Microsoft Visual C++. Zákaznice
  vloží do PowerShellu řádek, který krok vypíše za „Udělej:“, pak Claude úplně zavře (i z oznamovací oblasti
  vedle hodin), znovu otevře a ty spustíš `STUDIO priprava` znovu.
- **Windows, „nejde spustit“ / antivirus / Smart App Control:** Windows zablokoval stažený program. Spusť krok
  jednou znovu. Když to skončí stejně, řekni jí, co Windows zablokoval (text v závorce), a pošli výpis Marcele.
- **„no internet“ nebo stahování se nedokončilo:** spouštěč to zkusí sám třikrát. Pak ať zkontroluje připojení
  a ty krok spusť znovu. Co už se stáhlo, zůstává.
- Program nainstalovaný za běhu Claude najde, až když Claude úplně zavře a znovu otevře.

## 4b. Automatické aktualizace studia
Claude Code u pluginů od jiných autorů aktualizace samo nezapíná. Zapni je za zákaznici, ať jí nové styly,
písma a efekty chodí samy:
```
STUDIO aktualizace
```
Řekni jí jednou větou: „Automatické aktualizace jsou zapnuté, nové styly ti budou chodit samy.“
Když krok skončí 🔴, řekni jí větu za „Udělej:“.

## 4c. Zvuk
```
STUDIO cink zkouska
```
Zeptej se: „Slyšela jsi dva zvuky?“ Studio pak zahraje zvuk, když na ni čeká, a když dokončí delší práci.

## 5. Zkouška
Řekni: „Hotovo. Chceš to hned vyzkoušet na svém videu?“ a předej dovednosti `novy-reel`.

## 6. Chrome rozšíření Claude (volitelné, jen pro reely z Instagramu)
Když zákaznice pošle odkaz na cizí reel („udělej to podle tohohle“), nejdřív ho otevři vestavěným prohlížečem
aplikace Claude: veřejný reel jde bez přihlášení (OVĚŘENO 3. 11. 2026 na Macu Marcely; u cookies zvol „Odmítnout
volitelné“). Když Instagram chce přihlášení, nebo je reel soukromý, nabídni zálohu: rozšíření Claude pro Chrome
(odkaz dá Marcela v lekci; v obchodě Chrome má být vydavatel Anthropic) a přihlášení na Instagram v jejím Chromu.
Nikdy nechtěj heslo a nikdy se nepřihlašuj za ni. Třetí možnost: pošle snímky obrazovky reelu.
Claude Code jen v Terminálu bez aplikace vestavěný prohlížeč nemá (NEOVĚŘENO): tam rovnou rozšíření nebo snímky.
