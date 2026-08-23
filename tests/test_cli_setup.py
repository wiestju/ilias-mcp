import json

from typer.testing import CliRunner

from ilias_mcp import cli
from ilias_mcp.cli import app


def test_apply_json_target_creates_new_file(tmp_path):
    path = tmp_path / "sub" / "mcp.json"

    changed = cli._apply_json_target(path, "mcpServers", "ilias", "/fake/ilias-mcp-server")

    assert changed is True
    assert json.loads(path.read_text()) == {
        "mcpServers": {"ilias": {"command": "/fake/ilias-mcp-server"}}
    }


def test_apply_json_target_preserves_unrelated_content_and_backs_up(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"unrelated": "keep", "mcpServers": {"other": {"command": "x"}}}))

    changed = cli._apply_json_target(path, "mcpServers", "ilias", "/fake/ilias-mcp-server")

    assert changed is True
    data = json.loads(path.read_text())
    assert data["unrelated"] == "keep"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["ilias"] == {"command": "/fake/ilias-mcp-server"}
    assert path.with_suffix(".json.bak").exists()


def test_apply_json_target_idempotent(tmp_path):
    path = tmp_path / "config.json"
    cli._apply_json_target(path, "mcpServers", "ilias", "/fake/ilias-mcp-server")

    changed_again = cli._apply_json_target(path, "mcpServers", "ilias", "/fake/ilias-mcp-server")

    assert changed_again is False


def test_apply_toml_target_appends_table_and_preserves_content(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('some_setting = "value"\n\n[mcp_servers.other]\ncommand = "bar"\n')

    changed = cli._apply_toml_target(path, "mcp_servers", "ilias", "/fake/ilias-mcp-server")

    assert changed is True
    text = path.read_text()
    assert 'some_setting = "value"' in text
    assert "[mcp_servers.other]" in text
    assert "[mcp_servers.ilias]" in text
    assert path.with_suffix(".toml.bak").exists()


def test_apply_toml_target_idempotent(tmp_path):
    path = tmp_path / "config.toml"
    cli._apply_toml_target(path, "mcp_servers", "ilias", "/fake/ilias-mcp-server")

    changed_again = cli._apply_toml_target(path, "mcp_servers", "ilias", "/fake/ilias-mcp-server")

    assert changed_again is False


def test_setup_command_configures_target_client(tmp_path, monkeypatch):
    fake_target = tmp_path / "fake_claude" / "claude_desktop_config.json"
    monkeypatch.setitem(
        cli._SETUP_TARGETS,
        cli.SetupClient.claude_desktop,
        (fake_target, "json", "mcpServers"),
    )

    result = CliRunner().invoke(app, ["setup", "claude-desktop"])

    assert result.exit_code == 0
    assert "Configured" in result.stdout
    assert fake_target.exists()
    assert "ilias" in json.loads(fake_target.read_text())["mcpServers"]


def test_setup_command_is_idempotent_on_rerun(tmp_path, monkeypatch):
    fake_target = tmp_path / "fake_codex" / "config.toml"
    monkeypatch.setitem(
        cli._SETUP_TARGETS, cli.SetupClient.codex, (fake_target, "toml", "mcp_servers")
    )
    runner = CliRunner()
    runner.invoke(app, ["setup", "codex"])

    result = runner.invoke(app, ["setup", "codex"])

    assert result.exit_code == 0
    assert "Already configured" in result.stdout
