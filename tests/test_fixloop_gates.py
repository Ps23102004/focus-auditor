import os
import pytest
from fa import fixloop


def tree(tmp_path, files):
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return fixloop._tree_hashes(str(tmp_path))


def test_unchanged_tree_has_no_changes(tmp_path):
    t = tree(tmp_path, {"app/src/main/java/A.kt": "a"})
    assert fixloop.sandboxed_changes(t, dict(t)) == ([], [])


@pytest.mark.parametrize("path", ["app/src/main/java/com/x/A.kt", "app/src/main/res/layout/a.xml", "app/src/main/java/B.java"])
def test_allowed_source_edits_pass(path):
    allowed, refused = fixloop.sandboxed_changes({path: "1"}, {path: "2"})
    assert allowed == [path] and refused == []


@pytest.mark.parametrize("path", ["build.gradle", "app/build.gradle", "gradlew", "settings.gradle", "local.properties",
                                  "tests_generated/test_abcdef12.py", ".git/config", "app/src/test/A.kt",
                                  "app/src/main/AndroidManifest.xml.bak", "../escape.kt", "app/src/main/java/../../../x.kt",
                                  "app/src/main/jniLibs/x.so", "app/src/main/assets/x.sh", "gradle/wrapper/gradle-wrapper.jar"])
def test_everything_else_refused(path):
    allowed, refused = fixloop.sandboxed_changes({}, {path: "x"})
    assert path in refused and path not in allowed


def test_deleting_an_allowed_file_is_reported_as_a_change():
    allowed, refused = fixloop.sandboxed_changes({"app/src/main/java/A.kt": "1"}, {})
    assert allowed == ["app/src/main/java/A.kt"]  # deletion is visible so the caller can decide; tests catch removed controls


def test_symlink_replacing_an_allowed_file_is_refused():
    p = "app/src/main/java/A.kt"
    allowed, refused = fixloop.sandboxed_changes({p: "1"}, {p: "symlink:/etc/passwd"})
    assert refused == [p] and allowed == []


def test_tree_hashes_record_file_and_dir_symlinks(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "f.kt").write_text("x")
    os.symlink("/etc", tmp_path / "dlink")
    os.symlink("real/f.kt", tmp_path / "flink")
    h = fixloop._tree_hashes(str(tmp_path))
    assert h["dlink"] == "symlink:/etc" and h["flink"] == "symlink:real/f.kt"
    assert not any(k.startswith("dlink/") for k in h)  # never walked through the link


def test_tree_hash_changes_with_content(tmp_path):
    a = tree(tmp_path, {"f": "1"}); b = tree(tmp_path, {"f": "2"})
    assert a["f"] != b["f"]


def test_copy_ignore_skips_git_and_build_outputs():
    ig = fixloop._COPY_IGNORE("x", [".git", "build", ".gradle", "a.apk", "local.properties", ".idea", "src"])
    assert set(ig) == {".git", "build", ".gradle", "a.apk", "local.properties", ".idea"}


def test_agent_denies_cover_dangerous_tools():
    deny = " ".join(getattr(fixloop, "AGENT_DENY", []))
    for needle in ("rm", "curl", "git"):
        assert needle in deny or "Bash" not in fixloop.AGENT_TOOLS
    assert "Bash" not in fixloop.AGENT_TOOLS


def test_gradle_env_sets_sdk_and_java(monkeypatch):
    for k in ("ANDROID_SDK_ROOT", "ANDROID_HOME", "JAVA_HOME"):
        monkeypatch.delenv(k, raising=False)
    env = fixloop.gradle_env()
    assert env["ANDROID_HOME"] == env["ANDROID_SDK_ROOT"] and "openjdk@17" in env["JAVA_HOME"]
    assert env["PATH"].startswith(env["JAVA_HOME"] + "/bin")


def test_gradle_env_respects_existing_java(monkeypatch):
    monkeypatch.setenv("JAVA_HOME", "/custom/jdk")
    assert fixloop.gradle_env()["JAVA_HOME"] == "/custom/jdk"
