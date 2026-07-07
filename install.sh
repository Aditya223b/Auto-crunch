#!/usr/bin/env bash
set -euo pipefail

REPO_RAW_URL="${AUTOCRUNCH_REPO_RAW_URL:-https://raw.githubusercontent.com/Aditya223b/Auto-crunch/main}"
INSTALL_ROOT="${AUTOCRUNCH_INSTALL_ROOT:-$HOME/.local/lib/autocrunch}"
BIN_DIR="${AUTOCRUNCH_BIN_DIR:-$HOME/.local/bin}"
BIN_PATH="$BIN_DIR/autocrunch"

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [[ -f "./src/autocrunch.py" && "${1:-}" == "--local" ]]; then
  cp "./src/autocrunch.py" "$INSTALL_ROOT/autocrunch"
else
  curl -fsSL "$REPO_RAW_URL/src/autocrunch.py" -o "$INSTALL_ROOT/autocrunch"
fi

chmod +x "$INSTALL_ROOT/autocrunch"
ln -sfn "$INSTALL_ROOT/autocrunch" "$BIN_PATH"

echo "Installed Auto-crunch to $BIN_PATH"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo
    echo "Add this to your shell profile if autocrunch is not found:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

echo
echo "Try:"
echo "  autocrunch doctor"
echo "  autocrunch run"

