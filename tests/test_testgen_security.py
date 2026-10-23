import ast, copy, json, os
import pytest
from fa import testgen

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "buggy", "report.json")


def rep():
    return json.load(open(FIX))


def test_every_generated_file_is_valid_python(tmp_path):
    paths = testgen.generate_tests(rep(), str(tmp_path))
    assert paths
    for p in paths:
        ast.parse(open(p).read())


@pytest.mark.parametrize("rid", ["../x", "abc'; import os", "ABCDEF12", "", "12", "a" * 17, "abc def1", "abc\ndef123"])
def test_bad_run_id_refused(tmp_path, rid):
    r = rep(); r["meta"]["run_id"] = rid
    with pytest.raises(ValueError, match="run_id"):
        testgen.generate_tests(r, str(tmp_path))
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("fid", ["../../etc/x", "a b c d e f", "ZZZZZZZZ", "abcdef12'; os.system('x')", "abc"])
def test_bad_finding_id_refused(tmp_path, fid):
    r = rep(); r["findings"][0]["id"] = fid
    with pytest.raises(ValueError):
        testgen.generate_tests(r, str(tmp_path))


@pytest.mark.parametrize("kind", ["trap", "TRAP\n", "EXEC", "", "TRAP; x"])
def test_bad_kind_refused(tmp_path, kind):
    r = rep(); r["findings"][0]["kind"] = kind
    with pytest.raises(ValueError):
        testgen.generate_tests(r, str(tmp_path))


@pytest.mark.parametrize("pkg", ["a;b", "a.b c", "1a.b", "a", "a..b", "a.b'\"", "$(id).x"])
def test_bad_package_refused(tmp_path, pkg):
    r = rep(); r["meta"]["app"] = pkg
    with pytest.raises(ValueError, match="refusing target"):
        testgen.generate_tests(r, str(tmp_path))


@pytest.mark.parametrize("act", [".Main Activity", ".M;x", "$(id)", "a/b", ".a-b"])
def test_bad_activity_refused(tmp_path, act):
    r = rep(); r["meta"]["activity"] = act
    with pytest.raises(ValueError, match="refusing target"):
        testgen.generate_tests(r, str(tmp_path))


@pytest.mark.parametrize("keys", [["UP", "HOME"], ["up"], ["DOWN; reboot"], ["POWER"], [""], [None]])
def test_bad_witness_keys_refused(tmp_path, keys):
    r = rep(); r["findings"][0]["witness"]["keys"] = keys
    with pytest.raises(ValueError, match="witness keys"):
        testgen.generate_tests(r, str(tmp_path))


def test_hostile_label_cannot_break_out_of_the_data_literal(tmp_path):
    r = rep()
    dup = next((f for f in r["findings"] if f["kind"] == "DUPLICATE_LABEL"), None)
    assert dup is not None
    evil = '"""\nimport os; os.system("touch /tmp/pwned")\n"""\'\\'
    dup["evidence"]["label"] = evil
    paths = testgen.generate_tests(r, str(tmp_path))
    src = open(next(p for p in paths if dup["id"] in p)).read()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "system"]
    assert not calls, "label escaped the data literal"
    ns = {}
    data_line = next(l for l in src.splitlines() if l.startswith("DATA ="))
    exec("import json\n" + data_line, ns)
    assert ns["DATA"]["label"] == evil


def test_old_generated_tests_are_removed_but_other_files_kept(tmp_path):
    (tmp_path / "test_old.py").write_text("x")
    (tmp_path / "notes.txt").write_text("keep")
    testgen.generate_tests(rep(), str(tmp_path))
    assert not (tmp_path / "test_old.py").exists() and (tmp_path / "notes.txt").exists()


def test_generated_test_carries_no_assertion_logic(tmp_path):
    src = open(testgen.generate_tests(rep(), str(tmp_path))[0]).read()
    assert "assert" not in src.replace("testgen.check", "")


def test_generated_data_uses_geometry_not_ids_for_targets(tmp_path):
    for p in testgen.generate_tests(rep(), str(tmp_path)):
        src = open(p).read()
        data = json.loads(ast.literal_eval(next(l for l in src.splitlines() if l.startswith("DATA =")).split("json.loads(", 1)[1][:-1]))
        assert "target_geo" in data and len(data["target_geo"][1]) == 4


def test_generation_is_deterministic(tmp_path):
    a = [open(p).read() for p in testgen.generate_tests(rep(), str(tmp_path / "a"))]
    b = [open(p).read() for p in testgen.generate_tests(rep(), str(tmp_path / "b"))]
    assert a == b


def test_finding_without_a_recorded_key_path_gets_no_unpassable_test(tmp_path, capsys):
    """Judge-found: a control discovered only in the scroll pass has no witness; a replay test could never pass."""
    r = rep()
    r["findings"][1]["witness"]["keys"] = []
    paths = testgen.generate_tests(r, str(tmp_path))
    assert len(paths) == len(r["findings"]) - 1
    assert r["findings"][1]["id"] not in " ".join(paths)
    assert "no recorded key path" in capsys.readouterr().err
