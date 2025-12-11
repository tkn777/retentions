#!/usr/bin/env bash
set -euo pipefail

OUTDIR="${1:?Missing output directory}"
mkdir -p "$OUTDIR"

python3 - <<EOF > "${OUTDIR}/retentions.bash"
import shtab, retentions
parser = retentions.create_parser()
print(shtab.complete(parser, shell="bash"))
EOF

python3 - <<EOF > "${OUTDIR}/_retentions"
import shtab, retentions
parser = retentions.create_parser()
print(shtab.complete(parser, shell="zsh"))
EOF
