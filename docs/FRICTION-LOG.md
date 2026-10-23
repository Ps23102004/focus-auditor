# Friction log and product feedback (real entries from building Focus Auditor, Oct 18-19 2026)

Format per entry: task, steps, expected vs actual, severity, workaround, suggestion. Only things I actually hit are listed.

## Amazon Devices Builder Tools (ADBT) 1.0.17, `@amazon-devices/amazon-devices-buildertools-mcp`
**1. `init-context` installs skills globally even when MCP config is skipped.** Severity: medium.
- Task: add ADBT context to one project without touching global agent config.
- Steps: `npx -y @amazon-devices/amazon-devices-buildertools-mcp@1.0.17 init-context -a other -m -p <project dir> -f`.
- Expected: a context document written into the project only (`-m` = skip MCP config).
- Actual: 20 skills were copied into the user-global `~/.agents/skills/` (amazon-devices-* plus vega-multi-tv-migration) with no prompt; the summary printed "Installed 1 skill".
- Workaround: none needed for the build; I run the ADBT MCP server per process via a project-local `--mcp-config` file instead.
- Suggestion: add `--skills-dir` / `--no-skills`, install skills into the project by default when `-p` is given, and report the full list of installed skills.

**2. Fire OS support is "limited" while the hackathon's Fire TV track is mostly Fire OS.** Severity: low.
- ADBT docs: full support for Vega OS, limited for Fire OS. My app is a Fire OS / Android TV Compose app; the focus-management skill (`amazon-devices-vega-focus-management`) targets Vega's TVFocusGuideView. There is no runtime verification of focus in ADBT; the `scalable-ui-audit` skill is a read-only code scan. Suggestion: a Fire OS focus/accessibility skill, and a runtime check (this is the gap Focus Auditor fills).

## Fire TV development without a device
**3. No Fire OS emulator image; the closest is a stock Android TV AVD.** Severity: medium.
- Task: run and demo a Fire TV app with no Fire TV Stick.
- The FAQ allows the Android TV emulator or the Fire TV/Vega simulator. The Android TV system images available through `sdkmanager` are API 31+ (Android 12+), while Fire OS 8 is Android 11 based. Suggestion: publish a Fire OS AVD system image (or document which Android TV image best matches each Fire OS release).

**4. `avdmanager create avd ... -d tv_1080p` prints "Could not load devices from .../devices.xml" yet creates the AVD.** Severity: low. Misleading error; the AVD works.

**5. `hello-world-fire-tv` sample needs JDK 17.** Severity: low.
- `./gradlew assembleDebug` uses Gradle 8.2, which does not run on JDK 21 (current Homebrew default). Workaround: `brew install openjdk@17` and set `JAVA_HOME`. Suggestion: state the JDK requirement in the README or bump the Gradle wrapper.

**6. Compose TV focus traps depend on modifier order.** Severity: info (documentation).
- `Modifier.focusProperties { exit = { FocusRequester.Cancel } }.focusGroup()` traps focus; `.focusGroup().focusProperties { ... }` does not. `exit` is experimental and needs `@OptIn(ExperimentalComposeUiApi::class)`. Easy to get wrong, invisible in code review, and exactly what a runtime auditor catches.

**7. The sample's 30 cards all expose the same name "Movie Name".** Severity: low. Fine for a template, but it ships an accessibility anti-pattern by default; a screen reader announces the same name 30 times.

## Android tooling used by the auditor
**8. `uiautomator dump` is slow on the emulator (~2.5 s per dump).** Severity: medium for tool builders. A full bounded crawl of one screen took about 11 minutes (676 s) (385 presses, 136 probes, 27 cold starts). Workaround: animations off, one dump per step, budgets. Suggestion (Amazon): an official fast focus-state query for Fire OS (e.g. `dumpsys` of the focused accessibility node) would make runtime auditing practical in CI.

## Bee developer tools (explored for an earlier idea)
**9. `bee login` needs a TTY.** Severity: medium. Run from a non-interactive shell it printed usage and exited 0. Workaround: `script -q /dev/null bee login`. Suggestion: support non-TTY polling, or fail with a clear message.
**10. Login QR flow is unclear.** Severity: medium. Scanning the connect QR with the phone camera opens another QR page; it must be scanned inside the Bee app after enabling Developer Mode (tap version 5x). Suggestion: say this on the connect page.
**11. Package name collision.** Severity: low. The CLI is `@beeai/cli`; "BeeAI" is also an unrelated IBM project name, so I verified the package owner before installing.
**12. Intermittent ECONNREFUSED from the CLI and HTTP 000 from the public endpoint** during testing (twice in ~5 minutes). Workaround: retries.
**13. `alarm_at` delivery semantics are undocumented.** Completing a todo cancels its alarm; delivery delay is unspecified; one of three test alarms produced no notification.

## Feature requests
- ADBT: Fire OS focus and accessibility verification as an MCP tool (critical for agent-built TV apps).
- Fire TV: a Fire OS emulator image (important).
- Fire OS: fast focused-node query for automation (important).
- Bee: non-TTY login; documented alarm delivery (nice-to-have).

## TalkBack on the emulator (explored Oct 19)
**14. Real screen-reader speech cannot be observed from outside the device.** Severity: medium for tool builders.
- Task: compare my TalkBack-style announcement rules with what the real TalkBack says.
- Steps: the Android TV image ships TalkBack and Google TTS. `settings put secure enabled_accessibility_services com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService` + `accessibility_enabled 1` turns it on; it speaks on D-pad focus (audio-focus requests with USAGE_ASSISTANCE_ACCESSIBILITY appear in logcat).
- Expected: the spoken text in logcat. Actual: only audio-focus and SsbServiceClient warnings; `setprop log.tag.<Tag> VERBOSE` for the TalkBack tags changed nothing.
- Workaround: none within the time box; announcements in the demo come from my rules and are labelled as such.
- Suggestion: a supported way to read screen-reader utterances (a debug broadcast or an accessibility-test API) would let tools verify what users actually hear.
