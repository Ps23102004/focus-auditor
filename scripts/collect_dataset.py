"""Collect (screenshot, accessibility tree) pairs for offline ML evaluation.
Random D-pad walks from a cold start; every path is revisited three times with different settle delays so
self-changing screens (rotating banners) give genuine same-screen pairs. Different paths give different-screen
pairs. Output: <out>/<name>/{id.png,id.xml,meta.jsonl}. D-pad only, no CENTER/BACK, so nothing is purchased/played."""
import argparse, json, os, random, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fa.adb import Adb

KEYS = ["UP", "DOWN", "LEFT", "RIGHT"]
WAITS = [0.5, 3.5, 7.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True), ap.add_argument("--activity", default=".MainActivity")
    ap.add_argument("--name", required=True), ap.add_argument("--out", default="data/ml")
    ap.add_argument("--paths", type=int, default=30), ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-len", type=int, default=8), ap.add_argument("--deadline", type=float, default=2400)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    adb = Adb()
    adb.set_animations_off()
    d = os.path.join(a.out, a.name)
    os.makedirs(d, exist_ok=True)
    meta = open(os.path.join(d, "meta.jsonl"), "a")
    t0 = time.time()
    # bias toward DOWN/RIGHT so walks reach content, but keep UP/LEFT for variety
    pool = ["DOWN"] * 3 + ["RIGHT"] * 3 + ["UP", "LEFT"]
    seen_paths = set()
    for pi in range(a.paths):
        path = tuple(rng.choice(pool) for _ in range(rng.randint(1, a.max_len)))
        if path in seen_paths:
            continue
        seen_paths.add(path)
        for vi, wait in enumerate(WAITS):
            if time.time() - t0 > a.deadline:
                print("deadline reached", file=sys.stderr)
                return
            adb.cold_start(a.pkg, a.activity)
            for k in path:
                adb.key(k)
                time.sleep(0.5)
            time.sleep(wait)
            sid = f"p{pi:03d}v{vi}"
            shot = adb.screenshot_png(os.path.join(d, sid + ".png"))
            xml = adb.dump_xml()
            if not xml or not shot:
                print("capture failed", sid, file=sys.stderr)
                continue
            with open(os.path.join(d, sid + ".xml"), "w") as fh:
                fh.write(xml)
            meta.write(json.dumps({"id": sid, "app": a.pkg, "path": list(path), "visit": vi, "wait": wait,
                                   "t": time.time() - t0}) + "\n")
            meta.flush()
        print(f"path {pi} done ({len(path)} keys) {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
