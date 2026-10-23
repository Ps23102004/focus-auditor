"""Pure detectors. Input: FocusGraph / Snapshot. Output: list[Finding]."""
import hashlib
from dataclasses import asdict, dataclass, field

from .tree import effective_label

KEYS = ("UP", "DOWN", "LEFT", "RIGHT")


@dataclass
class Finding:
    id: str
    kind: str          # TRAP | MISSING_LABEL | DUPLICATE_LABEL
    severity: str      # high | medium | low
    node_id: str
    bounds: list
    evidence: dict
    fix_hint: str
    witness: dict = field(default_factory=dict)  # {"keys": [...]} cold-start key path to a state showing the problem
    test_id: str = ""

    def to_json(self):
        return asdict(self)


def fid(kind, node_id):
    return hashlib.sha1(f"{kind}|{node_id}".encode()).hexdigest()[:10]


def closed_sets(graph):
    """Sink strongly-connected sets of the probed graph. Unprobed/unexpanded edges lead to an unknown sink,
    so a node we did not fully probe can never be part of a closed set."""
    out = graph.out()
    UNKNOWN = "?"

    def succ(n):
        return {out.get(n, {}).get(k, UNKNOWN) for k in KEYS}

    reach = {}
    for n in graph.nodes:
        seen, st = set(), [n]
        while st:
            a = st.pop()
            for b in (succ(a) if a != UNKNOWN else ()):
                if b not in seen:
                    seen.add(b)
                    st.append(b)
        reach[n] = seen
    sets, done = [], set()
    for n in graph.nodes:
        if n in done or UNKNOWN in reach[n]:
            continue
        scc = {m for m in reach[n] if n in reach.get(m, ())} | {n}
        if all(reach[m] <= scc for m in scc):
            sets.append(frozenset(scc))
        done |= scc
    return sets


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


WHOLE_SCREEN_FRACTION = 0.75


def find_traps(graph, snapshot=None, snaps=None):
    """Closed focus region: from every member all four D-pad directions land inside the region, while other
    focusables exist outside it. BACK is recorded in evidence, never counted as an escape."""
    findings = []
    reasons = graph.coverage.get("inconclusive_reasons", [])
    for s in closed_sets(graph):
        # judge "outside" and "whole screen" on the region's OWN screen, not on whichever snapshot has the most controls
        own = next((snaps[m] for m in sorted(s, key=lambda m: (len(graph.witness(m) or [None] * 99), m)) if snaps and m in snaps), snapshot)
        outside = [n for n in graph.nodes if n not in s]
        if not outside and own is not None:  # whole reached graph is closed: look for focusables we never reached
            known = [n["bounds"] for n in graph.nodes.values()]
            outside = [n.id for n in own.focusables() if n.id not in graph.nodes
                       and not any(_overlap(n.bounds, k) for k in known)]
        if not outside:
            continue
        # witness: shortest cold-start path into the region, ties broken by id for determinism
        cand = [(graph.witness(n), n) for n in s]
        cand = [(w, n) for w, n in cand if w is not None]
        w, entry = min(cand, key=lambda c: (len(c[0]), c[1])) if cand else ([], sorted(s)[0])
        # Spec deviation: node_cap / budget_exhausted only limit breadth. Every member of a closed set was fully probed
        # (unprobed edges lead to the unknown sink), so the region itself is confirmed. Any other gap (replay mismatch,
        # unreadable focus, adb error, deadline) => suspected.
        suspected = any(not r.startswith(("node_cap", "budget_exhausted: max_presses")) for r in reasons)
        back = next((graph.back[n] for n in sorted(s) if n in graph.back), "not_probed")
        # A region that is nearly the whole screen AND that BACK leaves is a top-level screen, not a pocket inside one: the
        # live replay can reproduce it, but "no D-pad exit" is normal there. A full-screen modal that BACK cannot leave
        # either stays a firm trap.
        on_screen = max(len(s), len(own.focusables()) if own is not None else 0)  # controls on the region's OWN screen (earlier pages are not part of it)
        whole_screen = len(s) >= WHOLE_SCREEN_FRACTION * on_screen and back == "yes"
        suspected = suspected or whole_screen
        members = sorted(s)
        edges = [list(e) for e in graph.edges if e[0] in s]
        findings.append(Finding(
            fid("TRAP", entry), "TRAP", "medium" if suspected else "high", entry,
            _union([graph.nodes[n]["bounds"] for n in members]),
            {"region": members, "region_labels": [graph.nodes[n]["label"] for n in members], "region_edges": edges,
             "outside_count": len(outside), "suspected": suspected, "whole_screen": whole_screen, "back_exits": back,
             "summary": f"{len(members)} focusable(s): every D-pad direction stays inside; {len(outside)} other focusable(s) exist"
                        + (" (suspected: region is most of the screen, likely a top-level screen)" if whole_screen else " (suspected: crawl coverage incomplete)" if suspected else "")},
            "Remove the focus property that cancels/blocks exit (e.g. Compose focusProperties { exit = Cancel }) "
            "so UP/DOWN/LEFT/RIGHT can leave the group.",
            {"keys": w or [], "path": [entry]}))
    # the same physical region seen under another scroll offset has different ids: keep the shortest witness
    best = {}
    for f in findings:
        sig = tuple(sorted(zip(f.evidence["region_labels"], (graph.nodes[n]["bounds"][2] - graph.nodes[n]["bounds"][0]
                                                             for n in f.evidence["region"]))))
        if sig not in best or len(f.witness["keys"]) < len(best[sig].witness["keys"]):
            best[sig] = f
    return sorted(best.values(), key=lambda f: f.id)


