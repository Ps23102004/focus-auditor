# Launch kit (every claim here is backed by a committed run; see docs/REAL-APPS.md and docs/BUGS-FOUND-BY-TESTS.md)

## 20-second launch video script
| Time | Picture | Voice / caption |
|---|---|---|
| 0-3 s | Emulator: focus lands on an icon button. Caption "no accessible name". | "Your Fire TV app works with a remote. Does it work for someone who can't see the screen?" |
| 3-10 s | Dashboard: four findings over the real screen; the focus path hits the wall of a 3-control trap. | "Focus Auditor presses the D-pad over adb, 385 presses, and reports the trap, the unnamed icons, the 30 identical cards." |
| 10-16 s | Terminal: `4 failed` then `4 passed`. Chip: "a fake fix cannot pass". | "Every finding is a frozen live test. A coding agent fixes it in a sandbox, and the same four tests prove it." |
| 16-20 s | End card: "open source, MIT", repo URL. | "Free and open source. github.com/Ps23102004/focus-auditor" |

## Social post (X / LinkedIn / Reddit)
I built Focus Auditor for the Amazon Build, Ship, Shape hackathon (Fire TV track).

It drives a Fire TV / Android TV app with real D-pad presses over adb and reads the accessibility tree at every step. It finds focus traps (controls you can enter but not leave), controls with no accessible name, and groups sharing one name. Each finding becomes a frozen live test that fails while the bug exists. A sandboxed coding agent fixes it and the same tests re-run.

The part I care about most is that it will not lie: crashes, deleted controls and renamed groups cannot fake a pass, and when coverage is incomplete it says "inconclusive", never "pass". I tested the tester with 1,094 offline tests, 600 random apps with known answers, 34 deliberate code breaks, five rounds of independent AI judges (25 real bugs found and fixed), and four Google TV sample apps it had never seen.

Honest limits: Android TV emulator only so far, no screen-reader recording yet (the audio preview is a rules approximation), Vega OS not covered.

MIT: https://github.com/Ps23102004/focus-auditor

## README badge and hero banner spec
- Hero: 1280x320, navy #232F3E, orange #FF9900 focus ring around a small TV-remote D-pad glyph, title "Focus Auditor" (system-ui bold), one line "Drive a Fire TV app with a remote. Prove the fix."
- Badges (shields.io, one row): `license MIT` (orange), `tests 1094 passing` (green), `mutants 34/34 caught` (blue), `platform Android TV / Fire OS` (navy).
- Keep the numbers in the badges in sync with `scripts/mutation_check.py` and `pytest -m "not device"` output; do not add a badge for anything not measured.
