import os

from fa import announce
from fa.cli import load_fixture
from fa.tree import parse

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "buggy")


def N(cls, text="", desc="", b="[0,0][10,10]", foc=True, extra="", kids=""):
    return (f'<node class="{cls}" package="p" text="{text}" content-desc="{desc}" focusable="{str(foc).lower()}" '
            f'focused="false" clickable="false" {extra} bounds="{b}">{kids}</node>')


def snap(*kids):
    return parse('<hierarchy>' + N("android.view.ViewGroup", foc=False, b="[0,0][100,100]", kids="".join(kids)) + "</hierarchy>")


def test_label_role_position_in_reading_order():
    # tree order is reversed on purpose: position follows visual order
    s = snap(*[N("android.view.View", text=f"Item {i}", b=f"[{i * 10},0][{i * 10 + 9},9]") for i in (3, 2, 1)])
    out = dict(announce.announce_all(s))
    assert sorted(out.values()) == ["Item 1, button, 1 of 3", "Item 2, button, 2 of 3", "Item 3, button, 3 of 3"]


def test_unlabelled_and_no_position_for_short_groups():
    s = snap(N("android.view.View"), N("android.view.View", text="x"))
    assert [t for _, t in announce.announce_all(s)] == ["unlabelled, button", "x, button"]


def test_state_and_role_from_class():
    s = snap(N("android.widget.CheckBox", text="Subs", extra='checked="true" selected="true" enabled="false"'))
    assert announce.announce_all(s)[0][1] == "Subs, check box, checked, selected, disabled"


def test_content_desc_and_descendant_label():
    s = snap(N("android.view.View", desc="Search"), N("android.view.View", foc=True, kids=N("android.widget.TextView", text="Inner", foc=False)))
    assert [t for _, t in announce.announce_all(s)] == ["Search, button", "Inner, button"]


def test_fixture_witness_sequence_and_source():
    graph, snaps = load_fixture(FIX)
    seq = announce.witness_sequence(graph, snaps)
    assert seq and announce.SOURCE == "rules"
    assert any(t.startswith("unlabelled, button") for _, _, t in seq)  # the buggy fixture has unnamed controls
    assert all(isinstance(t, str) and t for _, _, t in seq)


def test_cli_announce_prints_sequence(capsys):
    from fa.cli import main
    assert main(["announce", "--from-fixture", FIX]) == 0
    out = capsys.readouterr().out
    assert "[rules]" in out and "button" in out


def test_speak_passes_text_on_stdin_never_as_argument(monkeypatch):
    from fa import announce
    seen = {}
    monkeypatch.setattr(announce.shutil, "which", lambda name: "/usr/bin/say")

    def fake_run(cmd, input=None, **kw):
        seen["cmd"], seen["input"] = cmd, input
    monkeypatch.setattr(announce.subprocess, "run", fake_run)
    assert announce.speak("-o /tmp/pwned.aiff hello")
    assert seen["cmd"] == ["/usr/bin/say", "-f", "-"]
    assert seen["input"] == b"-o /tmp/pwned.aiff hello"
