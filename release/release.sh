#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Validate input
# -----------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <version>"
    exit 1
fi

VERSION="$1"
APP="retentions"

# Determine project root directory (parent of release/)
ROOT_DIR="$(dirname "$(dirname "$0")")"

BUILD_DIR="${ROOT_DIR}/build"
PKG_DIR="${BUILD_DIR}/${APP}-${VERSION}"
DEB_DIR="${BUILD_DIR}/deb"
COMPL_DIR="${ROOT_DIR}/deploy/shell-completions"

echo "==> Building version ${VERSION}"

# -----------------------------------------------------------------------------
# Prepare build directories
# -----------------------------------------------------------------------------
echo "==> Cleaning old build artifacts..."
rm -rf "$BUILD_DIR"
mkdir -p "$PKG_DIR/macos" "$PKG_DIR/linux" "$PKG_DIR/docs" "$COMPL_DIR"

mkdir -p "$DEB_DIR/usr/bin" \
         "$DEB_DIR/usr/share/doc/${APP}" \
         "$DEB_DIR/usr/share/man/man1/" \
         "$DEB_DIR/DEBIAN" \
         "$DEB_DIR/usr/share/bash-completion/completions/" \
         "$DEB_DIR/usr/share/zsh/vendor-completions"

# -----------------------------------------------------------------------------
# Inject VERSION into retentions.py
# -----------------------------------------------------------------------------
echo "==> Injecting version into retentions.py..."
cd "$ROOT_DIR"
sed -i.bak -E "s/^(VERSION\s*(:\s*str)?\s*=\s*\")[^\"]*(\")/\1${VERSION}\3/" retentions.py

# -----------------------------------------------------------------------------
# Build macOS / Linux variants
# -----------------------------------------------------------------------------
echo "==> Creating macOS executable..."
{
    echo "#!/usr/bin/env python3"
    cat retentions.py
} > "${PKG_DIR}/macos/${APP}"
chmod 755 "${PKG_DIR}/macos/${APP}"

echo "==> Creating Linux executable..."
{
    echo "#!/usr/bin/python3"
    cat retentions.py
} > "${PKG_DIR}/linux/${APP}"
chmod 755 "${PKG_DIR}/linux/${APP}"

echo "==> Copying Python source..."
cp retentions.py "${PKG_DIR}/${APP}.py"

# -----------------------------------------------------------------------------
# Documentation + Manpage
# -----------------------------------------------------------------------------
echo "==> Copying documentation..."
cp README.md LICENSE SECURITY.md CONTRIBUTING.md DESIGN_DECISONS.md RELEASE_POLICY.md "$PKG_DIR/docs/" 2>/dev/null || true

echo "==> Copying man page..."
cp deploy/man_page/retentions.1 "$PKG_DIR/docs/${APP}.1"

# -----------------------------------------------------------------------------
# Create tar.gz archive
# -----------------------------------------------------------------------------
echo "==> Creating tar.gz archive..."
tar --owner=0 --group=0 -C "$BUILD_DIR" -czf "${BUILD_DIR}/${APP}-${VERSION}.tar.gz" "${APP}-${VERSION}"
echo "    -> ${BUILD_DIR}/${APP}-${VERSION}.tar.gz"

# -----------------------------------------------------------------------------
# Create ZIP archive
# -----------------------------------------------------------------------------
echo "==> Creating zip archive..."
(
    cd "$BUILD_DIR"
    zip -r "${APP}-${VERSION}.zip" "${APP}-${VERSION}" >/dev/null
)
echo "    -> ${BUILD_DIR}/${APP}-${VERSION}.zip"

# -----------------------------------------------------------------------------
# Provide retentions.py as standalone artifact
# -----------------------------------------------------------------------------
echo "==> Exporting standalone retentions.py..."
cp retentions.py "${BUILD_DIR}/${APP}.py"

# -----------------------------------------------------------------------------
# DEB package
# -----------------------------------------------------------------------------
echo "==> Creating Debian package..."

{
    echo "#!/usr/bin/python3"
    cat retentions.py
} > "$DEB_DIR/usr/bin/${APP}"
chmod 755 "$DEB_DIR/usr/bin/${APP}"

cp README.md LICENSE SECURITY.md CONTRIBUTING.md DESIGN_DECISONS.md RELEASE_POLICY.md "$DEB_DIR/usr/share/doc/${APP}/" 2>/dev/null || true

gzip -9 < deploy/man_page/retentions.1 > "$DEB_DIR/usr/share/man/man1/${APP}.1.gz"

cp "$COMPL_DIR/${APP}.bash" "$DEB_DIR/usr/share/bash-completion/completions/${APP}"
cp "$COMPL_DIR/_${APP}"      "$DEB_DIR/usr/share/zsh/vendor-completions/"

