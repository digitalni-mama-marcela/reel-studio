#!/bin/sh
# Reel Studio (Digitalni Mama Marcela): sound hook, for hooks/hooks.json.
#
# Claude Code runs hook commands with sh on macOS and with Git Bash on Windows (Git for Windows is needed to add
# the plugin from GitHub, so Git Bash is there). This file runs studio/cink.py with the studio's OWN Python only.
# It never runs a bare python3: on a Mac without Apple's developer tools /usr/bin/python3 opens an
# "install developer tools" window, and on Windows python3 is usually the Microsoft Store placeholder.
# Before the studio is installed there is no own Python yet: then it does nothing and ends quietly (exit 0),
# so a hook never shows an error to the customer.

# "${0%/*}", not dirname: on Windows ${CLAUDE_PLUGIN_ROOT} may come with backslashes, and hooks.json always adds
# "/nastroje/cink.sh" with forward slashes, so cutting at the last "/" gives this folder either way.
HERE=$(cd "${0%/*}" 2>/dev/null && pwd) || exit 0

# Windows (Git Bash): zvuk a hlášky obstará cink.ps1, který hook spouští hned po tomhle (hooks.json). Tady nic.
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) exit 0 ;; esac

if [ -n "${REEL_STUDIO_DATA:-}" ]; then
  DATA="$REEL_STUDIO_DATA"
elif [ -n "${USERPROFILE:-}" ]; then                       # Windows (Git Bash), stejně jako spust.ps1
  DATA="$USERPROFILE/.claude-reel-studio"
elif [ "$(uname -s)" = Darwin ]; then
  DATA="$HOME/Library/Application Support/ClaudeReelStudio"
else
  DATA="$HOME/.claude-reel-studio"
fi

# Git Bash: C:\Users\... na /c/Users/... (cygpath je součást Git for Windows)
command -v cygpath >/dev/null 2>&1 && DATA=$(cygpath -u "$DATA")

for PY in "$DATA/venv/bin/python" "$DATA/venv/Scripts/python.exe"; do
  if [ -f "$PY" ]; then
    # zacatek a start smí psát: co vypíšou (hláška o nové verzi, poznámka z kontroly), dostane Claude jako poznámku
    if [ "${1:-}" = zacatek ] || [ "${1:-}" = start ]; then
      REEL_STUDIO_DATA="$DATA" PYTHONIOENCODING=utf-8 "$PY" "$HERE/studio/cink.py" "$@" 2>/dev/null
    else
      REEL_STUDIO_DATA="$DATA" PYTHONIOENCODING=utf-8 "$PY" "$HERE/studio/cink.py" "$@" >/dev/null 2>&1
    fi
    exit 0
  fi
done

[ -t 0 ] || cat >/dev/null 2>&1      # read what the hook sent (not when typed in a terminal), end quietly
exit 0
