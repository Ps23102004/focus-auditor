"""Engine report -> dashboard data contract (see web/app.js). Optional pytest JUnit XML gives per-test status;
an optional second report becomes `after`."""
import json, os, shutil
import xml.etree.ElementTree as ET

SEVERITY = {"high": "critical", "medium": "warning", "low": "info"}


def _title(f):
    ev = f.get("evidence") or {}
    if f["kind"] == "TRAP":
        n = len(ev.get("region", []))
        named = [l for l in ev.get("region_labels", []) if l]
        where = f' around "{named[0]}"' if named else ""
        return f"Focus trap{where}: {n} controls, no way out"
    if f["kind"] == "MISSING_LABEL":
        return "Icon-only control without a name" if ev.get("subtype") == "icon_only" else "Control without a name"
    if f["kind"] == "DUPLICATE_LABEL":
        return f'{ev.get("count", "Many")} controls share the name "{ev.get("label", "")}"'
    return f["kind"].replace("_", " ").title()


def _evidence(f, back):
    ev = f.get("evidence") or {}
    if f["kind"] == "TRAP":
        exits = "BACK leaves the screen, but no D-pad direction does" if back.get(f["node_id"]) == "yes" else "No D-pad direction leaves it"
        return f"Every UP, DOWN, LEFT and RIGHT press from these {len(ev.get('region', []))} controls lands back inside. {exits}."
    if f["kind"] == "MISSING_LABEL":
        w, h = ev.get("size", [0, 0])
        return f"Focusable {w}x{h} px with no text, no content description and no named children, so a screen reader has nothing to say."
    if f["kind"] == "DUPLICATE_LABEL":
        return f'A screen reader announces "{ev.get("label", "")}" for {ev.get("count", 0)} different controls.'
    return ev.get("summary", "")


def _statuses(junit_path):
    """test name -> passing|failing|inconclusive from a pytest --junitxml file."""
    if not junit_path or not os.path.exists(junit_path):
        return {}
    text = open(junit_path).read()
    if "<!DOCTYPE" in text or "<!ENTITY" in text:  # we only parse files pytest wrote, but stay safe
        raise ValueError("refusing JUnit XML containing a DTD")
    out = {}
    for case in ET.fromstring(text).iter("testcase"):
        tags = {c.tag for c in case}
        out[case.get("name")] = "failing" if tags & {"failure", "error"} else ("inconclusive" if "skipped" in tags else "passing")
    return out


def convert(report, statuses=None, default_status="failing"):
    statuses = statuses or {}
    back = report.get("back") or {}
    findings = []
    for f in report.get("findings", []):
        ev = f.get("evidence") or {}
        test = f"test_{f['id']}"  # JUnit reports the function name; the file path is kept separately
        node_ids = ev.get("region") or ev.get("members") or [f.get("node_id")]
        findings.append({
            "id": f["id"], "kind": f["kind"], "severity": SEVERITY.get(f.get("severity"), "info"),
            "title": _title(f), "evidence": _evidence(f, back), "bounds": f.get("bounds"),
            "node_ids": [n for n in node_ids if n], "witness": (f.get("witness") or {}).get("keys", []),
            "fix_hint": f.get("fix_hint", ""), "test": test, "test_file": f.get("test_id"), "status": statuses.get(test, default_status),
        })
    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda x: order[x["severity"]])
    counts = (report.get("summary") or {}).get("counts", {})
    cov = report.get("coverage") or {}
    sev = [x["severity"] for x in findings]
    meta = report.get("meta") or {}
    return {
        "meta": {"app": meta.get("app"), "package": meta.get("app"), "device": meta.get("device"),
                 "fa_version": meta.get("fa_version"), "run_id": meta.get("run_id"),
                 "timestamp": meta.get("timestamp"), "fixture": False},
        "verdict": report.get("verdict"),
        "coverage": {"pressed": cov.get("pressed"), "budget": cov.get("budget"), "nodes": cov.get("nodes"),
                     "elapsed_s": cov.get("elapsed_s"), "inconclusive": cov.get("inconclusive_reasons", [])},
        "summary": {"trap": counts.get("TRAP", 0), "missing_label": counts.get("MISSING_LABEL", 0),
                    "duplicate_label": counts.get("DUPLICATE_LABEL", 0), "total": len(findings),
                    "critical": sev.count("critical"), "warning": sev.count("warning"), "info": sev.count("info")},
        "findings": findings,
        "graph": {"nodes": [{"id": n["id"], "label": n.get("label", ""), "bounds": n["bounds"]} for n in report.get("nodes", [])],
                  "edges": report.get("edges", [])},
        "screenshot": "data/screen.png",
        "after": None,
    }


