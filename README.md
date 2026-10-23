# Focus Auditor

**Drives a Fire TV app with a remote and reads the accessibility tree a screen reader uses, then hands each failure to a coding agent and re-runs the test that proves the fix.**

Amazon's Devices Builder Tools (ADBT) teach AI coding agents how to build Fire TV apps. Static checkers and Accessibility Scanner exist; I found nothing in ADBT that drives the running app with a D-pad to verify focus. Focus Auditor drives the running app with real D-pad input over adb, maps the focus graph, and reports:

- **Focus traps**: a set of controls where every UP, DOWN, LEFT and RIGHT press lands back inside, while the rest of the screen is unreachable. BACK is recorded separately and never counted as an escape.
- **Unnamed controls**: focusable controls with no exposed accessible name (own text, content description, or named children), including icon-only buttons.
- **Duplicate names**: many controls exposing the same name (informational).

Each finding becomes a **frozen live test** that fails while the defect exists and passes once it is fixed (it also fails if the control is simply deleted). A coding agent gets a fix prompt with file-only tools plus ADBT's documentation over MCP, patches the app, and the loop rebuilds, reinstalls and reruns the tests. A dashboard shows the findings over the real TV screenshot, and a Fire TV companion app shows the same report on the TV.


## Demo video (2:44)
[Watch it here](https://github.com/Ps23102004/focus-auditor/blob/main/docs/demo-video/focus-auditor-demo.mp4) (720p copy in this repo; every shot is a real run: the emulator, the dashboard, the test output). Script and the rule that every number on screen comes from a committed run: `docs/VIDEO-SCRIPT.md`.

## Results on Amazon's `hello-world-fire-tv` sample (Android TV emulator, API 31, 1920x1080)
On a `buggy` branch I planted a focus trap (a Compose row with `focusProperties { exit = Cancel }`) and two icon-only tiles; the sample's 30 cards already share the name "Movie Name".

| Step | Result (real runs) |
|---|---|
| Audit (buggy) | 4 findings: 1 trap (3 controls), 2 unnamed icon tiles, 1 duplicate-name group (30). 385 D-pad presses, 55 controls mapped, about 11 minutes (676 s, `demo-v2/before/report.json`). Identical finding ids on two runs. |
| Generated tests on buggy | 4 failed |
| Coding agent fix (Claude Code, Sonnet, file tools only) | 1 file changed, 7 insertions and 14 deletions (`demo-v2/fix/agent.diff`): trap exit removed, `contentDescription` added to the tiles, card titles made distinct |
| Generated tests on the fixed build | The fix loop's own post-fix run passed 2 of 4: the first version of the frozen tests matched controls by their position in the UI tree, which shifts after a fix (`demo-v2/fix/fixloop.json`). I then made the tests match by class and on-screen bounds and reran: 4 failed on the buggy build and 4 passed on the fixed build (`docs/REAL-APPS.md`). |
| Fix rerun with ADBT required (v1 patch: `sample-patches/fixed`; the committed evidence of ADBT use is the v2 log `demo-v2/fix/fixloop.json`) | agent called ADBT `search_documentation` and cited "Design and User Experience Guidelines" (Fire TV), "Implement VoiceView Accessibility Features (Fire TV)" and the Fire OS assistive-technologies API doc (search snippets only); 1 file, +13/-11; 4 of 4 tests passed on the first run |
| Re-audit of the fixed app | clean full rerun after the crawler fixes: 0 findings, 124 controls, inconclusive (budget, node cap); details in `docs/REAL-APPS.md` |
| Offline tests | 1104 passed, 2 skipped (`python3 -m pip install -r requirements-dev.txt && python3 -m pytest -q -m "not device"`); 36 of 36 deliberate code mutations are caught (`scripts/mutation_check.py`). Writing them (and an independent judge) found and fixed 28 real bugs, five of them ways a frozen test or `fa fix` could report success when it should not (bugs 10, 11, 12, 16, 21): see `docs/BUGS-FOUND-BY-TESTS.md`. |

**Real apps:** four Google TV samples the tool had never seen (Catalog, Leanback, TV Reference app, JetStream): recordings in `real-audits/`, results and limits in `docs/REAL-APPS.md`.

Honest limits: Fire OS / Android TV only (Vega not tested). A control seen unnamed while focused can still be skipped when it looks like the collapsed or clipped form of a wider named control in another state; every such skip now adds a `label_unverified` coverage note, so the audit is reported as inconclusive instead of passing. Other known limits: a list whose focused row stays pinned at one position can look like a small focus region (false trap) because control identity ignores labels; a focusable container whose only text comes from a nested focusable child is treated as named. A small trap on a screen it fills almost entirely (4 of 5 controls) that BACK can leave is reported as suspected, not as a firm fail. Frozen tests can flake to a failure right after an app install, never to a pass. Claims are "unnamed in the accessibility tree", not what VoiceView announces. A crawl that runs out of budget is reported with coverage notes and can never show a pass. `uiautomator dump` takes ~2.5 s on the emulator, so a full audit is slow.

## Quick start
Requirements: macOS/Linux, Python 3.10+. For live runs also Android SDK platform-tools, an Android TV emulator image, and JDK 17 for the sample.

No emulator needed (about a minute):
```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q -m "not device"                                        # offline tests
python3 -m fa audit --from-fixture tests/fixtures/buggy --out out/fixture   # replay a recorded audit
python3 -m http.server 38417 --directory web                                # dashboard: http://127.0.0.1:38417/?data=v2
```

Live, with the Android TV emulator running:
```bash
scripts/setup-sample.sh        # clones Amazon's sample into sample-native/ and applies my patches (branches below)
(cd sample-native && git checkout buggy-v2 && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk)
python3 -m fa audit --out out/live                                 # live audit (about 11 minutes)
python3 -m fa tests --report out/live/report.json --out out/tests  # frozen live tests
python3 -m pytest out/tests -m device -q                           # they fail on the buggy build
python3 -m fa fix --report out/live/report.json --app-dir sample-native --tests out/tests   # agent fix in a sandboxed copy, build, install, rerun
python3 -m fa export-web --report out/live/report.json --out web/data-live   # then open the dashboard with ?data=live
```
Fire TV companion app: `cd tv-app && ./gradlew assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk`.

## Layout
`fa/` engine (adb, tree, crawl, detectors, report, testgen, fixloop, webexport, cli) · `tests/` offline suite + recorded fixture · `web/` dashboard (vanilla HTML/CSS/JS, spring physics in `motion.js`) · `tv-app/` Fire TV WebView app · `sample-native/` Amazon's sample, created by `scripts/setup-sample.sh` (branches `baseline`, `buggy`, `fixed` for v1; `buggy-v2`, `fixed-v2` for the video demo); `sample-patches/` my patches · `docs/` friction log, design shots.

## Built with
adb + UI Automator, Jetpack Compose for TV (sample), Android TV emulator, Amazon Devices Builder Tools MCP (fix agent docs), Claude Code (fix agent). License: MIT (Focus Auditor); the sample app is Amazon's, MIT-0.


## AI layer (what is real, what is measured)
All three parts are optional; the verdicts always come from deterministic evidence and frozen tests.
- **Name suggestions (local vision-language model).** `python -m fa.ml.labelnames suggest` crops each unnamed control and asks Gemma 4 through Ollama (free, offline) for a 1-3 word accessible name. Output is strictly parsed, treated as untrusted, never executed, and only passed to the fix agent as quoted data. The frozen test proves a name is *exposed*, not that it is *correct*; the dashboard tags suggestions "unverified". Accuracy is reported only when at least 20 real labelled icons exist (see `docs/ml/label-eval.csv`).
- **Same-screen matching (pretrained image network).** A frozen MobileNetV3 embedding is compared with four rule baselines on auto-labelled screen pairs, calibrated and tested on disjoint halves of the recorded paths (`docs/ml/screen-match.md`). On my data the simple tree-hash check beat the network, so the auditor keeps the simple check; the experiment and numbers stay in the repo.
- **Announcements (rules, not ML).** `python -m fa announce` renders TalkBack-style text ("Menu A, button, 1 of 3") and can speak it with macOS `say`. It approximates TalkBack and is not what VoiceView says on a device.
- Bedrock: a `--backend bedrock` flag exists but has never run live (see the end of this file), so the AWS Builder mini is not claimed. Ideas that were cut, and why, are in `docs/AI-ROADMAP.md`.

## Security model of the fix loop
Text on the audited app's screen is untrusted (an app can show anything). So:
- The coding agent works in a **throwaway copy** of the app (no `.git`, no build output). Every file is hashed before and after; if the agent changed anything other than `app/src/main/**/*.{kt,java,xml}` (build scripts, Gradle wrapper, `.git`, symlinks, `..` paths), **nothing** is applied. Otherwise only those source files are copied back (real path checked, no symlinks), then the whole real checkout, including `.git` and build output, must differ from its pre-run snapshot in exactly those files, or nothing is built. Apps containing symlinks are refused. Absolute-path deny rules also cover the real checkout.
- App-derived labels reach the prompt only as quoted JSON marked UNTRUSTED.
- Agent tools: read/search scoped to the copy, edit scoped to app sources, three ADBT documentation tools; explicit deny rules for build files, shell, write and web. I tested that a headless allow-list alone can be widened by a user's global settings while the deny rules held, so the copy-back gate is the guarantee.
- Generated tests embed frozen data as escaped JSON; ids, kinds, package, activity and keys are validated before files are written and again before any adb call; every `adb shell` argument is shell-quoted.


## Real apps and footprint
- Real apps (Catalog: 8 cards unnamed while focused; Leanback, Reference and JetStream: no confirmed finding, all inconclusive): `docs/REAL-APPS.md`.
- What runs where, and memory: `docs/FOOTPRINT.md`. The local model (Gemma 4, 6.1 GB) runs on the developer machine, never on the TV; the optional companion app measured about 150 MB on a 2 GB emulator.

## Optional: run the fix agent through Amazon Bedrock
`python -m fa fix ... --backend bedrock --model us.anthropic.claude-haiku-5-5 --aws-region us-east-1` routes Claude Code through Bedrock
(needs AWS credentials in the environment; they are checked for presence only and never logged). Unit-tested without any call
(`tests/test_bedrock_backend.py`). Not verified against a live Bedrock call. Playground tests on Oct 19 and Oct 20 (Claude Haiku 5.5, one prompt each) returned
AccessDeniedException: first "account is being verified", then "anthropic.claude-haiku-5-5 is not available for this account".
Do not read this as a working Bedrock integration; the AWS Builder mini is not claimed.

## Author
Built solo by Parth Singh for the Amazon Build, Ship, Shape hackathon (Fire TV track). MIT licensed; see `LICENSE` and `NOTICE`.
