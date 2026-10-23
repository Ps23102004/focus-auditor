"""python -m fa audit|tests|record-fixture"""
import argparse, json, os, shutil, sys, time

from . import detectors, report as rpt, testgen
from .adb import Adb, AdbError
from .crawl import Crawler, FocusGraph, LiveDevice
from .tree import parse

PKG, ACT = "com.amazonappstore.helloworldtv", ".MainActivity"


def analyze(graph, snaps):
    """FocusGraph + {focused_id: Snapshot} -> findings (pure, shared by live and fixture paths)."""
    biggest = max(snaps.values(), key=lambda s: (len(s.focusables()), s.focused().id), default=None)
    findings = detectors.find_traps(graph, biggest, snaps)
    notes = graph.coverage.setdefault("inconclusive_reasons", [])
    notes[:] = [n for n in notes if not n.startswith("label_unverified")]  # analyze() may run twice on one graph
    findings += detectors.label_issues_across([(s, graph.witness(i) or []) for i, s in sorted(snaps.items())], notes)
    for f in findings:
        f.test_id = f"tests_generated/test_{f.id}.py"
    return findings


def save_fixture(graph, snaps, d):
    os.makedirs(os.path.join(d, "snapshots"), exist_ok=True)
    with open(os.path.join(d, "focus_graph.json"), "w") as fh:
        json.dump(graph.to_json(), fh, indent=2)
    for i, s in snaps.items():
        with open(os.path.join(d, "snapshots", f"{i}.xml"), "w") as fh:
            fh.write(s.raw)


def load_fixture(d):
    with open(os.path.join(d, "focus_graph.json")) as fh:
        graph = FocusGraph.from_json(json.load(fh))
    sd, snaps = os.path.join(d, "snapshots"), {}
    for fn in sorted(os.listdir(sd)):
        if fn.endswith(".xml"):
            with open(os.path.join(sd, fn)) as fh:
                snaps[fn[:-4]] = parse(fh.read())
    return graph, snaps


def live_crawl(args, out):
    adb = Adb(args.serial)
    adb.set_animations_off()
    dev = LiveDevice(adb, args.pkg, args.activity)
    cr = Crawler(dev, entry=args.entry.split(","), max_nodes=args.max_nodes, max_presses=args.max_presses,
                 deadline_s=args.deadline, log=(lambda m: print("  crawl:", m, file=sys.stderr)) if args.verbose else None)
    graph, snaps = cr.run()
    return adb, dev, graph, snaps


def screenshot_at(adb, dev, graph, findings, path):
    """Screenshot of the state that shows the first trap (else the entry focus) so overlays line up."""
    keys = next((f.witness["keys"] for f in findings if f.kind == "TRAP" and f.witness.get("keys")), None)
    dev.cold_start()
    for k in keys if keys is not None else [e[0] for e in graph.entry[:1]]:
        dev.press(k)
    time.sleep(0.5)
    return adb.screenshot_png(path)


def cmd_audit(args):
    out = args.out
    os.makedirs(out, exist_ok=True)
    shot, device = None, ""
    if args.from_fixture:
        graph, snaps = load_fixture(args.from_fixture)
        src = os.path.join(args.from_fixture, "screen.png")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out, "screen.png"))
            shot = "screen.png"
        device = "fixture"
        findings = analyze(graph, snaps)
    else:
        adb, dev, graph, snaps = live_crawl(args, out)
        findings = analyze(graph, snaps)
        device = (adb.shell("getprop", "ro.product.model").strip() or "android") + " " + (adb.serial or "default")
        try:
            shot = os.path.relpath(screenshot_at(adb, dev, graph, findings, os.path.join(out, "screen.png")), out)
        except (AdbError, OSError) as e:
            graph.coverage.setdefault("inconclusive_reasons", []).append(f"screenshot_failed: {e}")
        save_fixture(graph, snaps, out)
    report = rpt.build(graph, findings, app=graph.pkg or args.pkg, device=device, activity=args.activity, screenshot=shot)
    path = rpt.write(report, graph, out)
    c = report["coverage"]
    print(f"verdict={report['verdict']} findings={report['summary']['counts']} icon_only={report['summary']['icon_only']} "
          f"nodes={c.get('nodes')} presses={c.get('pressed')}/{c.get('budget')} elapsed={c.get('elapsed_s')}s -> {path}")
    for r in c.get("inconclusive_reasons", []):
        print("  INCONCLUSIVE:", r)
    for f in findings:
        print(f"  {f.id} {f.kind:15s} {f.severity:6s} {f.evidence.get('summary')}  witness={f.witness.get('keys')}")
    return {"pass": 0, "fail": 1, "inconclusive": 2}[report["verdict"]]


def cmd_tests(args):
    with open(args.report) as fh:
        report = json.load(fh)
    paths = testgen.generate_tests(report, args.out)
    for p in paths:
        print(p)
    print(f"{len(paths)} test file(s) written to {args.out}")
    return 0


