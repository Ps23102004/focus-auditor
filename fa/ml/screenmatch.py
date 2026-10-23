"""Is this the same screen? Replay-matching under self-changing content (rotating banners, clocks).

Methods: tree_exact, tree_struct, jaccard, phash, embed (frozen pretrained image encoder), fused (embed AND struct).

Pair-labelling rule (auto labels, no human): both screens come from the same app.
  * same path (the same key sequence from cold start, different visit)            -> SAME
  * different paths and (focused-node bounds differ OR the focusable-node sets differ by >= 30%,
    i.e. Jaccard of 8px-quantized focusable bounds <= 0.70)                        -> DIFFERENT
  * different paths but same focused bounds and <30% focusable difference         -> ambiguous, SKIPPED
Evaluation never tunes and reports on the same data: thresholds are chosen on one fold (one app, or one half of the
paths when only one app exists) and the metrics are reported on the other fold, in both directions.

python -m fa.ml.screenmatch eval data/ml --out docs/ml     (run with .venv-ml/bin/python)
"""
import argparse, hashlib, itertools, json, os, random, sys, time

from ..tree import TreeError, parse

Q = 8
DIFF_FRACTION = 0.30
NEG_PER_POS = 5          # negatives are subsampled (seeded) to at most this many per positive
METHODS = ("tree_exact", "tree_struct", "jaccard", "phash", "embed", "fused")
SCORED = ("jaccard", "phash", "embed")   # methods with a continuous score + threshold


