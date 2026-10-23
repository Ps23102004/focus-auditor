"""fa.adb with subprocess/time mocked. No device, no real adb."""
import shlex
import subprocess
import types

import pytest

from fa import adb as adb_mod
from fa.adb import Adb, AdbError


class Runner:
    """Fake subprocess.run: records argv, replays queued results (CompletedProcess or exception)."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(r, BaseException):
            raise r
        return r


def cp(stdout=b"", stderr=b"", rc=0):
    return subprocess.CompletedProcess([], rc, stdout, stderr)


@pytest.fixture
def mk(monkeypatch):
    def make(*results, **kw):
        r = Runner(*results)
        monkeypatch.setattr(adb_mod, "subprocess", types.SimpleNamespace(run=r, TimeoutExpired=subprocess.TimeoutExpired))
        monkeypatch.delenv("FA_SERIAL", raising=False)
        return Adb(adb_path="ADB", **kw), r
    return make


# ---- run() ------------------------------------------------------------
def test_run_builds_argv_with_serial(mk):
    a, r = mk(cp(b"ok"), serial="emu-5554")
    assert a.run("devices") == "ok"
    assert r.calls[0][0] == ["ADB", "-s", "emu-5554", "devices"]


def test_run_without_serial_omits_dash_s(mk):
    a, r = mk(cp(b"ok"))
    a.run("devices")
    assert r.calls[0][0] == ["ADB", "devices"]


def test_serial_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("FA_SERIAL", "from-env")
    assert Adb(adb_path="ADB").serial == "from-env"
    assert Adb("explicit", adb_path="ADB").serial == "explicit"


def test_run_timeout_becomes_adberror_and_names_deadline(mk):
    a, _ = mk(subprocess.TimeoutExpired("adb", 5), timeout=5)
    with pytest.raises(AdbError, match=r"timeout after 5s"):
        a.run("shell", "x")


def test_run_per_call_timeout_overrides_default(mk):
    a, r = mk(cp(b""), timeout=15)
    a.run("x", timeout=3)
    assert r.calls[0][1]["timeout"] == 3


def test_run_always_passes_a_deadline(mk):
    a, r = mk(cp(b""), timeout=15)
    a.run("x")
    assert r.calls[0][1]["timeout"] == 15


def test_missing_adb_binary_is_adberror(mk):
    a, _ = mk(FileNotFoundError("no such file"))
    with pytest.raises(AdbError, match="cannot run adb"):
        a.run("devices")


def test_nonzero_exit_without_stdout_raises_with_stderr(mk):
    a, _ = mk(cp(b"", b"error: device offline\n", rc=1))
    with pytest.raises(AdbError, match="device offline"):
        a.run("shell", "ls")


def test_nonzero_exit_with_stdout_is_returned_not_raised(mk):
    # documented adb quirk: `shell` returns the remote exit code, output is still valid
    a, _ = mk(cp(b"partial", b"", rc=1))
    assert a.run("shell", "x") == "partial"


def test_stderr_in_error_is_truncated_to_200(mk):
    a, _ = mk(cp(b"", b"E" * 5000, rc=1))
    with pytest.raises(AdbError) as ei:
        a.run("x")
    assert len(str(ei.value)) < 400


def test_invalid_utf8_stdout_does_not_crash(mk):
    a, _ = mk(cp(b"ok\xff\xfe"))
    assert a.run("x").startswith("ok")


def test_binary_mode_returns_bytes(mk):
    a, _ = mk(cp(b"\x89PNG\x00"))
    assert a.run("x", binary=True) == b"\x89PNG\x00"


# ---- shell quoting -----------------------------------------------------
HOSTILE = ["; rm -rf /sdcard", "$(reboot)", "`id`", "a b", "it's", "a\nb", "x && y", "*", "--flag=\"q\"", "$HOME", "|nc h 1", "", "ünï ✓"]


@pytest.mark.parametrize("arg", HOSTILE)
def test_shell_quotes_hostile_argument_into_single_token(mk, arg):
    a, r = mk(cp(b""))
    a.shell("echo", arg)
    argv = r.calls[0][0]
    assert argv[:2] == ["ADB", "shell"]
    # the device shell re-joins argv with spaces and re-parses: the hostile arg must survive as ONE token
    assert shlex.split(" ".join(argv[2:])) == ["echo", arg]


def test_shell_stringifies_non_str_args(mk):
    a, r = mk(cp(b""))
    a.shell("input", "tap", 10, 20)
    assert shlex.split(" ".join(r.calls[0][0][2:])) == ["input", "tap", "10", "20"]


def test_shell_forwards_binary_and_timeout_kwargs(mk):
    a, r = mk(cp(b"x"))
    assert a.shell("cat", "f", binary=True, timeout=2) == b"x"
    assert r.calls[0][1]["timeout"] == 2


# ---- key() ---------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("UP", "KEYCODE_DPAD_UP"), ("DOWN", "KEYCODE_DPAD_DOWN"), ("LEFT", "KEYCODE_DPAD_LEFT"), ("RIGHT", "KEYCODE_DPAD_RIGHT"),
    ("CENTER", "KEYCODE_DPAD_CENTER"), ("BACK", "KEYCODE_BACK"), ("KEYCODE_HOME", "KEYCODE_HOME"), ("KEYCODE_F1", "KEYCODE_F1"),
])
def test_key_maps_names_to_keycodes(mk, name, expected):
    a, r = mk(cp(b""))
    a.key(name)
    assert shlex.split(" ".join(r.calls[0][0][2:])) == ["input", "keyevent", expected]


@pytest.mark.parametrize("bad", [
    "up", "UP; reboot", "KEYCODE_", "KEYCODE_a", "KEYCODE_BACK;id", "KEYCODE_BACK\n", "KEYCODE_BACK ", "KEYCODE_$(id)",
    "UP DOWN", "KEYCODE_É", "../etc", "KEYCODE_UP\x00",
])
def test_key_rejects_invalid_keycodes_without_touching_adb(mk, bad):
    a, r = mk(cp(b""))
    with pytest.raises(AdbError, match="refusing key"):
        a.key(bad)
    assert r.calls == []


def test_key_rejects_empty_name(mk):
    a, r = mk(cp(b""))
    with pytest.raises(AdbError):
        a.key("")
    assert r.calls == []


def test_key_is_never_retried_on_failure(mk):
    a, r = mk(cp(b"", b"boom", rc=1))
    with pytest.raises(AdbError):
        a.key("UP")
    assert len(r.calls) == 1


def test_key_timeout_is_not_retried(mk):
    a, r = mk(subprocess.TimeoutExpired("adb", 1))
    with pytest.raises(AdbError):
        a.key("DOWN")
    assert len(r.calls) == 1


# ---- dump_xml ------------------------------------------------------------
def test_dump_xml_removes_stale_file_before_dumping_and_uses_per_instance_file(mk):
    a, r = mk(cp(b"<?xml version='1.0'?><hierarchy/>"))
    a.dump_xml()
    script = r.calls[0][0][-1]
    f = a.dump_file
    assert script.index(f"rm -f {f}") < script.index("uiautomator dump") < script.index(f"cat {f}")


def test_dump_files_are_unique_per_instance():
    assert Adb(adb_path="x").dump_file != Adb(adb_path="x").dump_file


def test_dump_xml_strips_leading_noise(mk):
    a, _ = mk(cp(b"WARNING: linker noise\n<?xml version='1.0'?><hierarchy/>"))
    assert a.dump_xml().startswith("<?xml")


def test_dump_xml_accepts_hierarchy_without_prolog(mk):
    a, _ = mk(cp(b"junk<hierarchy rotation='0'></hierarchy>"))
    assert a.dump_xml() == "<hierarchy rotation='0'></hierarchy>"


@pytest.mark.parametrize("out", [b"", b"cat: /sdcard/x.xml: No such file or directory\n", b"ERROR: could not get idle state.\n"])
def test_dump_xml_returns_none_when_no_xml_present(mk, out):
    a, _ = mk(cp(out))
    assert a.dump_xml() is None


def test_dump_xml_propagates_device_errors(mk):
    a, _ = mk(cp(b"", b"error: device offline", rc=1))
    with pytest.raises(AdbError):
        a.dump_xml()


def test_dump_xml_returns_truncated_xml_verbatim_for_parser_to_reject(mk):
    a, _ = mk(cp(b"<?xml version='1.0'?><hierarchy><node bounds="))
    from fa.tree import TreeError, parse
    x = a.dump_xml()
    assert x.endswith("bounds=")
    with pytest.raises(TreeError):
        parse(x)


# ---- screenshot ---------------------------------------------------------
def test_screenshot_rejects_non_png_and_writes_nothing(mk, tmp_path):
    a, _ = mk(cp(b"error: closed"))
    p = tmp_path / "s.png"
    with pytest.raises(AdbError, match="PNG"):
        a.screenshot_png(str(p))
    assert not p.exists()


def test_screenshot_writes_png_and_creates_dirs(mk, tmp_path):
    a, r = mk(cp(b"\x89PNG\r\n\x1a\nDATA"))
    p = tmp_path / "deep" / "dir" / "s.png"
    assert a.screenshot_png(str(p)) == str(p)
    assert p.read_bytes() == b"\x89PNG\r\n\x1a\nDATA"
    assert r.calls[0][1]["timeout"] == 30


# ---- cold_start -----------------------------------------------------------
class Clock:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def ns(self):
        return types.SimpleNamespace(time=lambda: self.t, sleep=self.sleep)

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def ready_xml(pkg, focusable=True):
    return f'<hierarchy><node package="{pkg}" focusable="{str(focusable).lower()}" bounds="[0,0][1,1]"/></hierarchy>'


@pytest.fixture
def cold(monkeypatch):
    clk = Clock()
    monkeypatch.setattr(adb_mod, "time", clk.ns())
    return clk


def stub_adb(monkeypatch, dumps):
    """Adb whose shell() is recorded and dump_xml() replays `dumps` (last repeats)."""
    a = Adb(adb_path="ADB")
    a.shells, it = [], iter(dumps)
    last = {}

    def dump():
        try:
            last["v"] = next(it)
        except StopIteration:
            pass
        return last["v"]
    monkeypatch.setattr(a, "shell", lambda *x, **k: a.shells.append(x))
    monkeypatch.setattr(a, "dump_xml", dump)
    return a


def test_cold_start_times_out_when_app_never_ready(cold, monkeypatch):
    a = stub_adb(monkeypatch, [ready_xml("com.launcher")])
    assert a.cold_start("com.app", ".Main", settle=2, ready_timeout=10) is False
    assert cold.t - 1000.0 >= 12  # settle + full ready window actually waited, no early give-up


def test_cold_start_false_when_no_xml_at_all(cold, monkeypatch):
    a = stub_adb(monkeypatch, [None])
    assert a.cold_start("com.app", ".Main", settle=0, ready_timeout=3) is False


def test_cold_start_requires_focusable_node_not_just_package(cold, monkeypatch):
    a = stub_adb(monkeypatch, [ready_xml("com.app", focusable=False)])
    assert a.cold_start("com.app", ".Main", settle=0, ready_timeout=3) is False


def test_cold_start_requires_exact_package_not_prefix(cold, monkeypatch):
    a = stub_adb(monkeypatch, [ready_xml("com.app.other")])
    assert a.cold_start("com.app", ".Main", settle=0, ready_timeout=3) is False


def test_cold_start_returns_true_once_app_appears_after_slow_launch(cold, monkeypatch):
    a = stub_adb(monkeypatch, [None, ready_xml("com.launcher"), ready_xml("com.app")])
    assert a.cold_start("com.app", ".Main", settle=1, ready_timeout=30) is True
    assert cold.t - 1000.0 < 30  # returned as soon as ready, not at the deadline


def test_cold_start_force_stops_then_starts_target_component(cold, monkeypatch):
    a = stub_adb(monkeypatch, [ready_xml("com.app")])
    a.cold_start("com.app", ".Main")
    assert a.shells[0] == ("am", "force-stop", "com.app")
    assert a.shells[1] == ("am", "start", "-S", "-n", "com.app/.Main")


def test_cold_start_does_not_swallow_adb_errors(cold, monkeypatch):
    a = stub_adb(monkeypatch, [None])

    def boom():
        raise AdbError("device offline")
    monkeypatch.setattr(a, "dump_xml", boom)
    with pytest.raises(AdbError):
        a.cold_start("com.app", ".Main", settle=0, ready_timeout=5)


def test_set_animations_off_sets_all_three_scales_to_zero(monkeypatch):
    a = Adb(adb_path="ADB")
    calls = []
    monkeypatch.setattr(a, "shell", lambda *x, **k: calls.append(x))
    a.set_animations_off()
    assert sorted(c[3] for c in calls) == ["animator_duration_scale", "transition_animation_scale", "window_animation_scale"]
    assert all(c[:3] == ("settings", "put", "global") and c[4] == "0" for c in calls)
