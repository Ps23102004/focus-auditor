import json, os
from fa import webexport

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "buggy")


def _report():
    with open(os.path.join(FIX, "report.json")) as fh:
        return json.load(fh)


def test_convert_maps_engine_report_to_dashboard_contract():
    d = webexport.convert(_report())
    assert d["verdict"] == "fail"
    assert d["summary"] == {"trap": 1, "missing_label": 2, "duplicate_label": 1, "total": 4,
                            "critical": 1, "warning": 2, "info": 1}
    assert [f["severity"] for f in d["findings"]] == ["critical", "warning", "warning", "info"]
    trap = d["findings"][0]
    assert trap["kind"] == "TRAP" and len(trap["node_ids"]) == 3 and trap["witness"]
    assert all(f["status"] == "failing" for f in d["findings"])
    assert d["coverage"]["inconclusive"], "coverage gaps must reach the dashboard"


def test_junit_statuses_apply(tmp_path):
    rep = _report()
    tid = "test_" + rep["findings"][0]["id"]
    junit = tmp_path / "j.xml"
    junit.write_text(f'<testsuites><testsuite><testcase name="{tid}"/></testsuite></testsuites>')
    d = webexport.convert(rep, webexport._statuses(str(junit)))
    assert {f["test"]: f["status"] for f in d["findings"]}[tid] == "passing"


def test_junit_with_dtd_is_refused(tmp_path):
    bad = tmp_path / "b.xml"
    bad.write_text('<!DOCTYPE x [<!ENTITY a "b">]><testsuites/>')
    try:
        webexport._statuses(str(bad))
    except ValueError:
        return
    raise AssertionError("DTD not refused")


def test_duplicate_box_aligned_to_screenshot_state(tmp_path):
    out = webexport.export(os.path.join(FIX, "report.json"), str(tmp_path))
    with open(out) as fh:
        d = json.load(fh)
    dup = next(f for f in d["findings"] if f["kind"] == "DUPLICATE_LABEL")
    trap = next(f for f in d["findings"] if f["kind"] == "TRAP")
    assert dup.get("on_screen", 0) >= 5
    assert dup["bounds"][1] >= trap["bounds"][3], "duplicate-name box must sit below the trap row, on the cards"


def test_testgen_refuses_unsafe_ids(tmp_path):
    from fa import testgen
    rep = _report()
    rep["findings"][0]["id"] = 'x"""\nimport os; os.system("id")\n"""'
    try:
        testgen.generate_tests(rep, str(tmp_path))
    except ValueError:
        assert not list(tmp_path.iterdir())
        return
    raise AssertionError("unsafe id accepted")


def test_testgen_data_round_trips_hostile_labels(tmp_path):
    import importlib.util
    from fa import testgen
    rep = _report()
    dup = next(f for f in rep["findings"] if f["kind"] == "DUPLICATE_LABEL")
    dup["evidence"]["label"] = '"""); import os; os.system("id"); ("'
    paths = testgen.generate_tests(rep, str(tmp_path))
    p = next(x for x in paths if dup["id"] in x)
    spec = importlib.util.spec_from_file_location("gen", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.DATA["label"] == dup["evidence"]["label"]


def test_attach_ai_marks_suggestions_untrusted_and_rejects_bad_names(tmp_path):
    d = webexport.convert(_report())
    ml = next(f for f in d["findings"] if f["kind"] == "MISSING_LABEL")
    sug = tmp_path / "s.json"
    sug.write_text(json.dumps({"model": "gemma4", "suggestions": [
        {"finding_id": ml["id"], "suggestion": "Search"},
        {"finding_id": "nope", "suggestion": "x" * 500}]}))
    ann = tmp_path / "announcements.json"
    ann.write_text(json.dumps([{"finding": ml["id"], "before": "unlabelled, button", "after": "Search, button"}]))
    (tmp_path / f"announce-{ml['id']}-after.m4a").write_bytes(b"\x00")
    out = tmp_path / "web"
    webexport.attach_ai(d, str(sug), str(ann), str(out))
    assert ml["suggested_name"] == "Search" and ml["suggestion_untrusted"] is True
    assert ml["announce_before"] == "unlabelled, button" and ml["announce_after"] == "Search, button"
    assert ml["audio_after"] == f"audio/announce-{ml['id']}-after.m4a" and (out / ml["audio_after"]).exists()
    assert "audio_before" not in ml


def test_screenshot_paths_follow_the_output_folder(tmp_path):
    out = tmp_path / "data-v2"
    d = json.load(open(webexport.export(os.path.join(FIX, "report.json"), str(out))))
    assert d["screenshot"] == "data-v2/screen.png"
