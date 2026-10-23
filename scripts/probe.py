"""Focus probe: press D-pad keys over adb, read the focused node via uiautomator, report
focusable nodes, missing labels, and focus transitions. Gate test for Focus Auditor."""
import re, subprocess, sys, xml.etree.ElementTree as ET

ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"


def adb(*a):
    return subprocess.run([ADB, *a], capture_output=True, text=True).stdout


def tree():
    raw = adb("exec-out", "uiautomator", "dump", "/dev/tty")
    i = raw.find("<?xml")
    doc = raw[i:raw.rfind("</hierarchy>") + 12]
    if "<!DOCTYPE" in doc or "<!ENTITY" in doc:  # untrusted app output: no DTDs, so no XXE or entity bombs
        raise ValueError("refusing UI dump containing a DTD")
    return ET.fromstring(doc)


def nodes(root):
    for n in root.iter("node"):
        yield {k: n.get(k, "") for k in ("class", "text", "content-desc", "resource-id",
                                         "focusable", "focused", "clickable", "bounds")}


def label(n):
    return n["text"] or n["content-desc"]


def focused(root):
    return [n for n in nodes(root) if n["focused"] == "true"]


def audit(root, pkg):
    focusables = [n for n in nodes(root) if n["focusable"] == "true" and n["bounds"] != "[0,0][0,0]"]
    unlabeled = [n for n in focusables if not label(n)]
    return focusables, unlabeled


if __name__ == "__main__":
    pkg = sys.argv[1] if len(sys.argv) > 1 else "com.amazonappstore.helloworldtv"
    keys = ["KEYCODE_DPAD_DOWN", "KEYCODE_DPAD_RIGHT", "KEYCODE_DPAD_DOWN", "KEYCODE_DPAD_LEFT",
            "KEYCODE_DPAD_UP", "KEYCODE_DPAD_RIGHT"]
    root = tree()
    f, u = audit(root, pkg)
    print(f"focusable nodes: {len(f)}  unlabeled focusables: {len(u)}")
    for n in u:
        print("  UNLABELED:", n["class"].split(".")[-1], n["resource-id"], n["bounds"])
    print("start focus:", [(label(n), n["bounds"]) for n in focused(root)])
    for k in keys:
        adb("shell", "input", "keyevent", k)
        import time; time.sleep(0.8)
        print(k.replace("KEYCODE_DPAD_", ""), "->", [(label(n) or n["resource-id"] or n["class"].split(".")[-1], n["bounds"]) for n in focused(tree())])
