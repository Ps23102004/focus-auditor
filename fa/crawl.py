"""Bounded D-pad crawl -> directed focus graph. Anything we could not observe is INCONCLUSIVE, never green."""
import hashlib, time
from dataclasses import dataclass, field

from .adb import Adb, AdbError
from .tree import TreeError, effective_label, node_id, parse

KEYS = ("UP", "DOWN", "LEFT", "RIGHT")
OPP = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


@dataclass
class FocusGraph:
    nodes: dict = field(default_factory=dict)      # id -> {id, cls, label, bounds}
    edges: list = field(default_factory=list)      # (from_id, key, to_id)
    coverage: dict = field(default_factory=dict)   # pressed, budget, inconclusive_reasons, ...
    entry: list = field(default_factory=list)      # [(key, node_id)] from cold start
    back: dict = field(default_factory=dict)       # node_id -> yes|no|inconclusive
    pkg: str = ""

    @property
    def root(self):
        return self.entry[0][1] if self.entry else None

    def out(self):
        o = {}
        for a, k, b in self.edges:
            o.setdefault(a, {})[k] = b
        return o

    def path(self, src, dst):
        """Shortest known key path src->dst (BFS, fixed key order => deterministic); None if unknown."""
        if src == dst:
            return []
        o, seen, q = self.out(), {src}, [(src, [])]
        while q:
            n, p = q.pop(0)
            for k in KEYS:
                t = o.get(n, {}).get(k)
                if t and t not in seen:
                    if t == dst:
                        return p + [k]
                    seen.add(t)
                    q.append((t, p + [k]))
        return None

    def witness(self, dst):
        """Cold-start key sequence reaching dst, or None."""
        if not self.entry:
            return None
        p = self.path(self.root, dst)
        return None if p is None else [self.entry[0][0]] + p

    def to_json(self):
        return {"pkg": self.pkg, "nodes": list(self.nodes.values()), "edges": [list(e) for e in self.edges],
                "coverage": self.coverage, "entry": [list(e) for e in self.entry], "back": self.back}

    @classmethod
    def from_json(cls, d):
        return cls({n["id"]: n for n in d["nodes"]}, [tuple(e) for e in d["edges"]], d.get("coverage", {}),
                   [tuple(e) for e in d["entry"]], d.get("back", {}), d.get("pkg", ""))


def summarize(n, snap):
    return {"id": n.id, "cls": n.cls, "label": effective_label(n, snap), "bounds": list(n.bounds)}


class LiveDevice:
    def __init__(self, adb: Adb, pkg, activity, settle=0.3, start_settle=3.5):
        self.adb, self.pkg, self.activity, self.settle, self.start_settle = adb, pkg, activity, settle, start_settle
        self.last_error = None

    def cold_start(self):
        self.adb.cold_start(self.pkg, self.activity, self.start_settle)

    def press(self, key):
        self.adb.key(key)
        time.sleep(self.settle)

    def read(self):
        """Snapshot, or None (dump failed / malformed). AdbError (lost device, timeout) propagates."""
        xml = self.adb.dump_xml()
        if xml is None:
            self.last_error = "no_xml"
            return None
        try:
            return parse(xml)
        except TreeError as e:
            self.last_error = f"malformed:{e}"
            return None


class FakeDevice:
    """Offline device for tests. Focus states are names; transitions {(state, key): state}.
    State None = cold start with nothing focused. BACK may map to 'EXIT' (app left)."""

    def __init__(self, transitions, names=None, pkg="fake.app", read_failures=0, press_error_after=None):
        self.t, self.pkg = dict(transitions), pkg
        self.names = names or sorted({s for (s, _k) in self.t if s} | {v for v in self.t.values() if v and v != "EXIT"})
        self.state, self.presses, self.cold_starts = None, 0, 0
        self.read_failures, self.press_error_after = read_failures, press_error_after

    def node_id(self, name):
        return node_id("android.view.View", self._bounds(name), 1 + self.names.index(name))

    def _bounds(self, name):
        i = self.names.index(name)
        return (i * 100, 0, i * 100 + 96, 96)

    def xml(self):
        if self.state == "EXIT":
            return ('<?xml version="1.0"?><hierarchy><node class="android.widget.FrameLayout" package="com.launcher" '
                    'text="" content-desc="" focusable="false" focused="false" clickable="false" bounds="[0,0][1920,1080]"/></hierarchy>')
        rows = "".join(
            f'<node class="android.view.View" package="{self.pkg}" text="{n}" content-desc="" focusable="true" '
            f'focused="{"true" if n == self.state else "false"}" clickable="true" bounds="[{self._bounds(n)[0]},0][{self._bounds(n)[2]},96]"/>'
            for n in self.names)
        return (f'<?xml version="1.0"?><hierarchy><node class="android.widget.FrameLayout" package="{self.pkg}" text="" '
                f'content-desc="" focusable="false" focused="false" clickable="false" bounds="[0,0][1920,1080]">{rows}</node></hierarchy>')

    def cold_start(self):
        self.state, self.cold_starts = None, self.cold_starts + 1

    def press(self, key):
        self.presses += 1
        if self.press_error_after is not None and self.presses > self.press_error_after:
            raise AdbError("device offline")
        if self.state == "EXIT":
            return
        self.state = self.t.get((self.state, key), self.state)

    def read(self):
        if self.read_failures > 0:
            self.read_failures -= 1
            return None
        return parse(self.xml())