def align_to_screenshot(data, report, report_dir):
    """Boxes must match the screenshot. The screenshot is taken at the trap's entry state (see cli.screenshot_at),
    so redraw DUPLICATE_LABEL groups from that state's snapshot: union of on-screen focusables sharing the label."""
    from .tree import parse, effective_label
    trap = next((f for f in report.get("findings", []) if f["kind"] == "TRAP"), None)
    if not trap:
        return data
    snap_path = os.path.join(report_dir, "snapshots", f"{trap['node_id']}.xml")
    if not os.path.exists(snap_path):
        return data
    with open(snap_path) as fh:
        snap = parse(fh.read())
    for f in data["findings"]:
        if f["kind"] != "DUPLICATE_LABEL":
            continue
        label = next((x["evidence"].get("label") for x in report["findings"] if x["id"] == f["id"]), None)
        boxes = [n.bounds for n in snap.focusables() if effective_label(n, snap) == label]
        if boxes:
            f["bounds"] = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                           max(b[2] for b in boxes), min(1080, max(b[3] for b in boxes))]
            f["on_screen"] = len(boxes)
    return data


def _safe_name(name):
    """Model output is untrusted: 1-40 printable characters, no newlines, no bidi/format controls (str.isprintable
    rejects Cc, Cf, Zl, Zp and non-space Zs)."""
    return isinstance(name, str) and 0 < len(name.strip()) <= 40 and name.isprintable()


def attach_ai(data, suggestions=None, announcements=None, out_dir=None):
    """Attach model-suggested names (untrusted, from fa.ml.labelnames) and before/after announcements
    (rules, from scripts/demo_v2_audio.py) to MISSING_LABEL findings. Audio files are copied next to the data."""
    by_id = {f["id"]: f for f in data["findings"]}
    if suggestions and os.path.exists(suggestions):
        doc = json.load(open(suggestions))
        for rec in doc.get("suggestions", []):
            f = by_id.get(rec.get("finding_id"))
            if f is not None:
                name = rec.get("suggestion")
                f["suggested_name"] = name.strip() if _safe_name(name) else None
                f["suggestion_model"] = doc.get("model")
                f["suggestion_untrusted"] = True
    if announcements and os.path.exists(announcements):
        for row in json.load(open(announcements)):
            f = by_id.get(row.get("finding"))
            if f is None:
                continue
            f["announce_before"], f["announce_after"] = row.get("before"), row.get("after")
            for tag in ("before", "after"):
                src = os.path.join(os.path.dirname(announcements), f"announce-{f['id']}-{tag}.m4a")
                if out_dir and os.path.exists(src):
                    os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)
                    shutil.copyfile(src, os.path.join(out_dir, "audio", os.path.basename(src)))
                    f[f"audio_{tag}"] = f"audio/{os.path.basename(src)}"
    return data


def export(report_path, out_dir, junit=None, after_report=None, after_junit=None, suggestions=None, announcements=None):
    with open(report_path) as fh:
        raw = json.load(fh)
    data = align_to_screenshot(convert(raw, _statuses(junit)), raw, os.path.dirname(report_path))
    base = os.path.basename(os.path.normpath(out_dir)) or "data"  # screenshots must point into THIS data folder
    data["screenshot"] = f"{base}/screen.png"
    attach_ai(data, suggestions, announcements, out_dir)
    if after_report:
        with open(after_report) as fh:
            after = convert(json.load(fh), _statuses(after_junit), default_status="inconclusive")  # no test result = no claim
        after["screenshot"] = f"{base}/screen-after.png"
        # What happened to each BEFORE finding: its frozen test result on the fixed build.
        after_status = _statuses(after_junit)
        after["resolved"] = [{"id": f["id"], "kind": f["kind"], "title": f["title"], "bounds": f["bounds"],
                              "test": f["test"], "status": after_status.get(f["test"], "inconclusive")}
                             for f in data["findings"]]
        data["after"] = after
        # Prefer a screenshot taken at the same witness state as BEFORE (like-for-like map), else the audit's own.
        witness = os.path.join(os.path.dirname(after_report), "screen-witness.png")
        shot = witness if os.path.exists(witness) else os.path.join(os.path.dirname(after_report), "screen.png")
        if os.path.exists(shot):
            shutil.copyfile(shot, os.path.join(out_dir, "screen-after.png"))
    os.makedirs(out_dir, exist_ok=True)
    shot = os.path.join(os.path.dirname(report_path), "screen.png")
    if os.path.exists(shot):
        shutil.copyfile(shot, os.path.join(out_dir, "screen.png"))
    path = os.path.join(out_dir, "report.json")
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1)
    return path
