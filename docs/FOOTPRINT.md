# Footprint: what runs where, and what it costs

Focus Auditor has two halves. Only one of them ever touches a Fire TV.

| Piece | Runs on | Memory | Notes |
|---|---|---|---|
| Auditor (`python -m fa`), frozen tests, fix loop | Developer machine or CI | tens of MB | Talks to the TV over adb. |
| Gemma 4 `e4b-it-qat` (icon-name suggestions) | Developer machine only | 6.1 GB on disk | Never on the TV. Optional: the audit works without it. |
| Companion app (`com.focusauditor.tv`) | Fire TV / Android TV | about 150 MB PSS total | Optional viewer. See below. |

## Companion app, measured (Android TV emulator, 2 GB RAM, API 31, Oct 19 2026)
`dumpsys meminfo` PSS: app 77 MB + WebView renderer 64 MB + WebView service 8 MB, about 150 MB while showing the report.
The same emulator had 745 MB free with the app open.

## Fire TV sticks (public spec sites, not Amazon's own pages)
Fire TV Stick HD / Lite class: 1 GB RAM. Stick 4K / 4K Max class: 2 GB RAM.
150 MB is roughly 15% of a 1 GB stick, so the companion app is a viewer you open on demand, not something left running.
The audit itself adds no resident process on the TV: it uses `input keyevent` and `uiautomator dump`, which start and exit per call.
We have not measured on a physical stick (none available); the emulator is a proxy.

## Rules we keep
- No model runs on the TV. Ever.
- The companion app does no audit work and stays closed unless the user opens it.
- Any new on-device component needs a measured PSS number in this file before it ships.
