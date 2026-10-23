"""Thin adb wrapper. Every call has a deadline. Keypresses are never retried."""
import re, shlex
import itertools, os, subprocess, time

ADB_PATH = os.environ.get("FA_ADB", "/opt/homebrew/share/android-commandlinetools/platform-tools/adb")
_counter = itertools.count()


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, serial=None, timeout=15, adb_path=ADB_PATH):
        self.serial = serial or os.environ.get("FA_SERIAL")
        self.timeout = timeout
        self.adb_path = adb_path
        # unique device-side file per instance so concurrent runs never read each other's dumps
        self.dump_file = f"/sdcard/fa_{os.getpid()}_{next(_counter)}.xml"

    def run(self, *args, timeout=None, binary=False):
        cmd = [self.adb_path] + (["-s", self.serial] if self.serial else []) + list(args)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"timeout after {timeout or self.timeout}s: {' '.join(args)[:80]}") from e
        except OSError as e:
            raise AdbError(f"cannot run adb: {e}") from e
        if p.returncode != 0 and not p.stdout:
            err = p.stderr.decode(errors="replace").strip()
            raise AdbError(f"adb {' '.join(args)[:80]} failed: {err[:200]}")
        return p.stdout if binary else p.stdout.decode(errors="replace")

    def shell(self, *args, **kw):
        # `adb shell a b c` joins argv into ONE string run by the device shell, so quote each argument.
        return self.run("shell", *[shlex.quote(str(a)) for a in args], **kw)

    def key(self, name):
        name = name if name.startswith("KEYCODE_") else {"CENTER": "KEYCODE_DPAD_CENTER", "BACK": "KEYCODE_BACK"}.get(name, f"KEYCODE_DPAD_{name}")
        if name in ("KEYCODE_DPAD_", "KEYCODE_") or not re.fullmatch(r"KEYCODE_[A-Z0-9_]+", name):
            raise AdbError(f"refusing key {name!r}")
        self.shell("input", "keyevent", name)

    def dump_xml(self):
        """One round trip. Stale file removed first so a failed dump can never return an old screen."""
        f = self.dump_file
        try:
            out = self.run("exec-out", "sh", "-c", f"rm -f {f}; uiautomator dump {f} >/dev/null 2>&1; cat {f}")
        except AdbError:
            raise
        i = out.find("<?xml")
        if i < 0:
            i = out.find("<hierarchy")
        return out[i:] if i >= 0 else None

    def screenshot_png(self, path):
        data = self.run("exec-out", "screencap", "-p", binary=True, timeout=30)
        if not data.startswith(b"\x89PNG"):
            raise AdbError("screencap did not return a PNG")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def cold_start(self, pkg, activity, settle=3.5, ready_timeout=30.0):
        """Force-stop, launch, then wait until the app's UI is actually on screen with focusable nodes.
        A fixed sleep is not enough right after `adb install` (first launch is much slower)."""
        self.shell("am", "force-stop", pkg)
        self.shell("am", "start", "-S", "-n", f"{pkg}/{activity}")
        time.sleep(settle)
        deadline = time.time() + ready_timeout
        while time.time() < deadline:
            xml = self.dump_xml()
            if xml and f'package="{pkg}"' in xml and 'focusable="true"' in xml:
                return True
            time.sleep(1.0)
        return False

    def set_animations_off(self):
        for k in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            self.shell("settings", "put", "global", k, "0")
