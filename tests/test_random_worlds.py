"""Unseen-data test: hundreds of random apps (focus graphs) with ground truth computed by an INDEPENDENT algorithm.
The crawler drives each fake app with D-pad presses only; detectors must find exactly the closed regions that exist."""
import random

import pytest
from fa.cli import analyze
from fa.crawl import Crawler, FakeDevice

KEYS = ("UP", "DOWN", "LEFT", "RIGHT")


def make_world(seed, exit_p=0.0):
    rng = random.Random(seed)
    n = rng.randint(3, 8)
    names = [chr(ord("A") + i) for i in range(n)]
    t = {(None, "DOWN"): names[0]}  # entry
    for a in names:
        for k in KEYS:
            r = rng.random()
            if r < 0.30:
                t[(a, k)] = a                     # no movement
            elif r < 0.30 + exit_p:
                t[(a, k)] = "EXIT"               # leaves the app
            else:
                t[(a, k)] = rng.choice(names)
    return names, t


def reachable(names, t):
    seen, st = {names[0]}, [names[0]]
    while st:
        a = st.pop()
        for k in KEYS:
            b = t[(a, k)]
            if b != "EXIT" and b not in seen:
                seen.add(b)
                st.append(b)
    return seen


def truth_closed_sets(names, t):
    """Maximal strongly connected sets whose every key lands inside the set (self loops allowed, EXIT is an escape),
    restricted to proper subsets of the controls on screen. Plain DFS reachability, no library."""
    nodes = sorted(reachable(names, t))
    reach = {}
    for a in nodes:
        seen, st = set(), [a]
        while st:
            x = st.pop()
            for k in KEYS:
                y = t[(x, k)]
                if y != "EXIT" and y not in seen:
                    seen.add(y)
                    st.append(y)
        reach[a] = seen
    out = set()
    for a in nodes:
        if any(t[(a, k)] == "EXIT" for k in KEYS):
            continue
        scc = frozenset({b for b in reach[a] if a in reach[b]} | {a})
        if all(t[(m, k)] != "EXIT" and t[(m, k)] in scc for m in scc for k in KEYS) and len(scc) < len(names):  # the fake screen shows every name, so unreachable ones count as outside
            out.add(scc)
    return out


def crawl(seed, exit_p=0.0):
    names, t = make_world(seed, exit_p)
    dev = FakeDevice(t, names=names, pkg="world.app")
    g, snaps = Crawler(dev, max_presses=4000, max_nodes=50, deadline_s=60).run()
    return names, t, g, snaps


@pytest.mark.parametrize("seed", range(300))
def test_detected_traps_equal_ground_truth(seed):
    names, t, g, snaps = crawl(seed)
    reasons = g.coverage["inconclusive_reasons"]
    if len(reachable(names, t)) < 2:  # a one-control world must be called tiny coverage, never a pass
        assert reasons and all(r.startswith("tiny_coverage") for r in reasons)
    else:
        assert not reasons, reasons  # no exits: the crawl must be complete
    want = truth_closed_sets(names, t)
    id_to_name = {}
    for nid, node in g.nodes.items():
        # fake devices place node i at x = 100*i, so the label is the name
        id_to_name[nid] = node["label"]
    got = {frozenset(id_to_name[i] for i in f.evidence["region"]) for f in analyze(g, snaps) if f.kind == "TRAP"}
    assert got == want, f"seed {seed}: crawler found {sorted(map(sorted, got))}, ground truth {sorted(map(sorted, want))}"


def test_no_world_where_a_trap_exists_is_reported_pass():
    from fa import report
    bad = 0
    for seed in range(300):
        names, t, g, snaps = crawl(seed)
        if truth_closed_sets(names, t):
            v = report.build(g, analyze(g, snaps))["verdict"]
            if v == "pass":
                bad += 1
    assert bad == 0


def test_world_generator_produces_a_mix_of_trap_and_trap_free_worlds():
    k = sum(1 for s in range(300) if truth_closed_sets(*make_world(s)))
    assert 20 < k < 280, f"degenerate generator: {k}/300 worlds have a trap"


def exit_reachable(names, t):
    return any(t[(a, k)] == "EXIT" for a in reachable(names, t) for k in KEYS)


@pytest.mark.parametrize("seed", range(300))
def test_worlds_with_exits_never_pass_and_never_invent_traps(seed):
    """Pressing a key that leaves the app gives no readable focus: the audit must say inconclusive, and every trap it
    does report must still be a real closed region (precision), never a made-up one."""
    from fa import report
    names, t, g, snaps = crawl(seed, exit_p=0.10)
    findings = analyze(g, snaps)
    if exit_reachable(names, t):
        assert report.build(g, findings)["verdict"] != "pass"
    id_to_name = {nid: n["label"] for nid, n in g.nodes.items()}
    reported = {frozenset(id_to_name[i] for i in f.evidence["region"]) for f in findings if f.kind == "TRAP"}
    # a reported region may not contain a node that has an EXIT key, and must be closed in the true graph
    for region in reported:
        for m in region:
            for k in KEYS:
                assert t[(m, k)] != "EXIT" and t[(m, k)] in region, f"seed {seed}: invented trap {sorted(region)}"


def test_complete_worlds_with_a_partial_trap_fail():
    """Severity/verdict, not just membership: a closed region smaller than 75% of the screen in a fully crawled world
    is a confirmed defect, so the verdict must be fail."""
    from fa import report
    checked = 0
    for seed in range(300):
        names, t, g, snaps = crawl(seed)
        want = truth_closed_sets(names, t)
        if not want or len(reachable(names, t)) < 2 or all(len(s) >= 0.75 * len(names) for s in want):
            continue
        checked += 1
        assert report.build(g, analyze(g, snaps))["verdict"] == "fail", f"seed {seed}"
    assert checked >= 20, checked
