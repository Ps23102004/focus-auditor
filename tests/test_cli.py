"""fa.cli: argument errors, exit codes, fixture round-trips. Live crawling is replaced by FakeDevice; no adb."""
import json
import os
import shutil

import pytest

from fa import cli
from fa.adb import AdbError
from fa.crawl import Crawler, FakeDevice

HERE = os.path.dirname(__file__)
BUGGY = os.path.join(HERE, "fixtures", "buggy")
ALL4 = ("UP", "DOWN", "LEFT", "RIGHT")


def clean_dev():
    t = {(n, k): n for n in "AB" for k in ALL4}
    t.update({(None, "DOWN"): "A", ("A", "DOWN"): "B", ("B", "UP"): "A", ("A", "RIGHT"): "B", ("B", "LEFT"): "A"})
    return FakeDevice(t)


def fake_live(dev_factory, **crawl_kw):
    class FakeAdb:
        serial = "ser1"
        shot_error = None

        def shell(self, *a, **k):
            return "Pixel\n"

        def screenshot_png(self, path):
            if self.shot_error:
                raise self.shot_error
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG")
            return path

    def live_crawl(args, out):
        dev = dev_factory()
        g, snaps = Crawler(dev, **crawl_kw).run()
        return FakeAdb(), dev, g, snaps
    return live_crawl, FakeAdb


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)


# ---- argparse errors (exit 2 via SystemExit) ----------------------------------------------
@pytest.mark.parametrize("argv", [
    [],
    ["nonsense"],
    ["audit", "--max-nodes", "many"],
    ["audit", "--deadline", "soon"],
    ["audit", "--bogus-flag"],
    ["record-fixture"],                       # --name is required
    ["announce"],                             # --from-fixture is required
    ["fix", "--agent", "gpt"],                # not in choices
    ["audit", "--max-presses"],               # missing value
])
def test_bad_arguments_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(argv)
    assert ei.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["--help"])
    assert ei.value.code == 0 and "audit" in capsys.readouterr().out


def test_defaults_are_conservative_budgets(monkeypatch):
    import argparse
    seen = {}
    orig = argparse.ArgumentParser.parse_args

    def spy(self, argv=None, ns=None):
        a = orig(self, argv, ns)
        seen.update(vars(a))
        a.fn = lambda _a: 0
        return a
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", spy)
    assert cli.main(["audit"]) == 0
    assert (seen["max_nodes"], seen["max_presses"], seen["deadline"], seen["entry"]) == (40, 400, 1500, "DOWN")


# ---- audit from fixture: exit codes ---------------------------------------------------------
def test_audit_from_buggy_fixture_fails_with_exit_1_and_writes_report(tmp_path, capsys):
    rc = cli.main(["audit", "--from-fixture", BUGGY, "--out", str(tmp_path / "o")])
    assert rc == 1
    r = json.load(open(tmp_path / "o" / "report.json"))
    assert r["verdict"] == "fail" and r["meta"]["device"] == "fixture"
    assert (tmp_path / "o" / "focus_graph.json").exists()
    out = capsys.readouterr().out
    assert "verdict=fail" in out and "TRAP" in out


def test_audit_fixture_copies_screenshot_when_present(tmp_path):
    cli.main(["audit", "--from-fixture", BUGGY, "--out", str(tmp_path)])
    assert (tmp_path / "screen.png").exists()
    assert json.load(open(tmp_path / "report.json"))["screenshot"] == "screen.png"


def test_audit_fixture_without_screenshot_reports_none(tmp_path):
    fx = tmp_path / "fx"
    shutil.copytree(BUGGY, fx)
    os.remove(fx / "screen.png")
    cli.main(["audit", "--from-fixture", str(fx), "--out", str(tmp_path / "o")])
    assert json.load(open(tmp_path / "o" / "report.json"))["screenshot"] is None


def make_fixture(tmp_path, reasons):
    """Round-trip a clean crawl through save_fixture so the fixture is a real one, then inject coverage reasons."""
    g, snaps = Crawler(clean_dev()).run()
    g.coverage["inconclusive_reasons"] = list(reasons)
    d = tmp_path / "fx"
    cli.save_fixture(g, snaps, str(d))
    return str(d)


def test_audit_clean_fixture_exits_0_pass(tmp_path):
    assert cli.main(["audit", "--from-fixture", make_fixture(tmp_path, []), "--out", str(tmp_path / "o")]) == 0
    assert json.load(open(tmp_path / "o" / "report.json"))["verdict"] == "pass"


def test_audit_inconclusive_fixture_exits_2_never_0(tmp_path, capsys):
    rc = cli.main(["audit", "--from-fixture", make_fixture(tmp_path, ["budget_exhausted: max_presses"]), "--out", str(tmp_path / "o")])
    assert rc == 2
    assert "INCONCLUSIVE: budget_exhausted: max_presses" in capsys.readouterr().out


