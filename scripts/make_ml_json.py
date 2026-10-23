"""docs/ml/{screen-match,label-eval}.json -> <out>/ml.json in the dashboard's Evidence schema.
Only numbers that exist in the eval files are written; F1 is the mean over test folds; nothing is rounded up."""
import json, os, sys


def screen_match(path):
    s = json.load(open(path))
    folds = s["folds"]
    methods = folds[0]["test_metrics"].keys()
    mean = {m: sum(f["test_metrics"][m]["f1"] for f in folds) / len(folds) for m in methods}
    best = max(mean, key=mean.get)
    n_pairs = sum(f["test_pairs"]["positive"] + f["test_pairs"]["negative_used"] for f in folds)
    net = mean.get("embed")
    if net is not None and mean[best] > net:
        verdict = f"The simple '{best}' check beat the neural network on this data, so the auditor keeps the simple check."
    else:
        verdict = "The neural network matched or beat every rule baseline on this data."
    return {"best_method": best, "best_f1": round(mean[best], 3), "network_f1": None if net is None else round(net, 3),
            "n_pairs": n_pairs, "model": s["meta"].get("model"), "verdict": verdict}


def name_suggestions(path):
    m = json.load(open(path))["metrics"]
    base = {k: v for k, v in m.items() if k != "model"}
    best = max(base, key=lambda k: (base[k]["token_f1"], base[k]["exact_match"]))
    return {"n": m["model"]["n"], "exact_match": m["model"]["exact_match"], "token_f1": m["model"]["token_f1"],
            "abstention_rate": m["model"]["abstention_rate"], "baseline": best,
            "baseline_exact_match": base[best]["exact_match"], "baseline_token_f1": base[best]["token_f1"]}


def main(ml_dir="docs/ml", out="web/data-v2"):
    doc = {"announcements": {"note": "Rules (TalkBack-style), not a device recording."}}
    if os.path.exists(f"{ml_dir}/screen-match.json"):
        doc["screen_match"] = screen_match(f"{ml_dir}/screen-match.json")
    if os.path.exists(f"{ml_dir}/label-eval.json"):
        doc["name_suggestions"] = name_suggestions(f"{ml_dir}/label-eval.json")
    os.makedirs(out, exist_ok=True)
    json.dump(doc, open(f"{out}/ml.json", "w"), indent=1)
    print(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
