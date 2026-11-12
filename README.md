# Reel Studio

Plugin pro Claude Code od Digitální Mámy Marcely (@digitalni_mama_marcela).
Z natočeného mluvícího videa udělá sestříhaný reel: vystřihne pauzy a přeřeky, přidá titulky, nadpis a efekty.
Všechno běží na tvém počítači, video nikam neodchází.

Plugin je součástí kurzu. Postup instalace a natáčení najdeš v lekcích.

## Instalace
V aplikaci Claude otevři záložku Code, vyber složku Reely a napiš:

**nainstaluj studio z github.com/digitalni-mama-marcela/reel-studio**

Claude zbytek udělá sám a na všechno se tě zeptá. Funguje na Macu (macOS 14 a novější s čipem M) i na Windows 10
a 11. Nic neinstaluješ sama a nikdo po tobě nechce heslo: studio si nástroje pro střih stáhne samo.

**Jen na Windows, jednou předem:** nainstaluj Git for Windows z git-scm.com (tlačítko Download for Windows,
pak pořád Next). Pak aplikaci Claude úplně zavři (i ikonu vedle hodin) a znovu otevři. Bez Gitu si Claude
plugin z GitHubu nestáhne. Když Claude napíše, že chybí git, udělej tohle a zkus to znovu.

## Pro Clauda: jak studio nainstalovat
Zákaznice tě požádala o instalaci tohoto pluginu. Mluv s ní česky, tykej, krátce, bez odborných slov.
Před každým příkazem jí jednou větou řekni, co děláš. Nic nemaž a nic neměň mimo kroky níž.
Repozitář do její složky nestahuj (žádné git clone). Stačí ti tenhle návod, plugin si stáhne krok 3 sám.

0. Windows: když chybí git (`git --version` nejde), řekni jí krok „Jen na Windows“ výš a počkej, až ho udělá.
   Bez gitu nejde přidat plugin z GitHubu.
1. Najdi program Claude Code (v aplikaci Claude bývá schovaný, příkaz `/plugin` v chatu aplikace nefunguje):
   - nejdřív `command -v claude` (Windows: `where claude`);
   - Mac, když nic: `ls -dt "$HOME/Library/Application Support/Claude/claude-code/"*/*/claude.app/Contents/MacOS/claude | head -1` (ls -dt, nejnovější);
   - Windows, když nic: hledej `claude.exe` ve složce `%APPDATA%\Claude\claude-code` (nevyzkoušeno).
   Když program nenajdeš, proveď ji klikáním: Nastavení → Customize → Plugins → + Add → přidat z GitHubu
   `digitalni-mama-marcela/reel-studio` → Install. Pak pokračuj krokem 4.
2. `"<program>" plugin marketplace add digitalni-mama-marcela/reel-studio`
3. `"<program>" plugin install reel-studio@digitalni-mama-marcela --scope user`
4. Najdi nainstalovanou složku pluginu: `~/.claude/plugins/cache/digitalni-mama-marcela/reel-studio/<verze>/`
   (nejvyšší verze). Přečti si v ní `skills/instalace/SKILL.md` a hned podle něj pokračuj v instalaci, jako by
   `${CLAUDE_PLUGIN_ROOT}` byla ta složka. Krok 4b (automatické aktualizace) nevynechávej.
5. Na konci řekni: „Hotovo. Otevři nový chat ve složce Reely, ať se studio načte celé, i se zvuky.“

© 2026 Marcela Kamenická (Digitální Máma Marcela). Všechna práva vyhrazena.
Písma, emoji a model pro text za hlavou jsou cizí díla s vlastní licencí, seznam je v souboru LICENSE.
