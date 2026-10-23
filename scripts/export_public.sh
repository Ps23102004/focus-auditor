#!/usr/bin/env bash
# Build a clean single-commit copy of the tracked tree (no history) for publishing. Usage: scripts/export_public.sh [dest]
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:-../focus-auditor-public}"
rm -rf "$DEST" && mkdir -p "$DEST"
git archive HEAD | tar -x -C "$DEST"
cd "$DEST"
git init -q -b main
git add -A
git -c user.name="Parth Singh" -c user.email="noreply@example.com" commit -q -m "Focus Auditor: drive a Fire TV app with a remote, prove focus and screen-reader defects, verify the fix"
echo "exported $(git ls-files | wc -l) files to $DEST (1 commit)"
