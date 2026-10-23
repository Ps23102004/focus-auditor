#!/bin/sh
# One command per video shot. Run from the repo root: ./video-kit/shot.sh <step>
# Everything here replays REAL committed runs or runs the real tool; nothing is mocked.
set -e
cd "$(dirname "$0")/.."
SDK=/opt/homebrew/share/android-commandlinetools
export PATH="$SDK/platform-tools:$SDK/emulator:$PATH"
PKG=com.amazonappstore.helloworldtv
PY=.venv-test/bin/python
[ -x "$PY" ] || PY=python3

case "$1" in
  boot)      # start the Android TV emulator (skip if already running) and turn animations off
    adb devices | grep -q emulator || { nohup emulator -avd firetv_test -no-snapshot-save -no-audio -no-boot-anim >/tmp/emu.log 2>&1 & }
    until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 3; done
    for k in window_animation_scale transition_animation_scale animator_duration_scale; do adb shell settings put global $k 0; done
    echo "emulator ready" ;;
  buggy)     # install the build with the planted bugs and open it
    adb install -r video-kit/hello-buggy.apk >/dev/null && adb shell am start -S -n $PKG/.MainActivity >/dev/null && echo "buggy build running" ;;
  fixed)     # install the agent-fixed build and open it
    adb install -r video-kit/hello-fixed.apk >/dev/null && adb shell am start -S -n $PKG/.MainActivity >/dev/null && echo "fixed build running" ;;
  say-before) afplay docs/demo/announce-72c12df2ba-before.m4a ;;   # rules preview: "unlabelled, button"
  say-after)  afplay docs/demo/announce-72c12df2ba-after.m4a ;;    # rules preview: "Search, button"
  replay)    # re-analyse the recorded 385-press crawl of the buggy app (instant, real data)
    $PY -m fa audit --from-fixture demo-v2/before --out /tmp/fa-replay ;;
  tests)     # the 4 frozen live tests against whatever build is installed (about 1-3 minutes)
    $PY -m pytest -m device tests_generated_v2 -q ;;
  gate)      # the unit tests that attack the fix-loop gate
    $PY -m pytest -q tests/test_fixloop_gates.py tests/test_fixloop.py ;;
  diff)      # the coding agent's committed fix
    git apply --stat demo-v2/fix/agent.diff; echo; head -40 demo-v2/fix/agent.diff ;;
  suite)     # whole offline suite
    $PY -m pytest -q -m "not device" | tail -3 ;;
  mutants)   # deliberately break the code 32 ways; every break must be caught (about 3-5 minutes)
    $PY scripts/mutation_check.py | tail -3 ;;
  dash)      # dashboard with the v2 run (real screenshot, findings, suggestions, audio)
    (cd web && nohup python3 -m http.server 8765 --bind 127.0.0.1 >/tmp/fa-dash.log 2>&1 &) ; sleep 1
    open "http://127.0.0.1:8765/index.html?data=v2" ;;
  tv)        # companion app on the TV (shows the report; arrow keys move, Enter inspects, Esc back)
    adb shell am start -S -n com.focusauditor.tv/.MainActivity >/dev/null && echo "companion app open" ;;
  *) echo "usage: $0 boot|buggy|fixed|say-before|say-after|replay|tests|gate|diff|suite|mutants|dash|tv"; exit 1 ;;
esac