def find_label_issues(snapshot, path_keys=()):
    out = []
    focusables = [n for n in snapshot.focusables()]
    groups = {}
    for n in focusables:
        lab = effective_label(n, snapshot)
        if not lab:
            w, h = n.size
            icon = w <= 120 and h <= 120 and not n.text
            out.append(Finding(
                fid("MISSING_LABEL", n.id), "MISSING_LABEL", "medium", n.id, list(n.bounds),
                {"subtype": "icon_only" if icon else "unnamed", "cls": n.cls, "size": [w, h],
                 "summary": "no exposed accessible name in the accessibility tree"},
                "Add a contentDescription (Compose: Modifier.semantics { contentDescription = ... }).",
                {"keys": list(path_keys)}))
        else:
            groups.setdefault(lab, []).append(n)
    for lab, ns in sorted(groups.items()):
        if len(ns) >= 3:
            root = snapshot.nodes[0].bounds
            first = next((n for n in ns if not _clipped(n.bounds, root)), ns[0])  # representative: a fully visible member
            out.append(Finding(
                fid("DUPLICATE_LABEL", first.id), "DUPLICATE_LABEL", "low", first.id, list(first.bounds),
                {"label": lab, "count": len(ns), "members": [n.id for n in ns],
                 "summary": f"{len(ns)} focusables expose the identical name {lab!r} (informational)"},
                "Give each item a distinct accessible name (e.g. the real title).", {"keys": list(path_keys)}))
    return out


def _near(a, b, tol=8):
    return abs(a - b) <= tol


def _clipped(b, root):
    return b[0] <= root[0] or b[1] <= root[1] or b[2] >= root[2] or b[3] >= root[3]


def label_issues_across(snapshots, notes=None):
    """snapshots: iterable of (Snapshot, path_keys). Merge label findings from several screen states.
    Order is deterministic (most focusables first). A MISSING_LABEL is dropped when it is only another view of a control:
      - same bounds overlap an already reported one (same control, other layout state),
      - it is the collapsed form of a control that has a name in another state (left/top/bottom match, narrower),
      - it is clipped by the viewport and an unclipped control occupies the same columns elsewhere.
    Duplicate groups keep the largest group seen in any single state."""
    order = sorted(snapshots, key=lambda sp: (-len(sp[0].focusables()), sp[0].focused().id if sp[0].focused() else ""))
    pool = []  # (snapshot idx, bounds, named, clipped, id) for every focusable in every state
    for si, (snap, _) in enumerate(order):
        root = snap.nodes[0].bounds
        pool += [(si, n.bounds, bool(effective_label(n, snap)), _clipped(n.bounds, root), n.id) for n in snap.focusables()]
    # A control is reported only when it was seen WITHOUT a name WHILE FOCUSED (that is when a screen reader speaks it).
    # Leanback-style cards show their title only on focus, so "no name while unfocused" proves nothing either way: such a
    # control is never a finding, and is counted as unverified unless a named focused state covers it.
    named_focus_centres = []
    for snap, _k in order:
        f = snap.focused()
        if f is not None and effective_label(f, snap):
            named_focus_centres.append(f.bounds)

    def _inside(pt, b):
        return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]

    def _covered_by_named_focus(b):
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        return any(_inside(c, fb) and _inside(((fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2), b) for fb in named_focus_centres)

    unverified = set()
    missing, dups = {}, {}
    for si, (snap, keys) in enumerate(order):
        root = snap.nodes[0].bounds
        for f in find_label_issues(snap, keys):
            if f.kind == "MISSING_LABEL":
                b = f.bounds
                if f.id in missing or any(_overlap(b, m.bounds) for m in missing.values()):
                    continue
                if any(named and sj != si and _near(pb[0], b[0]) and _near(pb[1], b[1]) and _near(pb[3], b[3])
                       and pb[2] - pb[0] > b[2] - b[0] for sj, pb, named, _c, _i in pool):
                    continue  # collapsed form of a named control (e.g. a collapsed nav drawer)
                if _clipped(b, root) and any(not clip and i != f.node_id and _near(pb[0], b[0]) and _near(pb[2], b[2])
                                             for _s, pb, _n, clip, i in pool):
                    continue  # sliver of a control that is fully visible in another state
                foc = snap.focused()
                if foc is None or foc.id != f.node_id:  # not focused in this state: no evidence about its spoken name
                    if not _covered_by_named_focus(b):
                        unverified.add(tuple(v // 8 for v in b))
                    continue
                missing[f.id] = f
            else:
                cur = dups.get(f.evidence["label"])
                if cur is None or f.evidence["count"] > cur.evidence["count"]:
                    dups[f.evidence["label"]] = f
    if unverified and notes is not None:
        notes.append(f"label_unverified: {len(unverified)} control(s) with no name: "
                     "they were never observed while focused on the same screen, so they are not reported")
    return sorted(missing.values(), key=lambda f: f.id) + sorted(dups.values(), key=lambda f: f.id)