cat > "$DEB_DIR/DEBIAN/control" <<EOF
Package: ${APP}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Maintainer: Thomas Kuhlmann <mail@thomas-kuhlmann.de>
Description: file retention cleanup tool (CLI)
 A small feature-rich cross-platform retention utility for pruning old file sets.
EOF

dpkg-deb --build --root-owner-group "$DEB_DIR" "${BUILD_DIR}/${APP}_${VERSION}_all.deb"
echo "    -> ${BUILD_DIR}/${APP}_${VERSION}_all.deb"

# -----------------------------------------------------------------------------
# RPM package via alien
# -----------------------------------------------------------------------------
echo "==> Creating RPM via alien..."
(
    TMPDIR="$(mktemp -d)"
    cp "${BUILD_DIR}/${APP}_${VERSION}_all.deb" "$TMPDIR/"
    cd "$TMPDIR"
    alien --to-rpm --scripts --version="${VERSION}-1" "${APP}_${VERSION}_all.deb" >/dev/null
    mv ./*.rpm "${OLDPWD}/build/"
    rm -rf "$TMPDIR"
)

# -----------------------------------------------------------------------------
# Self-extracting Linux installer (.install)
# -----------------------------------------------------------------------------
echo "==> Creating self-extracting Linux installer..."

INSTALLER_PAYLOAD_DIR="${BUILD_DIR}/${APP}-${VERSION}-linux-installer"
INSTALLER_FILE="${BUILD_DIR}/${APP}-${VERSION}-linux.install"

rm -rf "$INSTALLER_PAYLOAD_DIR"
mkdir -p "$INSTALLER_PAYLOAD_DIR/docs" "$INSTALLER_PAYLOAD_DIR/man"

# Python with shebang
{
    echo "#!/usr/bin/python3"
    cat retentions.py
} > "$INSTALLER_PAYLOAD_DIR/retentions.py"
chmod 755 "$INSTALLER_PAYLOAD_DIR/retentions.py"

# Docs
cp README.md LICENSE SECURITY.md CONTRIBUTING.md DESIGN_DECISONS.md RELEASE_POLICY.md "$INSTALLER_PAYLOAD_DIR/docs/" 2>/dev/null || true

# Man page
cp deploy/man_page/retentions.1 "$INSTALLER_PAYLOAD_DIR/man/retentions.1"

# Shell completions
mkdir -p "$INSTALLER_PAYLOAD_DIR/completions/bash"
mkdir -p "$INSTALLER_PAYLOAD_DIR/completions/zsh"

cp "$COMPL_DIR/${APP}.bash" "$INSTALLER_PAYLOAD_DIR/completions/bash/${APP}"
cp "$COMPL_DIR/_${APP}"      "$INSTALLER_PAYLOAD_DIR/completions/zsh/_${APP}"

# Build payload archive
PAYLOAD_TAR="$(mktemp)"
tar -czf "$PAYLOAD_TAR" -C "$INSTALLER_PAYLOAD_DIR" .

# Installer header
cat > "$INSTALLER_FILE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP="retentions"
PREFIX="/usr/local"

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo)." >&2
    exit 1
fi

ARCHIVE_LINE=$(awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0;}' "$0")

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "==> Extracting payload..."
tail -n +"$ARCHIVE_LINE" "$0" | tar xz -C "$TMPDIR"

echo "==> Installing executable..."
install -m 755 "$TMPDIR/retentions.py" "${PREFIX}/bin/retentions"

echo "==> Installing documentation..."
mkdir -p "${PREFIX}/share/doc/${APP}"
install -m 644 "$TMPDIR/docs/"* "${PREFIX}/share/doc/${APP}/"

echo "==> Installing man page..."
mkdir -p "${PREFIX}/share/man/man1"
install -m 644 "$TMPDIR/man/retentions.1" "${PREFIX}/share/man/man1/"

echo "==> Installing shell completions..."
mkdir -p "${PREFIX}/share/bash-completion/completions"
install -m 644 "$TMPDIR/completions/bash/${APP}" "${PREFIX}/share/bash-completion/completions/${APP}"

# Zsh
mkdir -p "${PREFIX}/share/zsh/site-functions"
install -m 644 "$TMPDIR/completions/zsh/_${APP}" "${PREFIX}/share/zsh/site-functions/_${APP}"

mandb || true

echo "==> ${APP} installed successfully."
exit 0

__ARCHIVE_BELOW__
EOF

cat "$PAYLOAD_TAR" >> "$INSTALLER_FILE"
chmod 755 "$INSTALLER_FILE"

rm -f "$PAYLOAD_TAR"
rm -rf "$INSTALLER_PAYLOAD_DIR"

# -----------------------------------------------------------------------------
# Restore retentions.py
# -----------------------------------------------------------------------------
echo "==> Restoring original retentions.py..."
mv retentions.py.bak retentions.py

echo "==> Done."