# ---------- tree features ----------
def _q(b):
    return tuple(v // Q for v in b)


def tree_exact(snap):
    return hashlib.sha1(repr([(n.cls, n.bounds, n.text) for n in snap.nodes]).encode()).hexdigest()


def focus_set(snap):
    return frozenset(_q(n.bounds) for n in snap.focusables())


def tree_struct(snap):
    return hashlib.sha1(repr(sorted((n.cls, _q(n.bounds)) for n in snap.focusables())).encode()).hexdigest()


def jaccard(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def focused_bounds(snap):
    f = snap.focused()
    return f.bounds if f else None


# ---------- image features ----------
def phash(img, size=32, keep=8):
    """64-bit DCT perceptual hash (int). img: PIL image."""
    import numpy as np
    g = np.asarray(img.convert("L").resize((size, size)), dtype="float64")
    k = np.arange(size)
    dct = np.cos(np.pi * (k[None, :] + 0.5) * k[:, None] / size)   # DCT-II basis
    low = (dct @ g @ dct.T)[:keep, :keep].ravel()
    bits = low > np.median(low[1:])                                 # ignore DC when picking the median
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a, b):
    return bin(a ^ b).count("1")


class Encoder:
    """Frozen pretrained image encoder -> L2-normalised vector. Records the model and device that really ran."""

    def __init__(self, prefer_dinov2=False):
        import torch, torchvision
        self.torch = torch
        self.name, model = None, None
        if prefer_dinov2:   # runs repo code from GitHub's hubconf: opt-in only
            try:
                model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", trust_repo=True)
                self.name, self.size = "dinov2_vits14", 224
            except Exception as e:   # noqa: BLE001 - any failure -> torchvision fallback, recorded
                print(f"dinov2 unavailable ({type(e).__name__}); falling back to torchvision", file=sys.stderr)
        if model is None:
            m = torchvision.models.mobilenet_v3_small(weights="DEFAULT")
            model = torch.nn.Sequential(m.features, m.avgpool, torch.nn.Flatten())
            self.name, self.size = "torchvision mobilenet_v3_small (ImageNet)", 224
        self.model = model.eval()
        self.device = "cpu"
        if torch.backends.mps.is_available():
            try:
                from PIL import Image
                self.model.to("mps")
                self.device = "mps"
                self._run(Image.new("RGB", (64, 64)))   # warm-up proves the device works
            except Exception:   # noqa: BLE001
                self.model.to("cpu")
                self.device = "cpu"

    def _prep(self, img):
        import numpy as np
        a = np.asarray(img.convert("RGB").resize((self.size, self.size)), dtype="float32") / 255.0
        a = (a - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        return self.torch.from_numpy(a.astype("float32")).permute(2, 0, 1)[None]

    def _run(self, img):
        with self.torch.inference_mode():
            v = self.model(self._prep(img).to(self.device)).flatten(1)
            v = self.torch.nn.functional.normalize(v, dim=1)
        return v[0].cpu().numpy()

    def __call__(self, img):
        return self._run(img)


# ---------- dataset ----------
def load_items(root):
    """Every complete (png + parsable xml + meta) record under root/<app>/. Returns list of dicts."""
    items = []
    for app in sorted(os.listdir(root)):
        d = os.path.join(root, app)
        mp = os.path.join(d, "meta.jsonl")
        if not os.path.isfile(mp):
            continue
        for line in open(mp):
            try:
                m = json.loads(line)
                png, xml = (os.path.join(d, m["id"] + e) for e in (".png", ".xml"))
                if not (os.path.isfile(png) and os.path.isfile(xml)):
                    continue
                snap = parse(open(xml).read())
            except (ValueError, KeyError, TreeError, OSError):
                continue
            items.append({"id": m["id"], "set": app, "path": tuple(m["path"]), "visit": m["visit"], "png": png, "snap": snap})
    return items


def pair_label(a, b):
    """1 = same screen, 0 = different screen, None = ambiguous (skipped). See module docstring for the rule."""
    if a["set"] != b["set"]:
        return None
    if a["path"] == b["path"]:
        return 1
    if focused_bounds(a["snap"]) != focused_bounds(b["snap"]):
        return 0
    if 1 - jaccard(focus_set(a["snap"]), focus_set(b["snap"])) >= DIFF_FRACTION:
        return 0
    return None


def build_pairs(items, seed=0):
    """-> (pairs [(a, b, label)], counts). Negatives subsampled to NEG_PER_POS x positives, seeded."""
    pos, neg, amb = [], [], 0
    for a, b in itertools.combinations(items, 2):
        y = pair_label(a, b)
        if y == 1:
            pos.append((a, b, 1))
        elif y == 0:
            neg.append((a, b, 0))
        elif a["set"] == b["set"]:
            amb += 1
    n_neg = len(neg)
    cap = max(NEG_PER_POS * len(pos), 1)
    if len(neg) > cap:
        neg = random.Random(seed).sample(neg, cap)
    return pos + neg, {"positive": len(pos), "negative_total": n_neg, "negative_used": len(neg), "ambiguous_skipped": amb}


def make_folds(items):
    """[(calibration_filter, test_filter, name)]: by app when >=2 apps have positives, else by path halves."""
    apps = sorted({i["set"] for i in items})
    with_pos = [a for a in apps if any(x["set"] == a and x["visit"] > 0 for x in items)]
    if len(with_pos) >= 2:
        f = lambda s: (lambda a, b: a["set"] == s)
        return [(f(x), f(y), f"calibrate on {x}, report on {y}") for x, y in itertools.permutations(with_pos[:2])]
    paths = sorted({i["path"] for i in items})
    half = {p: k % 2 for k, p in enumerate(paths)}
    f = lambda h: (lambda a, b: half[a["path"]] == h and half[b["path"]] == h)
    return [(f(0), f(1), "calibrate on even-indexed paths, report on odd"), (f(1), f(0), "calibrate on odd-indexed paths, report on even")]


# ---------- metrics ----------
def roc_auc(y, s):
    """Rank-based AUC with tie handling (Mann-Whitney U). None if a class is missing."""
    pos = [v for v, t in zip(s, y) if t == 1]
    neg = [v for v, t in zip(s, y) if t == 0]
    if not pos or not neg:
        return None
    u = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return u / (len(pos) * len(neg))


def prf(y, pred):
    tp = sum(1 for t, p in zip(y, pred) if t == 1 and p)
    fp = sum(1 for t, p in zip(y, pred) if t == 0 and p)
    fn = sum(1 for t, p in zip(y, pred) if t == 1 and not p)
    tn = sum(1 for t, p in zip(y, pred) if t == 0 and not p)
    pr = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f1 = 2 * pr * rc / (pr + rc) if pr and rc else (0.0 if pr is not None and rc is not None else None)
    return {"precision": pr, "recall": rc, "f1": f1, "false_merge_rate": fp / (fp + tn) if fp + tn else None,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def pick_threshold(y, s):
    """Threshold (predict same if score >= t) maximising F1 on the calibration fold; ties -> fewer false merges, then higher t."""
    best = None
    for t in sorted(set(s)):
        m = prf(y, [v >= t for v in s])
        key = (m["f1"] or 0.0, -(m["false_merge_rate"] or 0.0), t)
        if best is None or key > best[0]:
            best = (key, t)
    return best[1] if best else None


# ---------- evaluation ----------
def featurize(items, encoder=None):
    """Per-item features + per-image latencies (ms)."""
    from PIL import Image
    lat = {"tree_parse+hash": [], "phash": [], "embed": []}
    for it in items:
        t = time.perf_counter()
        s = it["snap"]
        it["f_exact"], it["f_struct"], it["f_set"] = tree_exact(s), tree_struct(s), focus_set(s)
        lat["tree_parse+hash"].append((time.perf_counter() - t) * 1000)
        with Image.open(it["png"]) as im:
            im.load()
            t = time.perf_counter()
            it["f_phash"] = phash(im)
            lat["phash"].append((time.perf_counter() - t) * 1000)
            if encoder:
                t = time.perf_counter()
                it["f_embed"] = encoder(im)
                lat["embed"].append((time.perf_counter() - t) * 1000)
    return {k: (sum(v) / len(v) if v else None) for k, v in lat.items()}


def pair_scores(a, b):
    import numpy as np
    return {"tree_exact": float(a["f_exact"] == b["f_exact"]), "tree_struct": float(a["f_struct"] == b["f_struct"]),
            "jaccard": jaccard(a["f_set"], b["f_set"]), "phash": 1 - hamming(a["f_phash"], b["f_phash"]) / 64,
            "embed": float(np.dot(a["f_embed"], b["f_embed"])) if "f_embed" in a else None}


def evaluate(items, encoder=None, seed=0):
    lat = featurize(items, encoder)
    methods = [m for m in METHODS if encoder or m not in ("embed", "fused")]
    result = {"folds": [], "latency_ms_per_image": lat}
    for cal_f, test_f, name in make_folds(items):
        out = {"name": name}
        for role, flt in (("calibration", cal_f), ("test", test_f)):
            sub = [i for i in items if flt(i, i)]
            pairs, counts = build_pairs(sub, seed)
            out[role] = {"images": len(sub), "pairs": counts,
                         "scores": [(pair_scores(a, b), y) for a, b, y in pairs]}
        cal, test = out.pop("calibration"), out.pop("test")
        ycal = [y for _, y in cal["scores"]]
        yt = [y for _, y in test["scores"]]
        res, thr = {}, {}
        for m in SCORED:
            if m in methods:
                thr[m] = pick_threshold(ycal, [sc[m] for sc, _ in cal["scores"]]) if ycal else None
        for m in methods:
            if not yt:
                continue
            if m == "fused":
                pred = [sc["embed"] >= thr["embed"] and sc["tree_struct"] == 1 for sc, _ in test["scores"]]
                r = prf(yt, pred)
                r["auc"], r["threshold"] = None, {"embed": thr["embed"], "tree_struct": "equal"}
            elif m in SCORED:
                s = [sc[m] for sc, _ in test["scores"]]
                r = prf(yt, [v >= thr[m] for v in s]) if thr[m] is not None else {}
                r["auc"], r["threshold"] = roc_auc(yt, s), thr[m]
            else:
                r = prf(yt, [sc[m] == 1 for sc, _ in test["scores"]])
                r["auc"], r["threshold"] = None, "exact hash equality"
            res[m] = r
        out["calibration_pairs"] = {"images": cal["images"], **cal["pairs"]}
        out["test_pairs"] = {"images": test["images"], **test["pairs"]}
        out["test_metrics"] = res
        result["folds"].append(out)
    return result


def verdict(result):
    """One plain sentence from the numbers: best mean F1 over folds, ties -> lower false-merge, then simpler method."""
    rows = []
    for m in METHODS:
        fs = [f["test_metrics"][m] for f in result["folds"] if m in f.get("test_metrics", {})]
        if fs and all(x.get("f1") is not None for x in fs):
            rows.append((sum(x["f1"] for x in fs) / len(fs), -sum(x["false_merge_rate"] or 0 for x in fs) / len(fs), -METHODS.index(m), m))
    if not rows:
        return "No method could be scored (not enough labelled pairs yet)."
    f1, fm, _, m = max(rows)
    few = min(f["test_pairs"]["positive"] + f["test_pairs"]["negative_used"] for f in result["folds"])
    warn = f"WARNING: only {few} test pairs in the smaller fold, ranking is not statistically meaningful. " if few < 60 else ""
    simple = {"tree_exact", "tree_struct", "jaccard", "phash"}
    return (warn + f"Best mean test F1 is `{m}` ({f1:.3f}, mean false-merge rate {abs(fm):.3f})."
            + (" A simple non-neural method wins; the neural encoder is not needed on this data." if m in simple
               else " The neural encoder (alone or fused) beats the simple methods on this data."))


def to_md(result, meta):
    f = lambda v: "-" if v is None else f"{v:.3f}"
    L = ["# Screen matching: same screen under self-changing content", "",
         f"Encoder: {meta['model']} on {meta['device']}. Images: {meta['images']} from {', '.join(meta['sets'])}. "
         "Labels are automatic (rule in `fa/ml/screenmatch.py`); thresholds are chosen on one fold and reported on the other.", "",
         "Pair labels (automatic): same path = SAME; different paths = DIFFERENT only if the focused-node bounds differ OR the "
         f"focusable-node sets differ by >= {int(DIFF_FRACTION * 100)}% (Jaccard of {Q}px-quantized bounds <= {1 - DIFF_FRACTION:.2f}); "
         f"other cross-path pairs are ambiguous and skipped. Different-screen pairs are subsampled (seeded) to at most {NEG_PER_POS}x the same-screen pairs.", "",
         f"**{verdict(result)}**", ""]
    for fold in result["folds"]:
        t = fold["test_pairs"]
        L += [f"## {fold['name']}", "",
              f"Test pairs: {t['positive']} same, {t['negative_used']} different (of {t['negative_total']}), "
              f"{t['ambiguous_skipped']} ambiguous skipped; {t['images']} images. "
              f"Calibration pairs: {fold['calibration_pairs']['positive']} same, {fold['calibration_pairs']['negative_used']} different.", "",
              "| method | AUC | threshold | precision | recall | F1 | false-merge rate |", "|---|---|---|---|---|---|---|"]
        for m, r in fold["test_metrics"].items():
            th = r["threshold"]
            th = f"{th:.3f}" if isinstance(th, float) else (json.dumps(th) if isinstance(th, dict) else th)
            L.append(f"| {m} | {f(r.get('auc'))} | {th} | {f(r.get('precision'))} | {f(r.get('recall'))} | {f(r.get('f1'))} | {f(r.get('false_merge_rate'))} |")
        L.append("")
    lat = result["latency_ms_per_image"]
    L += ["## Per-image latency (mean, ms)", "", "| step | ms |", "|---|---|"]
    L += [f"| {k} | {f(v)} |" for k, v in lat.items()]
    return "\n".join(L) + "\n"


def cmd_eval(args):
    items = load_items(args.root)
    enc = None if args.no_embed else Encoder(prefer_dinov2=args.try_dinov2)
    res = evaluate(items, enc, args.seed)
    meta = {"model": enc.name if enc else None, "device": enc.device if enc else None, "images": len(items),
            "sets": sorted({i["set"] for i in items}), "neg_per_pos_cap": NEG_PER_POS, "seed": args.seed}
    res["meta"] = meta
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "screen-match.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    with open(os.path.join(args.out, "screen-match.md"), "w") as fh:
        fh.write(to_md(res, meta))
    print(to_md(res, meta))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="fa.ml.screenmatch")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval")
    e.add_argument("root"), e.add_argument("--out", default="docs/ml"), e.add_argument("--seed", type=int, default=0)
    e.add_argument("--no-embed", action="store_true"), e.add_argument("--try-dinov2", action="store_true", help="run dinov2 hub code from GitHub (opt-in)")
    e.set_defaults(fn=cmd_eval)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
