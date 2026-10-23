"""Report v1: JSON written to out/report.json (+ screen.png, focus_graph.json)."""
import hashlib, json, os, time

from . import __version__

SCHEMA = 1


def verdict(findings, coverage):
    """fail: a confirmed defect. inconclusive: anything we could not observe (never pass). pass: complete and clean."""
    firm = [f for f in findings if f.severity in ("high", "medium") and not f.evidence.get("suspected")]
    if firm:
        return "fail"
    if coverage.get("inconclusive_reasons") or any(f.evidence.get("suspected") for f in findings):
        return "inconclusive"
    return "pass"


def build(graph, findings, app="", device="", activity="", screenshot=None, run_id=None):
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    counts = {}
    for f in findings:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    return {
        "schema_version": SCHEMA,
        "meta": {"app": app or graph.pkg, "activity": activity, "device": device, "timestamp": now,
                 "fa_version": __version__, "run_id": run_id or hashlib.sha1(f"{now}{os.getpid()}".encode()).hexdigest()[:8]},
        "coverage": graph.coverage,
        "nodes": list(graph.nodes.values()),
        "edges": [list(e) for e in graph.edges],
        "entry": [list(e) for e in graph.entry],
        "back": graph.back,
        "findings": [f.to_json() for f in findings],
        "screenshot": screenshot,
        "summary": {"counts": counts, "total": len(findings),
                    "icon_only": sum(1 for f in findings if f.evidence.get("subtype") == "icon_only")},
        "verdict": verdict(findings, graph.coverage),
    }


def write(report, graph, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name, obj in (("report.json", report), ("focus_graph.json", graph.to_json())):
        with open(os.path.join(out_dir, name), "w") as fh:
            json.dump(obj, fh, indent=2)
    return os.path.join(out_dir, "report.json")
