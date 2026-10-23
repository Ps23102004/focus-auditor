import pytest
from hypothesis import given, settings, strategies as st
from fa import announce
from fa.tree import parse
from tests.helpers import node, screen


def snap_of(*kids):
    return parse(screen(*kids))


def focus_nodes(s):
    return [n for n in s.nodes if n.focusable]


def say(s, i=0):
    return announce.announce(s, focus_nodes(s)[i])


def test_unlabelled_icon_button():
    assert say(snap_of(node())) == "unlabelled, button"


def test_text_wins_then_desc():
    assert say(snap_of(node(text="Play", desc="x"))) == "Play, button"
    assert say(snap_of(node(desc="Search"))) == "Search, button"


@pytest.mark.parametrize("cls,role", [("android.widget.EditText", "edit box"), ("android.widget.CheckBox", "check box"),
                                      ("android.widget.Switch", "switch"), ("android.widget.ImageView", "image"),
                                      ("android.widget.SeekBar", "slider"), ("android.widget.Spinner", "drop-down list")])
def test_roles(cls, role):
    assert say(snap_of(node(cls=cls, text="T"))) == f"T, {role}"


def test_unknown_class_focusable_is_button():
    assert say(snap_of(node(cls="com.x.Weird", text="T"))).endswith("button")


def test_states_appended():
    s = parse(screen('<node class="android.widget.CheckBox" text="Dark" content-desc="" focusable="true" focused="false" '
                     'clickable="true" checked="true" selected="true" enabled="false" bounds="[0,0][10,10]" package="a.b"/>'))
    assert say(s) == "Dark, check box, checked, selected, disabled"


def test_list_position_in_reading_order_not_tree_order():
    kids = [node(bounds=(300, 0, 400, 100), text="C"), node(bounds=(0, 0, 100, 100), text="A"), node(bounds=(150, 0, 250, 100), text="B")]
    s = snap_of(*kids)
    by_text = {n.text: n for n in focus_nodes(s)}
    assert announce.announce(s, by_text["A"]).endswith("1 of 3")
    assert announce.announce(s, by_text["C"]).endswith("3 of 3")


def test_fewer_than_three_siblings_is_not_a_list():
    s = snap_of(node(text="A"), node(bounds=(150, 0, 250, 100), text="B"))
    assert "of" not in say(s)


@given(st.text(max_size=200), st.text(max_size=200))
@settings(max_examples=60, deadline=None)
def test_never_raises_on_odd_labels(text, desc):
    esc = lambda t: t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    try:
        s = snap_of(node(text=esc(text), desc=esc(desc)))
    except Exception:
        return  # XML-illegal control chars are rejected at parse time, not here
    out = say(s)
    assert isinstance(out, str) and out


def test_long_unicode_rtl_label_passes_through_verbatim():
    label = "بحث " * 50 + "検索"
    assert say(snap_of(node(text=label))).startswith(label)


def test_announce_all_covers_every_focusable():
    s = snap_of(node(text="A"), node(bounds=(150, 0, 250, 100), text="B"), node(bounds=(0, 0, 0, 0), text="hidden"))
    assert [t for _, t in announce.announce_all(s)] == ["A, button", "B, button"]


def test_speak_sends_text_on_stdin_never_as_an_option(monkeypatch):
    calls = {}
    monkeypatch.setattr(announce.shutil, "which", lambda x: "/usr/bin/say")
    monkeypatch.setattr(announce.subprocess, "run", lambda cmd, **kw: calls.update(cmd=cmd, **kw))
    assert announce.speak("-o /tmp/evil") is True
    assert calls["cmd"] == ["/usr/bin/say", "-f", "-"] and calls["input"] == b"-o /tmp/evil"


def test_speak_without_say_binary_is_a_noop(monkeypatch):
    monkeypatch.setattr(announce.shutil, "which", lambda x: None)
    assert announce.speak("hi") is False
