#!/usr/bin/env bash
# Full v2 demo pipeline on the buggy-v2 sample (real Search/Settings icons with no accessible name).
# Every step logs to demo-v2/run.log; nothing here is mocked. Run from the repo root with the emulator up.
set -uo pipefail
cd "$(dirname "$0")/.."
export ANDROID_SDK_ROOT=/opt/homebrew/share/android-commandlinetools ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH" TORCH_HOME="$PWD/.cache-ml"
OUT=demo-v2; mkdir -p "$OUT"; LOG="$OUT/run.log"
say_step() { echo "=== $(date +%H:%M:%S) $*" | tee -a "$LOG"; }

say_step "1 build+install buggy-v2"
git -C sample-native checkout -q buggy-v2
(cd sample-native && ./gradlew assembleDebug --no-daemon -q) >>"$LOG" 2>&1
adb install -r sample-native/app/build/outputs/apk/debug/app-debug.apk >>"$LOG" 2>&1

say_step "2 audit buggy-v2"
python3 -m fa audit --out "$OUT/before/" >>"$LOG" 2>&1
python3 - <<'PY' | tee -a "$LOG"
import json; r=json.load(open("demo-v2/before/report.json")); print("before:", r["verdict"], r["summary"])
PY

say_step "3 frozen tests (expect failures)"
python3 -m fa tests --report "$OUT/before/report.json" --out tests_generated_v2 >>"$LOG" 2>&1
python3 -m pytest tests_generated_v2 -m device -q --junitxml="$OUT/before-junit.xml" 2>&1 | tail -3 | tee -a "$LOG"

say_step "4 local VLM name suggestions (Gemma 4 via Ollama)"
.venv-ml/bin/python -m fa.ml.labelnames suggest --report "$OUT/before/report.json" --shots "$OUT/before" \
  --out "$OUT/name-suggestions.json" >>"$LOG" 2>&1
cat "$OUT/name-suggestions.json" | tee -a "$LOG"

say_step "5 sandboxed fix with suggestions (untrusted)"
git -C sample-native checkout -q -B fixed-v2 buggy-v2
python3 -m fa fix --report "$OUT/before/report.json" --app-dir sample-native --out "$OUT/fix" --agent claude \
  --model sonnet --tests tests_generated_v2 --suggestions "$OUT/name-suggestions.json" 2>&1 | tail -8 | tee -a "$LOG"
git -C sample-native add -A -- app && git -C sample-native -c user.name="Parth Singh" -c user.email="noreply@example.com" \
  commit -q -m "fixed-v2: agent fix using model-suggested names (sandboxed fix loop)" >>"$LOG" 2>&1

say_step "6 re-audit fixed-v2"
python3 -m fa audit --out "$OUT/after/" >>"$LOG" 2>&1
python3 - <<'PY' | tee -a "$LOG"
import json; r=json.load(open("demo-v2/after/report.json")); print("after:", r["verdict"], r["summary"])
PY

say_step "7 witness screenshots + spoken before/after"
python3 scripts/demo_v2_audio.py >>"$LOG" 2>&1

say_step "8 export dashboard data (v2)"
python3 -m fa export-web --report "$OUT/before/report.json" --after "$OUT/after/report.json" \
  --after-junit "$OUT/fix/after-junit.xml" --suggestions "$OUT/name-suggestions.json" \
  --announcements docs/demo/announcements.json --out web/data-v2 >>"$LOG" 2>&1
python3 scripts/make_ml_json.py docs/ml web/data-v2 >>"$LOG" 2>&1
say_step "done"
