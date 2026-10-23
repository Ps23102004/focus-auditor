import pytest
from fa import fixloop


def test_anthropic_backend_clears_bedrock_flag():
    env = fixloop.agent_env("anthropic", {"CLAUDE_CODE_USE_BEDROCK": "1", "PATH": "/bin"})
    assert "CLAUDE_CODE_USE_BEDROCK" not in env and env["PATH"] == "/bin"


@pytest.mark.parametrize("base", [{}, {"AWS_ACCESS_KEY_ID": "x"}, {"AWS_SECRET_ACCESS_KEY": "y"}, {"AWS_REGION": "us-east-1"}])
def test_bedrock_without_credentials_refuses_before_any_call(base):
    with pytest.raises(ValueError, match="No call was made"):
        fixloop.agent_env("bedrock", base)


@pytest.mark.parametrize("creds", [{"AWS_PROFILE": "p"}, {"AWS_BEARER_TOKEN_BEDROCK": "t"},
                                   {"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b"}])
def test_bedrock_with_any_credential_form_sets_flag_and_region(creds):
    env = fixloop.agent_env("bedrock", dict(creds))
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1" and env["AWS_REGION"] == "us-east-1"


def test_bedrock_region_precedence_arg_over_env():
    assert fixloop.agent_env("bedrock", {"AWS_PROFILE": "p", "AWS_REGION": "eu-west-1"}, region="us-west-2")["AWS_REGION"] == "us-west-2"
    assert fixloop.agent_env("bedrock", {"AWS_PROFILE": "p", "AWS_REGION": "eu-west-1"})["AWS_REGION"] == "eu-west-1"


def test_credentials_never_appear_in_the_error():
    with pytest.raises(ValueError) as e:
        fixloop.agent_env("bedrock", {"AWS_ACCESS_KEY_ID": "AKIASECRET"})
    assert "AKIASECRET" not in str(e.value)


def test_unknown_backend_refused():
    with pytest.raises(ValueError, match="unknown backend"):
        fixloop.agent_env("openai", {})


def test_fix_with_bedrock_and_no_credentials_fails_before_creating_output(tmp_path, monkeypatch):
    for k in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_BEARER_TOKEN_BEDROCK"):
        monkeypatch.delenv(k, raising=False)
    out = tmp_path / "o"
    with pytest.raises(ValueError):
        fixloop.fix("nope.json", str(tmp_path), str(out), backend="bedrock")
    assert not out.exists()
