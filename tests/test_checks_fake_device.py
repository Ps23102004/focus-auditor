"""The frozen-test runtime (fa.testgen.check) against a fake TV: fixed passes, still-broken fails, removed control fails."""
import pytest
from fa import testgen
from tests.helpers import FakeDev, node, screen

BASE = {"finding_id": "abcdef1234", "node_id": "n1", "pkg": "a.b.c", "activity": ".Main", "keys": ["RIGHT"]}


def label_data(bounds=(200, 100, 300, 200)):
    return dict(BASE, kind="MISSING_LABEL", bounds=list(bounds), target_geo=["android.widget.Button", [v // 8 for v in bounds]])


def one_button(**kw):
    return FakeDev({"s0": screen(node(bounds=(0, 0, 100, 100), text="Play", focused=True), node(**kw)), "s1": screen(
        node(bounds=(0, 0, 100, 100), text="Play"), node(focused=True, **kw))}, {("s0", "RIGHT"): "s1"})


def test_label_passes_when_named():
    testgen.check(label_data(), one_button(bounds=(200, 100, 300, 200), text="Search"))


def test_label_passes_with_content_desc_only():
    testgen.check(label_data(), one_button(bounds=(200, 100, 300, 200), desc="Search"))


def test_label_fails_when_still_unnamed():
    with pytest.raises(AssertionError, match="still exposes no accessible name"):
        testgen.check(label_data(), one_button(bounds=(200, 100, 300, 200)))


def test_label_fails_when_control_deleted_not_fixed():
    dev = FakeDev({"s0": screen(node(bounds=(0, 0, 100, 100), text="Play", focused=True)),
                   "s1": screen(node(bounds=(0, 0, 100, 100), text="Play"))}, {("s0", "RIGHT"): "s1"})
    with pytest.raises(AssertionError, match="removed or moved"):
        testgen.check(label_data(), dev)


def test_label_fails_when_control_moved_far():
    with pytest.raises(AssertionError, match="removed or moved"):
        testgen.check(label_data(), one_button(bounds=(900, 500, 1000, 600), text="Search"))


def test_label_tolerates_small_layout_shift_within_grid():
    # bounds are bucketed in 8 px cells: a shift inside the cell still matches
    testgen.check(label_data(), one_button(bounds=(201, 101, 301, 201), text="Search"))


def test_label_named_by_child_text_counts():
    child = node("android.widget.TextView", (210, 110, 290, 190), text="Search", focusable=False, clickable=False)
    dev = FakeDev({"s0": screen(node(bounds=(200, 100, 300, 200), children=[child]))}, {})
    testgen.check(dict(label_data(), keys=[]), dev)


def test_unreadable_screen_is_a_failure_not_a_pass():
    class Broken(FakeDev):
        def read(self):
            return None
    with pytest.raises(AssertionError, match="could not read"):
        testgen.check(label_data(), Broken({"s0": ""}, {}))


def dup_data():
    return dict(BASE, kind="DUPLICATE_LABEL", bounds=[0, 0, 100, 100], label="Movie", min_group=3,
                target_geo=["android.widget.Button", [0, 0, 12, 12]], keys=[])


def cards(names):
    return FakeDev({"s0": screen(*[node(bounds=(i * 150, 0, i * 150 + 100, 100), text=t) for i, t in enumerate(names)])}, {})


def test_dup_fails_while_group_remains():
    with pytest.raises(AssertionError, match="still share the name"):
        testgen.check(dup_data(), cards(["Movie"] * 5))


def test_dup_passes_when_renamed():
    testgen.check(dup_data(), cards(["Movie 1", "Movie 2", "Movie 3"]))


def test_dup_passes_when_below_group_threshold():
    testgen.check(dup_data(), cards(["Movie", "Movie", "Other"]))


def test_dup_fails_if_the_cards_vanished():
    with pytest.raises(AssertionError, match="removed or moved"):
        testgen.check(dict(dup_data(), target_geo=["android.widget.Button", [500, 500, 600, 600]]), cards(["A", "B", "C"]))


# ---- trap ----
A, B, C = (0, 0, 100, 100), (150, 0, 250, 100), (300, 0, 400, 100)


def geo(b):
    return ["android.widget.Button", [v // 8 for v in b]]


def trap_data():
    return dict(BASE, kind="TRAP", bounds=[0, 0, 250, 100], keys=[], target_geo=geo(A), entry_geo=geo(A),
                region_geo=[geo(A), geo(B)], edges_geo=[[geo(A), "RIGHT", geo(B)], [geo(B), "LEFT", geo(A)]])


def two_btn_screens(focus):
    return screen(*[node(bounds=b, text=t, focused=(t == focus)) for b, t in ((A, "A"), (B, "B"), (C, "C"))])


def test_trap_fails_when_every_key_stays_inside():
    S = {k: two_btn_screens(k) for k in "ABC"}
    nav = {("A", "RIGHT"): "B", ("B", "LEFT"): "A"}  # UP/DOWN/LEFT from A and B and RIGHT from B stay put
    dev = FakeDev(S, nav, start="A")
    with pytest.raises(AssertionError, match="never leaves"):
        testgen.check(trap_data(), dev)


def test_trap_passes_when_a_key_escapes():
    S = {k: two_btn_screens(k) for k in "ABC"}
    nav = {("A", "RIGHT"): "B", ("B", "LEFT"): "A", ("B", "RIGHT"): "C"}
    testgen.check(trap_data(), FakeDev(S, nav, start="A"))


def test_trap_fails_when_entry_not_reached():
    S = {k: two_btn_screens(k) for k in "ABC"}
    with pytest.raises(AssertionError, match="no longer reaches"):
        testgen.check(dict(trap_data(), keys=["DOWN"]), FakeDev(S, {}, start="C"))


def test_trap_two_focused_nodes_is_inconclusive_failure():
    bad = screen(node(bounds=A, text="A", focused=True), node(bounds=B, text="B", focused=True))
    with pytest.raises(AssertionError):
        testgen.check(trap_data(), FakeDev({"s0": bad}, {}))


# ---- the runtime refuses edited generated files ----
@pytest.mark.parametrize("bad", [{"pkg": "a;rm -rf /"}, {"activity": ".M ain"}, {"keys": ["UP", "ENTER; reboot"]},
                                 {"pkg": "x"}, {"activity": ""}, {"keys": ["HOME"]}])
def test_check_rejects_tampered_target(bad):
    with pytest.raises(ValueError, match="refusing"):
        testgen.check(dict(label_data(), **bad), one_button(bounds=(200, 100, 300, 200), text="x"))


# ---- holes found by an independent judge (Astra, Oct 19): all three used to PASS ----
def test_named_but_not_focusable_control_does_not_pass():
    dev = FakeDev({"s0": screen(node(bounds=(200, 100, 300, 200), text="Search", focusable=False, clickable=False))}, {})
    with pytest.raises(AssertionError, match="no longer focusable"):
        testgen.check(dict(label_data(), keys=[]), dev)


def test_dup_renamed_uniformly_to_a_new_shared_name_does_not_pass():
    with pytest.raises(AssertionError, match="renamed to 'Item'"):
        testgen.check(dup_data(), cards(["Item"] * 5))


def test_dup_target_made_unfocusable_does_not_pass():
    dev = FakeDev({"s0": screen(*[node(bounds=(i * 150, 0, i * 150 + 100, 100), text=f"M{i}", focusable=(i != 0)) for i in range(4)])}, {})
    with pytest.raises(AssertionError, match="no longer focusable"):
        testgen.check(dup_data(), dev)


def test_dup_group_with_every_name_erased_does_not_pass():
    """Found by an independent judge: blanking all labels made the frozen test print success."""
    with pytest.raises(AssertionError, match="no accessible name at all"):
        testgen.check(dup_data(), cards([""] * 5))


# ---- round 4: leaving or crashing the app is never a pass ----
class LauncherAfter(FakeDev):
    """Any press lands on a launcher screen (package other.app) with one focused, named tile."""
    def read(self):
        from fa.tree import parse
        if self.presses:
            return parse(screen(node(bounds=(0, 0, 400, 300), text="Home", focused=True)).replace('package="a.b.c"', 'package="other.app"'))
        return super().read()


def test_trap_test_does_not_pass_when_a_key_exits_to_the_launcher():
    S = {k: two_btn_screens(k) for k in "ABC"}
    with pytest.raises(AssertionError, match="no longer in front"):
        testgen.check(trap_data(), LauncherAfter(S, {("A", "RIGHT"): "B"}, start="A"))


def test_label_test_does_not_pass_when_the_app_is_gone():
    dev = LauncherAfter({"s0": screen(node(bounds=(200, 100, 300, 200), text="Search", focused=True))}, {})
    with pytest.raises(AssertionError, match="no longer in front"):
        testgen.check(label_data(), dev)


def test_dup_test_does_not_pass_when_the_app_is_gone():
    dev = LauncherAfter({"s0": cards(["A", "B", "C"]).screens["s0"]}, {})
    with pytest.raises(AssertionError, match="no longer in front"):
        testgen.check(dict(dup_data(), keys=["RIGHT"]), dev)
