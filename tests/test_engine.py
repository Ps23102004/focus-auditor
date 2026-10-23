import os

import pytest

from fa import detectors, report as rpt
from fa.adb import Adb, AdbError
from fa.cli import analyze, load_fixture
from fa.crawl import Crawler, FakeDevice, LiveDevice
from fa.tree import TreeError, effective_label, node_id, parse

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "buggy")


def N(cls, text="", desc="", bounds="[0,0][10,10]", focusable=False, focused=False, kids=""):
    return (f'<node class="{cls}" package="p" text="{text}" content-desc="{desc}" focusable="{str(focusable).lower()}" '
            f'focused="{str(focused).lower()}" clickable="false" bounds="{bounds}">{kids}</node>')


def H(*nodes):
    return '<?xml version="1.0"?><hierarchy>' + "".join(nodes) + "</hierarchy>"


# ---------------- parser ----------------
def test_exactly_one_focused():
    s = parse(H(N("A", focusable=True, focused=True), N("B", focusable=True)))
    assert s.focused().cls == "A"
    two = parse(H(N("A", focused=True), N("B", focused=True)))
    none = parse(H(N("A"), N("B")))
    assert two.focused() is None and none.focused() is None  # != 1 focused => inconclusive


def test_dtd_and_entities_rejected():
    for bad in ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><hierarchy/>', '<!ENTITY a "b"><hierarchy/>'):
        with pytest.raises(TreeError):
            parse(bad)


def test_malformed_and_empty_rejected():
    for bad in ("", "<hierarchy><node", "<hierarchy/>"):
        with pytest.raises(TreeError):
            parse(bad)


def test_effective_label_merges_descendants():
    kid = lambda t: N("T", text=t, bounds="[1,1][5,5]")
    s = parse(H(N("Row", focusable=True, kids=kid("Play") + kid("now")),
                N("Own", text="Mine", focusable=True, kids=kid("ignored")),
                N("Desc", desc="Described", focusable=True),
                N("Empty", focusable=True)))
    labels = [effective_label(n, s) for n in s.nodes if n.focusable]
    assert labels == ["Play now", "Mine", "Described", ""]


def test_id_stable_across_dumps_and_label_free():
    a = parse(H(N("A", text="before", bounds="[100,100][200,200]", focusable=True)))
    b = parse(H(N("A", text="after", bounds="[101,103][203,201]", focusable=True)))  # same 8px cell, label fixed
    c = parse(H(N("A", text="after", bounds="[300,100][400,200]", focusable=True)))
    assert a.nodes[0].id == b.nodes[0].id != c.nodes[0].id
    assert a.nodes[0].id == node_id("A", (100, 100, 200, 200), 0)


# ---------------- label detectors ----------------
def test_label_detectors_unit():
    t = lambda b: N("T", text="Movie Name", bounds=b)
    cards = "".join(N("V", focusable=True, bounds=f"[{i*100},300][{i*100+90},400]", kids=t(f"[{i*100+5},310][{i*100+80},330]")) for i in range(4))
    snap = parse(H(
        N("V", bounds="[0,0][1920,1080]", kids=(
            N("V", focusable=True, bounds="[0,0][96,96]") +            # icon only
            N("V", focusable=True, bounds="[100,0][400,500]") +        # big unnamed
            N("V", focusable=True, desc="ok", bounds="[0,600][96,696]") + cards))))
    fs = detectors.find_label_issues(snap)
    miss = [f for f in fs if f.kind == "MISSING_LABEL"]
    assert sorted(f.evidence["subtype"] for f in miss) == ["icon_only", "unnamed"]
    dup = [f for f in fs if f.kind == "DUPLICATE_LABEL"]
    assert len(dup) == 1 and dup[0].evidence["count"] == 4 and dup[0].severity == "low"
    ids = [m for f in fs for m in ([f.node_id] if f.kind == "MISSING_LABEL" else f.evidence["members"])]
    assert len(ids) == len(set(ids))


# ---------------- graph / trap detection on synthetic devices ----------------
HEALTHY = {(None, "DOWN"): "A", ("A", "RIGHT"): "B", ("B", "LEFT"): "A", ("B", "RIGHT"): "C", ("C", "LEFT"): "B",
           ("A", "DOWN"): "C", ("C", "UP"): "A"}
