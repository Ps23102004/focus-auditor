# Real-app runs (not my own test app)

## Google TV Material Catalog (`com.google.tv.material.catalog`, Compose for TV), emulator API 31, Oct 19 2026
Audit: 114 presses, 17 focusable nodes, 314 s, no coverage gaps recorded. Raw data: `tests/fixtures/catalog/` (replayable offline).

| Result | What I know | What I do not know |
|---|---|---|
| 8 MISSING_LABEL with the current detector (12 in the first analysis, before names were judged in the focused state) (focusable cards, `NAF="true"`, empty text and content-description) | The dump shows each card exposes no name of its own. The visible label ("Color", "Buttons"...) is a separate non-focusable `TextView` sibling, not merged into the card. | Whether TalkBack/VoiceView still announces the sibling text through Compose semantic merging. Not checked with a real screen reader, so this is "no name in the accessibility tree", not "unusable by a blind user". |
| 1 TRAP, 17 closed controls (4 more focusables on that screen) | Live replay of the frozen test (written when the region was 14 controls) reproduced it in 16 min: from none of those controls does any D-pad direction leave the set. | It is the whole home screen. A top-level screen with nothing to navigate to is normal, so this is NOT claimed as a defect. The detector now marks regions of 75% or more of the screen as suspected (`whole_screen`). |

## Why this matters
Running on an app I did not write found a false positive my own test app could not. The fix and the data are committed
(`tests/test_crawl_edge.py::test_region_that_is_most_of_the_screen_is_only_suspected`).

## Google JetStream (Compose for TV reference)
An early run (352 presses, 49 controls) kept no raw output; the current recording is in the four-app table below (54 controls).

## Not yet done
- A screen-reader check of the 8 unnamed Catalog cards (TalkBack utterances are not observable from outside; see friction log 14).
- Fixing third-party apps is out of scope.

## Own sample app, frozen tests both ways (Oct 19)
Same four tests (matching controls by class and on-screen bounds), same emulator: buggy-v2 build `4 failed` (145 s), fixed-v2 build `4 passed` (55 s).

## Clean full re-audit of the fixed sample app (Oct 19, after the foreign-app crawler fix)
`python3 -m fa audit --pkg com.amazonappstore.helloworldtv --activity .MainActivity --out demo-v2/after-full2 --max-nodes 120 --max-presses 1000 --deadline 3300`
0 findings, 124 controls, 869 presses, every committed snapshot (124 of the 8,224 recorded) is from the audited package. Verdict inconclusive (press budget, node cap with 4 controls unexpanded, 3 replay mismatches), so this is "no defect found in what I could reach", not a clean certificate.

## Four apps the tool had never seen (Oct 19-20), re-analysed with the current detector
Audited on the Android TV emulator with `--max-nodes 60 --max-presses 400 --deadline 1500`; recordings (UI dumps and focus graphs, no screenshots) committed in `real-audits/<app>/`, re-analysis with `python3 -m fa audit --from-fixture real-audits/<app> --out real-audits/reanalysed-<app>`.

| App (Google sample, Apache 2.0) | Verdict | Findings | Notes |
|---|---|---|---|
| Leanback "Videos by Google" | inconclusive | none | 31 controls. First run showed only an onboarding screen and was wrongly reported as pass (bug 17). After onboarding: 36 cards look unnamed but were never seen focused on the same screen; every card that was focused had a title, so none is reported (bug 18). 7 replay mismatches. |
| TV Reference app | inconclusive | 1 trap, suspected | `--entry CENTER` dismisses a "Firebase not configured" dialog. The closed region is 14 of the 32 focusables on its screen (BACK leaves it), so it is NOT a whole-screen region; it stays suspected only because one replay mismatched and one control was not expanded. Unresolved: not claimed as a defect. 22 controls only seen unfocused. |
| JetStream | inconclusive | none | 54 controls, press budget used up. All snapshots from the audited package. |
| TV Material Catalog | fail | 8 unnamed cards (seen focused and unnamed), 1 trap (suspected, whole screen) | 29 more controls only seen unfocused are not reported (`label_unverified`). |

What this shows: on apps I did not write, the tool produced two false-positive classes and one false pass, all now fixed with regression tests. It has not yet found a confirmed defect in a Google sample beyond the 8 Catalog cards, and those are "no name in the accessibility tree while focused", not a screen-reader recording.

Re-run after the package checks were added to the frozen tests (Oct 20, fresh emulator boot): buggy-v2 `4 failed` (160 s), fixed-v2 `4 passed` (61 s).

Final check on submission day (Oct 23, fresh emulator boot, no other process using adb): buggy-v2 `4 failed` (174 s); fixed-v2 `4 passed` in three consecutive runs (64-69 s each). One earlier batch right after reinstalling the app had one transient failure on the fixed build (passed alone twice, then 3 x 4/4): a startup flake that can only make a test fail, never pass.
