#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="cursorbudget"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${ROOT}/cursorbudget/__init__.py")"
ARCH="all"
PKG_DIR="${ROOT}/dist/${NAME}_${VERSION}_${ARCH}"
DEB_PATH="${ROOT}/dist/${NAME}_${VERSION}_${ARCH}.deb"

"${ROOT}/scripts/check-privacy.sh"

rm -rf "${PKG_DIR}" "${DEB_PATH}"
mkdir -p \
  "${PKG_DIR}/DEBIAN" \
  "${PKG_DIR}/usr/bin" \
  "${PKG_DIR}/usr/lib/python3/dist-packages/cursorbudget" \
  "${PKG_DIR}/usr/lib/cursorbudget/lib" \
  "${PKG_DIR}/usr/share/applications" \
  "${PKG_DIR}/usr/share/doc/${NAME}" \
  "${PKG_DIR}/usr/share/icons/hicolor" \
  "${PKG_DIR}/usr/share/pixmaps"

python3 "${ROOT}/scripts/render_icon.py" \
  --out "${PKG_DIR}/usr/share/icons/hicolor" \
  --pixmap "${PKG_DIR}/usr/share/pixmaps/cursorbudget.png"

find "${PKG_DIR}" -type d -exec chmod 0755 {} +
find "${PKG_DIR}/usr/share/icons" "${PKG_DIR}/usr/share/pixmaps" -type f -exec chmod 0644 {} +

install -m 0755 "${ROOT}/bin/cursorbudget" "${PKG_DIR}/usr/bin/cursorbudget"
install -m 0644 "${ROOT}/cursorbudget/"*.py "${PKG_DIR}/usr/lib/python3/dist-packages/cursorbudget/"
install -m 0644 "${ROOT}/lib/"*.js "${PKG_DIR}/usr/lib/cursorbudget/lib/"
install -m 0644 "${ROOT}/lib/"*.json "${PKG_DIR}/usr/lib/cursorbudget/lib/"
install -m 0644 "${ROOT}/data/cursorbudget.desktop" "${PKG_DIR}/usr/share/applications/cursorbudget.desktop"
install -m 0644 "${ROOT}/README.md" "${PKG_DIR}/usr/share/doc/${NAME}/README.md"
install -m 0644 "${ROOT}/LICENSE" "${PKG_DIR}/usr/share/doc/${NAME}/copyright"

cat > "${PKG_DIR}/DEBIAN/control" <<EOF
Package: ${NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-cairo, nodejs
Maintainer: Xukun-Cia <noreply@users.noreply.github.com>
Description: Local Cursor and GPT quota monitor for Ubuntu
 CursorBudget shows Cursor API, Cursor Models, and GPT weekly quota in
 a compact floating card or GNOME top-bar readout. Login state and
 usage stay on this machine.
EOF

cat > "${PKG_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "${PKG_DIR}/DEBIAN/postinst"

# Refuse to package accidental local dumps.
if find "${PKG_DIR}" -iname '*api-response*' -o -iname 'probe-results.json' -o -name '*.vscdb' | grep -q .; then
  echo "Refusing to package local Cursor dumps" >&2
  exit 1
fi

dpkg-deb --build --root-owner-group "${PKG_DIR}" "${DEB_PATH}"
echo "Built ${DEB_PATH}"
ls -lh "${DEB_PATH}"
