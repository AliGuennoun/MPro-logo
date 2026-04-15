#!/usr/bin/env bash
# Polyglot installer for macOS and Linux.
# Creates a local virtualenv, installs dependencies, and drops a
# `polyglot` launcher script you can call from anywhere.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

echo "==> Polyglot installer"
echo "    Target directory: $DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required but was not found on PATH" >&2
  exit 1
fi

PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
PY_MINOR="$(echo "$PY_VER" | cut -d. -f2)"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
  echo "error: python 3.9+ required (found $PY_VER)" >&2
  exit 1
fi

case "$(uname -s)" in
  Linux*)
    if ! dpkg -s portaudio19-dev >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
      echo "==> You may need portaudio. On Debian/Ubuntu:"
      echo "    sudo apt-get install -y portaudio19-dev python3-dev"
    fi
    ;;
  Darwin*)
    if ! command -v brew >/dev/null 2>&1; then
      echo "note: Homebrew not detected. If sounddevice fails, install portaudio:"
      echo "      brew install portaudio"
    fi
    ;;
esac

echo "==> Creating virtualenv at $VENV"
python3 -m venv "$VENV"

# shellcheck disable=SC1091
. "$VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$DIR/requirements.txt"

LAUNCHER="$DIR/polyglot"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
exec "\$DIR/.venv/bin/python" "\$DIR/polyglot.py" "\$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

echo
echo "==> Done."
echo "    1. export OPENAI_API_KEY=sk-..."
echo "    2. $LAUNCHER"
echo
echo "    Then press Ctrl+Alt+Space in any app and start speaking."
