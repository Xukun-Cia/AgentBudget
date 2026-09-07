#!/bin/bash
# Optional: sync the editor companion into local Cursor.
# The main product is the Ubuntu desktop app — install the .deb (see README).
VERSION="1.1.0"
for ver in 0.1.0 0.2.0 0.3.0 0.3.1 0.4.0 0.5.0 0.5.1 0.5.2 0.5.3 0.5.4 0.6.0 0.6.1 0.6.2 0.6.3 0.6.4 0.7.0 0.8.0 0.8.1 0.9.0; do
  [ -d "$HOME/.cursor/extensions/local.cursor-daily-budget-$ver" ] && \
    rm -rf "$HOME/.cursor/extensions/local.cursor-daily-budget-$ver"
done
for ver in 1.0.0 1.0.1 1.0.2 1.0.3 1.1.0; do
  [ -d "$HOME/.cursor/extensions/local.cursorbudget-$ver" ] && \
    rm -rf "$HOME/.cursor/extensions/local.cursorbudget-$ver"
done
EXT_DIR="$HOME/.cursor/extensions/local.cursorbudget-$VERSION"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$EXT_DIR/lib"
cp "$SRC_DIR/package.json" "$EXT_DIR/"
cp "$SRC_DIR/extension.js" "$EXT_DIR/"
cp "$SRC_DIR/lib/"*.js "$EXT_DIR/lib/"
cp "$SRC_DIR/lib/"*.json "$EXT_DIR/lib/"

echo "✓ Editor companion synced to $EXT_DIR"
echo "  Reload Cursor (Ctrl+Shift+P → Developer: Reload Window)"
echo "  Desktop app: sudo apt install ./dist/cursorbudget_${VERSION}_all.deb && cursorbudget"
