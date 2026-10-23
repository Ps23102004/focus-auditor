"""TalkBack-style spoken announcement for a focused node. Source: "rules" (plain stdlib rules, not ML).

This APPROXIMATES the TalkBack rules (label, role, state, list position). It is NOT what VoiceView says on a
Fire TV device: VoiceView's wording and ordering differ. Use it to preview what an unlabelled control sounds like.
"""
import shutil, subprocess
import xml.etree.ElementTree as ET

from .tree import effective_label

SOURCE = "rules"
_ROLES = (("EditText", "edit box"), ("CheckBox", "check box"), ("Switch", "switch"), ("RadioButton", "radio button"),
          ("ToggleButton", "toggle button"), ("Button", "button"), ("ImageView", "image"), ("Spinner", "drop-down list"),
          ("SeekBar", "slider"), ("TabWidget", "tab"), ("TextView", "text"))


def _attrs(snap):
    """Per-node (checked, selected, enabled) from the raw dump, in the same DFS order as tree.parse()."""
    out = []

    def walk(el):
        out.append((el.get("checked") == "true", el.get("selected") == "true", el.get("enabled") != "false"))
        for c in el.findall("node"):
            walk(c)

    try:
        root = ET.fromstring(snap.raw.strip())
        for el in (root.findall("node") if root.tag == "hierarchy" else [root]):
            walk(el)
    except ET.ParseError:
        pass
    return out if len(out) == len(snap.nodes) else [(False, False, True)] * len(snap.nodes)


def role_of(node):
    for key, role in _ROLES:
        if node.cls.endswith(key):
            return role
    return "button" if node.clickable or node.focusable else ""


def position(snap, node):
    """(index, total) among focusable same-class siblings under one parent, in reading order, or None (fewer than 3 = not a list)."""
    parent = next((n for n in snap.nodes if node.index in n.children), None)
    if parent is None:
        return None
    sibs = [snap.nodes[i] for i in parent.children if snap.nodes[i].cls == node.cls and snap.nodes[i].focusable and snap.nodes[i].bounds != (0, 0, 0, 0)]  # hidden nodes are not in the list
    if len(sibs) < 3 or node not in sibs:
        return None
    sibs.sort(key=lambda n: (n.bounds[1], n.bounds[0], n.index))  # visual reading order, not tree order
    return [n.index for n in sibs].index(node.index) + 1, len(sibs)


def announce(snap, node):
    checked, selected, enabled = _attrs(snap)[node.index]
    parts = [effective_label(node, snap) or "unlabelled", role_of(node) or "button"]
    if checked:
        parts.append("checked")
    if selected:
        parts.append("selected")
    if not enabled:
        parts.append("disabled")
    pos = position(snap, node)
    if pos:
        parts.append(f"{pos[0]} of {pos[1]}")
    return ", ".join(parts)


def announce_all(snap):
    """Announcement for every focusable node, in document order."""
    return [(n.id, announce(snap, n)) for n in snap.focusables()]


def witness_sequence(graph, snaps):
    """Announcements along the recorded cold-start path to the deepest known focus state: entry, then the
    key path of the longest witness. Returns [(key, node_id, text)]."""
    if not graph.entry:
        return []
    ids = [i for i in snaps if graph.witness(i)]
    target = max(ids, key=lambda i: (len(graph.witness(i)), i), default=graph.root)
    keys, cur, seq = graph.witness(target) or [graph.entry[0][0]], None, []
    out = graph.out()
    for k in keys:
        cur = graph.entry[0][1] if cur is None else out.get(cur, {}).get(k, cur)
        s = snaps.get(cur)
        node = next((n for n in s.nodes if n.id == cur), None) if s else None
        seq.append((k, cur, announce(s, node) if node else "(no snapshot)"))
    return seq


def speak(text):
    exe = shutil.which("say")
    if not exe:
        return False
    # App-derived text is untrusted: send it on stdin (`-f -`) so a label like "-o /path" is never an option.
    subprocess.run([exe, "-f", "-"], input=text.encode("utf-8", "replace"), check=False, timeout=30)
    return True
