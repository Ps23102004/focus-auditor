# Focus Auditor: submission text

**Name:** Focus Auditor
**Track:** Fire TV. **Mini challenges:** Open Source (this repo, MIT). AWS Builder: not claimed (a Bedrock backend exists but Bedrock denied model access to my account; see README).

**Tagline:** Drives a Fire TV app with a remote, reads the accessibility tree a screen reader uses, hands each failure to a coding agent and re-runs the frozen test that proves the fix.

## What it does
Focus Auditor drives a running Fire TV (Fire OS / Android TV) app with real D-pad input over adb, builds its focus graph, and reads the accessibility tree at every step. It reports focus traps (controls you can enter but never leave with the D-pad), controls with no accessible name, and controls that share one name. Each finding becomes a frozen live test that fails while the defect exists and passes once fixed (and fails if the control is just deleted). A coding agent gets the failing tests plus Amazon Devices Builder Tools documentation over MCP, patches the app; the loop rebuilds, reinstalls and reruns the tests. A dashboard and a Fire TV companion app show the findings over the real TV screenshot, before and after.

## How I built it
Python engine (adb + UI Automator, stdlib only) with a bounded crawler that relaunches and replays a verified path for every probe; 1094 offline tests with a mutation check (34/34 caught). Dashboard: vanilla HTML/CSS/JS with a hand-written spring-physics module (interruptible springs, Apple-style damping/response). Fire TV companion app: Kotlin WebView app that bundles the dashboard in 10-foot mode. Fix agent: Claude Code (Sonnet) with file-only tools and the ADBT MCP server.

## Results (real runs on Amazon's hello-world-fire-tv sample with planted bugs, Android TV emulator)
4 findings (1 trap of 3 controls, 2 unnamed icon tiles, 30 cards named "Movie Name"), identical finding ids on two runs; the 4 generated tests fail on the buggy build; after the agent's one-file fix the loop's own run passed 2 of 4 (the first tests matched controls by their position in the UI tree), and after I made them match by class and on-screen bounds they passed 4 of 4 on the fixed build. An earlier agent run was required to consult ADBT first: it cited three Fire TV accessibility and UX documents and its fix passed 4 of 4 tests on the first run. Re-audit of the fixed app: 0 findings, reported as inconclusive because coverage was incomplete. On four Google TV samples I had never seen (Catalog, Leanback, TV Reference app, JetStream) the audit found 8 cards without a name while focused and no confirmed trap, and was inconclusive on three (replay mismatches and budgets): a limit I report rather than hide (`docs/REAL-APPS.md`).

## Platform note
Demoed on the Android TV emulator; the hackathon FAQ states "Fire TV: an emulator (Android TV Emulator or the Fire TV/Vega simulator) is fine - a physical device isn't required at any stage of submission or judging." Vega OS is not covered yet.

## Product feedback / friction log
See docs/FRICTION-LOG.md (14 entries: ADBT, Fire TV emulator, sample app, Compose focus, UI Automator speed, Bee CLI).

## Existing work
New during the submission window (repo created Oct 18-19 2026). The sample app is Amazon's (MIT-0); my changes are the planted bugs (`buggy`, `buggy-v2`) and the agent fixes (`fixed`, `fixed-v2`), recreated by `scripts/setup-sample.sh` from `sample-patches/`.

## What I learned
A test that can only pass is worse than no test. Independent judge models (Fable 5.1, Opus 5.5, GPT-6 Astra) and four Google TV samples I had never seen found 23 real defects in my own checker, including several ways it could have reported success when it should not. Each is fixed with a regression test (`docs/BUGS-FOUND-BY-TESTS.md`).

## What's next
A measured run on a physical Fire TV Stick, a real screen-reader recording (VoiceView/TalkBack utterances are not observable from outside the device), and Vega OS support.

## Built with
Python, adb/UI Automator, Kotlin and Jetpack Compose (sample + companion app), vanilla JS dashboard, Claude Code and Amazon's Devices Builder Tools MCP server, Gemma 4 (local, via Ollama) for icon-name suggestions.

## Links
Repo: https://github.com/Ps23102004/focus-auditor (MIT). Video: [paste the YouTube/Vimeo link here]; a copy is also in the repo at docs/demo-video/focus-auditor-demo.mp4. Open Source contribution URL and GitHub username: https://github.com/Ps23102004/focus-auditor and Ps23102004.
