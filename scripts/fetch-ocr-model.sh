#!/usr/bin/env sh
# Downloads the Kraken handwriting model used by the notes_sync OCR, and verifies it.
#
# McCATMuS: French (and 6 other languages) handwritten, printed and typewritten text,
# 16th to 21st century. CC BY 4.0, https://doi.org/10.5281/zenodo.13788177
#
# Usage: scripts/fetch-ocr-model.sh [destination_dir]   (default: ${DATA_PATH:-./data}/models)
# The default destination is mounted as /data/models in the container.
set -eu

NAME="McCATMuS_nfd_nofix_V1.mlmodel"
URL="https://zenodo.org/records/13788177/files/${NAME}?download=1"
SHA256="dfb911ba25fd11f93efc1b0c340957162981ecfdaac0ee1e26793d491f770244"

DEST="${1:-${DATA_PATH:-./data}/models}"
TARGET="${DEST}/${NAME}"

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

if [ -f "$TARGET" ] && [ "$(sha256 "$TARGET")" = "$SHA256" ]; then
    echo "Already present and verified: $TARGET"
    exit 0
fi

mkdir -p "$DEST"
TMP="${TARGET}.part"
trap 'rm -f "$TMP"' EXIT
curl --fail --location --silent --show-error --output "$TMP" "$URL"

ACTUAL="$(sha256 "$TMP")"
if [ "$ACTUAL" != "$SHA256" ]; then
    echo "Checksum mismatch for $NAME: expected $SHA256, got $ACTUAL" >&2
    exit 1
fi
mv "$TMP" "$TARGET"
echo "Model ready: $TARGET"
