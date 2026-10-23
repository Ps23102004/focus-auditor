"""Parse a uiautomator dump into a Snapshot. Untrusted input: DTDs/entities are rejected."""
import hashlib, re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_BOUNDS = re.compile(r"\[(-?\d{1,9}),(-?\d{1,9})\]\[(-?\d{1,9}),(-?\d{1,9})\]")
MAX_DEPTH = 256  # real UI trees are < 100 deep; this bounds the recursion on untrusted dumps


class TreeError(ValueError):
    pass


def node_id(cls, bounds, index):
    """Label-free identity: labels change when a bug is fixed, geometry does not."""
    q = tuple(v // 8 for v in bounds)
    return hashlib.sha1(f"{cls}|{q}|{index}".encode()).hexdigest()[:10]


@dataclass
class Node:
    id: str
    index: int
    cls: str
    text: str
    desc: str
    bounds: tuple
    focusable: bool
    focused: bool
    clickable: bool
    package: str = ""
    children: list = field(default_factory=list)  # indexes into Snapshot.nodes

    @property
    def size(self):
        l, t, r, b = self.bounds
        return (r - l, b - t)


class Snapshot:
    def __init__(self, nodes, raw=""):
        self.nodes = nodes
        self.raw = raw

    @property
    def package(self):
        return self.nodes[0].package if self.nodes else ""

    def focused_nodes(self):
        return [n for n in self.nodes if n.focused]

    def focused(self):
        """Exactly one focused node or None (anything else is inconclusive)."""
        f = self.focused_nodes()
        return f[0] if len(f) == 1 else None

    def focusables(self):
        return [n for n in self.nodes if n.focusable and n.bounds != (0, 0, 0, 0)]

    def by_id(self):
        return {n.id: n for n in self.nodes}


def parse(xml_text):
    if xml_text is None or not xml_text.strip():
        raise TreeError("empty dump")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml_text, re.I):
        raise TreeError("refusing UI dump containing a DTD/entity")
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError as e:
        raise TreeError(f"malformed XML: {e}") from e
    nodes = []

    def walk(el, parent, depth=0):
        if depth > MAX_DEPTH:
            raise TreeError(f"UI tree deeper than {MAX_DEPTH} levels")
        m = _BOUNDS.fullmatch(el.get("bounds", ""))
        if not m:
            raise TreeError(f"bad bounds {el.get('bounds')!r}")
        b = tuple(int(x) for x in m.groups())
        i = len(nodes)
        cls = el.get("class", "")
        n = Node(node_id(cls, b, i), i, cls, el.get("text", ""), el.get("content-desc", ""), b,
                 el.get("focusable") == "true", el.get("focused") == "true", el.get("clickable") == "true",
                 el.get("package", ""))
        nodes.append(n)
        if parent is not None:
            parent.children.append(i)
        for ch in el.findall("node"):
            walk(ch, n, depth + 1)

    tops = root.findall("node") if root.tag == "hierarchy" else [root]
    for el in tops:
        walk(el, None)
    if not nodes:
        raise TreeError("no nodes in dump")
    return Snapshot(nodes, xml_text)


def _descendant_text(node, snap, out):
    for ci in node.children:
        c = snap.nodes[ci]
        t = (c.text or c.desc).strip()
        if t:
            out.append(t)
        _descendant_text(c, snap, out)


def effective_label(node, snap):
    """Own text, else own content-desc, else merged descendant text. This is what the accessibility tree exposes."""
    if node.text.strip():  # whitespace-only is silent to a screen reader: not a label
        return node.text.strip()
    if node.desc.strip():
        return node.desc.strip()
    parts = []
    _descendant_text(node, snap, parts)
    return " ".join(parts)
