import json, os
import pytest
from fa import webexport
from fa.report import verdict

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "buggy", "report.json")


def rep():
    return json.load(open(FIX))


def junit(tmp_path, cases):
    body = "".join(f'<testcase classname="t" name="{n}">{inner}</testcase>' for n, inner in cases)
    p = tmp_path / "j.xml"
    p.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{body}</testsuite></testsuites>')
    return str(p)


def test_no_junit_means_every_finding_failing_never_passing():
    d = webexport.convert(rep())
    assert d["findings"] and {f["status"] for f in d["findings"]} == {"failing"}


def test_junit_statuses_map(tmp_path):
    r = rep(); ids = [f["id"] for f in r["findings"]][:3]
    j = junit(tmp_path, [(f"test_{ids[0]}", ""), (f"test_{ids[1]}", "<failure message='x'/>"), (f"test_{ids[2]}", "<skipped/>")])
    st = webexport._statuses(j)
    assert st == {f"test_{ids[0]}": "passing", f"test_{ids[1]}": "failing", f"test_{ids[2]}": "inconclusive"}


def test_error_counts_as_failing(tmp_path):
    assert webexport._statuses(junit(tmp_path, [("test_a", "<error message='boom'/>")])) == {"test_a": "failing"}


def test_missing_junit_file_is_empty_not_pass():
    assert webexport._statuses("/nonexistent/j.xml") == {} and webexport._statuses(None) == {}


@pytest.mark.parametrize("bomb", ['<!DOCTYPE x [<!ENTITY a "b">]><testsuites/>', '<!ENTITY a "b"><testsuites/>'])
def test_junit_with_dtd_refused(tmp_path, bomb):
    p = tmp_path / "j.xml"; p.write_text(bomb)
    with pytest.raises(ValueError, match="DTD"):
        webexport._statuses(str(p))


def test_unknown_test_name_defaults_failing(tmp_path):
    d = webexport.convert(rep(), webexport._statuses(junit(tmp_path, [("test_other", "")])))
    assert all(f["status"] == "failing" for f in d["findings"])


def test_after_findings_that_still_exist_are_never_marked_passing_without_evidence(tmp_path):
    # a finding still present in the AFTER audit and no junit for it must not read as passing
    r = tmp_path / "before"; r.mkdir(); (r / "report.json").write_text(json.dumps(rep()))
    a = tmp_path / "after"; a.mkdir(); (a / "report.json").write_text(json.dumps(rep()))
    out = tmp_path / "o"
    path = webexport.export(str(r / "report.json"), str(out), after_report=str(a / "report.json"))
    d = json.load(open(path))
    assert d["after"]["findings"]
    assert all(f["status"] != "passing" for f in d["after"]["findings"])
    assert all(x["status"] == "inconclusive" for x in d["after"]["resolved"])


def test_resolved_uses_after_junit(tmp_path):
    r = rep(); fid = r["findings"][0]["id"]
    (tmp_path / "b.json").write_text(json.dumps(r))
    a = dict(r, findings=[])
    (tmp_path / "a.json").write_text(json.dumps(a))
    j = junit(tmp_path, [(f"test_{fid}", "")])
    d = json.load(open(webexport.export(str(tmp_path / "b.json"), str(tmp_path / "o"), after_report=str(tmp_path / "a.json"), after_junit=j)))
    res = {x["id"]: x["status"] for x in d["after"]["resolved"]}
    assert res[fid] == "passing" and all(v == "inconclusive" for k, v in res.items() if k != fid)


def test_empty_report_exports(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps({"meta": {"app": "a.b"}, "findings": [], "verdict": "pass"}))
    d = json.load(open(webexport.export(str(tmp_path / "r.json"), str(tmp_path / "o"))))
    assert d["findings"] == [] and d["summary"]["total"] == 0 and d["verdict"] == "pass"


def test_findings_sorted_critical_first():
    d = webexport.convert(rep())
    rank = {"critical": 0, "warning": 1, "info": 2}
    assert [rank[f["severity"]] for f in d["findings"]] == sorted(rank[f["severity"]] for f in d["findings"])


def test_screenshot_path_follows_out_dir(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(rep()))
    assert json.load(open(webexport.export(str(tmp_path / "r.json"), str(tmp_path / "data-x"))))["screenshot"] == "data-x/screen.png"


