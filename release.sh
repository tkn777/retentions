#!/usr/bin/env bash

set -euo pipefail

APP="retentions"
VERSION="${1:-0.0.0}"
BUILD_DIR="build"
PKG_DIR="${BUILD_DIR}/${APP}-${VERSION}"
DEB_DIR="${BUILD_DIR}/deb"

echo "==> Building version ${VERSION}"
echo "==> Cleaning old build artifacts..."
rm -rf "$BUILD_DIR"
mkdir -p "$PKG_DIR/macos" "$PKG_DIR/linux" "$PKG_DIR/docs"
mkdir -p "$DEB_DIR/usr/bin" "$DEB_DIR/usr/share/doc/${APP}" "$DEB_DIR/usr/share/man/man1/" "$DEB_DIR/DEBIAN" "$DEB_DIR/usr/share/bash-completion/completions/" "$DEB_DIR/usr/share/zsh/vendor-completions"

# ---------------------------------------------------------------------------
# Patch retentions.py VERSION (supports type hints)
# ---------------------------------------------------------------------------
echo "==> Injecting version into retentions.py..."
sed -i.bak -E "s/^(VERSION\s*(:\s*str)?\s*=\s*\")[^\"]*(\")/\1${VERSION}\3/" retentions.py

# ---------------------------------------------------------------------------
# TAR.GZ (cross-platform release)
# ---------------------------------------------------------------------------

# macOS variant (#!/usr/bin/env python3)
echo "==> Creating macOS variant..."
{
    echo "#!/usr/bin/env python3"
    cat retentions.py
} > "${PKG_DIR}/macos/${APP}"
chmod 755 "${PKG_DIR}/macos/${APP}"

# Linux variant (#!/usr/bin/python3)
echo "==> Creating Linux variant..."
{
    echo "#!/usr/bin/python3"
    cat retentions.py
} > "${PKG_DIR}/linux/${APP}"
chmod 755 "${PKG_DIR}/linux/${APP}"

# Common variant
echo "==> Copy common variant..."
cp retentions.py "${PKG_DIR}/${APP}.py"

# Documentation
echo "==> Copying docs..."
cp README.md LICENSE CHANGELOG.md SECURITY.md ROADMAP.md "$PKG_DIR/docs/" 2>/dev/null || true

# Create tar.gz archive
echo "==> Creating tar.gz package..."
tar --owner=0 --group=0 -C "$BUILD_DIR" -czf "${BUILD_DIR}/${APP}-${VERSION}.tar.gz" "${APP}-${VERSION}"
echo "    -> ${BUILD_DIR}/${APP}-${VERSION}.tar.gz"

# Create ZIP archive
echo "==> Creating zip package..."
(
    cd "$BUILD_DIR"
    zip -r "${APP}-${VERSION}.zip" "${APP}-${VERSION}" >/dev/null
)
echo "    -> ${BUILD_DIR}/${APP}-${VERSION}.zip"

# ---------------------------------------------------------------------------
# DEB (Debian/Ubuntu)
# ---------------------------------------------------------------------------
echo "==> Creating Debian package..."
{
    echo "#!/usr/bin/python3"
    cat retentions.py
} > "$DEB_DIR/usr/bin/${APP}"
chmod 755 "$DEB_DIR/usr/bin/${APP}"

cp README.md LICENSE CHANGELOG.md SECURITY.md ROADMAP.md "$DEB_DIR/usr/share/doc/${APP}/" 2>/dev/null || true
gzip -9 < debian/retentions.1 > "$DEB_DIR/usr/share/man/man1/${APP}.1.gz"
cp debian/bash-shell-completion "$DEB_DIR/usr/share/bash-completion/completions/retentions/${APP}"
cp debian/zsh-shell-completion "$DEB_DIR/usr/share/zsh/vendor-completions/_${APP}"

cat > "$DEB_DIR/DEBIAN/control" <<EOF
Package: ${APP}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Maintainer: Thomas Kuhlmann <mail@thomas-kuhlmann.de>
Description: Simple file retention cleanup tool (CLI)
 A small cross-platform retention utility for pruning old file sets.
EOF

dpkg-deb --build --root-owner-group "$DEB_DIR" "${BUILD_DIR}/${APP}_${VERSION}_all.deb"
echo "    -> ${BUILD_DIR}/${APP}_${VERSION}_all.deb"

# ---------------------------------------------------------------------------
# RPM (via alien, isolated temp dir)
# ---------------------------------------------------------------------------
(
    TMPDIR="$(mktemp -d)"
    cp "${BUILD_DIR}/${APP}_${VERSION}_all.deb" "$TMPDIR/"
    cd "$TMPDIR"
    alien --to-rpm --scripts --version="${VERSION}-1" "${APP}_${VERSION}_all.deb" >/dev/null
    mv ./*.rpm "${OLDPWD}/build/"
    rm -rf "$TMPDIR"
)

# ---------------------------------------------------------------------------
# Restore original retentions.py
# ---------------------------------------------------------------------------
echo "==> Restoring original retentions.py..."
mv retentions.py.bak retentions.py

echo "==> Done."