def cmd_record(args):
    out = os.path.join(args.out, args.name)
    adb, dev, graph, snaps = live_crawl(args, out)
    findings = analyze(graph, snaps)
    save_fixture(graph, snaps, out)
    try:
        screenshot_at(adb, dev, graph, findings, os.path.join(out, "screen.png"))
    except (AdbError, OSError) as e:
        print("screenshot failed:", e, file=sys.stderr)
    print(f"fixture saved: {out} ({len(snaps)} snapshots, {len(graph.edges)} edges)")
    return 0


def cmd_export_web(args):
    from . import webexport
    path = webexport.export(args.report, args.out, junit=args.junit, after_report=args.after, after_junit=args.after_junit,
                            suggestions=args.suggestions, announcements=args.announcements)
    print(f"dashboard data written to {path}")
    return 0


def cmd_fix(args):
    from . import fixloop
    log = fixloop.fix(args.report, args.app_dir, args.out, agent=args.agent, model=args.model, tests_dir=args.tests, suggestions_path=args.suggestions,
                       backend=args.backend, region=args.aws_region)
    for st in log["steps"]:
        print(f"{st['step']:>8}: {'ok' if st['code'] == 0 else 'FAILED (' + str(st['code']) + ')'}")
    return 0 if log["steps"] and all(s["code"] == 0 for s in log["steps"]) else 1  # a failing post-fix test run is a failed fix


def cmd_announce(args):
    from . import announce
    graph, snaps = load_fixture(args.from_fixture)
    for key, nid, text in announce.witness_sequence(graph, snaps):
        print(f"{key:5s} {nid}  {text}   [{announce.SOURCE}]")
        if args.speak and not announce.speak(text):
            print("  (macOS `say` not available)", file=sys.stderr)
            args.speak = False
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="fa")
    sub = p.add_subparsers(dest="cmd", required=True)

    def live_opts(s):
        s.add_argument("--serial"), s.add_argument("--pkg", default=PKG), s.add_argument("--activity", default=ACT)
        s.add_argument("--entry", default="DOWN", help="comma-separated keys pressed after cold start")
        s.add_argument("--max-nodes", type=int, default=40), s.add_argument("--max-presses", type=int, default=400)
        s.add_argument("--deadline", type=float, default=1500, help="wall-clock seconds")
        s.add_argument("-v", "--verbose", action="store_true")

    a = sub.add_parser("audit")
    a.add_argument("--out", default="out/"), a.add_argument("--from-fixture")
    live_opts(a)
    a.set_defaults(fn=cmd_audit)
    t = sub.add_parser("tests")
    t.add_argument("--report", default="out/report.json"), t.add_argument("--out", default="tests_generated")
    t.set_defaults(fn=cmd_tests)
    r = sub.add_parser("record-fixture")
    r.add_argument("--name", required=True), r.add_argument("--out", default="tests/fixtures")
    live_opts(r)
    r.set_defaults(fn=cmd_record)
    w = sub.add_parser("export-web", help="convert a report into the dashboard data contract")
    w.add_argument("--report", default="out/report.json"), w.add_argument("--out", default="web/data")
    w.add_argument("--junit", help="pytest --junitxml results for the generated tests")
    w.add_argument("--after", help="report.json from the re-audit after the fix")
    w.add_argument("--after-junit")
    w.add_argument("--suggestions", help="name-suggestions.json from fa.ml.labelnames (untrusted model output)")
    w.add_argument("--announcements", help="announcements.json from scripts/demo_v2_audio.py")
    w.set_defaults(fn=cmd_export_web)
    fx = sub.add_parser("fix", help="fix prompt -> coding agent -> build -> install -> rerun generated tests")
    fx.add_argument("--report", default="out/report.json"), fx.add_argument("--app-dir", default="sample-native")
    fx.add_argument("--out", default="fix-run"), fx.add_argument("--agent", default="claude", choices=["claude", "none"])
    fx.add_argument("--suggestions", help="name-suggestions.json from fa.ml.labelnames (untrusted, quoted in the prompt)")
    fx.add_argument("--model", default="sonnet"), fx.add_argument("--tests", default="tests_generated")
    fx.add_argument("--backend", default="anthropic", choices=["anthropic", "bedrock"], help="bedrock: run the agent through Amazon Bedrock (needs AWS credentials in the environment; pass a Bedrock model id such as us.anthropic.claude-haiku-5-5 via --model)")
    fx.add_argument("--aws-region", default=None)
    fx.set_defaults(fn=cmd_fix)
    an = sub.add_parser("announce", help="TalkBack-style announcements (rules, approximates TalkBack, not VoiceView)")
    an.add_argument("--from-fixture", required=True), an.add_argument("--speak", action="store_true")
    an.set_defaults(fn=cmd_announce)
    args = p.parse_args(argv)
    return args.fn(args)