class _Stop(Exception):
    pass


MIN_NODES = 2  # a 'pass' over fewer controls than this is not a pass


class Crawler:
    def __init__(self, dev, entry=("DOWN",), max_nodes=40, max_presses=400, deadline_s=900, log=None):
        self.dev, self.entry = dev, list(entry)
        self.max_nodes, self.max_presses, self.deadline_s = max_nodes, max_presses, deadline_s
        self.g = FocusGraph()
        self.snaps = {}          # focused node id -> Snapshot (first seen)
        self.reasons, self.pressed, self.cold_starts, self.probes = [], 0, 0, 0
        self.pos, self.expanded, self.skipped, self.last_key = None, set(), set(), None
        self.explore_limit = int(max_presses * 0.85)
        self.t0, self.log = time.monotonic(), log or (lambda *_: None)

    # ---- primitives -------------------------------------------------
    def _budget(self):
        if self.pressed >= self.max_presses:
            raise _Stop("budget_exhausted: max_presses")
        if time.monotonic() - self.t0 > self.deadline_s:
            raise _Stop("budget_exhausted: deadline")

    def _press(self, key):
        self._budget()
        self.dev.press(key)
        self.pressed += 1

    def _cold(self):
        self._budget()
        self.dev.cold_start()
        self.cold_starts += 1
        self.pressed += 1
        self.pos = None

    def _read(self):
        """Focused node id after reading; one extra dump only when the first had no single focused node."""
        for _ in range(2):
            snap = self.dev.read()
            want = self.g.pkg or getattr(self.dev, "pkg", None)
            foc = snap.focused() if snap is not None else None
            if snap is not None and want and foc is not None and (snap.package != want or (foc.package and foc.package != want)):
                # Another app is in front (a link opened something else, the launcher resumed a different task).
                # Never record it: its controls would be reported as findings of the audited app.
                msg = f"left_app: expected {want}, saw {snap.package}"
                if msg not in self.reasons:
                    self.reasons.append(msg)
                return None
            if snap is not None and snap.focused() is not None:
                f = snap.focused()
                if f.id not in self.g.nodes:
                    self.g.nodes[f.id] = summarize(f, snap)
                    self.snaps[f.id] = snap
                if not self.g.pkg:
                    self.g.pkg = snap.package
                return f.id
        return None

    # ---- navigation ---------------------------------------------------
    def _goto(self, n):
        if self.pos == n:
            return True
        if self.pos is not None:
            p = self.g.path(self.pos, n)
            if p is not None:
                for k in p:
                    self._press(k)
                if self._read() == n:
                    self.pos = n
                    return True
        self._cold()
        self._press(self.entry[0])
        for k in self.g.path(self.g.root, n) or []:
            self._press(k)
        got = self._read()
        self.pos = got
        if got != n:
            self.reasons.append(f"replay_mismatch: wanted {n} got {got}")
            return False
        return True

    def _candidates(self):
        out = self.g.out()
        for n in list(self.g.nodes):
            if n not in self.expanded and len(self.expanded) >= self.max_nodes:
                continue
            for k in KEYS:
                if k not in out.get(n, {}) and (n, k) not in self.skipped:
                    yield n, k

    def _next(self):
        cands = list(self._candidates())
        if not cands:
            return None
        dist = {}
        if self.pos is not None:
            dist[self.pos] = 0
            q = [self.pos]
            o = self.g.out()
            while q:
                a = q.pop(0)
                for k in KEYS:
                    b = o.get(a, {}).get(k)
                    if b and b not in dist:
                        dist[b] = dist[a] + 1
                        q.append(b)
        depth = {self.g.root: 0}  # cold candidates: cheapest replay first
        q, o = [self.g.root], self.g.out()
        while q:
            a = q.pop(0)
            for k in KEYS:
                b = o.get(a, {}).get(k)
                if b and b not in depth:
                    depth[b] = depth[a] + 1
                    q.append(b)
        order = {n: i for i, n in enumerate(self.g.nodes)}
        # nearest first; at the same distance prefer the key that likely steps back to where we came from
        # (it is still a real probe of this node, and keeps replays short)
        return min(cands, key=lambda c: (dist.get(c[0], 1000 + depth.get(c[0], 999)), c[1] != OPP.get(self.last_key), order[c[0]], KEYS.index(c[1])))

    # ---- main ---------------------------------------------------------------
    def run(self, back_probe=True, before_back=None):
        try:
            self._enter()
            while True:
                if self.pressed >= self.explore_limit:  # keep 15% of the budget for the scroll pass and BACK probe
                    self.reasons.append("budget_exhausted: max_presses")
                    break
                nxt = self._next()
                if nxt is None:
                    break
                n, k = nxt
                if not self._goto(n):
                    self.skipped.update((n, kk) for kk in KEYS)
                    continue
                self.expanded.add(n)
                self._press(k)
                self.probes += 1
                to = self._read()
                if to is None:
                    self.reasons.append(f"no_focus_after: {k} from {n}")
                    self.skipped.add((n, k))
                    self.pos = None
                    continue
                self.g.edges.append((n, k, to))
                self.pos, self.last_key = to, k
                self.log(f"{n} {k} -> {to}  presses={self.pressed} nodes={len(self.g.nodes)}")
            self._scroll_pass()
            if before_back:
                before_back(self)
            if back_probe:
                self._probe_back()
            unexpanded = [n for n in self.g.nodes if n not in self.expanded]  # last: scroll pass and BACK probe add nodes too
            if unexpanded:
                self.reasons.append(f"node_cap: {len(unexpanded)} discovered nodes not expanded (max_nodes={self.max_nodes})")
        except _Stop as e:
            self.reasons.append(str(e))
        except AdbError as e:
            self.reasons.append(f"adb_error: {e}")
        return self._finish()

    def _enter(self):
        self._cold()
        prev = None
        for key in self.entry:
            self._press(key)
            nid = self._read()
            if nid is None:
                raise _Stop(f"no_focus_after_entry: {key}")
            if prev is not None:
                self.g.edges.append((prev, key, nid))
            self.g.entry.append((key, nid))
            prev = nid
        self.pos = prev
        self.g.entry = self.g.entry[:1]  # root = first focus; later entry keys are ordinary recorded edges

    def _scroll_pass(self):
        """Lists are lazily composed: capture the end-of-list state so label checks see every item.
        From the lowest node that can still move DOWN, press DOWN in chunks until focus stops changing."""
        movers = [n for n, o in self.g.out().items() if o.get("DOWN") not in (None, n)]
        if not movers:
            return
        start = max(movers, key=lambda n: (self.g.nodes[n]["bounds"][3], n))
        if not self._goto(start):
            return
        last = start
        for _ in range(6):
            for _ in range(4):
                self._press("DOWN")
            cur = self._read()
            self.pos = cur
            if cur is None or cur == last:
                break
            last = cur

    def _probe_back(self):
        from .detectors import closed_sets
        for s in closed_sets(self.g):
            first = sorted(s, key=lambda n: (len(self.g.witness(n) or [None] * 99), n))[0]
            if not self._goto(first):
                self.g.back[first] = "inconclusive"
                continue
            self._press("BACK")
            snap = self.dev.read()
            if snap is None:
                self.g.back[first] = "inconclusive"
            elif snap.package != self.g.pkg:
                self.g.back[first] = "yes"
            else:
                f = snap.focused()
                self.g.back[first] = "no" if f is not None and f.id in s else ("yes" if f is not None else "inconclusive")
            self.pos = None

    def _finish(self):
        if len(self.g.nodes) < MIN_NODES:  # e.g. a first-run onboarding screen with one button: nothing was audited
            self.reasons.append(f"tiny_coverage: only {len(self.g.nodes)} control(s) reachable with the D-pad; "
                                "use --entry (e.g. CENTER) to get past onboarding or a dialog")
        self.g.coverage = {
            "pressed": self.pressed, "budget": self.max_presses, "cold_starts": self.cold_starts, "probes": self.probes,
            "nodes": len(self.g.nodes), "expanded": len(self.expanded), "max_nodes": self.max_nodes,
            "elapsed_s": round(time.monotonic() - self.t0, 1), "inconclusive_reasons": list(self.reasons),
        }
        return self.g, self.snaps
