"""P0 gate (from the plan review): can we read focus reliably, fast, and repeatably on the buggy sample?
Pass: every dump has exactly one focused node; ids repeat across cold starts; median step <= 1.5 s;
UP/DOWN/LEFT/RIGHT stay inside the planted trap row."""
import hashlib, re, statistics, subprocess, sys, time
import xml.etree.ElementTree as ET

ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"
PKG = "com.amazonappstore.helloworldtv"
ACT = f"{PKG}/.MainActivity"


def adb(*a, timeout=20):
    return subprocess.run([ADB, *a], capture_output=True, text=True, timeout=timeout).stdout


def dump():
    t0 = time.time()
    adb("shell", "uiautomator", "dump", "/sdcard/fa_gate.xml")
    raw = adb("exec-out", "cat", "/sdcard/fa_gate.xml")
    if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
        raise ValueError("DTD in dump")
    root = ET.fromstring(raw[raw.find("<?xml"):])
    return root, time.time() - t0


def q(bounds):  # quantize to 8 px
    nums = [int(x) // 8 for x in re.findall(r"\d+", bounds)]
    return tuple(nums)


def node_id(n, idx):
    key = f'{n.get("class")}|{q(n.get("bounds",""))}|{idx}'
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def focused(root):
    out = []
    for i, n in enumerate(root.iter("node")):
        if n.get("focused") == "true":
            out.append((node_id(n, i), n.get("bounds"), n.get("class").split(".")[-1]))
    return out


def press(k):
    adb("shell", "input", "keyevent", k)
    time.sleep(0.4)


def cold_start():
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "am", "start", "-S", "-n", ACT)
    time.sleep(3.5)


def run_once(label):
    steps, times, ones = [], [], []
    cold_start()
    seq = ["KEYCODE_DPAD_RIGHT", "KEYCODE_DPAD_UP", "KEYCODE_DPAD_UP", "KEYCODE_DPAD_UP", "KEYCODE_DPAD_UP"]
    # walk toward the quick-actions row, then probe all directions 3x
    seq += ["KEYCODE_DPAD_UP", "KEYCODE_DPAD_DOWN", "KEYCODE_DPAD_LEFT", "KEYCODE_DPAD_RIGHT"] * 3
    for k in seq:
        t0 = time.time()
        press(k)
        root, _ = dump()
        f = focused(root)
        times.append(time.time() - t0)
        ones.append(len(f) == 1)
        steps.append((k.replace("KEYCODE_DPAD_", ""), f[0] if f else None))
    print(f"[{label}] steps={len(steps)} one-focused={sum(ones)}/{len(ones)} median_step={statistics.median(times):.2f}s")
    return steps


a = run_once("cold1")
b = run_once("cold2")
same = sum(1 for x, y in zip(a, b) if x[1] and y[1] and x[1][0] == y[1][0])
print(f"ids repeat across cold starts: {same}/{len(a)}")
for k, f in a[-12:]:
    print(" ", k, f)