def test_audit_missing_fixture_dir_raises_filenotfound_not_green(tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.main(["audit", "--from-fixture", str(tmp_path / "nope"), "--out", str(tmp_path / "o")])


def test_audit_fixture_with_corrupt_snapshot_raises_instead_of_passing(tmp_path):
    fx = make_fixture(tmp_path, [])
    p = os.path.join(fx, "snapshots", sorted(os.listdir(os.path.join(fx, "snapshots")))[0])
    open(p, "w").write("<hierarchy><node")
    with pytest.raises(Exception) as ei:
        cli.main(["audit", "--from-fixture", fx, "--out", str(tmp_path / "o")])
    assert type(ei.value).__name__ == "TreeError"


def test_audit_fixture_with_corrupt_graph_json_raises(tmp_path):
    fx = make_fixture(tmp_path, [])
    open(os.path.join(fx, "focus_graph.json"), "w").write("{not json")
    with pytest.raises(json.JSONDecodeError):
        cli.main(["audit", "--from-fixture", fx, "--out", str(tmp_path / "o")])


def test_audit_creates_missing_out_dir(tmp_path):
    out = tmp_path / "a" / "b" / "c"
    cli.main(["audit", "--from-fixture", BUGGY, "--out", str(out)])
    assert (out / "report.json").exists()


# ---- live path (crawl replaced) -------------------------------------------------------------------
def test_live_audit_clean_app_passes_and_saves_fixture(tmp_path, monkeypatch, capsys):
    live, _ = fake_live(clean_dev)
    monkeypatch.setattr(cli, "live_crawl", live)
    rc = cli.main(["audit", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "screen.png").exists() and (tmp_path / "focus_graph.json").exists()
    assert os.listdir(tmp_path / "snapshots")
    r = json.load(open(tmp_path / "report.json"))
    assert r["meta"]["device"] == "Pixel ser1" and r["screenshot"] == "screen.png"


def test_live_audit_exhausted_budget_exits_2(tmp_path, monkeypatch):
    live, _ = fake_live(clean_dev, max_presses=2)
    monkeypatch.setattr(cli, "live_crawl", live)
    assert cli.main(["audit", "--out", str(tmp_path)]) == 2


def test_live_audit_screenshot_failure_downgrades_pass_to_inconclusive(tmp_path, monkeypatch):
    live, FakeAdb = fake_live(clean_dev)
    FakeAdb.shot_error = AdbError("screencap did not return a PNG")
    monkeypatch.setattr(cli, "live_crawl", live)
    rc = cli.main(["audit", "--out", str(tmp_path)])
    r = json.load(open(tmp_path / "report.json"))
    assert rc == 2 and any(x.startswith("screenshot_failed") for x in r["coverage"]["inconclusive_reasons"])
    assert r["screenshot"] is None


def test_live_audit_no_device_focus_exits_2(tmp_path, monkeypatch):
    live, _ = fake_live(lambda: FakeDevice({("A", "DOWN"): "A"}, names=["A"]))
    monkeypatch.setattr(cli, "live_crawl", live)
    assert cli.main(["audit", "--out", str(tmp_path)]) == 2


def test_live_crawl_turns_animations_off_and_passes_cli_budgets(monkeypatch):
    calls = {}

    class A:
        def __init__(self, serial):
            calls["serial"] = serial

        def set_animations_off(self):
            calls["anim"] = True

    class C:
        def __init__(self, dev, **kw):
            calls["crawler"] = kw

        def run(self):
            return "g", {}

    monkeypatch.setattr(cli, "Adb", A)
    monkeypatch.setattr(cli, "Crawler", C)
    monkeypatch.setattr(cli, "LiveDevice", lambda adb, pkg, act: (pkg, act))
    import argparse
    ns = argparse.Namespace(serial="S9", pkg="p.k", activity=".Act", entry="DOWN,RIGHT", max_nodes=7, max_presses=77, deadline=5.0, verbose=False)
    adb, dev, g, s = cli.live_crawl(ns, "out")
    assert calls["serial"] == "S9" and calls["anim"] is True and dev == ("p.k", ".Act")
    assert calls["crawler"]["entry"] == ["DOWN", "RIGHT"]
    assert (calls["crawler"]["max_nodes"], calls["crawler"]["max_presses"], calls["crawler"]["deadline_s"]) == (7, 77, 5.0)
    assert calls["crawler"]["log"] is None


# ---- record-fixture ---------------------------------------------------------------------------------
def test_record_fixture_writes_named_dir_and_roundtrips(tmp_path, monkeypatch, capsys):
    live, _ = fake_live(clean_dev)
    monkeypatch.setattr(cli, "live_crawl", live)
    assert cli.main(["record-fixture", "--name", "mine", "--out", str(tmp_path)]) == 0
    d = tmp_path / "mine"
    assert (d / "focus_graph.json").exists() and (d / "screen.png").exists()
    g, snaps = cli.load_fixture(str(d))
    assert set(g.nodes) == set(snaps) and len(g.nodes) == 2
    assert "fixture saved" in capsys.readouterr().out


def test_record_fixture_survives_screenshot_failure(tmp_path, monkeypatch, capsys):
    live, FakeAdb = fake_live(clean_dev)
    FakeAdb.shot_error = AdbError("nope")
    monkeypatch.setattr(cli, "live_crawl", live)
    assert cli.main(["record-fixture", "--name", "x", "--out", str(tmp_path)]) == 0
    assert "screenshot failed" in capsys.readouterr().err
    assert not (tmp_path / "x" / "screen.png").exists()


# ---- analyze / fixtures --------------------------------------------------------------------------------------
def test_analyze_assigns_test_ids_from_finding_ids():
    g, snaps = cli.load_fixture(BUGGY)
    fs = cli.analyze(g, snaps)
    assert fs and all(f.test_id == f"tests_generated/test_{f.id}.py" for f in fs)


def test_analyze_empty_inputs_gives_no_findings():
    from fa.crawl import FocusGraph
    assert cli.analyze(FocusGraph(), {}) == []


def test_save_then_load_fixture_preserves_graph_and_raw_xml(tmp_path):
    g, snaps = Crawler(clean_dev()).run()
    cli.save_fixture(g, snaps, str(tmp_path))
    g2, s2 = cli.load_fixture(str(tmp_path))
    assert g2.edges == g.edges and g2.entry == g.entry
    assert {k: v.raw for k, v in s2.items()} == {k: v.raw for k, v in snaps.items()}


def test_load_fixture_ignores_non_xml_files_in_snapshots(tmp_path):
    g, snaps = Crawler(clean_dev()).run()
    cli.save_fixture(g, snaps, str(tmp_path))
    open(tmp_path / "snapshots" / "notes.txt", "w").write("hi")
    _, s2 = cli.load_fixture(str(tmp_path))
    assert set(s2) == set(snaps)


# ---- tests / announce subcommands --------------------------------------------------------------------------------
def test_tests_command_missing_report_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.main(["tests", "--report", str(tmp_path / "no.json"), "--out", str(tmp_path / "t")])


def test_tests_command_invalid_report_json_raises(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        cli.main(["tests", "--report", str(p), "--out", str(tmp_path / "t")])


def test_tests_command_generates_files_for_buggy_report(tmp_path, capsys):
    rc = cli.main(["tests", "--report", os.path.join(BUGGY, "report.json"), "--out", str(tmp_path / "t")])
    assert rc == 0
    files = os.listdir(tmp_path / "t")
    assert files and all(f.startswith("test_") for f in files)
    assert f"{len(files)} test file(s) written" in capsys.readouterr().out


def test_announce_prints_witness_and_returns_0(capsys):
    assert cli.main(["announce", "--from-fixture", BUGGY]) == 0
    assert capsys.readouterr().out.strip()


def test_announce_missing_fixture_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cli.main(["announce", "--from-fixture", str(tmp_path / "x")])


def test_announce_speak_unavailable_warns_once(monkeypatch, capsys):
    from fa import announce
    monkeypatch.setattr(announce, "speak", lambda t: False)
    cli.main(["announce", "--from-fixture", BUGGY, "--speak"])
    assert capsys.readouterr().err.count("`say` not available") == 1


# ---- fix exit code -------------------------------------------------------------------------------------------------------
def test_fix_exit_code_is_failure_when_the_post_fix_tests_fail(monkeypatch):
    from fa import fixloop

    def steps(*pairs):
        return lambda *a, **k: {"steps": [{"step": s, "code": c} for s, c in pairs]}
    monkeypatch.setattr(fixloop, "fix", steps(("agent", 0), ("build", 0), ("tests", 1)))
    assert cli.main(["fix"]) == 1  # a fix whose frozen tests still fail is not a fix
    monkeypatch.setattr(fixloop, "fix", steps(("agent", 0), ("build", 1), ("tests", 0)))
    assert cli.main(["fix"]) == 1
    monkeypatch.setattr(fixloop, "fix", steps(("agent", 0), ("build", 0), ("tests", 0)))
    assert cli.main(["fix"]) == 0


def test_fix_with_no_steps_is_failure(monkeypatch):
    from fa import fixloop
    monkeypatch.setattr(fixloop, "fix", lambda *a, **k: {"steps": []})
    assert cli.main(["fix"]) == 1
