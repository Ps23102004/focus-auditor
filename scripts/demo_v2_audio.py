"""Before/after announcements for each unnamed control in the v2 demo, from REAL trees:
before = the audit's own recorded snapshot where that control was focused; after = a live dump of the fixed app
after replaying the same witness keys. Also saves the after witness screenshot. Audio via macOS `say` (stdin)."""
import json, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fa.adb import Adb
from fa.announce import announce
from fa.tree import parse

OUT = "demo-v2"
PKG, ACT = "com.amazonappstore.helloworldtv", ".MainActivity"


def focused_announcement(xml):
    snap = parse(xml)
    node = snap.focused()
    return (announce(snap, node), node.bounds) if node else (None, None)


def say_to_file(text, path):
    exe = shutil.which("say")
    if exe:
        subprocess.run([exe, "-o", path, "-f", "-"], input=text.encode(), check=False, timeout=60)
        if shutil.which("afconvert") and os.path.exists(path):  # browsers cannot play AIFF; AAC in m4a works everywhere
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", path, path[:-5] + ".m4a"], check=False, timeout=60)


def node_at(snap, bounds, tol=8):
    """The control at these on-screen bounds. Position, not a recorded key path: after a fix the path can change."""
    best = None
    for n in snap.nodes:
        if n.focusable and all(abs(x - y) <= tol for x, y in zip(n.bounds, bounds)):
            best = n
            break
    return best


def announce_at(snap, node):
    # position-in-group ("3 of 23") is meaningless for two standalone toolbar buttons: say role and name only
    return announce(snap, node).split(", ")[0:2] and ", ".join(announce(snap, node).split(", ")[0:2])


def main():
    rep = json.load(open(f"{OUT}/before/report.json"))
    adb = Adb()
    os.makedirs("docs/demo", exist_ok=True)
    # one live look at the fixed app with the Quick actions row visible (drawer collapsed): DOWN, RIGHT from a cold start
    adb.cold_start(PKG, ACT)
    for k in ("DOWN", "RIGHT"):
        adb.key(k)
        time.sleep(0.7)
    time.sleep(1.0)
    after_xml = adb.dump_xml() or ""
    after_snap = parse(after_xml)
    adb.screenshot_png(f"{OUT}/after/witness-row.png")
    rows = []
    for f in rep["findings"]:
        if f["kind"] != "MISSING_LABEL":
            continue
        bsnap = None
        for cand in sorted(os.listdir(f"{OUT}/before/snapshots")):
            xml = open(f"{OUT}/before/snapshots/{cand}").read()
            snap = parse(xml)
            if node_at(snap, f["bounds"]):
                bsnap = snap
                break
        bnode = node_at(bsnap, f["bounds"]) if bsnap else None
        anode = node_at(after_snap, f["bounds"])
        before = announce_at(bsnap, bnode) if bnode else None
        after = announce_at(after_snap, anode) if anode else None
        rows.append({"finding": f["id"], "bounds": f["bounds"], "before": before, "after": after,
                     "source": "before: recorded audit snapshot; after: live dump of the fixed app, control found by on-screen position"})
        for tag, text in (("before", before), ("after", after)):
            if text:
                say_to_file(text, f"docs/demo/announce-{f['id']}-{tag}.aiff")
    json.dump(rows, open("docs/demo/announcements.json", "w"), indent=1)
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
