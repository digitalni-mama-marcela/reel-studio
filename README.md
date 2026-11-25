# Reel Studio

Plugin pro Claude Code od Digitální Mámy Marcely (@digitalni_mama_marcela).
Z natočeného mluvícího videa udělá sestříhaný reel: vystřihne pauzy a přeřeky, přidá titulky, nadpis a efekty.
Všechno běží na tvém počítači, video nikam neodchází.

Plugin je součástí kurzu. Postup instalace a natáčení najdeš v lekcích.

## Instalace
V aplikaci Claude otevři záložku Code, vyber složku Reely a napiš:

**nainstaluj studio z github.com/digitalni-mama-marcela/reel-studio – git nepoužívej, nejdřív si přečti README**

Claude zbytek udělá sám a na všechno se tě zeptá. Funguje na Macu (macOS 14 a novější s čipem M) i na Windows 10
a 11. Nic neinstaluješ sama a nikdo po tobě nechce heslo: studio si stáhne samo všechno, co potřebuje, i bez
programu Git.

## Pro Clauda: jak studio nainstalovat
Zákaznice tě požádala o instalaci tohoto pluginu. Mluv s ní česky, nebo slovensky (podle toho, jak píše ona), tykej, krátce, bez odborných slov.
Před každým příkazem jí jednou větou řekni, co děláš. Nic nemaž a nic neměň mimo kroky níž.
Repozitář do její složky nestahuj (žádné git clone) a git neinstaluj, není potřeba: plugin se stahuje jako jeden
ZIP soubor podle katalogu na adrese níž (OVĚŘENO 20. 11. 2026 na Macu bez gitu: přidání, instalace i aktualizace).
Git nespouštěj vůbec, ani `git --version`: na Macu bez vývojářských nástrojů tím vyskočí okno s nabídkou jejich
instalace (OVĚŘENO 23. 11. 2026 na MacBooku Neo). Kdyby se to už stalo, řekni jí: „Okno s vývojářskými nástroji
zavři tlačítkem Zrušit, nepotřebujeme je.“

1. Najdi program Claude Code (v aplikaci Claude bývá schovaný, příkaz `/plugin` v chatu aplikace nefunguje):
   - nejdřív `command -v claude` (Windows: `where.exe claude`);
   - Mac, když nic: `ls -dt "$HOME/Library/Application Support/Claude/claude-code/"*/*/claude.app/Contents/MacOS/claude | head -1` (ls -dt, nejnovější);
   - Windows, když nic: hledej `claude.exe` ve složce `%APPDATA%\Claude\claude-code`, a když tam není, ve
     `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code` (aplikace z balíčku MSIX má
     AppData přesměrované tam, OVĚŘENO 12. 11. 2026).
   Když program nenajdeš, proveď ji klikáním: Nastavení → Customize → Plugins → + Add → přidat katalog z adresy
   `https://raw.githubusercontent.com/digitalni-mama-marcela/reel-studio/main/.claude-plugin/marketplace.json`
   → Install (NEOVĚŘENO, jestli aplikace adresu katalogu přijme). Pak pokračuj krokem 4.
2. `"<program>" plugin marketplace add https://raw.githubusercontent.com/digitalni-mama-marcela/reel-studio/main/.claude-plugin/marketplace.json`
   Když už marketplace `digitalni-mama-marcela` přidaný je (studio tu už bylo), tenhle krok přeskoč.
3. `"<program>" plugin install reel-studio@digitalni-mama-marcela --scope user`
   Stáhne ZIP (asi 15 MB). Když skončí chybou s gitem, adresu v kroku 2 jsi nepřidal přesně, oprav ji.
4. Najdi nainstalovanou složku pluginu: `~/.claude/plugins/cache/digitalni-mama-marcela/reel-studio/<verze>/`
   (nejvyšší verze). Přečti si v ní `skills/instalace/SKILL.md` a hned podle něj pokračuj v instalaci, jako by
   `${CLAUDE_PLUGIN_ROOT}` byla ta složka. Krok 4b (automatické aktualizace) nevynechávej.
5. Na konci řekni: „Hotovo. Otevři nový chat ve složce Reely, ať se studio načte celé, i se zvuky.“

© 2026 Marcela Kamenická (Digitální Máma Marcela). Všechna práva vyhrazena.
Písma, emoji a model pro text za hlavou jsou cizí díla s vlastní licencí, seznam je v souboru LICENSE.