TRAP = {(None, "DOWN"): "M1", ("M1", "DOWN"): "M2", ("M2", "UP"): "M1", ("M1", "RIGHT"): "R1", ("M2", "RIGHT"): "R1",
        ("R1", "RIGHT"): "R2", ("R2", "LEFT"): "R1", ("R2", "RIGHT"): "R3", ("R3", "LEFT"): "R2"}  # row can't exit
DIALOG = {(None, "DOWN"): "D1", ("D1", "RIGHT"): "D2", ("D2", "LEFT"): "D1", ("D1", "BACK"): "EXIT", ("D2", "BACK"): "EXIT"}


def run(transitions, **kw):
    dev = FakeDevice(transitions)
    kw.setdefault("entry", ["DOWN"])
    g, snaps = Crawler(dev, **kw).run()
    return dev, g, snaps


def test_healthy_graph_has_no_trap_and_passes():
    dev, g, snaps = run(HEALTHY)
    assert g.coverage["inconclusive_reasons"] == [] and len(g.nodes) == 3
    assert detectors.find_traps(g, max(snaps.values(), key=lambda s: len(s.focusables()))) == []
    r = rpt.build(g, analyze(g, snaps))
    assert r["verdict"] in ("pass",) or all(f["kind"] == "DUPLICATE_LABEL" for f in r["findings"])


def test_trap_found_with_witness_and_back_recorded():
    dev, g, snaps = run(TRAP)
    traps = detectors.find_traps(g, None)
    assert len(traps) == 1
    t = traps[0]
    assert set(t.evidence["region"]) == {dev.node_id(n) for n in ("R1", "R2", "R3")}
    assert t.witness["keys"] == ["DOWN", "RIGHT"] and t.evidence["suspected"] is False
    assert t.evidence["back_exits"] == "no"  # BACK was probed and did nothing; it is not an escape either way
    assert rpt.verdict(analyze(g, snaps), g.coverage) == "fail"


def test_dialog_closed_graph_not_a_trap_even_though_back_exits():
    dev, g, snaps = run(DIALOG)
    assert detectors.find_traps(g, max(snaps.values(), key=lambda s: len(s.focusables()))) == []
    assert list(g.back.values()) == ["yes"]


def test_back_is_not_an_escape_when_other_focusables_exist():
    t = {**TRAP, ("R1", "BACK"): "EXIT", ("R2", "BACK"): "EXIT", ("R3", "BACK"): "EXIT"}
    dev, g, snaps = run(t)
    (f,) = detectors.find_traps(g, None)
    assert f.evidence["back_exits"] == "yes"  # recorded separately; still a trap


def test_finding_ids_deterministic():
    ids = [sorted(f.id for f in analyze(*run(TRAP)[1:])) for _ in range(2)]
    assert ids[0] == ids[1] and ids[0]


# ---------------- inconclusive, never pass ----------------
@pytest.mark.parametrize("kw,needle", [
    (dict(max_presses=6), "budget_exhausted"),
    (dict(deadline_s=-1), "budget_exhausted"),
    (dict(max_nodes=2), "node_cap"),
])
def test_budget_exhaustion_is_inconclusive(kw, needle):
    for tr in (HEALTHY, TRAP):
        dev, g, snaps = run(tr, **kw)
        assert any(needle in r for r in g.coverage["inconclusive_reasons"])
        assert rpt.verdict([], g.coverage) == "inconclusive"
        assert rpt.build(g, analyze(g, snaps))["verdict"] != "pass"


def test_breadth_limits_keep_fully_probed_trap_confirmed_but_run_inconclusive():
    dev, g, snaps = run({**TRAP, ("M2", "DOWN"): "X", ("X", "UP"): "M2"}, max_nodes=5)
    assert g.coverage["inconclusive_reasons"]  # coverage is incomplete: reported, never green
    (t,) = detectors.find_traps(g, None)
    assert t.evidence["suspected"] is False  # all 4 directions of every region member were observed


def test_other_gaps_make_trap_suspected():
    dev, g, snaps = run(TRAP)
    g.coverage["inconclusive_reasons"].append("replay_mismatch: x")
    (t,) = detectors.find_traps(g, None)
    assert t.evidence["suspected"] is True and rpt.verdict([t], g.coverage) == "inconclusive"


