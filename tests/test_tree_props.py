"""Property tests (hypothesis) and edge cases for fa.tree.parse / node_id."""
import re

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from fa.tree import Snapshot, TreeError, effective_label, node_id, parse

SET = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])

VALID = ('<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
         '<node index="0" text="" class="android.widget.FrameLayout" package="p" content-desc="" focusable="false" '
         'focused="false" clickable="false" bounds="[0,0][1920,1080]">'
         '<node index="0" text="Play" class="android.widget.Button" package="p" content-desc="" focusable="true" '
         'focused="true" clickable="true" bounds="[10,10][110,60]"/>'
         '<node index="1" text="" class="android.widget.ImageView" package="p" content-desc="Settings" focusable="true" '
         'focused="false" clickable="true" bounds="[120,10][220,60]"/></node></hierarchy>')


def xml_for(bounds_list):
    rows = "".join(f'<node class="V" package="p" text="" content-desc="" focusable="true" focused="false" '
                   f'clickable="false" bounds="[{l},{t}][{r},{b}]"/>' for l, t, r, b in bounds_list)
    return f'<hierarchy><node class="R" package="p" bounds="[0,0][1,1]">{rows}</node></hierarchy>'


def parses_or_treeerror(text):
    try:
        return parse(text)
    except TreeError:
        return None


# ---- never raises anything but TreeError --------------------------------------
@SET
@given(st.text())
def test_parse_arbitrary_text_only_raises_treeerror(t):
    parses_or_treeerror(t)


@SET
@given(st.data())
def test_parse_garbled_valid_xml_only_raises_treeerror(data):
    s = VALID
    for _ in range(data.draw(st.integers(1, 6))):
        i = data.draw(st.integers(0, len(s)))
        op = data.draw(st.sampled_from(["del", "ins", "trunc", "dup"]))
        if op == "del":
            s = s[:i] + s[i + data.draw(st.integers(1, 20)):]
        elif op == "ins":
            s = s[:i] + data.draw(st.text(max_size=12)) + s[i:]
        elif op == "trunc":
            s = s[:i]
        else:
            s = s[:i] + s[i:i + 30] + s[i:]
    parses_or_treeerror(s)


@SET
@given(st.binary(max_size=400))
def test_parse_decoded_garbage_bytes_only_raises_treeerror(b):
    parses_or_treeerror(b.decode("utf-8", errors="replace"))


@SET
@given(st.lists(st.sampled_from(["<", ">", "/", "node", " ", '"', "=", "bounds", "[0,0][1,1]", "hierarchy", "<node ", "/>", "&", ";", "<!", "--"]), max_size=40))
def test_parse_tag_soup_only_raises_treeerror(parts):
    parses_or_treeerror("".join(parts))


def test_parse_none_and_whitespace_are_treeerror():
    for bad in (None, "", "   \n\t "):
        with pytest.raises(TreeError):
            parse(bad)


def test_valid_dump_survives_parse():
    s = parse(VALID)
    assert [n.cls for n in s.nodes] == ["android.widget.FrameLayout", "android.widget.Button", "android.widget.ImageView"]
    assert s.focused().text == "Play"


def test_parse_huge_bounds_number_is_treeerror():
    big = "9" * 5000
    with pytest.raises(TreeError):
        parse(f'<hierarchy><node class="a" bounds="[0,0][{big},1]"/></hierarchy>')


def test_parse_deep_nesting_is_treeerror_not_recursionerror():
    depth = 3000
    xml = "<hierarchy>" + '<node class="a" bounds="[0,0][1,1]">' * depth + "</node>" * depth + "</hierarchy>"
    try:
        parse(xml)
    except TreeError:
        pass


@pytest.mark.parametrize("doc", [
    '<!DOCTYPE hierarchy><hierarchy><node bounds="[0,0][1,1]"/></hierarchy>',
    '<!doctype hierarchy><hierarchy><node bounds="[0,0][1,1]"/></hierarchy>',
    '<! DOCTYPE hierarchy><hierarchy/>',
    '<?xml version="1.0"?><!ENTITY x "y"><hierarchy/>',
    '<!   entity x "y"><hierarchy/>',
])
def test_dtd_and_entity_declarations_rejected_in_any_case(doc):
    with pytest.raises(TreeError, match="DTD"):
        parse(doc)


