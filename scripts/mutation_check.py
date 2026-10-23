"""Poor man's mutation test: break one line at a time in a throwaway copy and require the offline suite to fail.
A mutant that survives means the tests do not guard that line. Usage: python scripts/mutation_check.py"""
import os, shutil, subprocess, sys, tempfile

MUTANTS = [
    ("fa/testgen.py", "if not label:", "if False:", "label check: unnamed still passes"),
    ("fa/testgen.py", "    if target is None:\n        _fail(d, f\"no control at {d['bounds']} after replaying {d['keys']}: it was removed or moved\")", "    if False:\n        _fail(d, 'x')", "dup check: deleted cards pass"),
    ("fa/testgen.py", "if not node.focusable:", "if False:", "label check: unfocusable control passes"),
    ("fa/testgen.py", "if len(moved) >= d[\"min_group\"]:", "if False:", "dup check: uniform rename passes"),
    ("fa/cli.py", "all(s[\"code\"] == 0 for s in log[\"steps\"])", "all(s[\"code\"] == 0 for s in log[\"steps\"] if s[\"step\"] != \"tests\")", "fix exits 0 when post-fix tests fail"),
    ("fa/detectors.py", "suspected = suspected or whole_screen", "suspected = suspected", "whole-screen region reported firm"),
    ("fa/crawl.py", "if snap is not None and want and foc is not None and (snap.package != want or (foc.package and foc.package != want)):", "if False:", "foreign app screens recorded as nodes"),
    ("fa/detectors.py", "and back == \"yes\"", "", "modal trap downgraded when BACK cannot leave"),
    ("fa/testgen.py", "    if not new:  # erasing", "    if False:  # erasing", "dup check: erasing every name passes"),
    ("fa/crawl.py", "if len(self.g.nodes) < MIN_NODES:", "if False:", "one-control onboarding screen passes"),
    ("fa/detectors.py", "len(own.focusables()) if own is not None else 0", "0", "whole-screen ignores unreached controls"),
    ("fa/detectors.py", "if foc is None or foc.id != f.node_id:", "if False:", "unnamed-while-focused control not reported"),
    ("fa/detectors.py", "if not _covered_by_named_focus(b):", "if True:", "covered control counted as unverified"),
    ("fa/testgen.py", "if snap is not None and (snap.package != d[\"pkg\"] or (foc is not None and foc.package and foc.package != d[\"pkg\"])):", "if False:", "crash or exit counted as a pass"),
    ("fa/cli.py", "app=graph.pkg or args.pkg", "app=args.pkg", "report names the wrong app on fixture re-analysis"),
    ("fa/crawl.py", "                self._probe_back()\n            unexpanded = [n for n in self.g.nodes if n not in self.expanded]", "                self._probe_back()\n            unexpanded = []", "late-discovered nodes never counted"),
    ("fa/testgen.py", "        if not (f.get(\"witness\") or {}).get(\"keys\"):", "        if False:", "unpassable test generated for a finding with no key path"),
    ("fa/testgen.py", "(foc is not None and foc.package and foc.package != d[\"pkg\"])", "False", "foreign focus in a multi-root snapshot passes"),
    ("fa/tree.py", "if depth > MAX_DEPTH:", "if False:", "deep nesting crashes parser"),
    ("fa/testgen.py", "if node is None:\n        _fail(d, f\"no control at", "if False:\n        _fail(d, f\"no control at", "label check: deleted control passes"),
    ("fa/testgen.py", "if len(same) >= d[\"min_group\"]:", "if False:", "dup check: shared name passes"),
    ("fa/testgen.py", "if _gk(f) not in region:", "if True:", "trap check: any move counts as escape"),
    ("fa/testgen.py", "if not _PKG.match(str(pkg))", "if False and not _PKG.match(str(pkg))", "package injection allowed"),
    ("fa/testgen.py", "if not _ID.match(run_id):", "if False:", "run_id injection allowed"),
    ("fa/fixloop.py", "refused = [p for p in changed if not ALLOWED_CHANGE.match(p)", "refused = [p for p in changed if False and not ALLOWED_CHANGE.match(p)", "gate allows any path"),
    ("fa/fixloop.py", "str(after.get(p, \"\")).startswith(\"symlink:\")", "False", "gate allows symlinks"),
    ("fa/webexport.py", "default_status=\"inconclusive\")  # no test result", "default_status=\"passing\")  # no test result", "after findings pass without evidence"),
    ("fa/webexport.py", "and name.isprintable()", "", "control chars in suggestions"),
    ("fa/webexport.py", "<= 40 and", "<= 4000 and", "suggestion length cap"),
    ("fa/webexport.py", "if \"<!DOCTYPE\" in text or \"<!ENTITY\" in text:", "if False:", "junit DTD allowed"),
    ("fa/report.py", "if coverage.get(\"inconclusive_reasons\") or", "if False and coverage.get(\"inconclusive_reasons\") or", "incomplete audit can pass"),
    ("fa/tree.py", "if re.search(r\"<!\\s*(DOCTYPE|ENTITY)\", xml_text, re.I):", "if False:", "UI dump DTD allowed"),
    ("fa/announce.py", "and snap.nodes[i].bounds != (0, 0, 0, 0)]", "]", "hidden nodes counted in lists"),
    ("fa/announce.py", "\"-f\", \"-\"", "\"-v\", \"Alex\"", "speak text not on stdin"),
]


def pytest_cmd():
    return [sys.executable, "-m", "pytest", "-q", "-x", "-m", "not device", "-p", "no:cacheprovider"]


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = subprocess.run(pytest_cmd(), cwd=root, capture_output=True, text=True)
    if base.returncode != 0:  # a mutant only counts as killed against a green baseline
        sys.exit("baseline suite is not green; refusing to run mutants\n" + base.stdout[-800:])
    survived = []
    for path, old, new, why in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(root, tmp + "/r", ignore=shutil.ignore_patterns(".git", ".venv*", "sample-native", "real-apps*", "demo*", "web", "tv-app", "__pycache__", ".pytest_cache", "out*", "*.png", "*.mp4"))
            f = f"{tmp}/r/{path}"
            src = open(f).read()
            if old not in src:
                print(f"STALE   {path}: {why}  (pattern not found)")
                survived.append(why)
                continue
            open(f, "w").write(src.replace(old, new, 1))
            r = subprocess.run(pytest_cmd(), cwd=f"{tmp}/r", capture_output=True, text=True)
            killed = r.returncode == 1  # 1 = tests failed; 2-5 = collection/usage/internal errors, which prove nothing
            print(("killed  " if killed else "SURVIVED"), path, "-", why)
            if not killed:
                survived.append(why)
    print(f"\n{len(MUTANTS) - len(survived)}/{len(MUTANTS)} mutants killed")
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
