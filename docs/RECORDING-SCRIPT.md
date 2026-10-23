# Focus Auditor demo video: recording script

Solo project by Parth Singh. Target 2:55, hard limit 3:00. Speak at a normal pace and keep key presses brisk; the narration alone is about 2:30. Record each shot as its own clip, then join them.
Everything you show is a real run or a replay of a committed recording. Say "planted" and "rules preview" exactly where the script says so; judges reward honesty. First person singular throughout: you built this alone.

## 0. Setup (once, before recording, about 10 min)
Open Terminal and run these in order:

```bash
cd ~/Developer/focus-auditor
```

```bash
./video-kit/shot.sh boot
```

```bash
./video-kit/shot.sh buggy
```

```bash
./video-kit/shot.sh dash
```

- Screen recorder: Cmd+Shift+5, "Record Selected Portion" or full screen, Options > Microphone = your mic.
- Layout: emulator window left, Terminal right. Terminal font about 18 pt, dark theme, readable at 1080p.
- Turn on a Focus mode so no notifications appear.
- Pre-run the slow parts once now (frozen tests 1-3 min, mutation check 3-5 min) so you can record them sped up or cut to the summary line.

## 1. Intro and the first bug (0:00-0:25)
**Screen:** emulator with the buggy app. Click the emulator window, press Down, then Right until focus is on the first icon tile in the Quick actions row. Then run `./video-kit/shot.sh say-before`.

**Say:** "Hi, I'm Parth Singh, and this is Focus Auditor, which I built on my own for the Amazon Build, Ship, Shape hackathon. On a Fire TV you navigate with a remote, and blind users rely on a screen reader. This button has no name, so a screen reader has nothing to say for it; my rules preview reads it as 'unlabelled'. I planted these bugs in Amazon's hello-world sample so I can show the whole loop."

## 2. The trap (0:25-0:40)
**Screen:** on the Quick actions row press Up and Down a few times: focus stays in the row. Then press Escape (Back): the app closes.

**Say:** "There's also a trap I planted: three controls you can enter with the remote but can't leave with the D-pad. Only Back gets you out. One focus rule causes it, and it's easy to miss in code review."

## 3. How it finds them (0:40-1:00)
**Run:** `./video-kit/shot.sh replay` (shows verdict fail, 4 findings, 385/400 presses).

**Say:** "Focus Auditor doesn't change the app. It drives the running app over adb with real D-pad presses, about four hundred of them, and reads the accessibility tree at every step. This is a replay of that recorded eleven-minute run: four findings, each with the exact key presses that prove it."

## 4. The dashboard (1:00-1:25)
**Screen:** the browser tab from `shot.sh dash`. Click the trap finding (the ball hits the wall), then "Icon-only control without a name" to show the suggestion "Search" tagged "Gemma 4 · local · unverified suggestion".

**Say:** "The dashboard puts each finding on the real screenshot. For icons, a local vision model, Gemma 4, suggests a name. It runs on my laptop, never on the TV, and it's only a suggestion: a person confirms it, and the test only checks that a name exists."

## 5. Frozen tests fail, the agent fixes (1:25-1:55)
**Run (pre-recorded; speed up or cut to the summary):** `./video-kit/shot.sh tests` → "4 failed". Then `./video-kit/shot.sh diff`, then `./video-kit/shot.sh gate`.

**Say:** "Every finding becomes a frozen live test that fails while the bug exists. Then a coding agent fixes it in a sandboxed copy of the app, and a gate refuses any change outside the app's source files. These unit tests attack that gate. Here's the agent's fix: one file."

## 6. Proof the fix works (1:55-2:20)
**Run:** `./video-kit/shot.sh fixed`. Press Down, Right to the icons, then Up and Down: focus now leaves the row. Then `./video-kit/shot.sh say-after`, then `./video-kit/shot.sh tests` (pre-recorded, sped up) → "4 passed".

**Say:** "I rebuild and rerun the same four tests: four of four pass, and the icon now has a name. The tests also fail if the app crashes, leaves, or the control is simply deleted, so a fake fix can't pass."

## 7. Testing the tester (2:20-2:45)
**Run:** `./video-kit/shot.sh suite`. Optionally the last line of `./video-kit/shot.sh mutants` (pre-recorded): "32/32 mutants killed".

**Say:** "I also tested the tester: about eleven hundred offline tests, six hundred random apps with known answers, and thirty-two deliberate code breaks that the tests all catch. On four Google TV apps it had never seen, it found eight cards without a name, and when it can't be sure it says 'inconclusive', never 'pass'."

## 8. Close (2:45-2:58)
**Run:** `./video-kit/shot.sh tv`. Move through the findings with the arrow keys.

**Say:** "Amazon's Builder Tools teach agents how to build for Fire TV. Focus Auditor checks what they build. I'm Parth Singh, it's open source under MIT, and thanks for watching."

**End card:** Focus Auditor · Parth Singh · github.com/Ps23102004/focus-auditor

## Do not say
- "TalkBack says" or "a screen reader says": the speech is a rules preview played on the laptop.
- "Works on a real Fire TV": it ran on the Android TV emulator, which the hackathon FAQ allows.
- "Bedrock" or "AWS Builder": Bedrock was not available to this account.
- "The model names icons correctly": it was checked on two icons only.

## After recording
1. Trim dead air, keep it under 3:00, export 1080p.
2. Upload to YouTube as Unlisted (or Vimeo) and copy the link.
3. Paste the link into `docs/SUBMISSION.md` (Links) and the Devpost form.