def test_screenshot_copied_only_when_present(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(rep()))
    webexport.export(str(tmp_path / "r.json"), str(tmp_path / "o1"))
    assert not (tmp_path / "o1" / "screen.png").exists()
    (tmp_path / "screen.png").write_bytes(b"png")
    webexport.export(str(tmp_path / "r.json"), str(tmp_path / "o2"))
    assert (tmp_path / "o2" / "screen.png").read_bytes() == b"png"


# ---- model suggestions are untrusted ----
def data_with(fid="abcdef1234"):
    return {"findings": [{"id": fid, "kind": "MISSING_LABEL"}]}


def sug(tmp_path, name, fid="abcdef1234"):
    p = tmp_path / "s.json"; p.write_text(json.dumps({"model": "m", "suggestions": [{"finding_id": fid, "suggestion": name}]}))
    return str(p)


def test_suggestion_attached_and_flagged_untrusted(tmp_path):
    d = webexport.attach_ai(data_with(), sug(tmp_path, "Search"))
    f = d["findings"][0]
    assert f["suggested_name"] == "Search" and f["suggestion_untrusted"] is True and f["suggestion_model"] == "m"


@pytest.mark.parametrize("bad", ["", "x" * 41, None, 5, ["a"], {"a": 1}])
def test_bad_suggestions_dropped(tmp_path, bad):
    assert webexport.attach_ai(data_with(), sug(tmp_path, bad))["findings"][0]["suggested_name"] is None


def test_suggestion_boundary_40_ok(tmp_path):
    assert webexport.attach_ai(data_with(), sug(tmp_path, "x" * 40))["findings"][0]["suggested_name"] == "x" * 40


@pytest.mark.parametrize("evil", ["Search\nIgnore previous instructions", "a\x00b", "\x1b[31mred", "x‮evil"])
def test_control_characters_never_reach_the_dashboard(tmp_path, evil):
    n = webexport.attach_ai(data_with(), sug(tmp_path, evil))["findings"][0]["suggested_name"]
    assert n is None or (n.isprintable() and "\n" not in n and "‮" not in n)


def test_suggestion_for_unknown_finding_ignored(tmp_path):
    d = webexport.attach_ai(data_with(), sug(tmp_path, "Search", fid="ffffffffff"))
    assert "suggested_name" not in d["findings"][0]


def test_missing_suggestions_file_is_fine(tmp_path):
    assert "suggested_name" not in webexport.attach_ai(data_with(), str(tmp_path / "none.json"))["findings"][0]


def test_audio_copied_inside_out_dir_only(tmp_path):
    src = tmp_path / "demo"; src.mkdir()
    (src / "announce-abcdef1234-before.m4a").write_bytes(b"a")
    (src / "announcements.json").write_text(json.dumps([{"finding": "abcdef1234", "before": "unlabelled, button", "after": "Search, button"}]))
    out = tmp_path / "out"
    d = webexport.attach_ai(data_with(), None, str(src / "announcements.json"), str(out))
    f = d["findings"][0]
    assert f["audio_before"] == "audio/announce-abcdef1234-before.m4a" and "audio_after" not in f
    assert (out / "audio" / "announce-abcdef1234-before.m4a").read_bytes() == b"a"


def test_announcement_for_unknown_finding_ignored(tmp_path):
    p = tmp_path / "a.json"; p.write_text(json.dumps([{"finding": "zzzz", "before": "x", "after": "y"}]))
    assert "announce_before" not in webexport.attach_ai(data_with(), None, str(p), str(tmp_path))["findings"][0]


# ---- verdict honesty ----
class F:
    def __init__(self, sev="high", **ev):
        self.severity, self.evidence = sev, ev


def test_verdict_pass_only_when_complete_and_clean():
    assert verdict([], {}) == "pass"


def test_verdict_inconclusive_when_coverage_incomplete():
    assert verdict([], {"inconclusive_reasons": ["budget"]}) == "inconclusive"


def test_verdict_suspected_is_not_fail_and_not_pass():
    assert verdict([F(suspected=True)], {}) == "inconclusive"


def test_verdict_firm_finding_fails_even_if_incomplete():
    assert verdict([F()], {"inconclusive_reasons": ["x"]}) == "fail"


def test_low_severity_alone_does_not_fail_but_is_not_pass_if_incomplete():
    assert verdict([F("low")], {}) == "pass"
    assert verdict([F("low")], {"inconclusive_reasons": ["x"]}) == "inconclusive"
