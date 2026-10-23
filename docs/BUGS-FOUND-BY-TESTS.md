# Bugs found by the expanded test suite and by independent review (all fixed, each has a regression test)

| # | Bug | Found by | Effect before the fix |
|---|---|---|---|
| 1 | Model-suggested names could contain newlines, control or bidi characters | webexport tests | Untrusted text reached the dashboard |
| 2 | AFTER findings defaulted to "passing" with no test result | webexport tests | A still-present defect could read as passing |
| 3 | List position counted hidden zero-size nodes | announce tests | "1 of 3" with two visible controls |
| 4 | `Adb.key("")` mapped to `KEYCODE_DPAD_` and was sent | adb mock tests | Invalid key sent to the device |
| 5 | Bounds numbers over 4300 digits raised `ValueError` | hypothesis | Parser crash on untrusted dump |
| 6 | Deeply nested dump raised `RecursionError` | hypothesis | Parser crash on untrusted dump |
| 7 | Whitespace-only text counted as a name | crawl/detector tests | MISSING_LABEL missed (screen reader says nothing) |
| 8 | Names differing only by whitespace were not grouped | detector tests | DUPLICATE_LABEL missed |
| 9 | Whole-screen closed region reported as a firm trap | real app (Google TV Material Catalog) | False positive on a normal top-level screen |
| 10 | `fa fix` exited 0 when the post-fix frozen tests failed | independent judge (GPT-6 Astra) | A failed fix looked successful to scripts/CI |
| 11 | Label test passed for a named but non-focusable control | independent judge | Remote still could not reach it |
| 12 | Duplicate test passed when the whole group was renamed to one new shared name | independent judge | Defect moved, not fixed |
| 13 | Mutation script counted any non-zero pytest exit as a kill, with no green baseline | independent judge | Could overstate test strength |
| 14 | The crawler recorded screens of a different app as nodes of the audited app | full re-audit of the fixed app (`demo-v2/after-full/`, kept as evidence) (2 of the 127 recorded snapshot files, 70 of 8,352 UI nodes, came from the Catalog app) | 8 findings of another app attributed to the audited app. Fixed: `left_app` is reported, nothing recorded, verdict never pass |
| 15 | Whole-screen downgrade also hid full-screen modal traps | independent judges (round 2) | Now only when BACK can leave the screen; a modal BACK cannot leave stays a firm trap |
| 16 | Duplicate test passed when every label in the group was erased | independent judge (GPT-6 Astra, round 2) | An agent could blank all names and receive a passing regression |
| 17 | A one-control screen (first-run onboarding) was reported as pass | real app: Google Leanback sample | Now inconclusive (`tiny_coverage`) with a hint to use `--entry` |
| 18 | Cards that show their title only when focused were reported as unnamed (38 false positives) | real app: Google Leanback sample | Names are judged in the focused state; controls never seen focused become a `label_unverified` coverage note |
| 19 | A named card scrolled into the same slot vouched for an unnamed card (silent false pass) | independent judges (Fable 5.1 and Opus 5.5, round 3) | Focused-state evidence now needs the same screen context, and 'unnamed while focused' wins |
| 20 | The whole-screen downgrade ignored controls the crawl never reached (a 5-item menu trap became suspected) | independent judge (Opus 5.5, round 3) | Counts every focusable on screen |
| 21 | Frozen tests passed when a key crashed or exited the app (launcher screen counted as 'left the region') | independent judge (Fable 5.1, round 4) | Every check now requires the audited package to be in front |
| 22 | Trap region judged against the snapshot with the most controls, not its own screen; re-analysed reports named the wrong app; scroll-pass nodes never counted as unexpanded | independent judge (Fable 5.1, round 4) | Own-screen judgement, app name from the recorded graph, scroll-pass nodes counted |
| 23 | Whole-screen check lost its floor of all known controls; findings with no key path got an unpassable frozen test; nodes added by the BACK probe were never counted | independent judge (Fable 5.1, round 5) | Floor restored; no test is generated without a key path (stated on stderr); unexpanded count taken last |
| 24 | A multi-root snapshot whose focused node belonged to another app passed the 'app in front' check | independent judge (GPT-6 Astra, round 5) | The focused node's package is checked as well |
| 25 | A normal two-button second page counted the previous page's controls as 'outside' and was reported as a firm trap | independent judge (GPT-6 Astra, round 5) | Whole-screen test uses the region's own screen only (small screens that BACK leaves are 'suspected', never a firm fail) |
| 26 | A control whose name is only zero-width or other invisible characters counted as named (also passed the frozen test) | independent judges (Fable 5.1, Opus 5.5, round 6) | Invisible format/control characters are stripped before a name counts |
| 27 | Two heuristics (collapsed-form, sliver) dropped an unnamed focused control silently, which could yield a clean pass | independent judges (round 6) | Every suppression adds a `label_unverified` note, so the audit is inconclusive |
| 28 | A description was discarded when the text was only whitespace | independent judge (Fable 5.1, round 6) | The description is used |

The mutation check (`scripts/mutation_check.py`) now requires a green baseline, counts only pytest exit code 1, and covers these fixes (36 mutants).
