#!/bin/sh
# Reel Studio (Digitalni Mama Marcela): launcher for macOS.
#
# Usage:  sh spust.sh <step> [options]          (the same steps as start.py)
#
# The computer needs nothing but what every Mac ships (sh, curl, tar, shasum). No Homebrew, no password,
# nothing installed system-wide. Everything lands in the studio data folder:
#   ~/Library/Application Support/ClaudeReelStudio      (REEL_STUDIO_DATA overrides it, for tests)
# What it does:
#   1. gets the studio its own copy of uv (pinned version, checked against its SHA-256) into <data>/uv
#   2. uv gets the studio its own Python 3.12 into <data>/python (only uv-managed Pythons are used, so the
#      /usr/bin/python3 placeholder, which opens an "install developer tools" window, is never touched)
#   3. runs start.py with that Python
# Output: STATUS lines in English for Claude; start.py then prints its own Czech lines for the customer.

UV_VERSION='0.12.24'
UV_SHA_aarch64='0c4346de7abdb49495b393b9ec809fe387aa43e586be20fecb972216c1e71732'
UV_SHA_x86_64='4fa82e37cb94767661f532b001e470b67a186c7260e305bd84ddb78fd545c0b6'
PY_REQUEST='3.12'

HERE=$(cd "$(dirname "$0")" && pwd)
OS=$(uname -s)

if [ -n "${REEL_STUDIO_DATA:-}" ]; then
  DATA="$REEL_STUDIO_DATA"
elif [ "$OS" = Darwin ]; then
  DATA="$HOME/Library/Application Support/ClaudeReelStudio"
else
  DATA="$HOME/.claude-reel-studio"
fi
UV="$DATA/uv/uv"

missing() {   # $1 = what, $2 = why
  echo "STATUS $1 MISSING ($2)"
  echo 'NOT READY'
  exit 1
}

uv_runs() { [ -x "$UV" ] && "$UV" --version >/dev/null 2>&1; }

if ! uv_runs; then
  [ "$OS" = Darwin ] || missing uv "this launcher supports macOS only, on Windows use spust.ps1"
  # Apple Silicon even when this shell runs under Rosetta (uname -m then says x86_64)
  if [ "$(uname -m)" = arm64 ] || [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then
    target='aarch64-apple-darwin'; sum="$UV_SHA_aarch64"
  else
    target='x86_64-apple-darwin'; sum="$UV_SHA_x86_64"
  fi
  echo 'STATUS uv: getting the studio its own copy of uv (about 15 MB, one time)'
  mkdir -p "$DATA" || missing uv "could not create $DATA"
  part="$DATA/uv.tar.gz.part"
  unpack="$DATA/uv.unpack"
  rm -rf "$part" "$unpack"                 # leftovers of a run that was cut off
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
  try=1
  until curl -fsSL --connect-timeout 20 --speed-limit 1024 --speed-time 45 -o "$part" "$url"; do
    rm -f "$part"
    [ "$try" -lt 3 ] || missing uv 'no internet, or GitHub could not be reached'
    try=$((try + 1))
    echo "STATUS uv: the download did not finish, trying again (attempt $try of 3)"
    sleep 3
  done
  got=$(shasum -a 256 "$part" | cut -d ' ' -f 1)
  if [ "$got" != "$sum" ]; then
    rm -f "$part"
    missing uv 'the download did not pass its checksum, so it was not used'
  fi
  mkdir -p "$unpack" && tar -xzf "$part" -C "$unpack"
  rm -f "$part"
  mkdir -p "$DATA/uv"
  mv -f "$unpack/uv-$target/uv" "$UV" 2>/dev/null
  rm -rf "$unpack"
  uv_runs || missing uv 'the downloaded uv does not run on this Mac'
  echo "STATUS uv OK ($UV_VERSION, the studio's own copy)"
fi

# Everything uv downloads or caches stays in the studio data folder
UV_PYTHON_INSTALL_DIR="$DATA/python"
UV_CACHE_DIR="$DATA/uv-cache"
UV_PYTHON_PREFERENCE='only-managed'
UV_NO_CONFIG='1'
REEL_STUDIO_UV="$UV"
REEL_STUDIO_DATA="$DATA"
REEL_STUDIO_PYTHON="$PY_REQUEST"
PYTHONIOENCODING='utf-8'
export UV_PYTHON_INSTALL_DIR UV_CACHE_DIR UV_PYTHON_PREFERENCE UV_NO_CONFIG REEL_STUDIO_UV REEL_STUDIO_DATA \
       REEL_STUDIO_PYTHON PYTHONIOENCODING

if ! "$UV" python find "$PY_REQUEST" >/dev/null 2>&1; then
  echo 'STATUS python: getting the studio its own Python 3.12 (about 25 MB, one time)'
  # --no-bin: no python3.12 link in ~/.local/bin, everything stays in the studio folder
  "$UV" python install --no-bin "$PY_REQUEST" >/dev/null 2>&1 || "$UV" python install --no-bin "$PY_REQUEST" \
    || missing python 'uv could not download Python 3.12: check the internet connection and run it again'
  "$UV" python find "$PY_REQUEST" >/dev/null 2>&1 \
    || missing python "Python 3.12 was downloaded but cannot be started from $DATA. Send this output to Marcela"
  echo 'STATUS python OK (3.12, the studio'"'"'s own copy)'
fi

exec "$UV" run --quiet --no-project --python "$PY_REQUEST" "$HERE/start.py" "$@"