def test_generated_tests_fail_on_trap_and_pass_when_fixed(tmp_path):
    from fa import testgen
    dev, g, snaps = run(TRAP)
    rep = rpt.build(g, analyze(g, snaps), app="fake.app", activity=".M")
    paths = testgen.generate_tests(rep, str(tmp_path))
    assert len(paths) == len(rep["findings"]) and all("pytest.mark.device" in open(p).read() for p in paths)
    (f,) = [f for f in rep["findings"] if f["kind"] == "TRAP"]
    data = testgen._data(rep, f)
    with pytest.raises(AssertionError, match="never leaves"):
        testgen.check(data, FakeDevice(TRAP))
    testgen.check(data, FakeDevice({**TRAP, ("R3", "UP"): "M1"}))  # fix: row can exit upward
    gone = {k: v for k, v in TRAP.items() if "R1" not in k and v != "R1"}
    with pytest.raises(AssertionError, match="no longer reaches"):
        testgen.check(data, FakeDevice({**gone, ("M1", "RIGHT"): "M2"}, names=["M1", "M2", "R1", "R2", "R3"]))


def test_device_error_mid_crawl_is_inconclusive():
    dev = FakeDevice(HEALTHY, press_error_after=4)
    g, snaps = Crawler(dev, entry=["DOWN"]).run()
    assert any("adb_error" in r for r in g.coverage["inconclusive_reasons"])
    assert rpt.verdict([], g.coverage) == "inconclusive"


def test_unreadable_focus_is_inconclusive():
    dev = FakeDevice(HEALTHY, read_failures=1000)
    g, snaps = Crawler(dev, entry=["DOWN"]).run()
    assert g.coverage["inconclusive_reasons"] and rpt.verdict([], g.coverage) == "inconclusive"


def test_malformed_xml_from_device_gives_none_not_crash():
    class A:
        serial = None
        def dump_xml(self): return "<hierarchy><node"
    dev = LiveDevice(A(), "p", ".M")
    assert dev.read() is None and dev.last_error.startswith("malformed")


def test_adb_timeout_raises_adberror():
    with pytest.raises(AdbError):
        Adb(timeout=0.001, adb_path="/bin/sleep").run("5")


def test_clean_complete_run_passes():
    r = rpt.build(*run(HEALTHY)[1:2], [])
    assert r["verdict"] == "pass"


# ---------------- recorded live fixture (buggy sample) ----------------
needs_fixture = pytest.mark.skipif(not os.path.isdir(FIX), reason="fixture not recorded")


@needs_fixture
def test_buggy_fixture_findings():
    g, snaps = load_fixture(FIX)
    fs = analyze(g, snaps)
    traps = [f for f in fs if f.kind == "TRAP"]
    assert len(traps) == 1 and len(traps[0].evidence["region"]) == 3  # Play + two icon tiles
    assert traps[0].witness["keys"][0] == "DOWN"
    labels = [f for f in fs if f.kind == "MISSING_LABEL"]
    assert len(labels) == 2 and all(f.evidence["subtype"] == "icon_only" for f in labels)
    dups = [f for f in fs if f.kind == "DUPLICATE_LABEL"]
    assert len(dups) == 1 and dups[0].evidence["label"] == "Movie Name" and dups[0].evidence["count"] >= 25
    seen = []
    for f in fs:
        if f.kind != "TRAP":
            seen += [f.node_id] if f.kind != "DUPLICATE_LABEL" else f.evidence["members"]
    assert len(seen) == len(set(seen))  # no node reported twice
    assert [f.id for f in fs] == [f.id for f in analyze(g, snaps)]


@needs_fixture
def test_trap_region_matches_row_geometry():
    g, snaps = load_fixture(FIX)
    (t,) = [f for f in analyze(g, snaps) if f.kind == "TRAP"]
    l, tp, r, b = t.bounds
    assert tp < 250 and b < 260 and (r - l) < 600  # Quick actions row at the top, not the grid


@needs_fixture
def test_fixture_report_is_valid_json_schema():
    import json
    g, snaps = load_fixture(FIX)
    r = rpt.build(g, analyze(g, snaps))
    json.dumps(r)
    for k in ("schema_version", "meta", "coverage", "nodes", "edges", "findings", "screenshot", "summary", "verdict"):
        assert k in r
    for k in ("app", "device", "timestamp", "fa_version", "run_id"):
        assert k in r["meta"]


@pytest.mark.device
def test_device_smoke():
    adb = Adb()
    dev = LiveDevice(adb, "com.amazonappstore.helloworldtv", ".MainActivity")
    dev.cold_start()
    dev.press("DOWN")
    snap = dev.read()
    assert snap is not None and snap.focused() is not None