def test_billion_laughs_never_expands():
    bomb = ('<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            '<hierarchy><node class="&b;" bounds="[0,0][1,1]"/></hierarchy>')
    with pytest.raises(TreeError):
        parse(bomb)


# ---- bounds ---------------------------------------------------------------------
coord = st.integers(-50000, 50000)


@SET
@given(st.lists(st.tuples(coord, coord, coord, coord), min_size=1, max_size=8))
def test_bounds_roundtrip_exactly(bl):
    s = parse(xml_for(bl))
    assert [n.bounds for n in s.nodes[1:]] == [tuple(b) for b in bl]
    assert [n.size for n in s.nodes[1:]] == [(r - l, b - t) for l, t, r, b in bl]


@pytest.mark.parametrize("b", ["", "[0,0]", "[0,0][1]", "[a,b][c,d]", "0,0,1,1", "[0,0][1,1]x", " [0,0][1,1]", "[0.5,0][1,1]", "[1,1][2,2][3,3]", "[ 0,0][1,1]"])
def test_malformed_bounds_rejected_with_treeerror(b):
    with pytest.raises(TreeError, match="bad bounds"):
        parse(f'<hierarchy><node class="a" bounds="{b}"/></hierarchy>')


def test_missing_bounds_attribute_rejected():
    with pytest.raises(TreeError, match="bad bounds"):
        parse('<hierarchy><node class="a"/></hierarchy>')


def test_negative_bounds_parse_for_offscreen_nodes():
    s = parse('<hierarchy><node class="a" bounds="[-200,-50][-10,40]"/></hierarchy>')
    assert s.nodes[0].bounds == (-200, -50, -10, 40) and s.nodes[0].size == (190, 90)


def test_one_bad_node_anywhere_rejects_whole_dump():
    with pytest.raises(TreeError):
        parse('<hierarchy><node class="a" bounds="[0,0][1,1]"><node class="b" bounds="oops"/></node></hierarchy>')


# ---- node_id ---------------------------------------------------------------------
b4 = st.tuples(coord, coord, coord, coord)


@SET
@given(st.text(max_size=30), b4, st.integers(0, 10000))
def test_node_id_is_deterministic_and_10_hex(cls, b, i):
    a = node_id(cls, b, i)
    assert a == node_id(cls, tuple(b), i)
    assert re.fullmatch(r"[0-9a-f]{10}", a)


@SET
@given(st.text(max_size=10), b4, st.integers(0, 100), st.tuples(*[st.integers(0, 7)] * 4))
def test_node_id_stable_within_8px_cell(cls, b, i, jitter):
    # shift each coordinate inside its own 8px quantisation cell -> identical id
    shifted = tuple((v // 8) * 8 + j for v, j in zip(b, jitter))
    assert node_id(cls, shifted, i) == node_id(cls, b, i)


@SET
@given(b4, st.integers(0, 100), st.integers(-5000, 5000))
def test_node_id_changes_when_a_coordinate_moves_a_full_cell(b, i, k):
    moved = (b[0] + 8 * (k or 1),) + b[1:]
    assert node_id("c", moved, i) != node_id("c", b, i)


@SET
@given(b4, st.integers(0, 100))
def test_node_id_depends_on_class_and_index(b, i):
    assert node_id("A", b, i) != node_id("B", b, i)
    assert node_id("A", b, i) != node_id("A", b, i + 1)


@SET
@given(st.text(max_size=20), st.text(max_size=20))
def test_node_id_ignores_labels(t1, t2):
    def doc(t):
        from xml.sax.saxutils import quoteattr
        return f'<hierarchy><node class="V" text={quoteattr(t)} content-desc={quoteattr(t)} bounds="[8,8][96,96]" focusable="true"/></hierarchy>'
    ids = []
    for t in (t1, t2):
        s = parses_or_treeerror(doc(t))
        if s is not None:
            ids.append(s.nodes[0].id)
    assert len(set(ids)) <= 1


def test_parse_assigns_unique_ids_for_identical_siblings():
    same = '<node class="V" bounds="[0,0][8,8]"/>' * 5
    s = parse(f"<hierarchy>{same}</hierarchy>")
    assert len({n.id for n in s.nodes}) == 5  # index is part of identity


def test_parse_is_deterministic_across_calls():
    assert [n.id for n in parse(VALID).nodes] == [n.id for n in parse(VALID).nodes]


@SET
@given(st.lists(b4, min_size=1, max_size=10))
def test_ids_equal_between_parses_and_children_indexes_valid(bl):
    a, b = parse(xml_for(bl)), parse(xml_for(bl))
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
    assert a.nodes[0].children == list(range(1, len(bl) + 1))


# ---- Snapshot / labels ------------------------------------------------------------
def test_root_not_hierarchy_is_treated_as_single_top_node():
    s = parse('<node class="Solo" package="p" bounds="[0,0][5,5]"/>')
    assert len(s.nodes) == 1 and s.package == "p"


def test_snapshot_package_empty_for_no_nodes():
    assert Snapshot([]).package == ""


def test_focusables_exclude_origin_zero_box_only():
    s = parse(xml_for([(0, 0, 0, 0), (3, 3, 3, 3), (1, 1, 9, 9)]))
    assert [n.bounds for n in s.focusables()] == [(3, 3, 3, 3), (1, 1, 9, 9)]


def test_focused_none_for_two_focused_nodes():
    d = '<hierarchy><node class="a" focused="true" bounds="[0,0][1,1]"/><node class="b" focused="true" bounds="[1,1][2,2]"/></hierarchy>'
    s = parse(d)
    assert s.focused() is None and len(s.focused_nodes()) == 2


def test_effective_label_own_text_beats_desc_and_descendants():
    s = parse('<hierarchy><node class="a" text="T" content-desc="D" bounds="[0,0][9,9]"><node class="b" text="K" bounds="[0,0][1,1]"/></node></hierarchy>')
    assert effective_label(s.nodes[0], s) == "T"


def test_effective_label_merges_nested_descendants_in_document_order():
    s = parse('<hierarchy><node class="a" bounds="[0,0][9,9]"><node class="b" text="One" bounds="[0,0][1,1]">'
              '<node class="c" content-desc="Two" bounds="[0,0][1,1]"/></node><node class="d" text="Three" bounds="[0,0][1,1]"/></node></hierarchy>')
    assert effective_label(s.nodes[0], s) == "One Two Three"


def test_unicode_attributes_survive_parse():
    s = parse('<hierarchy><node class="a" text="Привет ▶ 日本語 😀" content-desc="é" bounds="[0,0][1,1]"/></hierarchy>')
    assert s.nodes[0].text == "Привет ▶ 日本語 😀" and s.nodes[0].desc == "é"
