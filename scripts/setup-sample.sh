#!/usr/bin/env bash
# Recreate Amazon's hello-world-fire-tv sample with our planted bugs and the agent fixes (v1: buggy/fixed; v2: buggy-v2/fixed-v2).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d sample-native ] || git clone https://github.com/AmazonAppDev/hello-world-fire-tv.git sample-native
cd sample-native
git checkout -q -B baseline 50108f4
git checkout -q -B buggy baseline && git am -q ../sample-patches/buggy/*.patch
git checkout -q -B fixed buggy && git am -q ../sample-patches/fixed/*.patch
git checkout -q -B buggy-v2 buggy && git am -q ../sample-patches/buggy-v2/*.patch    # v2: real Search/Settings icons, no names
git checkout -q -B fixed-v2 buggy-v2 && git am -q ../sample-patches/fixed-v2/*.patch  # v2: the sandboxed agent fix
git checkout -q buggy
echo "sample-native ready: branches baseline, buggy, fixed (v1) and buggy-v2, fixed-v2 (the demo in the video)"
